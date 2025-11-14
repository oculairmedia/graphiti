# Automated Cold Boot (Built-In)

## Overview

Cold boot automation is now **built directly into the Docker Compose stack**! No manual scripts needed - just start the stack and it handles everything automatically.

## Quick Start

```bash
# That's it! Just start the stack normally
docker-compose up -d
```

The stack will automatically:
1. ✅ Start databases (Neo4j + FalkorDB)
2. ✅ Clear FalkorDB (removes stale data)
3. ✅ Start sync service
4. ✅ Wait for complete restore (nodes + edges)
5. ✅ Start worker only when ready
6. ✅ Start all other services

## How It Works

### Built-In Init Container

The `graphiti-init` service runs automatically on startup:

```yaml
graphiti-init:
  image: redis:alpine
  restart: "no"  # Runs once, doesn't restart
  command: /bin/sh /scripts/cold-boot-init.sh --no-prompt
  depends_on:
    neo4j: service_healthy
    falkordb: service_healthy
    graphiti-sync-rs: service_started
```

**What it does:**
- Waits for Neo4j and FalkorDB to be healthy
- Clears FalkorDB database
- Waits for sync service to restore from Neo4j
- Monitors both **nodes AND edges** until stable
- Creates marker file when complete
- Exits successfully

### Worker Wait Mechanism

The `graphiti-worker` service waits for init to complete:

```yaml
graphiti-worker:
  entrypoint: ["/scripts/worker-entrypoint.sh"]
  depends_on:
    graphiti-init:
      condition: service_completed_successfully
```

**What it does:**
- Waits for marker file: `/tmp/graphiti-init-complete`
- Timeout: 30 minutes (configurable via `INIT_MAX_WAIT`)
- Only starts processing after FalkorDB is fully restored

## Monitoring Progress

### Check Init Service Status

```bash
# Watch init service logs
docker-compose logs -f graphiti-init

# Check if init completed
docker-compose ps graphiti-init
```

**Expected output:**
```
NAME                 STATUS
graphiti-init        Exited (0)  # Success!
```

### Monitor Restore Progress

```bash
# Use the monitoring script
./scripts/monitor-restore.sh

# Or check manually
docker-compose exec falkordb redis-cli GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)"
docker-compose exec falkordb redis-cli GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)"
```

### Watch Sync Service

```bash
# Live sync progress
docker-compose logs -f graphiti-sync-rs | grep "completed batch"
```

## Configuration

### Environment Variables

Configure cold boot behavior via environment variables:

```bash
# In your .env file or shell
export SYNC_TIMEOUT=1200        # Max time for restore (default: 1200s / 20 min)
export INIT_MAX_WAIT=1800       # Max time worker waits (default: 1800s / 30 min)
export CHECK_INTERVAL=5         # How often to check progress (default: 5s)
```

### For Faster Restores

```bash
# Increase sync parallelism (if you have resources)
export SYNC_PARALLEL_WORKERS=16
export SYNC_BATCH_SIZE=50

# Then restart
docker-compose restart graphiti-sync-rs
```

## Startup Scenarios

### Fresh Start (No Data in FalkorDB)

```bash
docker-compose up -d
```

**Timeline:**
1. Databases start (30s)
2. Init clears FalkorDB (instant - already empty)
3. Sync service restores data (5-15 min)
4. Worker starts when ready
5. All services operational

### Restart with Existing Data

```bash
docker-compose restart
```

**Timeline:**
1. Init detects existing data in FalkorDB
2. **Automatically clears and restores** (no prompt in auto-mode)
3. Ensures data is fresh from Neo4j
4. Worker waits for restore completion

**Note:** This guarantees FalkorDB always has the latest data from Neo4j!

### Cold Boot After `docker-compose down`

```bash
docker-compose down
docker-compose up -d
```

**Timeline:**
1. Fresh start (FalkorDB volume preserved but in-memory data lost)
2. Init clears any stale data
3. Full restore from Neo4j
4. Worker waits for completion

## Troubleshooting

### Init Service Failed

**Check logs:**
```bash
docker-compose logs graphiti-init
```

**Common issues:**
- Neo4j not responding: `docker-compose logs neo4j`
- Sync service not starting: `docker-compose logs graphiti-sync-rs`
- Timeout: Increase `SYNC_TIMEOUT` in `.env`

**Manual retry:**
```bash
# Remove failed init container
docker-compose rm -f graphiti-init

# Restart stack (will re-run init)
docker-compose up -d
```

### Worker Not Starting

**Check init status:**
```bash
docker-compose ps graphiti-init
```

If init didn't complete:
```bash
# Check worker logs
docker-compose logs graphiti-worker

# You'll see: "Waiting for system initialization to complete..."
```

**Solution:** Wait for init to finish or check init logs

### Restore Taking Too Long

**Expected times:**
- Small graphs (<10K nodes): 2-3 minutes
- Medium graphs (10K-50K nodes): 5-10 minutes
- Large graphs (>50K nodes): 10-20 minutes

**If exceeding 20 minutes:**

1. **Check if still syncing:**
   ```bash
   docker-compose logs -f graphiti-sync-rs | grep "batch"
   ```

2. **Increase timeout:**
   ```bash
   echo "SYNC_TIMEOUT=2400" >> .env  # 40 minutes
   docker-compose up -d
   ```

3. **Check resource usage:**
   ```bash
   docker stats
   ```

### Force Re-Initialization

If you need to restart the init process:

```bash
# Stop everything
docker-compose down

# Remove init marker
docker volume rm graphiti_init_ready_marker

# Start fresh
docker-compose up -d
```

## Advantages Over Manual Process

| Feature | Manual Process | Automated (Built-In) |
|---------|---------------|---------------------|
| **Startup** | Run script separately | Just `docker-compose up -d` |
| **Restarts** | Manual re-sync needed | Automatic |
| **Worker Timing** | Manual coordination | Waits automatically |
| **Edge Sync** | Must verify manually | Verified automatically |
| **Errors** | Hard to recover | Auto-retries, clear logs |
| **Production** | Risk of human error | Consistent, reliable |

## Disabling Auto-Initialization

If you want to skip the init process (not recommended):

```yaml
# In docker-compose.override.yml
services:
  graphiti-init:
    restart: "no"
    command: /bin/true  # No-op
  
  graphiti-worker:
    entrypoint: ["python", "-u", "worker/worker.py"]
    depends_on:
      graphiti-init:
        condition: service_started  # Changed from completed_successfully
```

## Migration from Old Setup

If you were using the manual scripts:

### Before (Manual):
```bash
./scripts/automated-cold-boot.sh
```

### After (Built-In):
```bash
docker-compose up -d
# That's it!
```

**No changes needed to:**
- Environment variables
- Configuration files
- Data volumes
- Service ports

**Optional cleanup:**
```bash
# You can remove the init override file if you had one
rm -f docker-compose.init.yml
```

## Best Practices

### Development

```bash
# Normal workflow - just restart
docker-compose restart

# Cold boot when needed
docker-compose down
docker-compose up -d
```

### Production

```bash
# Initial deployment
docker-compose up -d

# Updates (zero-downtime)
docker-compose pull
docker-compose up -d

# Full restart (with init)
docker-compose down && docker-compose up -d
```

### Monitoring

```bash
# Set up monitoring dashboard with these metrics
curl http://localhost:18080/health      # Init/Sync health
curl http://localhost:8003/healthcheck  # API health
curl http://localhost:3000/api/stats    # Graph stats
```

## Performance Tuning

### Fast Machines (High CPU/RAM)

```env
SYNC_PARALLEL_WORKERS=16
SYNC_BATCH_SIZE=50
SYNC_TIMEOUT=600
```

### Slow Machines (Limited Resources)

```env
SYNC_PARALLEL_WORKERS=4
SYNC_BATCH_SIZE=10
SYNC_TIMEOUT=2400
```

### Very Large Graphs (>100K nodes)

```env
SYNC_TIMEOUT=3600  # 1 hour
INIT_MAX_WAIT=3600
SYNC_BATCH_SIZE=100
```

## Health Checks

All services have proper health checks:

```bash
# Check all service health
docker-compose ps

# Healthy services show:
# - neo4j: healthy
# - falkordb: healthy
# - graphiti-sync-rs: Up
# - graphiti-init: Exited (0)
# - graphiti-worker: healthy
```

## Logs Reference

### Successful Init

```
[HH:MM:SS] 🚀 Starting Graphiti Cold Boot Initialization
[HH:MM:SS] Step 1: Waiting for databases to be ready...
[HH:MM:SS] ✅ Neo4j is ready
[HH:MM:SS] ✅ FalkorDB is ready
[HH:MM:SS] Step 2: Checking if restore is needed...
[HH:MM:SS] Step 3: Clearing FalkorDB...
[HH:MM:SS] ✅ FalkorDB cleared successfully
[HH:MM:SS] Step 4: Waiting for sync service...
[HH:MM:SS] ✅ Sync service is ready
[HH:MM:SS] Step 5: Triggering restore...
[HH:MM:SS] ✅ Sync service is healthy and will restore FalkorDB automatically
[HH:MM:SS] Step 6: Waiting for restore to complete...
[HH:MM:SS] This may take several minutes (syncing nodes + edges)...
[HH:MM:SS] Progress: 10000 nodes, 0 edges...
[HH:MM:SS] Progress: 31556 nodes, 0 edges...
[HH:MM:SS] Progress: 31556 nodes, 5000 edges...
[HH:MM:SS] ✅ Restore complete: 31556 nodes, 8807 edges
[HH:MM:SS] Step 7: Verifying restore...
[HH:MM:SS] ✅ Restore verification passed:
[HH:MM:SS]   • Nodes: 31556
[HH:MM:SS]   • Edges: 8807
[HH:MM:SS] Step 8: Marking system as ready...
[HH:MM:SS] ✅ Created ready marker: /tmp/graphiti-init-complete
[HH:MM:SS] ✅ 🎉 Cold Boot Initialization Complete!
[HH:MM:SS] ✅ System is ready for worker ingestion
```

### Worker Waiting

```
[HH:MM:SS] 🔧 Worker service starting...
[HH:MM:SS] Waiting for system initialization to complete...
[HH:MM:SS] Ready marker: /tmp/graphiti-init-complete
[HH:MM:SS] Still waiting for initialization... (30s / 1800s)
[HH:MM:SS] Still waiting for initialization... (60s / 1800s)
...
[HH:MM:SS] ✅ System initialization complete!
[HH:MM:SS] Starting worker...
```

## Summary

The cold boot automation is now **fully integrated** into the Docker Compose stack:

✅ **Zero manual intervention** - Just use `docker-compose up -d`  
✅ **Automatic FalkorDB restoration** - Always fresh from Neo4j  
✅ **Worker coordination** - Waits for complete sync  
✅ **Edge sync verification** - Ensures all relationships are restored  
✅ **Production ready** - Reliable, consistent, repeatable  
✅ **Easy monitoring** - Clear logs and status checks  
✅ **Configurable** - Tune timeouts and performance  

**No more manual cold boot scripts needed!** 🎉
