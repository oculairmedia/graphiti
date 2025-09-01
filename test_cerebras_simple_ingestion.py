#!/usr/bin/env python3
"""
Test Cerebras integration for simple ingestion without batching.
Based on the Ollama test but adapted for Cerebras to test summary generation quality.
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
from graphiti_core.embedder import EmbedderClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.cerebras_client import CerebrasClient
from graphiti_core.nodes import EpisodeType


# Timer context manager for performance tracking
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
logging.getLogger('neo4j').setLevel(logging.INFO)
logging.getLogger('httpcore').setLevel(logging.INFO)
logging.getLogger('httpx').setLevel(logging.INFO)
logging.getLogger('graphiti_core.search.search').setLevel(logging.INFO)
# Set cerebras client to DEBUG for detailed output
logging.getLogger('graphiti_core.llm_client.cerebras_client').setLevel(logging.DEBUG)


class OllamaEmbedder(EmbedderClient):
    """Custom embedder that uses Ollama for embeddings (keep as fallback for embeddings)."""

    def __init__(self, base_url: str, model: str = 'dengcao/Qwen3-Embedding-4B:Q4_K_M'):
        self.base_url = base_url
        self.model = model
        # Import here to avoid issues if not installed
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key='ollama',  # Ollama doesn't need a real API key
        )
        print(f'✓ Initialized OllamaEmbedder with model: {model}')

    async def create(self, input_data: list[str]) -> list[list[float]]:
        """Create embeddings using Ollama."""
        try:
            # Ollama's OpenAI-compatible endpoint for embeddings
            response = await self.client.embeddings.create(model=self.model, input=input_data)

            # Extract embeddings from response
            embeddings = [item.embedding for item in response.data]
            return embeddings

        except Exception as e:
            print(f'❌ Error creating embeddings: {e}')
            raise


# Test episodes for different complexity levels
test_episodes = [
    {
        'name': 'Simple Technical Content',
        'content': """A Visual Guide to Quantization Demystifying the Compression of Large Language Models. 
        Maarten Grootendorst Jul 22, 2024. As their name suggests, Large Language Models (LLMs) are often too large 
        to run on consumer hardware. These models may exceed billions of parameters and generally need GPUs with large 
        amounts of VRAM to speed up inference. As such, more and more research has been focused on making these models 
        smaller through improved training, adapters, etc. One major technique in this field is called quantization.""",
        'metadata': {
            'source': 'technical_article',
            'timestamp': '2025-01-23T10:00:00Z',
        },
    },
    {
        'name': 'Business Meeting Content',
        'content': """Team meeting with Sarah (project manager) and John (lead developer) on January 15th. 
        Discussed the new user authentication system implementation. Sarah mentioned the deadline is February 1st 
        and we need to prioritize security features. John raised concerns about the database schema changes 
        requiring significant testing time. They agreed to schedule additional code review sessions and 
        bring in Alice from the QA team for early testing feedback.""",
        'metadata': {
            'source': 'meeting_notes',
            'timestamp': '2025-01-15T14:30:00Z',
        },
    },
]


async def test_single_llm_request(client, prompt: str, description: str):
    """Test a single LLM request for summary generation."""
    print(f'\n🧠 Testing {description}')
    print(f'Prompt: {prompt[:100]}...' if len(prompt) > 100 else f'Prompt: {prompt}')
    
    messages = [{'role': 'user', 'content': prompt}]
    
    try:
        with timer(f'{description} request'):
            response = await client._generate_response(messages)
            
        print(f'✅ Response received:')
        # Handle both dict and object responses
        if isinstance(response, dict):
            response_str = str(response)
        elif hasattr(response, 'content'):
            response_str = str(response.content)
        else:
            response_str = str(response)
            
        if len(response_str) > 300:
            print(f'   {response_str[:300]}...')
        else:
            print(f'   {response_str}')
            
        return response
        
    except Exception as e:
        print(f'❌ Error in {description}: {e}')
        return None


async def test_cerebras_ingestion():
    print('\n🧠 Testing Cerebras Integration for Simple Ingestion')
    print('=' * 80)

    # Cerebras LLM Configuration - Conservative settings for testing
    cerebras_api_key = os.getenv('CEREBRAS_API_KEY')
    if not cerebras_api_key:
        print('❌ CEREBRAS_API_KEY environment variable not set')
        return

    llm_config = LLMConfig(
        api_key=cerebras_api_key,
        model='qwen-3-coder-480b',  # Use the main Qwen Coder model
        small_model='qwen-3-coder-480b',  # Keep consistent
        temperature=0.3,  # Lower temperature for more focused responses
        max_tokens=2000,  # Reasonable limit for testing
    )
    cerebras_llm_client = CerebrasClient(config=llm_config)
    print('✅ Cerebras LLM client initialized')

    # Ollama Embedder (keep using reliable embedding service)
    ollama_embedder = OllamaEmbedder(
        base_url='http://100.81.139.20:11434/v1',
        model='dengcao/Qwen3-Embedding-4B:Q4_K_M',
    )

    # Test individual LLM requests first (without ingestion)
    print('\n📝 Testing Individual LLM Requests')
    print('-' * 50)
    
    test_prompts = [
        ("Summarize this in one sentence: Quantization is a technique to compress LLMs.", "Simple summarization"),
        ("Extract key entities from: Sarah met John to discuss the project deadline.", "Entity extraction"),
        ("Create a brief summary: Machine learning models require significant computational resources.", "Technical summary"),
    ]
    
    for prompt, description in test_prompts:
        await test_single_llm_request(cerebras_llm_client, prompt, description)
        # Add delay between requests to respect rate limits
        await asyncio.sleep(2)

    # FalkorDB connection - READ ONLY as requested
    print('\n📊 Connecting to FalkorDB (READ-ONLY)...')
    graphiti = Graphiti(
        uri='falkordb://localhost:6379/graphiti_migration',
        user='',
        password='',
        embedder=ollama_embedder,
        llm_client=cerebras_llm_client,
    )

    try:
        # Test a simple search to verify read access
        print('🔍 Testing read access with simple search...')
        search_result = await graphiti.search(query='quantization', limit=3)
        
        if search_result:
            print(f'✅ Read access confirmed - found {len(search_result)} results')
            for i, result in enumerate(search_result[:2], 1):
                print(f'  Result {i}: {str(result)[:100]}...')
        else:
            print('ℹ️ No search results found (database might be empty)')

        # Test summary generation capabilities by simulating ingestion prompts
        print('\n🎯 Testing Cerebras Summary Generation Capabilities')
        print('-' * 60)
        
        for episode in test_episodes:
            print(f'\n📖 Testing with: {episode["name"]}')
            
            # Simulate the type of summarization prompt used during ingestion
            summary_prompt = f"""Please create a brief, informative summary of the following content. Focus on the key points and main ideas:

{episode['content']}

Provide a concise summary that captures the essential information."""

            summary_result = await test_single_llm_request(
                cerebras_llm_client, 
                summary_prompt, 
                f"Summary generation for {episode['name']}"
            )
            
            # Test entity extraction prompt
            entity_prompt = f"""Extract the main entities (people, organizations, concepts, technologies) from this text:

{episode['content']}

List the key entities you identified."""

            entity_result = await test_single_llm_request(
                cerebras_llm_client,
                entity_prompt,
                f"Entity extraction for {episode['name']}"
            )
            
            # Add delay between episodes
            await asyncio.sleep(3)

    finally:
        # Close the connection
        await graphiti.close()
        print('\n✨ Test complete!')


async def main():
    """Main test function."""
    print('🚀 Starting Cerebras Simple Ingestion Test')
    print('Focus: Testing summary generation and entity extraction without batching')
    print('Database: READ-ONLY mode for testing')
    
    try:
        await test_cerebras_ingestion()
    except KeyboardInterrupt:
        print('\n\n⚠️ Test interrupted by user')
    except Exception as e:
        print(f'\n❌ Test failed with error: {e}')
        import traceback
        print(f'Full traceback: {traceback.format_exc()}')


if __name__ == '__main__':
    asyncio.run(main())