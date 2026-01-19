#!/usr/bin/env python3
"""
Neo4j Embedding Regeneration - Safe and conservative.

Generates embeddings for Entity nodes (name_embedding) and Entity edges (fact_embedding)
and writes them directly to neo4j. The sync service will then copy them to FalkorDB.
"""

import asyncio
import time
import logging
import json
import os
from typing import List, Optional
from openai import AsyncOpenAI
from graphiti_core.driver.neo4j_driver import Neo4jDriver

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

async def check_neo4j_health(driver: Neo4jDriver) -> bool:
    try:
        result, _, _ = await driver.execute_query("RETURN 1 as health_check")
        return result[0]['health_check'] == 1
    except Exception as e:
        logger.error(f"Neo4j health check failed: {e}")
        return False

async def safe_batch_update_nodes(
    driver: Neo4jDriver,
    nodes: List[dict],
    embeddings: List[List[float]],
    retry_count: int = 3
) -> int:
    """Update Entity nodes with name_embedding using UNWIND."""
    batch_data = [
        {"uuid": node["uuid"], "embedding": embeddings[i]}
        for i, node in enumerate(nodes)
    ]

    query = """
    UNWIND $batch AS item
    MATCH (n:Entity {uuid: item.uuid})
    SET n.name_embedding = item.embedding
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

async def safe_batch_update_edges(
    driver: Neo4jDriver,
    edges: List[dict],
    embeddings: List[List[float]],
    retry_count: int = 3
) -> int:
    """Update Entity edges with fact_embedding using UNWIND."""
    batch_data = [
        {"uuid": edge["uuid"], "embedding": embeddings[i]}
        for i, edge in enumerate(edges)
    ]

    query = """
    UNWIND $batch AS item
    MATCH ()-[r {uuid: item.uuid}]->()
    SET r.fact_embedding = item.embedding
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

async def process_entity_nodes(driver: Neo4jDriver, embedder: SafeOllamaEmbedder):
    """Process Entity node embeddings."""
    BATCH_SIZE = 25
    BATCH_DELAY = 0.2
    CHECKPOINT_FILE = "/tmp/neo4j_entity_embedding_progress.json"

    logger.info("\n" + "=" * 80)
    logger.info("ENTITY NODE EMBEDDING GENERATION")
    logger.info("=" * 80)

    progress = ProgressTracker(CHECKPOINT_FILE)

    # Count total nodes
    count_query = "MATCH (n:Entity) WHERE n.name IS NOT NULL RETURN count(n) as total"
    result, _, _ = await driver.execute_query(count_query)
    total = result[0]['total'] if result else 0

    logger.info(f"📊 Found {total} Entity nodes to process\n")

    if total == 0:
        logger.warning("No nodes found!")
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
            updated_count = await safe_batch_update_nodes(driver, nodes, embeddings)
            update_time = time.time() - update_start
            logger.info(f"  ✓ Updated {updated_count} nodes in {update_time:.2f}s")
            updated += updated_count
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
            logger.info("🏥 Checking Neo4j health...")
            if not await check_neo4j_health(driver):
                logger.error("❌ Neo4j became unhealthy. Stopping.")
                break
            logger.info("✅ Still healthy\n")

        # Rate limiting
        await asyncio.sleep(BATCH_DELAY)

    # Final stats
    duration = time.time() - start_time
    progress.save()

    logger.info("=" * 80)
    logger.info("✅ ENTITY NODE PROCESSING COMPLETE!")
    logger.info("=" * 80)
    logger.info(f"Updated: {updated} nodes")
    logger.info(f"Skipped: {skipped} nodes (already processed)")
    logger.info(f"Failed: {failed} nodes")
    logger.info(f"Duration: {duration/60:.1f} minutes ({duration:.1f} seconds)")
    logger.info(f"Average rate: {updated/duration:.1f} nodes/sec")
    logger.info(f"Checkpoint: {CHECKPOINT_FILE}")
    logger.info("=" * 80 + "\n")

async def process_entity_edges(driver: Neo4jDriver, embedder: SafeOllamaEmbedder):
    """Process Entity edge embeddings."""
    BATCH_SIZE = 20
    BATCH_DELAY = 0.3
    CHECKPOINT_FILE = "/tmp/neo4j_edge_embedding_progress.json"

    logger.info("\n" + "=" * 80)
    logger.info("ENTITY EDGE EMBEDDING GENERATION")
    logger.info("=" * 80)

    progress = ProgressTracker(CHECKPOINT_FILE)

    # Count UNIQUE edge UUIDs (to handle duplicates)
    count_query = "MATCH ()-[r]->() WHERE r.fact IS NOT NULL RETURN count(DISTINCT r.uuid) as total"
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

        # Fetch batch (DISTINCT to handle duplicate UUIDs)
        fetch_start = time.time()
        fetch_query = """
        MATCH ()-[r]->()
        WHERE r.fact IS NOT NULL AND r.fact <> ''
        WITH DISTINCT r.uuid as uuid, r.fact as fact, r.created_at as created_at
        ORDER BY created_at DESC
        SKIP $offset
        LIMIT $limit
        RETURN uuid, fact
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
            updated_count = await safe_batch_update_edges(driver, edges, embeddings)
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
            logger.info("🏥 Checking Neo4j health...")
            if not await check_neo4j_health(driver):
                logger.error("❌ Neo4j became unhealthy. Stopping.")
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
    logger.info("=" * 80 + "\n")

async def main():
    # Configuration
    OLLAMA_URL = "http://192.168.50.80:11434/v1"
    OLLAMA_MODEL = "dengcao/Qwen3-Embedding-4B:Q4_K_M"
    NEO4J_URI = "bolt://localhost:7687"
    NEO4J_USER = "neo4j"
    NEO4J_PASSWORD = "graphiti123"
    DB_NAME = "neo4j"

    logger.info("=" * 80)
    logger.info("NEO4J EMBEDDING REGENERATION - Conservative Mode")
    logger.info("=" * 80)
    logger.info(f"Database: Neo4j @ {NEO4J_URI}/{DB_NAME}")
    logger.info(f"Ollama: {OLLAMA_URL}")
    logger.info(f"Model: {OLLAMA_MODEL}")
    logger.info(f"Processing: Single-threaded (safe)")
    logger.info("Strategy: Write to neo4j, sync service will copy to FalkorDB")
    logger.info("=" * 80)

    # Initialize
    driver = Neo4jDriver(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD, database=DB_NAME)
    embedder = SafeOllamaEmbedder(OLLAMA_URL, OLLAMA_MODEL)

    # Health check
    logger.info("\n🏥 Checking Neo4j health...")
    if not await check_neo4j_health(driver):
        logger.error("❌ Neo4j is not healthy. Aborting.")
        return
    logger.info("✅ Neo4j is healthy\n")

    try:
        # Process Entity nodes
        await process_entity_nodes(driver, embedder)

        # Process Entity edges
        await process_entity_edges(driver, embedder)

        logger.info("\n" + "=" * 80)
        logger.info("✅ ALL PROCESSING COMPLETE!")
        logger.info("=" * 80)
        logger.info("Embeddings have been written to neo4j.")
        logger.info("The sync service will automatically copy them to FalkorDB.")
        logger.info("=" * 80)

    finally:
        # Close driver
        await driver.close()

if __name__ == '__main__':
    asyncio.run(main())
