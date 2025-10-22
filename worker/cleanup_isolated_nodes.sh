#!/bin/bash
# Cleanup isolated nodes from FalkorDB graphiti_migration database

set -e

DB_NAME="graphiti_migration"
CONTAINER="graphiti-falkordb-1"

echo "=== FalkorDB Isolated Nodes Cleanup ==="
echo "Database: $DB_NAME"
echo

# Get count
echo "Checking for isolated nodes..."
RESULT=$(docker exec -i $CONTAINER redis-cli GRAPH.QUERY "$DB_NAME" \
    "MATCH (n) WHERE NOT (n)-[]-() RETURN count(n) as count" --csv | head -2 | tail -1)
TOTAL_COUNT=$RESULT

echo "Found $TOTAL_COUNT isolated nodes (nodes with no edges)"
echo

if [ "$TOTAL_COUNT" -eq "0" ]; then
    echo "✅ No isolated nodes found. Database is clean!"
    exit 0
fi

# Show breakdown by type
echo "Breakdown by node type:"
docker exec -i $CONTAINER redis-cli GRAPH.QUERY "$DB_NAME" \
    "MATCH (n) WHERE NOT (n)-[]-() RETURN labels(n) as labels, count(n) as count ORDER BY count DESC" \
    --csv | tail -n +2 | grep -v "Cached execution" | grep -v "Query internal" | while IFS=, read -r labels count; do
    echo "  $labels: $count nodes"
done
echo

# Show sample
echo "Sample isolated nodes (first 5):"
docker exec -i $CONTAINER redis-cli GRAPH.QUERY "$DB_NAME" \
    "MATCH (n) WHERE NOT (n)-[]-() RETURN labels(n) as labels, n.name as name LIMIT 5" \
    --csv | tail -n +2 | grep -v "Cached execution" | grep -v "Query internal" | head -5 | while IFS=, read -r labels name; do
    echo "  $labels - $name"
done
echo

# Confirm
read -p "Do you want to delete all $TOTAL_COUNT isolated nodes? (yes/no): " CONFIRMATION
if [[ ! "$CONFIRMATION" =~ ^[Yy]es$ ]] && [[ ! "$CONFIRMATION" =~ ^[Yy]$ ]]; then
    echo "Operation cancelled."
    exit 0
fi

echo
echo "Deleting isolated nodes in batches of 100..."

BATCH_SIZE=100
BATCH_NUM=1
TOTAL_DELETED=0

while true; do
    # Delete a batch
    RESULT=$(docker exec -i $CONTAINER redis-cli GRAPH.QUERY "$DB_NAME" \
        "MATCH (n) WHERE NOT (n)-[]-() WITH n LIMIT $BATCH_SIZE DELETE n RETURN count(n) as deleted" \
        --csv | head -2 | tail -1)
    
    DELETED_COUNT=$RESULT
    
    if [ "$DELETED_COUNT" -eq "0" ]; then
        break
    fi
    
    TOTAL_DELETED=$((TOTAL_DELETED + DELETED_COUNT))
    echo "  Batch $BATCH_NUM: Deleted $DELETED_COUNT nodes (total: $TOTAL_DELETED)"
    BATCH_NUM=$((BATCH_NUM + 1))
    
    # Check if done
    REMAINING=$(docker exec -i $CONTAINER redis-cli GRAPH.QUERY "$DB_NAME" \
        "MATCH (n) WHERE NOT (n)-[]-() RETURN count(n) as count" --csv | head -2 | tail -1)
    
    if [ "$REMAINING" -eq "0" ]; then
        break
    fi
done

echo
echo "Cleanup completed! Deleted $TOTAL_DELETED isolated nodes."
echo

# Final verification
FINAL_COUNT=$(docker exec -i $CONTAINER redis-cli GRAPH.QUERY "$DB_NAME" \
    "MATCH (n) WHERE NOT (n)-[]-() RETURN count(n) as count" --csv | head -2 | tail -1)

if [ "$FINAL_COUNT" -eq "0" ]; then
    echo "✅ Database is now clean - no isolated nodes remaining."
else
    echo "⚠️  Warning: $FINAL_COUNT isolated nodes still remain."
fi
