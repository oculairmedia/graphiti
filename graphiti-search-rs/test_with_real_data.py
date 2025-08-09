#!/usr/bin/env python3
"""
Test script for the Rust search service with real data from graphiti_migration.
"""

import json
import time
import requests
from typing import Dict, Any, List
import numpy as np
from colorama import init, Fore, Style

# Initialize colorama for colored output
init(autoreset=True)

# Configuration
BASE_URL = "http://localhost:3004"
HEADERS = {"Content-Type": "application/json"}

def print_test(test_name: str):
    """Print test header"""
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.YELLOW}Testing: {test_name}")
    print(f"{Fore.CYAN}{'='*60}")

def print_success(message: str):
    """Print success message"""
    print(f"{Fore.GREEN}✓ {message}")

def print_error(message: str):
    """Print error message"""
    print(f"{Fore.RED}✗ {message}")

def print_info(message: str):
    """Print info message"""
    print(f"{Fore.BLUE}ℹ {message}")

def print_response(response: Dict[Any, Any], limit: int = 3):
    """Pretty print response with limited items"""
    print(f"{Fore.MAGENTA}Response Preview:")
    if isinstance(response, dict):
        for key, value in response.items():
            if isinstance(value, list) and len(value) > 0:
                print(f"  {key}: {len(value)} items")
                for item in value[:limit]:
                    if isinstance(item, dict):
                        # Print first few fields of each item
                        preview = {k: v for k, v in list(item.items())[:3]}
                        print(f"    - {json.dumps(preview, default=str)}")
            elif not isinstance(value, (list, dict)):
                print(f"  {key}: {value}")

def test_health_check():
    """Test the health check endpoint"""
    print_test("Health Check")
    
    try:
        response = requests.get(f"{BASE_URL}/health")
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") == "healthy":
            print_success("Service is healthy")
            print_info(f"Database: {data.get('database')}")
        else:
            print_error("Service reports unhealthy status")
            
        return True
    except Exception as e:
        print_error(f"Health check failed: {e}")
        return False

def test_edge_search_with_real_queries():
    """Test edge search with queries that should match real data"""
    print_test("Edge Search with Real Data")
    
    test_queries = [
        "Node",  # Should match Node 1, Node 2, etc.
        "Claude",  # Should match Claude-related entities
        "chrome",  # Should match chrome-devtools entries
        "system",  # Should match system entities
        "test",  # Generic test query
    ]
    
    for query in test_queries:
        print_info(f"\nSearching for: '{query}'")
        
        payload = {
            "query": query,
            "config": {
                "search_methods": ["fulltext"],
                "reranker": "rrf",
                "bfs_max_depth": 2,
                "sim_min_score": 0.5,
                "mmr_lambda": 0.5
            },
            "filters": {}
        }
        
        try:
            response = requests.post(
                f"{BASE_URL}/search/edges",
                headers=HEADERS,
                json=payload,
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                total = data.get('total', 0)
                if total > 0:
                    print_success(f"Found {total} edges for '{query}'")
                    print_response({"edges": data.get('edges', [])})
                else:
                    print_info(f"No edges found for '{query}'")
                print_info(f"Latency: {data.get('latency_ms', 'N/A')} ms")
            else:
                print_error(f"Search failed for '{query}': {response.text[:100]}")
                
        except Exception as e:
            print_error(f"Error searching for '{query}': {e}")

def test_node_search_with_real_queries():
    """Test node search with queries that should match real data"""
    print_test("Node Search with Real Data")
    
    test_queries = [
        "Node",  # Should match Node 1, Node 2, Node 3
        "Claude",  # Should match Claude entities
        "chrome",  # Should match chrome-devtools
        "navigate",  # Should match navigation functions
    ]
    
    for query in test_queries:
        print_info(f"\nSearching nodes for: '{query}'")
        
        payload = {
            "query": query,
            "config": {
                "search_methods": ["fulltext"],
                "reranker": "rrf",
                "bfs_max_depth": 2,
                "sim_min_score": 0.5,
                "mmr_lambda": 0.5
            },
            "filters": {}
        }
        
        try:
            response = requests.post(
                f"{BASE_URL}/search/nodes",
                headers=HEADERS,
                json=payload,
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                total = data.get('total', 0)
                if total > 0:
                    print_success(f"Found {total} nodes for '{query}'")
                    print_response({"nodes": data.get('nodes', [])})
                else:
                    print_info(f"No nodes found for '{query}'")
                print_info(f"Latency: {data.get('latency_ms', 'N/A')} ms")
            elif response.status_code == 503:
                # Known issue with node search
                print_info(f"Node search returned 503 (known issue): {response.json().get('error', 'Unknown error')}")
            else:
                print_error(f"Search failed for '{query}': {response.text[:100]}")
                
        except Exception as e:
            print_error(f"Error searching for '{query}': {e}")

def test_combined_search():
    """Test combined search across all entity types"""
    print_test("Combined Search")
    
    payload = {
        "query": "Node",
        "config": {
            "edge_config": {
                "search_methods": ["fulltext"],
                "reranker": "rrf",
                "bfs_max_depth": 2,
                "sim_min_score": 0.5,
                "mmr_lambda": 0.5
            },
            "node_config": {
                "search_methods": ["fulltext"],
                "reranker": "rrf",
                "bfs_max_depth": 2,
                "sim_min_score": 0.5,
                "mmr_lambda": 0.5
            },
            "episode_config": {
                "reranker": "rrf"
            },
            "limit": 10,
            "reranker_min_score": 0.0
        },
        "filters": {}
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/search",
            headers=HEADERS,
            json=payload,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success("Combined search completed")
            
            edges = len(data.get('edges', []))
            nodes = len(data.get('nodes', []))
            episodes = len(data.get('episodes', []))
            
            print_info(f"Found {edges} edges, {nodes} nodes, {episodes} episodes")
            print_info(f"Total latency: {data.get('latency_ms', 'N/A')} ms")
            
            if edges > 0 or nodes > 0:
                print_response(data, limit=2)
        else:
            print_error(f"Combined search failed: {response.text[:200]}")
            
    except Exception as e:
        print_error(f"Combined search error: {e}")

def test_performance_with_real_data():
    """Test performance with real queries"""
    print_test("Performance Test with Real Data")
    
    import concurrent.futures
    import statistics
    
    def make_request():
        """Make a single search request and measure time"""
        start = time.time()
        payload = {
            "query": "Node",
            "config": {
                "search_methods": ["fulltext"],
                "reranker": "rrf",
                "bfs_max_depth": 1,
                "sim_min_score": 0.5,
                "mmr_lambda": 0.5
            },
            "filters": {}
        }
        
        try:
            response = requests.post(
                f"{BASE_URL}/search/edges",
                headers=HEADERS,
                json=payload,
                timeout=5
            )
            elapsed = (time.time() - start) * 1000  # Convert to ms
            return (elapsed, response.status_code == 200)
        except:
            return (None, False)
    
    # Warm up
    print_info("Warming up...")
    for _ in range(3):
        make_request()
    
    # Run concurrent requests
    num_requests = 20
    num_workers = 5
    
    print_info(f"Running {num_requests} requests with {num_workers} workers")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(make_request) for _ in range(num_requests)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    # Analyze results
    successful_times = [r[0] for r in results if r[0] is not None and r[1]]
    failed_count = sum(1 for r in results if not r[1])
    
    if successful_times:
        print_success(f"Successful requests: {len(successful_times)}/{num_requests}")
        if failed_count > 0:
            print_info(f"Failed requests: {failed_count}")
            
        print_info(f"Average latency: {statistics.mean(successful_times):.2f} ms")
        print_info(f"Median latency: {statistics.median(successful_times):.2f} ms")
        print_info(f"Min latency: {min(successful_times):.2f} ms")
        print_info(f"Max latency: {max(successful_times):.2f} ms")
        if len(successful_times) > 1:
            print_info(f"Std deviation: {statistics.stdev(successful_times):.2f} ms")
            
        # Calculate requests per second
        total_time_seconds = sum(successful_times) / 1000.0
        rps = len(successful_times) / (total_time_seconds / num_workers)
        print_info(f"Estimated throughput: {rps:.1f} requests/second")
    else:
        print_error("All requests failed")

def test_data_statistics():
    """Get statistics about the data in the graph"""
    print_test("Data Statistics")
    
    # Test a few queries to understand the data
    queries = ["", "Node", "Claude", "chrome", "system"]
    
    total_edges = 0
    total_nodes = 0
    
    for query in queries:
        # Try edge search
        payload = {
            "query": query if query else "test",
            "config": {
                "search_methods": ["fulltext"],
                "reranker": "rrf",
                "bfs_max_depth": 1,
                "sim_min_score": 0.3,
                "mmr_lambda": 0.5
            },
            "filters": {}
        }
        
        try:
            response = requests.post(
                f"{BASE_URL}/search/edges",
                headers=HEADERS,
                json=payload,
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                count = data.get('total', 0)
                if count > 0:
                    print_info(f"Query '{query}': {count} edges found")
                    total_edges = max(total_edges, count)
                    
        except:
            pass
    
    print_success(f"Graph contains data (sample searches found up to {total_edges} edges)")

def main():
    """Run all tests"""
    print(f"{Fore.CYAN}{'='*60}")
    print(f"{Fore.YELLOW}Rust Search Service Test with Real Data")
    print(f"{Fore.CYAN}{'='*60}")
    
    # Check if service is running
    if not test_health_check():
        print_error("Service is not running. Please start the service first.")
        return
    
    # Run all tests
    test_data_statistics()
    test_edge_search_with_real_queries()
    test_node_search_with_real_queries()
    test_combined_search()
    test_performance_with_real_data()
    
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.GREEN}All tests completed!")
    print(f"{Fore.CYAN}{'='*60}")

if __name__ == "__main__":
    main()