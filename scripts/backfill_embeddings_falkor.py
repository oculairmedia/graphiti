#!/usr/bin/env python3
"""
Backfill Missing Embeddings - FalkorDB Only (Batched UNWIND)

Uses UNWIND for efficient batch updates instead of individual queries.
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

BATCH_SIZE = 20  # Smaller batches for stability
BATCH_DELAY = 0.5  # More delay between batches


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


def get_missing_edges(r: redis.Redis, limit: int) -> List[dict]:
    """Get edges missing fact_embedding from FalkorDB."""
    query = f"""
        MATCH ()-[r:RELATES_TO]->()
        WHERE r.fact IS NOT NULL AND r.fact_embedding IS NULL
        RETURN r.uuid as uuid, r.fact as fact
        LIMIT {limit}
    """
    try:
        result = r.execute_command('GRAPH.QUERY', FALKORDB_GRAPH, query)
        if result and len(result) >= 2:
            rows = result[1]
            return [{'uuid': row[0], 'fact': row[1]} for row in rows if row[0] and row[1]]
        return []
    except Exception as e:
        logger.error(f'Fetch failed: {e}')
        return []


def get_missing_count(r: redis.Redis) -> int:
    """Count edges missing embeddings."""
    query = """
        MATCH ()-[r:RELATES_TO]->()
        WHERE r.fact IS NOT NULL AND r.fact_embedding IS NULL
        RETURN count(r) as cnt
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
    """Count edges WITH embeddings."""
    query = """
        MATCH ()-[r:RELATES_TO]->()
        WHERE r.fact_embedding IS NOT NULL
        RETURN count(r) as cnt
    """
    try:
        result = r.execute_command('GRAPH.QUERY', FALKORDB_GRAPH, query)
        if result and len(result) >= 2 and result[1]:
            return int(result[1][0][0])
        return 0
    except Exception as e:
        return 0


def batch_update_embeddings(r: redis.Redis, updates: List[dict]) -> int:
    """Update multiple edges using individual queries (FalkorDB doesn't support UNWIND well with vecf32)."""
    success = 0
    for u in updates:
        try:
            emb_str = ','.join(str(x) for x in u['embedding'])
            query = f"""
                MATCH ()-[r:RELATES_TO {{uuid: '{u['uuid']}'}}]->()
                SET r.fact_embedding = vecf32([{emb_str}])
                RETURN 1
            """
            r.execute_command('GRAPH.QUERY', FALKORDB_GRAPH, query)
            success += 1
        except Exception as e:
            logger.warning(f'Failed to update {u["uuid"]}: {e}')
    return success


async def main():
    logger.info('=' * 60)
    logger.info('FALKORDB EMBEDDING BACKFILL')
    logger.info('=' * 60)

    r = redis.Redis(host=FALKORDB_HOST, port=FALKORDB_PORT, decode_responses=True)
    embedder = OllamaEmbedder(OLLAMA_URL, OLLAMA_MODEL)

    # Check connection
    r.ping()
    logger.info('FalkorDB connected')

    # Get counts
    missing = get_missing_count(r)
    has_emb = get_total_with_embedding(r)
    total = missing + has_emb

    logger.info(f'Total edges: {total:,}')
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
    last_checkpoint = time.time()

    while True:
        edges = get_missing_edges(r, BATCH_SIZE)
        if not edges:
            break

        batch_num = processed // BATCH_SIZE + 1

        # Generate embeddings
        facts = [e['fact'] for e in edges]
        embeddings = await embedder.embed_batch(facts)

        if embeddings is None:
            failed += len(edges)
            logger.error(f'Batch {batch_num}: Embedding generation failed')
            await asyncio.sleep(5)
            continue

        # Prepare updates
        updates = [
            {'uuid': edges[i]['uuid'], 'embedding': embeddings[i]} for i in range(len(edges))
        ]

        # Update FalkorDB
        batch_success = batch_update_embeddings(r, updates)
        processed += batch_success
        failed += len(edges) - batch_success

        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        remaining = missing - processed
        eta = remaining / rate if rate > 0 else 0

        logger.info(
            f'Batch {batch_num}: +{batch_success}/{len(edges)} | Total: {processed:,}/{missing:,} ({processed * 100 // missing}%) | {rate:.1f}/s | ETA: {eta / 60:.1f}m'
        )

        # Progress checkpoint every 5 minutes
        if time.time() - last_checkpoint > 300:
            current_with_emb = get_total_with_embedding(r)
            logger.info(
                f'  CHECKPOINT: FalkorDB now has {current_with_emb:,} edges with embeddings'
            )
            last_checkpoint = time.time()

        await asyncio.sleep(BATCH_DELAY)

    duration = time.time() - start_time
    final_count = get_total_with_embedding(r)
    logger.info('=' * 60)
    logger.info(f'COMPLETE!')
    logger.info(f'Processed: {processed:,} edges')
    logger.info(f'Failed: {failed:,} edges')
    logger.info(f'Duration: {duration / 60:.1f} min')
    logger.info(f'FalkorDB edges with embeddings: {final_count:,}')
    logger.info('=' * 60)


if __name__ == '__main__':
    asyncio.run(main())
