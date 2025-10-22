#!/usr/bin/env python3
"""
Debug script to investigate FalkorDB edge extraction hang.
Tests the exact queries that are failing in the sync service.
"""

import asyncio
import time
from typing import Optional
import redis
from falkordb import FalkorDB

# Connection settings
FALKORDB_HOST = "192.168.50.90"
FALKORDB_PORT = 6379
FALKORDB_DATABASE = "graphiti_migration"

async def test_falkordb_connection():
    """Test basic FalkorDB connection and database info."""
    print("🔍 Testing FalkorDB Connection...")
    
    try:
        # Create connection
        db = FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
        graph = db.select_graph(FALKORDB_DATABASE)
        
        print(f"✅ Connected to FalkorDB at {FALKORDB_HOST}:{FALKORDB_PORT}")
        print(f"✅ Selected database: {FALKORDB_DATABASE}")
        
        return graph
    except Exception as e:
        print(f"❌ Failed to connect to FalkorDB: {e}")
        return None

async def test_basic_queries(graph):
    """Test basic node and edge count queries."""
    print("\n🔍 Testing Basic Queries...")
    
    queries = [
        ("Total Nodes", "MATCH (n) RETURN count(n)"),
        ("Entity Nodes", "MATCH (n:Entity) RETURN count(n)"),
        ("Episodic Nodes", "MATCH (n:Episodic) RETURN count(n)"),
        ("Community Nodes", "MATCH (n:Community) RETURN count(n)"),
        ("Total Edges", "MATCH ()-[r]->() RETURN count(r)"),
        ("RELATES_TO Edges", "MATCH ()-[r:RELATES_TO]->() RETURN count(r)"),
        ("MENTIONS Edges", "MATCH ()-[r:MENTIONS]->() RETURN count(r)"),
        ("HAS_MEMBER Edges", "MATCH ()-[r:HAS_MEMBER]->() RETURN count(r)"),
    ]
    
    for name, query in queries:
        try:
            start_time = time.time()
            result = await graph.query(query)
            end_time = time.time()
            
            count = result.result_set[0][0] if result.result_set else 0
            duration = end_time - start_time
            
            print(f"✅ {name}: {count:,} (took {duration:.2f}s)")
            
        except Exception as e:
            print(f"❌ {name} failed: {e}")

async def test_edge_extraction_query(graph):
    """Test the exact edge extraction query that's hanging."""
    print("\n🔍 Testing Edge Extraction Query (the one that hangs)...")
    
    # This is the exact query from extract_entity_edges_optimized
    query = """
    MATCH ()-[r:RELATES_TO]->()
    RETURN r.uuid, r.group_id, r.created_at, r.updated_at, r.valid_at, r.invalid_at, r.fact, r.episodes, r.chunks, r.source_node_uuid, r.target_node_uuid, r.weight, r.embedding
    ORDER BY r.uuid
    LIMIT 1000
    """
    
    try:
        print("⏳ Executing edge extraction query (timeout: 30s)...")
        start_time = time.time()
        
        # Set a timeout for the query
        result = await asyncio.wait_for(graph.query(query), timeout=30.0)
        
        end_time = time.time()
        duration = end_time - start_time
        
        rows = result.result_set if result and result.result_set else []
        print(f"✅ Edge extraction query completed!")
        print(f"   - Returned {len(rows)} rows")
        print(f"   - Duration: {duration:.2f}s")
        
        if rows:
            print(f"   - First edge UUID: {rows[0][0]}")
            print(f"   - Sample edge properties: {len([x for x in rows[0] if x is not None])} non-null fields")
        
        return True
        
    except asyncio.TimeoutError:
        print("❌ Edge extraction query TIMED OUT after 30 seconds!")
        print("   This confirms the hang issue in the sync service.")
        return False
        
    except Exception as e:
        print(f"❌ Edge extraction query failed: {e}")
        return False

async def test_smaller_edge_batches(graph):
    """Test smaller edge batch sizes to find the breaking point."""
    print("\n🔍 Testing Smaller Edge Batch Sizes...")
    
    batch_sizes = [10, 50, 100, 500, 1000]
    
    for batch_size in batch_sizes:
        query = f"""
        MATCH ()-[r:RELATES_TO]->()
        RETURN r.uuid, r.group_id, r.created_at, r.updated_at, r.valid_at, r.invalid_at, r.fact, r.episodes, r.chunks, r.source_node_uuid, r.target_node_uuid, r.weight, r.embedding
        ORDER BY r.uuid
        LIMIT {batch_size}
        """
        
        try:
            print(f"⏳ Testing batch size {batch_size}...")
            start_time = time.time()
            
            result = await asyncio.wait_for(graph.query(query), timeout=15.0)
            
            end_time = time.time()
            duration = end_time - start_time
            
            rows = result.result_set if result and result.result_set else []
            print(f"✅ Batch size {batch_size}: {len(rows)} rows in {duration:.2f}s")
            
        except asyncio.TimeoutError:
            print(f"❌ Batch size {batch_size}: TIMED OUT after 15s")
            break
            
        except Exception as e:
            print(f"❌ Batch size {batch_size}: Failed - {e}")
            break

async def test_memory_usage():
    """Test FalkorDB memory usage."""
    print("\n🔍 Testing FalkorDB Memory Usage...")
    
    try:
        # Direct Redis connection for memory info
        r = redis.Redis(host=FALKORDB_HOST, port=FALKORDB_PORT, decode_responses=True)
        
        memory_info = r.info('memory')
        
        print("📊 Memory Statistics:")
        print(f"   - Used Memory: {memory_info.get('used_memory_human', 'N/A')}")
        print(f"   - Used Memory RSS: {memory_info.get('used_memory_rss_human', 'N/A')}")
        print(f"   - Used Memory Peak: {memory_info.get('used_memory_peak_human', 'N/A')}")
        print(f"   - Memory Fragmentation Ratio: {memory_info.get('mem_fragmentation_ratio', 'N/A')}")
        
        # Check if memory is near limits
        used_memory = memory_info.get('used_memory', 0)
        max_memory = memory_info.get('maxmemory', 0)
        
        if max_memory > 0:
            usage_percent = (used_memory / max_memory) * 100
            print(f"   - Memory Usage: {usage_percent:.1f}% of max")
            
            if usage_percent > 90:
                print("⚠️  WARNING: Memory usage is very high!")
        
    except Exception as e:
        print(f"❌ Failed to get memory info: {e}")

async def main():
    """Main debug function."""
    print("🚀 FalkorDB Edge Extraction Debug Tool")
    print("=" * 50)
    
    # Test connection
    graph = await test_falkordb_connection()
    if not graph:
        return
    
    # Test basic queries
    await test_basic_queries(graph)
    
    # Test memory usage
    await test_memory_usage()
    
    # Test the problematic edge extraction query
    edge_query_success = await test_edge_extraction_query(graph)
    
    # If edge query fails, test smaller batches
    if not edge_query_success:
        await test_smaller_edge_batches(graph)
    
    print("\n" + "=" * 50)
    print("🏁 Debug Complete")
    
    if not edge_query_success:
        print("\n💡 FINDINGS:")
        print("   - The edge extraction query is indeed hanging/timing out")
        print("   - This confirms the sync service issue")
        print("   - Possible causes:")
        print("     • Memory exhaustion during large relationship traversals")
        print("     • FalkorDB performance issues with complex edge queries")
        print("     • Query optimization problems with ORDER BY on relationships")
        print("     • Network/connection timeouts")

if __name__ == "__main__":
    asyncio.run(main())
