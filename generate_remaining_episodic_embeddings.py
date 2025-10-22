#!/usr/bin/env python3
"""
Generate embeddings for remaining episodic nodes
"""

import asyncio
import os
import sys
import time
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

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        """Create embeddings using Ollama for batch input."""
        try:
            response = await self.client.embeddings.create(model=self.model, input=input_data_list)
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f'❌ Error creating batch embeddings: {e}')
            raise

async def generate_remaining_episodic_embeddings():
    """Generate embeddings for all remaining episodic nodes without embeddings."""

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

    print("="*80)
    print("REMAINING EPISODIC NODE EMBEDDING GENERATION")
    print("="*80)

    # Count remaining nodes
    count_query = """
    MATCH (n:Episodic)
    WHERE n.name_embedding IS NULL AND n.content IS NOT NULL
    RETURN count(n) as total
    """

    result, _, _ = await driver.execute_query(count_query)
    total_nodes = result[0]['total'] if result else 0

    print(f"Found {total_nodes} episodic nodes without embeddings")

    if total_nodes == 0:
        print("No nodes need embeddings!")
        await driver.close()
        return

    # Process in batches
    batch_size = 20  # Smaller batches for stability
    processed = 0
    updated = 0
    failed = 0
    start_time = time.time()

    while processed < total_nodes:
        # Get batch of nodes
        batch_query = """
        MATCH (n:Episodic)
        WHERE n.name_embedding IS NULL AND n.content IS NOT NULL
        RETURN
            n.uuid as uuid,
            n.name as name,
            n.content as content
        LIMIT $batch_size
        """

        records, _, _ = await driver.execute_query(batch_query, batch_size=batch_size)

        if not records:
            print("No more nodes to process")
            break

        print(f"\nProcessing batch {processed // batch_size + 1} ({len(records)} nodes)...")

        # Process each node in the batch
        for record in records:
            uuid = record.get('uuid')
            name = record.get('name')
            content = record.get('content')

            if not content:
                print(f"  ⚠️ No content for node {uuid}, skipping")
                processed += 1
                continue

            try:
                # Generate embedding
                content_str = str(content)
                embedding = await embedder.create(input_data=[content_str])

                # Update the node
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
                    updated += 1
                    if updated % 10 == 0:
                        elapsed = time.time() - start_time
                        rate = updated / elapsed
                        eta = (total_nodes - updated) / rate if rate > 0 else 0
                        print(f"  Updated {updated}/{total_nodes} nodes (Rate: {rate:.1f}/sec, ETA: {eta:.0f}s)")
                else:
                    failed += 1
                    print(f"  ❌ Failed to update node {uuid}")

            except Exception as e:
                failed += 1
                print(f"  ❌ Error processing node {uuid}: {e}")

            processed += 1

        # Small delay between batches
        await asyncio.sleep(0.5)

    # Final summary
    elapsed = time.time() - start_time
    print(f"\n" + "="*80)
    print("FINAL RESULTS")
    print("="*80)
    print(f"Total processed: {processed}")
    print(f"Successfully updated: {updated}")
    print(f"Failed: {failed}")
    print(f"Time elapsed: {elapsed:.1f} seconds")
    print(f"Rate: {updated / elapsed:.1f} nodes/sec")

    # Verify final count
    verify_query = """
    MATCH (n:Episodic)
    WHERE n.name_embedding IS NOT NULL
    RETURN count(n) as with_embeddings
    """

    result, _, _ = await driver.execute_query(verify_query)
    final_count = result[0]['with_embeddings'] if result else 0

    print(f"Final count: {final_count} episodic nodes now have embeddings")

    await driver.close()

if __name__ == "__main__":
    asyncio.run(generate_remaining_episodic_embeddings())