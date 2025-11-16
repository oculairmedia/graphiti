#!/bin/bash
#
# Monitor Cold Boot Progress
# Shows real-time sync status and alerts when complete
#

cd "$(dirname "$0")"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "╔════════════════════════════════════════════════════════════╗"
echo "║          Graphiti Cold Boot Progress Monitor              ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Target from Neo4j
echo -e "${BLUE}Checking Neo4j source...${NC}"
NEO4J_EDGES=$(docker-compose exec -T neo4j cypher-shell -u neo4j -p graphiti123 \
  "MATCH ()-[r]->() RETURN count(r) as edge_count;" 2>/dev/null | \
  grep -oP '\d+' | head -1 || echo "0")
echo -e "${GREEN}Neo4j has $NEO4J_EDGES edges to sync${NC}"
echo ""

# Monitor sync progress
echo -e "${BLUE}Monitoring FalkorDB sync progress...${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop monitoring${NC}"
echo ""

LAST_EDGE_COUNT=0
STABLE_COUNT=0

while true; do
    # Check if init container is still running
    INIT_STATUS=$(docker-compose ps graphiti-init --format json 2>/dev/null | jq -r '.State' 2>/dev/null || echo "unknown")
    
    # Get current counts
    CURRENT_NODES=$(docker-compose exec -T falkordb redis-cli \
        GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)" 2>/dev/null | \
        grep -oP '\d+' | head -1 || echo "0")
    
    CURRENT_EDGES=$(docker-compose exec -T falkordb redis-cli \
        GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" 2>/dev/null | \
        grep -oP '\d+' | head -1 || echo "0")
    
    # Calculate progress
    if [ "$NEO4J_EDGES" -gt 0 ]; then
        PROGRESS=$((CURRENT_EDGES * 100 / NEO4J_EDGES))
    else
        PROGRESS=0
    fi
    
    # Check if stable
    if [ "$CURRENT_EDGES" -eq "$LAST_EDGE_COUNT" ] && [ "$CURRENT_EDGES" -gt 0 ]; then
        STABLE_COUNT=$((STABLE_COUNT + 1))
    else
        STABLE_COUNT=0
    fi
    
    # Display progress
    printf "\r[%s] Nodes: %6s | Edges: %6s / %s (%3s%%) | Stable: %d/3 | Init: %s     " \
        "$(date +'%H:%M:%S')" \
        "$CURRENT_NODES" \
        "$CURRENT_EDGES" \
        "$NEO4J_EDGES" \
        "$PROGRESS" \
        "$STABLE_COUNT" \
        "$INIT_STATUS"
    
    # Check if complete
    if [ "$STABLE_COUNT" -ge 3 ] && [ "$INIT_STATUS" = "exited" ]; then
        echo ""
        echo ""
        echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║           ✅ SYNC COMPLETE - VISUALIZER STARTING           ║${NC}"
        echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${GREEN}Final state:${NC}"
        echo -e "  • Nodes: $CURRENT_NODES"
        echo -e "  • Edges: $CURRENT_EDGES / $NEO4J_EDGES"
        echo ""
        echo -e "${BLUE}Checking visualizer status...${NC}"
        sleep 5
        
        VISUALIZER_STATUS=$(docker-compose ps graph-visualizer-rust --format json 2>/dev/null | jq -r '.State' 2>/dev/null || echo "unknown")
        if [ "$VISUALIZER_STATUS" = "running" ]; then
            echo -e "${GREEN}✅ Visualizer is running!${NC}"
            echo ""
            echo "Access points:"
            echo "  • Frontend: http://localhost:8084"
            echo "  • API: http://localhost:3000/api/stats"
        else
            echo -e "${YELLOW}⚠️  Visualizer not started yet (status: $VISUALIZER_STATUS)${NC}"
            echo "Check logs: docker-compose logs graph-visualizer-rust"
        fi
        
        break
    fi
    
    LAST_EDGE_COUNT=$CURRENT_EDGES
    sleep 5
done

echo ""
