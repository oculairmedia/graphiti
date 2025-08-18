#!/usr/bin/env python3
import redis
import sys

# Test connection from outside container
try:
    # Connect to FalkorDB
    r = redis.Redis(host='localhost', port=6389, decode_responses=True)
    
    # Test PING
    pong = r.ping()
    print(f"✓ PING successful: {pong}")
    
    # Test GRAPH.QUERY
    result = r.execute_command('GRAPH.QUERY', 'graphiti_migration', 'MATCH (n:Entity) RETURN count(n) as count')
    print(f"✓ GRAPH.QUERY successful: {result}")
    
    # Test a simple search query
    search_result = r.execute_command('GRAPH.QUERY', 'graphiti_migration', 
                                     "MATCH (n:Entity) WHERE toLower(n.name) CONTAINS 'claude' RETURN n.name LIMIT 1")
    print(f"✓ Search query successful: {search_result}")
    
except Exception as e:
    print(f"✗ Error: {e}")
    sys.exit(1)