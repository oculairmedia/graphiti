#!/usr/bin/env python3
"""
Backfill Missing Embeddings - Writes to BOTH Neo4j and FalkorDB.

Generates embeddings for:
1. RELATES_TO edges without fact_embedding
2. Entity nodes without name_embedding

Writes to Neo4j first, then FalkorDB.
"""

import asyncio
import time
import logging
from typing import List, Optional
from openai import AsyncOpenAI
from neo4j import AsyncGraphDatabase
import redis

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
OLLAMA_URL = 'http://192.168.50.80:11434/v1'
OLLAMA_MODEL = 'dengcao/Qwen3-Embedding-4B:Q4_K_M'
NEO4J_URI = 'bolt://localhost:7687'
NEO4J_USER = 'neo4j'
NEO4J_PASSWORD = 'graphiti123'
NEO4J_DB = 'neo4j'
FALKORDB_HOST = 'localhost'
FALKORDB_PORT = 6379
FALKORDB_GRAPH = 'graphiti_migration'

BATCH_SIZE = 50
BATCH_DELAY = 0.1  # seconds between batches


class OllamaEmbedder:
    def __init__(self, base_url: str, model: str):
        self.client = AsyncOpenAI(base_url=base_url, api_key='ollama')
        self.model = model
        logger.info(f'Embedder initialized: {model} at {base_url}')

    async def embed_batch(self, texts: List[str], retries: int = 3) -> Optional[List[List[float]]]:
        """Generate embeddings for a batch of texts."""
        for attempt in range(retries):
            try:
                # Clean texts
                cleaned = [t.replace('\n', ' ').strip()[:8000] for t in texts]
                response = await self.client.embeddings.create(input=cleaned, model=self.model)
                return [item.embedding for item in response.data]
            except Exception as e:
                if attempt < retries - 1:
                    wait = 2**attempt
                    logger.warning(
                        f'Embed failed (attempt {attempt + 1}): {e}, retrying in {wait}s'
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(f'Embed failed after {retries} attempts: {e}')
                    return None


class FalkorDBClient:
    def __init__(self, host: str, port: int, graph: str):
        self.redis = redis.Redis(host=host, port=port, decode_responses=True)
        self.graph = graph
        logger.info(f'FalkorDB initialized: {host}:{port}/{graph}')

    def execute(self, query: str, params: Optional[dict] = None) -> list:
        """Execute a Cypher query on FalkorDB."""
        try:
            if params:
                # FalkorDB uses CYPHER prefix for parameters
                param_str = ' '.join(f'{k}={self._format_value(v)}' for k, v in params.items())
                full_query = f'CYPHER {param_str} {query}'
            else:
                full_query = query
            result = self.redis.execute_command('GRAPH.QUERY', self.graph, full_query)
            return result
        except Exception as e:
            logger.error(f'FalkorDB query failed: {e}')
            raise

    def _format_value(self, v):
        """Format a value for Cypher parameter."""
        if isinstance(v, str):
            return f'"{v}"'
        elif isinstance(v, list):
            return f'vecf32({v})'
        return str(v)

    def update_edge_embedding(self, uuid: str, embedding: List[float]) -> bool:
        """Update a single edge's fact_embedding."""
        try:
            # Convert embedding to vecf32 format string
            emb_str = ','.join(str(x) for x in embedding)
            query = f"""
                MATCH ()-[r:RELATES_TO {{uuid: '{uuid}'}}]->()
                SET r.fact_embedding = vecf32([{emb_str}])
                RETURN r.uuid
            """
            self.redis.execute_command('GRAPH.QUERY', self.graph, query)
            return True
        except Exception as e:
            logger.error(f'FalkorDB edge update failed for {uuid}: {e}')
            return False

    def update_node_embedding(self, uuid: str, embedding: List[float]) -> bool:
        """Update a single node's name_embedding."""
        try:
            emb_str = ','.join(str(x) for x in embedding)
            query = f"""
                MATCH (n:Entity {{uuid: '{uuid}'}})
                SET n.name_embedding = vecf32([{emb_str}])
                RETURN n.uuid
            """
            self.redis.execute_command('GRAPH.QUERY', self.graph, query)
            return True
        except Exception as e:
            logger.error(f'FalkorDB node update failed for {uuid}: {e}')
            return False

    def batch_update_edge_embeddings(self, updates: List[dict]) -> int:
        """Update multiple edges' embeddings."""
        success = 0
        for u in updates:
            if self.update_edge_embedding(u['uuid'], u['embedding']):
                success += 1
        return success

    def batch_update_node_embeddings(self, updates: List[dict]) -> int:
        """Update multiple nodes' embeddings."""
        success = 0
        for u in updates:
            if self.update_node_embedding(u['uuid'], u['embedding']):
                success += 1
        return success


async def get_missing_edge_count(driver) -> int:
    """Count edges missing fact_embedding in Neo4j."""
    async with driver.session(database=NEO4J_DB) as session:
        result = await session.run("""
            MATCH ()-[r:RELATES_TO]->()
            WHERE r.fact IS NOT NULL AND r.fact <> '' AND r.fact_embedding IS NULL
            RETURN count(r) as cnt
        """)
        record = await result.single()
        return record['cnt'] if record else 0


async def get_missing_node_count(driver) -> int:
    """Count Entity nodes missing name_embedding in Neo4j."""
    async with driver.session(database=NEO4J_DB) as session:
        result = await session.run("""
            MATCH (n:Entity)
            WHERE n.name IS NOT NULL AND n.name <> '' AND n.name_embedding IS NULL
            RETURN count(n) as cnt
        """)
        record = await result.single()
        return record['cnt'] if record else 0


async def fetch_edges_missing_embedding(driver, limit: int) -> List[dict]:
    """Fetch edges that need embeddings from Neo4j."""
    async with driver.session(database=NEO4J_DB) as session:
        result = await session.run(
            """
            MATCH ()-[r:RELATES_TO]->()
            WHERE r.fact IS NOT NULL AND r.fact <> '' AND r.fact_embedding IS NULL
            RETURN r.uuid as uuid, r.fact as fact
            LIMIT $limit
        """,
            limit=limit,
        )
        records = await result.data()
        return records


async def fetch_nodes_missing_embedding(driver, limit: int) -> List[dict]:
    """Fetch Entity nodes that need embeddings from Neo4j."""
    async with driver.session(database=NEO4J_DB) as session:
        result = await session.run(
            """
            MATCH (n:Entity)
            WHERE n.name IS NOT NULL AND n.name <> '' AND n.name_embedding IS NULL
            RETURN n.uuid as uuid, n.name as name
            LIMIT $limit
        """,
            limit=limit,
        )
        records = await result.data()
        return records


async def update_neo4j_edge_embeddings(driver, updates: List[dict]) -> int:
    """Update edges with their embeddings in Neo4j."""
    async with driver.session(database=NEO4J_DB) as session:
        result = await session.run(
            """
            UNWIND $updates AS item
            MATCH ()-[r:RELATES_TO {uuid: item.uuid}]->()
            SET r.fact_embedding = item.embedding
            RETURN count(r) as updated
        """,
            updates=updates,
        )
        record = await result.single()
        return record['updated'] if record else 0


async def update_neo4j_node_embeddings(driver, updates: List[dict]) -> int:
    """Update Entity nodes with their embeddings in Neo4j."""
    async with driver.session(database=NEO4J_DB) as session:
        result = await session.run(
            """
            UNWIND $updates AS item
            MATCH (n:Entity {uuid: item.uuid})
            SET n.name_embedding = item.embedding
            RETURN count(n) as updated
        """,
            updates=updates,
        )
        record = await result.single()
        return record['updated'] if record else 0


async def backfill_edges(neo4j_driver, falkor: FalkorDBClient, embedder: OllamaEmbedder):
    """Backfill missing edge embeddings to both databases."""
    total = await get_missing_edge_count(neo4j_driver)
    logger.info(f'\n{"=" * 60}')
    logger.info(f'EDGE EMBEDDING BACKFILL')
    logger.info(f'{"=" * 60}')
    logger.info(f'Edges missing fact_embedding: {total:,}')

    if total == 0:
        logger.info('No edges need embeddings!')
        return

    processed = 0
    failed = 0
    start_time = time.time()

    while True:
        # Fetch batch from Neo4j
        edges = await fetch_edges_missing_embedding(neo4j_driver, BATCH_SIZE)
        if not edges:
            break

        batch_num = processed // BATCH_SIZE + 1
        logger.info(f'\nBatch {batch_num}: Processing {len(edges)} edges...')

        # Generate embeddings
        facts = [e['fact'] for e in edges]
        embeddings = await embedder.embed_batch(facts)

        if embeddings is None:
            logger.error(f'Embedding failed for batch {batch_num}')
            failed += len(edges)
            await asyncio.sleep(5)
            continue

        # Prepare updates
        updates = [
            {'uuid': edges[i]['uuid'], 'embedding': embeddings[i]} for i in range(len(edges))
        ]

        try:
            # Update Neo4j
            neo4j_updated = await update_neo4j_edge_embeddings(neo4j_driver, updates)
            logger.info(f'  Neo4j: {neo4j_updated} edges updated')

            # Update FalkorDB
            falkor_updated = falkor.batch_update_edge_embeddings(updates)
            logger.info(f'  FalkorDB: {falkor_updated} edges updated')

            processed += neo4j_updated

            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = total - processed - failed
            eta = remaining / rate if rate > 0 else 0

            logger.info(
                f'  Progress: {processed:,}/{total:,} ({processed * 100 // total}%) | Rate: {rate:.1f}/sec | ETA: {eta / 60:.1f} min'
            )

        except Exception as e:
            logger.error(f'Update failed: {e}')
            failed += len(edges)

        await asyncio.sleep(BATCH_DELAY)

    duration = time.time() - start_time
    logger.info(f'\n{"=" * 60}')
    logger.info(f'EDGE BACKFILL COMPLETE')
    logger.info(f'{"=" * 60}')
    logger.info(f'Processed: {processed:,} edges')
    logger.info(f'Failed: {failed:,} edges')
    logger.info(f'Duration: {duration / 60:.1f} minutes')
    if duration > 0:
        logger.info(f'Rate: {processed / duration:.1f} edges/sec')


async def backfill_nodes(neo4j_driver, falkor: FalkorDBClient, embedder: OllamaEmbedder):
    """Backfill missing node embeddings to both databases."""
    total = await get_missing_node_count(neo4j_driver)
    logger.info(f'\n{"=" * 60}')
    logger.info(f'NODE EMBEDDING BACKFILL')
    logger.info(f'{"=" * 60}')
    logger.info(f'Nodes missing name_embedding: {total:,}')

    if total == 0:
        logger.info('No nodes need embeddings!')
        return

    processed = 0
    failed = 0
    start_time = time.time()

    while True:
        # Fetch batch from Neo4j
        nodes = await fetch_nodes_missing_embedding(neo4j_driver, BATCH_SIZE)
        if not nodes:
            break

        batch_num = processed // BATCH_SIZE + 1
        logger.info(f'\nBatch {batch_num}: Processing {len(nodes)} nodes...')

        # Generate embeddings
        names = [n['name'] for n in nodes]
        embeddings = await embedder.embed_batch(names)

        if embeddings is None:
            logger.error(f'Embedding failed for batch {batch_num}')
            failed += len(nodes)
            await asyncio.sleep(5)
            continue

        # Prepare updates
        updates = [
            {'uuid': nodes[i]['uuid'], 'embedding': embeddings[i]} for i in range(len(nodes))
        ]

        try:
            # Update Neo4j
            neo4j_updated = await update_neo4j_node_embeddings(neo4j_driver, updates)
            logger.info(f'  Neo4j: {neo4j_updated} nodes updated')

            # Update FalkorDB
            falkor_updated = falkor.batch_update_node_embeddings(updates)
            logger.info(f'  FalkorDB: {falkor_updated} nodes updated')

            processed += neo4j_updated

            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = total - processed - failed
            eta = remaining / rate if rate > 0 else 0

            logger.info(
                f'  Progress: {processed:,}/{total:,} ({processed * 100 // total}%) | Rate: {rate:.1f}/sec | ETA: {eta / 60:.1f} min'
            )

        except Exception as e:
            logger.error(f'Update failed: {e}')
            failed += len(nodes)

        await asyncio.sleep(BATCH_DELAY)

    duration = time.time() - start_time
    logger.info(f'\n{"=" * 60}')
    logger.info(f'NODE BACKFILL COMPLETE')
    logger.info(f'{"=" * 60}')
    logger.info(f'Processed: {processed:,} nodes')
    logger.info(f'Failed: {failed:,} nodes')
    logger.info(f'Duration: {duration / 60:.1f} minutes')
    if duration > 0:
        logger.info(f'Rate: {processed / duration:.1f} nodes/sec')


async def main():
    logger.info('=' * 60)
    logger.info('EMBEDDING BACKFILL - Neo4j + FalkorDB')
    logger.info('=' * 60)
    logger.info(f'Neo4j: {NEO4J_URI}')
    logger.info(f'FalkorDB: {FALKORDB_HOST}:{FALKORDB_PORT}/{FALKORDB_GRAPH}')
    logger.info(f'Ollama: {OLLAMA_URL}')
    logger.info(f'Model: {OLLAMA_MODEL}')
    logger.info(f'Batch size: {BATCH_SIZE}')
    logger.info('=' * 60)

    # Initialize Neo4j
    neo4j_driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    # Initialize FalkorDB
    falkor = FalkorDBClient(FALKORDB_HOST, FALKORDB_PORT, FALKORDB_GRAPH)

    # Initialize embedder
    embedder = OllamaEmbedder(OLLAMA_URL, OLLAMA_MODEL)

    # Check Neo4j connectivity
    try:
        async with neo4j_driver.session(database=NEO4J_DB) as session:
            result = await session.run('RETURN 1')
            await result.single()
        logger.info('Neo4j connection OK')
    except Exception as e:
        logger.error(f'Neo4j connection failed: {e}')
        return

    # Check FalkorDB connectivity
    try:
        falkor.redis.ping()
        logger.info('FalkorDB connection OK')
    except Exception as e:
        logger.error(f'FalkorDB connection failed: {e}')
        return

    try:
        # Backfill edges first (more important for search)
        await backfill_edges(neo4j_driver, falkor, embedder)

        # Then backfill nodes
        await backfill_nodes(neo4j_driver, falkor, embedder)

        logger.info('\n' + '=' * 60)
        logger.info('ALL BACKFILL COMPLETE!')
        logger.info('=' * 60)

    finally:
        await neo4j_driver.close()


if __name__ == '__main__':
    asyncio.run(main())
