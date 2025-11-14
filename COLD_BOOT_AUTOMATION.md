# Graphiti Cold Boot Automation

## Problem Statement

Graphiti has critical state dependencies that require careful orchestration during cold boot:

1. **Neo4j** - Primary persistent storage (source of truth)
2. **FalkorDB** - In-memory cache (must be restored from Neo4j)
3. **Sync Service** - Manages Neo4j → FalkorDB synchronization
4. **Worker** - Processes ingestion queue (should only start after FalkorDB is ready)

**Without automation, cold boots fail** because:
- FalkorDB may contain stale/partial data
- Worker starts ingesting before FalkorDB is properly restored
- Manual intervention required to clear and restore FalkorDB

## Solutions Provided

### Option 1: Automated Cold Boot Script (Recommended)

**Best for:** Quick restarts, development, manual operations

```bash
# Simple one-command cold boot
./scripts/automated-cold-boot.sh
```

**What it does:**
1. Starts databases (Neo4j + FalkorDB)
2. Waits for health checks
3. Clears FalkorDB
4. Starts sync service
5. Waits for restore completion
6. Starts remaining services (API, Worker, Frontend)
7. Verifies all services are healthy

**Pros:**
- Simple to use
- Transparent progress logging
- No docker-compose modifications needed
- Easy to customize

**Cons:**
- Requires manual execution
- Not suitable for auto-restart scenarios

### Option 2: Docker Compose Init Container

**Best for:** Production deployments, automated restarts

```bash
# Use the init container setup
docker-compose -f docker-compose.yml -f docker-compose.init.yml up
```

**What it does:**
1. Adds `graphiti-init` service that runs cold boot initialization
2. Modifies worker service to wait for initialization marker
3. All services start in proper order automatically

**Pros:**
- Fully automated
- Works with `docker-compose restart`
- Production-ready
- Handles container crashes gracefully

**Cons:**
- Requires docker-compose file modification
- More complex to debug

### Option 3: Manual Process (Current)

**For emergencies or troubleshooting:**

```bash
# 1. Start databases
docker-compose up -d neo4j falkordb

# 2. Wait for health
docker-compose ps

# 3. Clear FalkorDB
docker-compose exec falkordb redis-cli GRAPH.DELETE graphiti_migration

# 4. Start sync service
docker-compose up -d graphiti-sync-rs

# 5. Monitor restore
watch 'docker-compose exec falkordb redis-cli GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)"'

# 6. Start remaining services
docker-compose up -d
```

## Architecture

### Cold Boot Sequence

```
┌─────────────┐
│   Neo4j     │◄─── Persistent Storage (Source of Truth)
└─────────────┘
       │
       │ 1. Sync Service reads
       ▼
┌─────────────┐
│ Sync Service│
└─────────────┘
       │
       │ 2. Writes to
       ▼
┌─────────────┐
│  FalkorDB   │◄─── In-Memory Cache (Restored on boot)
└─────────────┘
       │
       │ 3. Worker reads from
       ▼
┌─────────────┐
│   Worker    │◄─── Should only start AFTER restore
└─────────────┘
```

### State Markers

The init system uses a shared volume with a marker file:

```
/tmp/graphiti-init-complete  ← Created when restore is complete
```

- **Init service:** Creates marker after successful restore
- **Worker service:** Waits for marker before starting ingestion

### Restore Verification

The restore is considered complete when **ALL** of the following conditions are met:

1. **Node count > 0** - Entities, Episodic nodes, Community nodes all synced
2. **Edge count > 0** - All relationships synced from Neo4j
3. **Both counts stable** - No changes for 3 consecutive checks (15 seconds)
4. **Sync service healthy** - Reports successful sync completion

**Important:** The script waits for **both nodes AND edges** to complete syncing. Edge synchronization typically happens after node sync and can take significant time depending on the number of relationships in your graph.

## Scripts Reference

### `scripts/automated-cold-boot.sh`

Main automation script for cold boot sequence.

**Usage:**
```bash
./scripts/automated-cold-boot.sh
```

**Environment Variables:**
- None required (uses docker-compose defaults)

**Exit Codes:**
- `0` - Success
- `1` - Database startup failure
- `2` - Restore timeout

### `scripts/cold-boot-init.sh`

Detailed initialization script with interactive prompts.

**Usage:**
```bash
# Interactive mode
./scripts/cold-boot-init.sh

# Automated mode (no prompts)
./scripts/cold-boot-init.sh --no-prompt
```

**Environment Variables:**
- `NEO4J_URI` - Neo4j connection string
- `FALKORDB_HOST` - FalkorDB hostname
- `FALKORDB_PORT` - FalkorDB port
- `SYNC_SERVICE_URL` - Sync service health endpoint
- `SYNC_TIMEOUT` - Maximum time to wait for restore (default: 600s / 10 min)
  - **Note:** For large graphs with many edges, you may need to increase this to 1200-1800s (20-30 minutes)

### `scripts/worker-entrypoint.sh`

Worker entrypoint that waits for initialization.

**Usage:**
```bash
# Used automatically when docker-compose.init.yml is active
# Can also be used standalone:
READY_MARKER_FILE=/tmp/init ./scripts/worker-entrypoint.sh python worker.py
```

**Environment Variables:**
- `READY_MARKER_FILE` - Path to ready marker (default: `/tmp/graphiti-init-complete`)
- `MAX_WAIT_SECONDS` - Maximum wait time (default: 1800s / 30 min)

## Monitoring

### Check Restore Progress

```bash
# Watch FalkorDB node AND edge counts
watch 'echo "=== FalkorDB Restore Progress ==="; \
echo -n "Nodes: "; \
docker-compose exec -T falkordb redis-cli GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)" 2>/dev/null | grep -oP "\d+" | head -1; \
echo -n "Edges: "; \
docker-compose exec -T falkordb redis-cli GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" 2>/dev/null | grep -oP "\d+" | head -1'

# Check sync service health
curl http://localhost:18080/health | jq .

# Check sync service metrics  
curl http://localhost:18081/metrics

# Watch sync service logs (live progress)
docker-compose logs -f --tail=50 graphiti-sync-rs
```

### Service Health

```bash
# All services status
docker-compose ps

# Individual service logs
docker-compose logs -f graphiti-sync-rs
docker-compose logs -f graphiti-worker
```

## Troubleshooting

### Restore Takes Too Long

**Symptoms:** Restore timeout after 10 minutes

**Root Cause:** Edge synchronization can be slow for graphs with many relationships

**Solutions:**
1. **Increase timeout for edge sync:**
   ```bash
   export SYNC_TIMEOUT=1200  # 20 minutes
   ./scripts/automated-cold-boot.sh
   ```

2. **Monitor progress to see if it's still syncing:**
   ```bash
   # Watch in real-time
   docker-compose logs -f graphiti-sync-rs | grep "completed batch"
   ```

3. **Check what's syncing:**
   ```bash
   # Nodes done, edges in progress?
   docker-compose exec falkordb redis-cli GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)"
   docker-compose exec falkordb redis-cli GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)"
   ```

4. **Verify source database:**
   - Neo4j connectivity: `docker-compose logs neo4j`
   - Sync service logs: `docker-compose logs graphiti-sync-rs`
   - Neo4j browser: http://localhost:7474

### Worker Starts Before Restore

**Symptoms:** Worker processes queue but data not in FalkorDB

**Solutions:**
1. Use `docker-compose.init.yml` for proper orchestration
2. Stop worker manually: `docker-compose stop graphiti-worker`
3. Wait for restore, then restart: `docker-compose start graphiti-worker`

### FalkorDB Not Clearing

**Symptoms:** Old data persists after clear

**Solutions:**
```bash
# Manual clear with verification
docker-compose exec falkordb redis-cli GRAPH.DELETE graphiti_migration
docker-compose exec falkordb redis-cli GRAPH.LIST
```

### Sync Service Not Responding

**Symptoms:** Sync service health check fails

**Solutions:**
```bash
# Check sync service is running
docker-compose ps graphiti-sync-rs

# Restart sync service
docker-compose restart graphiti-sync-rs

# Check logs for errors
docker-compose logs -f graphiti-sync-rs
```

## Configuration Reference

### Docker Compose Environment Variables

```bash
# Neo4j Configuration
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=graphiti123

# FalkorDB Configuration
FALKORDB_HOST=falkordb
FALKORDB_PORT=6379
FALKORDB_DATABASE=graphiti_migration

# Sync Service Configuration
SYNC_HEALTH_PORT=18080
SYNC_METRICS_PORT=18081
SYNC_BATCH_SIZE=25
SYNC_PARALLEL_WORKERS=8

# Init Configuration
SYNC_TIMEOUT=600          # Restore timeout (seconds)
INIT_MAX_WAIT=1800       # Worker wait timeout (seconds)
```

### Sync Service Environment Variables

See `docker-compose.yml` lines 188-219 for complete sync service configuration.

Key settings:
- `SYNC_SYNC_BATCH_SIZE` - Nodes per batch (default: 25)
- `SYNC_PARALLEL_WORKERS` - Parallel workers (default: 8)
- `SYNC_FALKOR_AUTORESTORE_THRESHOLD` - Auto-restore trigger (default: 0.80)

## Best Practices

### Development Workflow

```bash
# Quick restart during development
docker-compose restart

# Full cold boot after code changes
docker-compose down
./scripts/automated-cold-boot.sh
```

### Production Deployment

```bash
# Initial deployment
docker-compose -f docker-compose.yml -f docker-compose.init.yml up -d

# Updates (preserves Neo4j data)
docker-compose -f docker-compose.yml -f docker-compose.init.yml pull
docker-compose -f docker-compose.yml -f docker-compose.init.yml up -d
```

### Backup Before Cold Boot

```bash
# Backup Neo4j (persistent)
docker-compose exec neo4j neo4j-admin database dump neo4j

# Backup FalkorDB (optional, will be restored anyway)
docker-compose exec falkordb redis-cli BGSAVE
```

## Migration from Manual Process

If you're currently doing cold boots manually:

1. **Test the automated script:**
   ```bash
   docker-compose down
   ./scripts/automated-cold-boot.sh
   ```

2. **Verify services are healthy:**
   ```bash
   docker-compose ps
   curl http://localhost:8003/healthcheck
   ```

3. **Switch to init container for production:**
   ```bash
   # Update your startup command
   docker-compose -f docker-compose.yml -f docker-compose.init.yml up -d
   ```

## Performance Tuning

### Faster Restores

```bash
# Increase parallel workers (if you have CPU/memory)
export SYNC_PARALLEL_WORKERS=16

# Increase batch size (more memory, faster sync)
export SYNC_BATCH_SIZE=50
```

### Resource Constraints

```bash
# Reduce parallel workers on smaller systems
export SYNC_PARALLEL_WORKERS=4

# Reduce batch size
export SYNC_BATCH_SIZE=10
```

## Future Improvements

Potential enhancements to consider:

1. **Health-based restore detection** - Use sync service metrics instead of node count polling
2. **Restore checkpoint/resume** - Handle partial restore failures gracefully
3. **Parallel database startup** - Start services in parallel where safe
4. **Web UI for cold boot** - Dashboard showing restore progress
5. **Backup/restore integration** - Option to restore from backup instead of live Neo4j

## Support

If you encounter issues:

1. Check logs: `docker-compose logs`
2. Verify configuration: `docker-compose config`
3. Test services individually: `docker-compose up <service>`
4. Review this document's troubleshooting section
5. Open an issue with logs and environment details
