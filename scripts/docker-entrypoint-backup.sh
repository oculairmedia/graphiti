#!/bin/bash
#
# Docker entrypoint for FalkorDB backup service
# Initializes backup environment and starts cron daemon
#

set -e

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ENTRYPOINT: $1"
}

# Environment variable defaults
export CONTAINER_NAME="${FALKORDB_CONTAINER_NAME:-falkordb}"
export BACKUP_DIR="${BACKUP_DIR:-/backups/falkordb}"
export BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
export BACKUP_RETENTION_WEEKLY="${BACKUP_RETENTION_WEEKLY:-4}"
export BACKUP_RETENTION_MONTHLY="${BACKUP_RETENTION_MONTHLY:-3}"
export BACKUP_WEBHOOK_URL="${BACKUP_WEBHOOK_URL:-}"

# Write environment variables to a file that can be sourced by cron jobs
cat > /etc/environment <<EOF
export CONTAINER_NAME=$CONTAINER_NAME
export BACKUP_DIR=$BACKUP_DIR
export BACKUP_RETENTION_DAYS=$BACKUP_RETENTION_DAYS
export BACKUP_RETENTION_WEEKLY=$BACKUP_RETENTION_WEEKLY
export BACKUP_RETENTION_MONTHLY=$BACKUP_RETENTION_MONTHLY
export BACKUP_WEBHOOK_URL=$BACKUP_WEBHOOK_URL
export STATUS_FILE=$STATUS_FILE
EOF

# Ensure backup directories exist
log "Creating backup directories..."
mkdir -p "${BACKUP_DIR}"/{daily,weekly,monthly,snapshots}

# Ensure log files exist and are writable
touch /var/log/falkordb-backup.log /var/log/falkordb-backup-cron.log
chmod 666 /var/log/falkordb-backup.log /var/log/falkordb-backup-cron.log

# Display configuration
log "=== FalkorDB Backup Service Configuration ==="
log "Container Name: ${CONTAINER_NAME}"
log "Backup Directory: ${BACKUP_DIR}"
log "Retention - Daily: ${BACKUP_RETENTION_DAYS} days"
log "Retention - Weekly: ${BACKUP_RETENTION_WEEKLY} weeks"
log "Retention - Monthly: ${BACKUP_RETENTION_MONTHLY} months"
log "Webhook URL: ${BACKUP_WEBHOOK_URL:-Not configured}"
log "============================================="

# Display cron schedule
log "Backup Schedule:"
log "  Daily:    3:00 AM UTC"
log "  Weekly:   4:00 AM UTC (Sunday)"
log "  Monthly:  5:00 AM UTC (1st of month)"
log "  Snapshot: Every hour"

# Test connectivity to FalkorDB container
log "Testing connection to FalkorDB container..."
max_retries=30
retry_count=0
while [ $retry_count -lt $max_retries ]; do
    if docker exec "${CONTAINER_NAME}" redis-cli ping >/dev/null 2>&1; then
        log "✅ Successfully connected to FalkorDB container"
        break
    else
        log "Waiting for FalkorDB container to be ready... ($((retry_count+1))/$max_retries)"
        sleep 2
        ((retry_count++))
    fi
done

if [ $retry_count -eq $max_retries ]; then
    log "⚠️  Warning: Could not connect to FalkorDB container. Backups will fail until container is available."
fi

# Initialize status file for dashboard
export STATUS_FILE="/var/log/backup_status.json"
echo '{"backups": {}}' > "$STATUS_FILE"

# Start monitoring dashboard in background
if [ "${ENABLE_DASHBOARD:-true}" = "true" ]; then
    log "Starting monitoring dashboard on port 8080..."
    python3 /scripts/backup_dashboard.py &
    DASHBOARD_PID=$!
    log "Dashboard started with PID: $DASHBOARD_PID"
fi

# Run initial backup on startup (snapshot)
if [ "${RUN_INITIAL_BACKUP:-true}" = "true" ]; then
    log "Running initial snapshot backup..."
    /scripts/backup_falkordb.sh snapshot || log "Initial backup failed (this is normal if FalkorDB is still starting)"
fi

# Trap to ensure dashboard stops when container stops
trap "kill $DASHBOARD_PID 2>/dev/null" EXIT

# Start cron daemon in foreground
log "Starting cron daemon..."
exec "$@"