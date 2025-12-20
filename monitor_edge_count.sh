#!/bin/bash

echo "Starting edge count monitor for FalkorDB graphiti database"
echo "Checking every 5 minutes. Press Ctrl+C to stop."
echo "=================================================="
echo ""

while true; do
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    EDGE_COUNT=$(docker exec graphiti-falkordb-1 redis-cli -p 6379 GRAPH.QUERY graphiti "MATCH ()-[r]->() RETURN count(r)" 2>/dev/null | head -n 1)
    NODE_COUNT=$(docker exec graphiti-falkordb-1 redis-cli -p 6379 GRAPH.QUERY graphiti "MATCH (n) RETURN count(n)" 2>/dev/null | head -n 1)
    
    echo "[$TIMESTAMP] Nodes: $NODE_COUNT | Edges: $EDGE_COUNT"
    
    sleep 300  # 5 minutes
done
