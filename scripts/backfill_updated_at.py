#!/usr/bin/env python3
"""
GRAPH-100: Batched migration script to backfill updated_at field.

This script sets updated_at = created_at for all existing nodes and edges
that don't have an updated_at value. Uses batching to avoid overwhelming
the database.

Usage:
    python scripts/backfill_updated_at.py [--batch-size 5000] [--dry-run]

Target counts (as of implementation):
- Episodic nodes: ~37K
- Entity nodes: ~18K
- MENTIONS edges: ~146K
- RELATES_TO edges: ~44K
Total: ~245K records
"""

import argparse
import logging
import time
from datetime import datetime

import redis

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# FalkorDB connection settings
FALKORDB_HOST = 'localhost'
FALKORDB_PORT = 6379
FALKORDB_GRAPH = 'graphiti_migration'


def get_redis_client():
    """Get Redis client for FalkorDB."""
    return redis.Redis(host=FALKORDB_HOST, port=FALKORDB_PORT, decode_responses=True)


def execute_query(client, query, params=None):
    """Execute a FalkorDB graph query."""
    if params:
        # FalkorDB uses CYPHER_PARAMS for parameterized queries
        result = client.execute_command('GRAPH.QUERY', FALKORDB_GRAPH, query, '--compact')
    else:
        result = client.execute_command('GRAPH.QUERY', FALKORDB_GRAPH, query)
    return result


def count_missing_updated_at(client, entity_type: str, label_or_type: str) -> int:
    """Count entities missing updated_at field."""
    if entity_type == 'node':
        query = f'MATCH (n:{label_or_type}) WHERE n.updated_at IS NULL RETURN count(n) as cnt'
    else:  # edge
        query = (
            f'MATCH ()-[r:{label_or_type}]->() WHERE r.updated_at IS NULL RETURN count(r) as cnt'
        )

    result = execute_query(client, query)
    # Parse result - format varies but typically includes count
    # Result structure: [[['cnt'], [[count]]]]
    try:
        if isinstance(result, list) and len(result) >= 2:
            data = result[1]
            if isinstance(data, list) and len(data) > 0:
                row = data[0]
                if isinstance(row, list) and len(row) > 0:
                    return int(row[0])
    except (IndexError, ValueError, TypeError) as e:
        logger.warning(f'Failed to parse count result: {result}, error: {e}')
    return 0


def backfill_nodes(client, label: str, batch_size: int, dry_run: bool) -> tuple[int, int]:
    """
    Backfill updated_at for nodes of a specific label.
    Sets updated_at = created_at for nodes where updated_at IS NULL.

    Returns: (total_processed, batches_run)
    """
    total_processed = 0
    batches = 0

    # First, count how many need updating
    missing_count = count_missing_updated_at(client, 'node', label)
    logger.info(f'{label} nodes missing updated_at: {missing_count}')

    if missing_count == 0:
        logger.info(f'No {label} nodes need backfill')
        return 0, 0

    if dry_run:
        logger.info(f'[DRY RUN] Would update {missing_count} {label} nodes')
        return missing_count, (missing_count + batch_size - 1) // batch_size

    # Process in batches
    while True:
        batches += 1
        start_time = time.time()

        # Update batch of nodes: set updated_at = created_at where updated_at IS NULL
        query = f"""
        MATCH (n:{label})
        WHERE n.updated_at IS NULL
        WITH n LIMIT {batch_size}
        SET n.updated_at = n.created_at
        RETURN count(n) as updated_count
        """

        result = execute_query(client, query)

        # Parse result to get updated count
        updated_count = 0
        try:
            if isinstance(result, list) and len(result) >= 2:
                data = result[1]
                if isinstance(data, list) and len(data) > 0:
                    row = data[0]
                    if isinstance(row, list) and len(row) > 0:
                        updated_count = int(row[0])
        except (IndexError, ValueError, TypeError) as e:
            logger.warning(f'Failed to parse update result: {result}, error: {e}')
            break

        total_processed += updated_count
        elapsed = time.time() - start_time

        logger.info(
            f'Batch {batches}: Updated {updated_count} {label} nodes '
            f'({total_processed}/{missing_count}) in {elapsed:.2f}s'
        )

        if updated_count < batch_size:
            # Last batch or no more to process
            break

        # Small delay to avoid overwhelming the database
        time.sleep(0.1)

    return total_processed, batches


def backfill_edges(client, edge_type: str, batch_size: int, dry_run: bool) -> tuple[int, int]:
    """
    Backfill updated_at for edges of a specific type.
    Sets updated_at = created_at for edges where updated_at IS NULL.

    Returns: (total_processed, batches_run)
    """
    total_processed = 0
    batches = 0

    # First, count how many need updating
    missing_count = count_missing_updated_at(client, 'edge', edge_type)
    logger.info(f'{edge_type} edges missing updated_at: {missing_count}')

    if missing_count == 0:
        logger.info(f'No {edge_type} edges need backfill')
        return 0, 0

    if dry_run:
        logger.info(f'[DRY RUN] Would update {missing_count} {edge_type} edges')
        return missing_count, (missing_count + batch_size - 1) // batch_size

    # Process in batches
    while True:
        batches += 1
        start_time = time.time()

        # Update batch of edges: set updated_at = created_at where updated_at IS NULL
        query = f"""
        MATCH ()-[r:{edge_type}]->()
        WHERE r.updated_at IS NULL
        WITH r LIMIT {batch_size}
        SET r.updated_at = r.created_at
        RETURN count(r) as updated_count
        """

        result = execute_query(client, query)

        # Parse result to get updated count
        updated_count = 0
        try:
            if isinstance(result, list) and len(result) >= 2:
                data = result[1]
                if isinstance(data, list) and len(data) > 0:
                    row = data[0]
                    if isinstance(row, list) and len(row) > 0:
                        updated_count = int(row[0])
        except (IndexError, ValueError, TypeError) as e:
            logger.warning(f'Failed to parse update result: {result}, error: {e}')
            break

        total_processed += updated_count
        elapsed = time.time() - start_time

        logger.info(
            f'Batch {batches}: Updated {updated_count} {edge_type} edges '
            f'({total_processed}/{missing_count}) in {elapsed:.2f}s'
        )

        if updated_count < batch_size:
            # Last batch or no more to process
            break

        # Small delay to avoid overwhelming the database
        time.sleep(0.1)

    return total_processed, batches


def main():
    parser = argparse.ArgumentParser(
        description='Backfill updated_at field for existing nodes and edges'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=5000,
        help='Number of records to update per batch (default: 5000)',
    )
    parser.add_argument(
        '--dry-run', action='store_true', help='Show what would be updated without making changes'
    )
    parser.add_argument(
        '--host', type=str, default='localhost', help='FalkorDB host (default: localhost)'
    )
    parser.add_argument('--port', type=int, default=6379, help='FalkorDB port (default: 6379)')
    parser.add_argument(
        '--graph',
        type=str,
        default='graphiti_migration',
        help='Graph name (default: graphiti_migration)',
    )

    args = parser.parse_args()

    global FALKORDB_HOST, FALKORDB_PORT, FALKORDB_GRAPH
    FALKORDB_HOST = args.host
    FALKORDB_PORT = args.port
    FALKORDB_GRAPH = args.graph

    logger.info(
        f'Starting updated_at backfill (batch_size={args.batch_size}, dry_run={args.dry_run})'
    )
    logger.info(
        f'Connecting to FalkorDB at {FALKORDB_HOST}:{FALKORDB_PORT}, graph: {FALKORDB_GRAPH}'
    )

    client = get_redis_client()

    # Test connection
    try:
        client.ping()
        logger.info('Connected to FalkorDB')
    except redis.ConnectionError as e:
        logger.error(f'Failed to connect to FalkorDB: {e}')
        return 1

    start_time = time.time()
    total_records = 0
    total_batches = 0

    # Backfill nodes
    logger.info('=' * 60)
    logger.info('PHASE 1: Backfilling nodes')
    logger.info('=' * 60)

    for label in ['Episodic', 'Entity', 'Community']:
        processed, batches = backfill_nodes(client, label, args.batch_size, args.dry_run)
        total_records += processed
        total_batches += batches

    # Backfill edges
    logger.info('=' * 60)
    logger.info('PHASE 2: Backfilling edges')
    logger.info('=' * 60)

    for edge_type in ['MENTIONS', 'RELATES_TO', 'HAS_MEMBER']:
        processed, batches = backfill_edges(client, edge_type, args.batch_size, args.dry_run)
        total_records += processed
        total_batches += batches

    elapsed = time.time() - start_time

    logger.info('=' * 60)
    logger.info('BACKFILL COMPLETE')
    logger.info('=' * 60)
    logger.info(f'Total records processed: {total_records}')
    logger.info(f'Total batches: {total_batches}')
    logger.info(f'Total time: {elapsed:.2f}s')
    if total_records > 0:
        logger.info(f'Average rate: {total_records / elapsed:.0f} records/second')

    return 0


if __name__ == '__main__':
    exit(main())
