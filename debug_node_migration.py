#!/usr/bin/env python3
"""Debug node migration to see what's being migrated."""

import asyncio
from neo4j import AsyncGraphDatabase
from falkordb import FalkorDB

async def debug_node_migration():
    """Check what nodes are being migrated."""
    print("=== Node Migration Debug ===\n")
    
    # Neo4j connection
    neo4j_driver = AsyncGraphDatabase.driver(
        'bolt://localhost:7687', 
        auth=('neo4j', 'demodemo')
    )
    
    # FalkorDB connection  
    falkor_db = FalkorDB(host='localhost', port=6379)
    falkor_graph = falkor_db.select_graph('knowledge_graph')
    
    try:
        print("📊 NEO4J NODE COUNTS:")
        async with neo4j_driver.session() as session:
            # Node counts by label
            result = await session.run("""
                MATCH (n) 
                RETURN labels(n)[0] as label, count(n) as count
                ORDER BY count DESC
            """)
            neo4j_nodes = {}
            async for record in result:
                label = record['label'] or 'UNLABELED'
                count = record['count']
                neo4j_nodes[label] = count
                print(f"  {label}: {count}")
            
            total_neo4j = sum(neo4j_nodes.values())
            print(f"  TOTAL: {total_neo4j}")
            
            # Check Entity nodes specifically
            entity_result = await session.run("""
                MATCH (n:Entity) 
                WHERE n.uuid IS NOT NULL
                RETURN count(n) as entities_with_uuid
            """)
            entity_record = await entity_result.single()
            entities_with_uuid = entity_record['entities_with_uuid']
            print(f"  Entities with UUID: {entities_with_uuid}/{neo4j_nodes.get('Entity', 0)}")
        
        print(f"\n📊 FALKORDB NODE COUNTS:")
        try:
            # Node counts by label
            result = falkor_graph.query("""
                MATCH (n) 
                RETURN labels(n)[0] as label, count(n) as count
                ORDER BY count DESC
            """)
            falkor_nodes = {}
            if result.result_set:
                for record in result.result_set:
                    label = record[0] or 'UNLABELED'
                    count = record[1] 
                    falkor_nodes[label] = count
                    print(f"  {label}: {count}")
            
            total_falkor = sum(falkor_nodes.values())
            print(f"  TOTAL: {total_falkor}")
            
        except Exception as e:
            print(f"  Error querying FalkorDB nodes: {e}")
            falkor_nodes = {}
            total_falkor = 0
        
        print(f"\n📈 NODE MIGRATION ANALYSIS:")
        all_labels = set(neo4j_nodes.keys()) | set(falkor_nodes.keys())
        for label in sorted(all_labels):
            neo4j_count = neo4j_nodes.get(label, 0)
            falkor_count = falkor_nodes.get(label, 0)
            missing = neo4j_count - falkor_count
            if missing == 0:
                print(f"  {label}: {falkor_count}/{neo4j_count} ✓")
            else:
                print(f"  {label}: {falkor_count}/{neo4j_count} (missing {missing})")
        
        print(f"\nTotal nodes: {sum(falkor_nodes.values())}/{sum(neo4j_nodes.values())} migrated")
        
        # Key insight: if Entity nodes aren't migrated, relationships will fail
        entity_neo4j = neo4j_nodes.get('Entity', 0)
        entity_falkor = falkor_nodes.get('Entity', 0)
        if entity_neo4j > 0 and entity_falkor == 0:
            print(f"\n⚠️  CRITICAL: No Entity nodes migrated! This explains missing relationships.")
            print(f"   Entity-to-entity relationships require both source and target entities.")
        elif entity_falkor < entity_neo4j:
            print(f"\n⚠️  WARNING: Only {entity_falkor}/{entity_neo4j} Entity nodes migrated.")
            print(f"   Some entity-to-entity relationships will fail.")
    
    except Exception as e:
        print(f"Error during debug: {e}")
    
    finally:
        await neo4j_driver.close()

if __name__ == "__main__":
    asyncio.run(debug_node_migration())