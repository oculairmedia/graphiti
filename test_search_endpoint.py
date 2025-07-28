#!/usr/bin/env python3
"""
Test the search endpoint to verify FalkorDB connection
"""

import requests
import json

GRAPHITI_URL = "http://localhost:8003"

def test_search():
    """Test the search endpoint"""
    
    # Test 1: Basic search
    print("1. Testing search endpoint...")
    
    search_payload = {
        "query": "GraphCanvas",
        "group_ids": ["claude_conversations"],
        "max_facts": 10
    }
    
    response = requests.post(
        f"{GRAPHITI_URL}/search",
        json=search_payload
    )
    
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"   Response: {json.dumps(data, indent=2)}")
        
        if data.get("facts"):
            print(f"\n   ✅ Found {len(data['facts'])} facts")
            for i, fact in enumerate(data['facts'][:3]):
                print(f"      {i+1}. {fact.get('fact', '')[:100]}...")
        else:
            print("   ⚠️  No facts found")
    else:
        print(f"   ❌ Error: {response.text}")
        
    # Test 2: Node search
    print("\n2. Testing node search endpoint...")
    
    node_search_payload = {
        "query": "Claude",
        "group_ids": ["claude_conversations"],
        "max_nodes": 10
    }
    
    response = requests.post(
        f"{GRAPHITI_URL}/search/nodes",
        json=node_search_payload
    )
    
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if data.get("nodes"):
            print(f"\n   ✅ Found {len(data['nodes'])} nodes")
            for i, node in enumerate(data['nodes'][:5]):
                print(f"      {i+1}. {node.get('name', '')} ({node.get('uuid', '')[:8]}...)")
        else:
            print("   ⚠️  No nodes found")
    else:
        print(f"   ❌ Error: {response.text}")

if __name__ == "__main__":
    test_search()