#!/usr/bin/env python3
"""
Working migration script that copies data from Neo4j to FalkorDB.
"""

import asyncio
import json
import re
from datetime import datetime

from falkordb import FalkorDB

from graphiti_core.driver.neo4j_driver import Neo4jDriver


def escape_string(value):
    """Escape string for Cypher query."""
    if value is None:
        return 'null'
    return str(value).replace("'", "\\'").replace('"', '\\"')


def format_value(value):
    """Format value for Cypher query."""
    if value is None:
        return 'null'
    elif isinstance(value, str):
        return f"'{escape_string(value)}'"
    elif isinstance(value, bool):
        return 'true' if value else 'false'
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, datetime):
        return f"'{value.isoformat()}'"
    elif isinstance(value, list):
        # For lists, convert to string representation
        return f"'{json.dumps(value)}'"
    else:
        return f"'{escape_string(str(value))}'"


async def migrate_data(neo4j_driver: Neo4jDriver, falkor_graph, limit: int = None):
    """Migrate data from Neo4j to FalkorDB."""
    print('\nFetching data from Neo4j...')

    # Build limit clause
    limit_clause = f' LIMIT {limit}' if limit else ''

    # Get nodes
    nodes_query = f'MATCH (n) RETURN n, labels(n) as labels{limit_clause}'
    nodes_result = await neo4j_driver.execute_query(nodes_query)
    nodes = nodes_result.records if nodes_result else []

    print(f'Found {len(nodes)} nodes to migrate')

    # Migrate nodes
    print('\nMigrating nodes to FalkorDB...')
    node_count = 0
    node_uuid_map = {}  # Track successfully migrated nodes

    for i, record in enumerate(nodes):
        try:
            node = record['n']
            labels = record['labels']

            # Skip if no labels
            if not labels:
                continue

            label = labels[0]  # Use first label

            # Build properties
            props = []
            node_uuid = None

            for key, value in node.items():
                if key == 'uuid':
                    node_uuid = value
                # Skip complex values that might cause issues
                if isinstance(value, (dict, list)) and key not in ['name', 'type', 'summary']:
                    continue
                formatted_value = format_value(value)
                props.append(f'{key}: {formatted_value}')

            if props:
                props_str = '{' + ', '.join(props) + '}'
                query = f'CREATE (n:{label} {props_str})'
            else:
                query = f'CREATE (n:{label})'

            falkor_graph.query(query)
            node_count += 1

            if node_uuid:
                node_uuid_map[node_uuid] = True

            if (i + 1) % 100 == 0:
                print(f'  Migrated {i + 1}/{len(nodes)} nodes...')

        except Exception as e:
            if 'Invalid input' not in str(e):  # Skip syntax errors
                print(f'  Error migrating node {i}: {e}')

    print(f'Successfully migrated {node_count} nodes')

    # Get relationships
    if node_uuid_map:
        print(f'\nFetching relationships...')

        # Get all relationships between migrated nodes
        rels_query = f"""
        MATCH (s)-[r]->(t) 
        WHERE s.uuid IS NOT NULL AND t.uuid IS NOT NULL
        RETURN s.uuid as source_uuid, t.uuid as target_uuid, type(r) as rel_type, properties(r) as props
        """

        if limit:
            rels_query += f' LIMIT {limit}'

        try:
            rels_result = await neo4j_driver.execute_query(rels_query)
            relationships = rels_result.records if rels_result else []

            print(f'Found {len(relationships)} relationships to migrate')

            # Migrate relationships
            print('Migrating relationships...')
            rel_count = 0

            for i, record in enumerate(relationships):
                try:
                    source_uuid = record['source_uuid']
                    target_uuid = record['target_uuid']
                    rel_type = record['rel_type']
                    props = record['props']

                    # Format properties for Cypher
                    if props:
                        prop_list = []
                        for key, value in props.items():
                            formatted_value = format_value(value)
                            prop_list.append(f"{key}: {formatted_value}")
                        prop_string = "{" + ", ".join(prop_list) + "}"
                    else:
                        prop_string = ""

                    # Relationship creation with properties
                    rel_query = f"""
                    MATCH (s {{uuid: '{source_uuid}'}}), (t {{uuid: '{target_uuid}'}})
                    CREATE (s)-[:{rel_type} {prop_string}]->(t)
                    """

                    falkor_graph.query(rel_query)
                    rel_count += 1

                    if (i + 1) % 50 == 0:
                        print(f'  Migrated {i + 1}/{len(relationships)} relationships...')

                except Exception as e:
                    if 'Invalid input' not in str(e):
                        print(f'  Error migrating relationship {i}: {e}')

            print(f'Successfully migrated {rel_count} relationships')

        except Exception as e:
            print(f'Error fetching relationships: {e}')

    return node_count


async def main():
    """Main migration function."""
    # Configuration
    neo4j_uri = 'bolt://localhost:7687'
    neo4j_user = 'neo4j'
    neo4j_password = 'demodemo'

    print('=== Neo4j to FalkorDB Migration ===')
    print(f'Source: Neo4j at {neo4j_uri}')
    print(f'Target: FalkorDB at localhost:6389')

    # Create Neo4j driver
    neo4j_driver = Neo4jDriver(uri=neo4j_uri, user=neo4j_user, password=neo4j_password)

    # Create FalkorDB connection
    falkor_db = FalkorDB(host='localhost', port=6379)
    falkor_graph = falkor_db.select_graph('graphiti_migration')

    try:
        # Check Neo4j connection
        count_result = await neo4j_driver.execute_query('MATCH (n) RETURN count(n) as count')
        total_nodes = (
            count_result.records[0]['count'] if count_result and count_result.records else 0
        )
        print(f'\nNeo4j has {total_nodes} total nodes')

        # Clear FalkorDB
        print('\nClearing FalkorDB...')
        try:
            falkor_graph.query('MATCH (n) DETACH DELETE n')
        except:
            pass  # Graph might not exist yet

        # Migrate all nodes
        print(f'\nMigrating all {total_nodes} nodes...')
        migrated = await migrate_data(neo4j_driver, falkor_graph)

        # Verify migration
        print('\nVerifying migration...')
        result = falkor_graph.query('MATCH (n) RETURN count(n) as count')
        falkor_nodes = result.result_set[0][0] if result.result_set else 0

        result = falkor_graph.query('MATCH ()-[r]->() RETURN count(r) as count')
        falkor_rels = result.result_set[0][0] if result.result_set else 0

        print(f'\nMigration Summary:')
        print(f'  FalkorDB now has {falkor_nodes} nodes')
        print(f'  FalkorDB now has {falkor_rels} relationships')

        # Show sample data
        print('\nSample nodes in FalkorDB:')
        result = falkor_graph.query('MATCH (n) RETURN n.name, labels(n) LIMIT 10')
        for row in result.result_set:
            if row[0]:  # If name exists
                print(f'  - {row[0]} ({row[1]})')

        print('\n✓ Migration completed!')
        print(f'\nYou can access FalkorDB UI at: http://localhost:3100')
        print(f"Select the 'graphiti_migration' graph to view the data")

    except Exception as e:
        print(f'\n✗ Error: {e}')
        import traceback

        traceback.print_exc()

    finally:
        await neo4j_driver.close()


if __name__ == '__main__':
    asyncio.run(main())
