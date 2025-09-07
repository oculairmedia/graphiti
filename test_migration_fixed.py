#!/usr/bin/env python3
"""Test the fixed migration with correct database configuration."""

import asyncio
from sync_service.simple_migration import perform_simple_migration
from falkordb import FalkorDB

async def test_fixed_migration():
    """Test migration with correct configuration."""
    
    # Configuration
    neo4j_config = {
        'uri': 'bolt://localhost:7687',
        'user': 'neo4j',
        'password': 'demodemo'
    }
    
    falkordb_config = {
        'host': 'localhost',
        'port': 6379,
        'database': 'graphiti_migration'  # Use the correct database
    }
    
    print("=== Testing Fixed Migration ===")
    print(f"Target database: {falkordb_config['database']}")
    
    # Clear the target database first
    print("\nClearing target database...")
    falkor_db = FalkorDB(host='localhost', port=6379)
    falkor_graph = falkor_db.select_graph('graphiti_migration')
    try:
        falkor_graph.delete()
        print("  Database cleared")
    except:
        print("  Database didn't exist or already empty")
    
    # Run the migration
    print("\nRunning migration...")
    try:
        stats = await perform_simple_migration(neo4j_config, falkordb_config)
        
        print(f"\nMigration Result: {stats['status']}")
        if stats['status'] == 'completed':
            print(f"  Nodes: {stats['nodes_migrated']}/{stats['total_nodes']}")
            print(f"  Relationships: {stats['relationships_migrated']}/{stats['total_relationships']}")
            print(f"  Duration: {stats['duration_seconds']:.2f}s")
        else:
            print(f"  Error: {stats.get('error', 'Unknown error')}")
    except Exception as e:
        print(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Check the results
    print("\n=== Checking Results ===")
    
    # Check what's actually in the database
    result = falkor_graph.query("""
        MATCH ()-[r]->() 
        RETURN type(r) as rel_type, count(r) as count
        ORDER BY count DESC
    """)
    
    print("Relationships by type:")
    total = 0
    if result.result_set:
        for record in result.result_set:
            rel_type = record[0]
            count = record[1]
            print(f"  {rel_type}: {count}")
            total += count
    print(f"  TOTAL: {total}")
    
    # Check Entity-to-Entity specifically
    result = falkor_graph.query("""
        MATCH (e1:Entity)-[r:RELATES_TO]->(e2:Entity)
        RETURN count(r) as count
    """)
    entity_relates = result.result_set[0][0] if result.result_set else 0
    
    print(f"\nEntity-to-Entity RELATES_TO: {entity_relates}")
    
    if entity_relates == 0:
        print("\n⚠️  STILL MISSING Entity-to-Entity relationships!")
        print("Checking if entities exist...")
        
        # Check if Entity nodes exist
        entity_result = falkor_graph.query("MATCH (e:Entity) RETURN count(e) as count")
        entity_count = entity_result.result_set[0][0] if entity_result.result_set else 0
        print(f"  Entity nodes: {entity_count}")
        
        if entity_count > 0:
            print("  Entities exist but relationships weren't created")
        else:
            print("  No entities found - node migration may have failed")
    else:
        print(f"\n✓ SUCCESS! Found {entity_relates} Entity-to-Entity RELATES_TO relationships")

if __name__ == "__main__":
    asyncio.run(test_fixed_migration())