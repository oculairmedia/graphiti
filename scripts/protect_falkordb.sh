#!/bin/bash
# =============================================================================
# FalkorDB Data Protection Script
# =============================================================================
# Creates a copy of FalkorDB data outside Docker volumes for extra protection.
# This ensures data survives even aggressive `docker volume prune` commands.
#
# Usage:
#   ./protect_falkordb.sh              # Create protection copy
#   ./protect_falkordb.sh --restore    # Restore from protection copy
#   ./protect_falkordb.sh --status     # Check protection status
#
# Recommended: Run this after significant data changes or before maintenance.
# =============================================================================

set -e

# Configuration
DOCKER_VOLUME_PATH="/var/lib/docker/volumes/graphiti_falkordb_data/_data"
EXTERNAL_BACKUP_PATH="/opt/stacks/graphiti/data/falkordb_external"
CONTAINER_NAME="graphiti-falkordb-1"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

show_status() {
    echo "=============================================="
    echo "   FalkorDB Protection Status"
    echo "=============================================="
    echo ""
    
    # Check Docker volume
    if [[ -f "$DOCKER_VOLUME_PATH/falkordb.rdb" ]]; then
        SIZE=$(du -h "$DOCKER_VOLUME_PATH/falkordb.rdb" | cut -f1)
        MODIFIED=$(stat -c %y "$DOCKER_VOLUME_PATH/falkordb.rdb" 2>/dev/null | cut -d. -f1)
        log_info "Docker Volume: ✓ EXISTS"
        log_info "  Path: $DOCKER_VOLUME_PATH/falkordb.rdb"
        log_info "  Size: $SIZE"
        log_info "  Modified: $MODIFIED"
    else
        log_error "Docker Volume: ✗ MISSING"
    fi
    echo ""
    
    # Check external backup
    if [[ -f "$EXTERNAL_BACKUP_PATH/falkordb.rdb" ]]; then
        SIZE=$(du -h "$EXTERNAL_BACKUP_PATH/falkordb.rdb" | cut -f1)
        MODIFIED=$(stat -c %y "$EXTERNAL_BACKUP_PATH/falkordb.rdb" 2>/dev/null | cut -d. -f1)
        log_info "External Backup: ✓ EXISTS"
        log_info "  Path: $EXTERNAL_BACKUP_PATH/falkordb.rdb"
        log_info "  Size: $SIZE"
        log_info "  Modified: $MODIFIED"
    else
        log_warn "External Backup: ✗ NOT FOUND"
        log_warn "  Run: $0 to create protection copy"
    fi
    echo ""
    
    # Check container status
    if docker ps --format "{{.Names}}" | grep -q "$CONTAINER_NAME"; then
        MEMORY=$(docker stats --no-stream --format "{{.MemUsage}}" "$CONTAINER_NAME" 2>/dev/null || echo "unknown")
        log_info "Container: ✓ RUNNING ($MEMORY)"
    else
        log_warn "Container: ✗ NOT RUNNING"
    fi
    echo ""
    
    # Check data integrity
    if docker exec "$CONTAINER_NAME" redis-cli ping &>/dev/null; then
        KEYS=$(docker exec "$CONTAINER_NAME" redis-cli DBSIZE 2>/dev/null | grep -oP '\d+' || echo "?")
        EDGES=$(docker exec "$CONTAINER_NAME" redis-cli GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" --csv 2>/dev/null | tail -1 | tr -d ' ' || echo "?")
        NODES=$(docker exec "$CONTAINER_NAME" redis-cli GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)" --csv 2>/dev/null | tail -1 | tr -d ' ' || echo "?")
        log_info "Data Integrity:"
        log_info "  Keys: $KEYS"
        log_info "  Nodes: $NODES"
        log_info "  Edges: $EDGES"
    fi
}

create_protection_copy() {
    echo "=============================================="
    echo "   Creating FalkorDB Protection Copy"
    echo "=============================================="
    echo ""
    
    mkdir -p "$EXTERNAL_BACKUP_PATH"
    
    # Trigger BGSAVE first
    log_step "Triggering BGSAVE..."
    if docker exec "$CONTAINER_NAME" redis-cli BGSAVE &>/dev/null; then
        sleep 5  # Wait for save to complete
        log_info "BGSAVE completed"
    else
        log_warn "Could not trigger BGSAVE (container may not be running)"
    fi
    
    # Copy from Docker volume to external location
    log_step "Copying RDB file to external location..."
    if [[ -f "$DOCKER_VOLUME_PATH/falkordb.rdb" ]]; then
        cp "$DOCKER_VOLUME_PATH/falkordb.rdb" "$EXTERNAL_BACKUP_PATH/falkordb.rdb"
        
        # Create metadata
        cat > "$EXTERNAL_BACKUP_PATH/protection.meta" << EOF
{
    "created": "$(date -Iseconds)",
    "source": "$DOCKER_VOLUME_PATH/falkordb.rdb",
    "size": "$(du -h "$EXTERNAL_BACKUP_PATH/falkordb.rdb" | cut -f1)",
    "md5": "$(md5sum "$EXTERNAL_BACKUP_PATH/falkordb.rdb" | cut -d' ' -f1)"
}
EOF
        
        SIZE=$(du -h "$EXTERNAL_BACKUP_PATH/falkordb.rdb" | cut -f1)
        log_info "Protection copy created: $EXTERNAL_BACKUP_PATH/falkordb.rdb ($SIZE)"
    else
        log_error "Source RDB file not found at $DOCKER_VOLUME_PATH/falkordb.rdb"
        exit 1
    fi
    
    echo ""
    log_info "Protection copy complete!"
    log_info "This copy is OUTSIDE Docker and will survive 'docker volume prune'"
}

restore_from_protection() {
    echo "=============================================="
    echo "   Restoring FalkorDB from Protection Copy"
    echo "=============================================="
    echo ""
    
    if [[ ! -f "$EXTERNAL_BACKUP_PATH/falkordb.rdb" ]]; then
        log_error "No protection copy found at $EXTERNAL_BACKUP_PATH/falkordb.rdb"
        exit 1
    fi
    
    # Stop FalkorDB container
    log_step "Stopping FalkorDB container..."
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    sleep 2
    
    # Ensure volume directory exists
    mkdir -p "$DOCKER_VOLUME_PATH"
    
    # Copy from external to Docker volume
    log_step "Restoring RDB file..."
    cp "$EXTERNAL_BACKUP_PATH/falkordb.rdb" "$DOCKER_VOLUME_PATH/falkordb.rdb"
    
    # Start FalkorDB container
    log_step "Starting FalkorDB container..."
    docker start "$CONTAINER_NAME" 2>/dev/null || {
        log_warn "Could not start container directly, trying docker-compose..."
        cd /opt/stacks/graphiti && docker-compose up -d falkordb
    }
    
    # Wait for startup
    log_step "Waiting for FalkorDB to load data..."
    for i in {1..60}; do
        if docker exec "$CONTAINER_NAME" redis-cli ping &>/dev/null; then
            break
        fi
        sleep 2
    done
    
    # Verify
    if docker exec "$CONTAINER_NAME" redis-cli ping &>/dev/null; then
        EDGES=$(docker exec "$CONTAINER_NAME" redis-cli GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" --csv 2>/dev/null | tail -1 || echo "?")
        log_info "Restore complete! Edges: $EDGES"
    else
        log_error "FalkorDB did not start properly after restore"
        exit 1
    fi
}

# Main
case "${1:-}" in
    --status)
        show_status
        ;;
    --restore)
        restore_from_protection
        ;;
    *)
        create_protection_copy
        show_status
        ;;
esac
