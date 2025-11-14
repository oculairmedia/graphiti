#!/bin/bash
#
# Graphiti Cold Boot Initialization Script
# Manages proper startup sequence:
# 1. Wait for databases (Neo4j + FalkorDB)
# 2. Clear FalkorDB
# 3. Trigger Neo4j -> FalkorDB restore
# 4. Wait for restore completion
# 5. Signal ready for worker ingestion
#

set -euo pipefail

# Configuration
NEO4J_URI="${NEO4J_URI:-bolt://neo4j:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-graphiti123}"
FALKORDB_HOST="${FALKORDB_HOST:-falkordb}"
FALKORDB_PORT="${FALKORDB_PORT:-6379}"
FALKORDB_DATABASE="${FALKORDB_DATABASE:-graphiti_migration}"
SYNC_SERVICE_URL="${SYNC_SERVICE_URL:-http://graphiti-sync-rs:8080}"
SYNC_TIMEOUT="${SYNC_TIMEOUT:-600}"  # 10 minutes
CHECK_INTERVAL="${CHECK_INTERVAL:-5}"  # 5 seconds

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} ✅ $1"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} ❌ $1"
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} ⚠️  $1"
}

# Function to wait for a service to be healthy
wait_for_service() {
    local service_name=$1
    local health_check=$2
    local timeout=${3:-60}
    local elapsed=0
    
    log "Waiting for $service_name to be ready..."
    
    while [ $elapsed -lt $timeout ]; do
        if eval "$health_check" >/dev/null 2>&1; then
            log_success "$service_name is ready"
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    
    log_error "$service_name failed to become ready within ${timeout}s"
    return 1
}

# Function to check Neo4j connectivity
check_neo4j() {
    # Extract host from bolt URI
    local neo4j_host=$(echo "$NEO4J_URI" | sed 's|bolt://||' | cut -d: -f1)
    local neo4j_port=$(echo "$NEO4J_URI" | sed 's|bolt://||' | cut -d: -f2)
    
    # Try to connect using nc or timeout+bash
    timeout 2 bash -c "cat < /dev/null > /dev/tcp/${neo4j_host}/${neo4j_port}" 2>/dev/null
}

# Function to check FalkorDB connectivity
check_falkordb() {
    redis-cli -h "$FALKORDB_HOST" -p "$FALKORDB_PORT" PING 2>/dev/null | grep -q "PONG"
}

# Function to count nodes in Neo4j
count_neo4j_nodes() {
    # This is a placeholder - actual implementation would need cypher-shell or API
    # For now, we'll check if Neo4j is accessible
    check_neo4j
}

# Function to count nodes in FalkorDB
count_falkor_nodes() {
    local count=$(redis-cli -h "$FALKORDB_HOST" -p "$FALKORDB_PORT" \
        GRAPH.QUERY "$FALKORDB_DATABASE" "MATCH (n) RETURN count(n)" 2>/dev/null | \
        grep -oP '\d+' | head -1)
    echo "${count:-0}"
}

# Function to clear FalkorDB
clear_falkordb() {
    log "Clearing FalkorDB database: $FALKORDB_DATABASE"
    
    # Delete the entire graph
    redis-cli -h "$FALKORDB_HOST" -p "$FALKORDB_PORT" \
        GRAPH.DELETE "$FALKORDB_DATABASE" >/dev/null 2>&1 || true
    
    # Verify it's cleared
    local count=$(count_falkor_nodes)
    if [ "$count" -eq 0 ]; then
        log_success "FalkorDB cleared successfully"
        return 0
    else
        log_warning "FalkorDB may not be fully cleared (remaining nodes: $count)"
        return 1
    fi
}

# Function to trigger sync service restore
trigger_restore() {
    log "Triggering Neo4j -> FalkorDB restore via sync service..."
    
    # The sync service runs continuously, so we just need to verify it's working
    # Check sync service health
    if curl -sf "$SYNC_SERVICE_URL/health" >/dev/null 2>&1; then
        log_success "Sync service is healthy and will restore FalkorDB automatically"
        return 0
    else
        log_error "Sync service is not responding at $SYNC_SERVICE_URL/health"
        return 1
    fi
}

# Function to count edges in FalkorDB
count_falkor_edges() {
    local count=$(redis-cli -h "$FALKORDB_HOST" -p "$FALKORDB_PORT" \
        GRAPH.QUERY "$FALKORDB_DATABASE" "MATCH ()-[r]->() RETURN count(r)" 2>/dev/null | \
        grep -oP '\d+' | head -1)
    echo "${count:-0}"
}

# Function to wait for restore completion (both nodes AND edges)
wait_for_restore() {
    local timeout=$SYNC_TIMEOUT
    local elapsed=0
    
    log "Waiting for Neo4j -> FalkorDB restore to complete..."
    log "This may take several minutes (syncing nodes + edges)..."
    
    # Wait for both nodes AND edges to appear and stabilize
    local last_node_count=0
    local last_edge_count=0
    local stable_count=0
    
    while [ $elapsed -lt $timeout ]; do
        local current_node_count=$(count_falkor_nodes)
        local current_edge_count=$(count_falkor_edges)
        
        if [ "$current_node_count" -gt 0 ]; then
            # Check if BOTH nodes and edges are stable
            if [ "$current_node_count" -eq "$last_node_count" ] && \
               [ "$current_edge_count" -eq "$last_edge_count" ] && \
               [ "$current_edge_count" -gt 0 ]; then
                stable_count=$((stable_count + 1))
                
                # If both counts stable for 3 checks (15 seconds), consider complete
                if [ $stable_count -ge 3 ]; then
                    log_success "Restore complete: $current_node_count nodes, $current_edge_count edges"
                    return 0
                fi
            else
                stable_count=0
                log "Progress: $current_node_count nodes, $current_edge_count edges..."
            fi
            
            last_node_count=$current_node_count
            last_edge_count=$current_edge_count
        fi
        
        sleep $CHECK_INTERVAL
        elapsed=$((elapsed + CHECK_INTERVAL))
    done
    
    log_error "Restore did not complete within ${timeout}s"
    log_error "Current state: $last_node_count nodes, $last_edge_count edges"
    return 1
}

# Function to verify restore quality
verify_restore() {
    log "Verifying restore quality..."
    
    local falkor_node_count=$(count_falkor_nodes)
    local falkor_edge_count=$(count_falkor_edges)
    
    if [ "$falkor_node_count" -gt 0 ] && [ "$falkor_edge_count" -gt 0 ]; then
        log_success "Restore verification passed:"
        log "  • Nodes: $falkor_node_count"
        log "  • Edges: $falkor_edge_count"
        
        # Check sync service metrics if available
        if curl -sf "$SYNC_SERVICE_URL/metrics" >/dev/null 2>&1; then
            log "Sync service metrics available at $SYNC_SERVICE_URL/metrics"
        fi
        
        return 0
    else
        log_error "Restore verification failed:"
        log_error "  • Nodes: $falkor_node_count"
        log_error "  • Edges: $falkor_edge_count"
        
        if [ "$falkor_edge_count" -eq 0 ]; then
            log_error "Edge sync may still be in progress or failed"
        fi
        
        return 1
    fi
}

# Function to create ready marker file
create_ready_marker() {
    local marker_file="${READY_MARKER_FILE:-/tmp/graphiti-init-complete}"
    touch "$marker_file"
    log_success "Created ready marker: $marker_file"
}

# Main initialization sequence
main() {
    log "🚀 Starting Graphiti Cold Boot Initialization"
    log "================================================"
    
    # Step 1: Wait for databases
    log "Step 1: Waiting for databases to be ready..."
    if ! wait_for_service "Neo4j" check_neo4j 120; then
        log_error "Neo4j is not available"
        exit 1
    fi
    
    if ! wait_for_service "FalkorDB" check_falkordb 60; then
        log_error "FalkorDB is not available"
        exit 1
    fi
    
    # Step 2: Check if restore is needed
    log "Step 2: Checking if restore is needed..."
    local falkor_count=$(count_falkor_nodes)
    
    if [ "$falkor_count" -gt 0 ]; then
        log_warning "FalkorDB already contains $falkor_count nodes"
        
        if [ "${NO_PROMPT:-0}" = "1" ]; then
            log "Auto-mode: Clearing and restoring from Neo4j..."
        else
            read -p "Clear and restore from Neo4j? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                log "Skipping restore, using existing data"
                create_ready_marker
                exit 0
            fi
        fi
    fi
    
    # Step 3: Clear FalkorDB
    log "Step 3: Clearing FalkorDB..."
    if ! clear_falkordb; then
        log_error "Failed to clear FalkorDB"
        exit 1
    fi
    
    # Step 4: Wait for sync service
    log "Step 4: Waiting for sync service..."
    if ! wait_for_service "Sync Service" "curl -sf $SYNC_SERVICE_URL/health" 60; then
        log_error "Sync service is not available"
        exit 1
    fi
    
    # Step 5: Trigger restore
    log "Step 5: Triggering restore..."
    if ! trigger_restore; then
        log_error "Failed to trigger restore"
        exit 1
    fi
    
    # Step 6: Wait for restore completion
    log "Step 6: Waiting for restore to complete..."
    if ! wait_for_restore; then
        log_error "Restore did not complete successfully"
        exit 1
    fi
    
    # Step 7: Verify restore
    log "Step 7: Verifying restore..."
    if ! verify_restore; then
        log_error "Restore verification failed"
        exit 1
    fi
    
    # Step 8: Create ready marker
    log "Step 8: Marking system as ready..."
    create_ready_marker
    
    log_success "================================================"
    log_success "🎉 Cold Boot Initialization Complete!"
    log_success "System is ready for worker ingestion"
    log_success "================================================"
}

# Handle command line arguments
case "${1:-}" in
    "--help"|"-h")
        echo "Usage: $0 [--help|--no-prompt]"
        echo ""
        echo "Graphiti Cold Boot Initialization Script"
        echo ""
        echo "This script manages the proper startup sequence for Graphiti:"
        echo "  1. Wait for Neo4j and FalkorDB"
        echo "  2. Clear FalkorDB"
        echo "  3. Restore FalkorDB from Neo4j"
        echo "  4. Verify restore completion"
        echo "  5. Signal ready for worker ingestion"
        echo ""
        echo "Options:"
        echo "  --help        Show this help message"
        echo "  --no-prompt   Skip confirmation prompts (for automation)"
        exit 0
        ;;
    "--no-prompt")
        # Run without prompts for automation
        NO_PROMPT=1 main
        ;;
    *)
        main "$@"
        ;;
esac
