#!/usr/bin/env python3
"""
Test script to generate embeddings for just 5 episodic nodes
"""

import asyncio
import os
import sys
from openai import AsyncOpenAI
import logging

# Set up the path
sys.path.insert(0, '/opt/stacks/graphiti')

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder.client import EmbedderClient

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OllamaEmbedder(EmbedderClient):
    """Custom embedder that uses Ollama for embeddings."""

    def __init__(self, base_url: str, model: str = 'dengcao/Qwen3-Embedding-4B:Q4_K_M'):
        self.base_url = base_url
        self.model = model
        self.client = AsyncOpenAI(base_url=base_url, api_key='ollama')
        logger.info(f'✓ Initialized OllamaEmbedder with model: {model} at {base_url}')

    async def create(self, input_data: str | list[str]) -> list[float]:
        """Create embeddings using Ollama for single input."""
        try:
            if isinstance(input_data, str):
                input_data = [input_data]

            response = await self.client.embeddings.create(model=self.model, input=input_data)
            return response.data[0].embedding
        except Exception as e:
            logger.error(f'❌ Error creating embedding: {e}')
            raise

async def test_episodic_embeddings():
    # Initialize FalkorDB driver
    driver = FalkorDriver(
        host="localhost",
        port=6379,
        database="graphiti_migration"
    )

    # Initialize Ollama embedder
    embedder = OllamaEmbedder(
        model="dengcao/Qwen3-Embedding-4B:Q4_K_M",
        base_url="http://192.168.50.80:11434/v1"
    )

    print("✓ Initialized FalkorDB driver and Ollama embedder")

    # Get 5 episodic nodes without embeddings
    query = """
    MATCH (n:Episodic)
    WHERE n.name_embedding IS NULL
    RETURN
        n.uuid as uuid,
        n.name as name,
        n.content as content
    LIMIT 5
    """

    records, _, _ = await driver.execute_query(query)
    print(f"Found {len(records)} episodic nodes without embeddings")

    if not records:
        print("No episodic nodes need embeddings!")
        return

    # Generate embeddings for each node
    for i, record in enumerate(records, 1):
        # FalkorDB returns records as dictionaries with aliases
        uuid = record.get('uuid')
        name = record.get('name')
        content = record.get('content')

        name_preview = str(name)[:50] if name else "Unknown"
        print(f"\nProcessing node {i}/5: {name_preview}...")
        print(f"  UUID: {uuid}")
        print(f"  Content length: {len(str(content)) if content else 0}")

        if not content:
            print(f"  ⚠️ No content for node {uuid}, skipping")
            continue

        # Generate embedding for the content
        try:
            # Convert content to string and create embedding
            content_str = str(content)
            embedding = await embedder.create(input_data=[content_str])

            # Update the node with its embedding
            update_query = """
            MATCH (n:Episodic {uuid: $uuid})
            SET n.name_embedding = vecf32($embedding)
            RETURN n.uuid
            """

            result, _, _ = await driver.execute_query(
                update_query,
                **{
                    'uuid': uuid,
                    'embedding': embedding
                }
            )

            if result:
                print(f"  ✓ Updated embedding for node {uuid}")
            else:
                print(f"  ❌ Failed to update node {uuid}")

        except Exception as e:
            print(f"  ❌ Error generating embedding for node {uuid}: {e}")

    # Verify results
    verify_query = """
    MATCH (n:Episodic)
    WHERE n.name_embedding IS NOT NULL
    RETURN count(n) as with_embeddings
    """

    result, _, _ = await driver.execute_query(verify_query)
    count = result[0]['with_embeddings'] if result else 0

    print(f"\nResult: {count} episodic nodes now have embeddings")

    await driver.close()

if __name__ == "__main__":
    asyncio.run(test_episodic_embeddings())