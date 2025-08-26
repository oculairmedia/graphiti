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

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from pydantic import BaseModel

logger = logging.getLogger(__name__)


@dataclass
class EpisodeMetrics:
    """Metrics for a single episode processing"""
    episode_id: str
    processing_start: datetime
    processing_end: Optional[datetime] = None
    total_duration_ms: Optional[float] = None
    entity_extraction_time_ms: Optional[float] = None
    edge_extraction_time_ms: Optional[float] = None
    deduplication_time_ms: Optional[float] = None
    entities_created: int = 0
    edges_created: int = 0
    llm_calls: int = 0
    embedding_calls: int = 0
    memory_used_mb: Optional[float] = None
    errors: List[str] = field(default_factory=list)
    
    def mark_complete(self):
        """Mark episode processing as complete and calculate duration"""
        self.processing_end = datetime.now()
        if self.processing_start:
            duration = self.processing_end - self.processing_start
            self.total_duration_ms = duration.total_seconds() * 1000


@dataclass
class LLMMetrics:
    """Metrics for LLM operations"""
    total_calls: int = 0
    total_tokens_used: int = 0
    total_cost_usd: float = 0.0
    avg_latency_ms: float = 0.0
    provider_breakdown: Dict[str, int] = field(default_factory=dict)
    error_rate: float = 0.0
    rate_limit_hits: int = 0


@dataclass
class EmbeddingMetrics:
    """Metrics for embedding operations"""
    total_calls: int = 0
    total_vectors_generated: int = 0
    avg_latency_ms: float = 0.0
    batch_sizes: List[int] = field(default_factory=list)
    error_rate: float = 0.0


@dataclass
class GraphMetrics:
    """Metrics for graph operations"""
    nodes_would_create: int = 0
    edges_would_create: int = 0
    nodes_would_update: int = 0
    edges_would_update: int = 0
    deduplication_savings: int = 0
    write_operations_intercepted: int = 0


@dataclass
class ResourceMetrics:
    """System resource usage metrics"""
    peak_memory_mb: float = 0.0
    avg_cpu_percent: float = 0.0
    disk_io_mb: float = 0.0
    network_io_mb: float = 0.0


class BenchmarkMetrics(BaseModel):
    """Comprehensive metrics for benchmarking runs"""
    run_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    total_episodes_processed: int = 0
    successful_episodes: int = 0
    failed_episodes: int = 0
    episodes_per_second: Optional[float] = None
    
    episode_metrics: List[EpisodeMetrics] = []
    llm_metrics: LLMMetrics = LLMMetrics()
    embedding_metrics: EmbeddingMetrics = EmbeddingMetrics()
    graph_metrics: GraphMetrics = GraphMetrics()
    resource_metrics: ResourceMetrics = ResourceMetrics()
    
    hyperparameters: Dict[str, Any] = {}
    
    class Config:
        arbitrary_types_allowed = True
    
    def mark_complete(self):
        """Mark the benchmark run as complete"""
        self.end_time = datetime.now()
        if self.start_time:
            duration = self.end_time - self.start_time
            if duration.total_seconds() > 0:
                self.episodes_per_second = self.total_episodes_processed / duration.total_seconds()
    
    def add_episode_metrics(self, episode_metrics: EpisodeMetrics):
        """Add metrics for a processed episode"""
        self.episode_metrics.append(episode_metrics)
        self.total_episodes_processed += 1
        if episode_metrics.errors:
            self.failed_episodes += 1
        else:
            self.successful_episodes += 1
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics for the benchmark run"""
        if not self.episode_metrics:
            return {}
        
        durations = [em.total_duration_ms for em in self.episode_metrics if em.total_duration_ms]
        
        return {
            'total_episodes': self.total_episodes_processed,
            'success_rate': self.successful_episodes / self.total_episodes_processed if self.total_episodes_processed > 0 else 0,
            'avg_episode_duration_ms': sum(durations) / len(durations) if durations else 0,
            'min_episode_duration_ms': min(durations) if durations else 0,
            'max_episode_duration_ms': max(durations) if durations else 0,
            'episodes_per_second': self.episodes_per_second,
            'total_entities_created': sum(em.entities_created for em in self.episode_metrics),
            'total_edges_created': sum(em.edges_created for em in self.episode_metrics),
        }


class MetricsCollector:
    """Collects and aggregates metrics during dry-run operations"""
    
    def __init__(self):
        self.current_episode: Optional[EpisodeMetrics] = None
        self.write_operations: List[Dict[str, Any]] = []
        self.llm_call_times: List[float] = []
        self.embedding_call_times: List[float] = []
        
    def start_episode_timing(self, episode_id: str) -> EpisodeMetrics:
        """Start timing a new episode"""
        self.current_episode = EpisodeMetrics(
            episode_id=episode_id,
            processing_start=datetime.now()
        )
        return self.current_episode
    
    def record_write_operation(self, query: str, params: Dict[str, Any]):
        """Record a write operation that was intercepted"""
        self.write_operations.append({
            'timestamp': datetime.now(),
            'query': query[:200],  # Truncate for storage
            'param_keys': list(params.keys()),
            'query_type': self._classify_query(query)
        })
        
    def record_llm_call(self, duration_ms: float, tokens_used: int = 0, provider: str = ''):
        """Record an LLM API call"""
        self.llm_call_times.append(duration_ms)
        if self.current_episode:
            self.current_episode.llm_calls += 1
            
    def record_embedding_call(self, duration_ms: float, vectors_generated: int = 0):
        """Record an embedding API call"""
        self.embedding_call_times.append(duration_ms)
        if self.current_episode:
            self.current_episode.embedding_calls += 1
    
    def record_entities_created(self, count: int):
        """Record entities that would be created"""
        if self.current_episode:
            self.current_episode.entities_created += count
    
    def record_edges_created(self, count: int):
        """Record edges that would be created"""
        if self.current_episode:
            self.current_episode.edges_created += count
            
    def record_error(self, error: str):
        """Record an error during processing"""
        if self.current_episode:
            self.current_episode.errors.append(error)
    
    def finish_episode(self) -> Optional[EpisodeMetrics]:
        """Finish timing the current episode and return metrics"""
        if self.current_episode:
            self.current_episode.mark_complete()
            episode = self.current_episode
            self.current_episode = None
            return episode
        return None
    
    def _classify_query(self, query: str) -> str:
        """Classify the type of database query"""
        query_lower = query.lower().strip()
        if query_lower.startswith('create'):
            return 'CREATE'
        elif query_lower.startswith('merge'):
            return 'MERGE'
        elif query_lower.startswith('set'):
            return 'UPDATE'
        elif query_lower.startswith('delete'):
            return 'DELETE'
        elif query_lower.startswith('match') and 'set' in query_lower:
            return 'UPDATE'
        else:
            return 'OTHER'
    
    def get_aggregate_metrics(self) -> Dict[str, Any]:
        """Get aggregated metrics across all operations"""
        return {
            'total_write_operations': len(self.write_operations),
            'avg_llm_call_time_ms': sum(self.llm_call_times) / len(self.llm_call_times) if self.llm_call_times else 0,
            'avg_embedding_call_time_ms': sum(self.embedding_call_times) / len(self.embedding_call_times) if self.embedding_call_times else 0,
            'write_operation_types': self._get_write_operation_breakdown(),
        }
    
    def _get_write_operation_breakdown(self) -> Dict[str, int]:
        """Get breakdown of write operations by type"""
        breakdown = {}
        for op in self.write_operations:
            query_type = op['query_type']
            breakdown[query_type] = breakdown.get(query_type, 0) + 1
        return breakdown