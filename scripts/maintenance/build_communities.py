#!/usr/bin/env python3
"""
Build community nodes for Graphiti knowledge graph.

Communities are clusters of related entities that get summarized by LLM.
This enables GraphRAG-style global search queries.

Usage:
    python3 scripts/maintenance/build_communities.py                    # Build for all group_ids
    python3 scripts/maintenance/build_communities.py --group-ids claude_conversations huly-graph
    python3 scripts/maintenance/build_communities.py --top 5            # Build for top 5 group_ids by entity count
    python3 scripts/maintenance/build_communities.py --dry-run          # Preview without building
"""

import argparse
import asyncio
import logging
import os
import sys
from typing import Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def get_group_id_stats(driver) -> list[tuple[str, int]]:
    """Get all group_ids with their entity counts."""
    records, _, _ = await driver.execute_query(
        """
        MATCH (n:Entity)
        WHERE n.group_id IS NOT NULL
        RETURN n.group_id AS group_id, count(n) AS count
        ORDER BY count DESC
        """
    )
    return [(r['group_id'], r['count']) for r in records]


async def get_community_count(driver) -> int:
    """Get current community count."""
    records, _, _ = await driver.execute_query('MATCH (c:Community) RETURN count(c) AS count')
    return records[0]['count'] if records else 0


async def build_communities(
    group_ids: Optional[list[str]] = None, top_n: Optional[int] = None, dry_run: bool = False
):
    """Build communities for specified group_ids."""
    from graphiti_core import Graphiti
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.llm_client import OpenAIClient, LLMConfig
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

    # Initialize driver
    driver = FalkorDriver(
        host=os.getenv('FALKORDB_HOST', 'localhost'),
        port=int(os.getenv('FALKORDB_PORT', 6379)),
        database=os.getenv('FALKORDB_DATABASE', 'graphiti_migration'),
    )

    # Get stats first
    stats = await get_group_id_stats(driver)
    current_communities = await get_community_count(driver)

    logger.info(f'Current community count: {current_communities}')
    logger.info(f'Found {len(stats)} group_ids with entities:')
    for gid, count in stats[:10]:
        logger.info(f'  {gid}: {count} entities')
    if len(stats) > 10:
        logger.info(f'  ... and {len(stats) - 10} more')

    # Determine which group_ids to process
    target_group_ids: list[str] | None = None

    if group_ids:
        target_group_ids = group_ids
    elif top_n:
        target_group_ids = [gid for gid, _ in stats[:top_n]]
    # else: None means all group_ids

    if target_group_ids:
        total_entities = sum(count for gid, count in stats if gid in target_group_ids)
        logger.info(
            f'\nWill build communities for {len(target_group_ids)} group_ids ({total_entities} entities):'
        )
        for gid in target_group_ids:
            count = next((c for g, c in stats if g == gid), 0)
            logger.info(f'  - {gid}: {count} entities')
    else:
        total_entities = sum(count for _, count in stats)
        logger.info(
            f'\nWill build communities for ALL {len(stats)} group_ids ({total_entities} entities)'
        )

    if dry_run:
        logger.info('\n[DRY RUN] Would build communities. Exiting.')
        await driver.close()
        return

    # Initialize full Graphiti client
    llm_config = LLMConfig(
        api_key=os.getenv('OPENAI_API_KEY'),
        model=os.getenv('MODEL_NAME', 'gpt-4.1-mini'),
        small_model=os.getenv('SMALL_MODEL_NAME', 'gpt-4.1-nano'),
    )

    llm_client = OpenAIClient(config=llm_config)

    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            api_key=os.getenv('OPENAI_API_KEY'),
            embedding_model=os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small'),
        )
    )

    graphiti = Graphiti(
        graph_driver=driver,
        llm_client=llm_client,
        embedder=embedder,
    )

    logger.info('\nBuilding communities (this may take several minutes)...')

    try:
        community_nodes = await graphiti.build_communities(group_ids=target_group_ids)
        logger.info(f'\nSuccessfully built {len(community_nodes)} communities!')

        for node in community_nodes[:10]:
            logger.info(f'  - {node.name}: {node.summary[:100]}...')
        if len(community_nodes) > 10:
            logger.info(f'  ... and {len(community_nodes) - 10} more')

    except Exception as e:
        logger.error(f'Error building communities: {e}')
        raise
    finally:
        await driver.close()


def main():
    parser = argparse.ArgumentParser(description='Build community nodes for Graphiti')
    parser.add_argument(
        '--group-ids', nargs='+', help='Specific group_ids to build communities for'
    )
    parser.add_argument(
        '--top', type=int, help='Build communities for top N group_ids by entity count'
    )
    parser.add_argument('--dry-run', action='store_true', help='Preview without building')

    args = parser.parse_args()

    asyncio.run(build_communities(group_ids=args.group_ids, top_n=args.top, dry_run=args.dry_run))


if __name__ == '__main__':
    main()
