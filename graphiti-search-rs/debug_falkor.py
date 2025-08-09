#!/usr/bin/env python3
"""Debug FalkorDB response format."""

import redis
import json

# Connect to FalkorDB
r = redis.Redis(host='localhost', port=6389, decode_responses=False)

# Test simple query
graph_name = "graphiti_migration"
query = "MATCH (n) WHERE n.name CONTAINS 'Node 1' RETURN n LIMIT 1"

# Execute query
response = r.execute_command("GRAPH.QUERY", graph_name, query)

print("Full response structure:")
print(f"Type: {type(response)}, Length: {len(response)}")
print()

# Analyze each part
for i, part in enumerate(response):
    print(f"\n=== Part {i} ===")
    print(f"Type: {type(part)}")
    
    if isinstance(part, list):
        print(f"Length: {len(part)}")
        if i == 1 and len(part) > 0:  # Data rows
            print("\nFirst data row:")
            first_row = part[0]
            print(f"  Type: {type(first_row)}")
            
            if isinstance(first_row, list):
                print(f"  Length: {len(first_row)}")
                print("\n  First column (the node):")
                if len(first_row) > 0:
                    node_col = first_row[0]
                    print(f"    Type: {type(node_col)}")
                    
                    if isinstance(node_col, list):
                        print(f"    Length: {len(node_col)}")
                        for j, item in enumerate(node_col):
                            print(f"\n    Item {j}:")
                            print(f"      Type: {type(item)}")
                            if isinstance(item, list) and len(item) >= 2:
                                key = item[0]
                                val = item[1]
                                print(f"      Key: {key}")
                                print(f"      Val type: {type(val)}")
                                if isinstance(val, (bytes, str)):
                                    print(f"      Val: {val[:100]}")
                                elif isinstance(val, list):
                                    print(f"      Val length: {len(val)}")
                                    if len(val) > 0:
                                        print(f"      First item: {val[0]}")
                                else:
                                    print(f"      Val: {val}")
    else:
        print(f"Value: {part}")