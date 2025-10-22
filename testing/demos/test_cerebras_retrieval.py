#!/usr/bin/env python3
"""
Test data retrieval with Cerebras/Qwen integration.
First adds some data using Qwen's extraction capabilities, then tests various retrieval methods.
Adapted from test_ollama_retrieval.py for Cerebras optimization.
"""

import asyncio
from datetime import datetime

from graphiti_core import Graphiti
from graphiti_core.embedder import EmbedderClient
from graphiti_core.llm_client.cerebras_client import CerebrasClient, DEFAULT_CEREBRAS_MODEL
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.nodes import EpisodeType


class OllamaEmbedder(EmbedderClient):
    """Custom embedder that uses Ollama for embeddings (hybrid approach)."""

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


async def setup_graphiti():
    """Set up Graphiti with Cerebras/Qwen + Ollama embeddings."""
    
    # Initialize Cerebras LLM client with Qwen
    cerebras_config = LLMConfig(
        model=DEFAULT_CEREBRAS_MODEL,
        temperature=0.3,  # Optimal for Qwen extraction consistency
        max_tokens=1500,  # Qwen can handle longer responses efficiently
    )
    
    cerebras_client = CerebrasClient(config=cerebras_config)
    print(f'✓ Initialized Cerebras client with {DEFAULT_CEREBRAS_MODEL}')

    # Initialize Ollama embedder (hybrid approach)
    ollama_embedder = OllamaEmbedder(
        base_url='http://192.168.50.80:11434/v1',
        model='mxbai-embed-large'
    )

    # FalkorDB connection 
    graphiti = Graphiti(
        uri='bolt://localhost:6389',
        user='',
        password='',
        embedder=ollama_embedder,
        llm_client=cerebras_client,
    )

    # Build indices
    await graphiti.build_indices_and_constraints()
    return graphiti


async def add_test_data(graphiti):
    """Add test data optimized for Qwen's strengths."""

    print('\n📝 Adding Qwen-optimized test data to graph...')

    # Test episodes designed for Qwen's capabilities
    test_episodes = [
        {
            'name': 'Advanced AI Research',
            'content': '''
            Dr. Sarah Chen, the lead researcher at Stanford AI Lab, published groundbreaking work on transformer 
            architecture optimization. The research team, including machine learning engineer Bob Martinez and 
            computational linguist Dr. Aisha Patel, developed novel attention mechanisms that reduce inference 
            time by 40% while maintaining 99.2% accuracy on benchmark tasks.
            
            Key innovations include:
            1. Sparse attention patterns with dynamic masking
            2. Multi-head attention with adaptive head allocation  
            3. Layer-wise adaptive learning rates
            4. Gradient accumulation with memory-efficient backpropagation
            
            The work was published in ICML 2024 and has been cited 150+ times.
            ''',
            'source': 'AI Research Journal',
        },
        {
            'name': 'Quantum-Enhanced Machine Learning',
            'content': '''
            QuantumML Inc., led by CEO Dr. Maria Kowalski, announced a breakthrough in quantum-enhanced 
            optimization algorithms. The collaboration with IBM Quantum Network resulted in hybrid 
            quantum-classical neural networks that achieve 25% speedup on specific optimization problems.
            
            Technical achievements:
            - Variational Quantum Eigensolver (VQE) implementation
            - 127-qubit quantum processor utilization  
            - NISQ-era error correction methods
            - Quantum advantage demonstration on traveling salesman problems
            
            The partnership received $3.5M funding from the Department of Energy.
            ''',
            'source': 'Quantum Computing Today',
        },
        {
            'name': 'Code Generation with LLMs',
            'content': '''
            The engineering team at CodeAI Solutions, including software architects Alice Zhang, 
            Bob Thompson, and systems engineer Carol Rodriguez, released an advanced code generation 
            model that achieved state-of-the-art results:
            
            Benchmark Performance:
            - HumanEval: 91.5% pass rate (previous best: 87.2%)
            - MBPP: 89.3% pass rate (previous best: 85.1%)
            - CodeContests: 68.7% solve rate (previous best: 62.4%)
            
            Model Architecture:
            - 175B parameters with mixture-of-experts layers
            - Multi-task training on 50+ programming languages
            - Reinforcement learning from human feedback (RLHF)
            - Curriculum learning with graduated difficulty
            
            Beta testing begins with 2000 selected developers worldwide.
            ''',
            'source': 'Software Engineering Digest',
        },
    ]

    added_episodes = []

    for episode in test_episodes:
        try:
            print(f'\n  Processing with Qwen: {episode["name"]}...')

            # Add episode using Qwen for extraction
            result = await asyncio.wait_for(
                graphiti.add_episode(
                    name=episode['name'],
                    episode_body=episode['content'],
                    source_description=episode['source'],
                    reference_time=datetime.now(),
                    source=EpisodeType.text,
                ),
                timeout=90.0,  # Longer timeout for Qwen processing
            )

            print(f'  ✅ Qwen extraction completed!')
            if result:
                added_episodes.append(result)
                if hasattr(result, 'nodes') and result.nodes:
                    print(f'     Entities extracted by Qwen: {len(result.nodes)}')
                    # Show sample entities
                    for node in result.nodes[:2]:
                        labels = ', '.join(node.labels) if hasattr(node, 'labels') and node.labels else 'N/A'
                        print(f'       • {node.name} ({labels})')
                
                if hasattr(result, 'edges') and result.edges:
                    print(f'     Relationships extracted by Qwen: {len(result.edges)}')

        except asyncio.TimeoutError:
            print(f'  ⏱️ Timeout processing episode with Qwen')
        except Exception as e:
            print(f'  ❌ Error: {e}')

    return added_episodes


async def test_qwen_optimized_retrieval(graphiti):
    """Test retrieval methods optimized for Qwen-extracted content."""

    print('\n🧠 Testing Qwen-Optimized Data Retrieval')
    print('=' * 60)

    # Test 1: Direct database query for Qwen extractions
    print('\n1️⃣ Database Statistics for Qwen Extractions...')
    try:
        node_count = await graphiti.driver.execute_query('MATCH (n) RETURN count(n) as count')
        print(f'✅ Total nodes in graph: {node_count[0]["count"] if node_count else 0}')

        # Get detailed node type distribution (Qwen often creates detailed types)
        node_stats = await graphiti.driver.execute_query('''
            MATCH (n)
            RETURN labels(n)[0] as primary_type, 
                   size(labels(n)) as label_count,
                   count(n) as count
            ORDER BY count DESC
        ''')
        
        if node_stats:
            print('\n   Node distribution (Qwen extraction results):')
            for stat in node_stats:
                primary = stat["primary_type"] if stat["primary_type"] else 'Unlabeled'
                label_count = stat["label_count"]
                count = stat["count"]
                print(f'   - {primary} ({label_count} labels): {count} nodes')

        # Check relationship richness (Qwen typically creates rich relationships)
        edge_stats = await graphiti.driver.execute_query('''
            MATCH ()-[r]->() 
            RETURN type(r) as relationship_type, count(r) as count
            ORDER BY count DESC
            LIMIT 10
        ''')
        
        if edge_stats:
            print('\n   Top relationship types (Qwen extractions):')
            for stat in edge_stats:
                rel_type = stat["relationship_type"] if stat["relationship_type"] else 'Unknown'
                count = stat["count"]
                print(f'   - {rel_type}: {count} relationships')

    except Exception as e:
        print(f'❌ Database query error: {e}')

    # Test 2: Search for technical concepts (Qwen's strength)
    print("\n2️⃣ Technical Concept Search (Qwen speciality)...")
    technical_queries = [
        'transformer architecture attention mechanism',
        'quantum computing VQE algorithm',
        'code generation benchmarks HumanEval',
        'machine learning optimization gradient',
        'neural network reinforcement learning'
    ]
    
    for query in technical_queries:
        try:
            print(f'\n   🔍 Searching: "{query}"')
            search_results = await graphiti.search(query=query, limit=3)

            if search_results:
                print(f'   ✅ Found {len(search_results)} results')
                for i, result in enumerate(search_results, 1):
                    if hasattr(result, 'node'):
                        node = result.node
                        node_labels = ', '.join(node.labels) if hasattr(node, 'labels') and node.labels else 'N/A'
                        print(f'     {i}. {node.name} ({node_labels})')
                        if hasattr(result, 'score'):
                            print(f'        Score: {result.score:.3f}')
                        # Show Qwen-generated summary if available
                        if hasattr(node, 'summary') and node.summary:
                            summary = node.summary[:80] + '...' if len(node.summary) > 80 else node.summary
                            print(f'        Summary: {summary}')
            else:
                print(f'   ⚠️ No results for: {query}')

        except Exception as e:
            print(f'   ❌ Search error for "{query}": {e}')

    # Test 3: Complex relationship queries (leveraging Qwen's structured extraction)
    print("\n3️⃣ Complex Relationship Analysis...")
    try:
        # Find collaboration patterns (Qwen should extract these well)
        collaboration_query = '''
        MATCH (p1:Person)-[r]->(proj:Project)<-[r2]-(p2:Person)
        WHERE p1 <> p2
        RETURN p1.name as person1, p2.name as person2, proj.name as project,
               type(r) as relationship1, type(r2) as relationship2
        LIMIT 5
        '''
        
        collaborations = await graphiti.driver.execute_query(collaboration_query)
        
        if collaborations:
            print('   ✅ Found collaboration patterns:')
            for collab in collaborations:
                print(f'   - {collab["person1"]} & {collab["person2"]} → {collab["project"]}')
                print(f'     Relations: {collab["relationship1"]}, {collab["relationship2"]}')
        else:
            print('   ⚠️ No collaboration patterns found')

    except Exception as e:
        print(f'   ❌ Collaboration query error: {e}')

    # Test 4: Semantic search with technical depth
    print('\n4️⃣ Deep Semantic Search (Qwen + Embeddings)...')
    semantic_queries = [
        'mathematical optimization algorithms',
        'research team leadership structure',
        'performance benchmarks evaluation metrics',
        'funding and investment partnerships'
    ]
    
    for query in semantic_queries:
        try:
            print(f'\n   🔍 Semantic search: "{query}"')
            results = await graphiti.search(query=query, limit=2)
            
            if results:
                print(f'   ✅ {len(results)} semantically related results')
                for i, result in enumerate(results, 1):
                    if hasattr(result, 'node') and hasattr(result, 'score'):
                        node = result.node
                        print(f'     {i}. {node.name} (score: {result.score:.3f})')
            else:
                print(f'   ⚠️ No semantic results for: {query}')
                
        except Exception as e:
            print(f'   ❌ Semantic search error: {e}')

    # Test 5: Entity type analysis (Qwen creates rich entity types)
    print('\n5️⃣ Entity Type Analysis...')
    try:
        # Get entities by sophisticated types (Qwen typically creates these)
        entity_types = ['Person', 'Organization', 'Technology', 'Methodology', 'Metric']
        
        for entity_type in entity_types:
            entities = await graphiti.driver.execute_query(f'''
                MATCH (n:{entity_type})
                RETURN n.name as name, n.summary as summary
                LIMIT 3
            ''')
            
            if entities:
                print(f'\n   📊 {entity_type} entities:')
                for entity in entities:
                    print(f'     • {entity["name"]}')
                    if entity.get('summary'):
                        summary = entity["summary"][:60] + '...' if len(entity["summary"]) > 60 else entity["summary"]
                        print(f'       {summary}')
            else:
                print(f'\n   ⚠️ No {entity_type} entities found')

    except Exception as e:
        print(f'❌ Entity analysis error: {e}')

    # Test 6: Edge search for complex facts (Qwen generates detailed facts)
    print('\n6️⃣ Complex Fact Retrieval...')
    fact_queries = [
        'published research collaboration',
        'performance improvement benchmark',
        'funding partnership agreement',
        'technical innovation development'
    ]
    
    for query in fact_queries:
        try:
            print(f'\n   🔗 Fact search: "{query}"')
            edge_results = await graphiti.search_edges(query=query, limit=2)

            if edge_results:
                print(f'   ✅ Found {len(edge_results)} fact edges')
                for i, edge in enumerate(edge_results, 1):
                    if hasattr(edge, 'fact'):
                        fact_text = edge.fact[:100] + '...' if len(edge.fact) > 100 else edge.fact
                        print(f'     {i}. "{fact_text}"')
                        if hasattr(edge, 'rank'):
                            print(f'        Relevance: {edge.rank:.3f}')
            else:
                print(f'   ⚠️ No facts found for: {query}')

        except Exception as e:
            print(f'   ❌ Fact search error: {e}')


async def main():
    """Run the Cerebras/Qwen retrieval test."""

    print('🧠 Cerebras/Qwen Data Retrieval Test')
    print('=' * 70)

    try:
        # Set up Graphiti with Cerebras/Qwen
        graphiti = await setup_graphiti()
        print('✅ Graphiti initialized with Cerebras/Qwen + Ollama embeddings')

        # Add Qwen-optimized test data
        added_episodes = await add_test_data(graphiti)

        # Wait for indexing (longer for complex Qwen extractions)
        print('\n⏳ Waiting for Qwen extraction indexing...')
        await asyncio.sleep(5)

        # Test retrieval with Qwen-optimized queries
        await test_qwen_optimized_retrieval(graphiti)

        # Clean up
        await graphiti.close()
        print('\n🎉 Cerebras/Qwen retrieval test completed successfully!')

    except Exception as e:
        print(f'\n❌ Test failed: {e}')
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())