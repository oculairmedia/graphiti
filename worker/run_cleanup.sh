#!/bin/bash
DB_NAME="graphiti_migration"
CONTAINER="graphiti-falkordb-1"

echo "=== Deleting 1208 isolated nodes in batches ==="
BATCH_SIZE=100
TOTAL_DELETED=0

for i in {1..15}; do
    echo -n "Batch $i: "
    docker exec -i $CONTAINER redis-cli --raw GRAPH.QUERY "$DB_NAME" \
        "MATCH (n) WHERE NOT (n)-[]-() WITH n LIMIT $BATCH_SIZE DELETE n RETURN count(n) as deleted" 2>&1 | head -1
    TOTAL_DELETED=$((TOTAL_DELETED + BATCH_SIZE))
    sleep 1
done

echo
echo "Checking remaining isolated nodes..."
docker exec -i $CONTAINER redis-cli --raw GRAPH.QUERY "$DB_NAME" \
    "MATCH (n) WHERE NOT (n)-[]-() RETURN count(n) as count" 2>&1 | head -1
