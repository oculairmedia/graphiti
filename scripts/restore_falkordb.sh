#!/bin/bash
#
# FalkorDB Restore Script
# Restore from RDB or AOF backups with verification
#

set -e

# Configuration
CONTAINER_NAME="graphiti-falkordb"
BACKUP_DIR="/backups/falkordb"
LOG_FILE="/var/log/falkordb-restore.log"

# Logging
exec 1> >(tee -a "$LOG_FILE")
exec 2>&1

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# Show usage
usage() {
    echo "Usage: $0 <backup_file> [--force]"
    echo ""
    echo "Examples:"
    echo "  $0 /backups/falkordb/daily/falkordb_daily_20250124_143000.rdb"
    echo "  $0 falkordb_weekly_20250120_030000.rdb --force"
    echo ""
    echo "Options:"
    echo "  --force    Skip confirmation prompt"
    echo ""
    echo "Available backups:"
    find "$BACKUP_DIR" -name "*.rdb" -printf "  %TY-%Tm-%Td %TH:%TM  %s bytes  %p\n" 2>/dev/null | sort -r | head -10 || echo "  No backups found"
}

# Validate backup file
validate_backup() {
    local backup_file="$1"
    
    # Check if file exists
    if [[ ! -f "$backup_file" ]]; then
        # Try to find relative path
        local found_file
        found_file=$(find "$BACKUP_DIR" -name "$(basename "$backup_file")" | head -1)
        if [[ -n "$found_file" ]]; then
            backup_file="$found_file"
            log "Found backup file: $backup_file"
        else
            log "ERROR: Backup file not found: $backup_file"
            exit 1
        fi
    fi
    
    # Check if file is readable
    if [[ ! -r "$backup_file" ]]; then
        log "ERROR: Cannot read backup file: $backup_file"
        exit 1
    fi
    
    # Check if file is not empty
    if [[ ! -s "$backup_file" ]]; then
        log "ERROR: Backup file is empty: $backup_file"
        exit 1
    fi
    
    local size=$(du -h "$backup_file" | cut -f1)
    log "Backup file validated: $backup_file ($size)"
    echo "$backup_file"
}

# Check container status
check_container() {
    if ! docker ps | grep -q "$CONTAINER_NAME"; then
        log "ERROR: Container $CONTAINER_NAME is not running"
        exit 1
    fi
    log "Container $CONTAINER_NAME is running"
}

# Create backup of current state before restore
backup_current_state() {
    log "Creating backup of current state before restore..."
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local pre_restore_backup="$BACKUP_DIR/snapshots/pre_restore_${timestamp}.rdb"
    
    mkdir -p "$(dirname "$pre_restore_backup")"
    
    # Create backup using BGSAVE
    docker exec "$CONTAINER_NAME" redis-cli BGSAVE
    
    # Wait for BGSAVE to complete
    local initial_save=$(docker exec "$CONTAINER_NAME" redis-cli LASTSAVE)
    while true; do
        local current_save=$(docker exec "$CONTAINER_NAME" redis-cli LASTSAVE)
        if [[ "$current_save" != "$initial_save" ]]; then
            break
        fi
        sleep 1
    done
    
    # Copy current state
    docker cp "$CONTAINER_NAME:/data/falkordb.rdb" "$pre_restore_backup"
    
    if [[ -f "$pre_restore_backup" ]]; then
        log "✅ Current state backed up to: $pre_restore_backup"
        echo "$pre_restore_backup"
    else
        log "❌ Failed to backup current state"
        exit 1
    fi
}

# Get current database info
get_current_info() {
    local keys=$(docker exec "$CONTAINER_NAME" redis-cli eval "return #redis.call('keys', '*')" 0 2>/dev/null || echo "0")
    local memory=$(docker exec "$CONTAINER_NAME" redis-cli info memory | grep used_memory_human | cut -d: -f2 | tr -d '\r\n' 2>/dev/null || echo "unknown")
    local uptime=$(docker exec "$CONTAINER_NAME" redis-cli info server | grep uptime_in_seconds | cut -d: -f2 | tr -d '\r\n' 2>/dev/null || echo "unknown")
    
    echo "Current database info:"
    echo "  Keys: $keys"
    echo "  Memory: $memory"
    echo "  Uptime: $uptime seconds"
}

# Stop container gracefully
stop_container() {
    log "Stopping container gracefully..."
    docker stop "$CONTAINER_NAME"
    
    # Wait for container to stop
    local timeout=30
    while docker ps | grep -q "$CONTAINER_NAME" && [[ $timeout -gt 0 ]]; do
        sleep 1
        ((timeout--))
    done
    
    if docker ps | grep -q "$CONTAINER_NAME"; then
        log "WARNING: Container did not stop gracefully, forcing stop..."
        docker kill "$CONTAINER_NAME"
    fi
    
    log "Container stopped"
}

# Start container
start_container() {
    log "Starting container..."
    docker start "$CONTAINER_NAME"
    
    # Wait for container to be ready
    local timeout=60
    while ! docker exec "$CONTAINER_NAME" redis-cli ping >/dev/null 2>&1 && [[ $timeout -gt 0 ]]; do
        sleep 1
        ((timeout--))
    done
    
    if ! docker exec "$CONTAINER_NAME" redis-cli ping >/dev/null 2>&1; then
        log "ERROR: Container failed to start properly"
        exit 1
    fi
    
    log "Container started and ready"
}

# Perform the restore
perform_restore() {
    local backup_file="$1"
    
    log "Copying backup file to container..."
    docker cp "$backup_file" "$CONTAINER_NAME:/data/falkordb.rdb"
    
    # Verify the file was copied
    if ! docker exec "$CONTAINER_NAME" test -f /data/falkordb.rdb; then
        log "ERROR: Failed to copy backup file to container"
        exit 1
    fi
    
    log "Backup file copied successfully"
}

# Verify restore
verify_restore() {
    local backup_file="$1"
    
    log "Verifying restore..."
    
    # Check if Redis is responding
    if ! docker exec "$CONTAINER_NAME" redis-cli ping >/dev/null 2>&1; then
        log "ERROR: FalkorDB is not responding after restore"
        return 1
    fi
    
    # Get post-restore info
    local keys=$(docker exec "$CONTAINER_NAME" redis-cli eval "return #redis.call('keys', '*')" 0 2>/dev/null || echo "0")
    local memory=$(docker exec "$CONTAINER_NAME" redis-cli info memory | grep used_memory_human | cut -d: -f2 | tr -d '\r\n' 2>/dev/null || echo "unknown")
    
    log "Post-restore database info:"
    log "  Keys: $keys"
    log "  Memory: $memory"
    
    # Check if we have any keys (basic sanity check)
    if [[ "$keys" == "0" ]]; then
        log "WARNING: Database appears to be empty after restore"
        return 1
    fi
    
    # Check backup metadata if available
    local meta_file="${backup_file}.meta"
    if [[ -f "$meta_file" ]]; then
        local expected_keys=$(grep '"keys"' "$meta_file" | cut -d: -f2 | tr -d ' ,' 2>/dev/null || echo "unknown")
        if [[ "$expected_keys" != "unknown" && "$keys" != "$expected_keys" ]]; then
            log "WARNING: Key count mismatch - Expected: $expected_keys, Got: $keys"
        else
            log "✅ Key count matches backup metadata"
        fi
    fi
    
    log "✅ Restore verification completed"
    return 0
}

# Main restore function
main() {
    local backup_file="$1"
    local force_flag="$2"
    
    if [[ -z "$backup_file" ]]; then
        usage
        exit 1
    fi
    
    log "=== FalkorDB Restore Started ==="
    
    # Validate inputs
    backup_file=$(validate_backup "$backup_file")
    check_container
    
    # Show current state
    log "Current database state:"
    get_current_info
    
    # Confirmation prompt
    if [[ "$force_flag" != "--force" ]]; then
        echo ""
        echo "⚠️  WARNING: This will replace the current database with the backup!"
        echo "Backup file: $backup_file"
        echo ""
        read -p "Do you want to continue? (y/N): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log "Restore cancelled by user"
            exit 0
        fi
    fi
    
    # Create pre-restore backup
    local pre_restore_backup
    pre_restore_backup=$(backup_current_state)
    
    # Perform restore
    log "Starting restore process..."
    
    stop_container
    perform_restore "$backup_file"
    start_container
    
    if verify_restore "$backup_file"; then
        log "✅ Restore completed successfully!"
        log "Pre-restore backup saved as: $pre_restore_backup"
    else
        log "❌ Restore verification failed"
        log "You can rollback using: $0 $pre_restore_backup --force"
        exit 1
    fi
    
    log "=== FalkorDB Restore Completed ==="
}

# Handle command line arguments
case "${1:-}" in
    "-h"|"--help"|"help")
        usage
        exit 0
        ;;
    "")
        usage
        exit 1
        ;;
    *)
        main "$@"
        ;;
esac