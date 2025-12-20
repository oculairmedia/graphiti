# Graphiti Stack Timeout Analysis

## Critical Finding: Why `docker-compose up -d graph-visualizer-rust` Fails

### The Problem
When running `docker-compose up -d <service>`, Docker Compose checks ALL dependencies in the `depends_on` chain. If ANY dependency container doesn't exist or exited, Docker Compose will **recreate** it - even if it already ran successfully.

### The Dependency Chain
```
graph-visualizer-rust
  ├─ depends_on: graphiti-init (condition: service_completed_successfully)
  │    ├─ depends_on: neo4j (condition: service_healthy)
  │    ├─ depends_on: falkordb (condition: service_healthy)  ← IN-MEMORY ONLY
  │    └─ depends_on: graphiti-sync-rs (condition: service_started)
  │         ├─ depends_on: neo4j (condition: service_healthy)
  │         └─ depends_on: falkordb (condition: service_healthy)
  ├─ depends_on: falkordb (condition: service_healthy)
  └─ depends_on: graphiti-centrality-rs (condition: service_healthy)
```

### What Happens During `docker-compose up -d graph-visualizer-rust`

1. **Docker Compose checks**: Is `graphiti-init` present and completed successfully?
2. **If graphiti-init container was removed** (common after cleanup): Docker recreates it
3. **Recreating graphiti-init triggers its depends_on**: neo4j, falkordb, graphiti-sync-rs
4. **Since graphiti-init is being recreated**, Docker stops and recreates falkordb and neo4j
5. **FalkorDB has NO persistence** → All 121K edges lost
6. **Sync must re-run** → 2-3 hours to restore

### The Root Cause
**`graphiti-init` has `restart: no`** (line 449 in docker-compose.yml)

This means:
- After successful completion, the container exits and stays in "Exited (0)" state
- If the container is manually removed (e.g., during cleanup), it no longer exists
- Next `docker-compose up` will recreate it
- Recreating triggers the entire dependency chain

---

## All Timeout Settings in the Stack

### Service Healthchecks

#### 1. Neo4j (lines 29-36)
```yaml
healthcheck:
  interval: 1s           # Check every 1 second
  timeout: 10s           # Each check has 10s to respond
  retries: 10            # 10 failed checks before unhealthy
  start_period: 3s       # Grace period on startup
```
**Total time to healthy**: ~13 seconds (3s grace + 10 checks @ 1s)
**Total time to unhealthy after failure**: ~10 seconds

#### 2. FalkorDB (lines 58-65)
```yaml
healthcheck:
  interval: 10s          # Check every 10 seconds
  timeout: 5s            # Each check has 5s to respond
  retries: 3             # 3 failed checks before unhealthy
```
**Total time to healthy**: ~30 seconds (3 checks @ 10s)
**Total time to unhealthy after failure**: ~30 seconds

#### 3. graph-visualizer-rust (lines 110-119) ⚠️ CRITICAL
```yaml
healthcheck:
  interval: 15s          # Check every 15 seconds
  timeout: 5s            # Each check has 5s to respond
  retries: 100           # 100 failed checks before unhealthy
  start_period: 3600s    # 1 HOUR grace period
```
**Total time allowed**: Up to 85 minutes (1 hour + 100 × 15s)
**Why so long**: Must load ALL edges from FalkorDB into memory (121K+ edges)

#### 4. graphiti-centrality-rs (lines 141-149)
```yaml
healthcheck:
  interval: 30s          # Check every 30 seconds
  timeout: 10s           # Each check has 10s to respond
  retries: 3             # 3 failed checks before unhealthy
```
**Total time to healthy**: ~90 seconds

#### 5. graphiti-search-rs (lines 176-183)
```yaml
healthcheck:
  interval: 30s          # Same as centrality
  timeout: 10s
  retries: 3
```
**Total time to healthy**: ~90 seconds

#### 6. graph API (lines 326-335)
```yaml
healthcheck:
  interval: 10s          # Check every 10 seconds
  timeout: 5s            # Each check has 5s to respond
  retries: 3             # 3 failed checks before unhealthy
```
**Total time to healthy**: ~30 seconds

#### 7. graphiti-queued (lines 505-514)
```yaml
healthcheck:
  interval: 10s          # Check every 10 seconds
  timeout: 5s            # Each check has 5s to respond
  retries: 3             # 3 failed checks before unhealthy
  start_period: 15s      # 15s grace period
```
**Total time to healthy**: ~45 seconds

#### 8. graphiti-worker (lines 595-605)
```yaml
healthcheck:
  interval: 30s          # Check every 30 seconds
  timeout: 10s           # Each check has 10s to respond
  retries: 3             # 3 failed checks before unhealthy
  start_period: 30s      # 30s grace period
```
**Total time to healthy**: ~120 seconds

#### 9. frontend (lines 631-640)
```yaml
healthcheck:
  interval: 30s          # Check every 30 seconds
  timeout: 10s           # Each check has 10s to respond
  retries: 3             # 3 failed checks before unhealthy
  start_period: 10s      # 10s grace period
```
**Total time to healthy**: ~100 seconds

#### 10. nginx (lines 670-679)
```yaml
healthcheck:
  interval: 30s          # Same as frontend
  timeout: 10s
  retries: 3
  start_period: 10s
```
**Total time to healthy**: ~100 seconds

---

## cold-boot-init.sh Timeouts

### Service Wait Timeouts (wait_for_service function)
```bash
# Default timeout: 60 seconds (can be overridden)
wait_for_service "Neo4j" check_neo4j 120      # 120s timeout
wait_for_service "FalkorDB" check_falkordb 60 # 60s timeout
wait_for_service "Sync Service" "curl..." 60  # 60s timeout
```

### Sync Completion Timeout
```bash
SYNC_TIMEOUT="${SYNC_TIMEOUT:-0}"  # 0 = NO TIMEOUT (wait forever)
```

**Critical**: The init script waits **indefinitely** for sync to complete by default.

### Sync Stability Detection
```bash
CHECK_INTERVAL=5  # Check every 5 seconds
stable_count=3    # Must be stable for 3 checks (15 seconds total)
```

**How it works**:
1. Counts nodes AND edges every 5 seconds
2. If both counts unchanged for 3 consecutive checks (15s), sync is "complete"
3. This prevents premature completion detection

---

## Potential Issues & Fixes

### Issue 1: graphiti-init Container Removal
**Problem**: After cleanup or manual removal, `docker-compose up` recreates the entire chain

**Solution Options**:

#### Option A: Never remove graphiti-init container
```bash
# Safe stack operations
docker-compose ps                    # Check status only
docker restart <container-name>      # Restart individual containers
docker stop/start <container-name>   # Stop/start without removing
```

#### Option B: Change graphiti-init to stay running
```yaml
graphiti-init:
  restart: unless-stopped  # Instead of "no"
  command:
    - |
      # ... existing init logic ...
      # After completion, instead of exiting:
      log_success "Initialization complete, staying alive..."
      tail -f /dev/null  # Keep container running
```

**Trade-off**: Uses minimal resources but container stays in `docker ps`

#### Option C: Remove graphiti-init dependency from visualizer
**Most dangerous** - could start visualizer before sync completes

### Issue 2: Visualizer Healthcheck May Be Too Long
**Current**: Up to 85 minutes (3600s + 100 × 15s)

**Observation**: With 121K edges, visualizer loads data in ~2-3 minutes after sync completes

**Recommendation**: Current timeout is safe but generous. Could reduce to:
```yaml
start_period: 600s   # 10 minutes
retries: 20          # 20 × 15s = 5 more minutes
# Total: 15 minutes
```

### Issue 3: No Timeout on Sync Completion
**Current**: `SYNC_TIMEOUT=0` means wait forever

**Risk**: If sync hangs, init never completes, entire stack waits forever

**Recommendation**: Set reasonable timeout with escape hatch:
```yaml
environment:
  - SYNC_TIMEOUT=${SYNC_TIMEOUT:-10800}  # 3 hours default
```

Or add monitoring/alerting if sync exceeds expected time.

---

## Safe Operations Reference

### ✅ SAFE: Won't trigger dependency restarts
```bash
# View logs
docker-compose logs <service>
docker logs <container-name>

# Restart individual containers (use container name, not service name)
docker restart graphiti-graph-visualizer-rust-1
docker restart graphiti-frontend-1
docker restart graphiti-nginx-1

# Stop/start containers
docker stop <container-name>
docker start <container-name>

# Check status
docker-compose ps
docker ps -a
```

### ⚠️ DANGEROUS: Will trigger dependency cascades
```bash
# These will recreate services AND their dependencies
docker-compose up -d graph-visualizer-rust   # Recreates graphiti-init → falkordb
docker-compose restart graph-visualizer-rust  # Same issue
docker-compose up -d frontend                 # Recreates visualizer → init → falkordb

# These are safe ONLY if no dependencies
docker-compose restart falkordb    # No dependencies, but loses all data!
docker-compose restart neo4j       # Safe, data persisted
```

### 🚨 NEVER DO THIS
```bash
# Will lose ALL FalkorDB data (no persistence)
docker-compose restart falkordb
docker-compose up -d falkordb
docker restart graphiti-falkordb-1  # Only safe way to restart falkordb
```

---

## Recommended Workflow for Visualizer Issues

### If visualizer is stuck/broken:

1. **Check if it's actually broken**:
   ```bash
   docker logs --tail=50 graphiti-graph-visualizer-rust-1
   curl http://localhost:3000/health
   ```

2. **Restart container only** (safe):
   ```bash
   docker restart graphiti-graph-visualizer-rust-1
   ```

3. **If container doesn't exist**, recreate manually:
   ```bash
   # Extract env vars from compose
   docker-compose config | grep -A 30 graph-visualizer-rust
   
   # Use docker run with all settings
   docker run -d \
     --name graphiti-graph-visualizer-rust-1 \
     --network graphiti_graphiti_network \
     -p 3000:3000 \
     -v graphiti_visualizer_duckdb:/app/data \
     -e FALKORDB_HOST=falkordb \
     # ... all other env vars ...
     graphiti-rust-visualizer:incremental-updates
   ```

4. **If graphiti-init is missing**, DON'T recreate it - verify sync is complete first:
   ```bash
   # Check if sync is actually complete
   redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration \
     "MATCH ()-[r]->() RETURN count(r)" --csv
   
   # Should show 121,139 edges
   ```

---

## Summary of Findings

### Critical Issues
1. **graphiti-init has `restart: no`** → Container removal triggers full recreation chain
2. **FalkorDB has NO persistence** → Any restart = 2-3 hour data loss
3. **depend_on chains are recursive** → Updating one service can restart entire stack

### Timeouts Are Adequate
- Neo4j: 13s to healthy ✅
- FalkorDB: 30s to healthy ✅
- Visualizer: 85 minutes max (appropriate for 121K edges) ✅
- Init script: Waits indefinitely for sync (by design) ✅

### Root Cause of Today's Issue
Using `docker-compose up -d graph-visualizer-rust` when graphiti-init container was missing caused Docker Compose to recreate the entire dependency tree, including FalkorDB, losing all synced data.

### Prevention
**Never use `docker-compose up/restart` on services with dependencies.**
**Always use `docker restart <container-name>` instead.**
