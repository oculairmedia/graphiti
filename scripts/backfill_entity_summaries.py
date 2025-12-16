#!/usr/bin/env python3
"""
Backfill summaries for entities that have empty or missing summaries.

This script:
1. Queries FalkorDB for entities with empty/null summaries
2. For each entity, fetches related episodes for context
3. Calls the LLM to generate a summary
4. Updates the entity in FalkorDB

Usage:
    python scripts/backfill_entity_summaries.py [--limit N] [--group-id GROUP_ID] [--dry-run]
"""

import asyncio
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pydantic import BaseModel, Field, create_model
from typing import Any
from uuid import uuid4

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from falkordb import FalkorDB

from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.llm_client.config import LLMConfig, ModelSize
from graphiti_core.prompts import extract_nodes as prompt_library

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_falkordb_client():
    """Get FalkorDB client."""
    host = os.getenv('FALKORDB_HOST', 'localhost')
    port = int(os.getenv('FALKORDB_PORT', '6379'))
    database = os.getenv('FALKORDB_DATABASE', 'graphiti_migration')

    client = FalkorDB(host=host, port=port)
    graph = client.select_graph(database)
    return graph


def get_entities_without_summaries(
    graph, limit: int | None = None, group_id: str | None = None
) -> list[dict]:
    """Get entities that have empty or null summaries."""
    where_clause = "WHERE e.summary IS NULL OR e.summary = ''"
    if group_id:
        where_clause += f" AND e.group_id = '{group_id}'"

    limit_clause = f'LIMIT {limit}' if limit else ''

    query = f"""
        MATCH (e:Entity)
        {where_clause}
        RETURN e.uuid AS uuid, e.name AS name, e.group_id AS group_id, 
               e.summary AS summary, labels(e) AS labels
        ORDER BY e.created_at DESC
        {limit_clause}
    """

    result = graph.query(query)
    entities = []
    for row in result.result_set:
        entities.append(
            {
                'uuid': row[0],
                'name': row[1],
                'group_id': row[2],
                'summary': row[3] or '',
                'labels': row[4] if row[4] else ['Entity'],
            }
        )

    return entities


def get_entity_context(graph, entity_uuid: str) -> tuple[str, list[str]]:
    """Get episode context for an entity."""
    # Get episodes that mention this entity
    query = """
        MATCH (e:Entity {uuid: $uuid})<-[:MENTIONS]-(ep:Episodic)
        RETURN ep.content AS content
        ORDER BY ep.valid_at DESC
        LIMIT 5
    """

    result = graph.query(query, params={'uuid': entity_uuid})

    if not result.result_set:
        # No episodes - try getting related edges for context
        edge_query = """
            MATCH (e:Entity {uuid: $uuid})-[r:RELATES_TO]-(other:Entity)
            RETURN r.fact AS fact
            LIMIT 10
        """
        edge_result = graph.query(edge_query, params={'uuid': entity_uuid})
        if edge_result.result_set:
            facts = [row[0] for row in edge_result.result_set if row[0]]
            return ' '.join(facts), []
        return '', []

    episodes = [row[0] for row in result.result_set if row[0]]
    if not episodes:
        return '', []

    # First episode is current context, rest are previous
    return episodes[0], episodes[1:]


def update_entity_summary(graph, entity_uuid: str, summary: str):
    """Update entity summary in FalkorDB."""
    query = """
        MATCH (e:Entity {uuid: $uuid})
        SET e.summary = $summary
        RETURN e.uuid
    """
    graph.query(query, params={'uuid': entity_uuid, 'summary': summary})


async def generate_summary(
    llm_client: OpenAIGenericClient,
    entity: dict,
    episode_content: str,
    previous_episodes: list[str],
) -> str | None:
    """Generate summary for an entity using the LLM."""
    node_context = {
        'name': entity['name'],
        'summary': entity['summary'],
        'entity_types': entity['labels'],
        'attributes': {},
    }

    summary_context = {
        'node': node_context,
        'episode_content': episode_content,
        'previous_episodes': previous_episodes,
    }

    # Create response model
    attributes_definitions: dict[str, Any] = {
        'summary': (
            str,
            Field(
                description='Summary containing the important information about the entity. Under 250 words'
            ),
        )
    }
    entity_attributes_model = create_model(
        f'EntityAttributes_{uuid4().hex}', **attributes_definitions
    )

    try:
        messages = prompt_library.extract_attributes(summary_context)
        response = await llm_client.generate_response(
            messages,
            response_model=entity_attributes_model,
            model_size=ModelSize.small,
        )

        if 'summary' in response:
            return response['summary']
        else:
            logger.warning(
                f"No 'summary' key in response for {entity['name']}: {list(response.keys())}"
            )
            return None
    except Exception as e:
        logger.error(f'Error generating summary for {entity["name"]}: {e}')
        return None


async def backfill_summaries(
    limit: int | None = None,
    group_id: str | None = None,
    dry_run: bool = False,
    batch_size: int = 10,
):
    """Main backfill function."""
    # Initialize FalkorDB
    graph = get_falkordb_client()

    # Initialize LLM client
    base_url = os.getenv('OLLAMA_BASE_URL', 'http://192.168.50.90:8082/v1')
    model = os.getenv('OLLAMA_MODEL', 'haiku-4-5')
    api_key = os.getenv('OLLAMA_API_KEY', 'ollama')

    logger.info(f'LLM: {base_url} / {model}')

    config = LLMConfig(api_key=api_key, base_url=base_url, model=model, temperature=0.7)
    llm_client = OpenAIGenericClient(config)

    # Get entities without summaries
    logger.info('Fetching entities without summaries...')
    entities = get_entities_without_summaries(graph, limit=limit, group_id=group_id)
    logger.info(f'Found {len(entities)} entities without summaries')

    if not entities:
        logger.info('No entities to process')
        return

    # Process in batches
    success_count = 0
    fail_count = 0
    skip_count = 0

    for i, entity in enumerate(entities):
        logger.info(
            f'[{i + 1}/{len(entities)}] Processing: {entity["name"]} ({entity["uuid"][:8]}...)'
        )

        # Get context
        episode_content, previous_episodes = get_entity_context(graph, entity['uuid'])

        if not episode_content and not previous_episodes:
            logger.warning(f'  No context found for {entity["name"]}, skipping')
            skip_count += 1
            continue

        # Generate summary
        summary = await generate_summary(llm_client, entity, episode_content, previous_episodes)

        if summary:
            logger.info(f'  Generated summary: {summary[:100]}...')

            if dry_run:
                logger.info('  [DRY RUN] Would update entity')
            else:
                update_entity_summary(graph, entity['uuid'], summary)
                logger.info('  Updated entity in FalkorDB')

            success_count += 1
        else:
            fail_count += 1

        # Small delay to avoid rate limiting
        if (i + 1) % batch_size == 0:
            logger.info(f'Processed {i + 1}/{len(entities)} entities, sleeping 1s...')
            await asyncio.sleep(1)

    logger.info(f'\n=== Backfill Complete ===')
    logger.info(f'Success: {success_count}')
    logger.info(f'Failed: {fail_count}')
    logger.info(f'Skipped (no context): {skip_count}')
    logger.info(f'Total: {len(entities)}')


def main():
    parser = argparse.ArgumentParser(description='Backfill entity summaries')
    parser.add_argument(
        '--limit', type=int, default=None, help='Limit number of entities to process'
    )
    parser.add_argument(
        '--group-id', type=str, default=None, help='Only process entities in this group'
    )
    parser.add_argument('--dry-run', action='store_true', help="Don't actually update entities")
    parser.add_argument('--batch-size', type=int, default=10, help='Batch size before sleeping')

    args = parser.parse_args()

    asyncio.run(
        backfill_summaries(
            limit=args.limit,
            group_id=args.group_id,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )
    )


if __name__ == '__main__':
    main()
