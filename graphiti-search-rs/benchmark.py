#!/usr/bin/env python3
"""
Performance benchmark for Rust Search Service
Tests throughput and latency with caching
"""

import asyncio
import aiohttp
import time
import statistics
import json
from typing import List, Dict
import random

# Test configuration
BASE_URL = "http://localhost:3004"
TOTAL_REQUESTS = 1000
CONCURRENT_WORKERS = 50  # Number of concurrent connections

# Queries to test (mix of cached and uncached)
TEST_QUERIES = [
    "Node",      # Will be cached after first hit
    "Edge",      # Will be cached after first hit
    "test",      # Will be cached after first hit
    "Node 1",    # Specific queries
    "Node 2",
    "Node 3",
    f"random_{random.randint(1, 100)}",  # Some uncached queries
]

async def make_request(session: aiohttp.ClientSession, query: str) -> Dict:
    """Make a single search request and return timing info"""
    payload = {
        "query": query,
        "config": {
            "node_config": {
                "search_methods": ["fulltext"],
                "reranker": "rrf",
                "bfs_max_depth": 2,
                "sim_min_score": 0.5,
                "mmr_lambda": 0.5
            },
            "limit": 10,
            "reranker_min_score": 0.0
        },
        "filters": {}
    }
    
    start_time = time.perf_counter()
    try:
        async with session.post(f"{BASE_URL}/search", json=payload) as response:
            result = await response.json()
            end_time = time.perf_counter()
            
            return {
                "success": response.status == 200,
                "latency": (end_time - start_time) * 1000,  # Convert to ms
                "server_latency": result.get("latency_ms", 0),
                "query": query,
                "node_count": len(result.get("nodes", [])),
                "edge_count": len(result.get("edges", []))
            }
    except Exception as e:
        end_time = time.perf_counter()
        return {
            "success": False,
            "latency": (end_time - start_time) * 1000,
            "server_latency": 0,
            "query": query,
            "error": str(e)
        }

async def worker(session: aiohttp.ClientSession, request_queue: asyncio.Queue, results: List[Dict]):
    """Worker that processes requests from the queue"""
    while True:
        query = await request_queue.get()
        if query is None:
            break
        
        result = await make_request(session, query)
        results.append(result)
        request_queue.task_done()

async def warmup_cache(session: aiohttp.ClientSession):
    """Warm up the cache with initial queries"""
    print("Warming up cache...")
    tasks = []
    for query in TEST_QUERIES[:3]:  # Warm up with first 3 queries
        for _ in range(3):  # Hit each 3 times
            tasks.append(make_request(session, query))
    
    await asyncio.gather(*tasks)
    print("Cache warmed up!\n")

async def run_benchmark():
    """Run the performance benchmark"""
    print(f"Starting Performance Benchmark")
    print(f"Total Requests: {TOTAL_REQUESTS}")
    print(f"Concurrent Workers: {CONCURRENT_WORKERS}")
    print("=" * 60)
    
    # Create session with connection pooling
    connector = aiohttp.TCPConnector(limit=CONCURRENT_WORKERS)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Warm up cache
        await warmup_cache(session)
        
        # Prepare request queue
        request_queue = asyncio.Queue()
        results = []
        
        # Add requests to queue (mix of queries)
        for i in range(TOTAL_REQUESTS):
            query = TEST_QUERIES[i % len(TEST_QUERIES)]
            await request_queue.put(query)
        
        # Add stop signals
        for _ in range(CONCURRENT_WORKERS):
            await request_queue.put(None)
        
        # Start workers
        print(f"Starting {CONCURRENT_WORKERS} workers...")
        start_time = time.perf_counter()
        
        workers = [
            asyncio.create_task(worker(session, request_queue, results))
            for _ in range(CONCURRENT_WORKERS)
        ]
        
        # Wait for all requests to complete
        await asyncio.gather(*workers)
        
        end_time = time.perf_counter()
        total_time = end_time - start_time
        
        # Analyze results
        successful = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]
        
        if successful:
            client_latencies = [r["latency"] for r in successful]
            server_latencies = [r["server_latency"] for r in successful]
            
            # Group by query to analyze cache performance
            by_query = {}
            for r in successful:
                query = r["query"]
                if query not in by_query:
                    by_query[query] = []
                by_query[query].append(r["server_latency"])
            
            print("\n" + "=" * 60)
            print("PERFORMANCE RESULTS")
            print("=" * 60)
            
            print(f"\n📊 Throughput:")
            print(f"  Total Time: {total_time:.2f} seconds")
            print(f"  Requests/Second: {len(successful) / total_time:.2f} RPS")
            print(f"  Success Rate: {len(successful)}/{len(results)} ({len(successful)/len(results)*100:.1f}%)")
            
            print(f"\n⚡ Latency Statistics (Client-side):")
            print(f"  Min: {min(client_latencies):.2f}ms")
            print(f"  Max: {max(client_latencies):.2f}ms")
            print(f"  Mean: {statistics.mean(client_latencies):.2f}ms")
            print(f"  Median: {statistics.median(client_latencies):.2f}ms")
            print(f"  P95: {statistics.quantiles(client_latencies, n=20)[18]:.2f}ms")
            print(f"  P99: {statistics.quantiles(client_latencies, n=100)[98]:.2f}ms")
            
            print(f"\n🚀 Server-side Latency:")
            print(f"  Min: {min(server_latencies):.2f}ms")
            print(f"  Max: {max(server_latencies):.2f}ms")
            print(f"  Mean: {statistics.mean(server_latencies):.2f}ms")
            print(f"  Median: {statistics.median(server_latencies):.2f}ms")
            
            print(f"\n💾 Cache Performance by Query:")
            for query, latencies in sorted(by_query.items())[:5]:  # Show top 5
                if len(latencies) > 1:
                    first_hit = latencies[0]
                    subsequent = latencies[1:]
                    cache_speedup = first_hit / statistics.mean(subsequent) if subsequent and statistics.mean(subsequent) > 0 else 0
                    print(f"  '{query}':")
                    print(f"    First hit: {first_hit:.2f}ms")
                    print(f"    Cached (avg): {statistics.mean(subsequent):.2f}ms")
                    print(f"    Speedup: {cache_speedup:.1f}x")
            
            # Calculate cache hit ratio (rough estimate based on low latency)
            cache_hits = [r for r in successful if r["server_latency"] <= 2]  # <=2ms likely cached
            cache_ratio = len(cache_hits) / len(successful) * 100 if successful else 0
            print(f"\n📈 Estimated Cache Hit Ratio: {cache_ratio:.1f}%")
            
            if failed:
                print(f"\n❌ Failed Requests: {len(failed)}")
                for f in failed[:5]:  # Show first 5 failures
                    print(f"  - {f.get('error', 'Unknown error')}")
        
        else:
            print("❌ All requests failed!")
            for f in failed[:5]:
                print(f"  - {f.get('error', 'Unknown error')}")

async def test_connection_pool():
    """Test how many concurrent connections the service can handle"""
    print("\nTesting Connection Pool Capacity...")
    print("=" * 60)
    
    concurrent_tests = [10, 50, 100, 200, 300, 400, 500]
    
    for concurrent in concurrent_tests:
        connector = aiohttp.TCPConnector(limit=concurrent)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = []
            start = time.perf_counter()
            
            # Send requests concurrently
            for i in range(concurrent):
                query = f"test_{i % 10}"
                tasks.append(make_request(session, query))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            end = time.perf_counter()
            
            successful = [r for r in results if isinstance(r, dict) and r.get("success")]
            duration = end - start
            
            print(f"  {concurrent} concurrent: {len(successful)}/{concurrent} success, "
                  f"{concurrent/duration:.1f} RPS, "
                  f"avg latency: {statistics.mean([r['latency'] for r in successful]):.1f}ms")
            
            # Stop if we start seeing failures
            if len(successful) < concurrent * 0.95:
                print(f"  ⚠️  Reached connection limit around {concurrent} concurrent requests")
                break
    
    print()

if __name__ == "__main__":
    print("🔥 Rust Search Service Performance Benchmark 🔥\n")
    
    # Run main benchmark
    asyncio.run(run_benchmark())
    
    # Test connection pool limits
    asyncio.run(test_connection_pool())
    
    print("\n✅ Benchmark Complete!")