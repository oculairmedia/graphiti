#!/usr/bin/env python3
"""
Comprehensive test script for the Rust search service.
Tests all endpoints and functionality.
"""

import json
import time
import requests
from typing import Dict, Any, List, Optional
import numpy as np
from datetime import datetime
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

def print_response(response: Dict[Any, Any]):
    """Pretty print response"""
    print(f"{Fore.MAGENTA}Response:")
    print(json.dumps(response, indent=2, default=str))

def test_health_check():
    """Test the health check endpoint"""
    print_test("Health Check")
    
    try:
        response = requests.get(f"{BASE_URL}/health")
        response.raise_for_status()
        data = response.json()
        print_response(data)
        
        if data.get("status") == "healthy":
            print_success("Service is healthy")
        else:
            print_error("Service reports unhealthy status")
            
        return True
    except Exception as e:
        print_error(f"Health check failed: {e}")
        return False

def test_edge_search():
    """Test edge search endpoint"""
    print_test("Edge Search")
    
    payloads = [
        {
            "name": "Fulltext Search",
            "query": "test",
            "config": {
                "search_methods": ["fulltext"],
                "reranker": "rrf",
                "bfs_max_depth": 3,
                "sim_min_score": 0.5,
                "mmr_lambda": 0.5
            },
            "filters": {}
        },
        {
            "name": "Similarity Search with Vector",
            "query": "similarity test",
            "config": {
                "search_methods": ["similarity"],
                "reranker": "mmr",
                "bfs_max_depth": 3,
                "sim_min_score": 0.7,
                "mmr_lambda": 0.7
            },
            "filters": {},
            "query_vector": np.random.rand(384).tolist()  # Mock embedding
        }
    ]
    
    for payload_info in payloads:
        name = payload_info.pop("name")
        print_info(f"Testing: {name}")
        
        try:
            response = requests.post(
                f"{BASE_URL}/search/edges",
                headers=HEADERS,
                json=payload_info
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success(f"{name} completed successfully")
                print_info(f"Found {data.get('total', 0)} edges")
                print_info(f"Latency: {data.get('latency_ms', 'N/A')} ms")
            else:
                print_error(f"{name} failed: {response.text}")
                
        except Exception as e:
            print_error(f"{name} error: {e}")

def test_node_search():
    """Test node search endpoint"""
    print_test("Node Search")
    
    payloads = [
        {
            "name": "Fulltext Node Search",
            "query": "entity",
            "config": {
                "search_methods": ["fulltext"],
                "reranker": "rrf",
                "bfs_max_depth": 2,
                "sim_min_score": 0.5,
                "mmr_lambda": 0.5
            },
            "filters": {}
        },
        {
            "name": "Similarity Node Search",
            "query": "similar nodes",
            "config": {
                "search_methods": ["similarity"],
                "reranker": "mmr",
                "bfs_max_depth": 2,
                "sim_min_score": 0.6,
                "mmr_lambda": 0.8
            },
            "filters": {},
            "query_vector": np.random.rand(384).tolist()
        }
    ]
    
    for payload_info in payloads:
        name = payload_info.pop("name")
        print_info(f"Testing: {name}")
        
        try:
            response = requests.post(
                f"{BASE_URL}/search/nodes",
                headers=HEADERS,
                json=payload_info
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success(f"{name} completed successfully")
                print_info(f"Found {data.get('total', 0)} nodes")
                print_info(f"Latency: {data.get('latency_ms', 'N/A')} ms")
            else:
                print_error(f"{name} failed: {response.text}")
                
        except Exception as e:
            print_error(f"{name} error: {e}")

def test_episode_search():
    """Test episode search endpoint"""
    print_test("Episode Search")
    
    payload = {
        "query": "episode content",
        "config": {
            "reranker": "rrf"
        },
        "filters": {}
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/search/episodes",
            headers=HEADERS,
            json=payload
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success("Episode search completed successfully")
            print_info(f"Found {data.get('total', 0)} episodes")
            print_info(f"Latency: {data.get('latency_ms', 'N/A')} ms")
        else:
            print_error(f"Episode search failed: {response.text}")
            
    except Exception as e:
        print_error(f"Episode search error: {e}")

def test_community_search():
    """Test community search endpoint"""
    print_test("Community Search")
    
    payload = {
        "query": "community",
        "config": {
            "reranker": "rrf",
            "sim_min_score": 0.5,
            "mmr_lambda": 0.5
        },
        "filters": {},
        "query_vector": np.random.rand(384).tolist()
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/search/communities",
            headers=HEADERS,
            json=payload
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success("Community search completed successfully")
            print_info(f"Found {data.get('total', 0)} communities")
            print_info(f"Latency: {data.get('latency_ms', 'N/A')} ms")
        else:
            print_error(f"Community search failed: {response.text}")
            
    except Exception as e:
        print_error(f"Community search error: {e}")

def test_combined_search():
    """Test combined search with multiple entity types"""
    print_test("Combined Search (All Entity Types)")
    
    payload = {
        "query": "test search",
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
            "community_config": {
                "reranker": "rrf",
                "sim_min_score": 0.5,
                "mmr_lambda": 0.5
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
            json=payload
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success("Combined search completed successfully")
            print_info(f"Found {len(data.get('edges', []))} edges")
            print_info(f"Found {len(data.get('nodes', []))} nodes")
            print_info(f"Found {len(data.get('episodes', []))} episodes")
            print_info(f"Found {len(data.get('communities', []))} communities")
            print_info(f"Latency: {data.get('latency_ms', 'N/A')} ms")
        else:
            print_error(f"Combined search failed: {response.text}")
            
    except Exception as e:
        print_error(f"Combined search error: {e}")

def test_performance():
    """Test performance with multiple concurrent requests"""
    print_test("Performance Test")
    
    import concurrent.futures
    import statistics
    
    def make_request():
        """Make a single search request and measure time"""
        start = time.time()
        payload = {
            "query": "performance test",
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
            elapsed = (time.time() - start) * 1000  # Convert to ms
            return elapsed if response.status_code == 200 else None
        except:
            return None
    
    # Run concurrent requests
    num_requests = 20
    num_workers = 5
    
    print_info(f"Running {num_requests} requests with {num_workers} workers")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(make_request) for _ in range(num_requests)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    # Filter out failed requests
    successful_times = [r for r in results if r is not None]
    
    if successful_times:
        print_success(f"Successful requests: {len(successful_times)}/{num_requests}")
        print_info(f"Average latency: {statistics.mean(successful_times):.2f} ms")
        print_info(f"Median latency: {statistics.median(successful_times):.2f} ms")
        print_info(f"Min latency: {min(successful_times):.2f} ms")
        print_info(f"Max latency: {max(successful_times):.2f} ms")
        if len(successful_times) > 1:
            print_info(f"Std deviation: {statistics.stdev(successful_times):.2f} ms")
    else:
        print_error("All requests failed")

def test_error_handling():
    """Test error handling with invalid requests"""
    print_test("Error Handling")
    
    test_cases = [
        {
            "name": "Missing query",
            "endpoint": "/search/nodes",
            "payload": {"config": {"search_methods": ["fulltext"], "reranker": "rrf", "bfs_max_depth": 2, "sim_min_score": 0.5, "mmr_lambda": 0.5}, "filters": {}}
        },
        {
            "name": "Invalid search method",
            "endpoint": "/search/nodes",
            "payload": {
                "query": "test",
                "config": {
                    "search_methods": ["invalid_method"],
                    "reranker": "rrf",
                    "bfs_max_depth": 2,
                    "sim_min_score": 0.5,
                    "mmr_lambda": 0.5
                },
                "filters": {}
            }
        },
        {
            "name": "Missing config",
            "endpoint": "/search/edges",
            "payload": {
                "query": "test",
                "filters": {}
            }
        }
    ]
    
    for test_case in test_cases:
        name = test_case["name"]
        endpoint = test_case["endpoint"]
        payload = test_case["payload"]
        print_info(f"Testing: {name}")
        
        try:
            response = requests.post(
                f"{BASE_URL}{endpoint}",
                headers=HEADERS,
                json=payload
            )
            
            if response.status_code >= 400:
                print_success(f"{name}: Error handled correctly (status {response.status_code})")
                print_info(f"Error message: {response.text[:100]}...")
            else:
                print_error(f"{name}: Expected error but got success")
                
        except Exception as e:
            print_error(f"{name} unexpected error: {e}")

def test_bfs_search():
    """Test BFS search functionality"""
    print_test("BFS Search")
    
    # We need some node UUIDs for BFS - using dummy ones for testing
    payload = {
        "query": "bfs test",
        "config": {
            "search_methods": ["bfs"],
            "reranker": "node_distance",
            "bfs_max_depth": 3,
            "sim_min_score": 0.5,
            "mmr_lambda": 0.5
        },
        "filters": {},
        "bfs_origin_node_uuids": [
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002"
        ]
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/search/nodes",
            headers=HEADERS,
            json=payload
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success("BFS search completed successfully")
            print_info(f"Found {data.get('total', 0)} nodes")
        else:
            print_info(f"BFS search returned status {response.status_code} (expected if no matching nodes)")
            
    except Exception as e:
        print_error(f"BFS search error: {e}")

def main():
    """Run all tests"""
    print(f"{Fore.CYAN}{'='*60}")
    print(f"{Fore.YELLOW}Rust Search Service Comprehensive Test Suite")
    print(f"{Fore.CYAN}{'='*60}")
    
    # Check if service is running
    if not test_health_check():
        print_error("Service is not running. Please start the service first.")
        return
    
    # Run all tests
    test_edge_search()
    test_node_search() 
    test_episode_search()
    test_community_search()
    test_combined_search()
    test_bfs_search()
    test_performance()
    test_error_handling()
    
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.GREEN}All tests completed!")
    print(f"{Fore.CYAN}{'='*60}")

if __name__ == "__main__":
    main()