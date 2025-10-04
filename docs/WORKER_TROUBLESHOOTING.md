# Worker Pipeline Troubleshooting Guide

## Symptoms

Worker has gone silent - no activity on Ollama, indicating the ingestion pipeline is obstructed.

## Quick Diagnostics

Run these commands to identify the issue:

### 1. Check Worker Status

```bash
# Check if worker container is running
docker-compose ps graphiti-worker

# Check worker logs (last 100 lines)
docker-compose logs --tail=100 graphiti-worker

# Follow worker logs in real-time
docker-compose logs -f graphiti-worker
```

### 2. Check Queue Status

```bash
# List all queues
curl http://localhost:8093/queues

# Get ingestion queue metrics
curl -H "Accept: application/json" \
  http://localhost:8093/queue/ingestion/metrics | jq

# Get memory_replay queue metrics (if exists)
curl -H "Accept: application/json" \
  http://localhost:8093/queue/memory_replay/metrics | jq
```

### 3. Check for Stuck Messages

```bash
# Check if there are messages in the queue
# Look for "visible" vs "invisible" counts
curl -H "Accept: application/json" \
  http://localhost:8093/queue/ingestion/metrics | jq '.visible, .invisible'
```

### 4. Check Ollama Connectivity

```bash
# Test Ollama from worker container
docker exec <worker-container-name> curl http://192.168.50.80:11434/api/tags

# Or check if Ollama is responding
curl http://192.168.50.80:11434/api/tags
```

### 5. Check Database Connectivity

```bash
# Test FalkorDB connection
docker exec <worker-container-name> python3 -c "
from graphiti_core.driver.falkordb_driver import FalkorDriver
driver = FalkorDriver(host='falkordb', port=6379)
print('FalkorDB connection OK')
"
```

## Common Issues & Solutions

### Issue 1: Worker Crashed or Exited

**Symptoms:**
- Container status shows "Exited" or "Restarting"
- No recent logs

**Check:**
```bash
docker-compose ps graphiti-worker
docker-compose logs --tail=200 graphiti-worker | grep -i error
```

**Solution:**
```bash
# Restart worker
docker-compose restart graphiti-worker

# Or rebuild if code changed
docker-compose build --no-cache graph
docker-compose up -d --force-recreate graphiti-worker
```

### Issue 2: Messages Stuck in "Invisible" State

**Symptoms:**
- Queue metrics show high "invisible" count
- No "visible" messages
- Worker not processing

**Cause:** Messages were polled but not deleted/completed, visibility timeout hasn't expired yet.

**Check:**
```bash
curl -H "Accept: application/json" \
  http://localhost:8093/queue/ingestion/metrics | jq
```

**Solution:**
```bash
# Wait for visibility timeout to expire (default: 300 seconds)
# Or manually clear stuck messages (CAUTION: will lose messages)
# See "Force Clear Queue" section below
```

### Issue 3: Worker Waiting for Visibility Timeout

**Symptoms:**
- Worker logs show no activity
- Queue has messages but they're "invisible"
- Last log entry shows task processing started but not completed

**Cause:** Worker is processing a task that's taking longer than expected, or crashed mid-processing.

**Check:**
```bash
# Check last worker activity
docker-compose logs --tail=50 graphiti-worker | grep -E "Processing|Completed|Error"
```

**Solution:**
```bash
# Wait for visibility timeout (5 minutes default)
# Or restart worker to abandon current task
docker-compose restart graphiti-worker
```

### Issue 4: Ollama Connection Lost

**Symptoms:**
- Worker logs show connection errors to Ollama
- No activity on Ollama server

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
# Or update worker environment variables
# Check OLLAMA_BASE_URL is correct
```

### Issue 5: Database Connection Lost

**Symptoms:**
- Worker logs show database connection errors
- Tasks fail with database errors

**Check:**
```bash
# Check FalkorDB is running
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
# Restart FalkorDB
docker-compose restart falkordb

# Restart worker
docker-compose restart graphiti-worker
```

### Issue 6: Worker Deadlock or Infinite Loop

**Symptoms:**
- Worker container running but no logs
- CPU usage high or stuck
- No progress on tasks

**Check:**
```bash
# Check CPU usage
docker stats graphiti-worker --no-stream

# Check if worker is responsive
docker exec <worker-container> ps aux
```

**Solution:**
```bash
# Force restart
docker-compose kill graphiti-worker
docker-compose up -d graphiti-worker
```

## Advanced Diagnostics

### Check Worker Health

```bash
# If worker has health endpoint
curl http://localhost:<worker-port>/health

# Check worker process
docker exec <worker-container> ps aux | grep python
```

### Inspect Queue Messages

```python
# Create a script to peek at queue messages
from graphiti_core.ingestion.queue_client import QueuedClient
import asyncio

async def inspect_queue():
    client = QueuedClient(base_url="http://localhost:8093")
    
    # Poll with very short visibility timeout (1 second)
    messages = await client.poll(
        queue_name="ingestion",
        count=10,
        visibility_timeout=1
    )
    
    print(f"Found {len(messages)} messages")
    for msg_id, task, metadata in messages:
        print(f"\nMessage {msg_id}:")
        print(f"  Type: {task.type}")
        print(f"  Priority: {task.priority}")
        print(f"  Payload: {task.payload}")
        print(f"  Metadata: {metadata}")
    
    await client.close()

asyncio.run(inspect_queue())
```

### Check Worker Configuration

```bash
# Check all worker environment variables
docker exec <worker-container> env | sort

# Key variables to check:
# - QUEUE_URL
# - OLLAMA_BASE_URL
# - FALKORDB_HOST
# - FALKORDB_PORT
# - USE_FALKORDB
# - OPENAI_API_KEY (or other LLM keys)
```

## Force Clear Queue (CAUTION)

**WARNING:** This will permanently delete all messages in the queue.

```bash
# Option 1: Delete and recreate queue
curl -X DELETE http://localhost:8093/queue/ingestion
curl -X PUT http://localhost:8093/queue/ingestion

# Option 2: Use Python client
python3 << 'EOF'
from graphiti_core.ingestion.queue_client import QueuedClient
import asyncio

async def clear_queue():
    client = QueuedClient(base_url="http://localhost:8093")
    
    # Poll all messages with short timeout
    while True:
        messages = await client.poll(
            queue_name="ingestion",
            count=100,
            visibility_timeout=1
        )
        
        if not messages:
            break
        
        # Delete all polled messages
        for msg_id, _, _ in messages:
            await client.delete(queue_name="ingestion", message_ids=[msg_id])
        
        print(f"Deleted {len(messages)} messages")
    
    await client.close()

asyncio.run(clear_queue())
EOF
```

## Monitoring Commands

```bash
# Watch queue metrics in real-time
watch -n 5 'curl -s -H "Accept: application/json" http://localhost:8093/queue/ingestion/metrics | jq'

# Watch worker logs
docker-compose logs -f graphiti-worker

# Watch Ollama activity (if accessible)
watch -n 2 'curl -s http://192.168.50.80:11434/api/ps'
```

## Recovery Procedure

If worker is completely stuck:

```bash
# 1. Stop worker
docker-compose stop graphiti-worker

# 2. Check queue status
curl -H "Accept: application/json" \
  http://localhost:8093/queue/ingestion/metrics | jq

# 3. Wait for visibility timeout (5 minutes) or clear queue

# 4. Restart worker
docker-compose up -d graphiti-worker

# 5. Monitor logs
docker-compose logs -f graphiti-worker

# 6. Verify processing resumes
# Should see "Processing task" messages
```

## Prevention

### Set Appropriate Timeouts

```python
# In worker configuration
VISIBILITY_TIMEOUT = 300  # 5 minutes
POLL_INTERVAL = 5  # 5 seconds
MAX_RETRIES = 3
```

### Add Health Checks

```yaml
# In docker-compose.yml
graphiti-worker:
  healthcheck:
    test: ["CMD", "python", "-c", "import sys; sys.exit(0)"]
    interval: 30s
    timeout: 10s
    retries: 3
```

### Monitor Queue Depth

```bash
# Alert if queue depth exceeds threshold
DEPTH=$(curl -s -H "Accept: application/json" \
  http://localhost:8093/queue/ingestion/metrics | jq '.visible')

if [ "$DEPTH" -gt 100 ]; then
  echo "WARNING: Queue depth is $DEPTH"
fi
```

## Related Documentation

- **Queue API:** `docs/QUEUED_API_REFERENCE.md`
- **Worker System:** `docs/ingestion-queue-worker-triage.md`
- **Memory Replay:** `docs/11-memory-replay-operations.md`

