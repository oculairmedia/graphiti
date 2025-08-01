#!/usr/bin/env python3
"""
Test with Qwen3 and add query logging to debug the FalkorDB issue.
"""

import asyncio
import logging
from datetime import datetime

from openai import AsyncOpenAI

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder import EmbedderClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.nodes import EpisodeType

# Enable ALL debug logging
logging.basicConfig(
    level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Patch the FalkorDB driver to log queries
original_execute_query = FalkorDriver.execute_query


async def logged_execute_query(self, cypher_query, **kwargs):
    """Wrapper to log queries before execution."""
    print(f'\n🔍 QUERY DEBUG:')
    print(f'Query: {cypher_query[:200]}...')
    print(f'Params: {kwargs}')
    try:
        return await original_execute_query(self, cypher_query, **kwargs)
    except Exception as e:
        print(f'❌ Query failed: {e}')
        raise


# Monkey patch the method
FalkorDriver.execute_query = logged_execute_query


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


async def test_with_logging():
    print('\n🚀 Testing with Query Logging Enabled')
    print('=' * 60)

    # Create driver and client
    falkor_driver = FalkorDriver(host='localhost', port=6389, database='debug_test')

    # LLM Configuration
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

    # Create Graphiti
    graphiti = Graphiti(
        graph_driver=falkor_driver, embedder=ollama_embedder, llm_client=ollama_llm_client
    )

    try:
        # Build indices
        print('\n🔨 Building indices...')
        await graphiti.build_indices_and_constraints()

        # Try to add a simple episode
        print('\n📝 Adding test episode...')
        await graphiti.add_episode(
            name='Test Episode',
            episode_body='This is a simple test.',
            source_description='Debug Test',
            reference_time=datetime.now(),
            source=EpisodeType.text,
        )

        print('\n✅ Test completed!')

    except Exception as e:
        print(f'\n❌ Test failed: {e}')
        import traceback

        traceback.print_exc()

    finally:
        await graphiti.close()
        await falkor_driver.close()


if __name__ == '__main__':
    asyncio.run(test_with_logging())
