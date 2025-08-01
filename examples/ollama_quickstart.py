"""
Minimal example to get started with Graphiti using Ollama.

Prerequisites:
1. Ollama running with mistral model: ollama pull mistral
2. Neo4j database running
3. For embeddings: ollama pull nomic-embed-text (or we'll use sentence-transformers)
"""

import asyncio
import os
from datetime import datetime

from openai import AsyncOpenAI

from graphiti_core import Graphiti
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.llm_client import LLMConfig, OpenAIGenericClient

# Configuration
OLLAMA_URL = 'http://100.81.139.20:11434/v1'
OLLAMA_MODEL = 'mistral:latest'


class SimpleLocalEmbedder(EmbedderClient):
    """Simple embedder using sentence-transformers."""

    def __init__(self):
        try:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            print('✓ Using sentence-transformers for embeddings')
        except ImportError:
            print('✗ Please install sentence-transformers: pip install sentence-transformers')
            raise

    async def create(self, input_data: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(input_data)
        return embeddings.tolist()


async def main():
    """Simple example of using Graphiti with Ollama."""

    # Neo4j credentials (update these for your setup)
    neo4j_uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    neo4j_user = os.getenv('NEO4J_USER', 'neo4j')
    neo4j_password = os.getenv('NEO4J_PASSWORD', 'password')

    print(f'Connecting to Ollama at {OLLAMA_URL}')
    print(f'Using model: {OLLAMA_MODEL}')
    print(f'Connecting to Neo4j at {neo4j_uri}')

    # Create Ollama client
    llm_client = AsyncOpenAI(base_url=OLLAMA_URL, api_key='ollama')

    # Configure LLM
    llm_config = LLMConfig(
        model=OLLAMA_MODEL, small_model=OLLAMA_MODEL, temperature=0.7, max_tokens=2000
    )

    # Create Graphiti instance
    graphiti = Graphiti(
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
        llm_client=OpenAIGenericClient(config=llm_config, client=llm_client),
        embedder=SimpleLocalEmbedder(),
    )

    try:
        # Initialize
        print('\nInitializing Graphiti...')
        await graphiti.initialize()
        print('✓ Graphiti initialized')

        # Add a test episode
        print('\nAdding knowledge to the graph...')
        content = """
        Graphiti is a Python library for building knowledge graphs. 
        It uses Neo4j as the graph database and supports temporal queries.
        The library was created by Zep and is designed for AI agent memory.
        """

        result = await graphiti.add_episode(
            name='Graphiti Introduction',
            episode_body=content,
            source_description='Documentation',
            timestamp=datetime.now().isoformat(),
        )

        print(f'✓ Added episode')
        print(f'  - Extracted {len(result.nodes)} entities')
        print(f'  - Created {len(result.edges)} relationships')

        if result.nodes:
            print('\nExtracted entities:')
            for node in result.nodes[:5]:
                print(f'  - {node.name} ({node.type})')

        if result.edges:
            print('\nExtracted relationships:')
            for edge in result.edges[:5]:
                print(f'  - {edge.fact}')

        # Search example
        print('\nSearching the knowledge graph...')
        search_results = await graphiti.search_edges('Graphiti Python', limit=3)

        if search_results:
            print(f'Found {len(search_results)} relevant edges:')
            for edge in search_results:
                print(f'  - {edge.fact}')

    except Exception as e:
        print(f'\n✗ Error: {e}')
        import traceback

        traceback.print_exc()

    finally:
        await graphiti.close()
        print('\n✓ Connection closed')


if __name__ == '__main__':
    # Install required package if missing
    try:
        import sentence_transformers
    except ImportError:
        print('Installing sentence-transformers for local embeddings...')
        import subprocess

        subprocess.check_call(['pip', 'install', 'sentence-transformers'])

    asyncio.run(main())
