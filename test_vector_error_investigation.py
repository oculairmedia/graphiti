#!/usr/bin/env python3
"""
Comprehensive investigation of the FalkorDB vector type mismatch error
"""

import asyncio
import os
import sys
from typing import Any, List
import logging
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.graph_queries import get_vector_cosine_func_query

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def investigate_vector_error():
    """Deep investigation of the vector type mismatch issue"""
    
    driver = FalkorDriver(
        host='localhost',
        port=6379,
        database='graphiti_migration'
    )
    
    print("\n" + "="*80)
    print("FALKORDB VECTOR TYPE MISMATCH INVESTIGATION")
    print("="*80 + "\n")
    
    # Test 1: Check how vectors are stored in the database
    print("TEST 1: Checking how vectors are stored in existing edges")
    print("-" * 50)
    
    check_storage_query = """
    MATCH ()-[e:RELATES_TO]->()
    WHERE e.fact_embedding IS NOT NULL
    RETURN 
        e.uuid as uuid,
        e.fact_embedding as embedding,
        e.group_id as group_id
    LIMIT 3
    """
    
    try:
        results, _, _ = await driver.execute_query(check_storage_query)
        if results:
            for i, result in enumerate(results):
                embedding = result.get('embedding')
                print(f"\nEdge {i+1} (uuid: {result.get('uuid')[:8]}...):")
                print(f"  Group ID: {result.get('group_id')}")
                print(f"  Embedding type: {type(embedding)}")
                print(f"  Is list: {isinstance(embedding, list)}")
                if isinstance(embedding, list) and len(embedding) > 0:
                    print(f"  Length: {len(embedding)}")
                    print(f"  First element type: {type(embedding[0])}")
                    print(f"  Sample values: {embedding[:3]}...")
        else:
            print("  No edges with embeddings found")
    except Exception as e:
        print(f"  Error checking storage: {e}")
    
    # Test 2: Test direct vector operations
    print("\n\nTEST 2: Testing direct vector operations")
    print("-" * 50)
    
    # Create a test vector
    test_vector = [0.1] * 1024
    
    # Test 2a: Can we compare a stored vector with a parameter vector?
    print("\n2a. Testing stored vector vs parameter vector:")
    test_query_2a = """
    MATCH ()-[e:RELATES_TO]->()
    WHERE e.fact_embedding IS NOT NULL
    WITH e, (2 - vec.cosineDistance(e.fact_embedding, vecf32($test_vector)))/2 AS score
    RETURN e.uuid, score
    LIMIT 1
    """
    
    try:
        results, _, _ = await driver.execute_query(test_query_2a, test_vector=test_vector)
        print("  ✅ Query succeeded with e.fact_embedding vs vecf32($test_vector)")
    except Exception as e:
        print(f"  ❌ Query failed: {e}")
        
        # Try wrapping both
        print("\n  Trying with both wrapped:")
        test_query_2a_wrapped = """
        MATCH ()-[e:RELATES_TO]->()
        WHERE e.fact_embedding IS NOT NULL
        WITH e, (2 - vec.cosineDistance(vecf32(e.fact_embedding), vecf32($test_vector)))/2 AS score
        RETURN e.uuid, score
        LIMIT 1
        """
        try:
            results, _, _ = await driver.execute_query(test_query_2a_wrapped, test_vector=test_vector)
            print("    ✅ Query succeeded with both wrapped!")
        except Exception as e2:
            print(f"    ❌ Still failed: {e2}")
    
    # Test 3: The actual failing query pattern
    print("\n\nTEST 3: Testing the exact failing pattern (UNWIND with edge invalidation)")
    print("-" * 50)
    
    # Get an actual edge to test with
    get_edge_query = """
    MATCH (n:Entity)-[e:RELATES_TO]->(m:Entity)
    WHERE e.fact_embedding IS NOT NULL
    RETURN 
        e.uuid as uuid,
        n.uuid as source_uuid,
        m.uuid as target_uuid,
        e.group_id as group_id,
        e.fact_embedding as fact_embedding
    LIMIT 1
    """
    
    try:
        results, _, _ = await driver.execute_query(get_edge_query)
        if results and len(results) > 0:
            sample_edge = results[0]
            print(f"\nUsing edge: {sample_edge['uuid'][:8]}...")
            print(f"  Source: {sample_edge['source_uuid'][:8]}...")
            print(f"  Target: {sample_edge['target_uuid'][:8]}...")
            print(f"  Group: {sample_edge['group_id']}")
            
            # Create test edges data similar to production
            test_edges = [{
                'uuid': 'test-edge-1',
                'source_node_uuid': sample_edge['source_uuid'],
                'target_node_uuid': sample_edge['target_uuid'],
                'group_id': sample_edge['group_id'],
                'fact_embedding': test_vector  # Python list
            }]
            
            # Test 3a: The production query pattern
            print("\n3a. Testing production query pattern:")
            cosine_func = get_vector_cosine_func_query('e.fact_embedding', 'edge.fact_embedding', 'falkordb')
            print(f"  Cosine function: {cosine_func}")
            
            production_query = """
            UNWIND $edges AS edge
            MATCH (n:Entity)-[e:RELATES_TO {group_id: edge.group_id}]->(m:Entity)
            WHERE n.uuid IN [edge.source_node_uuid, edge.target_node_uuid] 
               OR m.uuid IN [edge.target_node_uuid, edge.source_node_uuid]
            WITH edge, e, """ + cosine_func + """ AS score
            WHERE score > 0.0
            RETURN edge.uuid AS search_edge_uuid, e.uuid as matched_uuid, score
            LIMIT 5
            """
            
            try:
                results, _, _ = await driver.execute_query(
                    production_query,
                    edges=test_edges
                )
                print(f"  ✅ Production query succeeded!")
                print(f"     Results: {len(results)} matches")
                for r in results:
                    print(f"     - Score: {r.get('score', 'N/A')}")
            except Exception as e:
                print(f"  ❌ Production query failed: {e}")
                
                # Test 3b: Try different wrapping strategies
                print("\n3b. Testing different wrapping strategies:")
                
                # Strategy 1: Wrap both
                print("\n  Strategy 1: Wrap both vectors")
                strategy1_query = """
                UNWIND $edges AS edge
                MATCH (n:Entity)-[e:RELATES_TO {group_id: edge.group_id}]->(m:Entity)
                WHERE n.uuid IN [edge.source_node_uuid, edge.target_node_uuid] 
                   OR m.uuid IN [edge.target_node_uuid, edge.source_node_uuid]
                WITH edge, e, (2 - vec.cosineDistance(vecf32(e.fact_embedding), vecf32(edge.fact_embedding)))/2 AS score
                WHERE score > 0.0
                RETURN edge.uuid AS search_edge_uuid, e.uuid as matched_uuid, score
                LIMIT 5
                """
                
                try:
                    results, _, _ = await driver.execute_query(
                        strategy1_query,
                        edges=test_edges
                    )
                    print("    ✅ Strategy 1 succeeded (both wrapped)!")
                except Exception as e1:
                    print(f"    ❌ Strategy 1 failed: {e1}")
                
                # Strategy 2: Wrap only edge.fact_embedding
                print("\n  Strategy 2: Wrap only edge.fact_embedding")
                strategy2_query = """
                UNWIND $edges AS edge
                MATCH (n:Entity)-[e:RELATES_TO {group_id: edge.group_id}]->(m:Entity)
                WHERE n.uuid IN [edge.source_node_uuid, edge.target_node_uuid] 
                   OR m.uuid IN [edge.target_node_uuid, edge.source_node_uuid]
                WITH edge, e, (2 - vec.cosineDistance(e.fact_embedding, vecf32(edge.fact_embedding)))/2 AS score
                WHERE score > 0.0
                RETURN edge.uuid AS search_edge_uuid, e.uuid as matched_uuid, score
                LIMIT 5
                """
                
                try:
                    results, _, _ = await driver.execute_query(
                        strategy2_query,
                        edges=test_edges
                    )
                    print("    ✅ Strategy 2 succeeded (only edge.fact_embedding wrapped)!")
                except Exception as e2:
                    print(f"    ❌ Strategy 2 failed: {e2}")
                
                # Strategy 3: No wrapping
                print("\n  Strategy 3: No wrapping")
                strategy3_query = """
                UNWIND $edges AS edge
                MATCH (n:Entity)-[e:RELATES_TO {group_id: edge.group_id}]->(m:Entity)
                WHERE n.uuid IN [edge.source_node_uuid, edge.target_node_uuid] 
                   OR m.uuid IN [edge.target_node_uuid, edge.source_node_uuid]
                WITH edge, e, (2 - vec.cosineDistance(e.fact_embedding, edge.fact_embedding))/2 AS score
                WHERE score > 0.0
                RETURN edge.uuid AS search_edge_uuid, e.uuid as matched_uuid, score
                LIMIT 5
                """
                
                try:
                    results, _, _ = await driver.execute_query(
                        strategy3_query,
                        edges=test_edges
                    )
                    print("    ✅ Strategy 3 succeeded (no wrapping)!")
                except Exception as e3:
                    print(f"    ❌ Strategy 3 failed: {e3}")
        else:
            print("  No edges with embeddings found to test")
    except Exception as e:
        print(f"  Error getting test edge: {e}")
    
    # Test 4: Check if the issue is specific to certain conditions
    print("\n\nTEST 4: Testing edge cases and conditions")
    print("-" * 50)
    
    # Test 4a: Empty result set
    print("\n4a. Testing with non-existent edges (should return empty, not error):")
    empty_test_edges = [{
        'uuid': 'non-existent',
        'source_node_uuid': 'fake-node-1',
        'target_node_uuid': 'fake-node-2',
        'group_id': 'non-existent-group',
        'fact_embedding': test_vector
    }]
    
    empty_query = """
    UNWIND $edges AS edge
    MATCH (n:Entity)-[e:RELATES_TO {group_id: edge.group_id}]->(m:Entity)
    WHERE n.uuid IN [edge.source_node_uuid, edge.target_node_uuid]
    RETURN count(e) as match_count
    """
    
    try:
        results, _, _ = await driver.execute_query(empty_query, edges=empty_test_edges)
        print(f"  ✅ Empty query succeeded: {results[0]['match_count']} matches (expected 0)")
    except Exception as e:
        print(f"  ❌ Empty query failed: {e}")
    
    # Test 4b: Check if error only happens when there ARE matches
    print("\n4b. Checking if error only occurs with actual matches:")
    
    # First, count how many edges exist
    count_query = """
    MATCH ()-[e:RELATES_TO]->()
    WHERE e.fact_embedding IS NOT NULL
    RETURN count(e) as total_edges
    """
    
    try:
        results, _, _ = await driver.execute_query(count_query)
        total_edges = results[0]['total_edges'] if results else 0
        print(f"  Total edges with embeddings: {total_edges}")
        
        if total_edges > 0:
            # Get a few edges to test
            sample_query = """
            MATCH (n:Entity)-[e:RELATES_TO]->(m:Entity)
            WHERE e.fact_embedding IS NOT NULL
            RETURN DISTINCT e.group_id as group_id
            LIMIT 5
            """
            
            results, _, _ = await driver.execute_query(sample_query)
            if results:
                print(f"  Found {len(results)} distinct group_ids")
                for result in results:
                    print(f"    - {result['group_id']}")
    except Exception as e:
        print(f"  Error counting edges: {e}")
    
    await driver.close()
    
    print("\n" + "="*80)
    print("INVESTIGATION COMPLETE")
    print("="*80 + "\n")
    
    print("FINDINGS:")
    print("-" * 50)
    print("1. The error occurs when FalkorDB tries to compare vectors in specific contexts")
    print("2. The issue is related to how UNWIND parameters interact with stored vectors")
    print("3. The working strategy will be identified from the test results above")
    print("\nRECOMMENDATION:")
    print("Based on which strategy succeeded, update get_vector_cosine_func_query accordingly")

if __name__ == "__main__":
    asyncio.run(investigate_vector_error())