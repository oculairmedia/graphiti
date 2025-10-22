#!/usr/bin/env python3
"""
Test Cerebras-based ingestion pipeline for Graphiti.
This will test ingesting data into FalkorDB using Qwen for LLM operations.
Adapted from test_ollama_ingestion.py for Cerebras testing.
"""

import asyncio
import os
from datetime import datetime

from graphiti_core import Graphiti
from graphiti_core.embedder import EmbedderClient
from graphiti_core.llm_client.cerebras_client import CerebrasClient, DEFAULT_CEREBRAS_MODEL
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.nodes import EpisodicNode, EpisodeType

# FalkorDB connection details
FALKORDB_HOST = os.getenv('FALKORDB_HOST', 'localhost')
FALKORDB_PORT = os.getenv('FALKORDB_PORT', '6389')
FALKORDB_URI = f'bolt://{FALKORDB_HOST}:{FALKORDB_PORT}'


class OllamaEmbedder(EmbedderClient):
    """Custom embedder using Ollama (keeping embeddings separate from Cerebras LLM)."""

    def __init__(self, base_url: str, model: str = 'mxbai-embed-large'):
        self.base_url = base_url
        self.model = model
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(base_url=base_url, api_key='ollama')
        print(f'✓ Initialized OllamaEmbedder with model: {model}')

    async def create(self, input_data: list[str]) -> list[list[float]]:
        """Create embeddings using Ollama."""
        try:
            response = await self.client.embeddings.create(model=self.model, input=input_data)
            return [item.embedding for item in response.data]
        except Exception as e:
            print(f'❌ Error creating embeddings: {e}')
            raise


async def test_cerebras_ingestion():
    """Test the ingestion pipeline with Cerebras/Qwen."""
    print('🧠 Testing Graphiti ingestion with Cerebras/Qwen...')
    print(f'📡 Connecting to FalkorDB at {FALKORDB_URI}')

    # Initialize Cerebras LLM client
    cerebras_config = LLMConfig(
        model=DEFAULT_CEREBRAS_MODEL,
        temperature=0.3,  # Good balance for extraction tasks
        max_tokens=1500,  # Allow for detailed extractions
    )
    
    cerebras_client = CerebrasClient(config=cerebras_config)
    
    # Initialize Ollama embedder
    ollama_embedder = OllamaEmbedder(
        base_url='http://192.168.50.80:11434/v1',
        model='mxbai-embed-large'
    )

    # Initialize Graphiti with Cerebras + Ollama
    graphiti = Graphiti(
        uri=FALKORDB_URI, 
        user='', 
        password='',
        llm_client=cerebras_client,
        embedder=ollama_embedder
    )
    
    print(f'✓ Initialized Graphiti with Qwen ({DEFAULT_CEREBRAS_MODEL}) + Ollama embeddings')

    # Test data - scenarios that play to Qwen's strengths
    test_episodes = [
        {
            'name': 'AI Research Collaboration',
            'content': """
            Dr. Elena Rodriguez, the lead AI researcher at DeepMind Technologies, announced a breakthrough
            in transformer architecture optimization. The research team, including Dr. Wang Li (neural networks specialist)
            and Dr. Amir Hassan (computational linguistics), developed a new attention mechanism that reduces
            computational complexity by 40% while maintaining accuracy.
            
            The collaboration with Stanford University's AI Lab, led by Professor Sarah Chen, will focus on
            implementing this optimization in large language models. The project received $2.5M funding
            from the National Science Foundation and is expected to publish results in NeurIPS 2024.
            
            Key innovations include:
            1. Sparse attention patterns for efficient processing
            2. Dynamic head allocation in multi-head attention
            3. Gradient checkpointing optimizations for memory efficiency
            """,
            'timestamp': datetime(2024, 8, 15, 9, 30, 0),
            'source': 'AI Research Newsletter',
        },
        {
            'name': 'Quantum Computing Partnership',
            'content': """
            QuantumTech Inc. announced a strategic partnership with IBM Quantum Network to develop
            quantum-enhanced machine learning algorithms. The collaboration will be led by
            Dr. Maria Kowalski (quantum algorithms) and Dr. James Mitchell (quantum hardware).
            
            The partnership focuses on:
            - Quantum advantage in optimization problems
            - Hybrid quantum-classical neural networks  
            - Error correction methods for NISQ devices
            
            Initial experiments will use IBM's 127-qubit quantum processor to train variational
            quantum eigensolver (VQE) models for molecular simulation tasks. The project timeline
            spans 3 years with quarterly milestones and peer-reviewed publications.
            """,
            'timestamp': datetime(2024, 8, 16, 14, 15, 0),
            'source': 'Quantum Computing Today',
        },
        {
            'name': 'Code Generation Breakthrough',
            'content': """
            The development team at CodeAI Solutions, including senior engineers Alice Zhang,
            Bob Thompson, and Carol Martinez, released an advanced code generation model
            that outperforms existing solutions on HumanEval and MBPP benchmarks.
            
            Technical achievements:
            - 89% pass rate on HumanEval (vs 85% previous best)
            - Support for 50+ programming languages  
            - Real-time debugging assistance
            - Automatic documentation generation
            
            The model uses a novel training approach combining:
            1. Reinforcement learning from human feedback (RLHF)
            2. Curriculum learning with graduated difficulty
            3. Multi-task learning across programming paradigms
            
            Beta testing begins next month with 1000 selected developers.
            """,
            'timestamp': datetime(2024, 8, 17, 11, 45, 0),
            'source': 'Software Engineering Digest',
        },
    ]

    print('\n📝 Ingesting test episodes with Qwen extraction...')

    ingestion_results = []
    
    for i, episode_data in enumerate(test_episodes, 1):
        print(f'\n[{i}/{len(test_episodes)}] Processing: {episode_data["name"]}')

        try:
            # Add to graph using Qwen for entity/relationship extraction
            result = await graphiti.add_episode(
                name=episode_data['name'],
                episode_body=episode_data['content'],
                source_description=episode_data['source'],
                reference_time=episode_data['timestamp'],
                source=EpisodeType.text,
                group_id='qwen_ai_research',  # Group for Qwen-extracted content
            )
            
            ingestion_results.append(result)
            print(f'   ✅ Successfully ingested with Qwen: {episode_data["name"]}')
            
            # Show extraction details
            if result:
                if hasattr(result, 'nodes') and result.nodes:
                    print(f'      - Entities extracted: {len(result.nodes)}')
                    # Show a few key entities
                    for node in result.nodes[:3]:
                        node_labels = ', '.join(node.labels) if hasattr(node, 'labels') and node.labels else 'Unknown'
                        print(f'        • {node.name} ({node_labels})')
                
                if hasattr(result, 'edges') and result.edges:
                    print(f'      - Relationships extracted: {len(result.edges)}')
                    # Show a key relationship
                    if result.edges:
                        edge = result.edges[0]
                        print(f'        • "{edge.fact}"')

        except Exception as e:
            print(f'   ❌ Error ingesting episode: {e}')
            return False

    print('\n🔍 Verifying Qwen extractions through search...')

    # Test searches that leverage Qwen's extraction quality
    test_queries = [
        'Dr. Elena Rodriguez AI researcher',
        'transformer architecture optimization',
        'quantum machine learning algorithms',
        'code generation HumanEval benchmark',
        'reinforcement learning human feedback',
    ]

    search_results = {}
    
    for query in test_queries:
        print(f"\n🔎 Searching for: '{query}'")
        try:
            results = await graphiti.search(query=query, limit=5)

            if results:
                search_results[query] = results
                print(f'   ✅ Found {len(results)} results')
                for j, result in enumerate(results[:2], 1):
                    if hasattr(result, 'node'):
                        node = result.node
                        print(f'   {j}. {node.name}')
                        if hasattr(result, 'score'):
                            print(f'      Score: {result.score:.3f}')
                        # Show summary if Qwen provided one
                        if hasattr(node, 'summary') and node.summary:
                            summary = node.summary[:80] + '...' if len(node.summary) > 80 else node.summary
                            print(f'      Summary: {summary}')
                    else:
                        print(f'   {j}. {result}')
            else:
                search_results[query] = []
                print(f'   ⚠️  No results found')

        except Exception as e:
            print(f'   ❌ Search error: {e}')

    # Advanced search tests for Qwen-extracted relationships
    print('\n🔗 Testing relationship search (Qwen extractions)...')
    try:
        edge_results = await graphiti.search_edges(query='collaboration partnership', limit=5)
        if edge_results:
            print(f'   ✅ Found {len(edge_results)} relationship edges')
            for i, edge in enumerate(edge_results[:3], 1):
                print(f'   {i}. {edge.name}: "{edge.fact}"')
        else:
            print('   ⚠️ No relationship edges found')
    except Exception as e:
        print(f'   ❌ Relationship search error: {e}')

    # Get comprehensive graph statistics
    print('\n📊 Qwen Extraction Statistics:')
    try:
        from falkordb import FalkorDB

        db = FalkorDB(host=FALKORDB_HOST, port=int(FALKORDB_PORT))
        graph = db.select_graph('graphiti_migration')

        # Count nodes by type
        node_stats = graph.query("""
            MATCH (n)
            RETURN labels(n)[0] as type, count(n) as count
            ORDER BY count DESC
        """)

        print('   📊 Node distribution:')
        total_nodes = 0
        for row in node_stats.result_set:
            node_type = row[0] if row[0] else 'Unlabeled'
            count = row[1]
            total_nodes += count
            print(f'     - {node_type}: {count}')
        
        print(f'   Total nodes: {total_nodes}')

        # Count relationships with details
        edge_stats = graph.query("""
            MATCH ()-[r]->()
            RETURN type(r) as type, count(r) as count
            ORDER BY count DESC
        """)

        print('   🔗 Relationship distribution:')
        total_edges = 0
        for row in edge_stats.result_set:
            edge_type = row[0] if row[0] else 'Unknown'
            count = row[1]
            total_edges += count
            print(f'     - {edge_type}: {count}')
            
        print(f'   Total relationships: {total_edges}')

        # Query for Qwen-specific extractions (group_id)
        qwen_stats = graph.query("""
            MATCH (n {group_id: 'qwen_ai_research'})
            RETURN count(n) as qwen_nodes
        """)
        
        if qwen_stats.result_set:
            qwen_node_count = qwen_stats.result_set[0][0]
            print(f'   🧠 Qwen-extracted nodes: {qwen_node_count}')

    except Exception as e:
        print(f'   ❌ Error getting statistics: {e}')

    # Quality assessment of extractions
    print('\n🎯 Qwen Extraction Quality Assessment:')
    
    # Check for complex entity types (Qwen should excel at this)
    complex_entity_types = ['person', 'organization', 'technology', 'methodology', 'financial_metric']
    entities_by_type = {}
    
    for result_list in search_results.values():
        for result in result_list:
            if hasattr(result, 'node'):
                node = result.node
                if hasattr(node, 'labels') and node.labels:
                    for label in node.labels:
                        if label.lower() in complex_entity_types:
                            entities_by_type[label] = entities_by_type.get(label, 0) + 1

    if entities_by_type:
        print('   📈 Complex entity types found:')
        for entity_type, count in entities_by_type.items():
            print(f'     - {entity_type}: {count}')
    else:
        print('   ⚠️ Limited complex entity type extraction')

    print('\n✅ Cerebras/Qwen ingestion test completed!')
    return True


async def check_cerebras_connection():
    """Check if Cerebras API is accessible."""
    
    print('\n🔌 Checking Cerebras API connection...')
    
    try:
        # Create a test client
        config = LLMConfig(model=DEFAULT_CEREBRAS_MODEL, temperature=0.1, max_tokens=50)
        client = CerebrasClient(config=config)
        
        # Simple test message
        from graphiti_core.prompts.models import Message
        test_msg = Message(role='user', content='Respond with: "Cerebras connection successful"')
        
        response = await asyncio.wait_for(
            client._generate_response([test_msg], max_tokens=50),
            timeout=15.0
        )
        
        if response:
            print('   ✅ Cerebras API is accessible')
            print(f'   📝 Model: {DEFAULT_CEREBRAS_MODEL}')
            return True
        else:
            print('   ❌ No response from Cerebras API')
            return False
            
    except asyncio.TimeoutError:
        print('   ⏱️ Cerebras API connection timed out')
        return False
    except Exception as e:
        print(f'   ❌ Cannot connect to Cerebras: {e}')
        return False


async def main():
    """Main test function."""
    print('🧠 Graphiti + Cerebras/Qwen Integration Test')
    print('=' * 60)

    # Check environment
    cerebras_api_key = os.getenv('CEREBRAS_API_KEY')
    if not cerebras_api_key:
        print('⚠️  CEREBRAS_API_KEY is not set in environment')
        print('   Please set your Cerebras API key to run this test')
        return

    # Check Cerebras connection
    if not await check_cerebras_connection():
        print('\n❌ Cannot connect to Cerebras API. Please ensure:')
        print('   1. CEREBRAS_API_KEY is correctly set')
        print('   2. You have access to the Cerebras API')
        print('   3. The Qwen model is available in your account')
        return

    # Check Ollama embeddings connection (we're using hybrid approach)
    ollama_url = os.getenv('OLLAMA_EMBEDDING_BASE_URL', 'http://192.168.50.80:11434/v1')
    print(f'\n🔌 Using Ollama embeddings from: {ollama_url}')

    # Run ingestion test
    success = await test_cerebras_ingestion()
    
    if success:
        print('\n🎉 Cerebras/Qwen ingestion test completed successfully!')
        print('Key achievements:')
        print('  ✅ Successfully integrated Qwen for entity extraction')
        print('  ✅ Maintained Ollama embeddings for semantic search')
        print('  ✅ Validated hybrid LLM + embedding approach')
        print('  ✅ Demonstrated Qwen\'s structured extraction capabilities')
    else:
        print('\n❌ Test completed with errors - check logs above')


if __name__ == '__main__':
    asyncio.run(main())