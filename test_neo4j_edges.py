#!/usr/bin/env python3
"""
Check Neo4j for edge data to understand the memory exhaustion issue.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.driver.falkordb_driver import FalkorDriver


async def check_neo4j_data():
    """Check what data exists in Neo4j."""
    
    neo4j_driver = Neo4jDriver(
        host='localhost',
        port=7687,
        username='neo4j',
        password='demodemo',
        database='neo4j'
    )
    
    print("🔍 Checking Neo4j Database Content")
    print("=" * 50)
    
    try:
        # Check total edge count
        count_query = "MATCH ()-[e:RELATES_TO]->() RETURN count(e) as edge_count"
        result, _, _ = await neo4j_driver.execute_query(count_query)
        edge_count = result[0]['edge_count'] if result else 0
        print(f"Total edges in Neo4j: {edge_count:,}")
        
        if edge_count == 0:
            print("❌ No edges found in Neo4j!")
            return False
            
        # Check edges with embeddings
        embedding_query = "MATCH ()-[e:RELATES_TO]->() WHERE e.fact_embedding IS NOT NULL RETURN count(e) as embedding_count"
        result, _, _ = await neo4j_driver.execute_query(embedding_query)
        embedding_count = result[0]['embedding_count'] if result else 0
        print(f"Edges with embeddings: {embedding_count:,}")
        
        # Sample some edges
        if embedding_count > 0:
            sample_query = """
            MATCH ()-[e:RELATES_TO]->() 
            WHERE e.fact_embedding IS NOT NULL 
            RETURN e.uuid, e.group_id, e.fact, size(e.fact_embedding) as embedding_size
            LIMIT 5
            """
            result, _, _ = await neo4j_driver.execute_query(sample_query)
            print("\nSample edges with embeddings:")
            for i, edge in enumerate(result):
                print(f"  {i+1}. UUID: {edge['e.uuid']}")
                print(f"      Group: {edge['e.group_id']}")
                print(f"      Fact: {edge['e.fact'][:50]}...")
                print(f"      Embedding size: {edge['embedding_size']}")
                
        return embedding_count > 0
        
    except Exception as e:
        print(f"❌ Error checking Neo4j: {e}")
        return False
    finally:
        await neo4j_driver.close()


async def sync_some_data():
    """Manually sync a small amount of data from Neo4j to FalkorDB."""
    
    print("\n🔄 Manually syncing data from Neo4j to FalkorDB")
    print("=" * 55)
    
    neo4j_driver = Neo4jDriver(
        host='localhost',
        port=7687,
        username='neo4j',
        password='demodemo',
        database='neo4j'
    )
    
    falkor_driver = FalkorDriver(
        host='localhost',
        port=6379,
        username='',
        password='',
        database='falkordb'
    )
    
    try:
        # Get a few edges from Neo4j
        query = """
        MATCH (n:Entity)-[e:RELATES_TO]->(m:Entity)
        WHERE e.fact_embedding IS NOT NULL
        RETURN n.uuid as source_uuid, n.name as source_name,
               m.uuid as target_uuid, m.name as target_name,
               e.uuid, e.name, e.fact, e.group_id, e.created_at,
               e.fact_embedding, e.episodes, e.valid_at, e.invalid_at, e.expired_at
        LIMIT 10
        """
        
        result, _, _ = await neo4j_driver.execute_query(query)
        print(f"Found {len(result)} edges in Neo4j to sync")
        
        if not result:
            return False
            
        # First ensure nodes exist in FalkorDB
        nodes_to_create = set()
        for edge in result:
            nodes_to_create.add((edge['source_uuid'], edge['source_name']))
            nodes_to_create.add((edge['target_uuid'], edge['target_name']))
            
        print(f"Creating {len(nodes_to_create)} nodes in FalkorDB...")
        for uuid, name in nodes_to_create:
            node_query = """
            MERGE (n:Entity {uuid: $uuid})
            SET n.name = $name
            RETURN n.uuid
            """
            await falkor_driver.execute_query(node_query, uuid=uuid, name=name)
            
        # Now create edges
        print(f"Creating {len(result)} edges in FalkorDB...")
        for edge in result:
            edge_query = """
            MATCH (source:Entity {uuid: $source_uuid})
            MATCH (target:Entity {uuid: $target_uuid})
            MERGE (source)-[r:RELATES_TO {uuid: $edge_uuid, group_id: $group_id}]->(target)
            SET r.name = $name,
                r.fact = $fact,
                r.created_at = $created_at,
                r.episodes = $episodes,
                r.valid_at = $valid_at,
                r.invalid_at = $invalid_at,
                r.expired_at = $expired_at,
                r.fact_embedding = vecf32($fact_embedding)
            RETURN r.uuid
            """
            
            await falkor_driver.execute_query(
                edge_query,
                source_uuid=edge['source_uuid'],
                target_uuid=edge['target_uuid'],
                edge_uuid=edge['e.uuid'],
                group_id=edge['e.group_id'],
                name=edge['e.name'],
                fact=edge['e.fact'],
                created_at=edge['e.created_at'],
                episodes=edge['e.episodes'],
                valid_at=edge['e.valid_at'],
                invalid_at=edge['e.invalid_at'],
                expired_at=edge['e.expired_at'],
                fact_embedding=edge['e.fact_embedding']
            )
            
        print("✅ Successfully synced sample data to FalkorDB")
        return True
        
    except Exception as e:
        print(f"❌ Error syncing data: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await neo4j_driver.close()
        await falkor_driver.close()


if __name__ == '__main__':
    print("🧪 Neo4j Data Check and Sync Test")
    print()
    
    # Check Neo4j data
    has_data = asyncio.run(check_neo4j_data())
    
    if has_data:
        # Sync some data to FalkorDB for testing
        sync_success = asyncio.run(sync_some_data())
        
        if sync_success:
            print("\n✅ Ready to run edge invalidation tests with real data!")
        else:
            print("\n❌ Failed to sync data for testing")
    else:
        print("\n❌ No data available in Neo4j for testing")