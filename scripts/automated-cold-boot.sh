#!/bin/bash
#
# Automated Cold Boot Script
# Orchestrates the complete cold boot sequence for Graphiti
#

set -euo pipefail

cd "$(dirname "$0")/.."

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} ✅ $1"
}

log_error() {
    echo -e "${RED}[$(date +'%H:%M:%S')]${NC} ❌ $1"
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%H:%M:%S')]${NC} ⚠️  $1"
}

echo "╔════════════════════════════════════════════════════════════╗"
echo "║     Graphiti Automated Cold Boot Initialization           ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Start core databases
log "Step 1: Starting core databases (Neo4j + FalkorDB)..."
docker-compose up -d neo4j falkordb

log "Waiting for databases to be healthy..."
timeout=120
elapsed=0
while [ $elapsed -lt $timeout ]; do
    if docker-compose ps neo4j | grep -q "healthy" && \
       docker-compose ps falkordb | grep -q "healthy"; then
        log_success "Databases are healthy"
        break
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done

if [ $elapsed -ge $timeout ]; then
    log_error "Databases failed to become healthy"
    exit 1
fi

# Step 2: Clear FalkorDB
log "Step 2: Clearing FalkorDB..."
docker-compose exec -T falkordb redis-cli GRAPH.DELETE graphiti_migration 2>/dev/null || true
log_success "FalkorDB cleared"

# Step 3: Start sync service
log "Step 3: Starting sync service..."
docker-compose up -d graphiti-sync-rs

log "Waiting for sync service..."
timeout=60
elapsed=0
while [ $elapsed -lt $timeout ]; do
    if curl -sf http://localhost:18080/health >/dev/null 2>&1; then
        log_success "Sync service is healthy"
        break
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done

# Step 4: Wait for restore (both nodes AND edges)
log "Step 4: Waiting for Neo4j -> FalkorDB restore..."
log "This may take several minutes (syncing nodes + edges)..."

last_node_count=0
last_edge_count=0
stable_count=0
restore_timeout=1200  # Increased to 20 minutes for edge sync
elapsed=0

while [ $elapsed -lt $restore_timeout ]; do
    # Get current node count
    current_node_count=$(docker-compose exec -T falkordb redis-cli \
        GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)" 2>/dev/null | \
        grep -oP '\d+' | head -1 || echo "0")
    
    # Get current edge count
    current_edge_count=$(docker-compose exec -T falkordb redis-cli \
        GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" 2>/dev/null | \
        grep -oP '\d+' | head -1 || echo "0")
    
    if [ "$current_node_count" -gt 0 ]; then
        # Check if both nodes AND edges are stable
        if [ "$current_node_count" -eq "$last_node_count" ] && \
           [ "$current_edge_count" -eq "$last_edge_count" ] && \
           [ "$current_edge_count" -gt 0 ]; then
            stable_count=$((stable_count + 1))
            
            # If both counts stable for 3 checks (15 seconds), consider complete
            if [ $stable_count -ge 3 ]; then
                log_success "Restore complete: $current_node_count nodes, $current_edge_count edges"
                break
            fi
        else
            stable_count=0
            if [ $((elapsed % 30)) -eq 0 ]; then
                log "Progress: $current_node_count nodes, $current_edge_count edges..."
            fi
        fi
        
        last_node_count=$current_node_count
        last_edge_count=$current_edge_count
    fi
    
    sleep 5
    elapsed=$((elapsed + 5))
done

if [ $stable_count -lt 3 ]; then
    log_warning "Restore may not be complete"
    log_warning "Current state: $last_node_count nodes, $last_edge_count edges"
    
    # Ask if user wants to continue anyway
    read -p "Continue starting services? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_error "Aborted by user"
        exit 1
    fi
fi

# Step 5: Start remaining services
log "Step 5: Starting remaining services..."
docker-compose up -d

log "Waiting for all services to be healthy..."
sleep 10

# Verify key services
services=("graph" "graphiti-queued" "graphiti-worker" "graph-visualizer-rust")
all_healthy=true

for service in "${services[@]}"; do
    if docker-compose ps "$service" 2>/dev/null | grep -q "Up"; then
        log_success "$service is running"
    else
        log_error "$service is not running"
        all_healthy=false
    fi
done

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
if [ "$all_healthy" = true ]; then
    echo "║            ✅ Cold Boot Completed Successfully            ║"
else
    echo "║            ⚠️  Cold Boot Completed with Warnings          ║"
fi
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
log "FalkorDB state:"
log "  • Nodes: $last_node_count"
log "  • Edges: $last_edge_count"
echo ""
log "Service URLs:"
log "  • API: http://localhost:8003"
log "  • Frontend: http://localhost:8084"
log "  • Graph Visualizer: http://localhost:3000"
log "  • Neo4j Browser: http://localhost:7474"
echo ""
