"""
Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import asyncio
import logging
import time
import traceback
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, AsyncGenerator
from uuid import uuid4
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None

try:
    import pyinstrument
    PYINSTRUMENT_AVAILABLE = True
except ImportError:
    PYINSTRUMENT_AVAILABLE = False
    pyinstrument = None

from graphiti_core.graphiti import Graphiti
from graphiti_core.nodes import EpisodicNode
from graphiti_core.utils.maintenance.graph_data_operations import retrieve_episodes
from .dry_run_driver import create_dry_run_driver
from .metrics import MetricsCollector, EpisodeMetrics, BenchmarkMetrics
from .config import DryRunConfig

logger = logging.getLogger(__name__)


class DryRunWorker:
    """Worker service that processes episodes in dry-run mode for benchmarking"""
    
    def __init__(self, graphiti: Graphiti, config: DryRunConfig):
        self.graphiti = graphiti
        self.config = config
        self.metrics_collector = MetricsCollector()
        self.benchmark_metrics = BenchmarkMetrics(
            run_id=config.run_id or str(uuid4()),
            start_time=datetime.now(),
            hyperparameters=config.hyperparameters
        )
        
        # Wrap the driver with dry-run wrapper
        self.original_driver = graphiti.driver
        self.dry_run_driver = create_dry_run_driver(
            self.original_driver, 
            self.metrics_collector
        )
        
        # Create dry-run Graphiti instance with the dry-run driver
        self.dry_run_graphiti = Graphiti(
            graph_driver=self.dry_run_driver,
            llm_client=graphiti.llm_client,
            embedder=graphiti.embedder,
            cross_encoder=graphiti.cross_encoder,
        )
        
        self.profiler = None
        if config.enable_profiling and PYINSTRUMENT_AVAILABLE:
            self.profiler = pyinstrument.Profiler()
    
    async def run_benchmark(self) -> BenchmarkMetrics:
        """Run the complete dry-run benchmark"""
        logger.info(f"Starting dry-run benchmark {self.benchmark_metrics.run_id}")
        
        # Validate configuration
        validation_errors = self.config.validate()
        if validation_errors:
            raise ValueError(f"Configuration validation failed: {validation_errors}")
        
        try:
            if self.profiler:
                self.profiler.start()
            
            # Get episodes to process
            episodes = await self._get_episodes()
            logger.info(f"Found {len(episodes)} episodes to process")
            
            # Process episodes in batches
            processed_count = 0
            async for batch in self._batch_episodes(episodes):
                batch_results = await self._process_batch(batch)
                for episode_metrics in batch_results:
                    self.benchmark_metrics.add_episode_metrics(episode_metrics)
                    processed_count += 1
                
                logger.info(f"Processed {processed_count}/{len(episodes)} episodes")
                
                # Check for early termination conditions
                if self._should_terminate():
                    logger.warning("Early termination triggered")
                    break
            
            self.benchmark_metrics.mark_complete()
            
            # Save results
            await self._save_results()
            
            logger.info(f"Benchmark complete: {self.benchmark_metrics.run_id}")
            return self.benchmark_metrics
            
        except Exception as e:
            logger.error(f"Benchmark failed: {e}")
            logger.error(traceback.format_exc())
            raise
        finally:
            if self.profiler:
                self.profiler.stop()
                if self.config.enable_profiling:
                    await self._save_profile()
    
    async def _get_episodes(self) -> List[EpisodicNode]:
        """Retrieve episodes for processing based on configuration"""
        if self.config.episodes_source == "database":
            # Use retrieve_episodes function from graph_data_operations
            # For dry-run benchmarking, we'll get recent episodes
            from graphiti_core.utils.datetime_utils import utc_now
            
            episodes = await retrieve_episodes(
                driver=self.original_driver,
                reference_time=utc_now(),
                last_n=self.config.episodes_limit or 100,
                group_ids=self.config.episodes_filter.get('group_ids'),
                source=self.config.episodes_filter.get('source'),
            )
            
            # If we have a specific episode limit, truncate the list
            if self.config.episodes_limit and len(episodes) > self.config.episodes_limit:
                episodes = episodes[:self.config.episodes_limit]
            
            return episodes
        
        else:
            raise NotImplementedError(f"Episodes source '{self.config.episodes_source}' not implemented")
    
    async def _batch_episodes(self, episodes: List[EpisodicNode]) -> AsyncGenerator[List[EpisodicNode], None]:
        """Yield episodes in configured batch sizes"""
        batch_size = self.config.batch_size
        for i in range(0, len(episodes), batch_size):
            yield episodes[i:i + batch_size]
    
    async def _process_batch(self, episodes: List[EpisodicNode]) -> List[EpisodeMetrics]:
        """Process a batch of episodes concurrently"""
        semaphore = asyncio.Semaphore(self.config.max_concurrent_episodes)
        
        async def process_single(episode: EpisodicNode) -> EpisodeMetrics:
            async with semaphore:
                return await self._process_episode(episode)
        
        tasks = [process_single(episode) for episode in episodes]
        return await asyncio.gather(*tasks, return_exceptions=False)
    
    async def _process_episode(self, episode: EpisodicNode) -> EpisodeMetrics:
        """Process a single episode and collect metrics"""
        episode_metrics = self.metrics_collector.start_episode_timing(str(episode.uuid))
        
        try:
            # Record memory usage before processing
            if self.config.collect_memory_stats and PSUTIL_AVAILABLE:
                process = psutil.Process()
                memory_before = process.memory_info().rss / 1024 / 1024  # MB
                episode_metrics.memory_used_mb = memory_before
            
            # Apply hyperparameters if specified
            original_config = {}
            if self.config.hyperparameters:
                original_config = await self._apply_hyperparameters()
            
            try:
                # Process the episode through the dry-run pipeline
                start_time = time.time()
                
                await self.dry_run_graphiti.add_episode(
                    name=episode.name,
                    episode_body=episode.content,
                    source=episode.source,
                    source_description=episode.source_description,
                    group_id=episode.group_id,
                    uuid=episode.uuid,
                    reference_time=episode.valid_at
                )
                
                end_time = time.time()
                episode_metrics.total_duration_ms = (end_time - start_time) * 1000
                
                logger.debug(f"Processed episode {episode.uuid} in {episode_metrics.total_duration_ms:.2f}ms")
                
            finally:
                # Restore original configuration
                if original_config:
                    await self._restore_hyperparameters(original_config)
            
            # Record final memory usage
            if self.config.collect_memory_stats and PSUTIL_AVAILABLE:
                memory_after = process.memory_info().rss / 1024 / 1024  # MB
                episode_metrics.memory_used_mb = max(episode_metrics.memory_used_mb or 0, memory_after)
            
        except Exception as e:
            logger.error(f"Error processing episode {episode.uuid}: {e}")
            episode_metrics.errors.append(str(e))
        
        finally:
            episode_metrics.mark_complete()
        
        return episode_metrics
    
    async def _apply_hyperparameters(self) -> Dict[str, Any]:
        """Apply hyperparameters to the dry-run Graphiti instance"""
        original_config = {}
        
        for param_name, param_value in self.config.hyperparameters.items():
            try:
                if param_name == 'temperature':
                    if hasattr(self.dry_run_graphiti.llm_client, 'temperature'):
                        original_config['temperature'] = self.dry_run_graphiti.llm_client.temperature
                        self.dry_run_graphiti.llm_client.temperature = param_value
                
                elif param_name == 'max_tokens':
                    if hasattr(self.dry_run_graphiti.llm_client, 'max_tokens'):
                        original_config['max_tokens'] = self.dry_run_graphiti.llm_client.max_tokens
                        self.dry_run_graphiti.llm_client.max_tokens = param_value
                
                elif param_name == 'search_limit':
                    if hasattr(self.dry_run_graphiti.search, 'limit'):
                        original_config['search_limit'] = self.dry_run_graphiti.search.limit
                        self.dry_run_graphiti.search.limit = param_value
                
                # Add more hyperparameters as needed
                logger.debug(f"Applied hyperparameter {param_name}={param_value}")
                
            except Exception as e:
                logger.warning(f"Failed to apply hyperparameter {param_name}={param_value}: {e}")
        
        return original_config
    
    async def _restore_hyperparameters(self, original_config: Dict[str, Any]):
        """Restore original hyperparameter values"""
        for param_name, param_value in original_config.items():
            try:
                if param_name == 'temperature':
                    self.dry_run_graphiti.llm_client.temperature = param_value
                elif param_name == 'max_tokens':
                    self.dry_run_graphiti.llm_client.max_tokens = param_value
                elif param_name == 'search_limit':
                    self.dry_run_graphiti.search.limit = param_value
            except Exception as e:
                logger.warning(f"Failed to restore hyperparameter {param_name}: {e}")
    
    def _should_terminate(self) -> bool:
        """Check if benchmark should terminate early"""
        # Check runtime limit
        if self.config.safety.max_runtime_minutes > 0:
            elapsed_minutes = (datetime.now() - self.benchmark_metrics.start_time).total_seconds() / 60
            if elapsed_minutes > self.config.safety.max_runtime_minutes:
                logger.warning(f"Runtime limit exceeded: {elapsed_minutes:.1f} minutes")
                return True
        
        # Check episode limit
        if (self.config.safety.max_episodes_per_run > 0 and 
            self.benchmark_metrics.total_episodes_processed >= self.config.safety.max_episodes_per_run):
            logger.warning(f"Episode limit reached: {self.benchmark_metrics.total_episodes_processed}")
            return True
        
        return False
    
    async def _save_results(self):
        """Save benchmark results to configured output formats"""
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save benchmark metrics
        if 'json' in self.config.export_formats:
            import json
            results_file = self.config.output_dir / f"{self.benchmark_metrics.run_id}_results.json"
            
            results_data = {
                'benchmark_metrics': self.benchmark_metrics.dict(),
                'summary_stats': self.benchmark_metrics.get_summary_stats(),
                'config': self.config.to_dict(),
                'aggregate_metrics': self.metrics_collector.get_aggregate_metrics(),
            }
            
            with open(results_file, 'w') as f:
                json.dump(results_data, f, indent=2, default=str)
            
            logger.info(f"Results saved to {results_file}")
        
        if 'csv' in self.config.export_formats:
            await self._save_csv_results()
    
    async def _save_csv_results(self):
        """Save episode metrics to CSV format"""
        import csv
        
        csv_file = self.config.output_dir / f"{self.benchmark_metrics.run_id}_episodes.csv"
        
        if not self.benchmark_metrics.episode_metrics:
            return
        
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'episode_id', 'total_duration_ms', 'entity_extraction_time_ms',
                'edge_extraction_time_ms', 'deduplication_time_ms',
                'entities_created', 'edges_created', 'llm_calls',
                'embedding_calls', 'memory_used_mb', 'errors'
            ])
            
            # Data rows
            for episode_metrics in self.benchmark_metrics.episode_metrics:
                writer.writerow([
                    episode_metrics.episode_id,
                    episode_metrics.total_duration_ms,
                    episode_metrics.entity_extraction_time_ms,
                    episode_metrics.edge_extraction_time_ms,
                    episode_metrics.deduplication_time_ms,
                    episode_metrics.entities_created,
                    episode_metrics.edges_created,
                    episode_metrics.llm_calls,
                    episode_metrics.embedding_calls,
                    episode_metrics.memory_used_mb,
                    '; '.join(episode_metrics.errors) if episode_metrics.errors else ''
                ])
        
        logger.info(f"Episode metrics saved to {csv_file}")
    
    async def _save_profile(self):
        """Save performance profile if enabled"""
        if not self.profiler:
            return
        
        profile_file = self.config.output_dir / f"{self.benchmark_metrics.run_id}_profile.html"
        with open(profile_file, 'w') as f:
            f.write(self.profiler.output_html())
        
        logger.info(f"Performance profile saved to {profile_file}")
    
    async def close(self):
        """Clean up resources"""
        if self.dry_run_driver:
            await self.dry_run_driver.close()