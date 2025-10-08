#!/usr/bin/env python3
"""
Debug script to investigate FalkorDB edge extraction hang.
"""

import asyncio
import time
import redis
from falkordb import FalkorDB

# Connection settings
FALKORDB_HOST = "192.168.50.90"
FALKORDB_PORT = 6379
FALKORDB_DATABASE = "graphiti_migration"

async def test_connection():
    """Test FalkorDB connection."""
    print("Testing FalkorDB connection...")
    
    try:
        db = FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
        graph = db.select_graph(FALKORDB_DATABASE)
        print(f"✅ Connected to {FALKORDB_HOST}:{FALKORDB_PORT}/{FALKORDB_DATABASE}")
        return graph
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return None

def test_basic_counts(graph):
    """Test basic node and edge counts."""
    print("\nTesting basic counts...")

    queries = [
        ("Nodes", "MATCH (n) RETURN count(n)"),
        ("Edges", "MATCH ()-[r]->() RETURN count(r)"),
        ("RELATES_TO", "MATCH ()-[r:RELATES_TO]->() RETURN count(r)"),
    ]

    for name, query in queries:
        try:
            start = time.time()
            result = graph.query(query)
            duration = time.time() - start
            count = result.result_set[0][0] if result.result_set else 0
            print(f"✅ {name}: {count:,} ({duration:.2f}s)")
        except Exception as e:
            print(f"❌ {name}: {e}")

def test_edge_query(graph):
    """Test the problematic edge extraction query."""
    print("\nTesting edge extraction query...")

    # The exact query that hangs in sync service
    query = """
    MATCH ()-[r:RELATES_TO]->()
    RETURN r.uuid, r.group_id, r.created_at, r.updated_at, r.valid_at, r.invalid_at,
           r.fact, r.episodes, r.chunks, r.source_node_uuid, r.target_node_uuid,
           r.weight, r.embedding
    ORDER BY r.uuid
    LIMIT 1000
    """

    try:
        print("⏳ Running edge query...")
        start = time.time()

        result = graph.query(query)

        duration = time.time() - start
        rows = result.result_set if result and result.result_set else []
        print(f"✅ Query completed: {len(rows)} rows in {duration:.2f}s")

        if rows:
            print(f"   First edge UUID: {rows[0][0]}")

        return True

    except Exception as e:
        print(f"❌ Query failed: {e}")
        return False

def test_memory():
    """Check FalkorDB memory usage."""
    print("\nChecking memory usage...")

    try:
        r = redis.Redis(host=FALKORDB_HOST, port=FALKORDB_PORT, decode_responses=True)
        memory_info = r.info('memory')

        print(f"Used Memory: {memory_info.get('used_memory_human', 'N/A')}")
        print(f"Peak Memory: {memory_info.get('used_memory_peak_human', 'N/A')}")
        print(f"Fragmentation: {memory_info.get('mem_fragmentation_ratio', 'N/A')}")

    except Exception as e:
        print(f"❌ Memory check failed: {e}")

async def main():
    print("🔍 FalkorDB Edge Hang Debug")
    print("=" * 40)

    graph = await test_connection()
    if not graph:
        return

    test_basic_counts(graph)
    test_memory()

    success = test_edge_query(graph)

    print("\n" + "=" * 40)
    if not success:
        print("💡 CONFIRMED: Edge extraction query hangs!")
        print("   This explains the sync service failure.")
    else:
        print("✅ Edge query works - issue may be elsewhere.")

if __name__ == "__main__":
    asyncio.run(main())
