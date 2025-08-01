#!/usr/bin/env python3
"""
Test data retrieval with Ollama integration.
First adds some simple data, then tests various retrieval methods.
"""

import asyncio
from datetime import datetime

from openai import AsyncOpenAI

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder import EmbedderClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.nodes import EpisodeType


class OllamaEmbedder(EmbedderClient):
    """Custom embedder that uses Ollama for embeddings."""

    def __init__(self, base_url: str, model: str = 'mxbai-embed-large'):
        self.base_url = base_url
        self.model = model
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
    """Set up Graphiti with Ollama."""
    # Create FalkorDB driver
    falkor_driver = FalkorDriver(host='localhost', port=6389, database='graphiti_test')

    # LLM Configuration for Ollama
    llm_config = LLMConfig(
        base_url='http://100.81.139.20:11434/v1',
        model='mistral:latest',
        api_key='ollama',
        temperature=0.2,
        max_tokens=1000,
    )

    # Create Ollama client for LLM
    llm_client = AsyncOpenAI(base_url='http://100.81.139.20:11434/v1', api_key='ollama')

    ollama_llm_client = OpenAIGenericClient(config=llm_config, client=llm_client)

    # Embedder Configuration for Ollama
    ollama_embedder = OllamaEmbedder(
        base_url='http://100.81.139.20:11434/v1', model='mxbai-embed-large'
    )

    # Create Graphiti instance
    graphiti = Graphiti(
        graph_driver=falkor_driver, embedder=ollama_embedder, llm_client=ollama_llm_client
    )

    # Build indices
    await graphiti.build_indices_and_constraints()

    return graphiti


async def add_test_data(graphiti):
    """Add some simple test data to the graph."""

    print('\n📝 Adding test data to graph...')

    test_episodes = [
        {
            'name': 'AI Basics',
            'content': 'Artificial Intelligence is the simulation of human intelligence by machines. Machine learning is a subset of AI that enables systems to learn from data.',
            'source': 'AI Tutorial',
        },
        {
            'name': 'Deep Learning',
            'content': 'Deep learning uses neural networks with multiple layers. It has revolutionized computer vision and natural language processing.',
            'source': 'DL Guide',
        },
        {
            'name': 'Quantization Explained',
            'content': "Quantization reduces model precision to make them smaller and faster. It's essential for deploying AI models on edge devices.",
            'source': 'Optimization Guide',
        },
    ]

    added_episodes = []

    for episode in test_episodes:
        try:
            print(f'\n  Adding: {episode["name"]}...')

            # Try with a timeout
            result = await asyncio.wait_for(
                graphiti.add_episode(
                    name=episode['name'],
                    episode_body=episode['content'],
                    source_description=episode['source'],
                    reference_time=datetime.now(),
                    source=EpisodeType.text,
                ),
                timeout=60.0,  # 60 second timeout
            )

            print(f'  ✅ Added successfully!')
            if result:
                added_episodes.append(result)
                if hasattr(result, 'nodes') and result.nodes:
                    print(f'     Extracted {len(result.nodes)} entities')

        except asyncio.TimeoutError:
            print(f'  ⏱️ Timeout adding episode')
        except Exception as e:
            print(f'  ❌ Error: {e}')

    return added_episodes


async def test_retrieval(graphiti):
    """Test various retrieval methods."""

    print('\n🔍 Testing Data Retrieval')
    print('=' * 50)

    # Test 1: Direct database query
    print('\n1️⃣ Direct Database Query - Count all nodes...')
    try:
        node_count = await graphiti.driver.execute_query('MATCH (n) RETURN count(n) as count')
        print(f'✅ Total nodes in graph: {node_count[0]["count"] if node_count else 0}')

        # Get node types
        node_types = await graphiti.driver.execute_query(
            'MATCH (n) RETURN DISTINCT labels(n) as types, count(n) as count ORDER BY count DESC'
        )
        if node_types:
            print('\n   Node types:')
            for nt in node_types:
                print(f'   - {nt["types"]}: {nt["count"]} nodes')
    except Exception as e:
        print(f'❌ Database query error: {e}')

    # Test 2: Search for specific content
    print("\n2️⃣ Search for 'AI machine learning'...")
    try:
        search_results = await graphiti.search(query='AI machine learning', limit=5)

        if search_results:
            print(f'✅ Found {len(search_results)} results:')
            for i, result in enumerate(search_results, 1):
                print(f'\n   Result {i}:')
                if hasattr(result, 'node'):
                    node = result.node
                    print(f'   - Type: {type(node).__name__}')
                    if hasattr(node, 'name'):
                        print(f'   - Name: {node.name}')
                    if hasattr(node, 'content'):
                        print(f'   - Content: {node.content[:100]}...')
                    if hasattr(result, 'score'):
                        print(f'   - Score: {result.score:.3f}')
                else:
                    print(f'   - {result}')
        else:
            print('❌ No search results found')

    except Exception as e:
        print(f'❌ Search error: {e}')

    # Test 3: Search for edges
    print("\n3️⃣ Search for edges about 'learning'...")
    try:
        edge_results = await graphiti.search_edges(query='learning', limit=5)

        if edge_results:
            print(f'✅ Found {len(edge_results)} edges:')
            for i, edge in enumerate(edge_results, 1):
                print(f'\n   Edge {i}:')
                if hasattr(edge, 'fact'):
                    print(f'   - Fact: {edge.fact}')
                if hasattr(edge, 'name'):
                    print(f'   - Name: {edge.name}')
                if hasattr(edge, 'rank'):
                    print(f'   - Score: {edge.rank:.3f}')
        else:
            print('❌ No edges found')

    except Exception as e:
        print(f'❌ Edge search error: {e}')

    # Test 4: Get entities by type
    print('\n4️⃣ Query specific entity types...')
    try:
        # Get all Entity nodes
        entities = await graphiti.driver.execute_query(
            'MATCH (n:Entity) RETURN n.name as name, n.summary as summary LIMIT 10'
        )

        if entities:
            print(f'✅ Found {len(entities)} entities:')
            for entity in entities:
                print(f'   - {entity["name"]}')
                if entity.get('summary'):
                    print(f'     Summary: {entity["summary"][:100]}...')
        else:
            print('❌ No entities found')

    except Exception as e:
        print(f'❌ Entity query error: {e}')

    # Test 5: Get recent episodes
    print('\n5️⃣ Query recent episodes...')
    try:
        episodes = await graphiti.driver.execute_query(
            """
            MATCH (e:EpisodicNode)
            RETURN e.name as name, e.content as content, e.created_at as created_at
            ORDER BY e.created_at DESC
            LIMIT 5
            """
        )

        if episodes:
            print(f'✅ Found {len(episodes)} recent episodes:')
            for ep in episodes:
                print(f'   - {ep["name"]}')
                if ep.get('content'):
                    print(f'     Content: {ep["content"][:100]}...')
        else:
            print('❌ No episodes found')

    except Exception as e:
        print(f'❌ Episode query error: {e}')

    # Test 6: Test semantic search with embeddings
    print('\n6️⃣ Semantic search test...')
    try:
        # Search for conceptually related content
        semantic_results = await graphiti.search(
            query='neural network architecture optimization', limit=3
        )

        if semantic_results:
            print(f'✅ Found {len(semantic_results)} semantically related results')
            for i, result in enumerate(semantic_results, 1):
                print(f'   Result {i}: Score {getattr(result, "score", "N/A")}')
        else:
            print('❌ No semantic search results')

    except Exception as e:
        print(f'❌ Semantic search error: {e}')


async def main():
    """Run the retrieval test."""

    print('🦙 Ollama Data Retrieval Test')
    print('=' * 60)

    try:
        # Set up Graphiti
        graphiti = await setup_graphiti()
        print('✅ Graphiti initialized with Ollama')

        # Add test data
        added_episodes = await add_test_data(graphiti)

        # Wait a bit for indexing
        print('\n⏳ Waiting for indexing...')
        await asyncio.sleep(2)

        # Test retrieval
        await test_retrieval(graphiti)

        # Clean up
        await graphiti.close()
        print('\n✅ Test complete!')

    except Exception as e:
        print(f'\n❌ Test failed: {e}')
        import traceback

        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
