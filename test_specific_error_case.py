#!/usr/bin/env python3
"""
Test the specific case that's failing in production
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
from graphiti_core.search.search_utils import get_edge_invalidation_candidates
from graphiti_core.edges import EntityEdge
from graphiti_core.search.search_filters import SearchFilters

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_specific_error():
    """Test the exact function that's failing"""
    
    driver = FalkorDriver(
        host='localhost',
        port=6379,
        database='graphiti_migration'
    )
    
    print("\n" + "="*80)
    print("TESTING EXACT PRODUCTION FAILURE CASE")
    print("="*80 + "\n")
    
    # First, get some real edges from the database
    print("Step 1: Getting real edges from database")
    print("-" * 50)
    
    get_edges_query = """
    MATCH (n:Entity)-[e:RELATES_TO]->(m:Entity)
    WHERE e.fact_embedding IS NOT NULL
    RETURN 
        e.uuid as uuid,
        n.uuid as source_node_uuid,
        m.uuid as target_node_uuid,
        e.group_id as group_id,
        e.name as name,
        e.fact as fact,
        e.fact_embedding as fact_embedding,
        e.created_at as created_at,
        e.expired_at as expired_at,
        e.valid_at as valid_at,
        e.invalid_at as invalid_at,
        e.episodes as episodes
    LIMIT 3
    """
    
    try:
        results, _, _ = await driver.execute_query(get_edges_query)
        if results:
            print(f"Found {len(results)} edges with embeddings")
            
            # Create EntityEdge objects from the results
            test_edges = []
            for result in results:
                # Check the type of fact_embedding when retrieved
                fact_embedding = result.get('fact_embedding')
                print(f"\nEdge {result['uuid'][:8]}...:")
                print(f"  fact_embedding type: {type(fact_embedding)}")
                print(f"  fact_embedding is list: {isinstance(fact_embedding, list)}")
                if isinstance(fact_embedding, list):
                    print(f"  fact_embedding length: {len(fact_embedding)}")
                
                edge = EntityEdge(
                    uuid=result['uuid'],
                    source_node_uuid=result['source_node_uuid'],
                    target_node_uuid=result['target_node_uuid'],
                    group_id=result['group_id'],
                    name=result.get('name', ''),
                    fact=result.get('fact', ''),
                    fact_embedding=fact_embedding,
                    created_at=result.get('created_at'),
                    expired_at=result.get('expired_at'),
                    valid_at=result.get('valid_at'),
                    invalid_at=result.get('invalid_at'),
                    episodes=result.get('episodes', [])
                )
                test_edges.append(edge)
            
            # Test the actual function
            print("\nStep 2: Testing get_edge_invalidation_candidates function")
            print("-" * 50)
            
            search_filter = SearchFilters(group_ids=[test_edges[0].group_id])
            
            try:
                print("Calling get_edge_invalidation_candidates...")
                invalidation_candidates = await get_edge_invalidation_candidates(
                    driver=driver,
                    edges=test_edges[:1],  # Test with just one edge
                    search_filter=search_filter,
                    min_score=0.0
                )
                print(f"✅ SUCCESS! Function returned {len(invalidation_candidates)} candidates")
                if invalidation_candidates:
                    print(f"   First candidate has {len(invalidation_candidates[0])} matches")
            except Exception as e:
                print(f"❌ FAILED with error: {e}")
                print(f"   Error type: {type(e).__name__}")
                
                # Now test with a manually created edge that has a Python list embedding
                print("\nStep 3: Testing with manually created edge")
                print("-" * 50)
                
                # Create a test vector as a Python list
                test_vector = [0.1] * 1024
                
                manual_edge = EntityEdge(
                    uuid='test-edge-manual',
                    source_node_uuid=test_edges[0].source_node_uuid,
                    target_node_uuid=test_edges[0].target_node_uuid,
                    group_id=test_edges[0].group_id,
                    name='Test Edge',
                    fact='Test fact',
                    fact_embedding=test_vector,  # Python list
                    created_at=test_edges[0].created_at,
                    expired_at=None,
                    valid_at=test_edges[0].valid_at,
                    invalid_at=None,
                    episodes=[]
                )
                
                try:
                    print("Testing with manually created edge...")
                    invalidation_candidates = await get_edge_invalidation_candidates(
                        driver=driver,
                        edges=[manual_edge],
                        search_filter=search_filter,
                        min_score=0.0
                    )
                    print(f"✅ Manual edge test succeeded!")
                except Exception as e2:
                    print(f"❌ Manual edge test also failed: {e2}")
                    
                    # Check what model_dump produces
                    print("\nStep 4: Checking model_dump output")
                    print("-" * 50)
                    dumped = manual_edge.model_dump()
                    print(f"model_dump keys: {list(dumped.keys())}")
                    print(f"fact_embedding type after model_dump: {type(dumped.get('fact_embedding'))}")
                    print(f"fact_embedding is list: {isinstance(dumped.get('fact_embedding'), list)}")
                    
        else:
            print("No edges with embeddings found")
    except Exception as e:
        print(f"Error getting edges: {e}")
    
    # Test the raw query that's being generated
    print("\nStep 5: Testing raw query generation")
    print("-" * 50)
    
    cosine_func = get_vector_cosine_func_query('e.fact_embedding', 'edge.fact_embedding', 'falkordb')
    print(f"Generated cosine function: {cosine_func}")
    
    # Check if the issue is with NULL embeddings
    print("\nStep 6: Checking for NULL embedding handling")
    print("-" * 50)
    
    null_check_query = """
    MATCH ()-[e:RELATES_TO]->()
    RETURN 
        count(CASE WHEN e.fact_embedding IS NULL THEN 1 END) as null_count,
        count(CASE WHEN e.fact_embedding IS NOT NULL THEN 1 END) as not_null_count,
        count(e) as total_count
    """
    
    try:
        results, _, _ = await driver.execute_query(null_check_query)
        if results:
            result = results[0]
            print(f"NULL embeddings: {result['null_count']}")
            print(f"NOT NULL embeddings: {result['not_null_count']}")
            print(f"Total edges: {result['total_count']}")
            
            if result['null_count'] > 0:
                print("\n⚠️  There are edges with NULL embeddings!")
                print("   This might cause issues if not handled properly")
    except Exception as e:
        print(f"Error checking NULL embeddings: {e}")
    
    await driver.close()
    
    print("\n" + "="*80)
    print("ANALYSIS COMPLETE")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(test_specific_error())