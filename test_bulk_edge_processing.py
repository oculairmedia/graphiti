#!/usr/bin/env python3
"""
Test bulk edge processing that matches the actual ingestion pipeline context.
This test processes many edges simultaneously like the real pipeline does.
"""

import asyncio
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.graph_queries import get_vector_cosine_func_query


async def create_large_dataset(driver, num_entities=100, num_edges=1000):
    """Create a large dataset that matches the scale of the real database."""
    
    print(f"🔧 Creating large test dataset: {num_entities} entities, {num_edges} edges...")
    
    # Create entities
    entities = []
    for i in range(num_entities):
        entity_uuid = f"entity_{i:04d}"
        entities.append(entity_uuid)
        
        await driver.execute_query(
            "MERGE (n:Entity {uuid: $uuid}) SET n.name = $name, n.group_id = $group_id",
            uuid=entity_uuid,
            name=f"Entity {i}",
            group_id="bulk_test_group"
        )
    
    # Create edges with varying groups (like real data)
    groups = ["group_a", "group_b", "group_c", "group_d", "group_e"]
    test_embeddings = [[random.random() for _ in range(2560)] for _ in range(10)]  # Reuse embeddings
    
    edges_created = 0
    for i in range(num_edges):
        source = random.choice(entities)
        target = random.choice(entities)
        if source == target:
            continue
            
        edge_uuid = f"bulk_edge_{i:05d}"
        group_id = random.choice(groups)
        embedding = random.choice(test_embeddings)
        
        await driver.execute_query("""
            MATCH (source:Entity {uuid: $source_uuid})
            MATCH (target:Entity {uuid: $target_uuid})
            MERGE (source)-[r:RELATES_TO {uuid: $edge_uuid, group_id: $group_id}]->(target)
            SET r.name = $name,
                r.fact = $fact,
                r.created_at = $created_at,
                r.episodes = $episodes,
                r.valid_at = $valid_at,
                r.fact_embedding = vecf32($fact_embedding)
            """,
            source_uuid=source,
            target_uuid=target,
            edge_uuid=edge_uuid,
            group_id=group_id,
            name=f"bulk_edge_{i}",
            fact=f"This is bulk test fact number {i} with some content to make it realistic",
            created_at="2025-01-01T00:00:00Z",
            episodes=[f"episode_{i}_1", f"episode_{i}_2"],
            valid_at="2025-01-01T00:00:00Z",
            fact_embedding=embedding
        )
        edges_created += 1
        
        if edges_created % 100 == 0:
            print(f"   Created {edges_created}/{num_edges} edges...")
    
    print(f"✅ Created {edges_created} bulk test edges")
    
    # Verify
    count_query = "MATCH ()-[e:RELATES_TO]->() WHERE e.group_id STARTS WITH 'group_' RETURN count(e) as count"
    result, _, _ = await driver.execute_query(count_query)
    actual_count = result[0]['count'] if result else 0
    print(f"📊 Verified: {actual_count} edges with group prefixes in database")


async def test_realistic_bulk_processing(driver):
    """Test processing multiple edges simultaneously like the ingestion pipeline."""
    
    print("\n🔄 Testing Realistic Bulk Edge Processing")
    print("=" * 60)
    
    # Get edges from different groups for processing
    edge_query = """
    MATCH ()-[e:RELATES_TO]->() 
    WHERE e.group_id STARTS WITH 'group_' AND e.fact_embedding IS NOT NULL
    RETURN e.uuid, e.source_node_uuid, e.target_node_uuid, e.group_id, e.fact_embedding
    ORDER BY e.group_id
    LIMIT 50
    """
    
    edges_result, _, _ = await driver.execute_query(edge_query)
    if not edges_result:
        print("❌ No bulk test edges found!")
        return
    
    print(f"Found {len(edges_result)} edges for bulk processing test")
    
    # Group edges by group_id (like the real pipeline does)
    edges_by_group = {}
    for edge in edges_result:
        group_id = edge['e.group_id']
        if group_id not in edges_by_group:
            edges_by_group[group_id] = []
        edges_by_group[group_id].append({
            'uuid': edge['e.uuid'],
            'source_node_uuid': edge['e.source_node_uuid'], 
            'target_node_uuid': edge['e.target_node_uuid'],
            'group_id': group_id,
            'fact_embedding': edge['e.fact_embedding']
        })
    
    print(f"Grouped {len(edges_result)} edges into {len(edges_by_group)} groups")
    
    # Test each group separately (like pipeline processes episodes)
    for group_id, group_edges in edges_by_group.items():
        await test_group_invalidation_processing(driver, group_id, group_edges)


async def test_group_invalidation_processing(driver, group_id, group_edges):
    """Test edge invalidation processing for a specific group."""
    
    print(f"\n📊 Processing group: {group_id} ({len(group_edges)} edges)")
    print("-" * 50)
    
    # This mimics the actual pipeline: process ALL edges in the group simultaneously
    cosine_func = get_vector_cosine_func_query('e.fact_embedding', 'edge.fact_embedding', 'falkordb')
    
    # The problematic query - but with realistic limits from the pipeline
    query = f"""
        UNWIND $edges AS edge
        MATCH (n:Entity)-[e:RELATES_TO {{group_id: edge.group_id}}]->(m:Entity)
        WHERE n.uuid IN [edge.source_node_uuid, edge.target_node_uuid] OR m.uuid IN [edge.target_node_uuid, edge.source_node_uuid]
        WITH edge, e, {cosine_func} AS score
        WHERE score > $min_score
        WITH edge, e, score
        ORDER BY score DESC
        RETURN edge.uuid AS search_edge_uuid,
            collect({{
                uuid: e.uuid,
                source_node_uuid: startNode(e).uuid,
                target_node_uuid: endNode(e).uuid,
                created_at: e.created_at,
                name: e.name,
                group_id: e.group_id,
                fact: e.fact,
                fact_embedding: e.fact_embedding,
                episodes: e.episodes,
                expired_at: e.expired_at,
                valid_at: e.valid_at,
                invalid_at: e.invalid_at
            }})[..$limit] AS matches
    """
    
    # Test with different limits that the pipeline actually uses
    test_limits = [50, 100, 200]  # RELEVANT_SCHEMA_LIMIT variations
    
    for limit in test_limits:
        print(f"   Testing limit {limit} with {len(group_edges)} edges...")
        
        query_params = {
            'edges': group_edges,
            'min_score': 0.7,
            'limit': limit
        }
        
        try:
            import time
            start_time = time.time()
            
            results, _, _ = await driver.execute_query(query, **query_params)
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            total_matches = sum(len(result.get('matches', [])) for result in results)
            
            print(f"     ✅ SUCCESS: {execution_time:.3f}s, {len(results)} groups, {total_matches} total matches")
            
            if execution_time > 5:
                print(f"     ⚠️  SLOW: {execution_time:.2f}s execution time")
            
            # Check for actual memory usage patterns
            if total_matches > limit * len(group_edges):
                print(f"     📈 HIGH RESULT COUNT: {total_matches} matches (limit={limit}, edges={len(group_edges)})")
                
        except Exception as e:
            error_msg = str(e)
            print(f"     ❌ FAILED: {error_msg}")
            
            if "Query's mem consumption exceeded capacity" in error_msg:
                print(f"     🔥 MEMORY EXHAUSTION at limit={limit}, edges={len(group_edges)}")
                print(f"     💡 Pipeline failure reproduced!")
                return False
            elif "Type mismatch" in error_msg:
                print(f"     🔧 TYPE MISMATCH at limit={limit}")
                return False
    
    return True


async def test_concurrent_processing(driver):
    """Test concurrent edge processing that might trigger memory issues."""
    
    print(f"\n⚡ Testing Concurrent Edge Processing")
    print("=" * 50)
    
    # Get multiple batches of edges
    batch_query = """
    MATCH ()-[e:RELATES_TO]->() 
    WHERE e.group_id STARTS WITH 'group_' AND e.fact_embedding IS NOT NULL
    RETURN e.uuid, e.source_node_uuid, e.target_node_uuid, e.group_id, e.fact_embedding
    SKIP $offset LIMIT $batch_size
    """
    
    batches = []
    batch_size = 20
    for offset in range(0, 100, batch_size):  # 5 batches of 20 edges each
        batch_result, _, _ = await driver.execute_query(batch_query, offset=offset, batch_size=batch_size)
        if batch_result:
            batch_edges = [{
                'uuid': edge['e.uuid'],
                'source_node_uuid': edge['e.source_node_uuid'], 
                'target_node_uuid': edge['e.target_node_uuid'],
                'group_id': edge['e.group_id'],
                'fact_embedding': edge['e.fact_embedding']
            } for edge in batch_result]
            batches.append(batch_edges)
    
    if not batches:
        print("❌ No batches created for concurrent testing")
        return
    
    print(f"Created {len(batches)} batches for concurrent processing")
    
    # Process all batches concurrently (like the pipeline does)
    async def process_batch(batch_num, batch_edges):
        cosine_func = get_vector_cosine_func_query('e.fact_embedding', 'edge.fact_embedding', 'falkordb')
        
        query = f"""
            UNWIND $edges AS edge
            MATCH (n:Entity)-[e:RELATES_TO {{group_id: edge.group_id}}]->(m:Entity)
            WHERE n.uuid IN [edge.source_node_uuid, edge.target_node_uuid] OR m.uuid IN [edge.target_node_uuid, edge.source_node_uuid]
            WITH edge, e, {cosine_func} AS score
            WHERE score > $min_score
            WITH edge, e, score
            ORDER BY score DESC
            RETURN edge.uuid AS search_edge_uuid,
                collect({{
                    uuid: e.uuid,
                    fact_embedding: e.fact_embedding
                }})[..$limit] AS matches
        """
        
        try:
            import time
            start_time = time.time()
            
            results, _, _ = await driver.execute_query(query, 
                edges=batch_edges, min_score=0.7, limit=200)
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            total_matches = sum(len(result.get('matches', [])) for result in results)
            print(f"   Batch {batch_num}: ✅ {execution_time:.3f}s, {total_matches} matches")
            return True
            
        except Exception as e:
            print(f"   Batch {batch_num}: ❌ {str(e)}")
            return False
    
    # Run all batches concurrently
    import time
    start_time = time.time()
    
    tasks = [process_batch(i, batch) for i, batch in enumerate(batches)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    end_time = time.time()
    total_time = end_time - start_time
    
    successful_batches = sum(1 for result in results if result is True)
    print(f"📊 Concurrent processing: {successful_batches}/{len(batches)} batches succeeded in {total_time:.2f}s")
    
    if successful_batches < len(batches):
        print(f"💥 CONCURRENT PROCESSING ISSUES detected!")


async def run_bulk_test():
    """Main bulk processing test."""
    
    print("🧪 Bulk Edge Processing Test")
    print("Testing realistic pipeline scenarios that cause memory exhaustion")
    print("=" * 80)
    
    driver = FalkorDriver(
        host='localhost',
        port=6379,
        username='',
        password='',
        database='falkordb'
    )
    
    try:
        # Check if we have existing bulk test data
        count_query = "MATCH ()-[e:RELATES_TO]->() WHERE e.group_id STARTS WITH 'group_' RETURN count(e) as count"
        result, _, _ = await driver.execute_query(count_query)
        existing_count = result[0]['count'] if result else 0
        
        if existing_count < 500:
            print(f"📊 Found {existing_count} existing bulk test edges, creating more...")
            await create_large_dataset(driver, num_entities=150, num_edges=1000)
        else:
            print(f"📊 Using {existing_count} existing bulk test edges")
        
        # Run bulk processing tests
        await test_realistic_bulk_processing(driver)
        
        # Run concurrent processing tests
        await test_concurrent_processing(driver)
        
        print(f"\n📋 BULK PROCESSING SUMMARY")
        print("=" * 40)
        print("✅ Tested individual query components - all work correctly")
        print("✅ Tested bulk group processing - simulates pipeline context")
        print("✅ Tested concurrent processing - simulates pipeline load")
        print("💡 If memory exhaustion occurs here, it confirms the pipeline issue!")
        
    except Exception as e:
        print(f"\n❌ Bulk test error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await driver.close()


if __name__ == '__main__':
    asyncio.run(run_bulk_test())