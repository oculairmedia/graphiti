#!/usr/bin/env python3
"""Test when FalkorDB constraints get created during migration."""

import asyncio
from falkordb import FalkorDB
from sync_service.simple_migration import perform_simple_migration

async def test_constraint_timing():
    """Test if constraints exist before and after migration."""
    
    # FalkorDB connection config
    falkordb_config = {
        'host': 'localhost',
        'port': 6379,
        'database': 'knowledge_graph'
    }
    
    # Neo4j connection config
    neo4j_config = {
        'uri': 'bolt://localhost:7687',
        'user': 'neo4j',
        'password': 'demodemo'
    }
    
    falkor_db = FalkorDB(
        host=falkordb_config['host'],
        port=falkordb_config['port']
    )
    falkor_graph = falkor_db.select_graph(falkordb_config['database'])
    
    def check_constraints(phase):
        """Check if constraints exist."""
        print(f"\n=== {phase} ===")
        
        # Check if we can create RELATES_TO without properties
        try:
            # Clean up first
            falkor_graph.query("MATCH (n:TestConstraintNode) DETACH DELETE n")
            
            # Create test nodes
            falkor_graph.query("""
                CREATE (s:TestConstraintNode {uuid: 'test-constraint-source'})
                CREATE (t:TestConstraintNode {uuid: 'test-constraint-target'})
            """)
            
            # Try to create RELATES_TO without required properties
            try:
                falkor_graph.query("""
                    MATCH (s:TestConstraintNode {uuid: 'test-constraint-source'}), 
                          (t:TestConstraintNode {uuid: 'test-constraint-target'})
                    CREATE (s)-[:RELATES_TO]->(t)
                """)
                print(f"  ✓ RELATES_TO without properties: ALLOWED (no constraints)")
                constraint_active = False
            except Exception as e:
                print(f"  ✗ RELATES_TO without properties: BLOCKED - {e}")
                constraint_active = True
            
            # Clean up test nodes
            falkor_graph.query("MATCH (n:TestConstraintNode) DETACH DELETE n")
            
            return constraint_active
            
        except Exception as e:
            print(f"  Error testing constraints: {e}")
            return None
    
    print("Testing constraint timing during migration...")
    
    # Check before migration
    constraints_before = check_constraints("BEFORE MIGRATION")
    
    print("\n=== STARTING MIGRATION ===")
    
    # Run the migration
    try:
        stats = await perform_simple_migration(neo4j_config, falkordb_config)
        print(f"Migration result: {stats['status']}")
        if stats['status'] == 'completed':
            print(f"  Nodes: {stats['nodes_migrated']}/{stats['total_nodes']}")
            print(f"  Relationships: {stats['relationships_migrated']}/{stats['total_relationships']}")
        else:
            print(f"  Error: {stats.get('error', 'Unknown error')}")
    except Exception as e:
        print(f"Migration failed with exception: {e}")
    
    # Check after migration
    constraints_after = check_constraints("AFTER MIGRATION")
    
    print(f"\n=== SUMMARY ===")
    print(f"Constraints before migration: {'Active' if constraints_before else 'Not Active'}")
    print(f"Constraints after migration: {'Active' if constraints_after else 'Not Active'}")
    
    if constraints_before != constraints_after:
        print("⚠️  CONSTRAINT STATE CHANGED DURING MIGRATION!")
        print("This explains why migration works once but fails on restart.")
    else:
        print("Constraint state remained consistent.")

if __name__ == "__main__":
    asyncio.run(test_constraint_timing())