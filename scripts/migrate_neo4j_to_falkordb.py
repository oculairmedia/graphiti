#!/usr/bin/env python3
"""
Script to migrate data from Neo4j to FalkorDB.

This script copies all nodes and edges from an existing Neo4j instance
to a FalkorDB instance, preserving all properties and relationships.
"""

import asyncio
import os
from datetime import datetime
from typing import Any, Dict, List

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.edges import EntityEdge, EpisodicEdge
from graphiti_core.nodes import EntityNode, EpisodicNode


async def fetch_all_neo4j_data(neo4j_driver: Neo4jDriver) -> Dict[str, Any]:
    """Fetch all nodes and relationships from Neo4j."""
    print('Fetching data from Neo4j...')

    # Fetch all entity nodes
    entity_nodes_query = """
    MATCH (n:Entity)
    RETURN n
    """
    entity_nodes = await neo4j_driver.execute_query(entity_nodes_query)

    # Fetch all episodic nodes
    episodic_nodes_query = """
    MATCH (n:Episodic)
    RETURN n
    """
    episodic_nodes = await neo4j_driver.execute_query(episodic_nodes_query)

    # Fetch all entity edges
    entity_edges_query = """
    MATCH (source)-[r:RELATES_TO]->(target)
    RETURN r, source.uuid as source_uuid, target.uuid as target_uuid
    """
    entity_edges = await neo4j_driver.execute_query(entity_edges_query)

    # Fetch all episodic edges
    episodic_edges_query = """
    MATCH (episode:Episodic)-[r:MENTIONS]->(entity:Entity)
    RETURN r, episode.uuid as episode_uuid, entity.uuid as entity_uuid
    """
    episodic_edges = await neo4j_driver.execute_query(episodic_edges_query)

    # Fetch community nodes if any
    community_nodes_query = """
    MATCH (n:Community)
    RETURN n
    """
    community_nodes = await neo4j_driver.execute_query(community_nodes_query)

    print(f"Found: {len(entity_nodes)} entity nodes, {len(episodic_nodes)} episodic nodes, {len(community_nodes)} community nodes")
    print(f"Found: {len(entity_edges)} entity edges, {len(episodic_edges)} episodic edges")

    return {
        'entity_nodes': entity_nodes,
        'episodic_nodes': episodic_nodes,
        'entity_edges': entity_edges,
        'episodic_edges': episodic_edges,
        'community_nodes': community_nodes,
    }


async def migrate_nodes(falkor_driver: FalkorDriver, nodes: List[Dict], node_type: str):
    """Migrate nodes to FalkorDB."""
    print(f'Migrating {len(nodes)} {node_type} nodes...')

    for node_item in nodes:
        # Handle different data structures - nodes seem to be in lists
        if isinstance(node_item, list) and len(node_item) > 0:
            # Get the first item from list, which should be a Record
            first_record = node_item[0]
            if hasattr(first_record, 'data'):
                record_data = first_record.data()
                if 'n' in record_data:
                    node = record_data['n']
                else:
                    continue
            elif hasattr(first_record, 'get'):
                node = first_record.get('n') or first_record
            else:
                node = first_record
        else:
            # Fallback for other structures
            if isinstance(node_item, dict) and 'n' in node_item:
                node = node_item['n']
            else:
                node = node_item
        
        # Convert Neo4j node to dict if needed
        if hasattr(node, '_properties'):
            properties = dict(node._properties)
        elif hasattr(node, 'keys') and callable(node.keys):
            properties = {k: node[k] for k in node.keys()}
        else:
            print(f"DEBUG: Node type: {type(node)}, Node: {node}")
            if isinstance(node, dict):
                properties = node
            else:
                print(f"Unexpected node structure: {node}")
                continue

        # Create node in FalkorDB - build query dynamically
        if not properties.get('uuid') or not properties.get('name'):
            print(f"Skipping node without uuid or name: {properties}")
            continue
            
        property_parts = []
        params = {}
        
        for key, value in properties.items():
            # Convert Neo4j datetime objects to strings
            if hasattr(value, 'to_native'):
                try:
                    native_dt = value.to_native()
                    value = native_dt.strftime('%Y-%m-%dT%H:%M:%S')
                except:
                    value = str(value)
            
            property_parts.append(f"{key}: ${key}")
            params[key] = value

        create_query = f"""
        CREATE (n:{node_type} {{{', '.join(property_parts)}}})
        RETURN n
        """

        try:
            await falkor_driver.execute_query(create_query, parameters=params)
        except Exception as e:
            print(f'Error creating node {node.get("uuid", "unknown")}: {e}')


async def migrate_edges(falkor_driver: FalkorDriver, edges: List[Dict], edge_type: str):
    """Migrate edges to FalkorDB."""
    print(f'Migrating {len(edges)} {edge_type} edges...')

    for edge_data in edges:
        # Handle different possible data structures  
        if isinstance(edge_data, dict) and 'r' in edge_data:
            edge = edge_data['r']
            source_uuid = edge_data.get('source_uuid') or edge_data.get('episode_uuid')
            target_uuid = edge_data.get('target_uuid') or edge_data.get('entity_uuid')
        else:
            # Fallback for different structure
            print(f"Unexpected edge data structure: {edge_data}")
            continue

        # Convert Neo4j relationship to dict if needed
        if hasattr(edge, '_properties'):
            properties = dict(edge._properties)
        elif hasattr(edge, 'keys') and callable(edge.keys):
            properties = {k: edge[k] for k in edge.keys()}
        else:
            properties = dict(edge)
            
        # Convert Neo4j datetime objects to strings
        for key, value in properties.items():
            if hasattr(value, 'to_native'):
                try:
                    native_dt = value.to_native()
                    properties[key] = native_dt.strftime('%Y-%m-%dT%H:%M:%S')
                except:
                    properties[key] = str(value)

        # Build edge properties
        property_parts = []
        params = {'source_uuid': source_uuid, 'target_uuid': target_uuid}
        
        for key, value in properties.items():
            property_parts.append(f"{key}: ${key}")
            params[key] = value

        # Create edge in FalkorDB
        create_query = f"""
        MATCH (source {{uuid: $source_uuid}})
        MATCH (target {{uuid: $target_uuid}})
        CREATE (source)-[r:{edge_type} {{{', '.join(property_parts)}}}]->(target)
        RETURN r
        """

        try:
            await falkor_driver.execute_query(create_query, parameters=params)
        except Exception as e:
            print(f'Error creating edge {edge.get("uuid", "unknown")}: {e}')


async def verify_migration(neo4j_driver: Neo4jDriver, falkor_driver: FalkorDriver):
    """Verify the migration was successful."""
    print('\nVerifying migration...')

    # Count nodes in Neo4j
    neo4j_counts = {}
    for label in ['Entity', 'Episodic', 'Community']:
        query = f'MATCH (n:{label}) RETURN count(n) as count'
        result = await neo4j_driver.execute_query(query)
        if isinstance(result, list) and len(result) > 0:
            if hasattr(result[0], 'data'):
                neo4j_counts[label] = result[0].data()['count'] if result[0].data() else 0
            elif isinstance(result[0], dict):
                neo4j_counts[label] = result[0]['count']
            else:
                neo4j_counts[label] = result[0]
        else:
            neo4j_counts[label] = 0

    # Count nodes in FalkorDB
    falkor_counts = {}
    for label in ['Entity', 'Episodic', 'Community']:
        query = f'MATCH (n:{label}) RETURN count(n) as count'
        result = await falkor_driver.execute_query(query)
        if isinstance(result, list) and len(result) > 0:
            if hasattr(result[0], 'data'):
                falkor_counts[label] = result[0].data()['count'] if result[0].data() else 0
            elif isinstance(result[0], dict):
                falkor_counts[label] = result[0]['count']
            else:
                falkor_counts[label] = result[0]
        else:
            falkor_counts[label] = 0

    # Count edges
    neo4j_edge_count = await neo4j_driver.execute_query('MATCH ()-[r]->() RETURN count(r) as count')
    falkor_edge_count = await falkor_driver.execute_query(
        'MATCH ()-[r]->() RETURN count(r) as count'
    )

    print('\nMigration Summary:')
    print(f'{"Node Type":<15} {"Neo4j":<10} {"FalkorDB":<10} {"Status"}')
    print('-' * 45)

    for label in ['Entity', 'Episodic', 'Community']:
        status = '✓' if neo4j_counts[label] == falkor_counts[label] else '✗'
        print(f'{label:<15} {neo4j_counts[label]:<10} {falkor_counts[label]:<10} {status}')

    # Handle edge counts
    if isinstance(neo4j_edge_count, list) and len(neo4j_edge_count) > 0:
        if hasattr(neo4j_edge_count[0], 'data'):
            neo4j_edges = neo4j_edge_count[0].data()['count'] if neo4j_edge_count[0].data() else 0
        elif isinstance(neo4j_edge_count[0], dict):
            neo4j_edges = neo4j_edge_count[0]['count']
        else:
            neo4j_edges = neo4j_edge_count[0]
    else:
        neo4j_edges = 0
        
    if isinstance(falkor_edge_count, list) and len(falkor_edge_count) > 0:
        if hasattr(falkor_edge_count[0], 'data'):
            falkor_edges = falkor_edge_count[0].data()['count'] if falkor_edge_count[0].data() else 0
        elif isinstance(falkor_edge_count[0], dict):
            falkor_edges = falkor_edge_count[0]['count']
        else:
            falkor_edges = falkor_edge_count[0]
    else:
        falkor_edges = 0
    status = '✓' if neo4j_edges == falkor_edges else '✗'
    print(f'{"Edges":<15} {neo4j_edges:<10} {falkor_edges:<10} {status}')


async def main():
    """Main migration function."""
    # Neo4j configuration
    neo4j_uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    neo4j_user = os.getenv('NEO4J_USER', 'neo4j')
    neo4j_password = os.getenv('NEO4J_PASSWORD', 'password')

    # FalkorDB configuration
    falkor_host = os.getenv('FALKORDB_HOST', 'localhost')
    falkor_port = int(os.getenv('FALKORDB_PORT', '6379'))
    falkor_database = os.getenv('FALKORDB_DATABASE', 'graphiti_migration')

    print('=== Neo4j to FalkorDB Migration ===')
    print(f'Source: Neo4j at {neo4j_uri}')
    print(f'Target: FalkorDB at {falkor_host}:{falkor_port}/{falkor_database}')

    # Create drivers
    neo4j_driver = Neo4jDriver(uri=neo4j_uri, user=neo4j_user, password=neo4j_password)

    falkor_driver = FalkorDriver(host=falkor_host, port=falkor_port, database=falkor_database)

    try:
        # Initialize FalkorDB indices
        print('\nInitializing FalkorDB indices...')
        graphiti_falkor = Graphiti(graph_driver=falkor_driver)
        await graphiti_falkor.build_indices_and_constraints()

        # Fetch all data from Neo4j
        data = await fetch_all_neo4j_data(neo4j_driver)

        # Migrate nodes
        await migrate_nodes(falkor_driver, data['entity_nodes'], 'Entity')
        await migrate_nodes(falkor_driver, data['episodic_nodes'], 'Episodic')
        await migrate_nodes(falkor_driver, data['community_nodes'], 'Community')

        # Migrate edges
        await migrate_edges(falkor_driver, data['entity_edges'], 'RELATES_TO')
        await migrate_edges(falkor_driver, data['episodic_edges'], 'MENTIONS')

        # Verify migration
        await verify_migration(neo4j_driver, falkor_driver)

        print('\n✓ Migration completed!')

    except Exception as e:
        print(f'\n✗ Migration failed: {e}')
        import traceback

        traceback.print_exc()

    finally:
        await neo4j_driver.close()
        await falkor_driver.close()


if __name__ == '__main__':
    asyncio.run(main())
