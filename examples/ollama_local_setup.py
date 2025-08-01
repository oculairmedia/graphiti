"""
Example configuration for using Graphiti with Ollama for local LLM inference.

This example shows how to configure Graphiti to use locally hosted models
via Ollama's OpenAI-compatible API endpoint.
"""

import asyncio
import os
from datetime import datetime

from openai import AsyncOpenAI

from graphiti_core import Graphiti
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client import LLMConfig, OpenAIGenericClient

# Ollama Configuration
OLLAMA_BASE_URL = 'http://100.81.139.20:11434/v1'
OLLAMA_MODEL = 'mistral:latest'  # or "mistral:7b-instruct-v0.3-q4_K_M" for specific version
OLLAMA_EMBEDDING_MODEL = 'nomic-embed-text:latest'  # Pull this with: ollama pull nomic-embed-text


class OllamaEmbedder(EmbedderClient):
    """Custom embedder using Ollama's embedding endpoint."""

    def __init__(self, base_url: str, model: str = 'nomic-embed-text:latest'):
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key='ollama',  # Ollama doesn't require a real API key
        )
        self.model = model

    async def create(self, input_data: list[str]) -> list[list[float]]:
        """Create embeddings for the given input data."""
        try:
            response = await self.client.embeddings.create(model=self.model, input=input_data)
            return [embedding.embedding for embedding in response.data]
        except Exception as e:
            print(f'Embedding error: {e}')
            # Fallback to sentence-transformers if Ollama embeddings fail
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer('all-MiniLM-L6-v2')
            embeddings = model.encode(input_data)
            return embeddings.tolist()


async def test_ollama_connection():
    """Test if Ollama is reachable and has the required models."""
    client = AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key='ollama')

    try:
        # Test LLM
        print('Testing Ollama LLM connection...')
        response = await client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[{'role': 'user', 'content': "Say 'Hello, Graphiti!'"}],
            max_tokens=50,
        )
        print(f'✓ LLM Response: {response.choices[0].message.content}')

        # Test structured output
        print('\nTesting structured output...')
        response = await client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[
                {'role': 'system', 'content': 'You are a helpful assistant that outputs JSON.'},
                {
                    'role': 'user',
                    'content': 'Output a JSON object with keys "name" and "type" for the entity "Python programming language"',
                },
            ],
            max_tokens=100,
            response_format={'type': 'json_object'},
        )
        print(f'✓ Structured output: {response.choices[0].message.content}')

        # Test embeddings
        print('\nTesting embeddings...')
        embedder = OllamaEmbedder(OLLAMA_BASE_URL, OLLAMA_EMBEDDING_MODEL)
        embeddings = await embedder.create(['test sentence'])
        print(f'✓ Embedding dimension: {len(embeddings[0])}')

        return True
    except Exception as e:
        print(f'✗ Error: {e}')
        return False


async def create_graphiti_with_ollama(neo4j_uri: str, neo4j_user: str, neo4j_password: str):
    """Create a Graphiti instance configured to use Ollama."""

    # Create Ollama client for LLM
    llm_client = AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key='ollama')

    # Configure LLM
    llm_config = LLMConfig(
        model=OLLAMA_MODEL,
        small_model=OLLAMA_MODEL,  # Use same model for both
        temperature=0.7,
        max_tokens=2000,
    )

    # Create LLM client wrapper
    ollama_llm_client = OpenAIGenericClient(config=llm_config, client=llm_client)

    # Create embedder
    embedder = OllamaEmbedder(OLLAMA_BASE_URL, OLLAMA_EMBEDDING_MODEL)

    # Alternative: Use OpenAI embedder with Ollama
    # embedder_client = AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
    # embedder_config = OpenAIEmbedderConfig(model=OLLAMA_EMBEDDING_MODEL)
    # embedder = OpenAIEmbedder(config=embedder_config, client=embedder_client)

    # Create Graphiti instance
    graphiti = Graphiti(
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
        llm_client=ollama_llm_client,
        embedder=embedder,
    )

    await graphiti.initialize()

    return graphiti


async def main():
    """Example usage of Graphiti with Ollama."""

    # Test Ollama connection first
    print('=== Testing Ollama Connection ===')
    if not await test_ollama_connection():
        print('\nPlease ensure Ollama is running and has the required models:')
        print(f'  ollama pull {OLLAMA_MODEL}')
        print(f'  ollama pull {OLLAMA_EMBEDDING_MODEL}')
        return

    print('\n=== Setting up Graphiti with Ollama ===')

    # Neo4j connection details (update these)
    neo4j_uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    neo4j_user = os.getenv('NEO4J_USER', 'neo4j')
    neo4j_password = os.getenv('NEO4J_PASSWORD', 'password')

    try:
        # Create Graphiti instance
        graphiti = await create_graphiti_with_ollama(neo4j_uri, neo4j_user, neo4j_password)

        print('✓ Graphiti initialized with Ollama')

        # Test with a simple example
        print('\n=== Testing Graphiti Operations ===')

        # Add an episode
        episode_data = {
            'name': 'Test Episode',
            'content': 'Python is a programming language. It was created by Guido van Rossum. Python is used for machine learning and data science.',
            'timestamp': datetime.now().isoformat(),
        }

        print('Adding episode...')
        result = await graphiti.add_episode(
            name=episode_data['name'],
            episode_body=episode_data['content'],
            source_description='test',
            timestamp=episode_data['timestamp'],
        )

        print(f'✓ Episode added successfully')
        print(f'  Extracted entities: {len(result.nodes)}')
        print(f'  Extracted edges: {len(result.edges)}')

        # Search for edges
        print('\nSearching for relationships...')
        search_results = await graphiti.search_edges(query='Python programming', limit=5)

        print(f'✓ Found {len(search_results)} edges')
        for edge in search_results[:3]:
            print(f'  - {edge.fact}')

        await graphiti.close()

    except Exception as e:
        print(f'✗ Error: {e}')
        import traceback

        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
