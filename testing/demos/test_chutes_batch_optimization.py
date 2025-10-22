#!/usr/bin/env python3
"""
Chutes AI Batch Processing Optimization Test
Tests different batch sizes to optimize API usage and prevent quota depletion.
"""

import asyncio
import time
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from graphiti_core import Graphiti
from graphiti_core.embedder import EmbedderClient
from graphiti_core.llm_client.chutes_client import ChutesClient, DEFAULT_MODEL, DEFAULT_BASE_URL
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.nodes import EpisodeType


@dataclass
class BatchTestResult:
    """Result from a batch processing test."""
    batch_size: int
    total_episodes: int
    successful_episodes: int
    total_api_calls: int
    total_time: float
    avg_time_per_episode: float
    api_calls_per_episode: float
    error_count: int
    quota_efficient: bool


class OllamaEmbedder(EmbedderClient):
    """Ollama embedder for hybrid approach."""
    
    def __init__(self, base_url: str = 'http://192.168.50.80:11434/v1', model: str = 'mxbai-embed-large'):
        self.base_url = base_url
        self.model = model
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(base_url=base_url, api_key='ollama')
        print(f'✓ Initialized OllamaEmbedder with {model}')

    async def create(self, input_data: list[str]) -> list[list[float]]:
        """Create embeddings using Ollama."""
        try:
            response = await self.client.embeddings.create(model=self.model, input=input_data)
            return [item.embedding for item in response.data]
        except Exception as e:
            print(f'❌ Error creating embeddings: {e}')
            raise


class ChutesAPICallTracker:
    """Track API calls to monitor quota usage."""
    
    def __init__(self):
        self.call_count = 0
        self.start_time = None
        self.call_log = []
    
    def start_tracking(self):
        """Start tracking API calls."""
        self.call_count = 0
        self.start_time = time.time()
        self.call_log = []
        print(f'🔍 Started API call tracking at {datetime.now().isoformat()}')
    
    def record_call(self, operation: str, tokens_estimated: int = 0):
        """Record an API call."""
        self.call_count += 1
        self.call_log.append({
            'timestamp': time.time(),
            'operation': operation,
            'call_number': self.call_count,
            'tokens_estimated': tokens_estimated
        })
        print(f'   📞 API Call #{self.call_count}: {operation} (~{tokens_estimated} tokens)')
    
    def get_stats(self) -> Dict[str, Any]:
        """Get tracking statistics."""
        if not self.start_time:
            return {}
        
        duration = time.time() - self.start_time
        return {
            'total_calls': self.call_count,
            'duration_seconds': duration,
            'calls_per_minute': (self.call_count / duration) * 60 if duration > 0 else 0,
            'estimated_total_tokens': sum(call['tokens_estimated'] for call in self.call_log)
        }


async def setup_graphiti_with_tracking(tracker: ChutesAPICallTracker):
    """Set up Graphiti with API call tracking."""
    
    chutes_config = LLMConfig(
        api_key=os.getenv('CHUTES_API_KEY'),
        base_url=DEFAULT_BASE_URL,
        model=DEFAULT_MODEL,
        temperature=0.1,  # Lower temperature for consistency in batching
        max_tokens=1500,  # Slightly lower to be conservative
    )
    
    # Create a wrapper client that tracks API calls
    chutes_client = ChutesClient(config=chutes_config)
    original_generate = chutes_client._generate_response
    
    async def tracked_generate_response(*args, **kwargs):
        """Wrapper to track API calls."""
        # Estimate tokens based on input
        messages = args[0] if args else []
        estimated_tokens = sum(len(msg.content.split()) * 1.3 for msg in messages)  # Rough estimate
        tracker.record_call('entity_extraction', int(estimated_tokens))
        return await original_generate(*args, **kwargs)
    
    chutes_client._generate_response = tracked_generate_response
    
    ollama_embedder = OllamaEmbedder()
    
    graphiti = Graphiti(
        uri='bolt://localhost:6389',
        user='',
        password='',
        embedder=ollama_embedder,
        llm_client=chutes_client,
    )
    
    await graphiti.build_indices_and_constraints()
    return graphiti


def generate_batch_test_data(batch_size: int) -> List[Dict[str, Any]]:
    """Generate test episodes for batch processing."""
    
    base_episodes = [
        {
            'name': 'AI Research Collaboration {i}',
            'content': '''
            Research team led by Dr. Sarah Chen published breakthrough results in neural architecture search.
            The work focuses on efficient transformer variants with reduced computational overhead.
            Key findings include 30% speed improvement and 15% accuracy gains on language tasks.
            Collaboration includes Stanford University, MIT, and Google Research teams.
            The paper was accepted to NeurIPS 2024 with strong reviewer scores.
            ''',
            'source': 'AI Research Journal'
        },
        {
            'name': 'Industry Deployment Case Study {i}',
            'content': '''
            Fortune 500 company deployed large language model for customer service automation.
            Implementation team includes Engineering Director Mike Johnson and ML Lead Lisa Wang.
            System handles 10,000+ queries daily with 85% automation rate and 92% satisfaction score.
            Technical stack uses Kubernetes orchestration with GPU clusters for model serving.
            Cost savings estimated at $2.3M annually compared to human-only support.
            ''',
            'source': 'Tech Industry Report'
        },
        {
            'name': 'Academic Conference Proceedings {i}',
            'content': '''
            International Conference on Machine Learning featured 1,200+ submissions this year.
            Program Committee Chair Prof. David Kim announced record participation from 67 countries.
            Notable trends include multimodal learning, efficient model architectures, and AI safety.
            Keynote speakers include Yoshua Bengio, Fei-Fei Li, and Andrew Ng discussing future directions.
            Best paper award went to UC Berkeley team for work on federated learning privacy.
            ''',
            'source': 'Academic Conference'
        }
    ]
    
    episodes = []
    for i in range(batch_size):
        base_episode = base_episodes[i % len(base_episodes)]
        episode = {
            'name': base_episode['name'].format(i=i+1),
            'content': base_episode['content'],
            'source': base_episode['source'],
            'timestamp': datetime.now() - timedelta(hours=i)
        }
        episodes.append(episode)
    
    return episodes


async def test_batch_processing(batch_size: int, timeout_per_episode: int = 120) -> BatchTestResult:
    """Test batch processing with specific batch size."""
    
    print(f'\n🧪 Testing Batch Size: {batch_size}')
    print(f'   Timeout per episode: {timeout_per_episode}s')
    
    tracker = ChutesAPICallTracker()
    tracker.start_tracking()
    
    try:
        # Set up Graphiti with tracking
        graphiti = await setup_graphiti_with_tracking(tracker)
        
        # Generate test data
        episodes = generate_batch_test_data(batch_size)
        print(f'   Generated {len(episodes)} test episodes')
        
        # Process episodes
        successful_episodes = 0
        error_count = 0
        start_time = time.time()
        
        for i, episode in enumerate(episodes):
            try:
                print(f'\n   Processing episode {i+1}/{len(episodes)}: {episode["name"]}')
                
                result = await asyncio.wait_for(
                    graphiti.add_episode(
                        name=episode['name'],
                        episode_body=episode['content'],
                        source_description=episode['source'],
                        reference_time=episode['timestamp'],
                        source=EpisodeType.text,
                    ),
                    timeout=timeout_per_episode
                )
                
                if result:
                    successful_episodes += 1
                    print(f'   ✅ Episode {i+1} processed successfully')
                    
                    # Show extraction results
                    if hasattr(result, 'nodes') and result.nodes:
                        print(f'      Entities: {len(result.nodes)}')
                    if hasattr(result, 'edges') and result.edges:
                        print(f'      Relationships: {len(result.edges)}')
                else:
                    error_count += 1
                    print(f'   ⚠️ Episode {i+1} returned no result')
                    
            except asyncio.TimeoutError:
                error_count += 1
                print(f'   ⏱️ Episode {i+1} timed out after {timeout_per_episode}s')
            except Exception as e:
                error_count += 1
                print(f'   ❌ Episode {i+1} failed: {e}')
                
            # Small pause between episodes to be respectful to API
            await asyncio.sleep(1)
        
        total_time = time.time() - start_time
        await graphiti.close()
        
        # Get tracking stats
        stats = tracker.get_stats()
        
        # Calculate metrics
        avg_time_per_episode = total_time / len(episodes) if episodes else 0
        api_calls_per_episode = stats['total_calls'] / len(episodes) if episodes else 0
        quota_efficient = api_calls_per_episode <= 3  # Target: max 3 API calls per episode
        
        result = BatchTestResult(
            batch_size=batch_size,
            total_episodes=len(episodes),
            successful_episodes=successful_episodes,
            total_api_calls=stats['total_calls'],
            total_time=total_time,
            avg_time_per_episode=avg_time_per_episode,
            api_calls_per_episode=api_calls_per_episode,
            error_count=error_count,
            quota_efficient=quota_efficient
        )
        
        # Print batch results
        print(f'\n📊 Batch Size {batch_size} Results:')
        print(f'   Success Rate: {successful_episodes}/{len(episodes)} ({successful_episodes/len(episodes)*100:.1f}%)')
        print(f'   Total API Calls: {stats["total_calls"]}')
        print(f'   API Calls per Episode: {api_calls_per_episode:.1f}')
        print(f'   Total Time: {total_time:.1f}s ({total_time/60:.1f} minutes)')
        print(f'   Avg Time per Episode: {avg_time_per_episode:.1f}s')
        print(f'   Quota Efficient: {"✅" if quota_efficient else "❌"} (target: ≤3 calls/episode)')
        print(f'   Estimated Tokens: {stats["estimated_total_tokens"]:,}')
        
        return result
        
    except Exception as e:
        print(f'❌ Batch test failed: {e}')
        return BatchTestResult(
            batch_size=batch_size,
            total_episodes=0,
            successful_episodes=0,
            total_api_calls=0,
            total_time=0,
            avg_time_per_episode=0,
            api_calls_per_episode=0,
            error_count=1,
            quota_efficient=False
        )


async def run_batch_optimization_tests():
    """Run comprehensive batch optimization tests."""
    
    print('🚀 Chutes AI Batch Processing Optimization Tests')
    print('=' * 80)
    print(f'Start Time: {datetime.now().isoformat()}')
    
    # Check prerequisites
    if not os.getenv('CHUTES_API_KEY'):
        print('❌ CHUTES_API_KEY not found')
        return
    
    # Test different batch sizes
    batch_sizes = [1, 3, 5, 10]  # Start small to conserve quota
    results = []
    
    print(f'\n🔄 Testing batch sizes: {batch_sizes}')
    print('💡 Strategy: Find optimal balance between speed and quota usage')
    
    for batch_size in batch_sizes:
        try:
            result = await test_batch_processing(batch_size)
            results.append(result)
            
            # Break if we're using too many API calls per episode
            if result.api_calls_per_episode > 5:
                print(f'⚠️ Stopping tests - batch size {batch_size} uses too many API calls per episode')
                break
                
            # Pause between batch tests to avoid rate limits
            print(f'⏳ Pausing 10 seconds before next batch test...')
            await asyncio.sleep(10)
            
        except Exception as e:
            print(f'❌ Batch size {batch_size} test failed: {e}')
    
    # Analyze results
    print(f'\n📈 BATCH OPTIMIZATION ANALYSIS')
    print('=' * 80)
    
    if not results:
        print('❌ No successful batch tests completed')
        return
    
    # Summary table
    print(f'\n📊 Results Summary:')
    print(f'{"Batch Size":<12} {"Success Rate":<12} {"API Calls":<12} {"Calls/Episode":<15} {"Time/Episode":<15} {"Efficient":<10}')
    print('-' * 90)
    
    for result in results:
        success_rate = f'{result.successful_episodes}/{result.total_episodes}'
        efficiency = '✅' if result.quota_efficient else '❌'
        print(f'{result.batch_size:<12} {success_rate:<12} {result.total_api_calls:<12} {result.api_calls_per_episode:<15.1f} {result.avg_time_per_episode:<15.1f}s {efficiency:<10}')
    
    # Find optimal batch size
    efficient_results = [r for r in results if r.quota_efficient and r.successful_episodes > 0]
    
    if efficient_results:
        # Sort by success rate, then by speed
        optimal = max(efficient_results, key=lambda r: (r.successful_episodes/r.total_episodes, -r.avg_time_per_episode))
        
        print(f'\n🎯 OPTIMAL CONFIGURATION:')
        print(f'   Recommended Batch Size: {optimal.batch_size}')
        print(f'   Expected Success Rate: {optimal.successful_episodes/optimal.total_episodes*100:.1f}%')
        print(f'   API Calls per Episode: {optimal.api_calls_per_episode:.1f}')
        print(f'   Processing Time per Episode: {optimal.avg_time_per_episode:.1f}s')
        
        # Calculate quota estimates
        daily_quota_estimate = 100000  # Assume 100k tokens per day
        episodes_per_day = daily_quota_estimate / (optimal.api_calls_per_episode * 1000)  # Rough estimate
        
        print(f'\n💰 QUOTA PROJECTIONS:')
        print(f'   Episodes processable per day (est.): {episodes_per_day:.0f}')
        print(f'   Recommended daily batch limit: {int(episodes_per_day * 0.8)}')  # 80% safety margin
        
    else:
        print(f'\n⚠️ No quota-efficient batch sizes found')
        print(f'   All tested sizes exceed 3 API calls per episode')
        print(f'   Consider optimizing prompts or reducing episode complexity')
    
    # Recommendations
    print(f'\n💡 PRODUCTION RECOMMENDATIONS:')
    
    if efficient_results:
        optimal = efficient_results[0]
        print(f'   1. Use batch size: {optimal.batch_size}')
        print(f'   2. Set timeout per episode: 120s')
        print(f'   3. Add 2-second pause between episodes')
        print(f'   4. Monitor API usage: target ≤3 calls per episode')
        print(f'   5. Implement quota monitoring and automatic throttling')
    else:
        print(f'   1. Start with batch size 1 for safety')
        print(f'   2. Increase timeout to 180s per episode')
        print(f'   3. Add 5-second pause between episodes') 
        print(f'   4. Optimize prompts to reduce token usage')
        print(f'   5. Consider using smaller model for initial extraction')
    
    print(f'\n🔧 IMPLEMENTATION SETTINGS:')
    print(f'   Environment Variables:')
    print(f'   - CHUTES_BATCH_SIZE={optimal.batch_size if efficient_results else 1}')
    print(f'   - CHUTES_EPISODE_TIMEOUT=120')
    print(f'   - CHUTES_INTER_EPISODE_DELAY=2')
    print(f'   - CHUTES_QUOTA_MONITOR=true')
    
    print(f'\n🎉 Batch Optimization Tests Completed!')
    print(f'End Time: {datetime.now().isoformat()}')


async def main():
    """Main batch optimization test runner."""
    await run_batch_optimization_tests()


if __name__ == '__main__':
    asyncio.run(main())