#!/bin/bash
#
# FalkorDB Automated Backup Script
# Supports multiple backup strategies with retention policies
#

set -e

# Configuration (can be overridden by environment variables)
CONTAINER_NAME="${CONTAINER_NAME:-graphiti-falkordb}"
BACKUP_DIR="${BACKUP_DIR:-/backups/falkordb}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
BACKUP_RETENTION_WEEKLY="${BACKUP_RETENTION_WEEKLY:-4}"  # Keep 4 weekly backups
BACKUP_RETENTION_MONTHLY="${BACKUP_RETENTION_MONTHLY:-3}" # Keep 3 monthly backups

# Logging
LOG_FILE="/var/log/falkordb-backup.log"
exec 1> >(tee -a "$LOG_FILE")
exec 2>&1

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# Check if container is running
check_container() {
    if ! docker ps | grep -q "$CONTAINER_NAME"; then
        log "ERROR: Container $CONTAINER_NAME is not running"
        exit 1
    fi
    log "Container $CONTAINER_NAME is running"
}

# Create backup directories
create_backup_dirs() {
    mkdir -p "$BACKUP_DIR"/{daily,weekly,monthly,snapshots}
    log "Backup directories created/verified"
}

# Test FalkorDB connectivity
test_connectivity() {
    if ! docker exec "$CONTAINER_NAME" redis-cli ping >/dev/null 2>&1; then
        log "ERROR: Cannot connect to FalkorDB"
        exit 1
    fi
    log "FalkorDB connectivity verified"
}

# Get database statistics
get_db_stats() {
    local keys=$(docker exec "$CONTAINER_NAME" redis-cli eval "return #redis.call('keys', '*')" 0)
    local memory=$(docker exec "$CONTAINER_NAME" redis-cli info memory | grep used_memory_human | cut -d: -f2 | tr -d '\r\n')
    log "Database stats: $keys keys, $memory memory used"
}

# Create RDB backup using BGSAVE
backup_rdb() {
    local backup_type="$1"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_name="falkordb_${backup_type}_${timestamp}.rdb"
    local backup_path="$BACKUP_DIR/$backup_type/$backup_name"
    local backup_start_time=$(date +%s)
    
    log "Starting $backup_type backup: $backup_name"
    
    # Get initial LASTSAVE before triggering BGSAVE
    local initial_save=$(docker exec "$CONTAINER_NAME" redis-cli LASTSAVE | tr -d '\r\n')
    
    # Trigger background save
    docker exec "$CONTAINER_NAME" redis-cli BGSAVE
    
    # Wait for BGSAVE to complete
    sleep 2  # Give BGSAVE time to start
    
    # Maximum wait time (30 seconds)
    local max_wait=30
    local waited=0
    
    while [ $waited -lt $max_wait ]; do
        local current_save=$(docker exec "$CONTAINER_NAME" redis-cli LASTSAVE | tr -d '\r\n')
        if [[ "$current_save" != "$initial_save" ]]; then
            break
        fi
        sleep 1
        ((waited++))
    done
    
    if [ $waited -eq $max_wait ]; then
        log "WARNING: BGSAVE may not have completed within $max_wait seconds"
    fi
    
    # Copy the RDB file
    docker cp "$CONTAINER_NAME:/data/falkordb.rdb" "$backup_path"
    
    # Verify backup
    if [[ -f "$backup_path" && -s "$backup_path" ]]; then
        local size_bytes=$(stat -c%s "$backup_path" 2>/dev/null || stat -f%z "$backup_path" 2>/dev/null || echo 0)
        local size=$(du -h "$backup_path" | cut -f1)
        local duration=$(($(date +%s) - ${backup_start_time:-$(date +%s)}))
        
        log "✅ $backup_type backup completed: $backup_name ($size)"
        
        # Create metadata file
        cat > "$backup_path.meta" <<EOF
{
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "type": "$backup_type",
    "size": "$size",
    "container": "$CONTAINER_NAME",
    "keys": $(docker exec "$CONTAINER_NAME" redis-cli eval "return #redis.call('keys', '*')" 0),
    "memory_used": "$(docker exec "$CONTAINER_NAME" redis-cli info memory | grep used_memory_human | cut -d: -f2 | tr -d '\r\n')"
}
EOF
        
        # Update backup status
        if [[ -x "/scripts/backup_status.sh" ]]; then
            /scripts/backup_status.sh update "$backup_type" "success" "$backup_path" "$size_bytes" "$duration" "" || true
        fi
        
    else
        log "❌ $backup_type backup failed: $backup_name"
        
        # Update backup status for failure
        if [[ -x "/scripts/backup_status.sh" ]]; then
            /scripts/backup_status.sh update "$backup_type" "error" "" "0" "0" "Backup file creation failed" || true
        fi
        
        exit 1
    fi
}

# Create AOF backup
backup_aof() {
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_name="falkordb_aof_${timestamp}.aof"
    local backup_path="$BACKUP_DIR/snapshots/$backup_name"
    
    log "Starting AOF backup: $backup_name"
    
    # Check if AOF is enabled
    if docker exec "$CONTAINER_NAME" redis-cli config get appendonly | grep -q "yes"; then
        docker cp "$CONTAINER_NAME:/data/appendonly.aof" "$backup_path" 2>/dev/null || true
        if [[ -f "$backup_path" ]]; then
            log "✅ AOF backup completed: $backup_name"
        else
            log "⚠️  AOF file not available"
        fi
    else
        log "ℹ️  AOF not enabled, skipping AOF backup"
    fi
}

# Cleanup old backups based on retention policy
cleanup_backups() {
    local backup_type="$1"
    local retention_days="$2"
    
    log "Cleaning up old $backup_type backups (retention: $retention_days days)"
    
    find "$BACKUP_DIR/$backup_type" -name "falkordb_${backup_type}_*.rdb" -mtime +$retention_days -delete 2>/dev/null || true
    find "$BACKUP_DIR/$backup_type" -name "falkordb_${backup_type}_*.rdb.meta" -mtime +$retention_days -delete 2>/dev/null || true
    
    local remaining=$(find "$BACKUP_DIR/$backup_type" -name "falkordb_${backup_type}_*.rdb" | wc -l)
    log "Cleanup completed: $remaining $backup_type backups remaining"
}

# Send backup notification
send_notification() {
    local status="$1"
    local message="$2"
    
    # Webhook notification (optional)
    if [[ -n "${BACKUP_WEBHOOK_URL:-}" ]]; then
        curl -s -X POST "$BACKUP_WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -d "{\"status\":\"$status\",\"message\":\"$message\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
            >/dev/null 2>&1 || true
    fi
    
    # Log the notification
    log "📢 Notification: $status - $message"
}

# Main backup function
main() {
    local backup_type="${1:-daily}"
    
    log "=== FalkorDB Backup Started ($backup_type) ==="
    
    check_container
    create_backup_dirs
    test_connectivity
    get_db_stats
    
    case "$backup_type" in
        "daily")
            backup_rdb "daily"
            cleanup_backups "daily" "$BACKUP_RETENTION_DAYS"
            ;;
        "weekly")
            backup_rdb "weekly"
            cleanup_backups "weekly" "$((BACKUP_RETENTION_WEEKLY * 7))"
            ;;
        "monthly")
            backup_rdb "monthly"
            cleanup_backups "monthly" "$((BACKUP_RETENTION_MONTHLY * 30))"
            ;;
        "snapshot")
            backup_rdb "snapshots"
            backup_aof
            ;;
        *)
            log "ERROR: Unknown backup type: $backup_type"
            log "Usage: $0 [daily|weekly|monthly|snapshot]"
            exit 1
            ;;
    esac
    
    send_notification "success" "$backup_type backup completed successfully"
    log "=== FalkorDB Backup Completed ($backup_type) ==="
}

# Run main function
main "$@"