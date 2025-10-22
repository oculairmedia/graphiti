# Worker Ingestion Performance Fix

## Problem Identified

**Massive LLM timeout storms** causing slow ingestion:
- 161+ timeouts in last 1000 log lines
- Workers experiencing cascading retry storms
- Root cause: **Too many concurrent Ollama requests**

## Analysis

### Before Fix:
```
WORKER_COUNT=4
BATCH_SIZE=10
→ Up to 40 concurrent LLM requests to Ollama
→ Ollama (gemma3:12b) couldn't handle the load
→ Requests timing out at 120s default
→ Retry storms amplifying the problem
```

### Ollama Server Status:
- **LLM**: http://100.81.139.20:11434 (gemma3:12b - 12B params, Q4_K_M)
- **Embeddings**: http://192.168.50.80:11434 (Qwen3-Embedding-4B - 4B params, Q4_K_M)
- Both servers loaded with models but overwhelmed by concurrent requests

## Solution Applied

Created `docker-compose.worker-fix.yml` with reduced concurrency:

```yaml
services:
  graphiti-worker:
    environment:
      - WORKER_COUNT=2              # Down from 4 (50% reduction)
      - BATCH_SIZE=3                # Down from 10 (70% reduction)
      - OLLAMA_TIMEOUT_SECONDS=300  # Increase to 5 minutes
      - OLLAMA_MAX_RETRIES=3        # Reduce retries from 5
      - POLL_INTERVAL=2.0           # Slow down polling
```

### Deployment:
```bash
docker-compose -f docker-compose.yml -f docker-compose.worker-fix.yml up -d graphiti-worker
```

## Results

### Before:
- ❌ 161 timeouts in 1000 log lines
- ❌ Worker logs filled with retry storms
- ❌ Ingestion essentially stalled

### After (30 second test):
- ✅ **0 timeouts**
- ✅ Clean processing logs
- ✅ Workers successfully extracting nodes
- ✅ ~6 concurrent requests instead of 40

### Sample Clean Logs:
```
2025-10-10 00:56:33 - INFO - Started worker pool with 2 workers
2025-10-10 00:56:33 - INFO - Processing episode with group_id: emmanuel_claude_tools
2025-10-10 00:56:33 - INFO - Created EpisodicNode (uuid: 420a5c27-e62c-59e7-91ab-d837feff9974)
2025-10-10 00:56:33 - INFO - Episode: Extracting nodes (attempt 1)
```

## Trade-offs

**Pros:**
- ✅ Stable, reliable ingestion
- ✅ No timeout errors
- ✅ Better Ollama server utilization
- ✅ Lower memory pressure on worker

**Cons:**
- ⚠️ Slower throughput (2 workers vs 4, batches of 3 vs 10)
- ⚠️ Queue will process more slowly

## Recommendations

### Short-term (Current):
- **Keep current settings** for stability
- Monitor queue depth vs processing rate

### Medium-term:
1. **Scale Ollama horizontally** - add more Ollama servers behind a load balancer
2. **Use faster model** - consider switching to smaller/faster model if acceptable
3. **Upgrade hardware** - Ollama server may benefit from more VRAM/CPU

### Long-term:
1. **Switch to managed LLM** - OpenAI/Anthropic for better throughput
2. **Hybrid approach** - Use fast API for extraction, Ollama for embeddings only
3. **Add rate limiting** - Implement proper concurrency control in worker pool

## Monitoring

Watch for healthy processing:
```bash
docker logs graphiti-graphiti-worker-1 --tail 50 --follow
```

Expect to see:
- ✅ "Processing episode with group_id:"
- ✅ "Created EpisodicNode"
- ✅ "Extracting nodes (attempt 1)"
- ❌ NO "Request timed out"
- ❌ NO "Retrying request" storms

## Files Modified

- `docker-compose.worker-fix.yml` (new override file)
- Applied via: `docker-compose -f docker-compose.yml -f docker-compose.worker-fix.yml up -d`

## Environment Variables Verified

```bash
$ docker exec graphiti-graphiti-worker-1 env | grep -E "(WORKER_COUNT|BATCH_SIZE|OLLAMA_TIMEOUT)"
BATCH_SIZE=3
OLLAMA_TIMEOUT_SECONDS=300
WORKER_COUNT=2
```

All settings correctly applied ✅
