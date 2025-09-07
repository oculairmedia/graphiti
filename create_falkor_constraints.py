#!/usr/bin/env python3
"""Manually create FalkorDB constraints to test constraint behavior."""

from falkordb import FalkorDB
from graphiti_core.utils.constraints import get_existence_constraints

def create_constraints():
    """Create FalkorDB constraints manually."""
    print("Creating FalkorDB constraints...")
    
    falkor_db = FalkorDB(host='localhost', port=6379)
    
    # Get constraint queries for FalkorDB
    constraint_queries = get_existence_constraints('falkordb')
    graph_key = 'knowledge_graph'
    
    print(f"Found {len(constraint_queries)} constraint queries to execute...")
    
    for i, query in enumerate(constraint_queries):
        try:
            if '{graph_key}' in query:
                command = query.format(graph_key=graph_key)
                print(f"Executing constraint {i+1}: {command}")
                # Execute the GRAPH.CONSTRAINT command directly
                result = falkor_db.execute_command(*command.split())
                print(f"  Result: {result}")
            else:
                print(f"Skipping constraint {i+1}: no graph_key placeholder")
        except Exception as e:
            print(f"  Error creating constraint {i+1}: {e}")

if __name__ == "__main__":
    create_constraints()