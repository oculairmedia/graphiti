#!/bin/bash
#
# Backup Status Tracking Script
# Manages backup status information in JSON format
#

STATUS_FILE="${STATUS_FILE:-/var/log/backup_status.json}"
LOCK_FILE="/var/lock/backup_status.lock"

# Initialize status file if it doesn't exist
init_status_file() {
    if [[ ! -f "$STATUS_FILE" ]]; then
        echo '{"backups": {}}' > "$STATUS_FILE"
    fi
}

# Acquire lock for file operations
acquire_lock() {
    local timeout=10
    local elapsed=0
    
    while [[ -f "$LOCK_FILE" ]] && [[ $elapsed -lt $timeout ]]; do
        sleep 0.5
        ((elapsed++))
    done
    
    if [[ $elapsed -ge $timeout ]]; then
        echo "ERROR: Could not acquire lock for status file" >&2
        return 1
    fi
    
    echo $$ > "$LOCK_FILE"
    return 0
}

# Release lock
release_lock() {
    rm -f "$LOCK_FILE"
}

# Update backup status
update_status() {
    local backup_type="$1"
    local status="$2"
    local backup_file="$3"
    local size_bytes="$4"
    local duration_seconds="$5"
    local error_message="${6:-}"
    
    acquire_lock || return 1
    
    # Create temporary file for atomic update
    local temp_file=$(mktemp)
    
    # Update status using jq or python
    if command -v jq >/dev/null 2>&1; then
        jq --arg type "$backup_type" \
           --arg status "$status" \
           --arg file "$backup_file" \
           --arg size "$size_bytes" \
           --arg duration "$duration_seconds" \
           --arg error "$error_message" \
           --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
           '.backups[$type] = {
                status: $status,
                last_backup_file: $file,
                last_backup_size: ($size | tonumber),
                last_backup_duration: ($duration | tonumber),
                last_backup_timestamp: $timestamp,
                error_message: $error
            }' "$STATUS_FILE" > "$temp_file"
    else
        # Fallback to Python if jq is not available
        python3 -c "
import json
import sys
from datetime import datetime

with open('$STATUS_FILE', 'r') as f:
    data = json.load(f)

if 'backups' not in data:
    data['backups'] = {}

data['backups']['$backup_type'] = {
    'status': '$status',
    'last_backup_file': '$backup_file',
    'last_backup_size': int('$size_bytes') if '$size_bytes' else 0,
    'last_backup_duration': float('$duration_seconds') if '$duration_seconds' else 0,
    'last_backup_timestamp': datetime.utcnow().isoformat() + 'Z',
    'error_message': '$error_message'
}

with open('$temp_file', 'w') as f:
    json.dump(data, f, indent=2)
"
    fi
    
    # Atomically replace the status file
    mv "$temp_file" "$STATUS_FILE"
    
    release_lock
}

# Get backup schedule
get_schedule() {
    cat <<EOF
{
  "daily": {
    "cron": "0 3 * * *",
    "next_run": "$(date -d 'tomorrow 03:00' -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)"
  },
  "weekly": {
    "cron": "0 4 * * 0",
    "next_run": "$(date -d 'next Sunday 04:00' -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)"
  },
  "monthly": {
    "cron": "0 5 1 * *",
    "next_run": "$(date -d 'next month' -u +%Y-%m-01T05:00:00Z 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)"
  },
  "snapshot": {
    "cron": "0 * * * *",
    "next_run": "$(date -d '+1 hour' -u +%Y-%m-%dT%H:00:00Z 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)"
  }
}
EOF
}

# Get storage statistics
get_storage_stats() {
    local backup_dir="${BACKUP_DIR:-/backups/falkordb}"
    
    if [[ -d "$backup_dir" ]]; then
        local total_size=$(du -sb "$backup_dir" 2>/dev/null | cut -f1)
        local daily_size=$(du -sb "$backup_dir/daily" 2>/dev/null | cut -f1 || echo 0)
        local weekly_size=$(du -sb "$backup_dir/weekly" 2>/dev/null | cut -f1 || echo 0)
        local monthly_size=$(du -sb "$backup_dir/monthly" 2>/dev/null | cut -f1 || echo 0)
        local snapshot_size=$(du -sb "$backup_dir/snapshots" 2>/dev/null | cut -f1 || echo 0)
        
        echo "{
            \"total_size\": $total_size,
            \"daily_size\": $daily_size,
            \"weekly_size\": $weekly_size,
            \"monthly_size\": $monthly_size,
            \"snapshot_size\": $snapshot_size
        }"
    else
        echo '{"total_size": 0}'
    fi
}

# Main function
main() {
    local action="${1:-}"
    
    init_status_file
    
    case "$action" in
        "update")
            shift
            update_status "$@"
            ;;
        "get")
            cat "$STATUS_FILE"
            ;;
        "schedule")
            get_schedule
            ;;
        "storage")
            get_storage_stats
            ;;
        *)
            echo "Usage: $0 {update|get|schedule|storage}"
            echo ""
            echo "  update <type> <status> <file> <size> <duration> [error_msg]"
            echo "  get                   - Get current status"
            echo "  schedule              - Get backup schedule"
            echo "  storage               - Get storage statistics"
            exit 1
            ;;
    esac
}

main "$@"