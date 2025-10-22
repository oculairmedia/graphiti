#!/usr/bin/env python3
"""
Test script to reproduce and verify the fix for the FalkorDB vector type mismatch error.
"""
import asyncio
import logging
import sys

# Import the necessary modules
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.search.search_utils import (
    get_edge_invalidation_candidates_batch,
)
from graphiti_core.search.search import SearchFilters
from graphiti_core.edges import EntityEdge

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_edge_invalidation_fix():
    """Test the edge invalidation with vector embeddings to reproduce the type mismatch error."""

    print("🔍 Testing FalkorDB Edge Invalidation Fix")
    print("=" * 50)

    # Connect to FalkorDB
    driver = FalkorDriver(host='falkordb', port=6379, database='graphiti_migration')

    try:
        await driver.connect()
        print("✅ Connected to FalkorDB")

        # Create test edge objects with vector embeddings
        test_edges = [
            EntityEdge(
                uuid='test-edge-1',
                source_node_uuid='node-1',
                target_node_uuid='node-2',
                group_id='test_group',
                name='test_relation_1',
                fact='Test fact 1',
                fact_embedding=[0.1, 0.2, 0.3, 0.4, 0.5]  # This should cause the type mismatch
            ),
            EntityEdge(
                uuid='test-edge-2',
                source_node_uuid='node-2',
                target_node_uuid='node-3',
                group_id='test_group',
                name='test_relation_2',
                fact='Test fact 2',
                fact_embedding=[0.6, 0.7, 0.8, 0.9, 1.0]  # This should cause the type mismatch
            )
        ]

        print(f"📋 Created {len(test_edges)} test edges with vector embeddings")

        # Set up search filters
        search_filter = SearchFilters()

        print("🚀 Running edge invalidation query...")

        # This should reproduce the "Type mismatch: expected Null or Vectorf32 but was List" error
        # before the fix, and succeed after the fix
        try:
            invalidation_results = await get_edge_invalidation_candidates_batch(
                driver=driver,
                edges=test_edges,
                search_filter=search_filter,
                min_score=0.0,
                limit=5
            )

            print("✅ SUCCESS: Edge invalidation completed without type mismatch error!")
            print(f"📊 Results: Found {len(invalidation_results)} invalidation candidate groups")

            # Print some details about the results
            for i, candidates in enumerate(invalidation_results):
                print(f"   Edge {i+1}: {len(candidates)} invalidation candidates")

        except Exception as e:
            print(f"❌ FAILED: Edge invalidation failed with error: {e}")

            # Check if it's the specific vector type mismatch error
            if "Type mismatch: expected Null or Vectorf32 but was List" in str(e):
                print("💡 This is the expected error before the fix is applied!")
                print("   The fix should wrap edge.fact_embedding with vecf32() in the query.")
            else:
                print(f"⚠️  This is a different error: {type(e).__name__}")

            return False

    except Exception as e:
        print(f"💥 Connection or setup error: {e}")
        return False

    finally:
        await driver.disconnect()
        print("🔌 Disconnected from FalkorDB")

    return True

async def test_query_wrapping():
    """Test the query wrapping logic independently."""

    print("\n🔧 Testing Query Wrapping Logic")
    print("=" * 40)

    # Import the function we fixed
    from graphiti_core.driver.falkordb_driver import _wrap_vector_params_in_query

    # Test query that should trigger the wrapping
    test_query = """
    UNWIND $edges AS edge
    MATCH (n:Entity {uuid: edge.source_node_uuid})-[e:RELATES_TO {group_id: edge.group_id}]-(m:Entity {uuid: edge.target_node_uuid})
    WITH e, edge, (2 - vec.cosineDistance(e.fact_embedding, edge.fact_embedding))/2 AS score
    WHERE score > $min_score
    RETURN edge.uuid AS search_edge_uuid
    """

    test_params = {
        'edges': [
            {
                'uuid': 'test-edge-1',
                'source_node_uuid': 'node-1',
                'target_node_uuid': 'node-2',
                'group_id': 'test_group',
                'fact_embedding': [0.1, 0.2, 0.3, 0.4, 0.5]
            }
        ],
        'min_score': 0.5
    }

    print("📝 Original query contains:")
    print("   - edge.fact_embedding (should be wrapped)")
    print("   - e.fact_embedding (should NOT be wrapped - it's a graph property)")

    # Apply the wrapping
    wrapped_query = _wrap_vector_params_in_query(test_query, test_params)

    print("\n🔍 Checking if edge.fact_embedding was wrapped...")

    if 'vecf32(edge.fact_embedding)' in wrapped_query:
        print("✅ SUCCESS: edge.fact_embedding was wrapped with vecf32()")
    else:
        print("❌ FAILED: edge.fact_embedding was NOT wrapped")

    if 'vecf32(e.fact_embedding)' not in wrapped_query and 'e.fact_embedding' in wrapped_query:
        print("✅ SUCCESS: e.fact_embedding was NOT wrapped (correct - it's a graph property)")
    else:
        print("❌ FAILED: e.fact_embedding wrapping behavior is incorrect")

    print(f"\n📄 Wrapped query snippet:")
    # Show the relevant part
    lines = wrapped_query.split('\n')
    for line in lines:
        if 'vec.cosineDistance' in line:
            print(f"   {line.strip()}")

    return 'vecf32(edge.fact_embedding)' in wrapped_query

async def main():
    """Main test function."""

    print("🧪 FalkorDB Vector Type Mismatch Fix Test Suite")
    print("=" * 60)

    # Test 1: Query wrapping logic
    wrapping_success = await test_query_wrapping()

    # Test 2: Actual edge invalidation
    invalidation_success = await test_edge_invalidation_fix()

    print("\n📊 Test Results Summary")
    print("=" * 30)
    print(f"Query Wrapping Logic: {'✅ PASS' if wrapping_success else '❌ FAIL'}")
    print(f"Edge Invalidation:    {'✅ PASS' if invalidation_success else '❌ FAIL'}")

    if wrapping_success and invalidation_success:
        print("\n🎉 All tests passed! The fix appears to be working.")
        return 0
    else:
        print("\n💥 Some tests failed. Check the output above for details.")
        return 1

if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
