#!/usr/bin/env python3
"""Test script to understand FalkorDB response format."""

import redis
import json

# Connect to FalkorDB
r = redis.Redis(host='localhost', port=6389, decode_responses=False)

# Test simple query
graph_name = "graphiti_migration"
query = "MATCH (n) RETURN n LIMIT 1"

# Execute query
response = r.execute_command("GRAPH.QUERY", graph_name, query)

print("Raw FalkorDB response:")
print(f"Type: {type(response)}")
print(f"Length: {len(response)}")
print()

for i, item in enumerate(response):
    print(f"Item {i}:")
    print(f"  Type: {type(item)}")
    if isinstance(item, list):
        print(f"  Length: {len(item)}")
        for j, subitem in enumerate(item[:3]):  # Show first 3 items
            print(f"  [{j}]: {type(subitem)} = {subitem[:100] if isinstance(subitem, (bytes, str)) else subitem}")
    else:
        print(f"  Value: {item}")
    print()

# Now test edge query
edge_query = "MATCH (a)-[r]->(b) RETURN a, r, b LIMIT 1"
edge_response = r.execute_command("GRAPH.QUERY", graph_name, edge_query)

print("\nEdge query response:")
print(f"Type: {type(edge_response)}")
print(f"Length: {len(edge_response)}")

for i, item in enumerate(edge_response):
    print(f"Item {i}:")
    print(f"  Type: {type(item)}")
    if isinstance(item, list):
        print(f"  Length: {len(item)}")
        if i == 1 and len(item) > 0:  # Data row
            for j, col in enumerate(item[0] if item else []):
                print(f"  Column {j}: {type(col)}")
                if isinstance(col, list) and len(col) >= 3:
                    print(f"    [0] ID: {col[0]}")
                    print(f"    [1] Labels/Type: {col[1]}")
                    print(f"    [2] Properties: {col[2][:200] if len(col) > 2 else 'N/A'}")
    print()