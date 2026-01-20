#!/usr/bin/env python3
"""
Initialize FalkorDB prompt storage schema for DSPy optimization.

This script creates the graphiti_prompts graph with PromptVersion nodes
and required indexes. Safe to run multiple times (idempotent).

Usage:
    python scripts/init_prompt_storage.py
    python scripts/init_prompt_storage.py --seed  # Also seed initial prompts
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Schema constants
PROMPT_DATABASE = 'graphiti_prompts'
PROMPT_TASKS = ['entity_extraction', 'edge_extraction', 'node_resolution', 'summary_generation']


async def create_schema(client) -> None:
    """Create the PromptVersion schema with indexes."""
    graph = client.select_graph(PROMPT_DATABASE)

    # FalkorDB uses RANGE indexes with different syntax than Neo4j
    # Format: CREATE INDEX FOR (n:Label) ON (n.property)
    schema_queries = [
        'CREATE INDEX FOR (p:PromptVersion) ON (p.task)',
        'CREATE INDEX FOR (p:PromptVersion) ON (p.status)',
        'CREATE INDEX FOR (p:PromptVersion) ON (p.version)',
        'CREATE INDEX FOR (p:PromptVersion) ON (p.id)',
    ]

    for query in schema_queries:
        try:
            await graph.query(query)
            logger.info(f'Created index: {query}')
        except Exception as e:
            error_msg = str(e).lower()
            if 'already indexed' in error_msg or 'already exists' in error_msg:
                logger.debug(f'Index already exists (skipping): {query}')
            else:
                logger.warning(f'Index creation warning: {e}')


async def get_current_docstrings() -> dict[str, str]:
    """Extract current docstrings from DSPy signatures."""
    from graphiti_core.dspy.signatures import (
        EntityExtractionSignature,
        EdgeExtractionSignature,
        NodeDeduplicationSignature,
        SummaryGenerationSignature,
    )

    return {
        'entity_extraction': EntityExtractionSignature.__doc__ or '',
        'edge_extraction': EdgeExtractionSignature.__doc__ or '',
        'node_resolution': NodeDeduplicationSignature.__doc__ or '',
        'summary_generation': SummaryGenerationSignature.__doc__ or '',
    }


async def get_edge_extraction_demos() -> list[dict]:
    """Get the curated few-shot demos for edge extraction as serializable dicts."""
    try:
        from graphiti_core.dspy.modules import EDGE_EXTRACTION_DEMOS

        serializable_demos = []
        for demo in EDGE_EXTRACTION_DEMOS:
            serializable_demo = {}
            for key, value in demo.items():
                if hasattr(value, 'model_dump'):
                    serializable_demo[key] = value.model_dump()
                else:
                    serializable_demo[key] = value
            serializable_demos.append(serializable_demo)
        return serializable_demos
    except ImportError:
        return []


async def seed_initial_prompts(client) -> None:
    """Seed initial prompts from current DSPy signatures."""
    graph = client.select_graph(PROMPT_DATABASE)

    docstrings = await get_current_docstrings()
    edge_demos = await get_edge_extraction_demos()

    now = datetime.now(timezone.utc).isoformat()

    for task in PROMPT_TASKS:
        # Check if version 1 already exists for this task
        check_query = """
        MATCH (p:PromptVersion {task: $task, version: 1})
        RETURN p.id as id
        """
        result = await graph.query(check_query, {'task': task})

        if result.result_set:
            logger.info(f'Task {task} already has version 1 (skipping)')
            continue

        # Create initial prompt version
        import uuid

        prompt_id = str(uuid.uuid4())
        docstring = docstrings.get(task, '')

        # Only edge_extraction has demos currently
        demos = json.dumps(edge_demos) if task == 'edge_extraction' else '[]'

        create_query = """
        CREATE (p:PromptVersion {
            id: $id,
            task: $task,
            version: 1,
            status: 'live',
            docstring: $docstring,
            demos: $demos,
            accuracy: null,
            latency_ms: null,
            token_count: null,
            created_at: $created_at,
            promoted_at: $created_at,
            archived_at: null,
            parent_version: null,
            training_examples: 0
        })
        RETURN p.id as id
        """

        await graph.query(
            create_query,
            {
                'id': prompt_id,
                'task': task,
                'docstring': docstring,
                'demos': demos,
                'created_at': now,
            },
        )

        logger.info(f'Seeded {task} v1 (id={prompt_id[:8]}..., status=live)')


async def verify_schema(client) -> bool:
    """Verify the schema was created correctly."""
    graph = client.select_graph(PROMPT_DATABASE)

    # Check for any PromptVersion nodes
    result = await graph.query('MATCH (p:PromptVersion) RETURN count(p) as count')
    count = result.result_set[0][0] if result.result_set else 0

    # Check indexes exist
    try:
        index_result = await graph.query('CALL db.indexes()')
        index_count = len(index_result.result_set) if result.result_set else 0
    except Exception:
        index_count = 'unknown'

    logger.info(f'Schema verification: {count} PromptVersion nodes, {index_count} indexes')
    return True


async def main():
    parser = argparse.ArgumentParser(description='Initialize FalkorDB prompt storage schema')
    parser.add_argument(
        '--seed', action='store_true', help='Seed initial prompts from current signatures'
    )
    parser.add_argument(
        '--host', default=os.getenv('FALKORDB_HOST', 'localhost'), help='FalkorDB host'
    )
    parser.add_argument(
        '--port', type=int, default=int(os.getenv('FALKORDB_PORT', '6379')), help='FalkorDB port'
    )
    args = parser.parse_args()

    try:
        from falkordb.asyncio import FalkorDB
    except ImportError:
        logger.error('falkordb package not installed. Run: pip install falkordb')
        sys.exit(1)

    logger.info(f'Connecting to FalkorDB at {args.host}:{args.port}')
    client = FalkorDB(host=args.host, port=args.port)

    try:
        # Create schema
        logger.info(f'Creating schema in database: {PROMPT_DATABASE}')
        await create_schema(client)

        # Optionally seed initial prompts
        if args.seed:
            logger.info('Seeding initial prompts from current signatures...')
            await seed_initial_prompts(client)

        # Verify
        await verify_schema(client)

        logger.info('Schema initialization complete!')

    finally:
        # FalkorDB async client doesn't have a close method - connection is managed internally
        pass


if __name__ == '__main__':
    asyncio.run(main())
