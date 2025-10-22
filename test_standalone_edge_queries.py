#!/usr/bin/env python3
"""
Standalone test for edge invalidation queries to isolate memory consumption and vector type issues.
"""

import asyncio
import os
import sys
from typing import Any

# Add the current directory to the path so we can import graphiti_core
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.graph_queries import get_vector_cosine_func_query
from graphiti_core.edges import EntityEdge
from graphiti_core.search.search_filters import SearchFilters


async def test_edge_invalidation_query():
    """Test the edge invalidation query that's causing memory exhaustion."""
    
    # Initialize FalkorDB connection
    driver = FalkorDriver(
        host='localhost',
        port=6379,
        username='',  # No auth for FalkorDB
        password='',
        database='falkordb'
    )
    
    print("🔍 Testing Edge Invalidation Query Components")
    print("=" * 60)
    
    try:
        # First, let's check how many edges we have in total
        print("\n1️⃣ Checking total edge count...")
        count_query = "MATCH ()-[e:RELATES_TO]->() RETURN count(e) as edge_count"
        result, _, _ = await driver.execute_query(count_query)
        total_edges = result[0]['edge_count'] if result else 0
        print(f"   Total edges in database: {total_edges:,}")
        
        # Get a small sample of edges to test with
        print("\n2️⃣ Fetching sample edges for testing...")
        sample_query = """
        MATCH ()-[e:RELATES_TO]->() 
        WHERE e.fact_embedding IS NOT NULL 
        RETURN e.uuid, e.source_node_uuid, e.target_node_uuid, e.group_id, e.fact_embedding
        LIMIT 5
        """
        sample_result, _, _ = await driver.execute_query(sample_query)
        
        if not sample_result:
            print("   ❌ No edges with embeddings found!")
            return
            
        print(f"   Found {len(sample_result)} sample edges with embeddings")
        
        # Create mock EntityEdge objects for testing
        test_edges = []
        for edge_data in sample_result[:2]:  # Test with just 2 edges first
            # Create a minimal EntityEdge mock
            edge = type('MockEdge', (), {
                'uuid': edge_data['e.uuid'],
                'source_node_uuid': edge_data['e.source_node_uuid'],
                'target_node_uuid': edge_data['e.target_node_uuid'],
                'group_id': edge_data['e.group_id'],
                'fact_embedding': edge_data['e.fact_embedding'],
                'model_dump': lambda self: {
                    'uuid': self.uuid,
                    'source_node_uuid': self.source_node_uuid,
                    'target_node_uuid': self.target_node_uuid,
                    'group_id': self.group_id,
                    'fact_embedding': self.fact_embedding
                }
            })()
            test_edges.append(edge)
        
        print(f"   Created {len(test_edges)} test edge objects")
        
        # Test the vector cosine function generation
        print("\n3️⃣ Testing vector cosine function generation...")
        cosine_func = get_vector_cosine_func_query('e.fact_embedding', 'edge.fact_embedding', 'falkordb')
        print(f"   Generated cosine function: {cosine_func}")
        
        # Test with small limit first
        print("\n4️⃣ Testing edge invalidation query with small limit...")
        await test_invalidation_query_with_limit(driver, test_edges, limit=10)
        
        # Test with medium limit
        print("\n5️⃣ Testing edge invalidation query with medium limit...")
        await test_invalidation_query_with_limit(driver, test_edges, limit=50)
        
        # Test with larger limit (this might cause memory issues)
        print("\n6️⃣ Testing edge invalidation query with larger limit...")
        await test_invalidation_query_with_limit(driver, test_edges, limit=200)
        
        print("\n✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await driver.close()


async def test_invalidation_query_with_limit(driver, test_edges, limit=50):
    """Test the invalidation query with a specific limit."""
    
    print(f"   Testing with limit={limit}...")
    
    # Prepare query parameters
    query_params = {
        'min_score': 0.7,  # Default minimum score
        'limit': limit
    }
    
    # Convert edges to the format expected by the query
    edges_data = [edge.model_dump() for edge in test_edges]
    
    # Log embedding info
    if edges_data and edges_data[0].get('fact_embedding'):
        embedding = edges_data[0]['fact_embedding']
        print(f"     Edge embedding type: {type(embedding)}")
        print(f"     Edge embedding is list: {isinstance(embedding, list)}")
        if isinstance(embedding, list):
            print(f"     Edge embedding length: {len(embedding)}")
    
    # Build the query (simplified version of the failing query)
    cosine_func = get_vector_cosine_func_query('e.fact_embedding', 'edge.fact_embedding', driver.provider)
    
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
    
    try:
        # Execute the query
        results, _, _ = await driver.execute_query(
            query,
            params=query_params,
            edges=edges_data,
            limit=limit,
            min_score=0.7,
            routing_='r',
        )
        
        print(f"     ✅ Query executed successfully, returned {len(results)} results")
        
        # Check result structure
        for i, result in enumerate(results[:2]):  # Show first 2 results
            matches = result.get('matches', [])
            print(f"     Result {i+1}: {len(matches)} matches for edge {result.get('search_edge_uuid')}")
            
    except Exception as e:
        error_msg = str(e)
        print(f"     ❌ Query failed: {error_msg}")
        
        # Analyze the error
        if "Query's mem consumption exceeded capacity" in error_msg:
            print(f"     📊 Memory exhaustion detected at limit={limit}")
        elif "Type mismatch" in error_msg and "Vectorf32" in error_msg:
            print(f"     🔧 Vector type mismatch detected")
        elif "vecf32" in error_msg.lower():
            print(f"     🔧 Vector conversion issue detected")
        
        raise


async def test_simple_vector_operations():
    """Test basic vector operations to isolate type conversion issues."""
    
    print("\n🧪 Testing Simple Vector Operations")
    print("=" * 40)
    
    driver = FalkorDriver(
        host='localhost',
        port=6379,
        username='',
        password='',
        database='falkordb'
    )
    
    try:
        # Test 1: Basic vector parameter
        print("1️⃣ Testing basic vector parameter conversion...")
        test_vector = [0.1] * 2560  # 2560-dimensional test vector
        
        simple_query = "RETURN vecf32($test_vec) as converted_vector"
        result, _, _ = await driver.execute_query(simple_query, test_vec=test_vector)
        print("   ✅ Basic vector parameter conversion works")
        
        # Test 2: UNWIND with vector
        print("2️⃣ Testing UNWIND with vector parameters...")
        test_data = [{'vec': test_vector, 'id': 'test1'}]
        
        unwind_query = "UNWIND $data AS item RETURN item.id, vecf32(item.vec) as converted"
        result, _, _ = await driver.execute_query(unwind_query, data=test_data)
        print("   ✅ UNWIND vector conversion works")
        
        # Test 3: Vector similarity with UNWIND
        print("3️⃣ Testing vector similarity with UNWIND...")
        similarity_query = """
        UNWIND $data AS item 
        MATCH ()-[e:RELATES_TO]->() 
        WHERE e.fact_embedding IS NOT NULL
        WITH item, e, (2 - vec.cosineDistance(e.fact_embedding, vecf32(item.vec)))/2 AS score
        RETURN item.id, score
        LIMIT 5
        """
        result, _, _ = await driver.execute_query(similarity_query, data=test_data)
        print(f"   ✅ Vector similarity with UNWIND works, got {len(result)} results")
        
    except Exception as e:
        print(f"   ❌ Vector operation test failed: {e}")
        raise
    finally:
        await driver.close()


if __name__ == '__main__':
    print("🧪 Standalone Edge Invalidation Query Test")
    print("This test isolates the queries causing memory exhaustion and type mismatches")
    print()
    
    # Run the main test
    asyncio.run(test_edge_invalidation_query())
    
    print("\n" + "=" * 80)
    
    # Run vector operation tests
    asyncio.run(test_simple_vector_operations())