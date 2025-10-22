#!/usr/bin/env python3
"""
Test Graphiti with Devstral model - should handle structured outputs better than Mistral.
"""

import asyncio
import hashlib
import logging
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder import EmbedderClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.nodes import EpisodeType


# Timer context manager
@contextmanager
def timer(name):
    start = time.time()
    yield
    elapsed = time.time() - start
    print(f'{name} took {elapsed:.2f} seconds')


# Configure logging
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logging.getLogger('graphiti_core.search.search').setLevel(logging.INFO)
logging.getLogger('httpcore').setLevel(logging.INFO)
logging.getLogger('httpx').setLevel(logging.INFO)


class OllamaEmbedder(EmbedderClient):
    """Custom embedder that uses Ollama for embeddings."""

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


async def test_devstral():
    print('\n🚀 Testing Graphiti with Devstral Model')
    print('=' * 60)

    # First, verify Devstral is available
    print('\n1️⃣ Checking Devstral availability...')
    from openai import AsyncOpenAI

    test_client = AsyncOpenAI(base_url='http://100.81.139.20:11434/v1', api_key='ollama')

    try:
        response = await test_client.chat.completions.create(
            model='devstral:latest',
            messages=[
                {'role': 'user', 'content': "Say 'Hello, I am Devstral!' in exactly 5 words."}
            ],
            temperature=0.1,
            max_tokens=50,
        )
        print(f'✅ Devstral response: {response.choices[0].message.content}')
    except Exception as e:
        print(f'❌ Devstral not available: {e}')
        return

    # Create FalkorDB driver
    falkor_driver = FalkorDriver(
        host='localhost',
        port=6389,
        database='devstral_test',  # Use a new database for clean test
    )

    # LLM Configuration for Devstral
    llm_config = LLMConfig(
        base_url='http://100.81.139.20:11434/v1',
        model='devstral:latest',  # Use Devstral instead of Mistral
        api_key='ollama',
        temperature=0.1,  # Lower temperature for more consistent outputs
        max_tokens=2000,
    )

    # Create Ollama client for LLM
    llm_client = AsyncOpenAI(base_url='http://100.81.139.20:11434/v1', api_key='ollama')

    ollama_llm_client = OpenAIGenericClient(config=llm_config, client=llm_client)

    # Embedder Configuration
    ollama_embedder = OllamaEmbedder(
        base_url='http://100.81.139.20:11434/v1', model='mxbai-embed-large'
    )

    # Create Graphiti instance
    print('\n2️⃣ Initializing Graphiti with Devstral...')
    graphiti = Graphiti(
        graph_driver=falkor_driver, embedder=ollama_embedder, llm_client=ollama_llm_client
    )

    try:
        # Build indices
        print('🔨 Building indices and constraints...')
        await graphiti.build_indices_and_constraints()

        # Test episodes with increasing complexity
        test_episodes = [
            {
                'name': 'Simple AI Fact',
                'content': 'Artificial Intelligence was coined by John McCarthy in 1956.',
                'complexity': 'simple',
            },
            {
                'name': 'AI and ML Relationship',
                'content': 'Machine Learning is a subset of Artificial Intelligence. Deep Learning is a subset of Machine Learning that uses neural networks.',
                'complexity': 'medium',
            },
            {
                'name': 'Quantization Details',
                'content': 'Quantization in machine learning reduces model precision from 32-bit to 8-bit or 4-bit. This technique was popularized by researchers at Google and Facebook. It enables deployment on edge devices.',
                'complexity': 'complex',
            },
        ]

        successful_episodes = []

        print('\n3️⃣ Testing data ingestion with Devstral...')
        for episode in test_episodes:
            print(f'\n📝 Adding {episode["complexity"]} episode: {episode["name"]}')

            with timer(f"Episode '{episode['name']}' ingestion"):
                try:
                    result = await asyncio.wait_for(
                        graphiti.add_episode(
                            name=episode['name'],
                            episode_body=episode['content'],
                            source_description='Devstral Test',
                            reference_time=datetime.now(),
                            source=EpisodeType.text,
                        ),
                        timeout=120.0,  # 2 minute timeout
                    )

                    print(f'✅ Successfully added!')
                    successful_episodes.append(episode['name'])

                    if result:
                        if hasattr(result, 'nodes') and result.nodes:
                            print(f'   - Extracted {len(result.nodes)} entities:')
                            for node in result.nodes[:5]:
                                print(f'     • {node.name}')

                        if hasattr(result, 'edges') and result.edges:
                            print(f'   - Created {len(result.edges)} relationships')

                except asyncio.TimeoutError:
                    print(f'⏱️ Timeout - episode too complex for Devstral')
                except Exception as e:
                    print(f'❌ Error: {str(e)[:200]}')

        # If we successfully added data, test retrieval
        if successful_episodes:
            print(f'\n4️⃣ Testing data retrieval ({len(successful_episodes)} episodes added)...')

            # Wait for indexing
            await asyncio.sleep(2)

            # Test search
            print("\n🔍 Searching for 'Artificial Intelligence'...")
            try:
                search_results = await graphiti.search(
                    query='Artificial Intelligence', num_results=5
                )

                if search_results:
                    print(f'✅ Found {len(search_results)} results:')
                    for i, result in enumerate(search_results[:3], 1):
                        print(f'\n   Result {i}:')
                        if hasattr(result, 'node'):
                            node = result.node
                            if hasattr(node, 'name'):
                                print(f'   - Name: {node.name}')
                            if hasattr(node, 'summary'):
                                print(f'   - Summary: {node.summary[:100]}...')
                        if hasattr(result, 'score'):
                            print(f'   - Score: {result.score:.3f}')
                else:
                    print('❌ No search results found')

            except Exception as e:
                print(f'❌ Search error: {e}')

            # Direct database queries
            print('\n🔍 Direct database inspection...')
            try:
                # Count nodes
                node_result = await falkor_driver.execute_query(
                    'MATCH (n) RETURN count(n) as count'
                )
                if node_result:
                    count = (
                        node_result[0]['count']
                        if isinstance(node_result[0], dict)
                        else node_result[0][0]
                    )
                    print(f'✅ Total nodes in graph: {count}')

                # Get entity types
                type_result = await falkor_driver.execute_query(
                    'MATCH (n:Entity) RETURN n.name as name, labels(n) as types LIMIT 10'
                )
                if type_result and len(type_result) > 0:
                    print(f'\n✅ Sample entities:')
                    for row in type_result[:5]:
                        if isinstance(row, dict):
                            print(f'   - {row.get("name", "Unknown")}: {row.get("types", [])}')
                        elif isinstance(row, list) and len(row) >= 2:
                            print(f'   - {row[0]}: {row[1]}')

            except Exception as e:
                print(f'❌ Database query error: {e}')

        else:
            print('\n❌ No episodes were successfully added - cannot test retrieval')

        print('\n✨ Test complete!')

    except Exception as e:
        print(f'\n❌ Test failed: {e}')
        import traceback

        traceback.print_exc()

    finally:
        await graphiti.close()
        await falkor_driver.close()


if __name__ == '__main__':
    print('🧪 Devstral Model Test for Graphiti')
    print('Using a more capable model should improve structured output generation')
    asyncio.run(test_devstral())
