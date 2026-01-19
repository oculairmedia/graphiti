#!/usr/bin/env python3
"""
Simple migration script that copies any existing data from Neo4j to FalkorDB
or creates test data if Neo4j is empty.
"""

import asyncio
import os

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.driver.neo4j_driver import Neo4jDriver


async def create_test_data_directly(neo4j_driver: Neo4jDriver):
    """Create test data directly in Neo4j without using LLM."""
    print('Creating test data in Neo4j...')

    # Create test entities
    entities = [
        {
            'name': 'Graph Databases',
            'type': 'Concept',
            'summary': 'Database systems that use graph structures',
        },
        {'name': 'Neo4j', 'type': 'Technology', 'summary': 'Popular graph database platform'},
        {'name': 'FalkorDB', 'type': 'Technology', 'summary': 'Redis-based graph database'},
        {
            'name': 'Knowledge Graphs',
            'type': 'Concept',
            'summary': 'Semantic networks of entities and relationships',
        },
        {
            'name': 'AI Systems',
            'type': 'Concept',
            'summary': 'Artificial intelligence applications',
        },
    ]

    for entity in entities:
        query = """
        CREATE (n:Entity {
            uuid: randomUUID(),
            name: $name,
            type: $type,
            summary: $summary,
            created_at: datetime(),
            group_id: 'test-migration'
        })
        RETURN n
        """
        await neo4j_driver.execute_query(query, parameters=entity)

    # Create relationships
    relationships = [
        ('Neo4j', 'Graph Databases', 'IMPLEMENTS'),
        ('FalkorDB', 'Graph Databases', 'IMPLEMENTS'),
        ('Knowledge Graphs', 'Graph Databases', 'USES'),
        ('AI Systems', 'Knowledge Graphs', 'UTILIZES'),
    ]

    for source, target, rel_type in relationships:
        query = f"""
        MATCH (s:Entity {{name: $source}})
        MATCH (t:Entity {{name: $target}})
        CREATE (s)-[r:RELATES_TO {{
            uuid: randomUUID(),
            type: $rel_type,
            fact: $source + ' ' + $rel_type + ' ' + $target,
            created_at: datetime(),
            group_id: 'test-migration'
        }}]->(t)
        RETURN r
        """
        params = {'source': source, 'target': target, 'rel_type': rel_type}
        await neo4j_driver.execute_query(query, parameters=params)

    print('Test data created successfully!')


async def migrate_data(neo4j_driver: Neo4jDriver, falkor_driver: FalkorDriver):
    """Migrate all data from Neo4j to FalkorDB."""
    print('\nFetching data from Neo4j...')

    # Get all nodes
    nodes_query = 'MATCH (n) RETURN n, labels(n) as labels'
    nodes_result = await neo4j_driver.execute_query(nodes_query)
    nodes = nodes_result.records if nodes_result else []

    # Get all relationships
    rels_query = 'MATCH (s)-[r]->(t) RETURN s.uuid as source_uuid, r, t.uuid as target_uuid, type(r) as rel_type'
    rels_result = await neo4j_driver.execute_query(rels_query)
    relationships = rels_result.records if rels_result else []

    print(f'Found {len(nodes)} nodes and {len(relationships)} relationships')

    # Migrate nodes
    print('\nMigrating nodes to FalkorDB...')
    for node_data in nodes:
        node = node_data['n']
        labels = node_data['labels']

        # Build properties string
        props = []
        for key, value in node.items():
            if isinstance(value, str):
                props.append(f"{key}: '{value}'")
            else:
                props.append(f"{key}: '{value}'")

        label = labels[0] if labels else 'Node'
        props_str = '{' + ', '.join(props) + '}'

        query = f'CREATE (n:{label} {props_str})'
        await falkor_driver.execute_query(query)

    # Migrate relationships
    print('Migrating relationships to FalkorDB...')
    for rel_data in relationships:
        rel = rel_data['r']
        source_uuid = rel_data['source_uuid']
        target_uuid = rel_data['target_uuid']
        rel_type = rel_data['rel_type']

        # Build properties string
        props = []
        for key, value in rel.items():
            if isinstance(value, str):
                props.append(f"{key}: '{value}'")
            else:
                props.append(f"{key}: '{value}'")

        props_str = '{' + ', '.join(props) + '}'

        query = f"""
        MATCH (s {{uuid: '{source_uuid}'}})
        MATCH (t {{uuid: '{target_uuid}'}})
        CREATE (s)-[r:{rel_type} {props_str}]->(t)
        """
        await falkor_driver.execute_query(query)

    print('Migration completed!')


async def verify_migration(neo4j_driver: Neo4jDriver, falkor_driver: FalkorDriver):
    """Verify the migration was successful."""
    print('\nVerifying migration...')

    # Count nodes in both databases
    neo4j_nodes = await neo4j_driver.execute_query('MATCH (n) RETURN count(n) as count')
    falkor_nodes = await falkor_driver.execute_query('MATCH (n) RETURN count(n) as count')

    # Count relationships
    neo4j_rels = await neo4j_driver.execute_query('MATCH ()-[r]->() RETURN count(r) as count')
    falkor_rels = await falkor_driver.execute_query('MATCH ()-[r]->() RETURN count(r) as count')

    neo4j_node_count = neo4j_nodes.records[0]['count'] if neo4j_nodes and neo4j_nodes.records else 0
    falkor_node_count = (
        falkor_nodes.records[0]['count'] if falkor_nodes and falkor_nodes.records else 0
    )
    neo4j_rel_count = neo4j_rels.records[0]['count'] if neo4j_rels and neo4j_rels.records else 0
    falkor_rel_count = falkor_rels.records[0]['count'] if falkor_rels and falkor_rels.records else 0

    print(f'\nMigration Summary:')
    print(f'Nodes: Neo4j={neo4j_node_count}, FalkorDB={falkor_node_count}')
    print(f'Relationships: Neo4j={neo4j_rel_count}, FalkorDB={falkor_rel_count}')

    if neo4j_node_count == falkor_node_count and neo4j_rel_count == falkor_rel_count:
        print('✓ Migration successful!')
    else:
        print('✗ Migration mismatch detected')


async def main():
    """Main migration function."""
    # Neo4j configuration
    neo4j_uri = 'bolt://localhost:7687'
    neo4j_user = 'neo4j'
    neo4j_password = 'demodemo'

    # FalkorDB configuration
    falkor_host = 'localhost'
    falkor_port = 6379
    falkor_database = 'graphiti_migration'

    print('=== Neo4j to FalkorDB Migration ===')
    print(f'Source: Neo4j at {neo4j_uri}')
    print(f'Target: FalkorDB at {falkor_host}:{falkor_port}/{falkor_database}')

    # Create drivers
    neo4j_driver = Neo4jDriver(uri=neo4j_uri, user=neo4j_user, password=neo4j_password)

    falkor_driver = FalkorDriver(host=falkor_host, port=falkor_port, database=falkor_database)

    try:
        # Check if Neo4j has data
        count_result = await neo4j_driver.execute_query('MATCH (n) RETURN count(n) as count')
        node_count = 0
        if count_result and count_result.records:
            node_count = count_result.records[0]['count']

        if node_count == 0:
            print('\nNeo4j is empty. Creating test data...')
            await create_test_data_directly(neo4j_driver)
        else:
            print(f'\nNeo4j has {node_count} existing nodes')

        # Clear FalkorDB before migration
        print('\nClearing FalkorDB...')
        await falkor_driver.execute_query('MATCH (n) DETACH DELETE n')

        # Perform migration
        await migrate_data(neo4j_driver, falkor_driver)

        # Verify
        await verify_migration(neo4j_driver, falkor_driver)

        # Show sample data from FalkorDB
        print('\nSample data from FalkorDB:')
        sample_nodes = await falkor_driver.execute_query(
            'MATCH (n) RETURN n.name, labels(n) LIMIT 5'
        )
        for node in sample_nodes:
            print(f'  - {node["n.name"]} ({node["labels(n)"]})')

    except Exception as e:
        print(f'\n✗ Migration failed: {e}')
        import traceback

        traceback.print_exc()

    finally:
        await neo4j_driver.close()
        await falkor_driver.close()


if __name__ == '__main__':
    asyncio.run(main())
