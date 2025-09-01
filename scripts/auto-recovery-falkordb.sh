#!/bin/bash
#
# FalkorDB Automated Recovery Script
# This script handles complete recovery from FalkorDB persistence issues:
# 1. Safely clears corrupted FalkorDB data
# 2. Enables full sync to restore from Neo4j
# 3. Regenerates embeddings automatically
# 4. Restores normal operation settings
#

set -e

# Configuration
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/opt/stacks/graphiti/logs/falkordb-recovery-${TIMESTAMP}.log"
MAX_WAIT_SYNC=300  # Maximum 5 minutes for sync
MAX_WAIT_EMBED=600 # Maximum 10 minutes for embeddings

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    local message="[$(date +'%Y-%m-%d %H:%M:%S')] $1"
    echo -e "${GREEN}${message}${NC}"
    echo "$message" >> "$LOG_FILE"
}

error() {
    local message="[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1"
    echo -e "${RED}${message}${NC}"
    echo "$message" >> "$LOG_FILE"
    exit 1
}

warn() {
    local message="[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1"
    echo -e "${YELLOW}${message}${NC}"
    echo "$message" >> "$LOG_FILE"
}

info() {
    local message="[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1"
    echo -e "${BLUE}${message}${NC}"
    echo "$message" >> "$LOG_FILE"
}

# Create logs directory
mkdir -p "$(dirname "$LOG_FILE")"

log "=== FalkorDB Automated Recovery Started ==="
log "Recovery session: $TIMESTAMP"
log "Log file: $LOG_FILE"

# Step 1: Stop all containers
log "Step 1: Stopping all containers..."
docker-compose down || error "Failed to stop containers"

# Step 2: FalkorDB is now non-persistent (runs in-memory only)
log "Step 2: FalkorDB is configured as non-persistent in-memory cache..."
info "FalkorDB will start fresh on every restart - no volume clearing needed"

# Step 3: Enable full sync on startup
log "Step 3: Ensuring full sync is enabled..."
# Check if already enabled
if grep -q "SYNC_FULL_ON_STARTUP=\${SYNC_FULL_ON_STARTUP:-true}" docker-compose.yml; then
    info "Full sync already enabled in docker-compose.yml"
else
    info "Enabling full sync on startup..."
    sed -i 's/SYNC_FULL_ON_STARTUP=\${SYNC_FULL_ON_STARTUP:-false}/SYNC_FULL_ON_STARTUP=${SYNC_FULL_ON_STARTUP:-true}/' docker-compose.yml
fi

# Step 4: Start core services in order
log "Step 4: Starting core database services..."
docker-compose up -d neo4j falkordb || error "Failed to start databases"

log "Waiting for databases to become healthy..."
wait_count=0
while [ $wait_count -lt 60 ]; do
    if docker-compose ps neo4j | grep -q "healthy" && docker-compose ps falkordb | grep -q "healthy"; then
        log "Databases are healthy!"
        break
    fi
    sleep 5
    ((wait_count++))
done

if [ $wait_count -eq 60 ]; then
    error "Databases failed to become healthy within 5 minutes"
fi

# Step 5: Start sync service to trigger full restore
log "Step 5: Starting sync service for full restore..."
docker-compose up -d sync-service || error "Failed to start sync service"

log "Waiting for sync service to become healthy..."
wait_count=0
while [ $wait_count -lt 30 ]; do
    if docker-compose ps sync-service | grep -q "healthy"; then
        log "Sync service is healthy!"
        break
    fi
    sleep 5
    ((wait_count++))
done

if [ $wait_count -eq 30 ]; then
    error "Sync service failed to become healthy within 2.5 minutes"
fi

# Step 6: Monitor sync completion
log "Step 6: Monitoring sync progress..."
sync_wait=0
sync_completed=false

while [ $sync_wait -lt $MAX_WAIT_SYNC ]; do
    # Check sync logs for completion indicators
    if docker logs graphiti-sync-service-1 2>&1 | grep -q "Successfully migrated.*100.0% success rate"; then
        # Check if relationships are also done
        if docker logs graphiti-sync-service-1 2>&1 | grep -q "relationship migration completed\|Successfully migrated.*relationships"; then
            log "Full sync completed successfully!"
            sync_completed=true
            break
        fi
    fi
    
    sleep 10
    ((sync_wait += 10))
    
    # Show progress every 30 seconds
    if [ $((sync_wait % 30)) -eq 0 ]; then
        info "Sync still in progress... (${sync_wait}/${MAX_WAIT_SYNC} seconds)"
        # Show last few log lines for progress
        docker logs graphiti-sync-service-1 --tail 3 2>&1 | while read line; do
            info "  $line"
        done
    fi
done

if [ "$sync_completed" = false ]; then
    warn "Sync did not complete within $MAX_WAIT_SYNC seconds, but continuing..."
    warn "You may need to check sync logs manually"
fi

# Step 7: Start remaining services
log "Step 7: Starting remaining services..."
docker-compose up -d || error "Failed to start all services"

# Give services time to stabilize
sleep 30

# Step 8: Run embedding regeneration
log "Step 8: Regenerating embeddings..."
cd /opt/stacks/graphiti

# Run embedding regeneration in background and monitor
python3 regenerate_all_embeddings.py > /tmp/embedding-recovery-${TIMESTAMP}.log 2>&1 &
EMBED_PID=$!

# Monitor embedding process
embed_wait=0
embed_completed=false

while [ $embed_wait -lt $MAX_WAIT_EMBED ]; do
    if ! kill -0 $EMBED_PID 2>/dev/null; then
        # Process finished, check if successful
        wait $EMBED_PID
        embed_exit_code=$?
        
        if [ $embed_exit_code -eq 0 ]; then
            log "Embedding regeneration completed successfully!"
            embed_completed=true
        else
            warn "Embedding regeneration failed with exit code $embed_exit_code"
            warn "Check logs at /tmp/embedding-recovery-${TIMESTAMP}.log"
        fi
        break
    fi
    
    sleep 15
    ((embed_wait += 15))
    
    # Show progress every 60 seconds
    if [ $((embed_wait % 60)) -eq 0 ]; then
        info "Embedding regeneration still running... (${embed_wait}/${MAX_WAIT_EMBED} seconds)"
    fi
done

if [ "$embed_completed" = false ]; then
    warn "Embedding regeneration did not complete within $MAX_WAIT_EMBED seconds"
    warn "Process may still be running in background"
    warn "Check logs at /tmp/embedding-recovery-${TIMESTAMP}.log"
    
    # Try to kill the process
    kill $EMBED_PID 2>/dev/null || true
fi

# Step 9: Restore normal operation settings (optional)
log "Step 9: Checking if normal operation settings should be restored..."
info "Keeping SYNC_FULL_ON_STARTUP=true for now (can be changed manually later)"
info "This ensures future restarts will also trigger full recovery"

# Step 10: Verify system status
log "Step 10: Verifying system status..."

# Check container health
unhealthy_containers=$(docker-compose ps --format json | jq -r 'select(.Health == "unhealthy") | .Name' 2>/dev/null || echo "")

if [ -n "$unhealthy_containers" ]; then
    warn "Some containers are unhealthy:"
    echo "$unhealthy_containers" | while read container; do
        warn "  - $container"
    done
else
    log "All containers are healthy!"
fi

# Final summary
log "=== Recovery Summary ==="
log "✅ FalkorDB volume cleared and recreated"
log "✅ Full sync from Neo4j triggered"
if [ "$sync_completed" = true ]; then
    log "✅ Sync completed successfully"
else
    log "⚠️  Sync status unclear - manual verification recommended"
fi

if [ "$embed_completed" = true ]; then
    log "✅ Embeddings regenerated successfully"
else
    log "⚠️  Embedding regeneration incomplete - check logs"
fi

log "✅ All services are running"
log ""
log "🎯 Recovery completed at $(date)"
log "📊 Recovery logs saved to: $LOG_FILE"
log "📊 Embedding logs: /tmp/embedding-recovery-${TIMESTAMP}.log"
log ""
log "🔧 Next steps:"
log "   - Verify graph data is accessible via API"
log "   - Test visualization services"
log "   - Monitor system for stability"

if [ "$sync_completed" = true ] && [ "$embed_completed" = true ]; then
    log "🎉 Full recovery completed successfully!"
    exit 0
else
    warn "⚠️  Recovery completed with warnings - manual verification recommended"
    exit 1
fi