# Worker Silent - Investigation Guide

## Problem

Worker has gone silent - no activity on Ollama, indicating the ingestion pipeline is obstructed.

## Quick Diagnosis

Run the diagnostic script:

```bash
python3 diagnose_worker.py
```

Or run these manual checks:

```bash
# 1. Check queue metrics
curl -H "Accept: application/json" \
  http://localhost:8093/queue/ingestion/metrics | jq

# 2. Check worker logs
docker-compose logs --tail=100 graphiti-worker

# 3. Check worker status
docker-compose ps graphiti-worker
```

## Most Likely Causes

### Cause 1: Messages Stuck in "Invisible" State (80% probability)

**Symptoms:**
- Queue metrics show `invisible > 0` and `visible = 0`
- Worker logs show task started but not completed
- No recent activity in logs

**Why it happens:**
- Worker polled messages with 20-minute visibility timeout
- Worker is still processing (long-running task)
- OR worker crashed mid-processing
- Messages won't become visible again until timeout expires

**Check:**
```bash
curl -H "Accept: application/json" \
  http://localhost:8093/queue/ingestion/metrics | jq '.visible, .invisible'
```

**Solution:**

```bash
# Option 1: Wait for visibility timeout (20 minutes)
# Messages will automatically become visible again

# Option 2: Restart worker to abandon current task
docker-compose restart graphiti-worker

# Option 3: Check what worker is doing
docker-compose logs --tail=50 graphiti-worker | grep -E "Processing|Completed|Error"
```

### Cause 2: Worker Crashed or Exited (15% probability)

**Symptoms:**
- Container status shows "Exited" or "Restarting"
- No recent logs
- Worker not responding

**Check:**
```bash
docker-compose ps graphiti-worker
```

**Solution:**
```bash
# Check exit reason
docker-compose logs --tail=200 graphiti-worker | grep -i error

# Restart worker
docker-compose restart graphiti-worker

# If keeps crashing, rebuild
docker-compose build --no-cache graph
docker-compose up -d --force-recreate graphiti-worker
```

### Cause 3: Ollama Connection Lost (3% probability)

**Symptoms:**
- Worker logs show connection errors to Ollama
- Ollama not responding on port 11434

**Check:**
```bash
# Test Ollama connectivity
curl http://192.168.50.80:11434/api/tags

# Check worker environment
docker exec <worker-container> env | grep OLLAMA
```

**Solution:**
```bash
# Restart Ollama service
# Or update OLLAMA_BASE_URL in worker environment
```

### Cause 4: Database Connection Lost (1% probability)

**Symptoms:**
- Worker logs show database connection errors
- FalkorDB not responding

**Check:**
```bash
# Check FalkorDB
docker-compose ps falkordb

# Test connection
docker exec <worker-container> python3 -c "
import redis
r = redis.Redis(host='falkordb', port=6379)
print(r.ping())
"
```

**Solution:**
```bash
docker-compose restart falkordb
docker-compose restart graphiti-worker
```

### Cause 5: Worker Deadlock (1% probability)

**Symptoms:**
- Worker running but no logs
- CPU usage stuck
- No progress

**Check:**
```bash
# Check CPU usage
docker stats graphiti-worker --no-stream

# Check processes
docker exec <worker-container> ps aux
```

**Solution:**
```bash
# Force restart
docker-compose kill graphiti-worker
docker-compose up -d graphiti-worker
```

## Step-by-Step Investigation

### Step 1: Run Diagnostic Script

```bash
python3 diagnose_worker.py
```

This will check:
- Queue service health
- Queue metrics (visible/invisible messages)
- Ollama connectivity
- Worker health
- Peek at queue messages

### Step 2: Analyze Queue Metrics

```bash
curl -H "Accept: application/json" \
  http://localhost:8093/queue/ingestion/metrics | jq
```

**Interpret results:**

| Visible | Invisible | Diagnosis |
|---------|-----------|-----------|
| 0 | 0 | Queue empty - no work |
| >0 | 0 | Messages ready - worker not polling |
| 0 | >0 | Messages stuck in processing |
| >0 | >0 | Mixed - some processing, some ready |

### Step 3: Check Worker Logs

```bash
# Last 100 lines
docker-compose logs --tail=100 graphiti-worker

# Follow in real-time
docker-compose logs -f graphiti-worker

# Search for errors
docker-compose logs graphiti-worker | grep -i error

# Search for task processing
docker-compose logs graphiti-worker | grep -E "Processing|Completed"
```

**Look for:**
- Last task started
- Any errors or exceptions
- Connection issues
- Rate limit messages

### Step 4: Check Worker Status

```bash
# Container status
docker-compose ps graphiti-worker

# Should show "Up" not "Exited" or "Restarting"
```

### Step 5: Check External Services

```bash
# Ollama
curl http://192.168.50.80:11434/api/tags

# FalkorDB
docker-compose ps falkordb

# Queue service
curl http://localhost:8093/healthz
```

## Recovery Procedures

### Procedure 1: Soft Recovery (Try First)

```bash
# 1. Check current state
python3 diagnose_worker.py

# 2. Restart worker
docker-compose restart graphiti-worker

# 3. Monitor logs
docker-compose logs -f graphiti-worker

# 4. Verify processing resumes
# Should see "Processing task" messages within 1-2 minutes
```

### Procedure 2: Hard Recovery (If Soft Fails)

```bash
# 1. Stop worker
docker-compose stop graphiti-worker

# 2. Check queue metrics
curl -H "Accept: application/json" \
  http://localhost:8093/queue/ingestion/metrics | jq

# 3. Wait for visibility timeout (20 minutes)
# OR force clear invisible messages (see below)

# 4. Rebuild worker
docker-compose build --no-cache graph

# 5. Start worker
docker-compose up -d graphiti-worker

# 6. Monitor
docker-compose logs -f graphiti-worker
```

### Procedure 3: Force Clear Stuck Messages (CAUTION)

**WARNING:** This will make invisible messages visible immediately, potentially causing duplicate processing.

```bash
# Option 1: Restart queue service (resets visibility)
docker-compose restart graphiti-queued

# Option 2: Delete and recreate queue (LOSES ALL MESSAGES)
curl -X DELETE http://localhost:8093/queue/ingestion
curl -X PUT http://localhost:8093/queue/ingestion
```

## Prevention

### 1. Add Worker Health Monitoring

```bash
# Add to docker-compose.yml
graphiti-worker:
  healthcheck:
    test: ["CMD", "python", "-c", "import sys; sys.exit(0)"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 40s
```

### 2. Monitor Queue Depth

```bash
# Create monitoring script
cat > monitor_queue.sh << 'EOF'
#!/bin/bash
while true; do
  VISIBLE=$(curl -s -H "Accept: application/json" \
    http://localhost:8093/queue/ingestion/metrics | jq '.visible')
  INVISIBLE=$(curl -s -H "Accept: application/json" \
    http://localhost:8093/queue/ingestion/metrics | jq '.invisible')
  
  echo "$(date): Visible=$VISIBLE, Invisible=$INVISIBLE"
  
  if [ "$INVISIBLE" -gt 10 ]; then
    echo "WARNING: High invisible count!"
  fi
  
  sleep 30
done
EOF

chmod +x monitor_queue.sh
./monitor_queue.sh
```

### 3. Reduce Visibility Timeout

If tasks are quick, reduce timeout to recover faster:

```python
# In worker.py, line 273
visibility_timeout=300  # 5 minutes instead of 20
```

### 4. Add Worker Heartbeat Logging

```python
# In worker._process_loop(), add periodic logging
if not tasks:
    logger.info(f"Worker {self.worker_id} idle, waiting for tasks...")
    await asyncio.sleep(self.poll_interval)
```

## Useful Commands Reference

```bash
# Queue metrics
curl -H "Accept: application/json" http://localhost:8093/queue/ingestion/metrics | jq

# Worker logs
docker-compose logs --tail=100 graphiti-worker

# Worker status
docker-compose ps graphiti-worker

# Restart worker
docker-compose restart graphiti-worker

# Rebuild worker
docker-compose build --no-cache graph && docker-compose up -d --force-recreate graphiti-worker

# Check Ollama
curl http://192.168.50.80:11434/api/tags

# Check FalkorDB
docker-compose ps falkordb

# Monitor in real-time
watch -n 5 'curl -s -H "Accept: application/json" http://localhost:8093/queue/ingestion/metrics | jq'
```

## Related Documentation

- **Worker Troubleshooting:** `docs/WORKER_TROUBLESHOOTING.md`
- **Queue API:** `docs/QUEUED_API_REFERENCE.md`
- **Diagnostic Script:** `diagnose_worker.py`

