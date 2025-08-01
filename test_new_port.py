#!/usr/bin/env python3
"""Test FalkorDB connection on new port."""

from falkordb import FalkorDB

# Connect to FalkorDB on new port
db = FalkorDB(host='localhost', port=6389)
graph = db.select_graph('test_new_port')

# Test query
graph.query("CREATE (n:Test {name: 'FalkorDB on port 6389'})")
result = graph.query('MATCH (n:Test) RETURN n.name')

if result.result_set:
    print(f'✓ Successfully connected to FalkorDB on port 6389')
    print(f'  Result: {result.result_set[0][0]}')
else:
    print('✗ Failed to query FalkorDB')

# Check the migration graph
migration_graph = db.select_graph('graphiti_migration')
result = migration_graph.query('MATCH (n) RETURN count(n) as count')
node_count = result.result_set[0][0] if result.result_set else 0
print(f'\n✓ Migration graph has {node_count} nodes')

print(f'\nFalkorDB is now running on:')
print(f'  - Redis port: 6389 (changed from 6379)')
print(f'  - UI port: 3100 (changed from 3000)')
print(f'  - UI URL: http://localhost:3100')
