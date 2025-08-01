#!/usr/bin/env python3
"""
Limited migration script that copies a subset of data from Neo4j to FalkorDB.
"""

import asyncio
import json

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.driver.neo4j_driver import Neo4jDriver


async def migrate_subset(neo4j_driver: Neo4jDriver, falkor_driver: FalkorDriver, limit: int = 100):
    """Migrate a limited subset of data from Neo4j to FalkorDB."""
    print(f'\nMigrating up to {limit} nodes and their relationships...')

    # Get limited nodes
    nodes_query = f'MATCH (n) RETURN n, labels(n) as labels LIMIT {limit}'
    nodes_result = await neo4j_driver.execute_query(nodes_query)
    nodes = nodes_result.records if nodes_result else []

    print(f'Fetched {len(nodes)} nodes')

    # Track node UUIDs for relationship query
    node_uuids = []

    # Migrate nodes
    print('Migrating nodes to FalkorDB...')
    for i, node_data in enumerate(nodes):
        try:
            node = node_data['n']
            labels = node_data['labels']

            # Track UUID
            if 'uuid' in node:
                node_uuids.append(node['uuid'])

            # Use parameterized query
            label = labels[0] if labels else 'Node'

            # Create node with parameters
            create_query = f'CREATE (n:{label} $props)'
            await falkor_driver.execute_query(create_query, params={'props': dict(node)})

            if i % 10 == 0:
                print(f'  Migrated {i}/{len(nodes)} nodes...')

        except Exception as e:
            print(f'  Error migrating node {i}: {e}')
            # Try simpler approach
            try:
                simple_query = f"CREATE (n:{label} {{uuid: '{node.get('uuid', 'unknown')}', name: '{node.get('name', 'unnamed')}'}})"
                await falkor_driver.execute_query(simple_query)
            except Exception as e2:
                print(f'  Fallback also failed: {e2}')

    print(f'Completed node migration')

    # Get relationships only between migrated nodes
    if node_uuids:
        print(f'\nFetching relationships between {len(node_uuids)} nodes...')

        # Create UUID list for query
        uuid_list = "', '".join(node_uuids[:50])  # Limit to first 50 to avoid query too long

        rels_query = f"""
        MATCH (s)-[r]->(t) 
        WHERE s.uuid IN ['{uuid_list}'] AND t.uuid IN ['{uuid_list}']
        RETURN s.uuid as source_uuid, t.uuid as target_uuid, type(r) as rel_type, r
        LIMIT 100
        """

        rels_result = await neo4j_driver.execute_query(rels_query)
        relationships = rels_result.records if rels_result else []

        print(f'Found {len(relationships)} relationships to migrate')

        # Migrate relationships
        print('Migrating relationships...')
        for i, rel_data in enumerate(relationships):
            try:
                source_uuid = rel_data['source_uuid']
                target_uuid = rel_data['target_uuid']
                rel_type = rel_data['rel_type']

                # Simple relationship creation
                rel_query = f"""
                MATCH (s {{uuid: '{source_uuid}'}})
                MATCH (t {{uuid: '{target_uuid}'}})
                CREATE (s)-[r:{rel_type}]->(t)
                """

                await falkor_driver.execute_query(rel_query)

                if i % 10 == 0:
                    print(f'  Migrated {i}/{len(relationships)} relationships...')

            except Exception as e:
                print(f'  Error migrating relationship {i}: {e}')

    print('Migration subset completed!')


async def verify_migration(falkor_driver: FalkorDriver):
    """Verify what was migrated to FalkorDB."""
    print('\nVerifying FalkorDB contents...')

    # Count nodes
    nodes_result = await falkor_driver.execute_query('MATCH (n) RETURN count(n) as count')
    node_count = nodes_result.records[0]['count'] if nodes_result and nodes_result.records else 0

    # Count relationships
    rels_result = await falkor_driver.execute_query('MATCH ()-[r]->() RETURN count(r) as count')
    rel_count = rels_result.records[0]['count'] if rels_result and rels_result.records else 0

    print(f'FalkorDB now has:')
    print(f'  - {node_count} nodes')
    print(f'  - {rel_count} relationships')

    # Show sample nodes
    print('\nSample nodes:')
    sample_result = await falkor_driver.execute_query('MATCH (n) RETURN n.name, labels(n) LIMIT 5')
    if sample_result and sample_result.records:
        for record in sample_result.records:
            name = record.get('n.name', 'unnamed')
            labels = record.get('labels(n)', ['Unknown'])
            print(f'  - {name} ({labels})')


async def main():
    """Main migration function."""
    # Configuration
    neo4j_uri = 'bolt://localhost:7687'
    neo4j_user = 'neo4j'
    neo4j_password = 'demodemo'

    falkor_host = 'localhost'
    falkor_port = 6379
    falkor_database = 'graphiti_test'  # Use different database

    print('=== Limited Neo4j to FalkorDB Migration ===')
    print(f'Source: Neo4j at {neo4j_uri}')
    print(f'Target: FalkorDB at {falkor_host}:{falkor_port}/{falkor_database}')

    # Create drivers
    neo4j_driver = Neo4jDriver(uri=neo4j_uri, user=neo4j_user, password=neo4j_password)

    falkor_driver = FalkorDriver(host=falkor_host, port=falkor_port, database=falkor_database)

    try:
        # Clear FalkorDB
        print('\nClearing FalkorDB...')
        try:
            await falkor_driver.execute_query('MATCH (n) DETACH DELETE n')
        except:
            pass  # Database might not exist yet

        # Migrate subset
        await migrate_subset(neo4j_driver, falkor_driver, limit=50)

        # Verify
        await verify_migration(falkor_driver)

    except Exception as e:
        print(f'\n✗ Error: {e}')
        import traceback

        traceback.print_exc()

    finally:
        await neo4j_driver.close()
        await falkor_driver.close()


if __name__ == '__main__':
    asyncio.run(main())
