#!/bin/bash

echo "Testing search service debugging..."

# Test 1: Health check
echo -e "\n1. Health Check:"
curl -s http://localhost:3004/health | jq

# Test 2: Direct node search with fulltext
echo -e "\n2. Node fulltext search for 'Claude':"
curl -s -X POST http://localhost:3004/node-search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "claude",
    "config": {
      "search_methods": ["fulltext"],
      "limit": 5
    }
  }' | jq

# Test 3: Check what's actually in the database
echo -e "\n3. Direct database query:"
docker exec graphiti-falkordb-1 redis-cli GRAPH.QUERY graphiti_migration \
  "MATCH (n:Entity) WHERE toLower(n.name) CONTAINS 'claude' RETURN n.name, n.uuid LIMIT 3"

# Test 4: Check if search service logs show anything  
echo -e "\n4. Recent search service logs:"
docker logs graphiti-search-rs --tail 10 2>&1 | grep -v "health"