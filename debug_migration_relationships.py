#!/usr/bin/env python3
"""Debug why RELATES_TO relationships aren't being migrated."""

import asyncio
from neo4j import AsyncGraphDatabase
from falkordb import FalkorDB

async def debug_relationship_migration():
    """Debug the relationship migration issue."""
    
    # Neo4j connection
    neo4j_driver = AsyncGraphDatabase.driver(
        'bolt://localhost:7687',
        auth=('neo4j', 'demodemo')
    )
    
    # FalkorDB connection
    falkor_db = FalkorDB(host='localhost', port=6379)
    falkor_graph = falkor_db.select_graph('graphiti_migration')
    
    print("=== Debugging Relationship Migration ===\n")
    
    try:
        # Check what would be fetched by the migration query
        async with neo4j_driver.session() as session:
            # The exact query used by migration
            result = await session.run("""
                MATCH (s)-[r]->(t) 
                WHERE s.uuid IS NOT NULL AND t.uuid IS NOT NULL
                RETURN type(r) as rel_type, count(r) as count
                ORDER BY count DESC
            """)
            
            print("Relationships that SHOULD be migrated (have source & target UUIDs):")
            total = 0
            async for record in result:
                rel_type = record['rel_type']
                count = record['count']
                print(f"  {rel_type}: {count}")
                total += count
            print(f"  TOTAL: {total}")
            
            # Check specifically for Entity-to-Entity RELATES_TO
            result2 = await session.run("""
                MATCH (s:Entity)-[r:RELATES_TO]->(t:Entity)
                WHERE s.uuid IS NOT NULL AND t.uuid IS NOT NULL
                RETURN count(r) as count
            """)
            record = await result2.single()
            entity_relates = record['count']
            print(f"\nEntity-to-Entity RELATES_TO with UUIDs: {entity_relates}")
            
            # Sample a few to verify they're valid
            result3 = await session.run("""
                MATCH (s:Entity)-[r:RELATES_TO]->(t:Entity)
                WHERE s.uuid IS NOT NULL AND t.uuid IS NOT NULL
                RETURN s.uuid as source, t.uuid as target, 
                       r.uuid as rel_uuid, r.group_id as group_id
                LIMIT 3
            """)
            print("\nSample Entity-to-Entity RELATES_TO:")
            async for record in result3:
                print(f"  {record['source'][:8]}... -> {record['target'][:8]}...")
                print(f"    rel_uuid: {record['rel_uuid']}")
                print(f"    group_id: {record['group_id']}")
        
        # Check what's actually in FalkorDB
        print("\n" + "="*50)
        print("What's actually in FalkorDB (graphiti_migration):")
        
        # Total relationships
        result = falkor_graph.query("""
            MATCH ()-[r]->() 
            RETURN type(r) as rel_type, count(r) as count
            ORDER BY count DESC
        """)
        if result.result_set:
            total_falkor = 0
            for record in result.result_set:
                rel_type = record[0]
                count = record[1]
                print(f"  {rel_type}: {count}")
                total_falkor += count
            print(f"  TOTAL: {total_falkor}")
        else:
            print("  No relationships found")
            
        # Entity-to-Entity specifically  
        result = falkor_graph.query("""
            MATCH (e1:Entity)-[r]->(e2:Entity)
            RETURN type(r) as rel_type, count(r) as count
        """)
        if result.result_set:
            print("\nEntity-to-Entity relationships:")
            for record in result.result_set:
                print(f"  {record[0]}: {record[1]}")
        else:
            print("\nNo Entity-to-Entity relationships found")
            
    except Exception as e:
        print(f"Error: {e}")
    
    finally:
        await neo4j_driver.close()

if __name__ == "__main__":
    asyncio.run(debug_relationship_migration())