#!/bin/bash
# Monitor Neo4j → FalkorDB sync progress
TARGET_EDGES=121139

echo "===== FalkorDB Sync Progress Monitor ====="
echo "Target: $TARGET_EDGES edges"
echo "Started: $(date)"
echo ""

while true; do
  CURRENT=$(docker exec graphiti-falkordb-1 redis-cli -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[e]->() RETURN count(e)" --csv 2>/dev/null | head -1 | grep -oE '[0-9]+')
  
  if [ -n "$CURRENT" ]; then
    PERCENT=$((CURRENT * 100 / TARGET_EDGES))
    REMAINING=$((TARGET_EDGES - CURRENT))
    RATE_PER_MIN=$((REMAINING / 30))  # Rough estimate at current rate
    
    printf "\r[%s] %6d / %6d edges (%3d%%) | Remaining: %6d | ~%d min left   " \
      "$(date '+%H:%M:%S')" "$CURRENT" "$TARGET_EDGES" "$PERCENT" "$REMAINING" "$RATE_PER_MIN"
    
    if [ "$CURRENT" -ge "$TARGET_EDGES" ]; then
      echo ""
      echo "✅ Sync complete at $(date)!"
      exit 0
    fi
  fi
  
  sleep 30
done
