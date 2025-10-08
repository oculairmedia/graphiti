#!/usr/bin/env python3
"""
Graphiti Search Tool - Allows Claude to query the knowledge graph at any time
"""

import sys
import json
import requests
from typing import Optional, List, Dict, Any

GRAPHITI_API_URL = "http://localhost:8003"

def search_facts(query: str, group_ids: Optional[List[str]] = None, max_facts: int = 10) -> Dict[str, Any]:
    """Search for facts in Graphiti"""
    payload = {
        "query": query,
        "max_facts": max_facts
    }
    if group_ids:
        payload["group_ids"] = group_ids
    
    try:
        response = requests.post(
            f"{GRAPHITI_API_URL}/search",
            json=payload,
            timeout=5
        )
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"API returned {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def search_nodes(query: str, group_ids: Optional[List[str]] = None, max_nodes: int = 10) -> Dict[str, Any]:
    """Search for nodes/entities in Graphiti"""
    payload = {
        "query": query,
        "max_nodes": max_nodes
    }
    if group_ids:
        payload["group_ids"] = group_ids
    
    try:
        response = requests.post(
            f"{GRAPHITI_API_URL}/search/nodes",
            json=payload,
            timeout=5
        )
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"API returned {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def main():
    if len(sys.argv) < 2:
        print("Usage: search_graphiti.py <query> [--facts|--nodes] [--max N]")
        sys.exit(1)
    
    query = sys.argv[1]
    search_type = "facts"
    max_results = 10
    
    # Parse optional arguments
    for i in range(2, len(sys.argv)):
        if sys.argv[i] == "--facts":
            search_type = "facts"
        elif sys.argv[i] == "--nodes":
            search_type = "nodes"
        elif sys.argv[i] == "--max" and i + 1 < len(sys.argv):
            max_results = int(sys.argv[i + 1])
    
    # Perform search
    if search_type == "facts":
        results = search_facts(query, max_facts=max_results)
        if "facts" in results:
            print(f"\n🔍 Found {len(results['facts'])} facts about '{query}':\n")
            for fact in results['facts']:
                print(f"• {fact.get('fact', fact)}")
                if 'created_at' in fact:
                    print(f"  (Created: {fact['created_at'][:10]})")
        else:
            print(f"Error: {results.get('error', 'Unknown error')}")
    
    elif search_type == "nodes":
        results = search_nodes(query, max_nodes=max_results)
        if "nodes" in results:
            print(f"\n🔍 Found {len(results['nodes'])} entities matching '{query}':\n")
            for node in results['nodes']:
                name = node.get('name', 'Unknown')
                summary = node.get('summary', '')
                print(f"• {name}")
                if summary:
                    print(f"  Summary: {summary[:100]}...")
        else:
            print(f"Error: {results.get('error', 'Unknown error')}")

if __name__ == "__main__":
    main()