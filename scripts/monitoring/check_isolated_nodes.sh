#!/bin/bash
# Check for isolated episodic nodes (no edges)

THRESHOLD=${1:-0}  # Alert if more than this many isolated nodes

count=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "
MATCH (e:Episodic) 
WHERE NOT (e)-[]-() 
RETURN count(e) as isolated
" 2>/dev/null | grep -E '^[0-9]+$' | head -1)

echo "Isolated episodic nodes: $count"

if [ "$count" -gt "$THRESHOLD" ]; then
    echo "WARNING: $count isolated nodes exceeds threshold of $THRESHOLD"
    
    # Show recent ones
    echo ""
    echo "Most recent isolated nodes:"
    redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "
    MATCH (e:Episodic) 
    WHERE NOT (e)-[]-() 
    RETURN e.name as name, e.created_at as created_at
    ORDER BY e.created_at DESC
    LIMIT 5
    " 2>/dev/null | head -20
    
    exit 1
fi

exit 0
