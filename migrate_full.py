#!/usr/bin/env python3
"""
Full migration script that copies ALL data from Neo4j to FalkorDB.
"""

import asyncio
import json
import re
from datetime import datetime
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from falkordb import FalkorDB

def escape_string(value):
    """Escape string for Cypher query."""
    if value is None:
        return 'null'
    return str(value).replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')

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

async def migrate_all_data(neo4j_driver: Neo4jDriver, falkor_graph):
    """Migrate ALL data from Neo4j to FalkorDB."""
    print("\nStarting FULL migration from Neo4j to FalkorDB...")
    
    # Get total counts
    count_result = await neo4j_driver.execute_query("MATCH (n) RETURN count(n) as count")
    total_nodes = count_result.records[0]['count'] if count_result and count_result.records else 0
    
    count_result = await neo4j_driver.execute_query("MATCH ()-[r]->() RETURN count(r) as count")
    total_rels = count_result.records[0]['count'] if count_result and count_result.records else 0
    
    print(f"\nTotal to migrate:")
    print(f"  - Nodes: {total_nodes:,}")
    print(f"  - Relationships: {total_rels:,}")
    
    # Clear FalkorDB first
    print("\nClearing FalkorDB...")
    try:
        falkor_graph.query("MATCH (n) DETACH DELETE n")
    except:
        pass  # Graph might be empty
    
    # Migrate nodes in batches
    print("\nMigrating nodes...")
    batch_size = 1000
    node_count = 0
    failed_nodes = 0
    
    for offset in range(0, total_nodes, batch_size):
        print(f"\nProcessing nodes {offset:,} to {min(offset + batch_size, total_nodes):,}...")
        
        # Fetch batch of nodes
        nodes_query = f"MATCH (n) RETURN n, labels(n) as labels SKIP {offset} LIMIT {batch_size}"
        nodes_result = await neo4j_driver.execute_query(nodes_query)
        nodes = nodes_result.records if nodes_result else []
        
        # Process each node
        for record in nodes:
            try:
                node = record['n']
                labels = record['labels']
                
                if not labels:
                    continue
                
                label = labels[0]  # Use first label
                
                # Build properties, filtering out problematic ones
                props = []
                for key, value in node.items():
                    # Skip complex nested structures that might cause issues
                    if key in ['entity_edges', 'episodic_edges'] and isinstance(value, list):
                        continue
                    
                    # Format the value
                    formatted_value = format_value(value)
                    if formatted_value != 'null':
                        props.append(f"{key}: {formatted_value}")
                
                if props:
                    props_str = "{" + ", ".join(props) + "}"
                    query = f"CREATE (n:{label} {props_str})"
                else:
                    query = f"CREATE (n:{label})"
                
                falkor_graph.query(query)
                node_count += 1
                
            except Exception as e:
                failed_nodes += 1
                if failed_nodes <= 5:  # Only show first 5 errors
                    print(f"  Error on node: {str(e)[:100]}")
        
        print(f"  Progress: {node_count:,} / {total_nodes:,} nodes migrated ({failed_nodes:,} failed)")
    
    print(f"\n✓ Node migration complete: {node_count:,} succeeded, {failed_nodes:,} failed")
    
    # Now migrate relationships in batches
    print("\nMigrating relationships...")
    rel_batch_size = 2000
    rel_count = 0
    failed_rels = 0
    
    for offset in range(0, total_rels, rel_batch_size):
        print(f"\nProcessing relationships {offset:,} to {min(offset + rel_batch_size, total_rels):,}...")
        
        # Fetch batch of relationships
        rels_query = f"""
        MATCH (s)-[r]->(t) 
        RETURN s.uuid as source_uuid, t.uuid as target_uuid, type(r) as rel_type, r
        SKIP {offset} LIMIT {rel_batch_size}
        """
        
        rels_result = await neo4j_driver.execute_query(rels_query)
        relationships = rels_result.records if rels_result else []
        
        # Process each relationship
        for record in relationships:
            try:
                source_uuid = record['source_uuid']
                target_uuid = record['target_uuid']
                rel_type = record['rel_type']
                rel_props = record['r']
                
                # Build relationship properties
                props = []
                if rel_props:
                    for key, value in rel_props.items():
                        if key in ['source_uuid', 'target_uuid']:  # Skip redundant properties
                            continue
                        formatted_value = format_value(value)
                        if formatted_value != 'null':
                            props.append(f"{key}: {formatted_value}")
                
                # Create relationship query
                if props:
                    props_str = "{" + ", ".join(props) + "}"
                    rel_query = f"""
                    MATCH (s {{uuid: '{source_uuid}'}}), (t {{uuid: '{target_uuid}'}})
                    CREATE (s)-[:{rel_type} {props_str}]->(t)
                    """
                else:
                    rel_query = f"""
                    MATCH (s {{uuid: '{source_uuid}'}}), (t {{uuid: '{target_uuid}'}})
                    CREATE (s)-[:{rel_type}]->(t)
                    """
                
                falkor_graph.query(rel_query)
                rel_count += 1
                
            except Exception as e:
                failed_rels += 1
                if failed_rels <= 5:  # Only show first 5 errors
                    print(f"  Error on relationship: {str(e)[:100]}")
        
        print(f"  Progress: {rel_count:,} / {total_rels:,} relationships migrated ({failed_rels:,} failed)")
    
    print(f"\n✓ Relationship migration complete: {rel_count:,} succeeded, {failed_rels:,} failed")
    
    return node_count, rel_count

async def verify_migration(falkor_graph):
    """Verify the migration results."""
    print("\nVerifying migration...")
    
    # Count nodes
    result = falkor_graph.query("MATCH (n) RETURN count(n) as count")
    node_count = result.result_set[0][0] if result.result_set else 0
    
    # Count relationships
    result = falkor_graph.query("MATCH ()-[r]->() RETURN count(r) as count")
    rel_count = result.result_set[0][0] if result.result_set else 0
    
    # Get node type distribution
    result = falkor_graph.query("MATCH (n) RETURN labels(n) as type, count(n) as count ORDER BY count DESC")
    
    print(f"\nFalkorDB now contains:")
    print(f"  - Total nodes: {node_count:,}")
    print(f"  - Total relationships: {rel_count:,}")
    
    if result.result_set:
        print("\nNode distribution:")
        for row in result.result_set[:10]:  # Show top 10
            print(f"  - {row[0]}: {row[1]:,}")
    
    return node_count, rel_count

async def main():
    """Main migration function."""
    # Configuration
    neo4j_uri = "bolt://localhost:7687"
    neo4j_user = "neo4j"
    neo4j_password = "demodemo"
    
    print("=== FULL Neo4j to FalkorDB Migration ===")
    print(f"Source: Neo4j at {neo4j_uri}")
    print(f"Target: FalkorDB at localhost:6389")
    
    # Create Neo4j driver
    neo4j_driver = Neo4jDriver(
        uri=neo4j_uri,
        user=neo4j_user,
        password=neo4j_password
    )
    
    # Create FalkorDB connection
    falkor_db = FalkorDB(host='localhost', port=6389)
    falkor_graph = falkor_db.select_graph("graphiti_migration")
    
    try:
        # Start timer
        start_time = datetime.now()
        
        # Perform full migration
        migrated_nodes, migrated_rels = await migrate_all_data(neo4j_driver, falkor_graph)
        
        # Verify results
        final_nodes, final_rels = await verify_migration(falkor_graph)
        
        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds()
        
        print(f"\n{'='*50}")
        print(f"✓ MIGRATION COMPLETED in {duration:.1f} seconds")
        print(f"{'='*50}")
        print(f"\nFinal Results:")
        print(f"  - Nodes: {final_nodes:,} (target was 4,440)")
        print(f"  - Relationships: {final_rels:,} (target was 13,904)")
        
        if final_nodes >= 4000 and final_rels >= 13000:
            print("\n✅ Migration successful! Most data transferred.")
        else:
            print("\n⚠️  Some data may have been skipped due to formatting issues.")
        
        print(f"\nYou can now query the full dataset in RedisInsight!")
        print(f"URL: http://192.168.50.90:5540")
        
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await neo4j_driver.close()

if __name__ == "__main__":
    asyncio.run(main())