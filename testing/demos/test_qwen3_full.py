#!/usr/bin/env python3
"""
Test Graphiti with Qwen3:32b model - a larger model that should handle complex structured outputs.
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


async def test_qwen3():
    print('\n🚀 Testing Graphiti with Qwen3:32b Model')
    print('=' * 60)

    # First, verify Qwen3 is available
    print('\n1️⃣ Checking Qwen3:32b availability...')
    from openai import AsyncOpenAI

    test_client = AsyncOpenAI(base_url='http://100.81.139.20:11434/v1', api_key='ollama')

    try:
        response = await test_client.chat.completions.create(
            model='qwen3:30b',
            messages=[
                {
                    'role': 'user',
                    'content': "Extract entities from: 'Albert Einstein developed the theory of relativity in 1905.' Return JSON with entities array.",
                }
            ],
            temperature=0.1,
            max_tokens=200,
        )
        print(f'✅ Qwen3 response: {response.choices[0].message.content[:200]}...')
    except Exception as e:
        print(f'❌ Qwen3:32b not available: {e}')
        return

    # Create FalkorDB driver
    falkor_driver = FalkorDriver(
        host='localhost',
        port=6389,
        database='qwen3_test',  # New database for clean test
    )

    # LLM Configuration for Qwen3
    llm_config = LLMConfig(
        base_url='http://100.81.139.20:11434/v1',
        model='qwen3:30b',  # Use Qwen3:32b
        api_key='ollama',
        temperature=0.1,  # Low temperature for consistency
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
    print('\n2️⃣ Initializing Graphiti with Qwen3:32b...')
    graphiti = Graphiti(
        graph_driver=falkor_driver, embedder=ollama_embedder, llm_client=ollama_llm_client
    )

    try:
        # Build indices
        print('🔨 Building indices and constraints...')
        await graphiti.build_indices_and_constraints()

        # Test episodes with rich entity content
        test_episodes = [
            {
                'name': "Einstein's Breakthrough",
                'content': 'Albert Einstein published his theory of special relativity in 1905 while working at the Swiss Patent Office in Bern. This revolutionary work changed our understanding of space and time.',
                'complexity': 'rich_entities',
            },
            {
                'name': 'Tech Giants Collaboration',
                'content': 'Microsoft CEO Satya Nadella announced a partnership with OpenAI in 2019. The collaboration led to the development of GPT-3 and later ChatGPT. Sam Altman leads OpenAI as CEO.',
                'complexity': 'multiple_entities',
            },
            {
                'name': 'AI Research Network',
                'content': 'Geoffrey Hinton, known as the godfather of AI, worked with Yann LeCun and Yoshua Bengio on deep learning. They received the Turing Award in 2018. Their students founded companies like DeepMind and Element AI.',
                'complexity': 'complex_relationships',
            },
        ]

        successful_episodes = []

        print('\n3️⃣ Testing entity extraction with Qwen3:32b...')
        for episode in test_episodes:
            print(f'\n📝 Adding {episode["complexity"]} episode: {episode["name"]}')

            with timer(f"Episode '{episode['name']}' processing"):
                try:
                    result = await asyncio.wait_for(
                        graphiti.add_episode(
                            name=episode['name'],
                            episode_body=episode['content'],
                            source_description='Qwen3 Test',
                            reference_time=datetime.now(),
                            source=EpisodeType.text,
                        ),
                        timeout=180.0,  # 3 minute timeout for larger model
                    )

                    print(f'✅ Successfully processed!')
                    successful_episodes.append(episode['name'])

                    if result:
                        if hasattr(result, 'nodes') and result.nodes:
                            print(f'   🔹 Extracted {len(result.nodes)} entities:')
                            for node in result.nodes[:10]:  # Show up to 10
                                print(
                                    f'      • {node.name} ({", ".join(node.labels) if hasattr(node, "labels") else "Entity"})'
                                )

                        if hasattr(result, 'edges') and result.edges:
                            print(f'   🔗 Created {len(result.edges)} relationships:')
                            for edge in result.edges[:5]:  # Show first 5
                                print(f'      • {edge.fact}')

                except asyncio.TimeoutError:
                    print(f'⏱️ Timeout - episode too complex even for Qwen3:32b')
                except Exception as e:
                    print(f'❌ Error: {str(e)[:200]}')

        # Test retrieval if we added data
        if successful_episodes:
            print(f'\n4️⃣ Testing data retrieval ({len(successful_episodes)} episodes processed)...')

            # Wait for indexing
            await asyncio.sleep(2)

            # Direct database inspection
            print('\n🔍 Database inspection...')

            # Count all nodes
            node_result = await falkor_driver.execute_query('MATCH (n) RETURN count(n) as count')
            if node_result:
                count = (
                    node_result[0]['count']
                    if isinstance(node_result[0], dict)
                    else node_result[0][0]
                )
                print(f'✅ Total nodes: {count}')

            # Count Entity nodes specifically
            entity_result = await falkor_driver.execute_query(
                'MATCH (n:Entity) RETURN count(n) as count'
            )
            if entity_result:
                count = (
                    entity_result[0]['count']
                    if isinstance(entity_result[0], dict)
                    else entity_result[0][0]
                )
                print(f'✅ Entity nodes: {count}')

            # Count relationships
            rel_result = await falkor_driver.execute_query(
                'MATCH ()-[r]->() RETURN count(r) as count'
            )
            if rel_result:
                count = (
                    rel_result[0]['count'] if isinstance(rel_result[0], dict) else rel_result[0][0]
                )
                print(f'✅ Relationships: {count}')

            # Get sample entities
            print('\n📋 Sample entities extracted:')
            entities = await falkor_driver.execute_query(
                'MATCH (n:Entity) RETURN n.name as name, labels(n) as types LIMIT 10'
            )
            if entities and len(entities) > 0:
                for row in entities[:10]:
                    if isinstance(row, dict):
                        print(f'   • {row.get("name", "Unknown")}: {row.get("types", [])}')

            # Get sample relationships
            print('\n📋 Sample relationships:')
            rels = await falkor_driver.execute_query(
                'MATCH (a:Entity)-[r]->(b:Entity) RETURN a.name as source, type(r) as rel_type, b.name as target, r.fact as fact LIMIT 10'
            )
            if rels and len(rels) > 0:
                for row in rels[:10]:
                    if isinstance(row, dict):
                        print(
                            f'   • {row.get("source", "?")} --[{row.get("rel_type", "?")}]--> {row.get("target", "?")}'
                        )
                        if row.get('fact'):
                            print(f'     Fact: {row["fact"]}')

            # Search for specific entities
            print("\n🔍 Searching for 'Einstein'...")
            einstein = await falkor_driver.execute_query(
                "MATCH (n:Entity) WHERE n.name CONTAINS 'Einstein' RETURN n.name, n.summary"
            )
            if einstein and len(einstein) > 0:
                print(f'✅ Found Einstein!')
                for row in einstein:
                    if isinstance(row, dict):
                        print(f'   Name: {row.get("name", "Unknown")}')
                        if row.get('summary'):
                            print(f'   Summary: {row["summary"][:200]}...')

        print('\n✨ Qwen3:32b test complete!')

        # Summary
        print('\n📊 Final Summary:')
        print(f'- Episodes processed: {len(successful_episodes)}/{len(test_episodes)}')
        print('- Check the counts above to see if entities and relationships were extracted')
        print('- Qwen3:32b should perform much better than smaller models')

    except Exception as e:
        print(f'\n❌ Test failed: {e}')
        import traceback

        traceback.print_exc()

    finally:
        await graphiti.close()
        await falkor_driver.close()


if __name__ == '__main__':
    print('🧪 Qwen3:32b Model Test for Graphiti')
    print('This 32B parameter model should handle complex entity extraction much better')
    asyncio.run(test_qwen3())
