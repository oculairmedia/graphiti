# Quick Start: Automated Cold Boot

> 🎉 **NEW:** Cold boot automation is now **built into the Docker Compose stack!**  
> See [AUTOMATED_COLD_BOOT.md](AUTOMATED_COLD_BOOT.md) for the new built-in method.

## ⚡ TL;DR - It's Now Built-In!

```bash
# Just start the stack - that's it!
docker-compose up -d
```

**Cold boot automation is now built into the stack!** No manual scripts needed anymore.

## Alternative: Manual Script (Optional)

If you prefer to run the cold boot separately:

```bash
./scripts/automated-cold-boot.sh
```

## What It Does

1. ✅ Starts Neo4j and FalkorDB
2. ✅ Clears FalkorDB (removes stale data)
3. ✅ Starts sync service
4. ✅ Waits for Neo4j → FalkorDB restore (auto-detects completion)
5. ✅ Starts all remaining services
6. ✅ Verifies everything is healthy

## Expected Output

```
╔════════════════════════════════════════════════════════════╗
║     Graphiti Automated Cold Boot Initialization           ║
╚════════════════════════════════════════════════════════════╝

[HH:MM:SS] Step 1: Starting core databases (Neo4j + FalkorDB)...
[HH:MM:SS] Waiting for databases to be healthy...
[HH:MM:SS] ✅ Databases are healthy
[HH:MM:SS] Step 2: Clearing FalkorDB...
[HH:MM:SS] ✅ FalkorDB cleared
[HH:MM:SS] Step 3: Starting sync service...
[HH:MM:SS] ✅ Sync service is healthy
[HH:MM:SS] Step 4: Waiting for Neo4j -> FalkorDB restore...
[HH:MM:SS] This may take several minutes (syncing nodes + edges)...
[HH:MM:SS] Progress: 5000 nodes, 0 edges...
[HH:MM:SS] Progress: 15000 nodes, 0 edges...
[HH:MM:SS] Progress: 31556 nodes, 0 edges...
[HH:MM:SS] Progress: 31556 nodes, 2500 edges...
[HH:MM:SS] Progress: 31556 nodes, 5000 edges...
[HH:MM:SS] Progress: 31556 nodes, 8807 edges...
[HH:MM:SS] ✅ Restore complete: 31556 nodes, 8807 edges
[HH:MM:SS] Step 5: Starting remaining services...
[HH:MM:SS] ✅ graph is running
[HH:MM:SS] ✅ graphiti-queued is running
[HH:MM:SS] ✅ graphiti-worker is running
[HH:MM:SS] ✅ graph-visualizer-rust is running

╔════════════════════════════════════════════════════════════╗
║            ✅ Cold Boot Completed Successfully            ║
╚════════════════════════════════════════════════════════════╝

FalkorDB state:
  • Nodes: 31556
  • Edges: 8807
API: http://localhost:8003
Frontend: http://localhost:8084
Graph Visualizer: http://localhost:3000
```

## Typical Timing

The restore process syncs **both nodes AND edges** from Neo4j to FalkorDB:

- **Small dataset (<10K nodes, <5K edges):** 2-3 minutes
- **Medium dataset (10K-50K nodes, 5K-20K edges):** 5-10 minutes  
- **Large dataset (>50K nodes, >20K edges):** 10-20 minutes

Current dataset: ~32K nodes + ~9K edges ≈ 8-12 minutes

**Note:** Edge syncing typically takes longer than node syncing due to relationship complexity.

## Manual Steps (If Needed)

If the automated script fails, you can run steps manually:

```bash
# 1. Stop everything
docker-compose down

# 2. Start databases only
docker-compose up -d neo4j falkordb

# 3. Wait for health (check with: docker-compose ps)

# 4. Clear FalkorDB
docker-compose exec falkordb redis-cli GRAPH.DELETE graphiti_migration

# 5. Start sync service
docker-compose up -d graphiti-sync-rs

# 6. Monitor restore (in separate terminal)
# Watch both nodes AND edges
watch 'echo "Nodes:"; docker-compose exec falkordb redis-cli GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)" 2>/dev/null | grep -oP "\d+" | head -1; echo "Edges:"; docker-compose exec falkordb redis-cli GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" 2>/dev/null | grep -oP "\d+" | head -1'

# 7. When stable, start everything else
docker-compose up -d
```

## Troubleshooting

### Script Times Out

**Problem:** Restore takes longer than expected

**Solution:** Increase timeout

```bash
# Set longer timeout (20 minutes)
SYNC_TIMEOUT=1200 ./scripts/automated-cold-boot.sh
```

### Worker Started Too Early

**Problem:** Worker is processing but FalkorDB is empty

**Solution:** Stop worker, let restore finish, restart worker

```bash
# Stop worker
docker-compose stop graphiti-worker

# Wait for restore (check with watch command above)

# Restart worker
docker-compose start graphiti-worker
```

### FalkorDB Has Stale Data

**Problem:** Node count doesn't match Neo4j

**Solution:** Force full re-sync

```bash
# Clear FalkorDB
docker-compose exec falkordb redis-cli GRAPH.DELETE graphiti_migration

# Restart sync service (triggers restore)
docker-compose restart graphiti-sync-rs

# Wait for restore
./scripts/automated-cold-boot.sh
```

## Advanced: Docker Compose Init Container

For production deployments with auto-restart:

```bash
# Use init container configuration
docker-compose -f docker-compose.yml -f docker-compose.init.yml up -d
```

This adds an init container that:
- Runs automatically on startup
- Worker waits for init completion
- No manual intervention needed

See [COLD_BOOT_AUTOMATION.md](COLD_BOOT_AUTOMATION.md) for details.

## Monitor Restore Progress

Use the included monitoring script for real-time progress:

```bash
./scripts/monitor-restore.sh
```

This displays:
- Current node and edge counts
- Changes per iteration (+delta)
- Elapsed time
- Status (syncing nodes/edges/complete)

## Verify System Health

```bash
# Check all services
docker-compose ps

# Check specific service health
curl http://localhost:8003/healthcheck  # API
curl http://localhost:18080/health      # Sync service
curl http://localhost:3000/api/stats    # Visualizer

# Check FalkorDB restore (nodes + edges)
echo "Nodes:"
docker-compose exec falkordb redis-cli GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)"
echo "Edges:"
docker-compose exec falkordb redis-cli GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)"
```

## Service URLs

After successful cold boot:

- **API Server:** http://localhost:8003
- **Frontend:** http://localhost:8084
- **Graph Visualizer:** http://localhost:3000
- **Neo4j Browser:** http://localhost:7474
- **Queue Dashboard:** http://localhost:8093
- **Sync Health:** http://localhost:18080/health
- **Grafana:** http://localhost:3011

## Next Steps

1. Verify services are running: `docker-compose ps`
2. Check API health: `curl http://localhost:8003/healthcheck`
3. Open frontend: http://localhost:8084
4. Monitor sync: http://localhost:18080/health

## Full Documentation

- **Complete automation guide:** [COLD_BOOT_AUTOMATION.md](COLD_BOOT_AUTOMATION.md)
- **Architecture details:** [CLAUDE.md](CLAUDE.md)
- **Service configuration:** [docker-compose.yml](docker-compose.yml)
