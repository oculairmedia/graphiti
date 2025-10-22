#!/usr/bin/env python3
"""
FAST embedding regeneration using bulk Redis operations.
This script uses pipelining to dramatically speed up embedding writes.
"""

import asyncio
import os
import time
from typing import List
from openai import AsyncOpenAI
import redis
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FastOllamaEmbedder:
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url
        self.model = model
        self.client = AsyncOpenAI(base_url=base_url, api_key='ollama')
        logger.info(f'Initialized OllamaEmbedder with {model} at {base_url}')

    async def create_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        response = await self.client.embeddings.create(
            input=texts,
            model=self.model
        )
        return [item.embedding for item in response.data]

async def main():
    # Configuration
    OLLAMA_URL = "http://192.168.50.80:11434/v1"
    OLLAMA_MODEL = "dengcao/Qwen3-Embedding-4B:Q4_K_M"
    REDIS_HOST = "localhost"
    REDIS_PORT = 6379
    DB_NAME = "graphiti_migration"
    BATCH_SIZE = 50

    # Initialize
    embedder = FastOllamaEmbedder(OLLAMA_URL, OLLAMA_MODEL)
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=False)

    # Get Entity nodes
    logger.info("Fetching Entity nodes...")
    result = r.execute_command(
        'GRAPH.QUERY', DB_NAME,
        'MATCH (n:Entity) WHERE n.name IS NOT NULL RETURN n.uuid, n.name LIMIT 10000'
    )

    # Parse results (skip header row)
    nodes = []
    for row in result[1:]:
        if isinstance(row, list) and len(row) >= 2:
            uuid_val = row[0]
            name_val = row[1]
            # Decode bytes to string
            if isinstance(uuid_val, bytes):
                uuid_val = uuid_val.decode('utf-8')
            if isinstance(name_val, bytes):
                name_val = name_val.decode('utf-8')
            nodes.append({'uuid': uuid_val, 'name': name_val})

    total = len(nodes)
    logger.info(f"Found {total} Entity nodes to process")

    if total == 0:
        logger.warning("No nodes found!")
        return

    # Process in batches
    updated = 0
    start_time = time.time()

    for i in range(0, total, BATCH_SIZE):
        batch = nodes[i:i+BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1

        logger.info(f"Batch {batch_num}: Processing {len(batch)} nodes...")

        # Generate embeddings
        names = [n['name'] for n in batch]
        embeddings = await embedder.create_batch(names)

        # Build bulk update using Redis pipelining
        pipe = r.pipeline()
        for j, node in enumerate(batch):
            # Convert embedding to vecf32 format
            emb_str = ','.join(str(x) for x in embeddings[j])
            query = f"""
            MATCH (n:Entity {{uuid: '{node['uuid']}'}})
            SET n.name_embedding = vecf32([{emb_str}])
            RETURN n.uuid
            """
            pipe.execute_command('GRAPH.QUERY', DB_NAME, query)

        # Execute pipeline
        pipe.execute()
        updated += len(batch)

        # Progress
        elapsed = time.time() - start_time
        rate = updated / elapsed
        eta = (total - updated) / rate if rate > 0 else 0
        logger.info(f"  Progress: {updated}/{total} ({updated*100//total}%)")
        logger.info(f"  Rate: {rate:.1f} nodes/sec, ETA: {eta/60:.1f} minutes")

    # Final stats
    duration = time.time() - start_time
    logger.info(f"\n✅ COMPLETE!")
    logger.info(f"  Total: {updated} nodes")
    logger.info(f"  Duration: {duration:.1f} seconds")
    logger.info(f"  Average rate: {updated/duration:.1f} nodes/sec")

if __name__ == '__main__':
    asyncio.run(main())
