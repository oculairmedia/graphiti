#!/usr/bin/env python3
"""
Test script to validate FalkorDB vector wrapping logic
"""

import asyncio
import os
import sys
from typing import Any
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.graph_queries import get_vector_cosine_func_query

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_vector_wrapping():
    """Test vector wrapping logic with FalkorDB"""
    
    # Test the wrapping logic
    test_cases = [
        ('e.fact_embedding', 'edge.fact_embedding', 'Edge invalidation'),
        ('n.name_embedding', 'node.name_embedding', 'Node deduplication'),
        ('r.fact_embedding', '$search_vector', 'Edge search'),
        ('n.name_embedding', '$search_vector', 'Node search'),
    ]
    
    print("\n=== Testing get_vector_cosine_func_query ===\n")
    
    for vec1, vec2, description in test_cases:
        result = get_vector_cosine_func_query(vec1, vec2, 'falkordb')
        print(f"{description}:")
        print(f"  Input: ({vec1}, {vec2})")
        print(f"  Output: {result}")
        print(f"  Analysis:")
        
        # Check if vec1 is wrapped
        vec1_wrapped = f'vecf32({vec1})' in result
        print(f"    {vec1} wrapped: {vec1_wrapped}")
        
        # Check if vec2 is wrapped
        vec2_wrapped = f'vecf32({vec2})' in result
        print(f"    {vec2} wrapped: {vec2_wrapped}")
        print()
    
    # Now test with actual FalkorDB connection if available
    try:
        print("\n=== Testing with FalkorDB Connection ===\n")
        
        driver = FalkorDriver(
            host=os.getenv('FALKORDB_HOST', 'localhost'),
            port=int(os.getenv('FALKORDB_PORT', 6379)),
            database='test_vectors'
        )
        
        # Create a test vector (1024 dimensions like our embeddings)
        test_vector = [0.1] * 1024
        
        # Test query 1: Direct vector parameter
        print("Test 1: Direct vector parameter ($search_vector)")
        query1 = """
        MATCH (e:TestEntity)
        WHERE """ + get_vector_cosine_func_query('e.embedding', '$search_vector', 'falkordb') + """ > 0.5
        RETURN e.name
        """
        print(f"Query: {query1}")
        
        try:
            # This should work because $search_vector gets wrapped
            results, _, _ = await driver.execute_query(
                query1,
                search_vector=test_vector
            )
            print("✅ Query executed successfully")
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print()
        
        # Test query 2: UNWIND parameter
        print("Test 2: UNWIND parameter (edge.fact_embedding)")
        
        # Create test edges data similar to what we send in the actual code
        test_edges = [
            {
                'uuid': 'test-edge-1',
                'source_node_uuid': 'node-1',
                'target_node_uuid': 'node-2',
                'group_id': 'test',
                'fact_embedding': test_vector
            }
        ]
        
        query2 = """
        UNWIND $edges AS edge
        MATCH (n:Entity)-[e:RELATES_TO {group_id: edge.group_id}]->(m:Entity)
        WITH e, edge, """ + get_vector_cosine_func_query('e.fact_embedding', 'edge.fact_embedding', 'falkordb') + """ AS score
        WHERE score > 0.5
        RETURN e.uuid, score
        """
        print(f"Query: {query2}")
        print(f"Cosine function: {get_vector_cosine_func_query('e.fact_embedding', 'edge.fact_embedding', 'falkordb')}")
        
        try:
            results, _, _ = await driver.execute_query(
                query2,
                edges=test_edges
            )
            print("✅ Query executed successfully")
        except Exception as e:
            print(f"❌ Error: {e}")
            
            # Try alternative approach - wrap e.fact_embedding too
            print("\nTrying alternative: Wrap both vectors")
            query2_alt = """
            UNWIND $edges AS edge
            MATCH (n:Entity)-[e:RELATES_TO {group_id: edge.group_id}]->(m:Entity)
            WITH e, edge, (2 - vec.cosineDistance(vecf32(e.fact_embedding), vecf32(edge.fact_embedding)))/2 AS score
            WHERE score > 0.5
            RETURN e.uuid, score
            """
            print(f"Alternative query with both wrapped: {query2_alt}")
            
            try:
                results, _, _ = await driver.execute_query(
                    query2_alt,
                    edges=test_edges
                )
                print("✅ Alternative query executed successfully!")
                print("⚠️  This means e.fact_embedding ALSO needs wrapping!")
            except Exception as e2:
                print(f"❌ Alternative also failed: {e2}")
        
        await driver.close()
        
    except Exception as e:
        print(f"Could not connect to FalkorDB: {e}")
        print("Skipping connection tests")

    print("\n=== Analysis Complete ===\n")
    
    # Print conclusion
    print("CONCLUSION:")
    print("-" * 50)
    print("The issue appears to be that when FalkorDB retrieves e.fact_embedding")
    print("from the database in a query context with UNWIND parameters,")
    print("it may be returning it as a List rather than keeping it as Vectorf32.")
    print("This could be a FalkorDB-specific behavior where vectors need")
    print("explicit conversion in certain query contexts.")
    print()
    print("POTENTIAL FIX:")
    print("We may need to wrap BOTH vectors when one comes from UNWIND,")
    print("or detect when we're in an UNWIND context and wrap accordingly.")

if __name__ == "__main__":
    asyncio.run(test_vector_wrapping())