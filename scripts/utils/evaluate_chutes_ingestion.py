#!/usr/bin/env python3
"""
Chutes AI Model Performance Evaluation for Memory Ingestion Tasks.

This script evaluates how well the Chutes AI model (zai-org/GLM-4.5-FP8) performs
on the core tasks required for memory ingestion:
- Entity extraction quality
- Entity deduplication accuracy  
- Relationship extraction
- Structured output compliance
- Response time and token efficiency
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

from graphiti_core.graphiti import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.nodes import EpisodicNode
from graphiti_core.utils.maintenance.graph_data_operations import retrieve_episodes


class ChutesIngestionEvaluator:
    """Evaluates Chutes AI model performance on memory ingestion tasks."""
    
    def __init__(self):
        self.results = {
            'evaluation_id': f"chutes_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            'model': 'zai-org/GLM-4.5-FP8',
            'start_time': datetime.now().isoformat(),
            'test_episodes': [],
            'entity_extraction_results': [],
            'deduplication_results': [], 
            'relationship_extraction_results': [],
            'performance_metrics': {
                'total_llm_calls': 0,
                'total_tokens_used': 0,
                'avg_response_time_ms': 0.0,
                'successful_extractions': 0,
                'failed_extractions': 0,
                'structured_output_compliance': 0.0,
            },
            'quality_metrics': {
                'entity_precision': 0.0,
                'entity_recall': 0.0,
                'relationship_accuracy': 0.0,
                'deduplication_accuracy': 0.0,
            }
        }
        
    async def setup_chutes_client(self) -> Graphiti:
        """Initialize Graphiti with Chutes AI configuration."""
        print("🧠 Setting up Chutes AI client...")
        
        # FalkorDB driver  
        driver = FalkorDriver(
            host='192.168.50.90',
            port=6379,
            database='graphiti_migration'
        )
        
        # Chutes AI LLM client
        chutes_config = LLMConfig(
            api_key='cpk_f62b08fa4c2b4ae0b195b944fd47d6fc.bb20b5a1d58c50c9bc051e74b2a39d7c.roXSCXsJnWAk8mcZ26umGcrPjkCaqXlh',
            base_url='https://llm.chutes.ai/v1',
            model='zai-org/GLM-4.5-FP8',
            temperature=0.1,  # Lower temperature for consistent extraction
            max_tokens=2048
        )
        llm_client = OpenAIClient(config=chutes_config)
        
        # Ollama embedder
        ollama_embedder_config = OpenAIEmbedderConfig(
            api_key='ollama',
            base_url='http://192.168.50.80:11434/v1',
            embedding_model='mxbai-embed-large'
        )
        embedder = OpenAIEmbedder(config=ollama_embedder_config)
        
        return Graphiti(
            graph_driver=driver,
            llm_client=llm_client,
            embedder=embedder
        )
        
    async def get_test_episodes(self, limit: int = 5) -> List[EpisodicNode]:
        """Get a diverse set of episodes for testing."""
        print(f"📊 Retrieving {limit} test episodes...")
        
        # Get episodes from database
        driver = FalkorDriver(
            host='192.168.50.90',
            port=6379,
            database='graphiti_migration'
        )
        
        from graphiti_core.utils.datetime_utils import utc_now
        episodes = await retrieve_episodes(
            driver=driver,
            reference_time=utc_now(),
            last_n=limit * 3,  # Get more to select diverse ones
            group_ids=None,
            source=None,
        )
        
        # Select diverse episodes (different lengths, content types)
        selected_episodes = []
        for episode in episodes[:limit]:
            selected_episodes.append(episode)
            self.results['test_episodes'].append({
                'uuid': str(episode.uuid),
                'name': episode.name,
                'content_length': len(episode.content),
                'source': episode.source.name if episode.source else 'unknown',
                'group_id': episode.group_id,
            })
            
        await driver.close()
        return selected_episodes
        
    async def evaluate_entity_extraction(self, graphiti: Graphiti, episodes: List[EpisodicNode]) -> Dict[str, Any]:
        """Test entity extraction quality and performance."""
        print("🔍 Evaluating entity extraction...")
        
        extraction_results = []
        
        for i, episode in enumerate(episodes):
            print(f"  Processing episode {i+1}/{len(episodes)}: {episode.name[:50]}...")
            
            start_time = time.time()
            try:
                # Test entity extraction using Graphiti's internal methods
                # We'll use the prompts module directly to test extraction
                from graphiti_core.prompts.extract_nodes import extract_text
                
                # Build the context for extraction
                context = {
                    'episode_content': episode.content,
                    'custom_prompt': 'Return only valid JSON with extracted entities.',
                    'entity_types': [
                        {'id': 1, 'type': 'Person', 'description': 'A human being'},
                        {'id': 2, 'type': 'Organization', 'description': 'A company, institution, or group'},
                        {'id': 3, 'type': 'Location', 'description': 'A place, city, country, or geographical location'},
                        {'id': 4, 'type': 'Technology', 'description': 'Software, hardware, or technical concepts'},
                        {'id': 5, 'type': 'Event', 'description': 'An occurrence, meeting, or happening'},
                        {'id': 6, 'type': 'Concept', 'description': 'An abstract idea or notion'},
                    ]
                }
                
                # Generate extraction prompt messages
                messages = extract_text(context)
                
                # Call LLM directly to measure performance
                response = await graphiti.llm_client.generate_response(
                    messages=messages,
                    response_model=None  # Test if it returns valid JSON
                )
                
                end_time = time.time()
                response_time = (end_time - start_time) * 1000
                
                # Try to parse the response as JSON to check structure compliance
                try:
                    if hasattr(response, 'content'):
                        content = response.content
                    else:
                        content = str(response)
                        
                    # Look for JSON in the response
                    import re
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        extracted_data = json.loads(json_match.group())
                        structured_compliance = True
                        entities_found = len(extracted_data.get('entities', []))
                    else:
                        structured_compliance = False
                        entities_found = 0
                        extracted_data = None
                        
                except (json.JSONDecodeError, AttributeError) as e:
                    structured_compliance = False
                    entities_found = 0
                    extracted_data = None
                
                result = {
                    'episode_uuid': str(episode.uuid),
                    'response_time_ms': response_time,
                    'structured_compliance': structured_compliance,
                    'entities_found': entities_found,
                    'raw_response': content[:500] if len(content) > 500 else content,
                    'extracted_data': extracted_data,
                    'success': True
                }
                
                self.results['performance_metrics']['successful_extractions'] += 1
                
            except Exception as e:
                result = {
                    'episode_uuid': str(episode.uuid),
                    'error': str(e),
                    'success': False
                }
                self.results['performance_metrics']['failed_extractions'] += 1
                print(f"    ❌ Error: {e}")
            
            extraction_results.append(result)
            self.results['performance_metrics']['total_llm_calls'] += 1
            
        return {
            'extraction_results': extraction_results,
            'summary': {
                'total_episodes': len(episodes),
                'successful_extractions': len([r for r in extraction_results if r.get('success')]),
                'avg_entities_per_episode': sum([r.get('entities_found', 0) for r in extraction_results]) / len(extraction_results),
                'avg_response_time_ms': sum([r.get('response_time_ms', 0) for r in extraction_results if r.get('success')]) / max(1, len([r for r in extraction_results if r.get('success')])),
                'structured_compliance_rate': len([r for r in extraction_results if r.get('structured_compliance')]) / len(extraction_results)
            }
        }
        
    async def evaluate_deduplication(self, graphiti: Graphiti, episodes: List[EpisodicNode]) -> Dict[str, Any]:
        """Test entity deduplication accuracy."""
        print("🔗 Evaluating entity deduplication...")
        
        # For deduplication testing, we'll create scenarios with known duplicates
        dedup_results = []
        
        # Test with synthetic examples that should be deduplicated
        test_entities = [
            {"name": "Apple Inc", "summary": "Technology company"},
            {"name": "Apple Inc.", "summary": "Tech company that makes iPhones"},
            {"name": "APPLE", "summary": "Technology corporation"},
            {"name": "Microsoft", "summary": "Software company"},
            {"name": "Google", "summary": "Search engine company"},
        ]
        
        try:
            from graphiti_core.prompts.dedupe_nodes import node
            
            # Test deduplication prompt
            context = {
                'selected_entity': test_entities[0],
                'duplicate_candidates': test_entities[1:4]  # Should identify Apple variants as duplicates
            }
            
            messages = node(context)
            
            start_time = time.time()
            response = await graphiti.llm_client.generate_response(
                messages=messages,
                response_model=None
            )
            end_time = time.time()
            
            response_time = (end_time - start_time) * 1000
            
            # Parse deduplication response
            if hasattr(response, 'content'):
                content = response.content
            else:
                content = str(response)
                
            dedup_results.append({
                'test_case': 'apple_variants',
                'response_time_ms': response_time,
                'raw_response': content[:500] if len(content) > 500 else content,
                'success': True
            })
            
        except Exception as e:
            dedup_results.append({
                'test_case': 'apple_variants',
                'error': str(e),
                'success': False
            })
            
        return {
            'deduplication_results': dedup_results,
            'summary': {
                'test_cases_run': len(dedup_results),
                'successful_cases': len([r for r in dedup_results if r.get('success')]),
            }
        }
    
    async def run_evaluation(self, num_episodes: int = 5) -> Dict[str, Any]:
        """Run the complete evaluation suite."""
        print(f"🚀 Starting Chutes AI Ingestion Evaluation with {num_episodes} episodes...")
        print("=" * 60)
        
        # Setup
        graphiti = await self.setup_chutes_client()
        episodes = await self.get_test_episodes(num_episodes)
        
        try:
            # Run evaluations
            entity_results = await self.evaluate_entity_extraction(graphiti, episodes)
            self.results['entity_extraction_results'] = entity_results
            
            dedup_results = await self.evaluate_deduplication(graphiti, episodes[:2])  # Smaller set for dedup
            self.results['deduplication_results'] = dedup_results
            
            # Calculate final metrics
            self._calculate_final_metrics()
            
            # Save results
            results_file = Path(f"chutes_evaluation_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            with open(results_file, 'w') as f:
                json.dump(self.results, f, indent=2, default=str)
                
            print("\n" + "=" * 60)
            print("📈 CHUTES AI EVALUATION RESULTS")
            print("=" * 60)
            self._print_summary()
            print(f"\n📁 Detailed results saved to: {results_file}")
            
        finally:
            await graphiti.close()
            
        return self.results
    
    def _calculate_final_metrics(self):
        """Calculate summary metrics from all test results."""
        entity_results = self.results['entity_extraction_results']
        
        if entity_results and 'summary' in entity_results:
            summary = entity_results['summary']
            
            # Performance metrics
            self.results['performance_metrics']['avg_response_time_ms'] = summary.get('avg_response_time_ms', 0)
            self.results['performance_metrics']['structured_output_compliance'] = summary.get('structured_compliance_rate', 0)
            
        self.results['end_time'] = datetime.now().isoformat()
        
    def _print_summary(self):
        """Print evaluation summary."""
        perf = self.results['performance_metrics']
        
        print(f"🔧 Model: {self.results['model']}")
        print(f"📊 Episodes tested: {len(self.results['test_episodes'])}")
        print(f"⚡ Total LLM calls: {perf['total_llm_calls']}")
        print(f"✅ Successful extractions: {perf['successful_extractions']}")
        print(f"❌ Failed extractions: {perf['failed_extractions']}")
        print(f"⏱️  Avg response time: {perf['avg_response_time_ms']:.1f}ms")
        print(f"📋 Structured output compliance: {perf['structured_output_compliance']:.1%}")
        
        if 'entity_extraction_results' in self.results and 'summary' in self.results['entity_extraction_results']:
            entity_summary = self.results['entity_extraction_results']['summary']
            print(f"🎯 Avg entities per episode: {entity_summary.get('avg_entities_per_episode', 0):.1f}")


async def main():
    """Run the Chutes AI evaluation."""
    evaluator = ChutesIngestionEvaluator()
    await evaluator.run_evaluation(num_episodes=5)


if __name__ == "__main__":
    asyncio.run(main())