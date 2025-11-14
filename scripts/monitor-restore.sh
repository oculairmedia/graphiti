#!/bin/bash
#
# Monitor FalkorDB Restore Progress
# Shows real-time node and edge sync status
#

set -euo pipefail

cd "$(dirname "$0")/.."

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "╔════════════════════════════════════════════════════════════╗"
echo "║         FalkorDB Restore Progress Monitor                 ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Press Ctrl+C to stop monitoring"
echo ""

last_node_count=0
last_edge_count=0
start_time=$(date +%s)

while true; do
    # Get current counts
    node_count=$(docker-compose exec -T falkordb redis-cli \
        GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)" 2>/dev/null | \
        grep -oP '\d+' | head -1 || echo "0")
    
    edge_count=$(docker-compose exec -T falkordb redis-cli \
        GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" 2>/dev/null | \
        grep -oP '\d+' | head -1 || echo "0")
    
    # Calculate deltas
    node_delta=$((node_count - last_node_count))
    edge_delta=$((edge_count - last_edge_count))
    
    # Calculate elapsed time
    current_time=$(date +%s)
    elapsed=$((current_time - start_time))
    elapsed_min=$((elapsed / 60))
    elapsed_sec=$((elapsed % 60))
    
    # Determine status
    if [ "$node_delta" -eq 0 ] && [ "$edge_delta" -eq 0 ] && [ "$edge_count" -gt 0 ]; then
        status="${GREEN}✅ COMPLETE${NC}"
    elif [ "$edge_count" -eq 0 ] && [ "$node_count" -gt 0 ]; then
        status="${YELLOW}⏳ Syncing edges...${NC}"
    elif [ "$node_count" -eq 0 ]; then
        status="${YELLOW}⏳ Syncing nodes...${NC}"
    else
        status="${BLUE}🔄 In progress${NC}"
    fi
    
    # Clear screen and display status
    clear
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║         FalkorDB Restore Progress Monitor                 ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
    printf "Status: ${status}\n"
    echo ""
    echo "Current State:"
    printf "  Nodes: ${GREEN}%'d${NC}" "$node_count"
    if [ "$node_delta" -gt 0 ]; then
        printf " (+%'d)" "$node_delta"
    fi
    echo ""
    printf "  Edges: ${GREEN}%'d${NC}" "$edge_count"
    if [ "$edge_delta" -gt 0 ]; then
        printf " (+%'d)" "$edge_delta"
    fi
    echo ""
    echo ""
    printf "Elapsed: %02d:%02d\n" "$elapsed_min" "$elapsed_sec"
    echo ""
    echo "Press Ctrl+C to stop monitoring"
    
    # Store counts for next iteration
    last_node_count=$node_count
    last_edge_count=$edge_count
    
    # Wait before next check
    sleep 5
done
