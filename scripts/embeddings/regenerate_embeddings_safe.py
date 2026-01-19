#!/usr/bin/env python3
"""
SAFE embedding regeneration - Conservative approach to prevent FalkorDB crashes.

Key Safety Features:
- Single-threaded processing (no concurrency)
- Small batches (25 nodes default)
- Rate limiting between batches
- Health checks
- Graceful error handling with exponential backoff
- Progress persistence (resume support)
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
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"Embedding failed (attempt {attempt + 1}/{retry_count}): {e}")
                    logger.info(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Embedding failed after {retry_count} attempts: {e}")
                    return None

class ProgressTracker:
    """Track and persist progress to allow resuming."""

    def __init__(self, checkpoint_file: str):
        self.checkpoint_file = checkpoint_file
        self.processed_offsets = set()
        self.load()

    def load(self):
        """Load progress from checkpoint file."""
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file, 'r') as f:
                    data = json.load(f)
                    self.processed_offsets = set(data.get('processed_offsets', []))
                logger.info(f"📂 Loaded checkpoint: {len(self.processed_offsets)} batches already processed")
            except Exception as e:
                logger.warning(f"Could not load checkpoint: {e}")

    def save(self):
        """Save progress to checkpoint file."""
        try:
            with open(self.checkpoint_file, 'w') as f:
                json.dump({
                    'processed_offsets': list(self.processed_offsets),
                    'last_update': time.time()
                }, f)
        except Exception as e:
            logger.warning(f"Could not save checkpoint: {e}")

    def mark_processed(self, offset: int):
        """Mark a batch offset as processed."""
        self.processed_offsets.add(offset)
        if len(self.processed_offsets) % 10 == 0:  # Save every 10 batches
            self.save()

    def is_processed(self, offset: int) -> bool:
        """Check if batch offset was already processed."""
        return offset in self.processed_offsets

async def check_falkordb_health(driver: FalkorDriver) -> bool:
    """Check if FalkorDB is responsive."""
    try:
        result, _, _ = await driver.execute_query("RETURN 1 as health_check")
        return result[0]['health_check'] == 1
    except Exception as e:
        logger.error(f"FalkorDB health check failed: {e}")
        return False

async def safe_batch_update(
    driver: FalkorDriver,
    nodes: List[dict],
    embeddings: List[List[float]],
    retry_count: int = 3
) -> int:
    """Update nodes with embeddings using UNWIND, with retry logic."""
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
    BATCH_SIZE = 25  # Small batches to be safe
    BATCH_DELAY = 0.2  # 200ms delay between batches
    CHECKPOINT_FILE = "/tmp/embedding_progress_entities.json"

    logger.info("=" * 80)
    logger.info("SAFE EMBEDDING REGENERATION - Conservative Mode")
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

    # Count total nodes
    count_query = "MATCH (n:Entity) WHERE n.name IS NOT NULL RETURN count(n) as total"
    result, _, _ = await driver.execute_query(count_query)
    total = result[0]['total'] if result else 0

    logger.info(f"📊 Found {total} Entity nodes to process\n")

    if total == 0:
        logger.warning("No nodes found!")
        return

    # Process in batches (single-threaded)
    updated = 0
    failed = 0
    skipped = 0
    start_time = time.time()

    for offset in range(0, total, BATCH_SIZE):
        batch_num = offset // BATCH_SIZE + 1
        limit = min(BATCH_SIZE, total - offset)

        # Skip if already processed
        if progress.is_processed(offset):
            skipped += limit
            logger.info(f"⏭️  Batch {batch_num}: Skipping (already processed)")
            continue

        logger.info(f"🔄 Batch {batch_num}/{(total + BATCH_SIZE - 1) // BATCH_SIZE}: Processing {limit} nodes (offset {offset})...")

        # Fetch batch
        fetch_start = time.time()
        fetch_query = """
        MATCH (n:Entity)
        WHERE n.name IS NOT NULL AND n.name <> ''
        RETURN n.uuid as uuid, n.name as name
        ORDER BY n.created_at DESC
        SKIP $offset
        LIMIT $limit
        """

        try:
            nodes, _, _ = await driver.execute_query(fetch_query, offset=offset, limit=limit)
        except Exception as e:
            logger.error(f"❌ Fetch failed: {e}")
            failed += limit
            continue

        if not nodes:
            logger.warning("No more nodes to fetch")
            break

        fetch_time = time.time() - fetch_start
        logger.info(f"  ✓ Fetched {len(nodes)} nodes in {fetch_time:.2f}s")

        # Generate embeddings
        embed_start = time.time()
        names = [n['name'] for n in nodes]
        embeddings = await embedder.create_batch(names)

        if embeddings is None:
            logger.error(f"❌ Embedding generation failed")
            failed += len(nodes)
            continue

        embed_time = time.time() - embed_start
        logger.info(f"  ✓ Generated {len(embeddings)} embeddings in {embed_time:.2f}s ({len(embeddings)/embed_time:.1f} emb/s)")

        # Update database
        update_start = time.time()
        try:
            updated_count = await safe_batch_update(driver, nodes, embeddings)
            update_time = time.time() - update_start
            logger.info(f"  ✓ Updated {updated_count} nodes in {update_time:.2f}s")
            updated += updated_count

            # Mark as processed
            progress.mark_processed(offset)

        except Exception as e:
            logger.error(f"❌ Update failed: {e}")
            failed += len(nodes)
            continue

        # Progress report
        elapsed = time.time() - start_time
        rate = updated / elapsed if elapsed > 0 else 0
        remaining = total - updated - failed - skipped
        eta = remaining / rate if rate > 0 else 0

        logger.info(f"\n📈 Progress: {updated + skipped}/{total} ({(updated + skipped)*100//total}%)")
        logger.info(f"   Updated: {updated}, Skipped: {skipped}, Failed: {failed}")
        logger.info(f"   Rate: {rate:.1f} nodes/sec, ETA: {eta/60:.1f} minutes\n")

        # Health check every 10 batches
        if batch_num % 10 == 0:
            logger.info("🏥 Checking FalkorDB health...")
            if not await check_falkordb_health(driver):
                logger.error("❌ FalkorDB became unhealthy. Stopping.")
                break
            logger.info("✅ Still healthy\n")

        # Rate limiting - give FalkorDB time to breathe
        await asyncio.sleep(BATCH_DELAY)

    # Final stats
    duration = time.time() - start_time
    progress.save()  # Final save

    logger.info("=" * 80)
    logger.info("✅ PROCESSING COMPLETE!")
    logger.info("=" * 80)
    logger.info(f"Updated: {updated} nodes")
    logger.info(f"Skipped: {skipped} nodes (already processed)")
    logger.info(f"Failed: {failed} nodes")
    logger.info(f"Duration: {duration/60:.1f} minutes ({duration:.1f} seconds)")
    logger.info(f"Average rate: {updated/duration:.1f} nodes/sec")
    logger.info(f"Checkpoint: {CHECKPOINT_FILE}")
    logger.info("=" * 80)

if __name__ == '__main__':
    asyncio.run(main())
