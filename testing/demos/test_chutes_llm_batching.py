#!/usr/bin/env python3
"""
Chutes AI LLM-Level Batching Test
Tests actual LLM request batching to minimize API calls and quota usage.
"""

import asyncio
import time
import os
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from graphiti_core.llm_client.chutes_client import ChutesClient, DEFAULT_MODEL, DEFAULT_BASE_URL
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.prompts.models import Message


@dataclass
class BatchingTestResult:
    """Result from LLM batching test."""
    strategy: str
    total_episodes: int
    total_api_calls: int
    successful_extractions: int
    total_time: float
    avg_time_per_episode: float
    api_calls_per_episode: float
    total_entities_extracted: int
    total_relationships_extracted: int
    quota_efficiency_score: float


class ChutesLLMBatcher:
    """Experimental LLM request batcher for Chutes AI."""
    
    def __init__(self, chutes_client: ChutesClient):
        self.client = chutes_client
        self.api_call_count = 0
        
    async def extract_entities_individual(self, episodes: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Extract entities using individual API calls (baseline)."""
        
        results = []
        self.api_call_count = 0
        
        for episode in episodes:
            try:
                # Individual entity extraction
                messages = [
                    Message(role='system', content='''
You are an expert at extracting entities and relationships from text.
Extract all named entities (people, organizations, locations, concepts) and their relationships.
Return a JSON object with this structure:
{
    "entities": [
        {"name": "Entity Name", "type": "Person|Organization|Location|Concept", "context": "brief context"}
    ],
    "relationships": [
        {"source": "Entity1", "target": "Entity2", "relationship_type": "relationship", "context": "context"}
    ]
}
                    '''),
                    Message(role='user', content=f'''
Extract entities and relationships from this text:

Title: {episode['name']}
Content: {episode['content']}
Source: {episode['source']}
                    ''')
                ]
                
                self.api_call_count += 1
                result = await self.client.generate_response(messages)
                results.append(result)
                
            except Exception as e:
                print(f'❌ Individual extraction failed for {episode["name"]}: {e}')
                results.append({'entities': [], 'relationships': []})
        
        return results
    
    async def extract_entities_batched(self, episodes: List[Dict[str, str]], batch_size: int = 3) -> List[Dict[str, Any]]:
        """Extract entities using batched API calls (experimental)."""
        
        results = []
        self.api_call_count = 0
        
        # Process in batches
        for i in range(0, len(episodes), batch_size):
            batch = episodes[i:i + batch_size]
            
            try:
                # Create a single prompt for multiple episodes
                batch_content = ""
                for j, episode in enumerate(batch):
                    batch_content += f'''
=== EPISODE {j+1} ===
Title: {episode['name']}
Content: {episode['content']}
Source: {episode['source']}

'''
                
                messages = [
                    Message(role='system', content=f'''
You are an expert at extracting entities and relationships from text.
I will provide {len(batch)} episodes. For each episode, extract entities and relationships.
Return a JSON array with {len(batch)} objects, each with this structure:
{{
    "episode_index": 1,
    "entities": [
        {{"name": "Entity Name", "type": "Person|Organization|Location|Concept", "context": "brief context"}}
    ],
    "relationships": [
        {{"source": "Entity1", "target": "Entity2", "relationship_type": "relationship", "context": "context"}}
    ]
}}
                    '''),
                    Message(role='user', content=f'Extract entities and relationships from these {len(batch)} episodes:\n\n{batch_content}')
                ]
                
                self.api_call_count += 1
                batch_result = await self.client.generate_response(messages)
                
                # Parse batch result
                if isinstance(batch_result, list):
                    for item in batch_result:
                        results.append(item)
                elif isinstance(batch_result, dict) and 'episodes' in batch_result:
                    results.extend(batch_result['episodes'])
                else:
                    # Try to parse as single batch response
                    for j in range(len(batch)):
                        results.append(batch_result if isinstance(batch_result, dict) else {'entities': [], 'relationships': []})
                
            except Exception as e:
                print(f'❌ Batch extraction failed for batch {i//batch_size + 1}: {e}')
                # Add empty results for failed batch
                for j in range(len(batch)):
                    results.append({'entities': [], 'relationships': []})
        
        return results
    
    async def extract_entities_mega_batch(self, episodes: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Extract entities using single mega API call (aggressive batching)."""
        
        self.api_call_count = 0
        
        try:
            # Create single prompt for all episodes
            all_content = ""
            for i, episode in enumerate(episodes):
                all_content += f'''
=== EPISODE {i+1} ===
Title: {episode['name']}
Content: {episode['content']}
Source: {episode['source']}

'''
            
            messages = [
                Message(role='system', content=f'''
You are an expert at extracting entities and relationships from text.
I will provide {len(episodes)} episodes. For each episode, extract entities and relationships.
Return a JSON object with this structure:
{{
    "episodes": [
        {{
            "episode_index": 1,
            "entities": [
                {{"name": "Entity Name", "type": "Person|Organization|Location|Concept", "context": "brief context"}}
            ],
            "relationships": [
                {{"source": "Entity1", "target": "Entity2", "relationship_type": "relationship", "context": "context"}}
            ]
        }}
    ]
}}
Ensure you return exactly {len(episodes)} episode objects in the episodes array.
                '''),
                Message(role='user', content=f'Extract entities and relationships from these {len(episodes)} episodes:\n\n{all_content}')
            ]
            
            self.api_call_count += 1
            mega_result = await self.client.generate_response(messages)
            
            # Parse mega result
            if isinstance(mega_result, dict) and 'episodes' in mega_result:
                results = mega_result['episodes']
                # Pad with empty results if needed
                while len(results) < len(episodes):
                    results.append({'entities': [], 'relationships': []})
                return results[:len(episodes)]  # Trim if too many
            else:
                # Fallback: distribute single result across all episodes
                return [mega_result if isinstance(mega_result, dict) else {'entities': [], 'relationships': []} for _ in episodes]
        
        except Exception as e:
            print(f'❌ Mega batch extraction failed: {e}')
            return [{'entities': [], 'relationships': []} for _ in episodes]


def generate_test_episodes(count: int = 5) -> List[Dict[str, str]]:
    """Generate test episodes for batching experiments."""
    
    episodes = [
        {
            'name': 'AI Research Breakthrough at Stanford',
            'content': '''
            Stanford University's AI Lab, led by Dr. Sarah Chen, announced a breakthrough in transformer efficiency.
            The research team includes graduate students Mike Johnson and Lisa Wang.
            Their new architecture reduces computational requirements by 40% while maintaining accuracy.
            The work was funded by Google Research and the National Science Foundation.
            Results will be presented at NeurIPS 2024 by Dr. Chen and the team.
            ''',
            'source': 'Stanford AI Lab Press Release'
        },
        {
            'name': 'Tech Company AI Deployment',
            'content': '''
            TechCorp Inc. deployed a large language model for customer service automation.
            CTO David Park led the implementation with ML Engineer Maria Rodriguez.
            The system processes 50,000 daily queries with 89% automation rate.
            AWS provided the cloud infrastructure with NVIDIA A100 GPUs.
            Customer satisfaction increased by 23% according to VP Sarah Kim.
            ''',
            'source': 'TechCorp Press Release'
        },
        {
            'name': 'Academic Conference ML Trends',
            'content': '''
            International Conference on Machine Learning featured 2,000 submissions.
            Program Chair Prof. Alex Thompson from MIT organized the event.
            Key trends include multimodal AI, federated learning, and model efficiency.
            Keynote speakers were Yoshua Bengio, Geoffrey Hinton, and Yann LeCun.
            Best Paper Award went to UC Berkeley team led by Dr. Jennifer Wu.
            ''',
            'source': 'ICML 2024 Proceedings'
        },
        {
            'name': 'Industry Partnership Announcement',
            'content': '''
            Microsoft and OpenAI announced expanded partnership for AI research.
            Microsoft CEO Satya Nadella and OpenAI CEO Sam Altman signed the agreement.
            Investment totals $10 billion over three years for compute resources.
            Focus areas include GPT-5 development and multimodal AI systems.
            Partnership also involves collaboration with Stanford and MIT researchers.
            ''',
            'source': 'Microsoft Press Release'
        },
        {
            'name': 'Open Source AI Model Release',
            'content': '''
            Meta AI released Llama-3 as an open source language model.
            Chief AI Scientist Yann LeCun announced the release at a conference.
            The model was trained on 15 trillion tokens using custom hardware.
            Engineering team led by Susan Zhang optimized for efficiency and safety.
            Model weights are available through Hugging Face and direct download.
            ''',
            'source': 'Meta AI Blog'
        }
    ]
    
    return episodes[:count]


async def test_batching_strategy(strategy_name: str, batcher: ChutesLLMBatcher, episodes: List[Dict[str, str]], **kwargs) -> BatchingTestResult:
    """Test a specific batching strategy."""
    
    print(f'\n🧪 Testing Strategy: {strategy_name}')
    
    start_time = time.time()
    
    if strategy_name == 'individual':
        results = await batcher.extract_entities_individual(episodes)
    elif strategy_name == 'batched':
        batch_size = kwargs.get('batch_size', 3)
        print(f'   Batch size: {batch_size}')
        results = await batcher.extract_entities_batched(episodes, batch_size)
    elif strategy_name == 'mega_batch':
        results = await batcher.extract_entities_mega_batch(episodes)
    else:
        raise ValueError(f'Unknown strategy: {strategy_name}')
    
    total_time = time.time() - start_time
    
    # Analyze results
    successful_extractions = 0
    total_entities = 0
    total_relationships = 0
    
    for result in results:
        if result and isinstance(result, dict):
            successful_extractions += 1
            if 'entities' in result:
                total_entities += len(result['entities'])
            if 'relationships' in result:
                total_relationships += len(result['relationships'])
    
    # Calculate metrics
    api_calls_per_episode = batcher.api_call_count / len(episodes) if episodes else 0
    avg_time_per_episode = total_time / len(episodes) if episodes else 0
    
    # Quota efficiency score (lower is better)
    # Formula: (API calls per episode) * (average time per episode in minutes)
    quota_efficiency_score = api_calls_per_episode * (avg_time_per_episode / 60)
    
    result = BatchingTestResult(
        strategy=strategy_name,
        total_episodes=len(episodes),
        total_api_calls=batcher.api_call_count,
        successful_extractions=successful_extractions,
        total_time=total_time,
        avg_time_per_episode=avg_time_per_episode,
        api_calls_per_episode=api_calls_per_episode,
        total_entities_extracted=total_entities,
        total_relationships_extracted=total_relationships,
        quota_efficiency_score=quota_efficiency_score
    )
    
    # Print results
    print(f'   ✅ Completed in {total_time:.1f}s')
    print(f'   API Calls: {batcher.api_call_count}')
    print(f'   API Calls per Episode: {api_calls_per_episode:.1f}')
    print(f'   Successful Extractions: {successful_extractions}/{len(episodes)}')
    print(f'   Entities Extracted: {total_entities}')
    print(f'   Relationships Extracted: {total_relationships}')
    print(f'   Quota Efficiency Score: {quota_efficiency_score:.2f} (lower is better)')
    
    return result


async def main():
    """Run comprehensive LLM batching tests."""
    
    print('🚀 Chutes AI LLM-Level Batching Tests')
    print('=' * 70)
    print(f'Start Time: {datetime.now().isoformat()}')
    
    # Check prerequisites
    if not os.getenv('CHUTES_API_KEY'):
        print('❌ CHUTES_API_KEY not found')
        return
    
    # Set up Chutes client
    chutes_config = LLMConfig(
        api_key=os.getenv('CHUTES_API_KEY'),
        base_url=DEFAULT_BASE_URL,
        model=DEFAULT_MODEL,
        temperature=0.2,  # Consistent extraction
        max_tokens=2000,  # Allow for batched responses
    )
    
    chutes_client = ChutesClient(config=chutes_config)
    batcher = ChutesLLMBatcher(chutes_client)
    
    # Generate test data
    episodes = generate_test_episodes(5)
    print(f'\n📝 Generated {len(episodes)} test episodes')
    
    # Test different batching strategies
    strategies = [
        ('individual', {}),
        ('batched', {'batch_size': 2}),
        ('batched', {'batch_size': 3}),
        ('mega_batch', {})
    ]
    
    results = []
    
    for strategy_name, kwargs in strategies:
        try:
            result = await test_batching_strategy(strategy_name, batcher, episodes, **kwargs)
            results.append(result)
            
            # Pause between tests
            print('⏳ Pausing 5 seconds before next test...')
            await asyncio.sleep(5)
            
        except Exception as e:
            print(f'❌ Strategy {strategy_name} failed: {e}')
    
    # Analysis and recommendations
    print(f'\n📈 BATCHING STRATEGY ANALYSIS')
    print('=' * 70)
    
    if not results:
        print('❌ No successful tests completed')
        return
    
    # Summary table
    print(f'\n📊 Results Comparison:')
    print(f'{"Strategy":<20} {"API Calls":<12} {"Calls/Episode":<15} {"Success Rate":<12} {"Entities":<10} {"Efficiency":<12}')
    print('-' * 100)
    
    for result in results:
        strategy_display = f"{result.strategy}({result.total_api_calls})" if 'batch' in result.strategy else result.strategy
        success_rate = f'{result.successful_extractions}/{result.total_episodes}'
        print(f'{strategy_display:<20} {result.total_api_calls:<12} {result.api_calls_per_episode:<15.1f} {success_rate:<12} {result.total_entities_extracted:<10} {result.quota_efficiency_score:<12.2f}')
    
    # Find best strategy
    best_strategy = min(results, key=lambda r: r.quota_efficiency_score)
    
    print(f'\n🏆 BEST STRATEGY: {best_strategy.strategy.upper()}')
    print(f'   API Calls per Episode: {best_strategy.api_calls_per_episode:.1f}')
    print(f'   Success Rate: {best_strategy.successful_extractions}/{best_strategy.total_episodes}')
    print(f'   Efficiency Score: {best_strategy.quota_efficiency_score:.2f}')
    print(f'   Average Entities per Episode: {best_strategy.total_entities_extracted/best_strategy.total_episodes:.1f}')
    
    # Quota projections
    daily_quota_calls = 1000  # Conservative estimate
    episodes_per_day = daily_quota_calls / best_strategy.api_calls_per_episode
    
    print(f'\n💰 QUOTA PROJECTIONS (Best Strategy):')
    print(f'   Episodes per day (1000 calls): {episodes_per_day:.0f}')
    print(f'   Recommended daily limit: {int(episodes_per_day * 0.8)}')  # 80% safety
    
    # Implementation recommendations
    print(f'\n💡 IMPLEMENTATION RECOMMENDATIONS:')
    if best_strategy.api_calls_per_episode <= 1:
        print('   ✅ Excellent: Use batching in production')
        print('   🔧 Implement batch size optimization')
        print('   📊 Monitor batch success rates')
    elif best_strategy.api_calls_per_episode <= 2:
        print('   ✅ Good: Batching provides significant savings')
        print('   🔧 Fine-tune batch sizes for optimal results')
    else:
        print('   ⚠️ Limited improvement from batching')
        print('   🔧 Focus on prompt optimization instead')
    
    print(f'\n🔧 PRODUCTION CONFIGURATION:')
    print(f'   CHUTES_BATCHING_STRATEGY={best_strategy.strategy}')
    if 'batch' in best_strategy.strategy:
        print(f'   CHUTES_BATCH_SIZE=3')
    print(f'   CHUTES_MAX_TOKENS=2000')
    print(f'   CHUTES_TEMPERATURE=0.2')
    
    print(f'\n🎉 LLM Batching Tests Completed!')
    print(f'End Time: {datetime.now().isoformat()}')


if __name__ == '__main__':
    asyncio.run(main())