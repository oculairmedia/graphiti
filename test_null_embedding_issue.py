#!/usr/bin/env python3
"""
Test if NULL embeddings are causing the vector type mismatch error
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

async def test_null_embedding_issue():
    """Test if NULL embeddings cause the vector type mismatch"""
    
    driver = FalkorDriver(
        host='localhost',
        port=6379,
        database='graphiti_migration'
    )
    
    print("\n" + "="*80)
    print("NULL EMBEDDING VECTOR TYPE MISMATCH INVESTIGATION")
    print("="*80 + "\n")
    
    # Create a test vector
    test_vector = [0.1] * 1024
    
    # Test 1: Find edges with NULL embeddings in specific groups
    print("TEST 1: Analyzing NULL embeddings by group")
    print("-" * 50)
    
    null_analysis_query = """
    MATCH ()-[e:RELATES_TO]->()
    RETURN 
        e.group_id as group_id,
        count(CASE WHEN e.fact_embedding IS NULL THEN 1 END) as null_count,
        count(CASE WHEN e.fact_embedding IS NOT NULL THEN 1 END) as not_null_count
    ORDER BY null_count DESC
    LIMIT 10
    """
    
    try:
        results, _, _ = await driver.execute_query(null_analysis_query)
        print("Group-wise NULL embedding distribution:")
        for result in results:
            print(f"  {result['group_id']}: NULL={result['null_count']}, NOT NULL={result['not_null_count']}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Test 2: Test UNWIND with edges that might encounter NULLs
    print("\n\nTEST 2: Testing UNWIND query with potential NULL encounters")
    print("-" * 50)
    
    # Get an edge from a group that has both NULL and non-NULL embeddings
    mixed_group_query = """
    MATCH (n:Entity)-[e:RELATES_TO]->(m:Entity)
    WHERE e.fact_embedding IS NOT NULL
    WITH e.group_id as group_id, count(e) as has_embedding
    MATCH ()-[e2:RELATES_TO {group_id: group_id}]->()
    WHERE e2.fact_embedding IS NULL
    WITH group_id, has_embedding, count(e2) as null_embedding
    WHERE has_embedding > 0 AND null_embedding > 0
    RETURN group_id
    LIMIT 1
    """
    
    try:
        results, _, _ = await driver.execute_query(mixed_group_query)
        if results:
            mixed_group = results[0]['group_id']
            print(f"Found mixed group: {mixed_group}")
            
            # Get a real edge from this group
            get_edge_query = """
            MATCH (n:Entity)-[e:RELATES_TO {group_id: $group_id}]->(m:Entity)
            WHERE e.fact_embedding IS NOT NULL
            RETURN 
                n.uuid as source_uuid,
                m.uuid as target_uuid,
                e.group_id as group_id
            LIMIT 1
            """
            
            results, _, _ = await driver.execute_query(get_edge_query, group_id=mixed_group)
            if results:
                edge_info = results[0]
                
                # Create test edge data
                test_edges = [{
                    'uuid': 'test-edge',
                    'source_node_uuid': edge_info['source_uuid'],
                    'target_node_uuid': edge_info['target_uuid'],
                    'group_id': edge_info['group_id'],
                    'fact_embedding': test_vector
                }]
                
                # Test the query that might encounter NULLs
                print(f"\nTesting UNWIND query for group {mixed_group}...")
                cosine_func = get_vector_cosine_func_query('e.fact_embedding', 'edge.fact_embedding', 'falkordb')
                
                test_query = """
                UNWIND $edges AS edge
                MATCH (n:Entity)-[e:RELATES_TO {group_id: edge.group_id}]->(m:Entity)
                WITH edge, e, """ + cosine_func + """ AS score
                WHERE score > 0.0
                RETURN 
                    edge.uuid AS search_edge_uuid,
                    e.uuid as matched_uuid,
                    e.fact_embedding IS NULL as is_null,
                    score
                LIMIT 10
                """
                
                try:
                    results, _, _ = await driver.execute_query(test_query, edges=test_edges)
                    print(f"  ✅ Query succeeded! Found {len(results)} matches")
                    for r in results:
                        print(f"     - UUID: {r['matched_uuid'][:8]}..., NULL: {r['is_null']}, Score: {r.get('score', 'N/A')}")
                except Exception as e:
                    print(f"  ❌ Query failed: {e}")
                    
                    # Try with NULL checking
                    print("\n  Testing with explicit NULL check...")
                    safe_query = """
                    UNWIND $edges AS edge
                    MATCH (n:Entity)-[e:RELATES_TO {group_id: edge.group_id}]->(m:Entity)
                    WHERE e.fact_embedding IS NOT NULL
                    WITH edge, e, """ + cosine_func + """ AS score
                    WHERE score > 0.0
                    RETURN 
                        edge.uuid AS search_edge_uuid,
                        e.uuid as matched_uuid,
                        score
                    LIMIT 10
                    """
                    
                    try:
                        results, _, _ = await driver.execute_query(safe_query, edges=test_edges)
                        print(f"    ✅ Query with NULL check succeeded! Found {len(results)} matches")
                    except Exception as e2:
                        print(f"    ❌ Still failed: {e2}")
        else:
            print("No mixed groups found")
    except Exception as e:
        print(f"Error finding mixed groups: {e}")
    
    # Test 3: Check what happens when comparing NULL with vector
    print("\n\nTEST 3: Direct NULL comparison test")
    print("-" * 50)
    
    null_comparison_query = """
    MATCH ()-[e:RELATES_TO]->()
    WHERE e.fact_embedding IS NULL
    WITH e, vecf32($test_vector) as vec
    RETURN e.uuid, vec IS NOT NULL as vec_exists
    LIMIT 1
    """
    
    try:
        results, _, _ = await driver.execute_query(null_comparison_query, test_vector=test_vector)
        print("  ✅ Can handle NULL embeddings with vector parameter")
    except Exception as e:
        print(f"  ❌ Error with NULL handling: {e}")
    
    # Test 4: Check if the issue is with the WHERE clause in the invalidation query
    print("\n\nTEST 4: Testing the exact invalidation query pattern")
    print("-" * 50)
    
    # Get some real edges to test with
    get_test_edges = """
    MATCH (n:Entity)-[e:RELATES_TO]->(m:Entity)
    WHERE e.fact_embedding IS NOT NULL
    RETURN 
        n.uuid as source_uuid,
        m.uuid as target_uuid,
        e.group_id as group_id
    LIMIT 1
    """
    
    try:
        results, _, _ = await driver.execute_query(get_test_edges)
        if results:
            edge = results[0]
            test_edges = [{
                'uuid': 'test-invalidation',
                'source_node_uuid': edge['source_uuid'],
                'target_node_uuid': edge['target_uuid'],
                'group_id': edge['group_id'],
                'fact_embedding': test_vector
            }]
            
            # This is the EXACT query from get_edge_invalidation_candidates
            cosine_func = get_vector_cosine_func_query('e.fact_embedding', 'edge.fact_embedding', 'falkordb')
            invalidation_query = """
            UNWIND $edges AS edge
            MATCH (n:Entity)-[e:RELATES_TO {group_id: edge.group_id}]->(m:Entity)
            WHERE n.uuid IN [edge.source_node_uuid, edge.target_node_uuid] OR m.uuid IN [edge.target_node_uuid, edge.source_node_uuid]
            WITH edge, e, """ + cosine_func + """ AS score
            WHERE score > $min_score
            WITH edge, e, score
            ORDER BY score DESC
            RETURN edge.uuid AS search_edge_uuid,
                collect({
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
                    invalid_at: e.invalid_at,
                    attributes: properties(e)
                })[..$limit] AS matches
            """
            
            print("Testing exact invalidation query...")
            try:
                results, _, _ = await driver.execute_query(
                    invalidation_query,
                    edges=test_edges,
                    min_score=0.0,
                    limit=10
                )
                print(f"  ✅ Exact invalidation query succeeded!")
                print(f"     Found {len(results)} result groups")
            except Exception as e:
                print(f"  ❌ Exact invalidation query failed: {e}")
                
                # Check if it's the collect that's causing issues
                print("\n  Testing without collect...")
                simple_query = """
                UNWIND $edges AS edge
                MATCH (n:Entity)-[e:RELATES_TO {group_id: edge.group_id}]->(m:Entity)
                WHERE n.uuid IN [edge.source_node_uuid, edge.target_node_uuid] OR m.uuid IN [edge.target_node_uuid, edge.source_node_uuid]
                WITH edge, e, """ + cosine_func + """ AS score
                WHERE score > $min_score
                RETURN edge.uuid, e.uuid, score
                LIMIT 10
                """
                
                try:
                    results, _, _ = await driver.execute_query(
                        simple_query,
                        edges=test_edges,
                        min_score=0.0
                    )
                    print(f"    ✅ Simple query without collect succeeded!")
                except Exception as e2:
                    print(f"    ❌ Simple query also failed: {e2}")
    except Exception as e:
        print(f"Error in exact query test: {e}")
    
    await driver.close()
    
    print("\n" + "="*80)
    print("INVESTIGATION COMPLETE")
    print("="*80 + "\n")
    
    print("KEY FINDINGS:")
    print("-" * 50)
    print("1. Many edges (2,961) have NULL embeddings")
    print("2. The query might fail when it encounters NULL embeddings")
    print("3. The solution may be to add WHERE e.fact_embedding IS NOT NULL")
    print("4. Or handle NULLs in the cosine similarity function")

if __name__ == "__main__":
    asyncio.run(test_null_embedding_issue())