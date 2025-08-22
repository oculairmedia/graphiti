#!/usr/bin/env python3
"""
Debug the exact query causing the FalkorDB error.
"""

import asyncio
import os
from datetime import datetime

# Disable parallel runtime
os.environ['USE_PARALLEL_RUNTIME'] = 'False'

from openai import AsyncOpenAI

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder import EmbedderClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.nodes import EpisodeType

# Monkey patch FalkorDriver to intercept ALL queries
original_execute_query = FalkorDriver.execute_query
query_count = 0


async def debug_execute_query(self, cypher_query_, **kwargs):
    global query_count
    query_count += 1
    print(f'\n🔍 QUERY #{query_count}:')
    print(f'Type: {type(cypher_query_)}')
    print(f'Query: {repr(cypher_query_)[:500]}')
    print(f'Kwargs: {list(kwargs.keys())}')

    # Check if the query is exactly "CYPHER params"
    if cypher_query_ == 'CYPHER params':
        print("❌ FOUND THE PROBLEM! Query is literally 'CYPHER params'")
        import traceback

        traceback.print_stack()
        raise Exception('Found the problematic query!')

    return await original_execute_query(self, cypher_query_, **kwargs)


FalkorDriver.execute_query = debug_execute_query


class OllamaEmbedder(EmbedderClient):
    """Custom embedder that uses Ollama for embeddings."""

    def __init__(self, base_url: str, model: str = 'mxbai-embed-large'):
        self.base_url = base_url
        self.model = model
        self.client = AsyncOpenAI(base_url=base_url, api_key='ollama')

    async def create(self, input_data: list[str]) -> list[list[float]]:
        """Create embeddings using Ollama."""
        response = await self.client.embeddings.create(model=self.model, input=input_data)
        return [item.embedding for item in response.data]


async def test_debug():
    print('🚀 Debugging FalkorDB Query Issue')
    print('=' * 60)

    falkor_driver = FalkorDriver(host='localhost', port=6389, database='debug_queries')

    llm_config = LLMConfig(
        base_url='http://100.81.139.20:11434/v1',
        model='qwen3:30b',
        api_key='ollama',
        temperature=0.1,
        max_tokens=1000,
    )

    llm_client = AsyncOpenAI(base_url='http://100.81.139.20:11434/v1', api_key='ollama')

    ollama_llm_client = OpenAIGenericClient(config=llm_config, client=llm_client)
    ollama_embedder = OllamaEmbedder(base_url='http://100.81.139.20:11434/v1')

    graphiti = Graphiti(
        graph_driver=falkor_driver, embedder=ollama_embedder, llm_client=ollama_llm_client
    )

    try:
        print('\n🔨 Building indices...')
        await graphiti.build_indices_and_constraints()

        print('\n📝 Adding simple episode...')
        await graphiti.add_episode(
            name='Test Episode',
            episode_body='Albert Einstein was a physicist.',
            source_description='Debug Test',
            reference_time=datetime.now(),
            source=EpisodeType.text,
        )

    except Exception as e:
        print(f'\n❌ Error: {e}')
        import traceback

        traceback.print_exc()

    finally:
        await graphiti.close()
        await falkor_driver.close()
        print(f'\nTotal queries executed: {query_count}')


if __name__ == '__main__':
    asyncio.run(test_debug())
