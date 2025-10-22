#!/usr/bin/env python3
"""
PARALLEL PIPELINED embedding regeneration.
Uses asyncio to overlap: fetch -> embed -> update operations.
"""

import asyncio
import time
import logging
from typing import List
from openai import AsyncOpenAI
from graphiti_core.driver.falkordb_driver import FalkorDriver

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FastOllamaEmbedder:
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url
        self.model = model
        self.client = AsyncOpenAI(base_url=base_url, api_key='ollama')
        logger.info(f'✓ Initialized with {model} at {base_url}')

    async def create_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        response = await self.client.embeddings.create(input=texts, model=self.model)
        return [item.embedding for item in response.data]

async def fetch_batch(driver: FalkorDriver, offset: int, limit: int):
    """Fetch a batch of nodes."""
    fetch_query = """
    MATCH (n:Entity)
    WHERE n.name IS NOT NULL AND n.name <> ''
    RETURN n.uuid as uuid, n.name as name
    ORDER BY n.created_at DESC
    SKIP $offset
    LIMIT $limit
    """
    nodes, _, _ = await driver.execute_query(fetch_query, offset=offset, limit=limit)
    return nodes

async def update_batch(driver: FalkorDriver, nodes: List[dict], embeddings: List[List[float]]):
    """Update nodes with embeddings using UNWIND."""
    batch_data = [
        {"uuid": node["uuid"], "embedding": embeddings[i]}
        for i, node in enumerate(nodes)
    ]

    query = """
    UNWIND $batch AS item
    MATCH (n:Entity {uuid: item.uuid})
    SET n.name_embedding = vecf32(item.embedding)
    RETURN count(n) as updated
    """

    result, _, _ = await driver.execute_query(query, batch=batch_data)
    return result[0]['updated'] if result else 0

async def process_batch(driver: FalkorDriver, embedder: FastOllamaEmbedder,
                       offset: int, limit: int, batch_num: int):
    """Process a single batch: fetch -> embed -> update."""
    start_time = time.time()

    # Fetch
    nodes = await fetch_batch(driver, offset, limit)
    if not nodes:
        return 0
    fetch_time = time.time() - start_time

    # Embed
    embed_start = time.time()
    names = [n['name'] for n in nodes]
    embeddings = await embedder.create_batch(names)
    embed_time = time.time() - embed_start

    # Update
    update_start = time.time()
    updated = await update_batch(driver, nodes, embeddings)
    update_time = time.time() - update_start

    total_time = time.time() - start_time

    logger.info(
        f"Batch {batch_num}: {updated} nodes | "
        f"Fetch: {fetch_time:.2f}s | Embed: {embed_time:.2f}s | "
        f"Update: {update_time:.2f}s | Total: {total_time:.2f}s"
    )

    return updated

async def main():
    # Configuration
    OLLAMA_URL = "http://192.168.50.80:11434/v1"
    OLLAMA_MODEL = "dengcao/Qwen3-Embedding-4B:Q4_K_M"
    DB_NAME = "graphiti_migration"
    BATCH_SIZE = 100  # Larger batches
    CONCURRENT_BATCHES = 3  # Process 3 batches in parallel!

    logger.info("=" * 80)
    logger.info("PARALLEL PIPELINED EMBEDDING REGENERATION")
    logger.info("=" * 80)
    logger.info(f"Database: {DB_NAME}")
    logger.info(f"Ollama: {OLLAMA_URL}")
    logger.info(f"Model: {OLLAMA_MODEL}")
    logger.info(f"Batch Size: {BATCH_SIZE}")
    logger.info(f"Concurrent Batches: {CONCURRENT_BATCHES}")
    logger.info("=" * 80)

    # Initialize
    driver = FalkorDriver(host='localhost', port=6379, database=DB_NAME)
    embedder = FastOllamaEmbedder(OLLAMA_URL, OLLAMA_MODEL)

    # Count total nodes
    count_query = "MATCH (n:Entity) WHERE n.name IS NOT NULL RETURN count(n) as total"
    result, _, _ = await driver.execute_query(count_query)
    total = result[0]['total'] if result else 0

    logger.info(f"\n📊 Found {total} Entity nodes to process\n")

    if total == 0:
        logger.warning("No nodes found!")
        return

    # Process in parallel batches
    updated = 0
    start_time = time.time()

    # Create tasks for concurrent processing
    tasks = []
    batch_num = 0

    for offset in range(0, total, BATCH_SIZE):
        batch_num += 1
        limit = min(BATCH_SIZE, total - offset)

        # Create task
        task = process_batch(driver, embedder, offset, limit, batch_num)
        tasks.append(task)

        # Execute in batches of CONCURRENT_BATCHES
        if len(tasks) >= CONCURRENT_BATCHES or offset + BATCH_SIZE >= total:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Count successful updates
            for result in results:
                if isinstance(result, int):
                    updated += result
                else:
                    logger.error(f"Batch failed: {result}")

            # Clear tasks for next batch
            tasks = []

            # Progress report
            elapsed = time.time() - start_time
            rate = updated / elapsed if elapsed > 0 else 0
            remaining = total - updated
            eta = remaining / rate if rate > 0 else 0

            logger.info(f"\n📈 Progress: {updated}/{total} ({updated*100//total}%)")
            logger.info(f"   Rate: {rate:.1f} nodes/sec | ETA: {eta/60:.1f} minutes\n")

    # Final stats
    duration = time.time() - start_time
    logger.info("=" * 80)
    logger.info("✅ COMPLETE!")
    logger.info("=" * 80)
    logger.info(f"Total processed: {updated} nodes")
    logger.info(f"Duration: {duration/60:.1f} minutes ({duration:.1f} seconds)")
    logger.info(f"Average rate: {updated/duration:.1f} nodes/sec")
    logger.info("=" * 80)

if __name__ == '__main__':
    asyncio.run(main())
