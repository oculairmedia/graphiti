# External Dependencies Catalog

## Overview
Graphiti's episode ingestion pipeline depends on multiple external services, each with specific rate limits, retry strategies, and failure modes. Understanding these dependencies is critical for designing a Temporal migration that maintains reliability.

---

## Dependency Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Graphiti Ingestion Pipeline                      │
└────────┬────────────────────┬───────────────────┬───────────────────┘
         │                    │                   │
         ▼                    ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   LLM Service   │  │ Embedding Svc   │  │   FalkorDB      │
│  (GLM-4.5 via   │  │ (Qwen3 vLLM)    │  │  (Graph Store)  │
│   Chutes/Z.AI)  │  │                 │  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
         │                    │                   │
         │                    │                   │
         ▼                    ▼                   ▼
  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
  │ Fallback:    │   │ Reranker:    │   │ Centrality:  │
  │ Anthropic    │   │ Qwen3-       │   │ Rust Service │
  │ (optional)   │   │ Reranker-4B  │   │ (optional)   │
  └──────────────┘   └──────────────┘   └──────────────┘
```

---

## 1. LLM Services (Language Models)

### 1.1 Primary: GLM-4.5 via Chutes (Z.AI)

**Purpose**: Entity extraction, node deduplication, edge extraction (15-25 calls per episode)

**Configuration** (from `.env`):
- `CHUTES_BASE_URL=https://api.z.ai/api/coding/paas/v4`
- `CHUTES_MODEL=glm-4.5` (main model)
- `CHUTES_SMALL_MODEL=glm-4.5-air` (simpler tasks)
- `CHUTES_API_KEY=c9e26b23c6194059892ff22e99ec0ad6.pSk7TwXDsLSQNtvT`

**Rate Limits**:
- **Quota System**: Hourly quota (currently at 34% as of Jan 12, 2026)
- **No explicit req/sec limit**: Controlled by quota consumption
- **Tokens per request**: Max 8192 (DEFAULT_MAX_TOKENS), typical: 6000 (MAX_PROMPT_TOKENS)

**Retry Strategy**:
- **Client-side**: BaseOpenAIClient.MAX_RETRIES = 2
- **Error detection**: String matching `'rate limit' in str(e).lower()`
- **Raises**: `RateLimitError` → triggers worker-level backoff

**Failure Modes**:
1. **Rate Limit Exceeded**: Returns HTTP 429, raises `RateLimitError`
2. **Quota Exhausted**: Same as rate limit, but may persist for hours
3. **Refusal Error**: Model refuses to respond (safety filters), raises `RefusalError`
4. **Empty Response**: No content returned, raises `EmptyResponseError`
5. **Timeout**: Network timeout, treated as transient error

**Worker-Level Handling** (from `worker.py`):
- **Detection**: `if 'rate limit' in str(e).lower()` (line 522)
- **Response**: Suspend group for 60s, raise `RateLimitError(group_id, retry_after=60)`
- **Queue behavior**: Task returned to queue with exponential backoff

**Circuit Breaker**: None (manual suspension via rate limiter)

---

### 1.2 Fallback: Anthropic Claude (Optional)

**Purpose**: Fallback when primary LLM fails (if `ENABLE_FALLBACK=true`)

**Configuration**:
- `ANTHROPIC_BASE_URL=http://192.168.50.90:8082`
- `ANTHROPIC_MODEL=claude-3-5-haiku-latest`
- `ANTHROPIC_SMALL_MODEL=claude-3-5-haiku-latest`
- `ANTHROPIC_API_KEY=sk-ant-api03-...(masked)...`

**Rate Limits**:
- **Anthropic API**: 50 requests/min (tier 1), 5000 requests/day
- **Tokens**: 40K input tokens/min, 8K output tokens/min (tier 1)

**Retry Strategy**:
- **Client-side**: FallbackClient catches `RateLimitError` and cascades to next provider
- **Cascade order**: Primary (Chutes) → Anthropic → (no further fallback)

**Failure Modes**:
1. **Rate limit**: HTTP 429, triggers cascade
2. **Context length exceeded**: Model max context (200K tokens) exceeded
3. **Network timeout**: Self-hosted proxy may be unreachable
4. **Authentication failure**: Invalid API key

**Current Status**: Enabled (`ENABLE_FALLBACK=true`), but rarely used (primary is stable)

---

### 1.3 Supported Providers (Not Currently Used)

**OpenAI** (client implemented, not configured):
- Rate limits: Tier-dependent (500 RPM for gpt-4o-mini on tier 1)
- Retry: Same as Chutes (BaseOpenAIClient)

**Groq** (client implemented):
- Rate limits: 30 RPM (free tier), 600 RPM (paid tier)
- Retry: Catches `groq.RateLimitError`, raises `RateLimitError`

**Gemini** (client implemented):
- Rate limits: 15 RPM (free tier), 1000 RPM (paid tier)
- Retry: Pattern matching for rate limit errors

**Ollama** (local LLM, client implemented):
- No rate limits (self-hosted)
- Failure mode: Service unavailable (connection refused)

---

## 2. Embedding Services

### 2.1 Primary: Qwen3-Embedding via vLLM

**Purpose**: Generate 1536-dimensional embeddings for nodes and edges (semantic search)

**Configuration**:
- `OLLAMA_EMBEDDING_BASE_URL=http://100.81.139.20:11450/v1`
- `OLLAMA_EMBEDDING_MODEL=qwen3-embedding`
- `USE_OLLAMA_EMBEDDINGS=true`
- `USE_DEDICATED_EMBEDDING_ENDPOINT=true`

**Rate Limits**:
- **Self-hosted vLLM**: No external rate limits
- **Throughput**: Limited by GPU availability (batch processing)
- **Batch size**: Configured in embedder client (typically 10-50)

**Retry Strategy**:
- **Client**: OpenAIEmbedder (uses OpenAI-compatible API)
- **Retries**: Handled by `httpx` library (default 3 retries with exponential backoff)
- **Timeout**: Default 60s per request

**Failure Modes**:
1. **Service unavailable**: vLLM container down (503 error)
2. **GPU OOM**: Batch too large, vLLM crashes
3. **Network timeout**: Slow GPU inference (rare)
4. **Invalid input**: Text too long, raises validation error

**Performance**:
- **Latency**: ~200-500ms per batch of 10 embeddings
- **Throughput**: ~20-30 embeddings/sec (single GPU)

**Fallback**: None configured (critical path failure)

---

### 2.2 Alternative: OpenAI Embeddings (Not Used)

**Configuration**:
- `OPENAI_API_KEY=` (empty, not configured)
- Model: `text-embedding-3-small` (default)

**Rate Limits**:
- **Tier 1**: 3000 requests/min, 1M tokens/min
- **Tier 2**: 5000 requests/min

**Retry Strategy**: Same as OpenAI LLM client

---

## 3. Graph Database: FalkorDB

### 3.1 Core Configuration

**Purpose**: Persistent graph storage, vector search, Cypher queries

**Connection**:
- **Host**: `localhost:6379` (Redis protocol)
- **Database**: `graphiti_migration`
- **Driver**: FalkorDB async Python client
- **Protocol**: Redis wire protocol with graph extensions

**Configuration** (from `docker-compose.yml`):
- **Memory**: 16GB limit (8GB runtime maxmemory, 8GB headroom for RDB reload)
- **Persistence**: RDB snapshots every 5 min (≥1 change) or 1 min (≥100 changes)
- **Indexes**: UUID indexes on all node/edge types (RANGE indexes)

---

### 3.2 Rate Limits & Performance

**Connection Pool**:
- **Not explicitly pooled**: FalkorDB driver uses single async connection
- **Concurrency**: Limited by Redis single-threaded nature (parallelism via pipelining)

**Query Limits**:
- **Memory per query**: `QUERY_MEM_CAPACITY=134217728` (128MB)
- **Node creation buffer**: `NODE_CREATION_BUFFER=128`
- **Cache size**: `CACHE_SIZE=5`
- **Max memory**: 8GB (runtime), 16GB (container limit)

**Performance Characteristics**:
- **Write throughput**: ~1000-2000 ops/sec (batched)
- **Read throughput**: ~5000-10000 ops/sec (simple queries)
- **Vector search**: ~100-500ms for similarity search (depends on graph size)
- **Batch operations**: Preferred (use `UNWIND` in Cypher)

---

### 3.3 Failure Modes

**1. Out of Memory (OOM)**:
- **Symptom**: Container restart, queries fail with OOM error
- **Cause**: Graph exceeds 8GB runtime limit or 16GB container limit
- **Mitigation**: Increase memory limits, reduce batch sizes
- **Retry**: Connection re-established automatically after restart

**2. RDB Save Failure**:
- **Symptom**: Log message "Background save failed"
- **Cause**: Disk space full, I/O error
- **Impact**: No immediate impact (writes continue, but no persistence)
- **Configured**: `stop-writes-on-bgsave-error no` (don't block writes)

**3. Connection Loss**:
- **Symptom**: `redis.exceptions.ConnectionError`
- **Cause**: FalkorDB container restart, network issue
- **Retry**: Worker treats as `TransientError`, retries with backoff

**4. Query Timeout**:
- **Symptom**: Query exceeds timeout (default 300s)
- **Cause**: Complex graph traversal, large result set
- **Mitigation**: Optimize query, add LIMIT clauses
- **Retry**: Worker retries as transient error

**5. Index Corruption**:
- **Symptom**: Query returns incorrect results, missing data
- **Cause**: Interrupted RDB save, index rebuild needed
- **Recovery**: Restart FalkorDB, indexes auto-rebuild (slow)

---

### 3.4 Healthcheck & Monitoring

**Healthcheck** (from `docker-compose.yml`):
```bash
test: ["CMD", "redis-cli", "ping"]
interval: 10s
timeout: 5s
retries: 3
start_period: 180s  # Allow 3 minutes for RDB reload
```

**Current Status** (Jan 12, 2026):
- **Nodes**: 66,187
- **Edges**: 226,095
- **RDB size**: ~5-6GB
- **Reload time**: ~2 minutes (after restart)

**Monitoring Script**:
- `/opt/stacks/graphiti/scripts/monitor_ingestion.sh` (running, PID 790275)
- Logs to: `/tmp/graphiti_monitor.log`
- Interval: 60 seconds

---

## 4. Reranker Service (Optional)

### 4.1 Qwen3-Reranker-4B via vLLM

**Purpose**: Context reranking for search results (PRD #01: Reranker Context Gating)

**Configuration**:
- `OLLAMA_RERANKER_BASE_URL=http://100.81.139.20:11435`
- `OLLAMA_RERANKER_MODEL=dengcao/Qwen3-Reranker-4B:Q5_K_M`
- `RERANKER_URL=http://100.81.139.20:11435`
- `RERANKER_TIMEOUT_MS=10000` (10 seconds)
- `ENABLE_CONTEXT_RERANKING=true`

**Rate Limits**:
- **Self-hosted vLLM**: No external rate limits
- **Throughput**: Limited by GPU availability
- **Timeout**: 10 seconds per request

**Retry Strategy**:
- **Timeout**: Request aborted after 10s
- **Fallback**: If reranker fails, use original ranking (no error)

**Failure Modes**:
1. **Service unavailable**: vLLM container down (graceful degradation)
2. **Timeout**: Reranking takes >10s (use original ranking)
3. **GPU OOM**: Model crashes (service restart required)

**Impact of Failure**: Non-critical (search quality degrades, but no pipeline failure)

---

## 5. Centrality Service (Optional)

### 5.1 Rust Centrality Service

**Purpose**: Compute graph centrality metrics (PageRank, betweenness, degree)

**Configuration** (from `docker-compose.yml`):
- `CENTRALITY_SERVICE_URL=http://graphiti-centrality-rs:3003`
- **Image**: `ghcr.io/oculairmedia/graphiti-centrality-rs:main`
- **Port**: 3003
- **Dependencies**: FalkorDB (reads graph data)

**Rate Limits**:
- **Self-hosted**: No rate limits
- **Performance**: Depends on graph size (currently 66K nodes, 224K edges)
- **Computation time**: Varies (PageRank: ~30s, betweenness: ~2 min on large graphs)

**Retry Strategy**:
- **Client**: HTTP requests from Python API
- **Timeout**: Configurable (default 60s)
- **Retries**: None (computation is expensive, no auto-retry)

**Failure Modes**:
1. **Service unavailable**: Container down (503 error)
2. **Timeout**: Computation exceeds timeout
3. **OOM**: Graph too large for memory (Rust process crashes)

**Current Usage**: 
- **Stage 7: Community Updates** (disabled by default in current pipeline)
- Not used in typical episode ingestion (COMMUNITY_ENABLED=false)
- Used on-demand via API endpoints

**Impact of Failure**: Non-critical (communities not updated, but ingestion proceeds)

---

## 6. Queue Service: Queued (LevelDB)

### 6.1 Configuration

**Purpose**: Task queue for episode ingestion (documented in `current-queue-system.md`)

**Configuration**:
- **Port**: 8093
- **Storage**: LevelDB (disk-backed)
- **Protocol**: HTTP + MessagePack

**Rate Limits**:
- **Capability**: 300K ops/sec (per queued docs)
- **Current load**: ~32 episodes/hour = 0.0089 episodes/sec
- **Headroom**: 33,707,865x current load (effectively unlimited)

**Retry Strategy**:
- **Visibility timeout**: 300s default (20 minutes in current config)
- **Redelivery**: Automatic if worker doesn't ack within timeout
- **Max redeliveries**: No limit (queue-level)

**Failure Modes**:
1. **Service unavailable**: Container down (workers can't poll)
2. **Disk full**: LevelDB can't write (503 error)
3. **Corruption**: LevelDB file corrupted (requires manual recovery)

**Current Status**: Stable, no known issues

---

## 7. Dependency Matrix

### 7.1 Criticality & Failure Impact

| Service | Criticality | Failure Impact | Retry Possible? | Fallback? |
|---------|-------------|----------------|-----------------|-----------|
| **LLM (Chutes)** | CRITICAL | Pipeline stops | Yes | Anthropic |
| **Embeddings (vLLM)** | CRITICAL | Pipeline stops | Yes | None |
| **FalkorDB** | CRITICAL | Pipeline stops | Yes | None |
| **Queued** | CRITICAL | Pipeline stops | N/A | None |
| **Reranker** | LOW | Quality degrades | No | Use original |
| **Centrality** | LOW | Communities stale | No | None |
| **Anthropic (fallback)** | MEDIUM | Cascade fails | Yes | None |

---

### 7.2 Rate Limit Summary

| Service | Rate Limit | Current Usage | Headroom | Limiting Factor |
|---------|------------|---------------|----------|-----------------|
| **GLM-4.5** | Quota-based | 34% (hourly) | 66% | Quota reset |
| **Embeddings** | GPU-limited | ~20 emb/sec | N/A | GPU availability |
| **FalkorDB** | Memory-limited | ~0.5 writes/sec | 1999.5 ops/sec | Memory (8GB) |
| **Anthropic** | 50 req/min | 0 req/min | 50 req/min | API tier |
| **Queued** | 300K ops/sec | 0.009 ops/sec | Effectively unlimited | None |

---

### 7.3 Retry Budget Per Episode

**Total Episode Duration**: ~226 seconds (3.76 minutes)

**Retry Breakdown**:
1. **LLM retries**: 2 retries per call × 20 calls = 40 max retries
2. **Embedding retries**: 3 retries (httpx default) × 5 batches = 15 max retries
3. **FalkorDB retries**: Unlimited (transient errors), 3 max (task-level)
4. **Task-level retries**: 3 max attempts (from `IngestionTask.max_retries`)

**Exponential Backoff**:
- **Task-level**: 10s → 20s → 40s → 80s (capped at 300s)
- **Formula**: `delay = min(300, 10 * (2^retry_count))`

**Total Retry Time** (worst case):
- 3 retries: 10s + 20s + 40s = 70 seconds
- Max delay per retry: 300 seconds
- **Worst case**: 3 × 300s = 15 minutes (task moved to DLQ)

---

## 8. External Dependency Risks

### 8.1 High-Risk Dependencies

**1. LLM Quota Exhaustion**:
- **Risk**: GLM-4.5 quota runs out mid-batch
- **Probability**: Medium (currently at 34%, trending up)
- **Impact**: All workers suspended for 60s, throughput drops 97%
- **Mitigation**: 
  - Monitor quota via API
  - Auto-scale workers down when quota <10%
  - Fallback to Anthropic

**2. FalkorDB Out of Memory**:
- **Risk**: Graph exceeds 8GB runtime limit
- **Probability**: Low (currently 5-6GB, but growing)
- **Impact**: FalkorDB restart, 2-minute downtime, all workers fail
- **Mitigation**:
  - Monitor memory usage (current: 6GB / 8GB = 75%)
  - Increase memory limit to 12GB runtime (24GB container)
  - Implement graph pruning (archive old episodes)

**3. Embedding Service GPU OOM**:
- **Risk**: vLLM runs out of GPU memory
- **Probability**: Low (batch sizes tested)
- **Impact**: Pipeline stops, no fallback
- **Mitigation**:
  - Reduce batch size from 50 to 10
  - Add fallback to OpenAI embeddings (requires API key)

---

### 8.2 Medium-Risk Dependencies

**1. Anthropic Fallback Unavailable**:
- **Risk**: Self-hosted proxy down, API key invalid
- **Probability**: Medium (self-hosted proxy is single point of failure)
- **Impact**: Fallback cascade stops at Chutes, no further recovery
- **Mitigation**:
  - Health check Anthropic proxy
  - Add Ollama as second fallback

**2. Network Partition**:
- **Risk**: Workers lose connection to FalkorDB/LLM
- **Probability**: Low (all services containerized, same network)
- **Impact**: Transient errors, exponential backoff, eventual DLQ
- **Mitigation**:
  - Circuit breaker pattern (not implemented)
  - Faster detection via health checks

---

### 8.3 Low-Risk Dependencies

**1. Reranker Service Down**:
- **Risk**: vLLM reranker container crashes
- **Probability**: Low
- **Impact**: Search quality degrades (no pipeline failure)
- **Mitigation**: None needed (graceful degradation)

**2. Centrality Service Down**:
- **Risk**: Rust service crashes
- **Probability**: Low
- **Impact**: Communities not updated (non-critical)
- **Mitigation**: None needed (disabled by default)

---

## 9. Temporal Migration Considerations

### 9.1 Dependency Wrapping Strategy

**Temporal Activities** should wrap each external dependency:

```python
# Activity 1: LLM Extraction (wraps LLM service)
@activity.defn
async def extract_entities_activity(episode: Episode) -> Entities:
    """Activity wraps LLM client, handles RateLimitError"""
    try:
        return await llm_client.extract_entities(episode)
    except RateLimitError as e:
        # Temporal handles retry with exponential backoff
        raise ApplicationError(
            message=f"Rate limited: {e}",
            type="RateLimitError",
            non_retryable=False  # Temporal will retry
        )

# Activity 2: Embedding Generation (wraps embedding service)
@activity.defn
async def generate_embeddings_activity(texts: List[str]) -> List[List[float]]:
    """Activity wraps embedder, handles GPU OOM"""
    try:
        return await embedder.create_batch(texts)
    except Exception as e:
        if "out of memory" in str(e).lower():
            # Reduce batch size and retry
            raise ApplicationError(
                message="GPU OOM, retry with smaller batch",
                type="GPUOOMError",
                non_retryable=False
            )
        raise

# Activity 3: Graph Persistence (wraps FalkorDB)
@activity.defn
async def save_to_graph_activity(nodes: List[Node], edges: List[Edge]):
    """Activity wraps FalkorDB driver, handles connection errors"""
    try:
        await graph_driver.save_nodes(nodes)
        await graph_driver.save_edges(edges)
    except redis.exceptions.ConnectionError as e:
        # Transient error, Temporal retries
        raise ApplicationError(
            message="FalkorDB connection lost",
            type="ConnectionError",
            non_retryable=False
        )
```

---

### 9.2 Retry Policy Mapping

**Current System** → **Temporal Equivalent**:

| Current | Temporal Retry Policy |
|---------|----------------------|
| LLM retry (2 attempts) | `start_to_close_timeout=300s`, `maximum_attempts=3`, `initial_interval=10s`, `backoff_coefficient=2` |
| Task retry (3 attempts, exponential) | `maximum_attempts=4`, `initial_interval=10s`, `maximum_interval=300s`, `backoff_coefficient=2` |
| Rate limit (60s suspend) | Custom retry policy: `initial_interval=60s`, `maximum_attempts=10` |
| Transient errors (unlimited) | `maximum_attempts=0` (unlimited), `non_retriable_error_types=["PermanentError"]` |

---

### 9.3 Activity Timeout Strategy

**Based on current pipeline timings**:

| Activity | Avg Duration | Timeout | Max Retries | Total Max Time |
|----------|-------------|---------|-------------|----------------|
| Entity Extraction | 86s | 180s | 3 | 540s (9 min) |
| Node Deduplication | 111s | 240s | 3 | 720s (12 min) |
| Edge Extraction | 24s | 60s | 3 | 180s (3 min) |
| Edge Resolution | 15s | 60s | 3 | 180s (3 min) |
| Graph Persistence | 30s | 120s | 3 | 360s (6 min) |
| **Workflow Total** | 226s | 900s | 1 | 900s (15 min) |

**Heartbeat Strategy** (for long-running LLM calls):
- **Heartbeat interval**: Every 30 seconds
- **Heartbeat timeout**: 60 seconds (2× interval)
- **Purpose**: Detect worker crashes mid-LLM call

---

### 9.4 Circuit Breaker Pattern (Recommended)

**Not implemented in current system**, but Temporal enables:

```python
# Circuit breaker for LLM service
circuit_breaker = CircuitBreaker(
    failure_threshold=5,  # Open after 5 consecutive failures
    recovery_timeout=60,  # Try to close after 60s
    expected_exception=RateLimitError
)

@activity.defn
async def extract_entities_activity(episode: Episode) -> Entities:
    async with circuit_breaker:
        return await llm_client.extract_entities(episode)
    # If circuit open, raise ApplicationError immediately (fail fast)
```

**Benefits**:
- Fail fast when service is known to be down
- Prevent thundering herd (all workers retrying simultaneously)
- Automatic recovery detection

---

## 10. Monitoring & Observability Gaps

### 10.1 Current Monitoring (Minimal)

**What's Monitored**:
- Episode count (via monitor script)
- Node/edge counts (via monitor script)
- Worker process health (systemd/Docker)

**What's NOT Monitored**:
- LLM API quota usage (no automated alerts)
- FalkorDB memory usage (no alerts until OOM)
- Embedding service GPU utilization
- Queue depth (no visibility into backlog)
- Retry rates (no aggregated metrics)
- DLQ size (no alerting on failed tasks)
- End-to-end latency (no p95/p99 tracking)

---

### 10.2 Temporal Improvements

**Temporal provides out-of-the-box**:
- **Workflow history**: Full trace of every activity, retry, failure
- **Web UI**: Real-time view of in-flight workflows
- **Metrics**: Success rate, latency, retry count (exportable to Prometheus)
- **Search**: Query workflows by status, error type, time range
- **Alerts**: Configure alerts on workflow failure rate, latency

**Example Temporal Queries**:
```sql
-- Find all failed workflows in last hour
WorkflowStatus = 'Failed' AND StartTime > '2026-01-12T00:00:00Z'

-- Find workflows stuck in rate limit retry loop
WorkflowStatus = 'Running' AND ActivityRetryCount > 5

-- Find slow workflows (>15 min)
WorkflowStatus = 'Running' AND ExecutionDuration > 900s
```

---

## 11. Recommended Actions

### 11.1 Before Migration

**1. Add monitoring for external dependencies**:
- ✅ LLM quota usage (API endpoint exists, poll every 5 min)
- ✅ FalkorDB memory usage (docker stats, alert at 90%)
- ✅ Queue depth (queued API, alert if >1000 tasks)
- ✅ DLQ size (queued API, alert if >10 tasks)

**2. Implement circuit breakers** (in current system):
- LLM service (5 consecutive failures → open for 60s)
- Embedding service (3 consecutive timeouts → open for 30s)

**3. Load test external dependencies**:
- LLM: Simulate 10 workers × 20 calls/episode = 200 concurrent calls
- Embeddings: Test batch sizes up to 100 (find GPU limit)
- FalkorDB: Test write throughput with 20 concurrent workers

---

### 11.2 During Migration

**1. Shadow mode testing**:
- Run Temporal workflows alongside current system (no writes)
- Compare retry counts, latency, error rates
- Validate activity timeouts are appropriate

**2. Canary rollout**:
- Route 1% of episodes to Temporal
- Monitor external service impact (no change expected)
- Increase to 10%, 50%, 100% over 1 week

**3. Rollback plan**:
- Keep current system running for 2 weeks
- Ability to route traffic back to old system (feature flag)

---

### 11.3 After Migration

**1. Tune retry policies** based on production data:
- Adjust `initial_interval` to match actual recovery times
- Set `maximum_attempts` based on acceptable latency

**2. Add custom activity metrics**:
- Export LLM token usage to Prometheus
- Export embedding batch size histogram
- Export FalkorDB query latency

**3. Implement adaptive rate limiting**:
- Detect LLM quota exhaustion (429 errors)
- Automatically reduce worker count (Temporal activity worker scaling)
- Auto-resume when quota resets

---

## 12. Summary

### 12.1 Critical Dependencies (Pipeline Stops if Failed)
1. **LLM Service (Chutes/GLM-4.5)**: 15-25 calls/episode, quota-limited, has Anthropic fallback
2. **Embedding Service (vLLM/Qwen3)**: 5-10 batches/episode, GPU-limited, NO fallback
3. **FalkorDB**: All graph operations, memory-limited (8GB), NO fallback
4. **Queued**: Task queue, disk-limited, NO fallback

### 12.2 Non-Critical Dependencies (Graceful Degradation)
1. **Reranker (vLLM/Qwen3-Reranker-4B)**: Search quality feature, timeout 10s, falls back to original ranking
2. **Centrality (Rust service)**: Community updates, disabled by default, not used in typical ingestion

### 12.3 Key Risks for Temporal Migration
1. **LLM quota exhaustion**: Need monitoring and auto-scaling
2. **FalkorDB OOM**: Need memory monitoring and alerting
3. **No embedding fallback**: Need OpenAI embeddings as backup
4. **Activity timeout tuning**: Need production data to set appropriate timeouts

### 12.4 Temporal Advantages
1. **Better retry control**: Per-activity retry policies (vs. per-task)
2. **Better observability**: Web UI shows all retries, failures, timing
3. **Circuit breakers**: Fail fast when service is down (prevent cascading failures)
4. **Activity-level parallelism**: Extract entities while deduplicating nodes (current system is sequential)
5. **Heartbeats**: Detect worker crashes mid-activity (current system has no heartbeat)

---

## 13. Next Steps

**Immediate** (this analysis session):
- ✅ Catalog external dependencies → **DONE**
- ⏳ Document error handling & retry mechanisms (Task #5)
- ⏳ Create migration phases document (Task #6)

**Short-term** (before migration):
- Add monitoring for LLM quota, FalkorDB memory, queue depth
- Load test external dependencies (find breaking points)
- Implement circuit breakers in current system (validate pattern)

**Medium-term** (during migration):
- Shadow mode testing (compare Temporal vs. current system)
- Tune activity timeouts and retry policies
- Canary rollout (1% → 10% → 50% → 100%)

**Long-term** (after migration):
- Add adaptive rate limiting (auto-scale workers based on quota)
- Add embedding fallback (OpenAI API)
- Optimize activity parallelism (run extraction + deduplication concurrently)

---

**Document Status**: ✅ Complete (Task #4 of 8)

**Next Document**: `error-handling-retry-mechanisms.md` (Task #5)
