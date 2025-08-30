#!/usr/bin/env python3
"""
Chutes AI Batch Pipeline Prototype
Tests a parallel LLM batch version that achieves same results as normal pipeline.
Small scale validation before production deployment.
"""

import asyncio
import time
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

from graphiti_core import Graphiti
from graphiti_core.embedder import EmbedderClient
from graphiti_core.llm_client.chutes_client import ChutesClient, DEFAULT_MODEL, DEFAULT_BASE_URL
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.nodes import EpisodeType


@dataclass
class PipelineComparisonResult:
    """Results comparing batch vs individual pipeline processing."""
    approach: str
    episodes_processed: int
    total_api_calls: int
    processing_time: float
    entities_extracted: int
    relationships_extracted: int
    episodes_created: int
    success_rate: float
    api_efficiency: float  # episodes per API call


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


class ChutesBatchPipeline:
    """Prototype batch pipeline for Chutes AI processing."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_call_count = 0
        
        # Configure for batch processing
        self.chutes_config = LLMConfig(
            api_key=api_key,
            base_url=DEFAULT_BASE_URL,
            model=DEFAULT_MODEL,
            temperature=0.1,  # Lower for consistency across batches
            max_tokens=4000,  # Higher for batch responses
        )
        
        self.client = ChutesClient(config=self.chutes_config)
        print(f'✓ Initialized ChutesBatchPipeline with max_tokens=4000')
    
    async def process_episodes_individual(self, episodes: List[Dict[str, Any]], graphiti: Graphiti) -> PipelineComparisonResult:
        """Process episodes individually using standard Graphiti pipeline."""
        
        print(f'\n🔄 Processing {len(episodes)} episodes INDIVIDUALLY...')
        self.api_call_count = 0
        start_time = time.time()
        
        # Track original API calls
        original_generate = self.client._generate_response
        async def counted_generate_response(*args, **kwargs):
            self.api_call_count += 1
            return await original_generate(*args, **kwargs)
        self.client._generate_response = counted_generate_response
        
        # Use graphiti with our tracked client
        graphiti.llm_client = self.client
        
        successful_episodes = []
        total_entities = 0
        total_relationships = 0
        
        for i, episode in enumerate(episodes):
            try:
                print(f'  Processing episode {i+1}/{len(episodes)}: {episode["name"][:50]}...')
                
                result = await asyncio.wait_for(
                    graphiti.add_episode(
                        name=episode['name'],
                        episode_body=episode['content'],
                        source_description=episode['source'],
                        reference_time=episode['timestamp'],
                        source=EpisodeType.text,
                    ),
                    timeout=120.0
                )
                
                if result:
                    successful_episodes.append(result)
                    if hasattr(result, 'nodes') and result.nodes:
                        total_entities += len(result.nodes)
                        print(f'    ✅ Extracted {len(result.nodes)} entities')
                    if hasattr(result, 'edges') and result.edges:
                        total_relationships += len(result.edges)
                        print(f'    ✅ Extracted {len(result.edges)} relationships')
                else:
                    print(f'    ⚠️ No result returned')
                    
                # Small pause between episodes
                await asyncio.sleep(1)
                
            except Exception as e:
                print(f'    ❌ Failed: {e}')
        
        processing_time = time.time() - start_time
        
        result = PipelineComparisonResult(
            approach='individual',
            episodes_processed=len(episodes),
            total_api_calls=self.api_call_count,
            processing_time=processing_time,
            entities_extracted=total_entities,
            relationships_extracted=total_relationships,
            episodes_created=len(successful_episodes),
            success_rate=len(successful_episodes) / len(episodes) if episodes else 0,
            api_efficiency=len(successful_episodes) / self.api_call_count if self.api_call_count > 0 else 0
        )
        
        print(f'✅ Individual processing completed:')
        print(f'   Episodes processed: {len(successful_episodes)}/{len(episodes)}')
        print(f'   API calls: {self.api_call_count}')
        print(f'   Entities: {total_entities}, Relationships: {total_relationships}')
        print(f'   Time: {processing_time:.1f}s')
        
        return result
    
    async def process_episodes_batch(self, episodes: List[Dict[str, Any]], graphiti: Graphiti, batch_size: int = 3) -> PipelineComparisonResult:
        """Process episodes in batches using prototype batch pipeline."""
        
        print(f'\n🚀 Processing {len(episodes)} episodes in BATCHES (size {batch_size})...')
        self.api_call_count = 0
        start_time = time.time()
        
        successful_episodes = []
        total_entities = 0
        total_relationships = 0
        
        # Process in batches
        for batch_start in range(0, len(episodes), batch_size):
            batch = episodes[batch_start:batch_start + batch_size]
            batch_num = (batch_start // batch_size) + 1
            
            print(f'\n  📦 Processing Batch {batch_num} ({len(batch)} episodes)...')
            
            try:
                # Extract entities from batch using single API call
                batch_entities = await self._extract_batch_entities(batch)
                
                # Process each episode in the batch with extracted entities
                for i, (episode, entities_data) in enumerate(zip(batch, batch_entities)):
                    episode_num = batch_start + i + 1
                    print(f'    Episode {episode_num}: {episode["name"][:40]}...')
                    
                    try:
                        # Create episode using pre-extracted entities (simulating batch pipeline)
                        result = await self._create_episode_from_batch_data(
                            episode, entities_data, graphiti
                        )
                        
                        if result:
                            successful_episodes.append(result)
                            entities_count = len(entities_data.get('entities', []))
                            relationships_count = len(entities_data.get('relationships', []))
                            total_entities += entities_count
                            total_relationships += relationships_count
                            print(f'      ✅ Created with {entities_count} entities, {relationships_count} relationships')
                        else:
                            print(f'      ⚠️ Failed to create episode')
                            
                    except Exception as e:
                        print(f'      ❌ Episode creation failed: {e}')
                
                # Pause between batches
                await asyncio.sleep(2)
                
            except Exception as e:
                print(f'    ❌ Batch {batch_num} failed: {e}')
        
        processing_time = time.time() - start_time
        
        result = PipelineComparisonResult(
            approach='batch',
            episodes_processed=len(episodes),
            total_api_calls=self.api_call_count,
            processing_time=processing_time,
            entities_extracted=total_entities,
            relationships_extracted=total_relationships,
            episodes_created=len(successful_episodes),
            success_rate=len(successful_episodes) / len(episodes) if episodes else 0,
            api_efficiency=len(successful_episodes) / self.api_call_count if self.api_call_count > 0 else 0
        )
        
        print(f'\n✅ Batch processing completed:')
        print(f'   Episodes processed: {len(successful_episodes)}/{len(episodes)}')
        print(f'   API calls: {self.api_call_count}')
        print(f'   Entities: {total_entities}, Relationships: {total_relationships}')
        print(f'   Time: {processing_time:.1f}s')
        print(f'   API efficiency: {result.api_efficiency:.1f} episodes per call')
        
        return result
    
    async def _extract_batch_entities(self, batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract entities from a batch of episodes using single API call."""
        
        # Build batch content
        batch_content = ""
        for i, episode in enumerate(batch):
            batch_content += f'''
=== EPISODE {i+1} ===
Title: {episode['name']}
Content: {episode['content']}
Source: {episode['source']}
Timestamp: {episode['timestamp'].isoformat()}

'''
        
        # Create batch extraction prompt
        system_prompt = f'''You are an expert at extracting entities and relationships from text.
I will provide {len(batch)} episodes. For each episode, extract all named entities and their relationships.

Return a JSON array with exactly {len(batch)} objects, each with this structure:
{{
    "episode_index": 1,
    "entities": [
        {{"name": "Entity Name", "type": "Person|Organization|Location|Concept|Technology|Event", "context": "brief context from text"}}
    ],
    "relationships": [
        {{"source": "Entity1", "target": "Entity2", "relationship_type": "leads|works_with|located_in|uses|develops|participates_in", "context": "relationship context"}}
    ]
}}

Focus on:
- People (researchers, engineers, executives)
- Organizations (companies, universities, institutions) 
- Technologies (models, systems, architectures)
- Events (conferences, publications, collaborations)
- Quantitative metrics (performance, costs, timelines)

Ensure you return exactly {len(batch)} episode objects in the array.'''
        
        user_prompt = f'Extract entities and relationships from these {len(batch)} episodes:\n\n{batch_content}'
        
        from graphiti_core.prompts.models import Message
        messages = [
            Message(role='system', content=system_prompt),
            Message(role='user', content=user_prompt)
        ]
        
        try:
            self.api_call_count += 1
            print(f'    📞 Making batch extraction API call for {len(batch)} episodes...')
            
            batch_result = await self.client.generate_response(messages)
            
            # Parse and validate batch result
            if isinstance(batch_result, list) and len(batch_result) >= len(batch):
                return batch_result[:len(batch)]  # Take exactly what we need
            elif isinstance(batch_result, dict) and 'episodes' in batch_result:
                episodes_data = batch_result['episodes']
                if len(episodes_data) >= len(batch):
                    return episodes_data[:len(batch)]
                else:
                    # Pad with empty data if needed
                    while len(episodes_data) < len(batch):
                        episodes_data.append({'entities': [], 'relationships': []})
                    return episodes_data
            else:
                # Fallback: distribute single result across all episodes
                base_result = batch_result if isinstance(batch_result, dict) else {'entities': [], 'relationships': []}
                return [base_result for _ in batch]
                
        except Exception as e:
            print(f'    ❌ Batch extraction failed: {e}')
            # Return empty results for all episodes in batch
            return [{'entities': [], 'relationships': []} for _ in batch]
    
    async def _create_episode_from_batch_data(self, episode: Dict[str, Any], entities_data: Dict[str, Any], graphiti: Graphiti) -> Any:
        """Create an episode using pre-extracted batch entity data."""
        
        # This is a simplified version - in full implementation, you'd need to:
        # 1. Create entities in the graph
        # 2. Create relationships between entities  
        # 3. Create the episode node
        # 4. Connect episode to entities
        # For now, we simulate this by calling add_episode but with awareness it uses extracted data
        
        try:
            # Note: In a real batch pipeline, we'd bypass the LLM here and use entities_data directly
            # For this prototype, we still use add_episode to maintain graph consistency
            result = await asyncio.wait_for(
                graphiti.add_episode(
                    name=episode['name'],
                    episode_body=episode['content'],
                    source_description=episode['source'],
                    reference_time=episode['timestamp'],
                    source=EpisodeType.text,
                ),
                timeout=90.0  # Shorter timeout since extraction is pre-done
            )
            return result
            
        except Exception as e:
            print(f'      ❌ Episode creation error: {e}')
            return None


async def setup_test_graphiti() -> Graphiti:
    """Set up Graphiti for pipeline testing."""
    
    # Initialize Ollama embedder (hybrid approach)
    ollama_embedder = OllamaEmbedder()
    
    # FalkorDB connection 
    graphiti = Graphiti(
        uri='bolt://localhost:6389',
        user='',
        password='',
        embedder=ollama_embedder,
        llm_client=None,  # Will be set by pipeline
    )
    
    # Build indices
    await graphiti.build_indices_and_constraints()
    return graphiti


def generate_test_episodes(count: int = 3) -> List[Dict[str, Any]]:
    """Generate small-scale test episodes for validation."""
    
    episodes = [
        {
            'name': 'Stanford AI Research Team Breakthrough',
            'content': '''
            Stanford University's Artificial Intelligence Laboratory announced a significant breakthrough 
            in transformer architecture optimization. The research team, led by Dr. Emily Chen and 
            Dr. Michael Rodriguez, developed a novel attention mechanism that reduces computational 
            requirements by 35% while maintaining model accuracy.
            
            The project involved collaboration with Google Research and received $2.5M funding from 
            the National Science Foundation. Graduate students Sarah Kim and David Park contributed 
            to the theoretical foundations. The work will be presented at NeurIPS 2024 conference
            by Dr. Chen and the team.
            
            Technical innovations include sparse attention patterns, dynamic head allocation, and 
            custom CUDA kernel optimizations. Performance testing showed 40% faster inference on 
            NVIDIA A100 GPUs compared to standard transformer implementations.
            ''',
            'source': 'Stanford AI Lab Press Release',
            'timestamp': datetime.now() - timedelta(days=5)
        },
        {
            'name': 'TechCorp Production AI System Launch',
            'content': '''
            TechCorp Inc. successfully launched its large-scale AI customer service system, handling 
            over 100,000 daily queries with 92% automation rate. The deployment was led by CTO 
            Lisa Wang and ML Engineering Director James Liu.
            
            The system runs on AWS infrastructure using 200 NVIDIA H100 GPUs across multiple 
            availability zones. The ML pipeline processes customer inquiries in real-time with 
            average response time of 150ms. Customer satisfaction scores improved by 28% compared 
            to the previous human-only support system.
            
            Key technical components include a fine-tuned Llama-2 70B model, vector database for 
            knowledge retrieval, and custom API gateway for load balancing. The project took 
            18 months and cost $15M including infrastructure and personnel.
            ''',
            'source': 'TechCorp Engineering Blog',
            'timestamp': datetime.now() - timedelta(days=3)
        },
        {
            'name': 'International AI Safety Summit 2024',
            'content': '''
            The International AI Safety Summit 2024 took place in London, bringing together 500 
            researchers and policymakers from 30 countries. The event was organized by the UK 
            AI Safety Institute and hosted by Dr. Rachel Thompson.
            
            Key presentations included work from OpenAI, Anthropic, DeepMind, and university 
            researchers. Notable speakers were Dr. Stuart Russell from UC Berkeley, Dr. Yoshua 
            Bengio from University of Montreal, and Dr. Demis Hassabis from Google DeepMind.
            
            Major topics covered constitutional AI, alignment techniques, robustness testing, 
            and governance frameworks. The summit concluded with the London AI Safety Declaration, 
            signed by representatives from all participating nations and organizations.
            
            Research highlights included new interpretability methods, safety benchmarks, and 
            international cooperation protocols for advanced AI systems.
            ''',
            'source': 'AI Safety Summit 2024 Proceedings',
            'timestamp': datetime.now() - timedelta(days=1)
        }
    ]
    
    return episodes[:count]


async def run_pipeline_comparison(episodes: List[Dict[str, Any]]) -> Tuple[PipelineComparisonResult, PipelineComparisonResult]:
    """Run comparison between individual and batch pipeline processing."""
    
    api_key = os.getenv('CHUTES_API_KEY')
    if not api_key:
        raise ValueError('CHUTES_API_KEY not found')
    
    batch_pipeline = ChutesBatchPipeline(api_key)
    
    print(f'\n🔬 PIPELINE COMPARISON TEST')
    print('=' * 70)
    print(f'Episodes to process: {len(episodes)}')
    print(f'Testing both individual and batch approaches...')
    
    # Set up Graphiti (shared between tests)
    print(f'\n⚙️ Setting up Graphiti...')
    graphiti = await setup_test_graphiti()
    
    # Test 1: Individual processing (baseline)
    individual_result = await batch_pipeline.process_episodes_individual(episodes, graphiti)
    
    # Wait between tests
    print(f'\n⏳ Waiting 10 seconds between tests...')
    await asyncio.sleep(10)
    
    # Test 2: Batch processing (prototype)
    batch_result = await batch_pipeline.process_episodes_batch(episodes, graphiti, batch_size=3)
    
    await graphiti.close()
    
    return individual_result, batch_result


def analyze_results(individual: PipelineComparisonResult, batch: PipelineComparisonResult):
    """Analyze and compare pipeline results."""
    
    print(f'\n📊 PIPELINE COMPARISON ANALYSIS')
    print('=' * 70)
    
    # Summary table
    print(f'\n📈 Results Summary:')
    print(f'{"Metric":<25} {"Individual":<15} {"Batch":<15} {"Improvement":<15}')
    print('-' * 75)
    
    # Calculate improvements
    api_improvement = (individual.total_api_calls - batch.total_api_calls) / individual.total_api_calls * 100 if individual.total_api_calls > 0 else 0
    time_improvement = (individual.processing_time - batch.processing_time) / individual.processing_time * 100 if individual.processing_time > 0 else 0
    efficiency_improvement = (batch.api_efficiency - individual.api_efficiency) / individual.api_efficiency * 100 if individual.api_efficiency > 0 else 0
    
    print(f'{"Episodes Processed":<25} {individual.episodes_created:<15} {batch.episodes_created:<15} {batch.episodes_created - individual.episodes_created:<15}')
    print(f'{"API Calls":<25} {individual.total_api_calls:<15} {batch.total_api_calls:<15} {api_improvement:>13.1f}%')
    print(f'{"Processing Time":<25} {individual.processing_time:<13.1f}s {batch.processing_time:<13.1f}s {time_improvement:>13.1f}%')
    print(f'{"Entities Extracted":<25} {individual.entities_extracted:<15} {batch.entities_extracted:<15} {batch.entities_extracted - individual.entities_extracted:<15}')
    print(f'{"Relationships":<25} {individual.relationships_extracted:<15} {batch.relationships_extracted:<15} {batch.relationships_extracted - individual.relationships_extracted:<15}')
    print(f'{"Success Rate":<25} {individual.success_rate:<13.1%} {batch.success_rate:<13.1%} {batch.success_rate - individual.success_rate:>13.1%}')
    print(f'{"API Efficiency":<25} {individual.api_efficiency:<13.1f} {batch.api_efficiency:<13.1f} {efficiency_improvement:>13.1f}%')
    
    # Quality analysis
    print(f'\n🎯 Quality Analysis:')
    if batch.success_rate >= individual.success_rate * 0.9:  # Within 10%
        print('   ✅ Batch processing maintains success rate')
    else:
        print('   ⚠️ Batch processing has lower success rate')
    
    entity_ratio = batch.entities_extracted / individual.entities_extracted if individual.entities_extracted > 0 else 0
    if entity_ratio >= 0.8:  # Within 20%
        print('   ✅ Batch processing maintains entity extraction quality')
    else:
        print('   ⚠️ Batch processing extracts fewer entities')
    
    rel_ratio = batch.relationships_extracted / individual.relationships_extracted if individual.relationships_extracted > 0 else 0
    if rel_ratio >= 0.8:  # Within 20%
        print('   ✅ Batch processing maintains relationship extraction quality')
    else:
        print('   ⚠️ Batch processing extracts fewer relationships')
    
    # Efficiency analysis
    print(f'\n⚡ Efficiency Analysis:')
    if api_improvement > 30:
        print(f'   🚀 Excellent API call reduction: {api_improvement:.1f}%')
    elif api_improvement > 10:
        print(f'   ✅ Good API call reduction: {api_improvement:.1f}%')
    else:
        print(f'   ⚠️ Limited API call reduction: {api_improvement:.1f}%')
    
    if batch.api_efficiency > individual.api_efficiency * 1.5:
        print(f'   🚀 Significant efficiency improvement: {efficiency_improvement:.1f}%')
    elif batch.api_efficiency > individual.api_efficiency:
        print(f'   ✅ Improved efficiency: {efficiency_improvement:.1f}%')
    else:
        print(f'   ⚠️ No efficiency improvement: {efficiency_improvement:.1f}%')
    
    # Recommendations
    print(f'\n💡 RECOMMENDATIONS:')
    
    if api_improvement > 30 and batch.success_rate >= individual.success_rate * 0.9:
        print('   🎯 PROCEED WITH BATCH PIPELINE')
        print('   ✅ Significant quota savings with maintained quality')
        print('   🔧 Recommended batch size: 3-5 episodes')
        print('   📈 Scale up testing with larger datasets')
    elif api_improvement > 10:
        print('   🤔 BATCH PIPELINE SHOWS PROMISE')
        print('   🔧 Optimize batch processing logic')
        print('   📊 Test with more diverse content')
        print('   ⚖️ Balance efficiency vs quality')
    else:
        print('   ⚠️ BATCH PIPELINE NEEDS OPTIMIZATION')
        print('   🔧 Review batching strategy')
        print('   📝 Improve prompt engineering')
        print('   🧪 Test different batch sizes')
    
    # Production settings
    if batch.success_rate >= individual.success_rate * 0.9 and api_improvement > 20:
        print(f'\n🔧 RECOMMENDED PRODUCTION SETTINGS:')
        print(f'   CHUTES_BATCH_PROCESSING=true')
        print(f'   CHUTES_BATCH_SIZE=3')
        print(f'   CHUTES_MAX_TOKENS=4000')
        print(f'   CHUTES_BATCH_TIMEOUT=180')
        print(f'   CHUTES_TEMPERATURE=0.1')


async def main():
    """Run the parallel LLM batch pipeline prototype test."""
    
    print('🚀 Chutes AI Batch Pipeline Prototype Test')
    print('=' * 70)
    print(f'Start Time: {datetime.now().isoformat()}')
    print(f'Scale: Small-scale validation (3 episodes)')
    
    # Check prerequisites
    if not os.getenv('CHUTES_API_KEY'):
        print('❌ CHUTES_API_KEY not found')
        return
    
    try:
        # Generate test data
        episodes = generate_test_episodes(3)  # Small scale test
        print(f'\n📝 Generated {len(episodes)} test episodes for validation')
        
        # Run comparison
        individual_result, batch_result = await run_pipeline_comparison(episodes)
        
        # Analyze results
        analyze_results(individual_result, batch_result)
        
        print(f'\n🎉 Batch Pipeline Prototype Test Completed!')
        print(f'End Time: {datetime.now().isoformat()}')
        
    except Exception as e:
        print(f'\n❌ Test failed: {e}')
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())