#!/usr/bin/env python3
"""
STREAMING PIPELINE embedding regeneration.
Uses asyncio queues for continuous processing - NO PAUSES!
Producer fetches -> Queue -> Consumer embeds+updates
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

async def producer(queue: asyncio.Queue, driver: FalkorDriver, total: int, batch_size: int):
    """Producer: Continuously fetch batches and put them in the queue."""
    batch_num = 0
    for offset in range(0, total, batch_size):
        batch_num += 1
        limit = min(batch_size, total - offset)

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

        if nodes:
            # Put batch in queue with batch number
            await queue.put((batch_num, nodes))
            logger.info(f"📥 Producer: Fetched batch {batch_num} ({len(nodes)} nodes)")

    # Signal completion
    await queue.put(None)
    logger.info("📥 Producer: Done fetching")

async def consumer(queue: asyncio.Queue, driver: FalkorDriver, embedder: FastOllamaEmbedder,
                  stats: dict, consumer_id: int):
    """Consumer: Take batches from queue, embed, and update."""
    while True:
        item = await queue.get()

        if item is None:
            # Put None back for other consumers
            await queue.put(None)
            break

        batch_num, nodes = item
        start_time = time.time()

        try:
            # Embed
            embed_start = time.time()
            names = [n['name'] for n in nodes]
            embeddings = await embedder.create_batch(names)
            embed_time = time.time() - embed_start

            # Update using UNWIND
            update_start = time.time()
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
            updated = result[0]['updated'] if result else 0
            update_time = time.time() - update_start

            total_time = time.time() - start_time

            logger.info(
                f"✅ Consumer-{consumer_id}: Batch {batch_num} → {updated} nodes | "
                f"Embed: {embed_time:.2f}s | Update: {update_time:.2f}s | Total: {total_time:.2f}s"
            )

            # Update stats
            stats['updated'] += updated

        except Exception as e:
            logger.error(f"❌ Consumer-{consumer_id}: Batch {batch_num} failed: {e}")
            stats['failed'] += len(nodes)

        finally:
            queue.task_done()

    logger.info(f"✅ Consumer-{consumer_id}: Done processing")

async def progress_reporter(stats: dict, total: int, start_time: float):
    """Periodically report progress."""
    while stats['updated'] + stats['failed'] < total:
        await asyncio.sleep(5)  # Report every 5 seconds

        elapsed = time.time() - start_time
        rate = stats['updated'] / elapsed if elapsed > 0 else 0
        remaining = total - stats['updated'] - stats['failed']
        eta = remaining / rate if rate > 0 else 0

        logger.info(
            f"\n📈 PROGRESS: {stats['updated']}/{total} ({stats['updated']*100//total}%) | "
            f"Rate: {rate:.1f} n/s | ETA: {eta/60:.1f} min | Failed: {stats['failed']}\n"
        )

async def main():
    # Configuration
    OLLAMA_URL = "http://192.168.50.80:11434/v1"
    OLLAMA_MODEL = "dengcao/Qwen3-Embedding-4B:Q4_K_M"
    DB_NAME = "graphiti_migration"
    BATCH_SIZE = 100
    NUM_CONSUMERS = 3  # 3 parallel consumers
    QUEUE_SIZE = 6  # Buffer up to 6 batches

    logger.info("=" * 80)
    logger.info("STREAMING PIPELINE EMBEDDING REGENERATION")
    logger.info("=" * 80)
    logger.info(f"Database: {DB_NAME}")
    logger.info(f"Ollama: {OLLAMA_URL}")
    logger.info(f"Batch Size: {BATCH_SIZE}")
    logger.info(f"Consumers: {NUM_CONSUMERS}")
    logger.info(f"Queue Size: {QUEUE_SIZE}")
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

    # Shared stats
    stats = {'updated': 0, 'failed': 0}
    start_time = time.time()

    # Create queue
    queue = asyncio.Queue(maxsize=QUEUE_SIZE)

    # Start producer, consumers, and progress reporter
    producer_task = asyncio.create_task(producer(queue, driver, total, BATCH_SIZE))

    consumer_tasks = [
        asyncio.create_task(consumer(queue, driver, embedder, stats, i+1))
        for i in range(NUM_CONSUMERS)
    ]

    reporter_task = asyncio.create_task(progress_reporter(stats, total, start_time))

    # Wait for all to complete
    await producer_task
    await queue.join()  # Wait for queue to be empty
    await asyncio.gather(*consumer_tasks)
    reporter_task.cancel()

    # Final stats
    duration = time.time() - start_time
    logger.info("=" * 80)
    logger.info("✅ COMPLETE!")
    logger.info("=" * 80)
    logger.info(f"Total processed: {stats['updated']} nodes")
    logger.info(f"Failed: {stats['failed']} nodes")
    logger.info(f"Duration: {duration/60:.1f} minutes ({duration:.1f} seconds)")
    logger.info(f"Average rate: {stats['updated']/duration:.1f} nodes/sec")
    logger.info("=" * 80)

if __name__ == '__main__':
    asyncio.run(main())
