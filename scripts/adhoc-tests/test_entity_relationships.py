#!/usr/bin/env python3
"""Test creating entity-to-entity relationships manually."""

import asyncio
from neo4j import AsyncGraphDatabase
from falkordb import FalkorDB

async def test_entity_relationships():
    """Test if we can create entity-to-entity relationships."""
    
    # Neo4j connection
    neo4j_driver = AsyncGraphDatabase.driver(
        'bolt://localhost:7687',
        auth=('neo4j', 'demodemo')
    )
    
    # FalkorDB connection - use the correct database
    falkor_db = FalkorDB(host='localhost', port=6379)
    falkor_graph = falkor_db.select_graph('graphiti_migration')
    
    print("=== Testing Entity-to-Entity Relationship Creation ===\n")
    
    try:
        # Get a sample RELATES_TO relationship from Neo4j
        async with neo4j_driver.session() as session:
            result = await session.run("""
                MATCH (e1:Entity)-[r:RELATES_TO]->(e2:Entity)
                RETURN e1.uuid as source_uuid, e2.uuid as target_uuid, 
                       r.uuid as rel_uuid, r.group_id as rel_group_id,
                       type(r) as rel_type
                LIMIT 1
            """)
            record = await result.single()
            
            if record:
                source_uuid = record['source_uuid']
                target_uuid = record['target_uuid']
                rel_uuid = record['rel_uuid']
                rel_group_id = record['rel_group_id']
                rel_type = record['rel_type']
                
                print(f"Sample relationship from Neo4j:")
                print(f"  Source: {source_uuid}")
                print(f"  Target: {target_uuid}")
                print(f"  Type: {rel_type}")
                print(f"  Rel UUID: {rel_uuid}")
                print(f"  Rel Group: {rel_group_id}")
                
                # Check if these entities exist in FalkorDB
                print(f"\nChecking if entities exist in FalkorDB...")
                
                # Check source entity
                source_result = falkor_graph.query(f"MATCH (n:Entity {{uuid: '{source_uuid}'}}) RETURN n.uuid as uuid")
                source_exists = len(source_result.result_set) > 0
                print(f"  Source entity exists: {source_exists}")
                
                # Check target entity
                target_result = falkor_graph.query(f"MATCH (n:Entity {{uuid: '{target_uuid}'}}) RETURN n.uuid as uuid")
                target_exists = len(target_result.result_set) > 0
                print(f"  Target entity exists: {target_exists}")
                
                if source_exists and target_exists:
                    # Try to create the relationship
                    print(f"\nAttempting to create RELATES_TO relationship...")
                    
                    # Method 1: Without label in MATCH (like current migration)
                    try:
                        query1 = f"""
                        MATCH (s {{uuid: '{source_uuid}'}}), (t {{uuid: '{target_uuid}'}})
                        CREATE (s)-[:RELATES_TO {{uuid: '{rel_uuid}_test1', group_id: '{rel_group_id}'}}]->(t)
                        """
                        falkor_graph.query(query1)
                        print("  ✓ Method 1 (no labels): SUCCESS")
                    except Exception as e:
                        print(f"  ✗ Method 1 (no labels): FAILED - {e}")
                    
                    # Method 2: With labels in MATCH
                    try:
                        query2 = f"""
                        MATCH (s:Entity {{uuid: '{source_uuid}'}}), (t:Entity {{uuid: '{target_uuid}'}})
                        CREATE (s)-[:RELATES_TO {{uuid: '{rel_uuid}_test2', group_id: '{rel_group_id}'}}]->(t)
                        """
                        falkor_graph.query(query2)
                        print("  ✓ Method 2 (with labels): SUCCESS")
                    except Exception as e:
                        print(f"  ✗ Method 2 (with labels): FAILED - {e}")
                    
                    # Check if relationships were created
                    check_result = falkor_graph.query("""
                        MATCH (e1:Entity)-[r:RELATES_TO]->(e2:Entity)
                        RETURN count(r) as count
                    """)
                    count = check_result.result_set[0][0] if check_result.result_set else 0
                    print(f"\n  Total Entity-to-Entity RELATES_TO relationships now: {count}")
                    
                    # Clean up test relationships
                    falkor_graph.query(f"MATCH ()-[r:RELATES_TO]->() WHERE r.uuid ENDS WITH '_test1' OR r.uuid ENDS WITH '_test2' DELETE r")
                    print("  Cleaned up test relationships")
                    
                else:
                    print("\n⚠️  Cannot test - one or both entities missing in FalkorDB!")
                    
    except Exception as e:
        print(f"Error during test: {e}")
    
    finally:
        await neo4j_driver.close()

if __name__ == "__main__":
    asyncio.run(test_entity_relationships())