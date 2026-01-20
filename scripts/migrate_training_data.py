#!/usr/bin/env python3
"""
Migrate training data from JSON files to FalkorDB.

One-time migration script to move existing training data from the
JSON file-based storage to the new FalkorDB-backed storage.

Usage:
    python scripts/migrate_training_data.py
    python scripts/migrate_training_data.py --dry-run  # Preview without migrating
    python scripts/migrate_training_data.py --data-dir /custom/path
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TRAINING_TASKS = ['entity_extraction', 'edge_extraction', 'node_resolution', 'summary_generation']
PROMPT_DATABASE = 'graphiti_prompts'


async def get_existing_count(graph, task: str) -> int:
    query = 'MATCH (t:TrainingExample {task: $task}) RETURN count(t)'
    result = await graph.query(query, {'task': task})
    return result.result_set[0][0] if result.result_set else 0


async def migrate_task(graph, task: str, data: dict, dry_run: bool) -> int:
    examples = data.get('examples', [])
    if not examples:
        logger.info(f'{task}: No examples to migrate')
        return 0

    created_at = data.get('created_at', datetime.now(timezone.utc).isoformat())
    migrated = 0

    for i, example in enumerate(examples):
        inputs = example.get('inputs', {})
        output = example.get('expected_output', {})
        metadata = example.get('metadata', {})
        metadata['migrated_from'] = 'json'
        metadata['original_index'] = i

        if dry_run:
            migrated += 1
            continue

        query = """
        CREATE (t:TrainingExample {
            id: $id,
            task: $task,
            inputs: $inputs,
            output: $output,
            metadata: $metadata,
            created_at: $created_at
        })
        """

        try:
            await graph.query(
                query,
                {
                    'id': str(uuid.uuid4()),
                    'task': task,
                    'inputs': json.dumps(inputs),
                    'output': json.dumps(output),
                    'metadata': json.dumps(metadata),
                    'created_at': created_at,
                },
            )
            migrated += 1
        except Exception as e:
            logger.warning(f'{task}[{i}]: Failed to migrate: {e}')

    return migrated


async def main():
    parser = argparse.ArgumentParser(description='Migrate training data from JSON to FalkorDB')
    parser.add_argument(
        '--data-dir',
        default=os.getenv('DSPY_TRAINING_DATA_DIR', '/data/training_data'),
        help='Directory containing JSON training data files',
    )
    parser.add_argument(
        '--host', default=os.getenv('FALKORDB_HOST', 'localhost'), help='FalkorDB host'
    )
    parser.add_argument(
        '--port', type=int, default=int(os.getenv('FALKORDB_PORT', '6379')), help='FalkorDB port'
    )
    parser.add_argument('--dry-run', action='store_true', help='Preview migration without changes')
    args = parser.parse_args()

    data_dir = Path(args.data_dir)

    if not data_dir.exists():
        logger.error(f'Data directory not found: {data_dir}')
        sys.exit(1)

    try:
        from falkordb.asyncio import FalkorDB
    except ImportError:
        logger.error('falkordb package not installed. Run: pip install falkordb')
        sys.exit(1)

    logger.info(f'Connecting to FalkorDB at {args.host}:{args.port}')
    client = FalkorDB(host=args.host, port=args.port)
    graph = client.select_graph(PROMPT_DATABASE)

    if args.dry_run:
        logger.info('=== DRY RUN MODE - No changes will be made ===')

    total_migrated = 0
    total_skipped = 0

    for task in TRAINING_TASKS:
        json_path = data_dir / f'{task}.json'

        if not json_path.exists():
            logger.info(f'{task}: No JSON file found at {json_path}')
            continue

        try:
            with open(json_path) as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f'{task}: Failed to read JSON file: {e}')
            continue

        example_count = len(data.get('examples', []))
        existing_count = await get_existing_count(graph, task)

        if existing_count > 0 and not args.dry_run:
            logger.warning(
                f'{task}: Already has {existing_count} examples in FalkorDB. '
                f'Skipping to avoid duplicates. Delete existing data first if needed.'
            )
            total_skipped += example_count
            continue

        logger.info(f'{task}: Migrating {example_count} examples...')
        migrated = await migrate_task(graph, task, data, args.dry_run)
        total_migrated += migrated
        logger.info(f'{task}: Migrated {migrated} examples')

    logger.info('=== Migration Summary ===')
    logger.info(f'Total migrated: {total_migrated}')
    logger.info(f'Total skipped: {total_skipped}')

    if not args.dry_run:
        logger.info('Verifying migration...')
        for task in TRAINING_TASKS:
            count = await get_existing_count(graph, task)
            logger.info(f'{task}: {count} examples in FalkorDB')

    if args.dry_run:
        logger.info('=== DRY RUN COMPLETE - No changes were made ===')


if __name__ == '__main__':
    asyncio.run(main())
