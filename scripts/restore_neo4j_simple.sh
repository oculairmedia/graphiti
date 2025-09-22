#!/bin/bash
#
# Neo4j Simple Restore Script
# Restore from file-based backups created by backup_neo4j_simple.sh
# Requires database shutdown for safe restoration
#

set -e

# Configuration
CONTAINER_NAME="${CONTAINER_NAME:-graphiti-neo4j-1}"
BACKUP_DIR="${BACKUP_DIR:-/opt/stacks/graphiti/backups/neo4j}"
NEO4J_USERNAME="${NEO4J_USERNAME:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-demodemo}"
LOG_FILE="/var/log/neo4j-restore.log"

# Logging
exec 1> >(tee -a "$LOG_FILE")
exec 2>&1

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# Show usage
usage() {
    echo "Usage: $0 <backup_file> [--force] [--create-backup]"
    echo ""
    echo "Examples:"
    echo "  $0 /opt/stacks/graphiti/backups/neo4j/daily/neo4j_daily_20250124_143000.tar.gz"
    echo "  $0 neo4j_weekly_20250120_030000.tar.gz --force --create-backup"
    echo ""
    echo "Options:"
    echo "  --force           Skip confirmation prompt"
    echo "  --create-backup   Create backup of current database before restore"
    echo ""
    echo "Available backups:"
    find "$BACKUP_DIR" -name "*.tar.gz" -printf "  %TY-%Tm-%Td %TH:%TM  %s bytes  %p\n" 2>/dev/null | sort -r | head -10 || echo "  No backups found in $BACKUP_DIR"
    echo ""
    echo "⚠️  WARNING: This restore requires stopping Neo4j container temporarily"
    echo "              The sync service will be impacted during restoration"
    echo ""
    echo "Environment variables:"
    echo "  CONTAINER_NAME    Neo4j container name (default: graphiti-neo4j-1)"
    echo "  NEO4J_USERNAME    Database username (default: neo4j)"
    echo "  NEO4J_PASSWORD    Database password (default: demodemo)"
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
            log "Available backups:"
            find "$BACKUP_DIR" -name "*.tar.gz" -printf "  %TY-%Tm-%Td %TH:%TM  %p\n" 2>/dev/null | sort -r | head -5
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

    # Verify it's a valid tar.gz file
    if ! tar -tzf "$backup_file" >/dev/null 2>&1; then
        log "ERROR: Backup file is not a valid tar.gz archive: $backup_file"
        exit 1
    fi

    # Check if it contains expected Neo4j files
    if ! tar -tzf "$backup_file" | grep -q "databases"; then
        log "WARNING: Backup may not contain expected Neo4j database files"
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

# Get current database info
get_current_info() {
    log "Getting current database information..."

    local nodes=$(docker exec "$CONTAINER_NAME" cypher-shell -u "$NEO4J_USERNAME" -p "$NEO4J_PASSWORD" --format plain "MATCH (n) RETURN count(n)" 2>/dev/null | tail -1 || echo "0")
    local relationships=$(docker exec "$CONTAINER_NAME" cypher-shell -u "$NEO4J_USERNAME" -p "$NEO4J_PASSWORD" --format plain "MATCH ()-[r]->() RETURN count(r)" 2>/dev/null | tail -1 || echo "0")
    local db_size=$(docker exec "$CONTAINER_NAME" du -sh /data 2>/dev/null | cut -f1 || echo "unknown")

    echo "Current database info:"
    echo "  Nodes: $nodes"
    echo "  Relationships: $relationships"
    echo "  Size: $db_size"

    # Store current stats for comparison
    echo "{
  \"nodes\": $nodes,
  \"relationships\": $relationships,
  \"database_size\": \"$db_size\",
  \"timestamp\": \"$(date -Iseconds)\"
}" > /tmp/pre_restore_stats.json
}

# Create backup of current state before restore
backup_current_state() {
    log "Creating backup of current state before restore..."

    local timestamp=$(date +%Y%m%d_%H%M%S)
    local pre_restore_backup="$BACKUP_DIR/snapshots/pre_restore_${timestamp}.tar.gz"
    local pre_restore_meta="$pre_restore_backup.meta"

    mkdir -p "$(dirname "$pre_restore_backup")"

    # Create compressed backup of current state
    log "Creating compressed backup of current /data directory..."
    docker exec "$CONTAINER_NAME" tar -czf "/tmp/pre_restore_backup.tar.gz" -C /data . || {
        log "ERROR: Failed to create pre-restore backup"
        exit 1
    }

    # Copy backup file from container
    docker cp "$CONTAINER_NAME:/tmp/pre_restore_backup.tar.gz" "$pre_restore_backup" || {
        log "ERROR: Failed to copy pre-restore backup"
        exit 1
    }

    # Create metadata
    cp /tmp/pre_restore_stats.json "$pre_restore_meta"

    # Cleanup
    docker exec "$CONTAINER_NAME" rm -f "/tmp/pre_restore_backup.tar.gz"

    if [[ -f "$pre_restore_backup" ]]; then
        local size=$(du -h "$pre_restore_backup" | cut -f1)
        log "✅ Current state backed up to: $pre_restore_backup ($size)"
        echo "$pre_restore_backup"
    else
        log "❌ Failed to backup current state"
        exit 1
    fi
}

# Stop Neo4j container for restore
stop_neo4j() {
    log "Stopping Neo4j container for restore..."
    log "⚠️  This will temporarily impact the sync service"

    # Stop the container gracefully
    docker stop "$CONTAINER_NAME" || {
        log "ERROR: Failed to stop Neo4j container"
        exit 1
    }

    log "Neo4j container stopped"
}

# Start Neo4j container and wait for readiness
start_neo4j() {
    log "Starting Neo4j container..."

    # Start the container
    docker start "$CONTAINER_NAME" || {
        log "ERROR: Failed to start Neo4j container"
        exit 1
    }

    # Wait for Neo4j to be ready
    local timeout=120
    log "Waiting for Neo4j to be ready..."

    while [[ $timeout -gt 0 ]]; do
        if docker exec "$CONTAINER_NAME" cypher-shell -u "$NEO4J_USERNAME" -p "$NEO4J_PASSWORD" "RETURN 1" >/dev/null 2>&1; then
            break
        fi
        sleep 2
        ((timeout--))
        if [[ $((timeout % 10)) -eq 0 ]]; then
            log "Still waiting for Neo4j... ($timeout seconds remaining)"
        fi
    done

    if ! docker exec "$CONTAINER_NAME" cypher-shell -u "$NEO4J_USERNAME" -p "$NEO4J_PASSWORD" "RETURN 1" >/dev/null 2>&1; then
        log "ERROR: Neo4j failed to start properly within timeout"
        exit 1
    fi

    log "Neo4j container started and ready"
}

# Perform the restore
perform_restore() {
    local backup_file="$1"

    log "Starting restore process..."

    # Copy backup file to container
    log "Copying backup file to container..."
    docker cp "$backup_file" "$CONTAINER_NAME:/tmp/restore_backup.tar.gz"

    # Verify the file was copied
    if ! docker exec "$CONTAINER_NAME" test -f /tmp/restore_backup.tar.gz; then
        log "ERROR: Failed to copy backup file to container"
        exit 1
    fi

    # Clear existing data directory and extract backup
    log "Clearing existing data and extracting backup..."
    docker exec "$CONTAINER_NAME" bash -c "
        cd /data &&
        rm -rf databases logs metrics plugins bin lib certificates import.report &&
        tar -xzf /tmp/restore_backup.tar.gz
    " || {
        log "ERROR: Failed to extract backup"
        exit 1
    }

    # Cleanup temporary file
    docker exec "$CONTAINER_NAME" rm -f /tmp/restore_backup.tar.gz

    log "Database restore completed"
}

# Verify restore
verify_restore() {
    local backup_file="$1"

    log "Verifying restore..."

    # Check if Neo4j is responding
    if ! docker exec "$CONTAINER_NAME" cypher-shell -u "$NEO4J_USERNAME" -p "$NEO4J_PASSWORD" "RETURN 1" >/dev/null 2>&1; then
        log "ERROR: Neo4j is not responding after restore"
        return 1
    fi

    # Get post-restore info
    local nodes=$(docker exec "$CONTAINER_NAME" cypher-shell -u "$NEO4J_USERNAME" -p "$NEO4J_PASSWORD" --format plain "MATCH (n) RETURN count(n)" 2>/dev/null | tail -1 || echo "0")
    local relationships=$(docker exec "$CONTAINER_NAME" cypher-shell -u "$NEO4J_USERNAME" -p "$NEO4J_PASSWORD" --format plain "MATCH ()-[r]->() RETURN count(r)" 2>/dev/null | tail -1 || echo "0")
    local db_size=$(docker exec "$CONTAINER_NAME" du -sh /data 2>/dev/null | cut -f1 || echo "unknown")

    log "Post-restore database info:"
    log "  Nodes: $nodes"
    log "  Relationships: $relationships"
    log "  Size: $db_size"

    # Basic sanity check
    if [[ "$nodes" == "0" ]] && [[ "$relationships" == "0" ]]; then
        log "WARNING: Database appears to be empty after restore"
        return 1
    fi

    # Check backup metadata if available
    local meta_file="${backup_file}.meta"
    if [[ -f "$meta_file" ]]; then
        local expected_nodes=$(grep '"nodes"' "$meta_file" | head -1 | cut -d: -f2 | tr -d ' ,' 2>/dev/null || echo "unknown")
        local expected_relationships=$(grep '"relationships"' "$meta_file" | head -1 | cut -d: -f2 | tr -d ' ,' 2>/dev/null || echo "unknown")

        if [[ "$expected_nodes" != "unknown" ]]; then
            if [[ "$nodes" == "$expected_nodes" ]]; then
                log "✅ Node count matches backup metadata: $nodes"
            else
                log "⚠️  Node count differs from backup metadata - Expected: $expected_nodes, Got: $nodes"
            fi
        fi

        if [[ "$expected_relationships" != "unknown" ]]; then
            if [[ "$relationships" == "$expected_relationships" ]]; then
                log "✅ Relationship count matches backup metadata: $relationships"
            else
                log "⚠️  Relationship count differs from backup metadata - Expected: $expected_relationships, Got: $relationships"
            fi
        fi
    fi

    log "✅ Restore verification completed"
    log "💡 The sync service should automatically reconnect once Neo4j is ready"
    return 0
}

# Main restore function
main() {
    local backup_file="$1"
    local force_flag=""
    local create_backup_flag=""

    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --force)
                force_flag="--force"
                shift
                ;;
            --create-backup)
                create_backup_flag="--create-backup"
                shift
                ;;
            -*)
                log "ERROR: Unknown option: $1"
                usage
                exit 1
                ;;
            *)
                if [[ -z "$backup_file" ]]; then
                    backup_file="$1"
                fi
                shift
                ;;
        esac
    done

    if [[ -z "$backup_file" ]]; then
        usage
        exit 1
    fi

    log "=== Neo4j Simple Restore Started ==="

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
        echo "⚠️  WARNING: Neo4j will be stopped temporarily, affecting the sync service!"
        echo "Backup file: $backup_file"
        echo ""
        read -p "Do you want to continue? (y/N): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log "Restore cancelled by user"
            exit 0
        fi
    fi

    # Create pre-restore backup if requested
    local pre_restore_backup=""
    if [[ "$create_backup_flag" == "--create-backup" ]]; then
        pre_restore_backup=$(backup_current_state)
    fi

    # Perform restore
    log "Starting restore process..."

    stop_neo4j
    perform_restore "$backup_file"
    start_neo4j

    # Clean up temporary files
    rm -f /tmp/pre_restore_stats.json

    if verify_restore "$backup_file"; then
        log "✅ Restore completed successfully!"
        if [[ -n "$pre_restore_backup" ]]; then
            log "Pre-restore backup saved as: $pre_restore_backup"
        fi
        log "🔄 Recommendation: Check sync service status after restore"
    else
        log "❌ Restore verification failed"
        if [[ -n "$pre_restore_backup" ]]; then
            log "You can rollback using: $0 $pre_restore_backup --force"
        fi
        exit 1
    fi

    log "=== Neo4j Simple Restore Completed ==="
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