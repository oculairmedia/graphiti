#!/usr/bin/env python3
"""
Chutes AI Batch Pipeline Prototype - API Only Version
Tests parallel LLM batch processing without database dependencies.
Validates batching approach for entity extraction efficiency.
"""

import asyncio
import time
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

from graphiti_core.llm_client.chutes_client import ChutesClient, DEFAULT_MODEL, DEFAULT_BASE_URL
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.prompts.models import Message


@dataclass
class BatchExtractionResult:
    """Results from batch vs individual entity extraction."""
    approach: str
    episodes_processed: int
    total_api_calls: int
    processing_time: float
    total_entities_extracted: int
    total_relationships_extracted: int
    avg_entities_per_episode: float
    avg_relationships_per_episode: float
    api_efficiency: float  # entities per API call
    success_rate: float


class ChutesBatchExtractor:
    """API-only batch entity extraction for Chutes AI."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_call_count = 0
        
        # Configure for batch processing with higher token limits
        self.chutes_config = LLMConfig(
            api_key=api_key,
            base_url=DEFAULT_BASE_URL,
            model=DEFAULT_MODEL,
            temperature=0.1,  # Lower for consistency
            max_tokens=6000,  # Higher for batch responses
        )
        
        self.client = ChutesClient(config=self.chutes_config)
        print(f'✓ Initialized ChutesBatchExtractor with max_tokens=6000')
    
    async def extract_entities_individual(self, episodes: List[Dict[str, Any]]) -> BatchExtractionResult:
        """Extract entities individually (baseline approach)."""
        
        print(f'\n🔄 Extracting from {len(episodes)} episodes INDIVIDUALLY...')
        self.api_call_count = 0
        start_time = time.time()
        
        all_extractions = []
        successful_extractions = 0
        
        for i, episode in enumerate(episodes):
            try:
                print(f'  Processing episode {i+1}/{len(episodes)}: {episode["name"][:50]}...')
                
                # Individual extraction prompt
                system_prompt = '''You are an expert at extracting entities and relationships from text.
Extract all named entities (people, organizations, locations, concepts, technologies, events) and their relationships.

Return a JSON object with this structure:
{
    "entities": [
        {"name": "Entity Name", "type": "Person|Organization|Location|Concept|Technology|Event", "context": "brief context from text"}
    ],
    "relationships": [
        {"source": "Entity1", "target": "Entity2", "relationship_type": "leads|works_with|located_in|uses|develops|participates_in|collaborates_with", "context": "relationship context"}
    ]
}

Focus on:
- People (researchers, engineers, executives, students)
- Organizations (companies, universities, institutions, labs)
- Technologies (models, systems, architectures, frameworks)
- Events (conferences, publications, collaborations, launches)
- Locations (countries, cities, institutions)
- Quantitative metrics (performance, costs, timelines, scores)'''
                
                user_prompt = f'''Extract entities and relationships from this episode:

Title: {episode['name']}
Content: {episode['content']}
Source: {episode['source']}
Timestamp: {episode['timestamp'].isoformat()}'''
                
                messages = [
                    Message(role='system', content=system_prompt),
                    Message(role='user', content=user_prompt)
                ]
                
                self.api_call_count += 1
                result = await asyncio.wait_for(
                    self.client.generate_response(messages),
                    timeout=90.0
                )
                
                if result and isinstance(result, dict):
                    all_extractions.append(result)
                    successful_extractions += 1
                    
                    entities = result.get('entities', [])
                    relationships = result.get('relationships', [])
                    print(f'    ✅ Extracted {len(entities)} entities, {len(relationships)} relationships')
                else:
                    print(f'    ⚠️ No valid result')
                    all_extractions.append({'entities': [], 'relationships': []})
                
                # Small pause
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f'    ❌ Failed: {e}')
                all_extractions.append({'entities': [], 'relationships': []})
        
        processing_time = time.time() - start_time
        
        # Calculate totals
        total_entities = sum(len(ext.get('entities', [])) for ext in all_extractions)
        total_relationships = sum(len(ext.get('relationships', [])) for ext in all_extractions)
        
        result = BatchExtractionResult(
            approach='individual',
            episodes_processed=len(episodes),
            total_api_calls=self.api_call_count,
            processing_time=processing_time,
            total_entities_extracted=total_entities,
            total_relationships_extracted=total_relationships,
            avg_entities_per_episode=total_entities / len(episodes) if episodes else 0,
            avg_relationships_per_episode=total_relationships / len(episodes) if episodes else 0,
            api_efficiency=total_entities / self.api_call_count if self.api_call_count > 0 else 0,
            success_rate=successful_extractions / len(episodes) if episodes else 0
        )
        
        print(f'\n✅ Individual extraction completed:')
        print(f'   Success rate: {successful_extractions}/{len(episodes)}')
        print(f'   API calls: {self.api_call_count}')
        print(f'   Total entities: {total_entities}')
        print(f'   Total relationships: {total_relationships}')
        print(f'   Processing time: {processing_time:.1f}s')
        
        return result
    
    async def extract_entities_batch(self, episodes: List[Dict[str, Any]], batch_size: int = 3) -> BatchExtractionResult:
        """Extract entities in batches (optimized approach)."""
        
        print(f'\n🚀 Extracting from {len(episodes)} episodes in BATCHES (size {batch_size})...')
        self.api_call_count = 0
        start_time = time.time()
        
        all_extractions = []
        successful_extractions = 0
        
        # Process in batches
        for batch_start in range(0, len(episodes), batch_size):
            batch = episodes[batch_start:batch_start + batch_size]
            batch_num = (batch_start // batch_size) + 1
            
            print(f'\n  📦 Processing Batch {batch_num} ({len(batch)} episodes)...')
            
            try:
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
                
                # Batch extraction prompt
                system_prompt = f'''You are an expert at extracting entities and relationships from text.
I will provide {len(batch)} episodes. For each episode, extract all named entities and their relationships.

Return a JSON array with exactly {len(batch)} objects, each with this structure:
{{
    "episode_index": 1,
    "entities": [
        {{"name": "Entity Name", "type": "Person|Organization|Location|Concept|Technology|Event", "context": "brief context from text"}}
    ],
    "relationships": [
        {{"source": "Entity1", "target": "Entity2", "relationship_type": "leads|works_with|located_in|uses|develops|participates_in|collaborates_with", "context": "relationship context"}}
    ]
}}

Focus on:
- People (researchers, engineers, executives, students)
- Organizations (companies, universities, institutions, labs)
- Technologies (models, systems, architectures, frameworks)
- Events (conferences, publications, collaborations, launches)
- Locations (countries, cities, institutions)
- Quantitative metrics (performance, costs, timelines, scores)

Return exactly {len(batch)} episode objects in the array, maintaining the same order as input.'''
                
                user_prompt = f'Extract entities and relationships from these {len(batch)} episodes:\n\n{batch_content}'
                
                messages = [
                    Message(role='system', content=system_prompt),
                    Message(role='user', content=user_prompt)
                ]
                
                self.api_call_count += 1
                print(f'    📞 Making batch API call for {len(batch)} episodes...')
                
                batch_result = await asyncio.wait_for(
                    self.client.generate_response(messages),
                    timeout=150.0  # Longer timeout for batch processing
                )
                
                # Parse batch result
                batch_extractions = []
                if isinstance(batch_result, list) and len(batch_result) >= len(batch):
                    batch_extractions = batch_result[:len(batch)]
                elif isinstance(batch_result, dict) and 'episodes' in batch_result:
                    episodes_data = batch_result['episodes']
                    if len(episodes_data) >= len(batch):
                        batch_extractions = episodes_data[:len(batch)]
                    else:
                        # Pad with empty data
                        batch_extractions = episodes_data[:]
                        while len(batch_extractions) < len(batch):
                            batch_extractions.append({'entities': [], 'relationships': []})
                else:
                    # Fallback: distribute single result
                    base_result = batch_result if isinstance(batch_result, dict) else {'entities': [], 'relationships': []}
                    batch_extractions = [base_result for _ in batch]
                
                # Process batch results
                for i, extraction in enumerate(batch_extractions):
                    episode_num = batch_start + i + 1
                    if extraction and isinstance(extraction, dict):
                        entities = extraction.get('entities', [])
                        relationships = extraction.get('relationships', [])
                        successful_extractions += 1
                        print(f'    Episode {episode_num}: ✅ {len(entities)} entities, {len(relationships)} relationships')
                    else:
                        extraction = {'entities': [], 'relationships': []}
                        print(f'    Episode {episode_num}: ⚠️ No valid extraction')
                    
                    all_extractions.append(extraction)
                
                # Pause between batches
                await asyncio.sleep(2)
                
            except Exception as e:
                print(f'    ❌ Batch {batch_num} failed: {e}')
                # Add empty results for failed batch
                for i in range(len(batch)):
                    all_extractions.append({'entities': [], 'relationships': []})
        
        processing_time = time.time() - start_time
        
        # Calculate totals
        total_entities = sum(len(ext.get('entities', [])) for ext in all_extractions)
        total_relationships = sum(len(ext.get('relationships', [])) for ext in all_extractions)
        
        result = BatchExtractionResult(
            approach='batch',
            episodes_processed=len(episodes),
            total_api_calls=self.api_call_count,
            processing_time=processing_time,
            total_entities_extracted=total_entities,
            total_relationships_extracted=total_relationships,
            avg_entities_per_episode=total_entities / len(episodes) if episodes else 0,
            avg_relationships_per_episode=total_relationships / len(episodes) if episodes else 0,
            api_efficiency=total_entities / self.api_call_count if self.api_call_count > 0 else 0,
            success_rate=successful_extractions / len(episodes) if episodes else 0
        )
        
        print(f'\n✅ Batch extraction completed:')
        print(f'   Success rate: {successful_extractions}/{len(episodes)}')
        print(f'   API calls: {self.api_call_count}')
        print(f'   Total entities: {total_entities}')
        print(f'   Total relationships: {total_relationships}')
        print(f'   Processing time: {processing_time:.1f}s')
        print(f'   API efficiency: {result.api_efficiency:.1f} entities per call')
        
        return result


def generate_test_episodes(count: int = 5) -> List[Dict[str, Any]]:
    """Generate realistic test episodes for batch processing validation."""
    
    episodes = [
        {
            'name': 'Stanford AI Lab Transformer Breakthrough',
            'content': '''
            Stanford University's Artificial Intelligence Laboratory announced a groundbreaking advancement 
            in transformer architecture optimization. The research team, led by Dr. Emily Chen and 
            Dr. Michael Rodriguez, developed a revolutionary sparse attention mechanism that achieves 
            45% reduction in computational requirements while improving model accuracy by 8%.
            
            The project was a collaborative effort involving Google Research, NVIDIA Corporation, 
            and the National Science Foundation, with total funding of $5.2 million over 3 years. 
            Key contributors include graduate students Sarah Kim, David Park, and Maria Santos, who 
            worked on theoretical foundations and implementation.
            
            Technical innovations include dynamic head allocation, custom CUDA kernels for 
            sparse matrix operations, and novel positional encoding schemes. Performance testing 
            on NVIDIA H100 GPUs showed 60% faster inference compared to standard transformers, 
            with potential applications in natural language processing and computer vision.
            
            The work will be presented at NeurIPS 2024 by Dr. Chen's team and published in 
            Nature Machine Intelligence. Industry partners Facebook AI Research and OpenAI have 
            expressed strong interest in licensing the technology for production systems.
            ''',
            'source': 'Stanford AI Laboratory Press Release',
            'timestamp': datetime.now() - timedelta(days=7)
        },
        {
            'name': 'TechCorp AI Customer Service Deployment Success',
            'content': '''
            TechCorp Inc., a Fortune 500 technology company, successfully launched the largest 
            AI-powered customer service system in the industry, processing over 500,000 daily 
            queries with 94% automation rate and 96% customer satisfaction score.
            
            The deployment was spearheaded by CTO Lisa Wang, ML Engineering Director James Liu, 
            and Customer Experience VP Rachel Chen. The technical team included senior engineers 
            Alex Johnson, Priya Patel, and Carlos Rodriguez, supported by a team of 25 ML specialists.
            
            The system architecture leverages Amazon Web Services infrastructure with 400 
            NVIDIA A100 GPUs distributed across 3 availability zones. Core components include 
            a fine-tuned Llama-2 70B model for query understanding, Pinecone vector database 
            for knowledge retrieval, and custom API gateway built with FastAPI and Redis.
            
            Performance metrics show average response time of 120ms, 99.9% uptime, and $12 million 
            annual cost savings compared to human-only support. The project took 24 months with 
            total investment of $28 million including infrastructure, personnel, and training data.
            
            Customer feedback indicates 35% improvement in resolution time and 28% increase in 
            satisfaction scores. The success has led to expansion plans for international markets 
            and additional AI applications across TechCorp's product portfolio.
            ''',
            'source': 'TechCorp Engineering Blog',
            'timestamp': datetime.now() - timedelta(days=4)
        },
        {
            'name': 'Global AI Safety Summit London 2024 Outcomes',
            'content': '''
            The International AI Safety Summit 2024 concluded in London with unprecedented 
            participation from 750 researchers, policymakers, and industry leaders representing 
            45 countries and 120 organizations. The event was hosted by the UK AI Safety Institute 
            under the leadership of Director Dr. Rachel Thompson.
            
            Keynote presentations featured distinguished speakers including Dr. Stuart Russell 
            from UC Berkeley on AI alignment, Dr. Yoshua Bengio from University of Montreal on 
            ethical AI development, Dr. Demis Hassabis from Google DeepMind on AGI safety, and 
            Dr. Dario Amodei from Anthropic on constitutional AI approaches.
            
            Major outcomes included the adoption of the London AI Safety Charter, signed by 
            representatives from United States, European Union, United Kingdom, Canada, Japan, 
            Australia, and South Korea. Key commitments involve establishing international 
            oversight mechanisms, mandatory safety testing protocols, and $2 billion funding 
            for safety research initiatives.
            
            Technical working groups presented breakthrough research in interpretability methods, 
            robustness testing frameworks, and governance protocols for advanced AI systems. 
            Notable contributions came from OpenAI's safety team, Anthropic's alignment research, 
            DeepMind's ethics group, and university collaborations from MIT, Stanford, and Oxford.
            
            The summit established the International AI Safety Consortium with headquarters in 
            Geneva, annual budget of $500 million, and mandate to coordinate global safety 
            standards. Next year's summit will be hosted by Singapore with focus on Asia-Pacific 
            AI governance challenges.
            ''',
            'source': 'AI Safety Summit 2024 Official Proceedings',
            'timestamp': datetime.now() - timedelta(days=2)
        },
        {
            'name': 'Meta AI Releases Llama-3 Open Source Language Model',
            'content': '''
            Meta AI announced the release of Llama-3, the most advanced open-source large language 
            model to date, featuring 70 billion parameters and trained on 2 trillion tokens from 
            diverse multilingual datasets. The model demonstrates state-of-the-art performance 
            across reasoning, mathematics, coding, and multilingual understanding benchmarks.
            
            The development was led by Chief AI Scientist Yann LeCun, VP of AI Research Joelle Pineau, 
            and Technical Director Susan Zhang. The core team included research scientists Ahmad Rashid, 
            Naman Goyal, and Myle Ott, supported by infrastructure engineers and data specialists 
            across Meta's AI Research divisions.
            
            Technical innovations include a novel training methodology combining supervised 
            fine-tuning with constitutional AI techniques, custom attention mechanisms optimized 
            for efficiency, and extensive safety filtering using advanced content classifiers. 
            Training infrastructure utilized 16,000 NVIDIA H100 GPUs over 6 months at an estimated 
            cost of $50 million.
            
            The model achieves 89% accuracy on MMLU benchmark, 76% on HumanEval coding tasks, 
            and demonstrates strong performance in 12 languages including English, Spanish, 
            French, German, Italian, Portuguese, Chinese, Japanese, Korean, Arabic, Hindi, and Russian.
            
            Open source release includes model weights, training code, evaluation scripts, and 
            comprehensive documentation through Hugging Face Hub and GitHub. Commercial licensing 
            allows derivative works and enterprise deployment, marking a significant shift in 
            Meta's AI strategy toward open innovation and research collaboration.
            ''',
            'source': 'Meta AI Research Blog',
            'timestamp': datetime.now() - timedelta(days=1)
        },
        {
            'name': 'Microsoft Azure OpenAI Partnership Expansion',
            'content': '''
            Microsoft Corporation and OpenAI announced a major expansion of their strategic 
            partnership with additional $15 billion investment over 5 years, strengthening 
            Azure's position as the exclusive cloud provider for OpenAI's advanced AI models 
            including GPT-5, which is expected to launch in Q2 2025.
            
            The announcement was made jointly by Microsoft CEO Satya Nadella and OpenAI CEO 
            Sam Altman at Microsoft Ignite 2024 conference in Seattle. Key executives involved 
            include Microsoft CTO Kevin Scott, Azure VP Jason Zander, and OpenAI CTO Mira Murati, 
            along with product teams from both organizations.
            
            Technical integration includes dedicated Azure AI infrastructure with 50,000 NVIDIA 
            H100 and upcoming H200 GPUs, custom networking protocols for ultra-low latency model 
            serving, and enterprise-grade security features for Fortune 500 deployments. The 
            partnership also encompasses joint research initiatives in multimodal AI and robotics.
            
            Commercial offerings through Azure OpenAI Service will provide enterprise customers 
            with private model deployments, custom fine-tuning capabilities, and usage-based 
            pricing starting at $0.002 per 1K tokens. Early access customers include Goldman Sachs, 
            Walmart, BMW, and The Guardian, with use cases spanning customer service, content 
            creation, and data analysis.
            
            The expanded partnership positions Microsoft Azure to capture an estimated $100 billion 
            AI services market by 2027, while providing OpenAI with computational resources 
            necessary for developing artificial general intelligence systems. Integration roadmap 
            includes Office 365, Teams, and Dynamics 365 AI-powered features launching throughout 2025.
            ''',
            'source': 'Microsoft Press Release',
            'timestamp': datetime.now() - timedelta(hours=12)
        }
    ]
    
    return episodes[:count]


def analyze_batch_results(individual: BatchExtractionResult, batch: BatchExtractionResult):
    """Analyze and compare batch vs individual extraction results."""
    
    print(f'\n📊 BATCH EXTRACTION ANALYSIS')
    print('=' * 80)
    
    # Efficiency comparison
    api_reduction = (individual.total_api_calls - batch.total_api_calls) / individual.total_api_calls * 100 if individual.total_api_calls > 0 else 0
    time_improvement = (individual.processing_time - batch.processing_time) / individual.processing_time * 100 if individual.processing_time > 0 else 0
    efficiency_improvement = (batch.api_efficiency - individual.api_efficiency) / individual.api_efficiency * 100 if individual.api_efficiency > 0 else 0
    
    # Results table
    print(f'\n📈 Extraction Results Comparison:')
    print(f'{"Metric":<30} {"Individual":<15} {"Batch":<15} {"Improvement":<15}')
    print('-' * 80)
    print(f'{"Episodes Processed":<30} {individual.episodes_processed:<15} {batch.episodes_processed:<15} {"Same":<15}')
    print(f'{"API Calls":<30} {individual.total_api_calls:<15} {batch.total_api_calls:<15} {api_reduction:>13.1f}%')
    print(f'{"Processing Time (s)":<30} {individual.processing_time:<13.1f} {batch.processing_time:<13.1f} {time_improvement:>13.1f}%')
    print(f'{"Total Entities":<30} {individual.total_entities_extracted:<15} {batch.total_entities_extracted:<15} {batch.total_entities_extracted - individual.total_entities_extracted:<15}')
    print(f'{"Total Relationships":<30} {individual.total_relationships_extracted:<15} {batch.total_relationships_extracted:<15} {batch.total_relationships_extracted - individual.total_relationships_extracted:<15}')
    print(f'{"Entities per Episode":<30} {individual.avg_entities_per_episode:<13.1f} {batch.avg_entities_per_episode:<13.1f} {batch.avg_entities_per_episode - individual.avg_entities_per_episode:>13.1f}')
    print(f'{"Success Rate":<30} {individual.success_rate:<13.1%} {batch.success_rate:<13.1%} {batch.success_rate - individual.success_rate:>13.1%}')
    print(f'{"API Efficiency":<30} {individual.api_efficiency:<13.1f} {batch.api_efficiency:<13.1f} {efficiency_improvement:>13.1f}%')
    
    # Quality assessment
    print(f'\n🎯 Quality Assessment:')
    entity_retention = batch.total_entities_extracted / individual.total_entities_extracted if individual.total_entities_extracted > 0 else 0
    rel_retention = batch.total_relationships_extracted / individual.total_relationships_extracted if individual.total_relationships_extracted > 0 else 0
    
    if entity_retention >= 0.9:
        print('   ✅ Excellent entity extraction retention (≥90%)')
    elif entity_retention >= 0.8:
        print('   ✅ Good entity extraction retention (≥80%)')
    else:
        print('   ⚠️ Significant entity extraction loss (<80%)')
    
    if rel_retention >= 0.9:
        print('   ✅ Excellent relationship extraction retention (≥90%)')
    elif rel_retention >= 0.8:
        print('   ✅ Good relationship extraction retention (≥80%)')
    else:
        print('   ⚠️ Significant relationship extraction loss (<80%)')
    
    if batch.success_rate >= individual.success_rate * 0.9:
        print('   ✅ Success rate maintained in batch processing')
    else:
        print('   ⚠️ Batch processing has lower success rate')
    
    # Efficiency evaluation
    print(f'\n⚡ Efficiency Evaluation:')
    if api_reduction >= 50:
        print(f'   🚀 Outstanding API reduction: {api_reduction:.1f}%')
        efficiency_grade = 'A+'
    elif api_reduction >= 30:
        print(f'   🚀 Excellent API reduction: {api_reduction:.1f}%')
        efficiency_grade = 'A'
    elif api_reduction >= 15:
        print(f'   ✅ Good API reduction: {api_reduction:.1f}%')
        efficiency_grade = 'B'
    else:
        print(f'   ⚠️ Limited API reduction: {api_reduction:.1f}%')
        efficiency_grade = 'C'
    
    # Quota impact analysis
    daily_quota_calls = 1000  # Conservative estimate
    individual_episodes_per_day = daily_quota_calls / (individual.total_api_calls / individual.episodes_processed) if individual.episodes_processed > 0 else 0
    batch_episodes_per_day = daily_quota_calls / (batch.total_api_calls / batch.episodes_processed) if batch.episodes_processed > 0 else 0
    
    print(f'\n💰 Quota Impact Analysis:')
    print(f'   Individual approach: {individual_episodes_per_day:.0f} episodes/day')
    print(f'   Batch approach: {batch_episodes_per_day:.0f} episodes/day')
    print(f'   Daily capacity increase: {batch_episodes_per_day - individual_episodes_per_day:.0f} episodes')
    print(f'   Capacity multiplier: {batch_episodes_per_day / individual_episodes_per_day:.1f}x' if individual_episodes_per_day > 0 else '   Capacity multiplier: ∞')
    
    # Recommendations
    print(f'\n💡 RECOMMENDATIONS:')
    
    if efficiency_grade in ['A+', 'A'] and entity_retention >= 0.8 and rel_retention >= 0.8:
        print('   🎯 STRONGLY RECOMMEND BATCH PIPELINE')
        print('   ✅ Major quota savings with maintained extraction quality')
        print('   🚀 Deploy batch processing in production immediately')
        print('   📈 Consider scaling to larger batch sizes (5-7 episodes)')
    elif efficiency_grade == 'B' and entity_retention >= 0.7 and rel_retention >= 0.7:
        print('   ✅ RECOMMEND BATCH PIPELINE WITH OPTIMIZATION')
        print('   🔧 Fine-tune batch processing for better entity retention')
        print('   📊 Monitor quality metrics in production deployment')
        print('   ⚖️ Good balance of efficiency and quality')
    else:
        print('   🤔 BATCH PIPELINE NEEDS SIGNIFICANT IMPROVEMENT')
        print('   🔧 Optimize prompting and batch processing logic')
        print('   📝 Improve entity extraction consistency')
        print('   🧪 Test with different batch sizes and strategies')
    
    # Production configuration
    if efficiency_grade in ['A+', 'A', 'B']:
        print(f'\n🔧 RECOMMENDED PRODUCTION SETTINGS:')
        print(f'   CHUTES_BATCH_PROCESSING=true')
        print(f'   CHUTES_BATCH_SIZE=3')
        print(f'   CHUTES_MAX_TOKENS=6000')
        print(f'   CHUTES_BATCH_TIMEOUT=150')
        print(f'   CHUTES_TEMPERATURE=0.1')
        print(f'   CHUTES_INTER_BATCH_DELAY=2')


async def main():
    """Run API-only batch pipeline prototype test."""
    
    print('🚀 Chutes AI Batch Pipeline Prototype - API Only Test')
    print('=' * 80)
    print(f'Start Time: {datetime.now().isoformat()}')
    print(f'Scale: Small-scale validation (5 episodes)')
    print(f'Mode: API-only testing (no database dependencies)')
    
    # Check prerequisites
    if not os.getenv('CHUTES_API_KEY'):
        print('❌ CHUTES_API_KEY not found')
        return
    
    try:
        api_key = os.getenv('CHUTES_API_KEY')
        extractor = ChutesBatchExtractor(api_key)
        
        # Generate test episodes
        episodes = generate_test_episodes(5)
        print(f'\n📝 Generated {len(episodes)} realistic test episodes')
        for i, ep in enumerate(episodes, 1):
            print(f'   {i}. {ep["name"]}')
        
        print(f'\n🔬 RUNNING EXTRACTION COMPARISON')
        print('=' * 50)
        
        # Test 1: Individual extraction (baseline)
        individual_result = await extractor.extract_entities_individual(episodes)
        
        # Pause between tests
        print(f'\n⏳ Pausing 10 seconds before batch test...')
        await asyncio.sleep(10)
        
        # Test 2: Batch extraction (optimized)
        batch_result = await extractor.extract_entities_batch(episodes, batch_size=3)
        
        # Analysis and recommendations
        analyze_batch_results(individual_result, batch_result)
        
        print(f'\n🎉 API-Only Batch Pipeline Test Completed!')
        print(f'End Time: {datetime.now().isoformat()}')
        
    except Exception as e:
        print(f'\n❌ Test failed: {e}')
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())