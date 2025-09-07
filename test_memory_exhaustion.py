#!/usr/bin/env python3
"""
Test to reproduce the memory exhaustion issue in edge invalidation queries.
Creates test data directly in FalkorDB and tests the failing query patterns.
"""

import asyncio
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.graph_queries import get_vector_cosine_func_query


async def create_test_data(driver, num_edges=100):
    """Create test data that mimics the real data structure causing memory issues."""
    
    print(f"🔧 Creating {num_edges} test edges with embeddings...")
    
    # Create some test entities first
    entities = []
    for i in range(num_edges // 5):  # 20 entities for 100 edges
        entity_uuid = f"entity_{i:04d}"
        entities.append(entity_uuid)
        
        create_entity_query = """
        MERGE (n:Entity {uuid: $uuid})
        SET n.name = $name, n.group_id = $group_id
        RETURN n.uuid
        """
        
        await driver.execute_query(
            create_entity_query,
            uuid=entity_uuid,
            name=f"Test Entity {i}",
            group_id="test_group"
        )
    
    print(f"✅ Created {len(entities)} test entities")
    
    # Create test edges with realistic embeddings
    test_embedding = [random.random() for _ in range(2560)]  # 2560-dimensional vector
    
    for i in range(num_edges):
        source_entity = random.choice(entities)
        target_entity = random.choice(entities)
        if source_entity == target_entity:
            continue
            
        edge_uuid = f"edge_{i:04d}"
        
        create_edge_query = """
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
        
        await driver.execute_query(
            create_edge_query,
            source_uuid=source_entity,
            target_uuid=target_entity,
            edge_uuid=edge_uuid,
            group_id="test_group",
            name=f"test_edge_{i}",
            fact=f"Test fact for edge {i} connecting entities",
            created_at="2025-01-01T00:00:00Z",
            episodes=["episode_1", "episode_2"],
            valid_at="2025-01-01T00:00:00Z",
            invalid_at=None,
            expired_at=None,
            fact_embedding=test_embedding
        )
    
    print(f"✅ Created {num_edges} test edges with embeddings")
    
    # Verify data was created
    count_query = "MATCH ()-[e:RELATES_TO]->() WHERE e.fact_embedding IS NOT NULL RETURN count(e) as edge_count"
    result, _, _ = await driver.execute_query(count_query)
    actual_count = result[0]['edge_count'] if result else 0
    print(f"📊 Verified: {actual_count} edges with embeddings in database")


async def test_memory_exhaustion_scenarios(driver):
    """Test different scenarios that might cause memory exhaustion."""
    
    print("\n🧪 Testing Memory Exhaustion Scenarios")
    print("=" * 60)
    
    # Get some test edges to use in the query
    sample_query = """
    MATCH ()-[e:RELATES_TO]->() 
    WHERE e.fact_embedding IS NOT NULL 
    RETURN e.uuid, e.source_node_uuid, e.target_node_uuid, e.group_id, e.fact_embedding
    LIMIT 10
    """
    
    sample_result, _, _ = await driver.execute_query(sample_query)
    if not sample_result:
        print("❌ No test edges found!")
        return
    
    print(f"Found {len(sample_result)} sample edges for testing")
    
    # Create mock edge data for the UNWIND operation
    test_edges = []
    for edge_data in sample_result:
        test_edges.append({
            'uuid': edge_data['e.uuid'],
            'source_node_uuid': edge_data['e.source_node_uuid'], 
            'target_node_uuid': edge_data['e.target_node_uuid'],
            'group_id': edge_data['e.group_id'],
            'fact_embedding': edge_data['e.fact_embedding']
        })
    
    # Test scenarios with increasing complexity
    scenarios = [
        {"limit": 10, "description": "Small limit (baseline)"},
        {"limit": 50, "description": "Medium limit"},
        {"limit": 200, "description": "Large limit (potential memory issue)"},
        {"limit": 500, "description": "Very large limit (likely memory exhaustion)"},
        {"limit": 1000, "description": "Extreme limit (definite memory exhaustion)"}
    ]
    
    for scenario in scenarios:
        await test_invalidation_query_scenario(driver, test_edges, scenario)


async def test_invalidation_query_scenario(driver, test_edges, scenario):
    """Test a specific invalidation query scenario."""
    
    limit = scenario["limit"]
    description = scenario["description"]
    
    print(f"\n🔬 Testing: {description} (limit={limit})")
    print("-" * 40)
    
    # Build the problematic query (exact copy from search_utils.py)
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
    
    query_params = {
        'edges': test_edges,
        'min_score': 0.7,
        'limit': limit
    }
    
    try:
        print(f"   Executing query with {len(test_edges)} UNWIND edges...")
        print(f"   Limit: {limit}, Min score: 0.7")
        
        # Execute the query with timing
        import time
        start_time = time.time()
        
        results, _, _ = await driver.execute_query(query, **query_params)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        print(f"   ✅ SUCCESS: Query completed in {execution_time:.2f}s")
        print(f"   📊 Results: {len(results)} edge groups returned")
        
        # Analyze results
        total_matches = sum(len(result.get('matches', [])) for result in results)
        print(f"   📈 Total matches across all groups: {total_matches}")
        
        if execution_time > 10:
            print(f"   ⚠️  SLOW: Query took {execution_time:.2f}s (>10s threshold)")
        
    except Exception as e:
        error_msg = str(e)
        print(f"   ❌ FAILED: {error_msg}")
        
        # Analyze the specific error
        if "Query's mem consumption exceeded capacity" in error_msg:
            print(f"   🔥 MEMORY EXHAUSTION detected at limit={limit}")
            print(f"   💡 This confirms the memory issue in the pipeline!")
            
        elif "Type mismatch" in error_msg and "Vectorf32" in error_msg:
            print(f"   🔧 VECTOR TYPE MISMATCH detected")
            print(f"   💡 Vector conversion issue confirmed!")
            
        # This is the critical finding - we've reproduced the issue!
        return False
    
    return True


async def run_memory_test():
    """Main test runner."""
    
    print("🧪 FalkorDB Memory Exhaustion Test")
    print("Reproducing the edge invalidation query failures")
    print("=" * 70)
    
    driver = FalkorDriver(
        host='localhost',
        port=6379,
        username='',
        password='',
        database='falkordb'
    )
    
    try:
        # Clear any existing test data
        print("🧹 Clearing existing test data...")
        await driver.execute_query("MATCH (n:Entity) WHERE n.group_id = 'test_group' DETACH DELETE n")
        
        # Create test data
        await create_test_data(driver, num_edges=200)
        
        # Run memory exhaustion tests
        await test_memory_exhaustion_scenarios(driver)
        
        print(f"\n📋 SUMMARY")
        print("=" * 30)
        print("This test reproduces the exact failing query from the ingestion pipeline.")
        print("If memory exhaustion occurs, it confirms the root cause of the 0% success rate.")
        
    except Exception as e:
        print(f"\n❌ Test framework error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await driver.close()


if __name__ == '__main__':
    asyncio.run(run_memory_test())