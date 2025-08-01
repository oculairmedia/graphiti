#!/usr/bin/env python3
"""
Run deduplication maintenance on the Graphiti knowledge graph.
This script identifies and resolves duplicate nodes.
"""

import asyncio
import os
from datetime import datetime
from uuid import uuid4

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.nodes import EntityNode, EpisodicNode
from graphiti_core.search.search import search
from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_RRF
from graphiti_core.search.search_filters import SearchFilters
from graphiti_core.utils.datetime_utils import utc_now
from graphiti_core.utils.maintenance.edge_operations import build_duplicate_of_edges


async def find_potential_duplicates(graphiti: Graphiti, group_id: str = None):
    """Find potential duplicate nodes using similarity search"""

    print('=== DEDUPLICATION MAINTENANCE ===')
    print(f'Started at: {datetime.now()}')

    # Get all entity nodes
    query = (
        """
    MATCH (n:Entity)
    """
        + (f"WHERE n.group_id = '{group_id}'" if group_id else '')
        + """
    RETURN n.uuid as uuid, n.name as name, n.group_id as group_id, n.labels as labels
    ORDER BY n.name
    """
    )

    records, _, _ = await graphiti.driver.execute_query(query)
    print(f'Found {len(records)} entity nodes to check')

    duplicates_found = []
    checked_pairs = set()

    # For each node, search for similar nodes
    for i, record in enumerate(records):
        node_uuid = record['uuid']
        node_name = record['name']
        node_group_id = record['group_id']

        if i % 10 == 0:
            print(f'Progress: {i}/{len(records)} nodes checked...')

        # Search for similar nodes
        search_results = await search(
            graphiti.driver,
            graphiti.embedder,
            query=node_name,
            group_ids=[node_group_id] if node_group_id else None,
            search_type='entity',
            search_filter=SearchFilters(),
            config=NODE_HYBRID_SEARCH_RRF,
            k=5,  # Get top 5 similar nodes
        )

        # Check if any results are potential duplicates
        for similar_node in search_results.nodes:
            if similar_node.uuid == node_uuid:
                continue  # Skip self

            # Create a sorted pair to avoid checking both directions
            pair = tuple(sorted([node_uuid, similar_node.uuid]))
            if pair in checked_pairs:
                continue
            checked_pairs.add(pair)

            # Check if names are very similar (you can adjust the threshold)
            if (
                similar_node.name.lower() == node_name.lower()
                or similar_node.name.lower() in node_name.lower()
                or node_name.lower() in similar_node.name.lower()
            ):
                duplicates_found.append(
                    {
                        'node1_uuid': node_uuid,
                        'node1_name': node_name,
                        'node2_uuid': similar_node.uuid,
                        'node2_name': similar_node.name,
                        'score': search_results.metadata.get('scores', {}).get(
                            similar_node.uuid, 0
                        ),
                    }
                )

    print(f'\nFound {len(duplicates_found)} potential duplicate pairs')
    return duplicates_found


async def resolve_duplicates(graphiti: Graphiti, duplicates):
    """Create IS_DUPLICATE_OF edges for confirmed duplicates"""

    if not duplicates:
        print('No duplicates to resolve')
        return

    print('\nResolving duplicates...')

    # Group duplicates by node to avoid creating multiple edges
    node_duplicates = {}
    for dup in duplicates:
        node1_uuid = dup['node1_uuid']
        node2_uuid = dup['node2_uuid']

        # Always use the lexicographically first UUID as the primary
        if node1_uuid < node2_uuid:
            primary, duplicate = node1_uuid, node2_uuid
        else:
            primary, duplicate = node2_uuid, node1_uuid

        if primary not in node_duplicates:
            node_duplicates[primary] = []
        node_duplicates[primary].append(duplicate)

    # Create IS_DUPLICATE_OF edges
    edges_created = 0
    now = utc_now()

    for primary_uuid, duplicate_uuids in node_duplicates.items():
        # Get the nodes
        primary_node = await EntityNode.get_by_uuid(graphiti.driver, primary_uuid)

        for dup_uuid in duplicate_uuids:
            dup_node = await EntityNode.get_by_uuid(graphiti.driver, dup_uuid)

            if primary_node and dup_node:
                # Check if edge already exists
                existing_check = await graphiti.driver.execute_query(
                    """
                    MATCH (n1:Entity {uuid: $uuid1})-[r:IS_DUPLICATE_OF]-(n2:Entity {uuid: $uuid2})
                    RETURN r
                    """,
                    uuid1=primary_uuid,
                    uuid2=dup_uuid,
                )

                if not existing_check[0]:  # No existing edge
                    # Create the edge
                    duplicate_edges = build_duplicate_of_edges(
                        EpisodicNode(
                            name='Deduplication Maintenance',
                            uuid=str(uuid4()),
                            group_id=primary_node.group_id,
                        ),
                        now,
                        [(dup_node, primary_node)],
                    )

                    for edge in duplicate_edges:
                        await edge.save(graphiti.driver)
                        edges_created += 1
                        print(f'Created edge: {dup_node.name} IS_DUPLICATE_OF {primary_node.name}')

    print(f'\nCreated {edges_created} IS_DUPLICATE_OF edges')


async def main():
    # Initialize Graphiti with FalkorDB
    print('Initializing Graphiti...')

    # Use environment variables or defaults
    falkordb_host = os.getenv('FALKORDB_HOST', 'localhost')
    falkordb_port = int(os.getenv('FALKORDB_PORT', 6389))

    driver = FalkorDriver(host=falkordb_host, port=falkordb_port, database='graphiti_migration')

    graphiti = Graphiti(graph_driver=driver)
    await graphiti.initialize()

    # Find duplicates
    duplicates = await find_potential_duplicates(graphiti)

    # Show duplicates found
    if duplicates:
        print('\nPotential duplicates found:')
        for i, dup in enumerate(duplicates[:20]):  # Show first 20
            print(
                f"{i + 1}. '{dup['node1_name']}' <-> '{dup['node2_name']}' (score: {dup['score']:.3f})"
            )

        if len(duplicates) > 20:
            print(f'... and {len(duplicates) - 20} more')

        # Ask for confirmation
        response = input('\nDo you want to create IS_DUPLICATE_OF edges for these? (y/n): ')
        if response.lower() == 'y':
            await resolve_duplicates(graphiti, duplicates)

    print('\nDeduplication maintenance completed!')


if __name__ == '__main__':
    asyncio.run(main())
