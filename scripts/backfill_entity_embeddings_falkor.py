#!/usr/bin/env python3
"""
Backfill Missing Entity Embeddings - FalkorDB Only
"""

import asyncio
import time
import logging
from typing import List, Optional
from openai import AsyncOpenAI
import redis

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
OLLAMA_URL = 'http://192.168.50.80:11434/v1'
OLLAMA_MODEL = 'dengcao/Qwen3-Embedding-4B:Q4_K_M'
FALKORDB_HOST = 'localhost'
FALKORDB_PORT = 6379
FALKORDB_GRAPH = 'graphiti_migration'

BATCH_SIZE = 50
BATCH_DELAY = 0.3


class OllamaEmbedder:
    def __init__(self, base_url: str, model: str):
        self.client = AsyncOpenAI(base_url=base_url, api_key='ollama')
        self.model = model

    async def embed_batch(self, texts: List[str], retries: int = 3) -> Optional[List[List[float]]]:
        for attempt in range(retries):
            try:
                cleaned = [t.replace('\n', ' ').strip()[:8000] for t in texts]
                response = await self.client.embeddings.create(input=cleaned, model=self.model)
                return [item.embedding for item in response.data]
            except Exception as e:
                if attempt < retries - 1:
                    await asyncio.sleep(2**attempt)
                else:
                    logger.error(f'Embed failed: {e}')
                    return None


def get_missing_entities(r: redis.Redis, limit: int) -> List[dict]:
    """Get entities missing name_embedding."""
    query = f"""
        MATCH (e:Entity)
        WHERE e.name IS NOT NULL AND e.name_embedding IS NULL
        RETURN e.uuid as uuid, e.name as name
        LIMIT {limit}
    """
    try:
        result = r.execute_command('GRAPH.QUERY', FALKORDB_GRAPH, query)
        if result and len(result) >= 2:
            rows = result[1]
            return [{'uuid': row[0], 'name': row[1]} for row in rows if row[0] and row[1]]
        return []
    except Exception as e:
        logger.error(f'Fetch failed: {e}')
        return []


def get_missing_count(r: redis.Redis) -> int:
    """Count entities missing embeddings."""
    query = """
        MATCH (e:Entity)
        WHERE e.name IS NOT NULL AND e.name_embedding IS NULL
        RETURN count(e) as cnt
    """
    try:
        result = r.execute_command('GRAPH.QUERY', FALKORDB_GRAPH, query)
        if result and len(result) >= 2 and result[1]:
            return int(result[1][0][0])
        return 0
    except Exception as e:
        logger.error(f'Count failed: {e}')
        return 0


def get_total_with_embedding(r: redis.Redis) -> int:
    """Count entities WITH embeddings."""
    query = """
        MATCH (e:Entity)
        WHERE e.name_embedding IS NOT NULL
        RETURN count(e) as cnt
    """
    try:
        result = r.execute_command('GRAPH.QUERY', FALKORDB_GRAPH, query)
        if result and len(result) >= 2 and result[1]:
            return int(result[1][0][0])
        return 0
    except Exception as e:
        return 0


def batch_update_embeddings(r: redis.Redis, updates: List[dict]) -> int:
    """Update entity embeddings."""
    success = 0
    for u in updates:
        try:
            emb_str = ','.join(str(x) for x in u['embedding'])
            query = f"""
                MATCH (e:Entity {{uuid: '{u['uuid']}'}})
                SET e.name_embedding = vecf32([{emb_str}])
                RETURN 1
            """
            r.execute_command('GRAPH.QUERY', FALKORDB_GRAPH, query)
            success += 1
        except Exception as e:
            logger.warning(f'Failed to update {u["uuid"]}: {e}')
    return success


async def main():
    logger.info('=' * 60)
    logger.info('FALKORDB ENTITY EMBEDDING BACKFILL')
    logger.info('=' * 60)

    r = redis.Redis(host=FALKORDB_HOST, port=FALKORDB_PORT, decode_responses=True)
    embedder = OllamaEmbedder(OLLAMA_URL, OLLAMA_MODEL)

    r.ping()
    logger.info('FalkorDB connected')

    missing = get_missing_count(r)
    has_emb = get_total_with_embedding(r)
    total = missing + has_emb

    logger.info(f'Total entities: {total:,}')
    logger.info(f'With embedding: {has_emb:,}')
    logger.info(f'Missing embedding: {missing:,}')
    logger.info(f'Batch size: {BATCH_SIZE}')
    logger.info('=' * 60)

    if missing == 0:
        logger.info('Nothing to do!')
        return

    processed = 0
    failed = 0
    start_time = time.time()

    while True:
        entities = get_missing_entities(r, BATCH_SIZE)
        if not entities:
            break

        batch_num = processed // BATCH_SIZE + 1

        names = [e['name'] for e in entities]
        embeddings = await embedder.embed_batch(names)

        if embeddings is None:
            failed += len(entities)
            logger.error(f'Batch {batch_num}: Embedding generation failed')
            await asyncio.sleep(5)
            continue

        updates = [
            {'uuid': entities[i]['uuid'], 'embedding': embeddings[i]} for i in range(len(entities))
        ]

        batch_success = batch_update_embeddings(r, updates)
        processed += batch_success
        failed += len(entities) - batch_success

        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        remaining = missing - processed
        eta = remaining / rate if rate > 0 else 0

        logger.info(
            f'Batch {batch_num}: +{batch_success}/{len(entities)} | Total: {processed:,}/{missing:,} ({processed * 100 // missing}%) | {rate:.1f}/s | ETA: {eta / 60:.1f}m'
        )

        await asyncio.sleep(BATCH_DELAY)

    duration = time.time() - start_time
    final_count = get_total_with_embedding(r)
    logger.info('=' * 60)
    logger.info(f'COMPLETE!')
    logger.info(f'Processed: {processed:,} entities')
    logger.info(f'Failed: {failed:,} entities')
    logger.info(f'Duration: {duration / 60:.1f} min')
    logger.info(f'FalkorDB entities with embeddings: {final_count:,}')
    logger.info('=' * 60)


if __name__ == '__main__':
    asyncio.run(main())
