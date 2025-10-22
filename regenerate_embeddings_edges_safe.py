#!/usr/bin/env python3
"""
SAFE Edge embedding regeneration - Conservative approach.

Generates embeddings for relationship edges in the graph.
"""

import asyncio
import time
import logging
import json
import os
from typing import List, Optional
from pathlib import Path
from openai import AsyncOpenAI
from graphiti_core.driver.falkordb_driver import FalkorDriver

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SafeOllamaEmbedder:
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url
        self.model = model
        self.client = AsyncOpenAI(base_url=base_url, api_key='ollama')
        logger.info(f'✓ Embedder initialized: {model} at {base_url}')

    async def create_batch(self, texts: List[str], retry_count: int = 3) -> Optional[List[List[float]]]:
        """Generate embeddings with retry logic."""
        for attempt in range(retry_count):
            try:
                response = await self.client.embeddings.create(input=texts, model=self.model)
                return [item.embedding for item in response.data]
            except Exception as e:
                if attempt < retry_count - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Embedding failed (attempt {attempt + 1}/{retry_count}): {e}")
                    logger.info(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Embedding failed after {retry_count} attempts: {e}")
                    return None

class ProgressTracker:
    def __init__(self, checkpoint_file: str):
        self.checkpoint_file = checkpoint_file
        self.processed_offsets = set()
        self.load()

    def load(self):
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file, 'r') as f:
                    data = json.load(f)
                    self.processed_offsets = set(data.get('processed_offsets', []))
                logger.info(f"📂 Loaded checkpoint: {len(self.processed_offsets)} batches already processed")
            except Exception as e:
                logger.warning(f"Could not load checkpoint: {e}")

    def save(self):
        try:
            with open(self.checkpoint_file, 'w') as f:
                json.dump({
                    'processed_offsets': list(self.processed_offsets),
                    'last_update': time.time()
                }, f)
        except Exception as e:
            logger.warning(f"Could not save checkpoint: {e}")

    def mark_processed(self, offset: int):
        self.processed_offsets.add(offset)
        if len(self.processed_offsets) % 10 == 0:
            self.save()

    def is_processed(self, offset: int) -> bool:
        return offset in self.processed_offsets

async def check_falkordb_health(driver: FalkorDriver) -> bool:
    try:
        result, _, _ = await driver.execute_query("RETURN 1 as health_check")
        return result[0]['health_check'] == 1
    except Exception as e:
        logger.error(f"FalkorDB health check failed: {e}")
        return False

async def safe_batch_update(
    driver: FalkorDriver,
    edges: List[dict],
    embeddings: List[List[float]],
    retry_count: int = 3
) -> int:
    """Update edges with embeddings using UNWIND."""
    batch_data = [
        {"uuid": edge["uuid"], "embedding": embeddings[i]}
        for i, edge in enumerate(edges)
    ]

    # Note: Edges use 'fact_embedding' field
    query = """
    UNWIND $batch AS item
    MATCH ()-[r {uuid: item.uuid}]->()
    SET r.fact_embedding = vecf32(item.embedding)
    RETURN count(r) as updated
    """

    for attempt in range(retry_count):
        try:
            result, _, _ = await driver.execute_query(query, batch=batch_data)
            return result[0]['updated'] if result else 0
        except Exception as e:
            if attempt < retry_count - 1:
                wait_time = 2 ** attempt
                logger.warning(f"Update failed (attempt {attempt + 1}/{retry_count}): {e}")
                logger.info(f"Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Update failed after {retry_count} attempts: {e}")
                raise

async def main():
    # Configuration
    OLLAMA_URL = "http://192.168.50.80:11434/v1"
    OLLAMA_MODEL = "dengcao/Qwen3-Embedding-4B:Q4_K_M"
    DB_NAME = "graphiti_migration"
    BATCH_SIZE = 20  # Smaller for edges since they're more complex
    BATCH_DELAY = 0.3  # Slightly longer delay for edges
    CHECKPOINT_FILE = "/tmp/embedding_progress_edges.json"

    logger.info("=" * 80)
    logger.info("SAFE EDGE EMBEDDING REGENERATION - Conservative Mode")
    logger.info("=" * 80)
    logger.info(f"Database: {DB_NAME}")
    logger.info(f"Ollama: {OLLAMA_URL}")
    logger.info(f"Model: {OLLAMA_MODEL}")
    logger.info(f"Batch Size: {BATCH_SIZE} (conservative)")
    logger.info(f"Batch Delay: {BATCH_DELAY}s (rate limited)")
    logger.info(f"Processing: Single-threaded (safe)")
    logger.info("=" * 80)

    # Initialize
    driver = FalkorDriver(host='localhost', port=6379, database=DB_NAME)
    embedder = SafeOllamaEmbedder(OLLAMA_URL, OLLAMA_MODEL)
    progress = ProgressTracker(CHECKPOINT_FILE)

    # Health check
    logger.info("\n🏥 Checking FalkorDB health...")
    if not await check_falkordb_health(driver):
        logger.error("❌ FalkorDB is not healthy. Aborting.")
        return
    logger.info("✅ FalkorDB is healthy\n")

    # Count total edges - edges use 'fact' field for embedding
    count_query = "MATCH ()-[r]->() WHERE r.fact IS NOT NULL RETURN count(r) as total"
    result, _, _ = await driver.execute_query(count_query)
    total = result[0]['total'] if result else 0

    logger.info(f"📊 Found {total} edges to process\n")

    if total == 0:
        logger.warning("No edges found!")
        return

    # Process in batches
    updated = 0
    failed = 0
    skipped = 0
    start_time = time.time()

    for offset in range(0, total, BATCH_SIZE):
        batch_num = offset // BATCH_SIZE + 1
        limit = min(BATCH_SIZE, total - offset)

        if progress.is_processed(offset):
            skipped += limit
            logger.info(f"⏭️  Batch {batch_num}: Skipping (already processed)")
            continue

        logger.info(f"🔄 Batch {batch_num}/{(total + BATCH_SIZE - 1) // BATCH_SIZE}: Processing {limit} edges (offset {offset})...")

        # Fetch batch - edges have 'fact' field for text content
        fetch_start = time.time()
        fetch_query = """
        MATCH ()-[r]->()
        WHERE r.fact IS NOT NULL AND r.fact <> ''
        RETURN r.uuid as uuid, r.fact as fact
        ORDER BY r.created_at DESC
        SKIP $offset
        LIMIT $limit
        """

        try:
            edges, _, _ = await driver.execute_query(fetch_query, offset=offset, limit=limit)
        except Exception as e:
            logger.error(f"❌ Fetch failed: {e}")
            failed += limit
            continue

        if not edges:
            logger.warning("No more edges to fetch")
            break

        fetch_time = time.time() - fetch_start
        logger.info(f"  ✓ Fetched {len(edges)} edges in {fetch_time:.2f}s")

        # Generate embeddings from fact field
        embed_start = time.time()
        facts = [e['fact'] for e in edges]
        embeddings = await embedder.create_batch(facts)

        if embeddings is None:
            logger.error(f"❌ Embedding generation failed")
            failed += len(edges)
            continue

        embed_time = time.time() - embed_start
        logger.info(f"  ✓ Generated {len(embeddings)} embeddings in {embed_time:.2f}s ({len(embeddings)/embed_time:.1f} emb/s)")

        # Update database
        update_start = time.time()
        try:
            updated_count = await safe_batch_update(driver, edges, embeddings)
            update_time = time.time() - update_start
            logger.info(f"  ✓ Updated {updated_count} edges in {update_time:.2f}s")
            updated += updated_count
            progress.mark_processed(offset)
        except Exception as e:
            logger.error(f"❌ Update failed: {e}")
            failed += len(edges)
            continue

        # Progress report
        elapsed = time.time() - start_time
        rate = updated / elapsed if elapsed > 0 else 0
        remaining = total - updated - failed - skipped
        eta = remaining / rate if rate > 0 else 0

        logger.info(f"\n📈 Progress: {updated + skipped}/{total} ({(updated + skipped)*100//total}%)")
        logger.info(f"   Updated: {updated}, Skipped: {skipped}, Failed: {failed}")
        logger.info(f"   Rate: {rate:.1f} edges/sec, ETA: {eta/60:.1f} minutes\n")

        # Health check every 10 batches
        if batch_num % 10 == 0:
            logger.info("🏥 Checking FalkorDB health...")
            if not await check_falkordb_health(driver):
                logger.error("❌ FalkorDB became unhealthy. Stopping.")
                break
            logger.info("✅ Still healthy\n")

        # Rate limiting
        await asyncio.sleep(BATCH_DELAY)

    # Final stats
    duration = time.time() - start_time
    progress.save()

    logger.info("=" * 80)
    logger.info("✅ EDGE PROCESSING COMPLETE!")
    logger.info("=" * 80)
    logger.info(f"Updated: {updated} edges")
    logger.info(f"Skipped: {skipped} edges (already processed)")
    logger.info(f"Failed: {failed} edges")
    logger.info(f"Duration: {duration/60:.1f} minutes ({duration:.1f} seconds)")
    logger.info(f"Average rate: {updated/duration:.1f} edges/sec")
    logger.info(f"Checkpoint: {CHECKPOINT_FILE}")
    logger.info("=" * 80)

if __name__ == '__main__':
    asyncio.run(main())
