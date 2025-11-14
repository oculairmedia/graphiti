# Testing Automated Cold Boot

## Test the Built-In Automation

Follow these steps to verify the automated cold boot works:

### Step 1: Clean Slate

```bash
# Stop everything
docker-compose down

# Remove init marker (force fresh init)
docker volume rm graphiti_init_ready_marker 2>/dev/null || true
```

### Step 2: Start Stack

```bash
# Start everything
docker-compose up -d
```

### Step 3: Monitor Init Service

```bash
# Watch init logs in real-time
docker-compose logs -f graphiti-init
```

**Expected output:**
```
graphiti-init  | [HH:MM:SS] 🚀 Starting Graphiti Cold Boot Initialization
graphiti-init  | [HH:MM:SS] Step 1: Waiting for databases to be ready...
graphiti-init  | [HH:MM:SS] ✅ Neo4j is ready
graphiti-init  | [HH:MM:SS] ✅ FalkorDB is ready
graphiti-init  | [HH:MM:SS] Step 3: Clearing FalkorDB...
graphiti-init  | [HH:MM:SS] ✅ FalkorDB cleared successfully
graphiti-init  | [HH:MM:SS] Step 6: Waiting for restore to complete...
graphiti-init  | [HH:MM:SS] Progress: 5000 nodes, 0 edges...
graphiti-init  | [HH:MM:SS] Progress: 31556 nodes, 8807 edges...
graphiti-init  | [HH:MM:SS] ✅ Restore complete: 31556 nodes, 8807 edges
graphiti-init  | [HH:MM:SS] ✅ 🎉 Cold Boot Initialization Complete!
```

### Step 4: Verify Init Completed

```bash
# Check init status
docker-compose ps graphiti-init
```

**Expected:**
```
NAME            STATUS
graphiti-init   Exited (0)
```

Exit code 0 = success!

### Step 5: Verify Worker Waited

```bash
# Check worker logs
docker-compose logs graphiti-worker | head -20
```

**Expected:**
```
graphiti-worker  | [HH:MM:SS] 🔧 Worker service starting...
graphiti-worker  | [HH:MM:SS] Waiting for system initialization to complete...
graphiti-worker  | [HH:MM:SS] ✅ System initialization complete!
graphiti-worker  | [HH:MM:SS] Starting worker...
```

### Step 6: Verify FalkorDB Restored

```bash
# Check node count
docker-compose exec falkordb redis-cli GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)"

# Check edge count
docker-compose exec falkordb redis-cli GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)"
```

**Expected:**
- Nodes: ~31,556 (or your database size)
- Edges: ~8,807 (or your database size)

### Step 7: Verify All Services Running

```bash
docker-compose ps
```

**All services should be Up/healthy:**
- ✅ neo4j (healthy)
- ✅ falkordb (healthy)
- ✅ graphiti-sync-rs (Up)
- ✅ graphiti-init (Exited 0)
- ✅ graphiti-worker (healthy)
- ✅ graph (healthy)
- ✅ frontend (healthy)

## Troubleshooting Test Failures

### Init Service Failed

```bash
# Check detailed logs
docker-compose logs graphiti-init

# Common fixes:
# 1. Neo4j not ready
docker-compose logs neo4j

# 2. Sync service issues
docker-compose logs graphiti-sync-rs

# 3. Timeout - increase in .env
echo "SYNC_TIMEOUT=2400" >> .env
docker-compose down
docker-compose up -d
```

### Worker Started Too Early

```bash
# Check if init completed
docker-compose ps graphiti-init

# Should show "Exited (0)"
# If not, check init logs
```

### FalkorDB Empty After Init

```bash
# Check if sync service is running
docker-compose logs graphiti-sync-rs

# Manually trigger restore
docker-compose restart graphiti-sync-rs

# Wait and check again
sleep 60
docker-compose exec falkordb redis-cli GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)"
```

## Test Different Scenarios

### Scenario 1: Fresh Start

```bash
docker-compose down
docker volume rm graphiti_init_ready_marker
docker-compose up -d
# Should restore from Neo4j
```

### Scenario 2: Restart (Data Exists)

```bash
docker-compose restart
# Init should clear and restore
```

### Scenario 3: After Code Update

```bash
docker-compose down
docker-compose pull
docker-compose up -d
# Should restore fresh data
```

## Success Criteria

✅ Init service exits with code 0  
✅ Worker waits for init completion  
✅ FalkorDB contains nodes AND edges  
✅ All services start successfully  
✅ No errors in logs  
✅ API healthcheck passes: `curl http://localhost:8003/healthcheck`  
✅ Frontend accessible: http://localhost:8084  

## Performance Benchmarks

Track init times for your system:

```bash
# Start timing
START=$(date +%s)

# Run cold boot
docker-compose down && docker volume rm graphiti_init_ready_marker
docker-compose up -d

# Wait for completion
while [ "$(docker-compose ps -q graphiti-init | xargs docker inspect -f '{{.State.Status}}')" != "exited" ]; do
  sleep 5
done

# Calculate duration
END=$(date +%s)
echo "Cold boot took: $((END - START)) seconds"
```

**Baseline expectations:**
- Small graph (<10K nodes): 2-3 minutes
- Medium graph (10K-50K nodes): 5-10 minutes
- Large graph (>50K nodes): 10-20 minutes

## Cleanup After Testing

```bash
# Stop all services
docker-compose down

# Remove init marker
docker volume rm graphiti_init_ready_marker

# Start normally
docker-compose up -d
```
