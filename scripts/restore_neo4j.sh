#!/bin/bash
#
# Neo4j Restore Script
# Restore from neo4j-admin dump files with verification
# Replaces the broken FalkorDB restore system
#

set -e

# Configuration
CONTAINER_NAME="${CONTAINER_NAME:-graphiti-neo4j-1}"
BACKUP_DIR="${BACKUP_DIR:-/opt/stacks/graphiti/backups/neo4j}"
NEO4J_DATABASE="${NEO4J_DATABASE:-neo4j}"
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
    echo "  $0 /opt/stacks/graphiti/backups/neo4j/daily/neo4j_daily_20250124_143000.dump"
    echo "  $0 neo4j_weekly_20250120_030000.dump --force --create-backup"
    echo ""
    echo "Options:"
    echo "  --force           Skip confirmation prompt"
    echo "  --create-backup   Create backup of current database before restore"
    echo ""
    echo "Available backups:"
    find "$BACKUP_DIR" -name "*.dump" -printf "  %TY-%Tm-%Td %TH:%TM  %s bytes  %p\n" 2>/dev/null | sort -r | head -10 || echo "  No backups found in $BACKUP_DIR"
    echo ""
    echo "Environment variables:"
    echo "  CONTAINER_NAME    Neo4j container name (default: graphiti-neo4j-1)"
    echo "  NEO4J_DATABASE    Database name (default: neo4j)"
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
            find "$BACKUP_DIR" -name "*.dump" -printf "  %TY-%Tm-%Td %TH:%TM  %p\n" 2>/dev/null | sort -r | head -5
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

    # Verify it's likely a Neo4j dump file
    if ! file "$backup_file" | grep -q "data\|archive\|gzip"; then
        log "WARNING: File may not be a valid Neo4j dump file: $backup_file"
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
    echo "  Database: $NEO4J_DATABASE"
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
    local pre_restore_backup="$BACKUP_DIR/snapshots/pre_restore_${timestamp}.dump"
    local pre_restore_meta="$pre_restore_backup.meta"

    mkdir -p "$(dirname "$pre_restore_backup")"

    # Create dump of current database
    log "Creating dump of current database..."
    docker exec "$CONTAINER_NAME" neo4j-admin database dump --to-path=/tmp --verbose "$NEO4J_DATABASE" || {
        log "ERROR: Failed to create pre-restore backup"
        exit 1
    }

    # Copy dump file from container
    docker cp "$CONTAINER_NAME:/tmp/$NEO4J_DATABASE.dump" "$pre_restore_backup" || {
        log "ERROR: Failed to copy pre-restore backup"
        exit 1
    }

    # Create metadata
    cp /tmp/pre_restore_stats.json "$pre_restore_meta"

    # Cleanup
    docker exec "$CONTAINER_NAME" rm -f "/tmp/$NEO4J_DATABASE.dump"

    if [[ -f "$pre_restore_backup" ]]; then
        local size=$(du -h "$pre_restore_backup" | cut -f1)
        log "✅ Current state backed up to: $pre_restore_backup ($size)"
        echo "$pre_restore_backup"
    else
        log "❌ Failed to backup current state"
        exit 1
    fi
}

# Stop database and container services
stop_database() {
    log "Stopping Neo4j database..."

    # Try graceful shutdown first
    docker exec "$CONTAINER_NAME" neo4j stop || {
        log "Graceful shutdown failed, stopping container..."
        docker stop "$CONTAINER_NAME"
    }

    # Wait for container to stop
    local timeout=60
    while docker ps | grep -q "$CONTAINER_NAME" && [[ $timeout -gt 0 ]]; do
        sleep 2
        ((timeout--))
    done

    if docker ps | grep -q "$CONTAINER_NAME"; then
        log "WARNING: Container did not stop gracefully, forcing stop..."
        docker kill "$CONTAINER_NAME"
        sleep 5
    fi

    log "Neo4j database stopped"
}

# Start database and wait for readiness
start_database() {
    log "Starting Neo4j database..."

    docker start "$CONTAINER_NAME"

    # Wait for container to start
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

    log "Neo4j database started and ready"
}

# Perform the restore
perform_restore() {
    local backup_file="$1"

    log "Starting restore process..."

    # Copy backup file to container
    log "Copying backup file to container..."
    docker cp "$backup_file" "$CONTAINER_NAME:/tmp/restore.dump"

    # Verify the file was copied
    if ! docker exec "$CONTAINER_NAME" test -f /tmp/restore.dump; then
        log "ERROR: Failed to copy backup file to container"
        exit 1
    fi

    # Load the dump using neo4j-admin
    log "Loading database from dump file..."
    docker exec "$CONTAINER_NAME" neo4j-admin database load --from-path=/tmp --overwrite-destination=true "$NEO4J_DATABASE" || {
        log "ERROR: neo4j-admin load failed"
        exit 1
    }

    # Cleanup temporary file
    docker exec "$CONTAINER_NAME" rm -f /tmp/restore.dump

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
        local expected_nodes=$(grep '"nodes"' "$meta_file" | cut -d: -f2 | tr -d ' ,' 2>/dev/null || echo "unknown")
        local expected_relationships=$(grep '"relationships"' "$meta_file" | cut -d: -f2 | tr -d ' ,' 2>/dev/null || echo "unknown")

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

    log "=== Neo4j Restore Started ==="

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
        echo "Database: $NEO4J_DATABASE"
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

    stop_database
    perform_restore "$backup_file"
    start_database

    # Clean up temporary files
    rm -f /tmp/pre_restore_stats.json

    if verify_restore "$backup_file"; then
        log "✅ Restore completed successfully!"
        if [[ -n "$pre_restore_backup" ]]; then
            log "Pre-restore backup saved as: $pre_restore_backup"
        fi
    else
        log "❌ Restore verification failed"
        if [[ -n "$pre_restore_backup" ]]; then
            log "You can rollback using: $0 $pre_restore_backup --force"
        fi
        exit 1
    fi

    log "=== Neo4j Restore Completed ==="
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