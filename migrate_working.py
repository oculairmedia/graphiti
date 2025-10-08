#!/usr/bin/env python3
"""
Working migration script that copies data from Neo4j to FalkorDB.
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from falkordb import FalkorDB

from graphiti_core.driver.neo4j_driver import Neo4jDriver

# Configuration for migration behavior
CONFIG = {
    'max_query_length': 10000,  # Maximum Cypher query length for FalkorDB
    'embedding_properties': ['name_embedding', 'summary_embedding', 'embedding', 'embeddings'],
    'skip_large_arrays': True,  # Skip properties with large arrays (>100 elements)
    'max_array_size': 100,  # Maximum array size to include
    'retry_attempts': 3,  # Number of retry attempts for failed operations
    'batch_progress_interval': 50,  # Progress reporting interval
}


def escape_string(value: str) -> str:
    """Enhanced string escaping for Cypher queries."""
    if value is None:
        return 'null'
    
    # Convert to string and handle various escape sequences
    value_str = str(value)
    
    # Escape backslashes first to prevent double escaping
    value_str = value_str.replace('\\', '\\\\')
    
    # Escape quotes
    value_str = value_str.replace("'", "\\'")
    value_str = value_str.replace('"', '\\"')
    
    # Escape newlines and other control characters
    value_str = value_str.replace('\n', '\\n')
    value_str = value_str.replace('\r', '\\r')
    value_str = value_str.replace('\t', '\\t')
    
    # Handle Unicode and special characters
    try:
        # Ensure the string is properly encoded
        value_str.encode('utf-8')
    except UnicodeEncodeError:
        # Replace problematic characters
        value_str = value_str.encode('utf-8', errors='replace').decode('utf-8')
    
    return value_str


def should_skip_property(key: str, value: Any) -> bool:
    """Determine if a property should be skipped during migration."""
    # Skip known problematic embedding properties
    if key.lower() in CONFIG['embedding_properties']:
        return True
    
    # Skip large arrays that might cause query length issues
    if isinstance(value, list) and CONFIG['skip_large_arrays']:
        if len(value) > CONFIG['max_array_size']:
            return True
        
        # Check if array contains large objects or deeply nested data
        try:
            serialized = json.dumps(value)
            if len(serialized) > 1000:  # Skip if JSON representation is too large
                return True
        except (TypeError, ValueError):
            # Skip if not JSON serializable
            return True
    
    # Skip complex nested dictionaries
    if isinstance(value, dict) and key not in ['name', 'type', 'summary']:
        try:
            serialized = json.dumps(value)
            if len(serialized) > 500:  # Skip large nested objects
                return True
        except (TypeError, ValueError):
            return True
    
    return False


def format_value(value: Any) -> str:
    """Format value for Cypher query with improved handling."""
    if value is None:
        return 'null'
    elif isinstance(value, str):
        return f"'{escape_string(value)}'"
    elif isinstance(value, bool):
        return 'true' if value else 'false'
    elif isinstance(value, (int, float)):
        # Handle special float values
        if isinstance(value, float):
            if value != value:  # NaN check
                return 'null'
            elif value == float('inf'):
                return '999999999'  # Large number representation
            elif value == float('-inf'):
                return '-999999999'  # Large negative number
        return str(value)
    elif isinstance(value, datetime):
        return f"'{value.isoformat()}'"
    elif hasattr(value, 'to_native'):
        # Handle Neo4j DateTime objects
        try:
            native_dt = value.to_native()
            return f"'{native_dt.strftime('%Y-%m-%dT%H:%M:%S')}'"
        except:
            return f"'{str(value).split('.')[0].replace('+00:00', '').replace('Z', '')}'"
    elif isinstance(value, list):
        # Only include small lists
        if len(value) <= CONFIG['max_array_size']:
            try:
                json_str = json.dumps(value, default=str)
                if len(json_str) <= 500:  # Reasonable size limit
                    return f"'{escape_string(json_str)}'"
            except:
                pass
        return f"'[{len(value)} items]'"  # Placeholder for large lists
    else:
        return f"'{escape_string(str(value))}'"


def estimate_query_length(query: str) -> int:
    """Estimate the length of a Cypher query."""
    return len(query.encode('utf-8'))


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

            # Build properties with smart filtering
            props = []
            node_uuid = None
            skipped_properties = []

            for key, value in node.items():
                if key == 'uuid':
                    node_uuid = value
                
                # Apply smart property filtering
                if should_skip_property(key, value):
                    skipped_properties.append(key)
                    continue
                
                try:
                    formatted_value = format_value(value)
                    props.append(f'{key}: {formatted_value}')
                except Exception as e:
                    print(f'    Warning: Failed to format property {key}: {e}')
                    skipped_properties.append(key)
            
            if skipped_properties:
                print(f'    Skipped properties for node {node_uuid}: {skipped_properties}')

            # Build and execute query with retry logic
            success = False
            for attempt in range(CONFIG['retry_attempts']):
                try:
                    if props:
                        props_str = '{' + ', '.join(props) + '}'
                        query = f'CREATE (n:{label} {props_str})'
                    else:
                        query = f'CREATE (n:{label})'
                    
                    # Check query length
                    if estimate_query_length(query) > CONFIG['max_query_length']:
                        print(f'    Warning: Query too long for node {node_uuid}, simplifying...')
                        # Create simplified query with only essential properties
                        essential_props = []
                        for prop in props:
                            if any(key in prop for key in ['uuid:', 'name:', 'type:', 'group_id:']):
                                essential_props.append(prop)
                        if essential_props:
                            props_str = '{' + ', '.join(essential_props) + '}'
                            query = f'CREATE (n:{label} {props_str})'
                        else:
                            query = f'CREATE (n:{label})'
                    
                    falkor_graph.query(query)
                    node_count += 1
                    success = True
                    
                    if node_uuid:
                        node_uuid_map[node_uuid] = True
                    
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    if attempt == CONFIG['retry_attempts'] - 1:  # Last attempt
                        error_msg = str(e)
                        if 'Invalid input' not in error_msg and 'query with more than one statement' not in error_msg:
                            print(f'  Error migrating node {i} (uuid: {node_uuid}): {error_msg}')
                        break
                    else:
                        print(f'    Retry {attempt + 1} for node {node_uuid}: {e}')
                        await asyncio.sleep(0.1)  # Brief delay before retry
            
            if (i + 1) % CONFIG['batch_progress_interval'] == 0:
                print(f'  Migrated {i + 1}/{len(nodes)} nodes...')

        except Exception as e:
            print(f'  Unexpected error processing node {i}: {e}')

    success_rate = (node_count / len(nodes)) * 100 if nodes else 0
    print(f'Successfully migrated {node_count}/{len(nodes)} nodes ({success_rate:.1f}% success rate)')

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

                    # Format properties for Cypher with filtering
                    prop_list = []
                    if props:
                        for key, value in props.items():
                            if should_skip_property(key, value):
                                continue
                            try:
                                formatted_value = format_value(value)
                                prop_list.append(f"{key}: {formatted_value}")
                            except Exception as e:
                                print(f'    Warning: Failed to format relationship property {key}: {e}')
                    
                    prop_string = "{" + ", ".join(prop_list) + "}" if prop_list else ""

                    # Relationship creation with retry logic
                    success = False
                    for attempt in range(CONFIG['retry_attempts']):
                        try:
                            rel_query = f"""
                            MATCH (s {{uuid: '{escape_string(source_uuid)}'}}), (t {{uuid: '{escape_string(target_uuid)}'}}) 
                            CREATE (s)-[:{rel_type} {prop_string}]->(t)
                            """
                            
                            # Check query length
                            if estimate_query_length(rel_query) > CONFIG['max_query_length']:
                                # Simplify by removing properties
                                rel_query = f"""
                                MATCH (s {{uuid: '{escape_string(source_uuid)}'}}), (t {{uuid: '{escape_string(target_uuid)}'}}) 
                                CREATE (s)-[:{rel_type}]->(t)
                                """
                            
                            falkor_graph.query(rel_query)
                            rel_count += 1
                            success = True
                            break
                            
                        except Exception as e:
                            if attempt == CONFIG['retry_attempts'] - 1:
                                error_msg = str(e)
                                if 'Invalid input' not in error_msg:
                                    print(f'  Error migrating relationship {i} ({source_uuid} -> {target_uuid}): {error_msg}')
                                break
                            else:
                                await asyncio.sleep(0.1)

                    if (i + 1) % CONFIG['batch_progress_interval'] == 0:
                        print(f'  Migrated {i + 1}/{len(relationships)} relationships...')

                except Exception as e:
                    print(f'  Unexpected error processing relationship {i}: {e}')

            rel_success_rate = (rel_count / len(relationships)) * 100 if relationships else 0
            print(f'Successfully migrated {rel_count}/{len(relationships)} relationships ({rel_success_rate:.1f}% success rate)')

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
