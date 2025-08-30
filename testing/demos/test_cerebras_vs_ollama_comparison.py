#!/usr/bin/env python3
"""
Comparative testing framework: Cerebras/Qwen vs Ollama/Mistral
Benchmarks extraction quality, performance, and reliability.
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from graphiti_core import Graphiti
from graphiti_core.embedder import EmbedderClient
from graphiti_core.llm_client.cerebras_client import CerebrasClient, DEFAULT_CEREBRAS_MODEL
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.nodes import EpisodeType


@dataclass
class ComparisonResult:
    """Results from comparing two LLM approaches."""
    test_name: str
    cerebras_result: Optional[Any]
    ollama_result: Optional[Any]
    cerebras_time: float
    ollama_time: float
    cerebras_entities: int
    ollama_entities: int
    cerebras_relationships: int
    ollama_relationships: int
    cerebras_error: Optional[str]
    ollama_error: Optional[str]


class OllamaEmbedder(EmbedderClient):
    """Ollama embedder for both test scenarios."""

    def __init__(self, base_url: str = 'http://192.168.50.80:11434/v1', model: str = 'mxbai-embed-large'):
        self.base_url = base_url
        self.model = model
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(base_url=base_url, api_key='ollama')
        print(f'✓ Initialized shared embedder: {model}')

    async def create(self, input_data: list[str]) -> list[list[float]]:
        """Create embeddings using Ollama."""
        try:
            response = await self.client.embeddings.create(model=self.model, input=input_data)
            return [item.embedding for item in response.data]
        except Exception as e:
            print(f'❌ Error creating embeddings: {e}')
            raise


async def setup_cerebras_client():
    """Set up Cerebras/Qwen client."""
    config = LLMConfig(
        model=DEFAULT_CEREBRAS_MODEL,
        temperature=0.3,  # Consistent temperature for comparison
        max_tokens=1500,
    )
    return CerebrasClient(config=config)


async def setup_ollama_client():
    """Set up Ollama/Mistral client."""
    from openai import AsyncOpenAI
    
    config = LLMConfig(
        base_url='http://192.168.50.80:11434/v1',
        model='mistral:latest',
        api_key='ollama',
        temperature=0.3,  # Match Cerebras temperature
        max_tokens=1500,  # Match Cerebras token limit
    )
    
    client = AsyncOpenAI(base_url='http://192.168.50.80:11434/v1', api_key='ollama')
    return OpenAIGenericClient(config=config, client=client)


async def setup_graphiti_instances():
    """Set up two Graphiti instances for comparison."""
    
    # Shared embedder
    shared_embedder = OllamaEmbedder()
    
    # Cerebras instance
    cerebras_client = await setup_cerebras_client()
    cerebras_graphiti = Graphiti(
        uri='bolt://localhost:6389',
        user='',
        password='',
        llm_client=cerebras_client,
        embedder=shared_embedder
    )
    
    # Ollama instance
    ollama_client = await setup_ollama_client()
    ollama_graphiti = Graphiti(
        uri='bolt://localhost:6389',
        user='',
        password='',
        llm_client=ollama_client,
        embedder=shared_embedder
    )
    
    # Build indices for both
    await cerebras_graphiti.build_indices_and_constraints()
    await ollama_graphiti.build_indices_and_constraints()
    
    print('✅ Both Graphiti instances initialized')
    return cerebras_graphiti, ollama_graphiti


class ComparisonTester:
    """Framework for testing Cerebras vs Ollama."""
    
    def __init__(self, cerebras_graphiti: Graphiti, ollama_graphiti: Graphiti):
        self.cerebras_graphiti = cerebras_graphiti
        self.ollama_graphiti = ollama_graphiti
        self.results: List[ComparisonResult] = []

    async def run_episode_comparison(self, test_name: str, episode_content: str, source: str) -> ComparisonResult:
        """Compare episode processing between the two systems."""
        
        print(f'\n🔬 Testing: {test_name}')
        
        # Test Cerebras/Qwen
        cerebras_result = None
        cerebras_error = None
        cerebras_entities = 0
        cerebras_relationships = 0
        
        print('   🧠 Testing Cerebras/Qwen...')
        start_time = time.time()
        try:
            cerebras_result = await asyncio.wait_for(
                self.cerebras_graphiti.add_episode(
                    name=f'Cerebras_{test_name}',
                    episode_body=episode_content,
                    source_description=source,
                    reference_time=datetime.now(),
                    source=EpisodeType.text,
                ),
                timeout=120.0
            )
            
            if cerebras_result:
                cerebras_entities = len(cerebras_result.nodes) if hasattr(cerebras_result, 'nodes') and cerebras_result.nodes else 0
                cerebras_relationships = len(cerebras_result.edges) if hasattr(cerebras_result, 'edges') and cerebras_result.edges else 0
                
        except asyncio.TimeoutError:
            cerebras_error = 'Timeout after 120 seconds'
        except Exception as e:
            cerebras_error = str(e)
            
        cerebras_time = time.time() - start_time
        
        # Test Ollama/Mistral  
        ollama_result = None
        ollama_error = None
        ollama_entities = 0
        ollama_relationships = 0
        
        print('   🦙 Testing Ollama/Mistral...')
        start_time = time.time()
        try:
            ollama_result = await asyncio.wait_for(
                self.ollama_graphiti.add_episode(
                    name=f'Ollama_{test_name}',
                    episode_body=episode_content,
                    source_description=source,
                    reference_time=datetime.now(),
                    source=EpisodeType.text,
                ),
                timeout=120.0
            )
            
            if ollama_result:
                ollama_entities = len(ollama_result.nodes) if hasattr(ollama_result, 'nodes') and ollama_result.nodes else 0
                ollama_relationships = len(ollama_result.edges) if hasattr(ollama_result, 'edges') and ollama_result.edges else 0
                
        except asyncio.TimeoutError:
            ollama_error = 'Timeout after 120 seconds'
        except Exception as e:
            ollama_error = str(e)
            
        ollama_time = time.time() - start_time
        
        # Create comparison result
        result = ComparisonResult(
            test_name=test_name,
            cerebras_result=cerebras_result,
            ollama_result=ollama_result,
            cerebras_time=cerebras_time,
            ollama_time=ollama_time,
            cerebras_entities=cerebras_entities,
            ollama_entities=ollama_entities,
            cerebras_relationships=cerebras_relationships,
            ollama_relationships=ollama_relationships,
            cerebras_error=cerebras_error,
            ollama_error=ollama_error
        )
        
        self.results.append(result)
        
        # Print comparison
        print(f'   ⚡ Performance:')
        print(f'     Cerebras: {cerebras_time:.2f}s ({cerebras_entities} entities, {cerebras_relationships} relations)')
        print(f'     Ollama:   {ollama_time:.2f}s ({ollama_entities} entities, {ollama_relationships} relations)')
        
        if cerebras_error:
            print(f'     ❌ Cerebras error: {cerebras_error}')
        if ollama_error:
            print(f'     ❌ Ollama error: {ollama_error}')
            
        return result

    async def run_search_comparison(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Compare search performance between systems."""
        
        print(f'\n🔍 Search Comparison: "{query}"')
        
        # Cerebras search
        cerebras_search_time = 0
        cerebras_results = []
        cerebras_search_error = None
        
        start_time = time.time()
        try:
            cerebras_results = await self.cerebras_graphiti.search(query=query, limit=limit)
            cerebras_search_time = time.time() - start_time
        except Exception as e:
            cerebras_search_error = str(e)
            cerebras_search_time = time.time() - start_time
            
        # Ollama search
        ollama_search_time = 0
        ollama_results = []
        ollama_search_error = None
        
        start_time = time.time()
        try:
            ollama_results = await self.ollama_graphiti.search(query=query, limit=limit)
            ollama_search_time = time.time() - start_time
        except Exception as e:
            ollama_search_error = str(e)
            ollama_search_time = time.time() - start_time
        
        search_comparison = {
            'query': query,
            'cerebras_time': cerebras_search_time,
            'ollama_time': ollama_search_time,
            'cerebras_results': len(cerebras_results) if cerebras_results else 0,
            'ollama_results': len(ollama_results) if ollama_results else 0,
            'cerebras_error': cerebras_search_error,
            'ollama_error': ollama_search_error
        }
        
        print(f'   Search Times: Cerebras {cerebras_search_time:.2f}s, Ollama {ollama_search_time:.2f}s')
        print(f'   Results: Cerebras {len(cerebras_results) if cerebras_results else 0}, Ollama {len(ollama_results) if ollama_results else 0}')
        
        return search_comparison

    def print_summary(self):
        """Print comprehensive comparison summary."""
        
        print('\n📊 CEREBRAS vs OLLAMA COMPARISON SUMMARY')
        print('=' * 70)
        
        if not self.results:
            print('❌ No test results to analyze')
            return
            
        # Performance metrics
        cerebras_times = [r.cerebras_time for r in self.results if r.cerebras_error is None]
        ollama_times = [r.ollama_time for r in self.results if r.ollama_error is None]
        
        if cerebras_times and ollama_times:
            avg_cerebras = sum(cerebras_times) / len(cerebras_times)
            avg_ollama = sum(ollama_times) / len(ollama_times)
            
            print(f'\n⚡ Average Processing Times:')
            print(f'   Cerebras/Qwen:    {avg_cerebras:.2f}s')
            print(f'   Ollama/Mistral:   {avg_ollama:.2f}s')
            print(f'   Speed Difference: {((avg_ollama - avg_cerebras) / avg_ollama * 100):+.1f}% (Cerebras vs Ollama)')
        
        # Extraction quality
        total_cerebras_entities = sum(r.cerebras_entities for r in self.results if r.cerebras_error is None)
        total_ollama_entities = sum(r.ollama_entities for r in self.results if r.ollama_error is None)
        total_cerebras_relations = sum(r.cerebras_relationships for r in self.results if r.cerebras_error is None)
        total_ollama_relations = sum(r.ollama_relationships for r in self.results if r.ollama_error is None)
        
        print(f'\n🎯 Extraction Quality:')
        print(f'   Cerebras Entities: {total_cerebras_entities}')
        print(f'   Ollama Entities:   {total_ollama_entities}')
        print(f'   Cerebras Relations: {total_cerebras_relations}')
        print(f'   Ollama Relations:   {total_ollama_relations}')
        
        # Reliability
        cerebras_successes = len([r for r in self.results if r.cerebras_error is None])
        ollama_successes = len([r for r in self.results if r.ollama_error is None])
        total_tests = len(self.results)
        
        print(f'\n✅ Reliability:')
        print(f'   Cerebras Success Rate: {cerebras_successes}/{total_tests} ({cerebras_successes/total_tests*100:.1f}%)')
        print(f'   Ollama Success Rate:   {ollama_successes}/{total_tests} ({ollama_successes/total_tests*100:.1f}%)')
        
        # Error analysis
        cerebras_errors = [r.cerebras_error for r in self.results if r.cerebras_error]
        ollama_errors = [r.ollama_error for r in self.results if r.ollama_error]
        
        if cerebras_errors:
            print(f'\n❌ Cerebras Errors:')
            for error in set(cerebras_errors):
                count = cerebras_errors.count(error)
                print(f'   - {error} ({count}x)')
                
        if ollama_errors:
            print(f'\n❌ Ollama Errors:')
            for error in set(ollama_errors):
                count = ollama_errors.count(error)
                print(f'   - {error} ({count}x)')

        # Recommendations
        print(f'\n💡 Recommendations:')
        
        if cerebras_times and ollama_times:
            if avg_cerebras < avg_ollama:
                speed_advantage = ((avg_ollama - avg_cerebras) / avg_ollama * 100)
                print(f'   ✅ Cerebras is {speed_advantage:.1f}% faster than Ollama')
            else:
                speed_advantage = ((avg_cerebras - avg_ollama) / avg_cerebras * 100)
                print(f'   ⚠️ Ollama is {speed_advantage:.1f}% faster than Cerebras')
        
        if total_cerebras_entities > total_ollama_entities:
            entity_advantage = ((total_cerebras_entities - total_ollama_entities) / total_ollama_entities * 100)
            print(f'   ✅ Cerebras extracts {entity_advantage:.1f}% more entities')
        elif total_ollama_entities > total_cerebras_entities:
            entity_advantage = ((total_ollama_entities - total_cerebras_entities) / total_cerebras_entities * 100)
            print(f'   ⚠️ Ollama extracts {entity_advantage:.1f}% more entities')
            
        if cerebras_successes > ollama_successes:
            print(f'   ✅ Cerebras is more reliable ({(cerebras_successes - ollama_successes)} fewer failures)')
        elif ollama_successes > cerebras_successes:
            print(f'   ⚠️ Ollama is more reliable ({(ollama_successes - cerebras_successes)} fewer failures)')


async def main():
    """Run comprehensive comparison tests."""
    
    print('🧠🆚🦙 Cerebras/Qwen vs Ollama/Mistral Comparison')
    print('=' * 80)
    
    # Setup
    try:
        cerebras_graphiti, ollama_graphiti = await setup_graphiti_instances()
    except Exception as e:
        print(f'❌ Setup failed: {e}')
        return
        
    tester = ComparisonTester(cerebras_graphiti, ollama_graphiti)
    
    # Test episodes designed to highlight differences
    test_episodes = [
        {
            'name': 'Technical Research Paper',
            'content': '''
            Dr. Sarah Chen and her research team at Stanford AI Lab published a groundbreaking 
            study on transformer architecture optimization in the Journal of Machine Learning Research. 
            The paper, co-authored by machine learning engineer Bob Martinez and computational linguist 
            Dr. Aisha Patel, demonstrates a 45% reduction in inference time while maintaining 99.2% 
            accuracy on GLUE benchmarks. The methodology involves sparse attention patterns with 
            dynamic head allocation and layer-wise adaptive learning rates.
            ''',
            'source': 'Academic Journal'
        },
        {
            'name': 'Business Partnership Announcement',
            'content': '''
            QuantumTech Inc., led by CEO Dr. Maria Kowalski, announced a strategic partnership 
            with IBM Quantum Network worth $4.2M over 3 years. The collaboration will focus on 
            developing quantum-enhanced optimization algorithms using IBM's 127-qubit processor. 
            Key team members include quantum physicist Dr. James Wilson and software architect 
            Alice Rodriguez. The project aims to demonstrate quantum advantage in logistics 
            optimization problems by Q4 2024.
            ''',
            'source': 'Press Release'
        },
        {
            'name': 'Code Generation Breakthrough',
            'content': '''
            The engineering team at CodeAI Solutions achieved state-of-the-art results on code 
            generation benchmarks: HumanEval (91.5% pass rate), MBPP (89.3%), and CodeContests (68.7%). 
            The model uses a mixture-of-experts architecture with 175B parameters, trained on 50+ 
            programming languages using reinforcement learning from human feedback (RLHF). 
            Senior engineers Alice Zhang, Bob Thompson, and Carol Martinez led the development, 
            with beta testing starting among 2000 selected developers worldwide.
            ''',
            'source': 'Technical Report'
        }
    ]
    
    # Run episode processing comparisons
    print('\n📝 EPISODE PROCESSING COMPARISON')
    print('-' * 50)
    
    for episode in test_episodes:
        await tester.run_episode_comparison(
            episode['name'], 
            episode['content'], 
            episode['source']
        )
        
        # Brief pause between tests
        await asyncio.sleep(2)
    
    # Run search comparisons
    print('\n🔍 SEARCH PERFORMANCE COMPARISON')
    print('-' * 50)
    
    search_queries = [
        'machine learning research Stanford',
        'quantum computing partnership IBM',
        'code generation benchmarks performance',
        'Dr. Sarah Chen transformer architecture',
        'optimization algorithms neural networks'
    ]
    
    search_results = []
    for query in search_queries:
        search_result = await tester.run_search_comparison(query, limit=3)
        search_results.append(search_result)
        await asyncio.sleep(1)
    
    # Print comprehensive summary
    tester.print_summary()
    
    # Search summary
    if search_results:
        print(f'\n🔍 Search Performance Summary:')
        avg_cerebras_search = sum(r['cerebras_time'] for r in search_results if r['cerebras_error'] is None) / len(search_results)
        avg_ollama_search = sum(r['ollama_time'] for r in search_results if r['ollama_error'] is None) / len(search_results)
        
        print(f'   Average Search Time:')
        print(f'     Cerebras: {avg_cerebras_search:.3f}s')
        print(f'     Ollama:   {avg_ollama_search:.3f}s')
    
    # Cleanup
    try:
        await cerebras_graphiti.close()
        await ollama_graphiti.close()
        print('\n🧹 Cleanup completed')
    except Exception as e:
        print(f'\n⚠️ Cleanup warning: {e}')
    
    print('\n🎉 Comparison test completed!')


if __name__ == '__main__':
    asyncio.run(main())