#!/usr/bin/env python3
"""
Backfill summaries for entities that are missing them.

This script finds entities with empty summaries and generates summaries
using the LLM via extract_attributes_from_node().

Usage:
    python3 scripts/maintenance/backfill_entity_summaries.py --limit 100
    python3 scripts/maintenance/backfill_entity_summaries.py --dry-run
    python3 scripts/maintenance/backfill_entity_summaries.py --group-id claude_conversations --limit 50
"""

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def get_entities_without_summaries(driver, group_id: str | None, limit: int) -> list[dict]:
    group_filter = 'AND n.group_id = $group_id' if group_id else ''
    params: dict = {'limit': limit}
    if group_id:
        params['group_id'] = group_id

    records, _, _ = await driver.execute_query(
        f"""
        MATCH (n:Entity)
        WHERE (n.summary IS NULL OR n.summary = '') {group_filter}
        RETURN n.uuid AS uuid, n.name AS name, n.group_id AS group_id, 
               n.created_at AS created_at, labels(n) AS labels
        ORDER BY n.created_at DESC
        LIMIT $limit
        """,
        **params,
    )
    return [dict(r) for r in records]


async def get_recent_episode_for_entity(driver, entity_uuid: str, group_id: str):
    """Find a recent episode that mentions this entity."""
    from graphiti_core.nodes import EpisodicNode

    records, _, _ = await driver.execute_query(
        """
        MATCH (e:Episodic)-[:MENTIONS]->(n:Entity {uuid: $uuid})
        RETURN e.uuid AS uuid
        ORDER BY e.created_at DESC
        LIMIT 1
        """,
        uuid=entity_uuid,
    )

    if records:
        episodes = await EpisodicNode.get_by_uuids(driver, [records[0]['uuid']])
        return episodes[0] if episodes else None
    return None


async def backfill_summaries(
    group_id: str | None = None, limit: int = 100, dry_run: bool = False, batch_size: int = 10
):
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.client_factory import GraphitiClientFactory
    from graphiti_core.nodes import EntityNode
    from graphiti_core.utils.maintenance.node_operations import extract_attributes_from_node
    from graphiti_core.utils.datetime_utils import utc_now

    driver = FalkorDriver(
        host=os.getenv('FALKORDB_HOST', 'localhost'),
        port=int(os.getenv('FALKORDB_PORT', 6379)),
        database=os.getenv('FALKORDB_DATABASE', 'graphiti_migration'),
    )

    entities = await get_entities_without_summaries(driver, group_id, limit)

    logger.info(f'Found {len(entities)} entities without summaries')

    if not entities:
        logger.info('No entities need summaries')
        await driver.close()
        return

    if dry_run:
        logger.info('[DRY RUN] Would backfill summaries for:')
        for e in entities[:20]:
            logger.info(f'  - {e["name"]} ({e["group_id"]}) created {e["created_at"]}')
        if len(entities) > 20:
            logger.info(f'  ... and {len(entities) - 20} more')
        await driver.close()
        return

    llm_client = GraphitiClientFactory.create_llm_client()

    success_count = 0
    error_count = 0

    for i, entity_data in enumerate(entities):
        try:
            logger.info(f'[{i + 1}/{len(entities)}] Processing: {entity_data["name"]}')

            node = EntityNode(
                uuid=entity_data['uuid'],
                name=entity_data['name'],
                group_id=entity_data['group_id'],
                labels=entity_data.get('labels', ['Entity']),
                created_at=entity_data.get('created_at') or utc_now(),
                summary='',
            )

            episode = await get_recent_episode_for_entity(
                driver, entity_data['uuid'], entity_data['group_id']
            )

            updated_node = await extract_attributes_from_node(
                llm_client,
                node,
                episode=episode,
                previous_episodes=[],
                entity_type=None,
                group_id=entity_data['group_id'],
            )

            if updated_node.summary:
                await driver.execute_query(
                    """
                    MATCH (n:Entity {uuid: $uuid})
                    SET n.summary = $summary
                    """,
                    uuid=entity_data['uuid'],
                    summary=updated_node.summary,
                )
                logger.info(f'  Summary generated: {updated_node.summary[:80]}...')
                success_count += 1
            else:
                logger.warning(f'  No summary generated for {entity_data["name"]}')
                error_count += 1

        except Exception as e:
            logger.error(f'  Error processing {entity_data["name"]}: {e}')
            error_count += 1

        if (i + 1) % batch_size == 0:
            logger.info(
                f'Progress: {i + 1}/{len(entities)} ({success_count} success, {error_count} errors)'
            )

    logger.info(f'\nBackfill complete: {success_count} success, {error_count} errors')
    await driver.close()


def main():
    parser = argparse.ArgumentParser(description='Backfill entity summaries')
    parser.add_argument('--group-id', help='Only process entities in this group')
    parser.add_argument('--limit', type=int, default=100, help='Max entities to process')
    parser.add_argument(
        '--batch-size', type=int, default=10, help='Batch size for progress logging'
    )
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')

    args = parser.parse_args()

    asyncio.run(
        backfill_summaries(
            group_id=args.group_id,
            limit=args.limit,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )
    )


if __name__ == '__main__':
    main()
