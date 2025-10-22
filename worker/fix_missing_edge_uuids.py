#!/usr/bin/env python3
"""
Fix edges missing UUID properties in FalkorDB.

This script finds all RELATES_TO edges that have null/missing uuid properties
and assigns them valid UUIDs to satisfy the mandatory constraint.
"""

import asyncio
import os
import sys
from uuid import uuid4

sys.path.insert(0, '/app')

from graphiti_core.driver import FalkorDriver


async def fix_missing_edge_uuids():
    """Find and fix all edges with missing UUIDs."""

    # Initialize FalkorDB driver
    driver = FalkorDriver(
        host=os.getenv('FALKORDB_HOST', 'localhost'),
        port=int(os.getenv('FALKORDB_PORT', '6379')),
        username=os.getenv('FALKORDB_USERNAME'),
        password=os.getenv('FALKORDB_PASSWORD'),
        database=os.getenv('FALKORDB_GRAPH_NAME', 'graphiti_migration'),
    )

    graph_name = driver._database
    print(f"🔍 Scanning for edges with missing UUIDs in graph '{graph_name}'...")

    # Find all RELATES_TO edges with null uuid
    find_query = """
    MATCH ()-[r:RELATES_TO]->()
    WHERE r.uuid IS NULL
    RETURN id(r) as edge_id, type(r) as rel_type
    LIMIT 10000
    """

    result_tuple = await driver.execute_query(find_query)
    results = result_tuple[0] if result_tuple and len(result_tuple) > 0 else []

    if not results:
        print('✅ No edges with missing UUIDs found!')
        return

    print(f'⚠️  Found {len(results)} RELATES_TO edges with missing UUIDs')

    # Fix edges in batch using a single query
    # Since we can't update by id(), we'll update all null-uuid edges at once
    print(f'🔧 Updating edges in batches...')

    batch_size = 1000
    total_fixed = 0

    while True:
        # Check how many remain
        count_query = """
        MATCH ()-[r:RELATES_TO]->()
        WHERE r.uuid IS NULL
        RETURN count(r) as null_count
        """

        count_result = await driver.execute_query(count_query)
        null_count = count_result[0][0].get('null_count') if count_result and count_result[0] else 0

        if null_count == 0:
            break

        print(f'  Remaining edges with null uuid: {null_count}')

        # Fix one batch
        # We need to do this carefully - match, set uuid, return to confirm
        batch_query = """
        MATCH (source)-[r:RELATES_TO]->(target)
        WHERE r.uuid IS NULL
        WITH r, source, target
        LIMIT $batch_size
        SET r.uuid = randomUUID()
        RETURN count(r) as updated
        """

        try:
            batch_result = await driver.execute_query(batch_query, batch_size=batch_size)
            updated = batch_result[0][0].get('updated') if batch_result and batch_result[0] else 0
            total_fixed += updated
            print(f'  ✓ Fixed {updated} edges (total: {total_fixed})')

            if updated == 0:
                # No more to update
                break

        except Exception as e:
            # randomUUID() might not exist, try with generated UUIDs
            print(f'  ℹ️  randomUUID() not available, using Python UUID generation')

            # Get batch of edges
            get_batch_query = """
            MATCH (source)-[r:RELATES_TO]->(target)
            WHERE r.uuid IS NULL
            RETURN source.uuid as source_uuid, target.uuid as target_uuid, r.name as edge_name
            LIMIT $batch_size
            """

            batch_edges = await driver.execute_query(get_batch_query, batch_size=batch_size)
            edge_list = batch_edges[0] if batch_edges and batch_edges[0] else []

            if not edge_list:
                break

            # Update each edge
            for edge_data in edge_list:
                source_uuid = edge_data.get('source_uuid')
                target_uuid = edge_data.get('target_uuid')
                edge_name = edge_data.get('edge_name', 'RELATES_TO')
                new_uuid = str(uuid4())

                update_query = """
                MATCH (source:Entity {uuid: $source_uuid})-[r:RELATES_TO {name: $edge_name}]->(target:Entity {uuid: $target_uuid})
                WHERE r.uuid IS NULL
                SET r.uuid = $new_uuid
                RETURN r
                LIMIT 1
                """

                try:
                    update_res = await driver.execute_query(
                        update_query,
                        source_uuid=source_uuid,
                        target_uuid=target_uuid,
                        edge_name=edge_name,
                        new_uuid=new_uuid,
                    )
                    if update_res and update_res[0]:
                        total_fixed += 1
                except Exception as update_err:
                    print(f'  ✗ Error updating edge {source_uuid}->{target_uuid}: {update_err}')

            print(f'  ✓ Fixed batch (total: {total_fixed})')

    print(f'\n📊 Summary:')
    print(f'  • Successfully fixed: {total_fixed} edges')

    # Verify fix
    verify_query = """
    MATCH ()-[r:RELATES_TO]->()
    WHERE r.uuid IS NULL
    RETURN count(r) as remaining_null
    """

    verify_result = await driver.execute_query(verify_query)
    remaining = (
        verify_result[0][0].get('remaining_null') if verify_result and verify_result[0] else 0
    )

    if remaining == 0:
        print(f'\n✅ All RELATES_TO edges now have UUIDs!')
    else:
        print(f'\n⚠️  Still {remaining} edges with missing UUIDs - run again')


if __name__ == '__main__':
    asyncio.run(fix_missing_edge_uuids())
