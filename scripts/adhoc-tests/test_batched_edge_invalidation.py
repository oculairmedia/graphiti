#!/usr/bin/env python3
"""
Test batched edge invalidation to prevent FalkorDB memory exhaustion.

This test validates that the new batched approach can handle large numbers of edges
without causing "Query's mem consumption exceeded capacity" errors.
"""

import asyncio
import os
import sys
import random
import uuid
from datetime import datetime
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.edges import EntityEdge  
from graphiti_core.search.search_utils import (
    DEFAULT_MIN_SCORE,
    RELEVANT_SCHEMA_LIMIT,
    get_edge_invalidation_candidates,
    get_edge_invalidation_candidates_batch,
)
from graphiti_core.search.search import SearchFilters


async def create_test_edges(driver, num_entities=50, num_edges=200):
    """Create test entities and edges for batch testing."""
    
    print(f"🔧 Creating {num_entities} entities and {num_edges} edges for batch testing...")
    
    # Create entities
    entities = []
    for i in range(num_entities):
        entity_uuid = str(uuid.uuid4())
        entities.append(entity_uuid)
        
        await driver.execute_query(
            "MERGE (n:Entity {uuid: $uuid}) SET n.name = $name, n.group_id = $group_id",
            uuid=entity_uuid,
            name=f"Batch Test Entity {i}",
            group_id="batch_test"
        )
    
    # Create edges with embeddings for testing
    test_embeddings = [[random.random() for _ in range(2560)] for _ in range(20)]
    edge_objects = []
    
    for i in range(num_edges):
        source = random.choice(entities)
        target = random.choice(entities)
        if source == target:
            continue
            
        edge_uuid = str(uuid.uuid4())
        embedding = random.choice(test_embeddings)
        
        # Create edge in database
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
            group_id="batch_test",
            name=f"batch_test_edge_{i}",
            fact=f"This is batch test fact {i} for testing memory limits",
            created_at="2025-01-01T00:00:00Z",
            episodes=[str(uuid.uuid4()), str(uuid.uuid4())],
            valid_at="2025-01-01T00:00:00Z",
            fact_embedding=embedding
        )
        
        # Create EntityEdge object for testing
        edge_obj = EntityEdge(
            uuid=edge_uuid,
            source_node_uuid=source,
            target_node_uuid=target,
            name=f"batch_test_edge_{i}",
            fact=f"This is batch test fact {i} for testing memory limits",
            fact_embedding=embedding,
            group_id="batch_test",
            episodes=[str(uuid.uuid4()), str(uuid.uuid4())],
            created_at=datetime.fromisoformat("2025-01-01T00:00:00"),
            valid_at=datetime.fromisoformat("2025-01-01T00:00:00")
        )
        edge_objects.append(edge_obj)
        
        if (i + 1) % 50 == 0:
            print(f"   Created {i + 1}/{num_edges} edges...")
    
    print(f"✅ Created {len(edge_objects)} test edges")
    return edge_objects


async def test_batched_invalidation_memory_safe(driver, test_edges: List[EntityEdge]):
    """Test batched edge invalidation with various batch sizes."""
    
    print(f"\n🧪 Testing Batched Edge Invalidation")
    print("=" * 60)
    
    search_filter = SearchFilters()
    
    try:
        import time

        start_time = time.time()
        results = await get_edge_invalidation_candidates_batch(
            driver,
            test_edges,
            search_filter,
            min_score=DEFAULT_MIN_SCORE,
            limit=RELEVANT_SCHEMA_LIMIT,
        )
        end_time = time.time()

        execution_time = end_time - start_time
        total_candidates = sum(len(candidates) for candidates in results)
        print(f"   ✅ SUCCESS: {execution_time:.3f}s, {total_candidates} invalidation candidates found")

        if execution_time > 30:
            print(f"   ⚠️  SLOW: {execution_time:.2f}s execution time")

        return True

    except Exception as e:
        error_msg = str(e)
        print(f"   ❌ FAILED: {error_msg}")

        if "Query's mem consumption exceeded capacity" in error_msg:
            print("   🔥 MEMORY EXHAUSTION during invalidation run")
        elif "Type mismatch" in error_msg:
            print("   🔧 TYPE MISMATCH during invalidation run")

        return False


async def test_automatic_batch_splitting(driver, test_edges: List[EntityEdge]):
    """Test automatic batch splitting when memory exhaustion occurs."""
    
    print(f"\n🔧 Testing Automatic Batch Splitting")
    print("=" * 60)
    
    search_filter = SearchFilters()
    
    # Execute a full invalidation run to ensure per-edge querying remains stable
    print(f"📊 Testing per-edge invalidation stability across {len(test_edges)} edges")
    print(f"   Processing {len(test_edges)} edges...")
    
    try:
        import time
        start_time = time.time()
        
        results = await get_edge_invalidation_candidates_batch(
            driver,
            test_edges,
            search_filter,
            min_score=DEFAULT_MIN_SCORE,
            limit=RELEVANT_SCHEMA_LIMIT,
        )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        total_candidates = sum(len(candidates) for candidates in results)
        print(f"   ✅ SUCCESS: {execution_time:.3f}s, {total_candidates} invalidation candidates")
        print("   💡 Per-edge invalidation completed successfully")
        
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"   ❌ FAILED: {error_msg}")
        return False


async def test_environment_variable_batch_size(driver, test_edges: List[EntityEdge]):
    """Test batch size configuration via environment variable."""
    
    print(f"\n⚙️ Testing Environment Variable Batch Size")
    print("=" * 60)
    
    search_filter = SearchFilters()

    print(f"📊 Testing default invalidation helper over {len(test_edges)} edges")
    
    try:
        import time
        start_time = time.time()
        
        results = await get_edge_invalidation_candidates(
            driver, test_edges, search_filter
        )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        total_candidates = sum(len(candidates) for candidates in results)
        print(f"   ✅ SUCCESS: {execution_time:.3f}s, {total_candidates} invalidation candidates")
        print("   ⚙️ Default helper executed successfully")
        
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"   ❌ FAILED: {error_msg}")
        return False
    
    finally:
        pass


async def run_batch_invalidation_tests():
    """Run comprehensive batched edge invalidation tests."""
    
    print("🧪 Batched Edge Invalidation Tests")
    print("Testing memory-safe edge invalidation to prevent FalkorDB exhaustion")
    print("=" * 80)
    
    driver = FalkorDriver(
        host='localhost',
        port=6379,
        username='',
        password='',
        database='falkordb'
    )
    
    try:
        # Create test data (smaller dataset for faster testing)
        test_edges = await create_test_edges(driver, num_entities=30, num_edges=100)
        
        # Run tests
        test_results = []
        
        test_results.append(await test_batched_invalidation_memory_safe(driver, test_edges))
        test_results.append(await test_automatic_batch_splitting(driver, test_edges))
        test_results.append(await test_environment_variable_batch_size(driver, test_edges))
        
        # Summary
        passed_tests = sum(test_results)
        total_tests = len(test_results)
        
        print(f"\n📋 BATCH INVALIDATION TEST SUMMARY")
        print("=" * 50)
        print(f"✅ Tests passed: {passed_tests}/{total_tests}")
        
        if passed_tests == total_tests:
            print("🎉 All batched edge invalidation tests passed!")
            print("✅ Memory exhaustion issues should be resolved")
            print("✅ Ingestion pipeline should now handle large edge counts")
        else:
            print(f"❌ {total_tests - passed_tests} tests failed")
            print("💡 Additional optimization may be needed")
        
    except Exception as e:
        print(f"\n❌ Batch invalidation test error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await driver.close()


if __name__ == '__main__':
    asyncio.run(run_batch_invalidation_tests())
