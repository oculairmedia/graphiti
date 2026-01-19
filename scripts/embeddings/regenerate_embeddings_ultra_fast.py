#!/usr/bin/env python3
"""
ULTRA FAST embedding regeneration using UNWIND for bulk updates.
This processes nodes in batches and uses a single query per batch.
"""

import asyncio
import os
import time
import logging
from typing import List
from openai import AsyncOpenAI
from graphiti_core.driver.falkordb_driver import FalkorDriver

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FastOllamaEmbedder:
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url
        self.model = model
        self.client = AsyncOpenAI(base_url=base_url, api_key='ollama')
        logger.info(f'✓ Initialized with {model} at {base_url}')

    async def create_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        try:
            response = await self.client.embeddings.create(
                input=texts,
                model=self.model
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise

async def bulk_update_embeddings(driver: FalkorDriver, nodes: List[dict], embeddings: List[List[float]]):
    """Update multiple nodes using individual queries (FalkorDB limitation workaround)."""
    for i, node in enumerate(nodes):
        try:
            # Convert embedding to FalkorDB vecf32 format
            query = """
            MATCH (n:Entity {uuid: $uuid})
            SET n.name_embedding = vecf32($embedding)
            RETURN n.uuid
            """
            await driver.execute_query(query, uuid=node['uuid'], embedding=embeddings[i])
        except Exception as e:
            logger.error(f"Failed to update {node['uuid']}: {e}")
            raise

async def main():
    # Configuration
    OLLAMA_URL = "http://192.168.50.80:11434/v1"
    OLLAMA_MODEL = "dengcao/Qwen3-Embedding-4B:Q4_K_M"
    DB_NAME = "graphiti_migration"
    BATCH_SIZE = 100  # Process more nodes per batch
    MAX_NODES = None  # Set to limit for testing, None for all

    logger.info("=" * 80)
    logger.info("ULTRA-FAST EMBEDDING REGENERATION")
    logger.info("=" * 80)
    logger.info(f"Database: {DB_NAME}")
    logger.info(f"Ollama: {OLLAMA_URL}")
    logger.info(f"Model: {OLLAMA_MODEL}")
    logger.info(f"Batch Size: {BATCH_SIZE}")
    logger.info("=" * 80)

    # Initialize
    driver = FalkorDriver(host='localhost', port=6379, database=DB_NAME)
    embedder = FastOllamaEmbedder(OLLAMA_URL, OLLAMA_MODEL)

    # Count total nodes
    count_query = "MATCH (n:Entity) WHERE n.name IS NOT NULL RETURN count(n) as total"
    result, _, _ = await driver.execute_query(count_query)
    total = result[0]['total'] if result else 0

    if MAX_NODES:
        total = min(total, MAX_NODES)

    logger.info(f"\n📊 Found {total} Entity nodes to process\n")

    if total == 0:
        logger.warning("No nodes found!")
        return

    # Process in batches
    updated = 0
    failed = 0
    start_time = time.time()

    for offset in range(0, total, BATCH_SIZE):
        batch_num = offset // BATCH_SIZE + 1
        limit = min(BATCH_SIZE, total - offset)

        logger.info(f"🔄 Batch {batch_num}: Fetching {limit} nodes (offset {offset})...")

        # Fetch batch
        fetch_query = """
        MATCH (n:Entity)
        WHERE n.name IS NOT NULL AND n.name <> ''
        RETURN n.uuid as uuid, n.name as name
        ORDER BY n.created_at DESC
        SKIP $offset
        LIMIT $limit
        """
        nodes, _, _ = await driver.execute_query(fetch_query, offset=offset, limit=limit)

        if not nodes:
            logger.warning("No more nodes to fetch")
            break

        logger.info(f"  ↳ Retrieved {len(nodes)} nodes")

        # Generate embeddings
        logger.info(f"  ⚡ Generating embeddings...")
        emb_start = time.time()
        names = [n['name'] for n in nodes]
        try:
            embeddings = await embedder.create_batch(names)
            emb_time = time.time() - emb_start
            logger.info(f"  ✓ Generated {len(embeddings)} embeddings in {emb_time:.2f}s ({len(embeddings)/emb_time:.1f} emb/sec)")
        except Exception as e:
            logger.error(f"  ✗ Failed to generate embeddings: {e}")
            failed += len(nodes)
            continue

        # Bulk update
        logger.info(f"  💾 Writing to FalkorDB...")
        update_start = time.time()
        try:
            await bulk_update_embeddings(driver, nodes, embeddings)
            update_time = time.time() - update_start
            logger.info(f"  ✓ Updated {len(nodes)} nodes in {update_time:.2f}s ({len(nodes)/update_time:.1f} nodes/sec)")
            updated += len(nodes)
        except Exception as e:
            logger.error(f"  ✗ Bulk update failed: {e}")
            failed += len(nodes)
            continue

        # Progress report
        elapsed = time.time() - start_time
        rate = updated / elapsed if elapsed > 0 else 0
        remaining = total - updated - failed
        eta = remaining / rate if rate > 0 else 0

        logger.info(f"\n📈 Progress: {updated}/{total} ({updated*100//total}%)")
        logger.info(f"   Updated: {updated}, Failed: {failed}")
        logger.info(f"   Rate: {rate:.1f} nodes/sec")
        logger.info(f"   ETA: {eta/60:.1f} minutes\n")

        # Small delay
        await asyncio.sleep(0.1)

    # Final stats
    duration = time.time() - start_time
    logger.info("=" * 80)
    logger.info("✅ COMPLETE!")
    logger.info("=" * 80)
    logger.info(f"Total processed: {updated} nodes")
    logger.info(f"Failed: {failed} nodes")
    logger.info(f"Duration: {duration/60:.1f} minutes ({duration:.1f} seconds)")
    logger.info(f"Average rate: {updated/duration:.1f} nodes/sec")
    logger.info("=" * 80)

if __name__ == '__main__':
    asyncio.run(main())
