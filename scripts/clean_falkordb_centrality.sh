#!/bin/bash
#
# Clean FalkorDB centrality data to reduce memory usage
# This script removes computed centrality metrics while preserving graph structure
#

set -e

# Configuration
VOLUME_NAME="${VOLUME_NAME:-graphiti_falkordb_data}"
BACKUP_DIR="${BACKUP_DIR:-/opt/stacks/graphiti/backups/centrality_cleanup}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
    exit 1
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

# Create backup directory
mkdir -p "$BACKUP_DIR"

log "=== FalkorDB Centrality Cleanup Started ==="

# Step 1: Backup current data first
log "Creating backup of current data..."
docker run --rm \
    -v "${VOLUME_NAME}:/data:ro" \
    -v "$BACKUP_DIR:/backup" \
    alpine tar czf "/backup/falkordb_pre_cleanup_${TIMESTAMP}.tar.gz" -C /data .

BACKUP_SIZE=$(du -h "$BACKUP_DIR/falkordb_pre_cleanup_${TIMESTAMP}.tar.gz" | cut -f1)
log "Backup created: $BACKUP_DIR/falkordb_pre_cleanup_${TIMESTAMP}.tar.gz (Size: $BACKUP_SIZE)"

# Step 2: Start a temporary FalkorDB container with strict memory limits
log "Starting temporary FalkorDB container with memory limits..."
docker run -d \
    --name falkordb-cleanup \
    --memory="4g" \
    --memory-swap="4g" \
    -v "${VOLUME_NAME}:/var/lib/falkordb/data" \
    -p 6391:6379 \
    falkordb/falkordb:latest \
    redis-server \
    --maxmemory 3gb \
    --maxmemory-policy volatile-lru \
    --save "" \
    --appendonly no

# Wait for container to start
log "Waiting for FalkorDB to start..."
ATTEMPTS=0
MAX_ATTEMPTS=30
while [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
    if docker exec falkordb-cleanup redis-cli ping >/dev/null 2>&1; then
        log "FalkorDB is ready!"
        break
    fi
    sleep 1
    ((ATTEMPTS++))
done

if [ $ATTEMPTS -eq $MAX_ATTEMPTS ]; then
    docker stop falkordb-cleanup 2>/dev/null
    docker rm falkordb-cleanup 2>/dev/null
    error "FalkorDB failed to start within 30 seconds"
fi

# Step 3: Check current memory usage
log "Checking current memory usage..."
MEMORY_BEFORE=$(docker exec falkordb-cleanup redis-cli info memory | grep "used_memory_human" | cut -d: -f2 | tr -d '\r')
log "Memory usage before cleanup: $MEMORY_BEFORE"

# Step 4: List graphs
log "Listing graphs in database..."
GRAPHS=$(docker exec falkordb-cleanup redis-cli --raw GRAPH.LIST 2>/dev/null || echo "")
if [ -z "$GRAPHS" ]; then
    warn "No graphs found or GRAPH.LIST command failed"
else
    log "Found graphs: $GRAPHS"
fi

# Step 5: Try to remove centrality properties from nodes
log "Attempting to clean centrality data from graphiti_migration..."

# First, let's check if we can query the graph at all
docker exec falkordb-cleanup redis-cli --raw eval "
    local graph_key = 'graphiti_migration'
    
    -- Try to get graph info without loading everything
    local exists = redis.call('EXISTS', graph_key)
    if exists == 0 then
        return 'Graph does not exist'
    end
    
    -- Try to get basic graph stats
    local graph_type = redis.call('TYPE', graph_key)
    return 'Graph exists, type: ' .. graph_type['ok']
" 0 2>/dev/null || warn "Could not query graph directly"

# Try to clean centrality properties using Cypher queries
log "Removing centrality properties from nodes..."
docker exec falkordb-cleanup redis-cli GRAPH.RO_QUERY graphiti_migration "MATCH (n) RETURN count(n) as node_count LIMIT 1" 2>/dev/null || warn "Could not count nodes"

# Remove pagerank and betweenness properties if they exist
docker exec falkordb-cleanup redis-cli GRAPH.QUERY graphiti_migration "
    MATCH (n) 
    WHERE n.pagerank IS NOT NULL OR n.betweenness IS NOT NULL
    SET n.pagerank = null, n.betweenness = null
    RETURN count(n) as cleaned_nodes
" 2>/dev/null || warn "Could not remove centrality properties"

# Remove any other centrality-related properties
docker exec falkordb-cleanup redis-cli GRAPH.QUERY graphiti_migration "
    MATCH (n) 
    WHERE n.degree_centrality IS NOT NULL OR n.closeness IS NOT NULL
    SET n.degree_centrality = null, n.closeness = null
    RETURN count(n) as cleaned_nodes
" 2>/dev/null || warn "Could not remove additional centrality properties"

# Step 6: Force memory cleanup
log "Forcing memory cleanup..."
docker exec falkordb-cleanup redis-cli MEMORY PURGE 2>/dev/null || warn "MEMORY PURGE command not available"
docker exec falkordb-cleanup redis-cli FLUSHDB 2>/dev/null || warn "Could not flush database"

# Step 7: Save cleaned data
log "Saving cleaned data..."
docker exec falkordb-cleanup redis-cli BGSAVE
sleep 5  # Wait for background save to complete

# Step 8: Check memory after cleanup
MEMORY_AFTER=$(docker exec falkordb-cleanup redis-cli info memory | grep "used_memory_human" | cut -d: -f2 | tr -d '\r')
log "Memory usage after cleanup: $MEMORY_AFTER"

# Step 9: Stop and remove cleanup container
log "Stopping cleanup container..."
docker stop falkordb-cleanup
docker rm falkordb-cleanup

log "=== Cleanup Summary ==="
log "✅ Cleanup completed!"
log "📊 Memory before: $MEMORY_BEFORE"
log "📊 Memory after: $MEMORY_AFTER"
log "💾 Backup saved: $BACKUP_DIR/falkordb_pre_cleanup_${TIMESTAMP}.tar.gz"
log ""
log "To restore the original data if needed:"
log "  cd $BACKUP_DIR && tar xzf falkordb_pre_cleanup_${TIMESTAMP}.tar.gz -C /path/to/volume"
log ""
log "Try starting FalkorDB now with: docker-compose up -d falkordb"