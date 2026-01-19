#!/bin/bash
# Clean up isolated episodic nodes (no edges)
# Usage: ./cleanup_isolated_episodic.sh [--dry-run]

DRY_RUN=""
if [ "$1" == "--dry-run" ]; then
    DRY_RUN="true"
    echo "DRY RUN - no changes will be made"
fi

# Count isolated nodes
count=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "
MATCH (e:Episodic) 
WHERE NOT (e)-[]-() 
RETURN count(e) as isolated
" 2>/dev/null | grep -E '^[0-9]+$' | head -1)

echo "Found $count isolated episodic nodes"

if [ "$count" -eq "0" ]; then
    echo "Nothing to clean up"
    exit 0
fi

if [ -n "$DRY_RUN" ]; then
    echo ""
    echo "Would delete these nodes:"
    redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "
    MATCH (e:Episodic) 
    WHERE NOT (e)-[]-() 
    RETURN e.uuid as uuid, e.name as name, e.created_at as created_at
    ORDER BY e.created_at DESC
    " 2>/dev/null | head -100
    exit 0
fi

# Delete isolated nodes
echo "Deleting $count isolated episodic nodes..."
result=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "
MATCH (e:Episodic) 
WHERE NOT (e)-[]-() 
DELETE e
RETURN count(e) as deleted
" 2>/dev/null)

echo "$result"
echo "Done"
