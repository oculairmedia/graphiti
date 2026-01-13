#!/bin/bash
# Graphiti Ingestion Monitor
# Shows real-time progress of episode ingestion

INTERVAL=${1:-60}  # Default 60 seconds between updates

echo "=== Graphiti Ingestion Monitor ==="
echo "Press Ctrl+C to stop"
echo ""

# Get baseline
LAST_EPISODES=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH (e:Episodic) RETURN count(e)" --csv 2>/dev/null | grep -E '^[0-9]+$' | head -1)
LAST_ENTITIES=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH (n:Entity) RETURN count(n)" --csv 2>/dev/null | grep -E '^[0-9]+$' | head -1)
LAST_EDGES=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" --csv 2>/dev/null | grep -E '^[0-9]+$' | head -1)
LAST_TIME=$(date +%s)

echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting monitor"
echo "Baseline: Episodes=$LAST_EPISODES | Entities=$LAST_ENTITIES | Edges=$LAST_EDGES"
echo ""

while true; do
    sleep $INTERVAL
    
    # Get current counts
    EPISODES=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH (e:Episodic) RETURN count(e)" --csv 2>/dev/null | grep -E '^[0-9]+$' | head -1)
    ENTITIES=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH (n:Entity) RETURN count(n)" --csv 2>/dev/null | grep -E '^[0-9]+$' | head -1)
    EDGES=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" --csv 2>/dev/null | grep -E '^[0-9]+$' | head -1)
    CURRENT_TIME=$(date +%s)
    
    # Calculate deltas
    DELTA_EPISODES=$((EPISODES - LAST_EPISODES))
    DELTA_ENTITIES=$((ENTITIES - LAST_ENTITIES))
    DELTA_EDGES=$((EDGES - LAST_EDGES))
    ELAPSED=$((CURRENT_TIME - LAST_TIME))
    
    # Calculate rates (per hour)
    RATE_EPISODES=$(echo "scale=1; $DELTA_EPISODES * 3600 / $ELAPSED" | bc)
    RATE_ENTITIES=$(echo "scale=1; $DELTA_ENTITIES * 3600 / $ELAPSED" | bc)
    RATE_EDGES=$(echo "scale=1; $DELTA_EDGES * 3600 / $ELAPSED" | bc)
    
    # Color output
    if [ $DELTA_EPISODES -gt 0 ]; then
        COLOR="\033[0;32m"  # Green
    elif [ $DELTA_EPISODES -lt 0 ]; then
        COLOR="\033[0;31m"  # Red
    else
        COLOR="\033[0;33m"  # Yellow
    fi
    RESET="\033[0m"
    
    echo -e "$(date '+%Y-%m-%d %H:%M:%S') - ${COLOR}Episodes: $EPISODES (+$DELTA_EPISODES, ${RATE_EPISODES}/hr)${RESET} | Entities: $ENTITIES (+$DELTA_ENTITIES) | Edges: $EDGES (+$DELTA_EDGES)"
    
    # Update baseline
    LAST_EPISODES=$EPISODES
    LAST_ENTITIES=$ENTITIES
    LAST_EDGES=$EDGES
    LAST_TIME=$CURRENT_TIME
done
