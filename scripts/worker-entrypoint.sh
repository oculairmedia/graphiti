#!/bin/bash
#
# Worker Service Entrypoint
# Waits for cold boot initialization before starting ingestion
#

set -euo pipefail

# Configuration
READY_MARKER="${READY_MARKER_FILE:-/tmp/graphiti-init-complete}"
MAX_WAIT="${MAX_WAIT_SECONDS:-1800}"  # 30 minutes max
CHECK_INTERVAL=5

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

log "🔧 Worker service starting..."
log "Waiting for system initialization to complete..."
log "Ready marker: $READY_MARKER"

elapsed=0
while [ ! -f "$READY_MARKER" ] && [ $elapsed -lt $MAX_WAIT ]; do
    if [ $((elapsed % 30)) -eq 0 ]; then
        log "Still waiting for initialization... (${elapsed}s / ${MAX_WAIT}s)"
    fi
    sleep $CHECK_INTERVAL
    elapsed=$((elapsed + CHECK_INTERVAL))
done

if [ -f "$READY_MARKER" ]; then
    log "✅ System initialization complete!"
    log "Starting worker..."
    
    # Execute the actual worker command
    exec "$@"
else
    log "❌ Timeout waiting for system initialization"
    log "Ready marker not found: $READY_MARKER"
    exit 1
fi
