#!/usr/bin/env python3
"""Test script to verify FalkorDB Rust client similarity search works."""

import requests
import json
import time

# Test configuration
RUST_SERVICE_URL = "http://localhost:3004"
PYTHON_SERVICE_URL = "http://localhost:8000"

def test_similarity_search():
    """Test similarity search through the Rust service."""
    
    # First, let's try fulltext search to make sure service is working
    print("Testing fulltext search...")
    fulltext_payload = {
        "query": "alice",
        "config": {
            "node_config": {
                "search_methods": ["fulltext"],
                "reranker": "rrf",
                "bfs_max_depth": 2,
                "sim_min_score": 0.0,
                "mmr_lambda": 0.5
            },
            "limit": 5,
            "reranker_min_score": 0.0
        },
        "filters": {}
    }
    
    try:
        response = requests.post(f"{RUST_SERVICE_URL}/search/nodes", json=fulltext_payload)
        if response.status_code == 200:
            results = response.json()
            print(f"✓ Fulltext search returned {len(results)} results")
        else:
            print(f"✗ Fulltext search failed: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"✗ Fulltext search error: {e}")
    
    # Now test similarity search
    print("\nTesting similarity search with new FalkorDB client...")
    similarity_payload = {
        "query": "alice and bob are friends",
        "config": {
            "node_config": {
                "search_methods": ["similarity"],
                "reranker": "rrf",
                "bfs_max_depth": 2,
                "sim_min_score": 0.0,
                "mmr_lambda": 0.5
            },
            "limit": 5,
            "reranker_min_score": 0.0
        },
        "filters": {}
    }
    
    try:
        response = requests.post(f"{RUST_SERVICE_URL}/search/nodes", json=similarity_payload)
        if response.status_code == 200:
            results = response.json()
            print(f"✓ Similarity search returned {len(results)} results")
            if results:
                print(f"  Top result: {results[0].get('name', 'N/A')}")
        else:
            print(f"✗ Similarity search failed: {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"✗ Similarity search error: {e}")
        return False
    
    # Test edge similarity search
    print("\nTesting edge similarity search...")
    edge_payload = {
        "query": "alice and bob are friends",
        "config": {
            "edge_config": {
                "search_methods": ["similarity"],
                "reranker": "rrf",
                "bfs_max_depth": 2,
                "sim_min_score": 0.0,
                "mmr_lambda": 0.5
            },
            "limit": 5,
            "reranker_min_score": 0.0
        },
        "filters": {}
    }
    
    try:
        response = requests.post(f"{RUST_SERVICE_URL}/search/edges", json=edge_payload)
        if response.status_code == 200:
            results = response.json()
            print(f"✓ Edge similarity search returned {len(results)} results")
            if results:
                print(f"  Top result fact: {results[0].get('fact', 'N/A')[:50]}...")
        else:
            print(f"✗ Edge similarity search failed: {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"✗ Edge similarity search error: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("Testing FalkorDB Rust Client with Similarity Search")
    print("=" * 60)
    
    # Check if service is running
    try:
        response = requests.get(f"{RUST_SERVICE_URL}/health")
        if response.status_code != 200:
            print("✗ Rust service is not running at port 3004")
            print("  Start it with: cd graphiti-search-rs && cargo run --release")
            exit(1)
    except:
        print("✗ Cannot connect to Rust service at port 3004")
        print("  Start it with: cd graphiti-search-rs && cargo run --release")
        exit(1)
    
    print("✓ Rust service is running\n")
    
    # Run tests
    success = test_similarity_search()
    
    print("\n" + "=" * 60)
    if success:
        print("✓ All tests passed! FalkorDB client is working correctly.")
    else:
        print("✗ Some tests failed. Check the logs for details.")
    print("=" * 60)