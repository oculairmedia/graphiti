#!/usr/bin/env python3
"""
End-to-End Pipeline Integration Test for Cerebras/Qwen.
Tests the complete ingestion → extraction → storage → retrieval → analysis pipeline.
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from graphiti_core import Graphiti
from graphiti_core.embedder import EmbedderClient
from graphiti_core.llm_client.cerebras_client import CerebrasClient, DEFAULT_CEREBRAS_MODEL
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.nodes import EpisodeType


@dataclass
class PipelineStage:
    """Represents a stage in the pipeline test."""
    name: str
    start_time: float
    end_time: Optional[float] = None
    success: bool = False
    data: Any = None
    error: Optional[str] = None
    
    @property
    def duration(self) -> float:
        """Get stage duration in seconds."""
        if self.end_time is None:
            return 0.0
        return self.end_time - self.start_time


class OllamaEmbedder(EmbedderClient):
    """Ollama embedder for hybrid approach."""

    def __init__(self, base_url: str = 'http://192.168.50.80:11434/v1', model: str = 'mxbai-embed-large'):
        self.base_url = base_url
        self.model = model
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(base_url=base_url, api_key='ollama')

    async def create(self, input_data: list[str]) -> list[list[float]]:
        """Create embeddings using Ollama."""
        try:
            response = await self.client.embeddings.create(model=self.model, input=input_data)
            return [item.embedding for item in response.data]
        except Exception as e:
            print(f'❌ Error creating embeddings: {e}')
            raise


class PipelineTester:
    """End-to-end pipeline tester for Cerebras/Qwen integration."""
    
    def __init__(self):
        self.graphiti: Optional[Graphiti] = None
        self.stages: List[PipelineStage] = []
        self.test_data = self._generate_test_data()

    def _generate_test_data(self) -> List[Dict[str, Any]]:
        """Generate comprehensive test data for pipeline testing."""
        
        return [
            {
                'name': 'AI Research Collaboration Network',
                'content': '''
                The Stanford AI Lab, directed by Dr. Sarah Chen, announced a multi-institutional 
                collaboration with MIT's Computer Science and Artificial Intelligence Laboratory (CSAIL) 
                led by Prof. Michael Rodriguez, and CMU's Machine Learning Department under Dr. Aisha Patel. 
                
                The $5.8M NSF-funded project, titled "Next-Generation Transformer Architectures," 
                will span 4 years and involve 15 graduate students and 8 postdocs. Key research areas include:
                
                1. Sparse Attention Mechanisms: Led by PhD student Alice Wang (Stanford)
                2. Multi-Modal Learning: Supervised by Dr. James Liu (MIT) and Dr. Maria Santos (CMU)
                3. Efficient Training Methods: Joint effort between Bob Chen (Stanford) and Carol Johnson (MIT)
                4. Benchmark Development: Coordinated by David Kim (CMU)
                
                The collaboration has already produced 3 preprints on arXiv and submitted 2 papers 
                to NeurIPS 2024. Industry partners include Google DeepMind, OpenAI, and Anthropic, 
                providing computational resources worth $1.2M annually.
                ''',
                'source': 'Academic Research Network',
                'timestamp': datetime.now() - timedelta(days=30),
                'expected_entities': ['Stanford AI Lab', 'MIT CSAIL', 'CMU Machine Learning', 'Dr. Sarah Chen', 
                                    'Prof. Michael Rodriguez', 'Dr. Aisha Patel', 'NSF', 'Google DeepMind', 'OpenAI', 'Anthropic'],
                'expected_concepts': ['transformer architecture', 'sparse attention', 'multi-modal learning', 'efficient training']
            },
            {
                'name': 'Quantum-AI Hybrid Computing Breakthrough',
                'content': '''
                QuantumTech Inc., a quantum computing startup founded by Dr. Elena Kowalski (former IBM Research), 
                announced a breakthrough in quantum-enhanced machine learning. The company's quantum processor, 
                featuring 256 superconducting qubits with 99.9% fidelity, achieved quantum advantage on specific 
                optimization problems.
                
                Technical Achievements:
                - Variational Quantum Eigensolver (VQE) implementation for molecular simulation
                - Quantum Approximate Optimization Algorithm (QAOA) for logistics problems  
                - Hybrid quantum-classical neural networks with 35% speedup over classical methods
                - Error correction using surface codes on NISQ-era devices
                
                The research team includes:
                - Chief Quantum Officer: Dr. Ahmad Hassan (PhD Physics, Caltech)
                - Lead Software Engineer: Jennifer Zhang (MS Computer Science, Stanford)
                - Quantum Algorithm Researcher: Dr. Carlos Mendez (PhD Applied Math, MIT)
                
                Partnerships with BMW (automotive optimization), Roche (drug discovery), and 
                Goldman Sachs (portfolio optimization) are already showing promising results. 
                Series B funding of $45M was led by Andreessen Horowitz with participation 
                from Google Ventures and In-Q-Tel.
                ''',
                'source': 'Quantum Computing Industry Report',
                'timestamp': datetime.now() - timedelta(days=15),
                'expected_entities': ['QuantumTech Inc', 'Dr. Elena Kowalski', 'IBM Research', 'Dr. Ahmad Hassan', 
                                    'Jennifer Zhang', 'Dr. Carlos Mendez', 'BMW', 'Roche', 'Goldman Sachs'],
                'expected_concepts': ['quantum advantage', 'VQE', 'QAOA', 'NISQ', 'surface codes']
            },
            {
                'name': 'Advanced Code Generation Model Release',
                'content': '''
                CodeGen-X, developed by the 25-person engineering team at Syntax AI (San Francisco), 
                achieved state-of-the-art performance across multiple programming benchmarks:
                
                Benchmark Results:
                - HumanEval: 94.2% pass@1 (previous best: 91.5%)
                - MBPP: 91.8% pass@1 (previous best: 89.3%)  
                - CodeContests: 73.4% solve rate (previous best: 68.7%)
                - MultiPL-E: 87.6% average across 18 languages
                - DS-1000: 89.2% on data science problems
                
                Model Architecture:
                - 180B parameters with mixture-of-experts (MoE) design
                - 32 expert modules, 4 active per token
                - 8K context length with sliding window attention
                - Trained on 2.1TB of high-quality code from 120+ programming languages
                
                The training pipeline involved:
                1. Data collection and filtering (6 months): Led by Dr. Lisa Park
                2. Model architecture design (4 months): Supervised by CTO Alex Rodriguez  
                3. Distributed training (8 months): Managed by MLOps team under Sarah Kim
                4. Safety alignment (3 months): Coordinated by Ethics team led by Dr. Robert Taylor
                
                Commercial deployment includes GitHub Copilot integration, VS Code extension, 
                and API access for enterprise customers including Microsoft, Google, and Meta.
                The model is available through OpenAI-compatible endpoints at $0.002 per 1K tokens.
                ''',
                'source': 'Software Engineering Publication',
                'timestamp': datetime.now() - timedelta(days=7),
                'expected_entities': ['CodeGen-X', 'Syntax AI', 'Dr. Lisa Park', 'Alex Rodriguez', 'Sarah Kim', 
                                    'Dr. Robert Taylor', 'GitHub Copilot', 'Microsoft', 'Google', 'Meta'],
                'expected_concepts': ['mixture-of-experts', 'sliding window attention', 'code generation', 'safety alignment']
            }
        ]

    async def start_stage(self, name: str) -> PipelineStage:
        """Start a new pipeline stage."""
        stage = PipelineStage(name=name, start_time=time.time())
        self.stages.append(stage)
        print(f'🔄 Starting: {name}')
        return stage

    async def complete_stage(self, stage: PipelineStage, success: bool = True, data: Any = None, error: str = None):
        """Complete a pipeline stage."""
        stage.end_time = time.time()
        stage.success = success
        stage.data = data
        stage.error = error
        
        status = '✅' if success else '❌'
        print(f'{status} Completed: {stage.name} ({stage.duration:.2f}s)')
        if error:
            print(f'   Error: {error}')

    async def test_initialization(self) -> bool:
        """Test system initialization."""
        stage = await self.start_stage('System Initialization')
        
        try:
            # Initialize Cerebras client
            cerebras_config = LLMConfig(
                model=DEFAULT_CEREBRAS_MODEL,
                temperature=0.3,
                max_tokens=2000,
            )
            cerebras_client = CerebrasClient(config=cerebras_config)
            
            # Initialize embedder
            embedder = OllamaEmbedder()
            
            # Initialize Graphiti
            self.graphiti = Graphiti(
                uri='bolt://localhost:6389',
                user='',
                password='',
                llm_client=cerebras_client,
                embedder=embedder
            )
            
            # Build indices and constraints
            await self.graphiti.build_indices_and_constraints()
            
            await self.complete_stage(stage, success=True, data={
                'llm_model': DEFAULT_CEREBRAS_MODEL,
                'embedder_model': embedder.model,
                'database': 'FalkorDB'
            })
            return True
            
        except Exception as e:
            await self.complete_stage(stage, success=False, error=str(e))
            return False

    async def test_data_ingestion(self) -> bool:
        """Test data ingestion pipeline."""
        stage = await self.start_stage('Data Ingestion Pipeline')
        
        ingestion_results = []
        
        try:
            for i, episode_data in enumerate(self.test_data, 1):
                print(f'   📄 Processing episode {i}/{len(self.test_data)}: {episode_data["name"]}')
                
                episode_start = time.time()
                try:
                    result = await asyncio.wait_for(
                        self.graphiti.add_episode(
                            name=episode_data['name'],
                            episode_body=episode_data['content'],
                            source_description=episode_data['source'],
                            reference_time=episode_data['timestamp'],
                            source=EpisodeType.text,
                        ),
                        timeout=180.0  # 3 minutes per episode
                    )
                    
                    episode_time = time.time() - episode_start
                    
                    if result:
                        entities_count = len(result.nodes) if hasattr(result, 'nodes') and result.nodes else 0
                        relationships_count = len(result.edges) if hasattr(result, 'edges') and result.edges else 0
                        
                        ingestion_results.append({
                            'episode': episode_data['name'],
                            'time': episode_time,
                            'entities': entities_count,
                            'relationships': relationships_count,
                            'success': True
                        })
                        
                        print(f'     ✅ Extracted {entities_count} entities, {relationships_count} relationships ({episode_time:.2f}s)')
                        
                        # Validate expected entities were found
                        extracted_names = [node.name.lower() for node in result.nodes] if result.nodes else []
                        expected_found = sum(1 for expected in episode_data['expected_entities'] 
                                           if any(expected.lower() in name for name in extracted_names))
                        
                        print(f'     📊 Found {expected_found}/{len(episode_data["expected_entities"])} expected entities')
                    else:
                        ingestion_results.append({
                            'episode': episode_data['name'],
                            'time': episode_time,
                            'success': False,
                            'error': 'No result returned'
                        })
                        
                except asyncio.TimeoutError:
                    ingestion_results.append({
                        'episode': episode_data['name'],
                        'success': False,
                        'error': 'Timeout after 180 seconds'
                    })
                    print(f'     ⏱️ Timeout processing episode')
                    
                except Exception as e:
                    ingestion_results.append({
                        'episode': episode_data['name'],
                        'success': False,
                        'error': str(e)
                    })
                    print(f'     ❌ Error: {e}')
                
                # Brief pause between episodes
                await asyncio.sleep(2)
            
            # Calculate success rate
            successful = len([r for r in ingestion_results if r.get('success', False)])
            success_rate = successful / len(ingestion_results) * 100
            
            await self.complete_stage(stage, 
                                    success=success_rate >= 80,  # 80% success threshold
                                    data={
                                        'results': ingestion_results,
                                        'success_rate': success_rate,
                                        'total_episodes': len(ingestion_results)
                                    })
            
            return success_rate >= 80
            
        except Exception as e:
            await self.complete_stage(stage, success=False, error=str(e))
            return False

    async def test_data_retrieval(self) -> bool:
        """Test data retrieval and search functionality."""
        stage = await self.start_stage('Data Retrieval & Search')
        
        try:
            # Wait for indexing
            await asyncio.sleep(5)
            
            retrieval_results = []
            
            # Test semantic search queries
            search_queries = [
                'artificial intelligence research collaboration Stanford MIT',
                'quantum computing machine learning hybrid algorithms',
                'code generation programming benchmarks performance',
                'Dr. Sarah Chen transformer architecture optimization',
                'funding investment venture capital AI startups'
            ]
            
            for query in search_queries:
                print(f'   🔍 Testing search: "{query}"')
                
                search_start = time.time()
                try:
                    results = await asyncio.wait_for(
                        self.graphiti.search(query=query, limit=5),
                        timeout=30.0
                    )
                    search_time = time.time() - search_start
                    
                    if results:
                        retrieval_results.append({
                            'query': query,
                            'results_count': len(results),
                            'time': search_time,
                            'success': True
                        })
                        print(f'     ✅ Found {len(results)} results ({search_time:.3f}s)')
                        
                        # Show top result details
                        if results and hasattr(results[0], 'node'):
                            node = results[0].node
                            score = getattr(results[0], 'score', 'N/A')
                            print(f'     Top result: {node.name} (score: {score})')
                    else:
                        retrieval_results.append({
                            'query': query,
                            'results_count': 0,
                            'time': search_time,
                            'success': False,
                            'error': 'No results found'
                        })
                        print(f'     ⚠️ No results found')
                        
                except asyncio.TimeoutError:
                    retrieval_results.append({
                        'query': query,
                        'success': False,
                        'error': 'Search timeout'
                    })
                    print(f'     ⏱️ Search timeout')
                    
                except Exception as e:
                    retrieval_results.append({
                        'query': query,
                        'success': False,
                        'error': str(e)
                    })
                    print(f'     ❌ Search error: {e}')
            
            # Test edge search
            print(f'   🔗 Testing relationship search...')
            try:
                edge_results = await self.graphiti.search_edges(query='collaboration partnership research', limit=5)
                edge_count = len(edge_results) if edge_results else 0
                print(f'     ✅ Found {edge_count} relationship edges')
                
                retrieval_results.append({
                    'query': 'edge_search_test',
                    'results_count': edge_count,
                    'success': True
                })
                
            except Exception as e:
                print(f'     ❌ Edge search error: {e}')
                retrieval_results.append({
                    'query': 'edge_search_test',
                    'success': False,
                    'error': str(e)
                })
            
            # Calculate retrieval success rate
            successful_searches = len([r for r in retrieval_results if r.get('success', False)])
            retrieval_success_rate = successful_searches / len(retrieval_results) * 100
            
            await self.complete_stage(stage,
                                    success=retrieval_success_rate >= 70,  # 70% success threshold
                                    data={
                                        'results': retrieval_results,
                                        'success_rate': retrieval_success_rate
                                    })
            
            return retrieval_success_rate >= 70
            
        except Exception as e:
            await self.complete_stage(stage, success=False, error=str(e))
            return False

    async def test_graph_analysis(self) -> bool:
        """Test graph analysis and statistics."""
        stage = await self.start_stage('Graph Analysis & Statistics')
        
        try:
            # Database statistics
            stats = {}
            
            # Count nodes by type
            node_stats = await self.graphiti.driver.execute_query('''
                MATCH (n)
                RETURN labels(n)[0] as node_type, count(n) as count
                ORDER BY count DESC
            ''')
            
            stats['node_distribution'] = {row['node_type']: row['count'] for row in node_stats}
            total_nodes = sum(stats['node_distribution'].values())
            
            # Count relationships
            edge_stats = await self.graphiti.driver.execute_query('''
                MATCH ()-[r]->()
                RETURN type(r) as relationship_type, count(r) as count
                ORDER BY count DESC
                LIMIT 10
            ''')
            
            stats['relationship_distribution'] = {row['relationship_type']: row['count'] for row in edge_stats}
            total_relationships = sum(stats['relationship_distribution'].values())
            
            # Calculate graph metrics
            stats['total_nodes'] = total_nodes
            stats['total_relationships'] = total_relationships
            stats['density'] = total_relationships / (total_nodes * (total_nodes - 1)) if total_nodes > 1 else 0
            
            print(f'   📊 Graph Statistics:')
            print(f'     Total nodes: {total_nodes}')
            print(f'     Total relationships: {total_relationships}')
            print(f'     Graph density: {stats["density"]:.4f}')
            
            # Check for expected entity types
            expected_types = ['Person', 'Organization', 'Technology', 'Concept', 'Event']
            found_types = set(stats['node_distribution'].keys())
            type_coverage = len(found_types.intersection(expected_types)) / len(expected_types)
            
            stats['entity_type_coverage'] = type_coverage
            print(f'     Entity type coverage: {type_coverage:.2%}')
            
            await self.complete_stage(stage,
                                    success=total_nodes > 50 and total_relationships > 20,  # Minimum thresholds
                                    data=stats)
            
            return total_nodes > 50 and total_relationships > 20
            
        except Exception as e:
            await self.complete_stage(stage, success=False, error=str(e))
            return False

    async def test_pipeline_integrity(self) -> bool:
        """Test overall pipeline integrity and data consistency."""
        stage = await self.start_stage('Pipeline Integrity Check')
        
        try:
            integrity_checks = []
            
            # Check 1: Episode-Entity consistency
            episode_check = await self.graphiti.driver.execute_query('''
                MATCH (e:EpisodicNode)-[mentions]->(entity)
                RETURN count(DISTINCT e) as episodes_with_entities,
                       count(DISTINCT entity) as mentioned_entities,
                       count(mentions) as total_mentions
            ''')
            
            if episode_check:
                episodes_with_entities = episode_check[0]['episodes_with_entities']
                mentioned_entities = episode_check[0]['mentioned_entities']
                total_mentions = episode_check[0]['total_mentions']
                
                integrity_checks.append({
                    'check': 'episode_entity_consistency',
                    'episodes_with_entities': episodes_with_entities,
                    'mentioned_entities': mentioned_entities,
                    'total_mentions': total_mentions,
                    'passed': episodes_with_entities > 0 and mentioned_entities > 0
                })
                
                print(f'   🔗 Episode-Entity links: {episodes_with_entities} episodes mention {mentioned_entities} entities')
            
            # Check 2: Temporal data integrity
            temporal_check = await self.graphiti.driver.execute_query('''
                MATCH (n)
                WHERE n.created_at IS NOT NULL
                RETURN count(n) as nodes_with_timestamps
            ''')
            
            if temporal_check:
                nodes_with_timestamps = temporal_check[0]['nodes_with_timestamps']
                integrity_checks.append({
                    'check': 'temporal_integrity',
                    'nodes_with_timestamps': nodes_with_timestamps,
                    'passed': nodes_with_timestamps > 0
                })
                
                print(f'   ⏰ Temporal integrity: {nodes_with_timestamps} nodes have timestamps')
            
            # Check 3: Entity relationship richness
            relationship_check = await self.graphiti.driver.execute_query('''
                MATCH (n)-[r]->(m)
                WHERE NOT n:EpisodicNode AND NOT m:EpisodicNode
                RETURN count(DISTINCT n) as connected_entities,
                       count(r) as entity_relationships
            ''')
            
            if relationship_check:
                connected_entities = relationship_check[0]['connected_entities']
                entity_relationships = relationship_check[0]['entity_relationships']
                
                integrity_checks.append({
                    'check': 'relationship_richness',
                    'connected_entities': connected_entities,
                    'entity_relationships': entity_relationships,
                    'passed': connected_entities > 10 and entity_relationships > 5
                })
                
                print(f'   🕸️ Relationship richness: {connected_entities} entities have {entity_relationships} inter-connections')
            
            # Overall integrity score
            passed_checks = len([c for c in integrity_checks if c.get('passed', False)])
            integrity_score = passed_checks / len(integrity_checks) if integrity_checks else 0
            
            print(f'   ✅ Integrity score: {integrity_score:.2%} ({passed_checks}/{len(integrity_checks)} checks passed)')
            
            await self.complete_stage(stage,
                                    success=integrity_score >= 0.8,  # 80% integrity threshold
                                    data={
                                        'checks': integrity_checks,
                                        'integrity_score': integrity_score
                                    })
            
            return integrity_score >= 0.8
            
        except Exception as e:
            await self.complete_stage(stage, success=False, error=str(e))
            return False

    async def cleanup(self):
        """Clean up resources."""
        stage = await self.start_stage('Cleanup')
        
        try:
            if self.graphiti:
                await self.graphiti.close()
            await self.complete_stage(stage, success=True)
        except Exception as e:
            await self.complete_stage(stage, success=False, error=str(e))

    def print_pipeline_report(self):
        """Print comprehensive pipeline test report."""
        
        print('\n📋 CEREBRAS/QWEN PIPELINE INTEGRATION REPORT')
        print('=' * 80)
        
        # Overall pipeline status
        successful_stages = len([s for s in self.stages if s.success])
        total_stages = len(self.stages)
        overall_success_rate = successful_stages / total_stages * 100 if total_stages > 0 else 0
        
        print(f'\n🎯 Overall Pipeline Status: {overall_success_rate:.1f}% ({successful_stages}/{total_stages} stages passed)')
        
        # Stage-by-stage breakdown
        print(f'\n📊 Stage-by-Stage Results:')
        total_time = 0
        for stage in self.stages:
            status = '✅ PASS' if stage.success else '❌ FAIL'
            duration = stage.duration
            total_time += duration
            
            print(f'   {status} {stage.name}: {duration:.2f}s')
            if stage.error:
                print(f'        Error: {stage.error}')
                
        print(f'\n⏱️ Total Pipeline Time: {total_time:.2f}s')
        
        # Detailed data analysis
        for stage in self.stages:
            if stage.data and isinstance(stage.data, dict):
                if stage.name == 'Data Ingestion Pipeline':
                    print(f'\n📝 Ingestion Details:')
                    results = stage.data.get('results', [])
                    for result in results:
                        status = '✅' if result.get('success') else '❌'
                        episode_name = result.get('episode', 'Unknown')
                        print(f'   {status} {episode_name}')
                        if result.get('success'):
                            entities = result.get('entities', 0)
                            relationships = result.get('relationships', 0)
                            time_taken = result.get('time', 0)
                            print(f'       {entities} entities, {relationships} relationships ({time_taken:.2f}s)')
                
                elif stage.name == 'Graph Analysis & Statistics':
                    print(f'\n📊 Graph Analysis:')
                    node_dist = stage.data.get('node_distribution', {})
                    rel_dist = stage.data.get('relationship_distribution', {})
                    
                    print(f'   Entity Types:')
                    for node_type, count in list(node_dist.items())[:5]:
                        print(f'     {node_type}: {count}')
                        
                    print(f'   Relationship Types:')
                    for rel_type, count in list(rel_dist.items())[:5]:
                        print(f'     {rel_type}: {count}')
        
        # Performance recommendations
        print(f'\n💡 Performance Analysis:')
        if total_time > 0:
            stages_by_time = sorted(self.stages, key=lambda s: s.duration, reverse=True)
            slowest_stage = stages_by_time[0]
            print(f'   Slowest stage: {slowest_stage.name} ({slowest_stage.duration:.2f}s)')
            
            if slowest_stage.duration > total_time * 0.5:
                print(f'   ⚠️ Performance bottleneck detected in {slowest_stage.name}')
            
        # Success/failure analysis
        failed_stages = [s for s in self.stages if not s.success]
        if failed_stages:
            print(f'\n❌ Failed Stages Analysis:')
            for stage in failed_stages:
                print(f'   {stage.name}: {stage.error}')
                
        # Final recommendations
        print(f'\n🎯 Recommendations:')
        if overall_success_rate >= 90:
            print('   ✅ Pipeline is production-ready with excellent performance')
        elif overall_success_rate >= 75:
            print('   ⚠️ Pipeline is functional but needs optimization')
            print('   💡 Focus on failed stages and performance bottlenecks')
        else:
            print('   ❌ Pipeline needs significant improvements before production use')
            print('   🔧 Address critical failures and stability issues')


async def main():
    """Run comprehensive pipeline integration test."""
    
    print('🧠 Cerebras/Qwen End-to-End Pipeline Integration Test')
    print('=' * 80)
    print(f'Model: {DEFAULT_CEREBRAS_MODEL}')
    print(f'Test Start: {datetime.now().isoformat()}')
    
    tester = PipelineTester()
    
    # Run pipeline stages
    try:
        # Stage 1: Initialization
        if not await tester.test_initialization():
            print('❌ Initialization failed - aborting pipeline test')
            return
        
        # Stage 2: Data Ingestion
        if not await tester.test_data_ingestion():
            print('⚠️ Ingestion had issues - continuing with retrieval test')
        
        # Stage 3: Data Retrieval
        if not await tester.test_data_retrieval():
            print('⚠️ Retrieval had issues - continuing with analysis')
        
        # Stage 4: Graph Analysis
        if not await tester.test_graph_analysis():
            print('⚠️ Graph analysis had issues - continuing with integrity check')
        
        # Stage 5: Pipeline Integrity
        await tester.test_pipeline_integrity()
        
    except Exception as e:
        print(f'❌ Pipeline test failed with error: {e}')
        
    finally:
        # Cleanup
        await tester.cleanup()
    
    # Generate report
    tester.print_pipeline_report()
    
    print(f'\n🎉 Pipeline integration test completed!')
    print(f'Test End: {datetime.now().isoformat()}')


if __name__ == '__main__':
    asyncio.run(main())