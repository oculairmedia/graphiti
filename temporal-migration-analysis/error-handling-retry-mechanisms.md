# Error Handling & Retry Mechanisms

## Overview
Graphiti's ingestion pipeline implements a multi-layered error handling strategy with exponential backoff, error classification, and dead letter queue (DLQ) management. Understanding these mechanisms is critical for designing an equivalent Temporal migration.

---

## Error Classification System

### 1. Error Hierarchy

```
Exception (Python base)
│
├── RateLimitError (worker.py:34)
│   ├── Used for: LLM/API rate limits exceeded
│   ├── Attributes: group_id, retry_after (default: 60s)
│   └── Handling: Suspend group, return to queue
│
├── TransientError (worker.py:43)
│   ├── Used for: Temporary failures (network, connection)
│   ├── Examples: ConnectionError, TimeoutError
│   └── Handling: Retry with exponential backoff
│
├── PermanentError (worker.py:49)
│   ├── Used for: Unrecoverable failures
│   ├── Examples: Invalid UUID, unknown task type, malformed data
│   └── Handling: Move to DLQ immediately (no retries)
│
└── GraphitiError (errors.py)
    ├── NodeNotFoundError
    ├── EdgeNotFoundError
    ├── SearchRerankerError
    ├── EntityTypeValidationError
    ├── GroupIdValidationError
    └── DuplicateEdgeError
```

### 2. Error Classification Rules (worker.py:865-886)

```python
# Permanent errors (no retries):
if isinstance(error, (PermanentError, NodeNotFoundError, EdgeNotFoundError)):
    await self._move_to_dlq(task, error)
    await self.queue.delete(message_id, poll_tag)
    # No further retries

# Transient errors or retries remaining:
elif isinstance(error, TransientError) or task.retry_count < task.max_retries:
    delay = min(300, 10 * (2**task.retry_count))
    await self.queue.update(message_id, poll_tag, delay)
    # Task returns to queue with exponential backoff

# Max retries exceeded:
else:
    await self._move_to_dlq(task, error)
    await self.queue.delete(message_id, poll_tag)
    # Exhausted retries, move to DLQ
```

**Key Insight**: The error classification is **binary**:
- **Permanent** → Immediate DLQ (NodeNotFoundError, EdgeNotFoundError, PermanentError)
- **Retryable** → Exponential backoff (TransientError, all other errors up to max_retries)

---

## Retry Mechanisms

### 1. Task-Level Retries (Worker)

**Configuration** (queue_client.py:48):
```python
@dataclass
class IngestionTask:
    retry_count: int = 0
    max_retries: int = 3  # Default: 3 attempts total (initial + 2 retries)
    visibility_timeout: int = 300  # 5 minutes
```

**Exponential Backoff Formula** (worker.py:877):
```python
delay = min(300, 10 * (2**task.retry_count))
```

**Backoff Schedule**:
| Attempt | retry_count | Delay (seconds) | Cumulative Time |
|---------|-------------|-----------------|-----------------|
| Initial | 0 | 0 | 0s |
| Retry 1 | 1 | 10 × 2^1 = 20s | 20s |
| Retry 2 | 2 | 10 × 2^2 = 40s | 60s |
| Retry 3 | 3 | 10 × 2^3 = 80s | 140s |
| DLQ | 4 | N/A | Task moved to DLQ |

**Max Delay**: Capped at 300 seconds (5 minutes)

**Total Retry Window**: ~140 seconds (2.3 minutes) + original execution time

---

### 2. Rate Limit Retries (Special Case)

**Configuration** (worker.py:37-40):
```python
class RateLimitError(Exception):
    def __init__(self, group_id: str, retry_after: int = 60):
        self.group_id = group_id
        self.retry_after = retry_after  # Default: 60 seconds
```

**Handling** (worker.py:324-330):
```python
except RateLimitError as e:
    # Return to queue with adaptive backoff
    retry_after = min(300, e.retry_after * (2**task.retry_count))
    await self.queue.update(message_id, poll_tag, retry_after)
    self.metrics.record_retry()
    logger.warning(f'Rate limited task {task.id}, retry in {retry_after}s')
```

**Rate Limit Backoff Schedule**:
| Attempt | Delay | Cumulative |
|---------|-------|------------|
| Retry 1 | 60s | 60s |
| Retry 2 | 60 × 2 = 120s | 180s |
| Retry 3 | 60 × 4 = 240s | 420s |
| Retry 4 | 60 × 8 = 480s (capped at 300s) | 720s |

**Group Suspension** (worker.py:206):
```python
self.rate_limiter.suspend_group(group_id, 60)  # 60 second suspension
```

**Key Difference**: Rate limit errors use `retry_after` from the exception (default 60s), not the standard 10s base.

---

### 3. LLM Client-Level Retries

**Configuration** (openai_base_client.py:50):
```python
class BaseOpenAIClient(LLMClient):
    MAX_RETRIES: ClassVar[int] = 2  # Client-level retries
```

**Total Retry Chain** (LLM call example):
1. **Client retry 1**: BaseOpenAIClient catches exception, retries (0 delay)
2. **Client retry 2**: BaseOpenAIClient catches exception, retries (0 delay)
3. **Client gives up**: Raises exception to worker
4. **Worker retry 1**: Task retries with 20s delay
5. **Worker retry 2**: Task retries with 40s delay
6. **Worker retry 3**: Task retries with 80s delay
7. **DLQ**: Task moved to dead letter queue

**Total Attempts**: 2 (client) + 3 (worker) = **5 total attempts** before DLQ

**Total Time**: ~140s (worker backoff) + 5 × LLM_latency (typically 5 × 5s = 25s) = **~165 seconds**

---

### 4. Resilient Ingestion Wrapper (Optional)

**Purpose**: Checkpoint progress to avoid losing work on partial failures

**Location**: `graphiti_core/utils/resilient_ingestion.py`

**Configuration** (resilient_ingestion.py:137-140):
```python
effective_max_retries = int(os.getenv('RESILIENT_RETRY_MAX_ATTEMPTS', '3'))
effective_base_delay = float(os.getenv('RESILIENT_RETRY_BASE_DELAY', '2.0'))
effective_max_delay = float(os.getenv('RESILIENT_RETRY_MAX_DELAY', '60.0'))
effective_exponential_base = float(os.getenv('RESILIENT_RETRY_EXPONENTIAL_BASE', '2.0'))
```

**Retry Formula**:
```python
delay = min(effective_base_delay * (effective_exponential_base ** attempt), effective_max_delay)
```

**Backoff Schedule** (with defaults):
| Attempt | Delay | Cumulative |
|---------|-------|------------|
| Initial | 0s | 0s |
| Retry 1 | 2.0 × 2^0 = 2s | 2s |
| Retry 2 | 2.0 × 2^1 = 4s | 6s |
| Retry 3 | 2.0 × 2^2 = 8s | 14s |
| Fail | N/A | Exception raised |

**Jitter** (resilient_ingestion.py:162-164):
```python
if jitter:
    import random
    delay += random.uniform(0, delay * 0.1)  # Add 0-10% random jitter
```

**Purpose**: Prevent thundering herd problem when many workers retry simultaneously

---

### 5. Checkpointing System

**State Tracking** (resilient_ingestion.py:33-64):
```python
class ResilientIngestionState(BaseModel):
    episode_id: str
    group_id: str
    
    # Stage completion flags
    nodes_extracted: bool = False
    nodes_resolved: bool = False
    edges_extracted: bool = False
    episode_created: bool = False
    
    # Cached results from completed stages
    extracted_nodes: Optional[list[dict[str, Any]]] = None
    resolved_nodes: Optional[list[dict[str, Any]]] = None
    extracted_edges: Optional[list[dict[str, Any]]] = None
    
    # Additional cached data
    uuid_map: Optional[dict[str, str]] = None
    node_duplicates: Optional[list[dict[str, Any]]] = None
    
    # Retry tracking
    nodes_extract_attempts: int = 0
    nodes_resolve_attempts: int = 0
    edges_extract_attempts: int = 0
```

**How It Works**:
1. **Before each stage**: Check if stage already completed (via `nodes_extracted`, `nodes_resolved`, etc.)
2. **If completed**: Skip stage, use cached results from `extracted_nodes`, `resolved_nodes`, etc.
3. **If not completed**: Execute stage, cache results, set completion flag
4. **On failure**: State persists in memory (`IngestionProgressCache`), next retry skips completed stages

**Example Flow** (with failure at edge extraction):
```
Attempt 1:
  ✅ Extract nodes (86s) → Cache results, set nodes_extracted=True
  ✅ Resolve nodes (111s) → Cache results, set nodes_resolved=True
  ❌ Extract edges (24s) → Failure at 20s, state persisted

Attempt 2 (after 20s backoff):
  ⏭️  Extract nodes → SKIPPED (nodes_extracted=True, use cached data)
  ⏭️  Resolve nodes → SKIPPED (nodes_resolved=True, use cached data)
  🔄 Extract edges → RETRY from beginning (no checkpoint within stage)
```

**Limitations**:
- Checkpointing is **stage-level**, not sub-stage
- If edge extraction fails after 20s, the entire 20s of work is lost
- Checkpoints are **in-memory only** (lost if worker crashes)

---

## Dead Letter Queue (DLQ)

### 1. DLQ Structure

**Implementation** (worker.py:888-904):
```python
async def _move_to_dlq(self, task: IngestionTask, error: Exception):
    """Move failed task to dead letter queue."""
    task.metadata['error'] = str(error)
    task.metadata['error_type'] = type(error).__name__
    task.metadata['failed_at'] = utc_now().isoformat()
    task.metadata['worker_id'] = self.worker_id
    
    # Push to DLQ with no expiry
    await self.queue.push([task], queue_name='dead_letter')
    
    logger.error(f'Task {task.id} moved to dead letter queue: {error}')
```

**DLQ Metadata**:
- `error`: Error message string
- `error_type`: Exception class name (e.g., "NodeNotFoundError")
- `failed_at`: ISO 8601 timestamp
- `worker_id`: Worker that encountered the failure

**DLQ Queue Name**: `"dead_letter"` (separate queue in queued service)

**Expiry**: None (messages persist indefinitely)

---

### 2. When Tasks Move to DLQ

**Trigger Conditions**:
1. **Permanent Errors**: Immediate DLQ (no retries)
   - `PermanentError`: Invalid UUID, unknown task type, malformed data
   - `NodeNotFoundError`: Referenced node doesn't exist in graph
   - `EdgeNotFoundError`: Referenced edge doesn't exist in graph

2. **Max Retries Exceeded**: After 3 failed attempts (default)
   - Includes transient errors that didn't resolve within retry window
   - Examples: Connection timeouts, temporary API outages

**Code Path** (worker.py:867-886):
```python
if isinstance(error, (PermanentError, NodeNotFoundError, EdgeNotFoundError)):
    await self._move_to_dlq(task, error)  # Immediate DLQ
    
elif isinstance(error, TransientError) or task.retry_count < task.max_retries:
    # Retry with backoff
    
else:
    await self._move_to_dlq(task, error)  # Exhausted retries
```

---

### 3. DLQ Monitoring & Alerting

**Current State**: **NO AUTOMATED ALERTING**

**Available Operations**:
- View DLQ size: `queue.get_stats('dead_letter')` → Returns count
- List DLQ messages: `queue.poll('dead_letter', count=100, timeout=0)`
- Replay DLQ message: `queue.push([task], queue_name='ingestion')` (manual)

**Gaps**:
- ❌ No alerts when DLQ size exceeds threshold
- ❌ No automatic retry of DLQ messages
- ❌ No DLQ expiration (messages persist forever)
- ❌ No DLQ categorization (all failures lumped together)

**Recommended Monitoring** (for Temporal migration):
- Alert when DLQ size > 10 messages
- Daily DLQ digest email (last 24 hours)
- Categorize by error type (PermanentError vs. exhausted retries)

---

## Rate Limiting System

### 1. Rate Limiter Architecture

**Implementation** (worker.py:55-77):
```python
@dataclass
class RateLimitWindow:
    """Sliding window for rate limiting"""
    requests: list[float]  # Timestamps of requests
    limit: int             # Max requests per window
    window_seconds: int    # Window duration
    
    def is_allowed(self) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds
        
        # Remove old requests
        self.requests = [t for t in self.requests if t > cutoff]
        
        # Check if under limit
        return len(self.requests) < self.limit
```

**Configuration** (worker.py:138-145):
```python
class RateLimiter:
    def __init__(
        self,
        global_limit: int = 100,      # Requests per second (global)
        group_limit: int = 10,        # Requests per second (per group)
        window_seconds: int = 1,      # Sliding window size
    ):
        self.global_window = RateLimitWindow([], global_limit, window_seconds)
        self.group_windows: Dict[str, RateLimitWindow] = {}
        self.suspended_groups: Dict[str, float] = {}  # group_id -> unsuspend_time
```

---

### 2. Rate Limiting Behavior

**Check Order** (worker.py:189-207):
1. **Check global rate limit**: 100 req/sec (all workers combined)
2. **Check group rate limit**: 10 req/sec per group_id
3. **Check group suspension**: If group suspended, raise RateLimitError

**Code Path**:
```python
async def acquire(self, group_id: Optional[str] = None):
    # Check global rate limit
    if not self.global_window.is_allowed():
        raise RateLimitError('global', retry_after=1)
    
    # Check group rate limit
    if group_id:
        if not group_window.is_allowed():
            remaining = self._get_remaining_time(group_id)
            if remaining > 0:
                raise RateLimitError(group_id, retry_after=remaining)
            else:
                # Suspend group for exponential backoff
                self.suspend_group(group_id, 60)
                raise RateLimitError(group_id, retry_after=60)
    
    # Record request
    self.global_window.record_request()
    if group_id:
        group_window.record_request()
```

**Key Insight**: Rate limits are **per-worker**, not global across all workers!
- 2 workers × 100 req/sec = **200 req/sec actual limit**
- 2 workers × 10 req/sec/group = **20 req/sec per group actual limit**

---

### 3. Group Suspension

**Purpose**: Prevent rapid retries when a group is rate-limited

**Suspension Logic** (worker.py:174-176):
```python
def suspend_group(self, group_id: str, duration: int):
    """Suspend a group for rate limiting"""
    self.suspended_groups[group_id] = time.time() + duration
```

**Unsuspension** (worker.py:158-163):
```python
def _is_group_suspended(self, group_id: str) -> bool:
    if group_id in self.suspended_groups:
        if time.time() < self.suspended_groups[group_id]:
            return True
        else:
            del self.suspended_groups[group_id]
    return False
```

**Duration**: 60 seconds (hardcoded)

**Effect**: All tasks for that group_id are rejected with `RateLimitError` for 60 seconds

---

## Error Recovery Strategies

### 1. Idempotency Protection

**Episode-Level** (graphiti.py):
```python
# Check if episode already processed
existing_episodes = await self.retrieve_episodes(group_ids=[group_id], reference_time=valid_at)
if any(ep.name == name for ep in existing_episodes):
    logger.info(f'Episode {name} already exists, skipping')
    return  # No-op, idempotent
```

**Node-Level** (worker.py:647):
```python
except Exception as e:
    if 'duplicate' in str(e).lower():
        # Duplicate entity is not an error
        logger.debug(f'Entity already exists: {payload.get("name")}')
    else:
        raise
```

**Result**: Re-running the same episode is safe (no duplicate data)

---

### 2. Connection Error Handling

**Detection** (worker.py:522-525):
```python
except Exception as e:
    if 'rate limit' in str(e).lower():
        raise RateLimitError(effective_group_id, retry_after=60)
    raise TransientError(f'Connection error: {e}')
```

**Result**: Connection errors are classified as `TransientError` → retry with backoff

---

### 3. LLM-Specific Errors

**Rate Limit Detection** (openai_base_client.py + cerebras_client.py):
```python
except openai.RateLimitError as e:
    raise RateLimitError from e

# Cerebras (string matching)
if 'rate_limit' in str(e).lower():
    raise RateLimitError(f'Cerebras rate limit exceeded: {e}')
```

**Refusal Error** (openai_base_client.py):
```python
except RefusalError as e:
    # Don't retry on refusal - model refused to respond (safety filters)
    logger.error(f"LLM refused to respond: {e}")
    raise e
```

**Empty Response** (openai_base_client.py):
```python
except EmptyResponseError as e:
    # Don't retry on empty response - likely permanent issue
    logger.error(f"LLM returned empty response: {e}")
    raise e
```

**Result**: LLM-specific errors have custom handling (rate limit → retry, refusal/empty → fail)

---

## Failure Modes & Recovery

### 1. Worker Crash Mid-Task

**Scenario**: Worker process crashes while processing a task (e.g., OOM, SIGKILL)

**Recovery**:
1. Task has **visibility timeout** of 300 seconds (5 minutes) in queue
2. After 300s without ack/delete, task becomes visible again
3. Another worker polls and receives the task
4. Task's `retry_count` is preserved (incremented from previous attempt)
5. If retry_count < max_retries, task is processed again

**Idempotency**: Episode UUID check prevents duplicate work if task partially succeeded

**Checkpoint Loss**: Resilient ingestion checkpoints are in-memory → lost on crash

---

### 2. FalkorDB Connection Loss

**Scenario**: FalkorDB container restarts, all connections severed

**Detection** (worker.py):
```python
except Exception as e:
    # Connection errors are caught generically
    raise TransientError(f'Connection error: {e}')
```

**Recovery**:
1. Task fails with `TransientError`
2. Worker retries with 20s backoff (first retry)
3. FalkorDB typically reloads RDB in ~2 minutes
4. Subsequent retry succeeds

**Result**: ~2 minute delay, but task completes successfully

---

### 3. LLM Quota Exhaustion

**Scenario**: GLM-4.5 hourly quota runs out (currently at 34%)

**Detection** (LLM client):
```python
except openai.RateLimitError as e:
    raise RateLimitError from e
```

**Recovery**:
1. Worker raises `RateLimitError(group_id, retry_after=60)`
2. Group suspended for 60 seconds
3. Task returns to queue with 60s × 2^retry_count delay
4. **Fallback**: If `ENABLE_FALLBACK=true`, FallbackClient cascades to Anthropic
5. If quota still exhausted after max retries, task moves to DLQ

**Current Configuration**:
- Fallback enabled: `ENABLE_FALLBACK=true`
- Anthropic has separate quota (50 req/min)

**Result**: Pipeline continues using Anthropic until GLM-4.5 quota resets

---

### 4. Embedding Service GPU OOM

**Scenario**: vLLM embedding service runs out of GPU memory

**Detection**: Service returns 503 error or times out

**Recovery**:
1. Worker catches exception (likely `httpx.HTTPStatusError` or `TimeoutError`)
2. Classified as retryable error (not explicitly TransientError, but retry_count < max_retries)
3. Task retries with exponential backoff
4. If vLLM container auto-restarts (Docker `restart: unless-stopped`), service recovers
5. Subsequent retry succeeds

**Current Gap**: **NO FALLBACK** for embeddings (critical path failure)

**Recommended**: Add OpenAI embeddings fallback (requires `OPENAI_API_KEY`)

---

## Metrics & Observability

### 1. Worker Metrics

**Tracked Metrics** (worker.py:108-131):
```python
@dataclass
class WorkerMetrics:
    tasks_processed: int = 0
    tasks_succeeded: int = 0
    tasks_failed: int = 0
    tasks_retried: int = 0
    
    total_processing_time: float = 0.0
    total_wait_time: float = 0.0
    
    rate_limits_hit: int = 0
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            'tasks_processed': self.tasks_processed,
            'tasks_succeeded': self.tasks_succeeded,
            'tasks_failed': self.tasks_failed,
            'tasks_retried': self.tasks_retried,
            'success_rate': self.tasks_succeeded / max(1, self.tasks_processed),
            'avg_processing_time': self.total_processing_time / max(1, self.tasks_succeeded),
            'total_wait_time': self.total_wait_time,
            'rate_limits_hit': self.rate_limits_hit,
        }
```

**Exposure**: `worker.get_metrics()` returns dict (not exported to Prometheus/Grafana)

---

### 2. Queue Metrics

**Available** (queue_client.py):
```python
class QueueMetrics:
    def get_stats(self, queue_name: str) -> Dict[str, int]:
        # Returns: size, visible_count, invisible_count
        return self.client.get_stats(queue_name)
```

**Current Usage**: Manual polling via API, no automated monitoring

---

### 3. Observability Gaps

**NOT Currently Tracked**:
- ❌ Retry distribution (how many tasks fail 1×, 2×, 3× before success/DLQ?)
- ❌ DLQ growth rate (how fast is DLQ filling up?)
- ❌ Error type distribution (what % are PermanentError vs. TransientError?)
- ❌ Stage-level failure rates (which stage fails most often?)
- ❌ LLM API latency (p50, p95, p99)
- ❌ End-to-end latency per episode (time from enqueue to completion)

**Temporal Improvements**:
- ✅ Workflow history: Full trace of every activity, retry, failure
- ✅ Web UI: Real-time view of in-flight workflows
- ✅ Metrics: Success rate, latency, retry count (exportable to Prometheus)
- ✅ Search: Query workflows by status, error type, time range
- ✅ Alerts: Configure alerts on workflow failure rate, latency

---

## Temporal Migration Mapping

### 1. Error Classification → Temporal Error Types

| Current System | Temporal Equivalent |
|----------------|---------------------|
| `PermanentError` | `ApplicationError(non_retryable=True)` |
| `NodeNotFoundError` | `ApplicationError(type="NodeNotFoundError", non_retryable=True)` |
| `EdgeNotFoundError` | `ApplicationError(type="EdgeNotFoundError", non_retryable=True)` |
| `TransientError` | `ApplicationError(non_retryable=False)` (default) |
| `RateLimitError` | `ApplicationError(type="RateLimitError", non_retryable=False)` with custom retry policy |

**Temporal Advantage**: Explicit `non_retryable` flag (vs. implicit classification via exception type)

---

### 2. Retry Policies → Temporal Retry Policy

**Current System**:
```python
retry_count < max_retries:  # max_retries = 3
    delay = min(300, 10 * (2**task.retry_count))
```

**Temporal Equivalent**:
```python
@activity.defn(
    retry_policy=RetryPolicy(
        initial_interval=timedelta(seconds=10),
        backoff_coefficient=2.0,
        maximum_interval=timedelta(seconds=300),
        maximum_attempts=4,  # Initial + 3 retries
        non_retriable_error_types=["PermanentError", "NodeNotFoundError", "EdgeNotFoundError"]
    )
)
async def extract_entities_activity(episode: Episode) -> Entities:
    ...
```

**Rate Limit Retry Policy**:
```python
@activity.defn(
    retry_policy=RetryPolicy(
        initial_interval=timedelta(seconds=60),
        backoff_coefficient=2.0,
        maximum_interval=timedelta(seconds=300),
        maximum_attempts=10,  # More attempts for rate limit
    )
)
```

---

### 3. Checkpointing → Temporal Workflow State

**Current System**: In-memory checkpoints (lost on crash)

**Temporal**: Workflow state persisted to database

```python
@workflow.defn
class IngestEpisodeWorkflow:
    @workflow.run
    async def run(self, episode: Episode) -> None:
        # Stage 1: Extract entities
        entities = await workflow.execute_activity(
            extract_entities_activity,
            episode,
            start_to_close_timeout=timedelta(seconds=180)
        )
        # State automatically persisted: entities stored in workflow history
        
        # Stage 2: Deduplicate nodes (uses entities from Stage 1)
        nodes = await workflow.execute_activity(
            deduplicate_nodes_activity,
            entities,
            start_to_close_timeout=timedelta(seconds=240)
        )
        # State automatically persisted: nodes stored in workflow history
        
        # If worker crashes here, workflow resumes from this point
        # No need to re-run extract_entities or deduplicate_nodes!
```

**Temporal Advantage**: Automatic checkpointing between activities (vs. manual checkpointing within stages)

---

### 4. DLQ → Temporal Failed Workflows

**Current System**: Separate `dead_letter` queue in queued service

**Temporal**: Failed workflows searchable via Web UI

```sql
-- Find all failed workflows in last 24 hours
WorkflowStatus = 'Failed' AND StartTime > '2026-01-11T00:00:00Z'

-- Find workflows that failed due to NodeNotFoundError
WorkflowStatus = 'Failed' AND ExecutionError LIKE '%NodeNotFoundError%'

-- Find workflows that exhausted retries
WorkflowStatus = 'Failed' AND ActivityRetryCount >= 3
```

**Temporal Advantage**: 
- ✅ Rich query language (vs. manual DLQ polling)
- ✅ Categorization by error type (vs. flat DLQ)
- ✅ Replay capability (re-run failed workflow from Web UI)

---

## Performance & Scaling Considerations

### 1. Retry Overhead

**Current System**:
- **Avg episode**: 226 seconds (no retries)
- **With 1 retry**: 226s + 20s (backoff) + 226s = **472 seconds** (2.1× slower)
- **With 3 retries**: 226s + 20s + 40s + 80s + 3×226s = **1044 seconds** (4.6× slower)

**Worst Case Scenario** (all stages fail and retry):
- Stage 2 (node dedup) fails 3 times: 111s × 4 attempts + 140s (backoff) = **584 seconds**
- Stage 1 (entity extract) fails 3 times: 86s × 4 attempts + 140s (backoff) = **484 seconds**
- **Total**: ~1068 seconds (**17.8 minutes** for a single episode)

**Mitigation**:
- Most retries succeed on first attempt (transient errors are rare)
- Rate limit errors are infrequent (currently at 34% quota)
- Checkpointing prevents re-running completed stages

---

### 2. DLQ Growth Rate

**Observation** (from monitor log):
- **Current throughput**: ~36 episodes/hour
- **Failure rate**: Unknown (no metrics)
- **Estimated failure rate**: ~1-2% (based on typical production systems)
- **DLQ growth**: ~0.4-0.7 episodes/hour (if 1-2% failure rate)

**Projected DLQ Size**:
- **Daily**: 0.5 episodes/hour × 24 hours = **12 episodes/day**
- **Weekly**: 12 × 7 = **84 episodes/week**
- **Monthly**: 12 × 30 = **360 episodes/month**

**Alert Threshold**: DLQ size > 50 episodes (indicates systemic issue)

---

### 3. Rate Limiter Contention

**Current System**:
- Rate limiter is **per-worker** (no coordination)
- 2 workers × 100 req/sec = **200 req/sec actual limit** (not 100)
- Scaling to 10 workers → **1000 req/sec actual limit**

**Problem**: Uncoordinated rate limiting leads to quota exhaustion

**Temporal Advantage**: 
- Temporal workers can share rate limiter state (via database or Redis)
- More accurate global rate limiting
- Better quota management

---

## Recommendations for Temporal Migration

### 1. Error Handling

**Keep**:
- ✅ Error classification (Permanent vs. Transient)
- ✅ Exponential backoff formula (10s base, 2× multiplier, 300s cap)
- ✅ Idempotency checks (episode UUID, duplicate detection)

**Improve**:
- ⚠️ Add explicit `non_retryable` error types (vs. implicit classification)
- ⚠️ Add per-activity retry policies (vs. per-task)
- ⚠️ Add custom retry policy for rate limit errors (60s base, not 10s)

**Add**:
- ➕ Circuit breaker pattern (fail fast when service is down)
- ➕ Adaptive rate limiting (reduce worker count based on quota usage)
- ➕ DLQ alerting (email/Slack when DLQ size > threshold)

---

### 2. Checkpointing

**Current Limitation**: In-memory checkpoints lost on worker crash

**Temporal Solution**: Workflow state persisted between activities

**Migration Strategy**:
1. **Phase 1**: No checkpointing (rely on Temporal's automatic checkpoints between activities)
2. **Phase 2**: Add sub-activity checkpointing if stages are very long (>5 minutes)
3. **Phase 3**: Use Temporal's `workflow.execute_local_activity()` for fast operations (no history overhead)

---

### 3. Observability

**Current Gap**: Minimal metrics, no alerting

**Temporal Solution**: Built-in metrics, Web UI, search

**Action Items**:
1. **Export Temporal metrics to Prometheus**:
   - Workflow success rate
   - Activity retry count
   - End-to-end latency (p50, p95, p99)
   - DLQ size (failed workflow count)

2. **Set up alerts**:
   - DLQ size > 10 workflows
   - Workflow failure rate > 5%
   - p99 latency > 15 minutes

3. **Create dashboards**:
   - Real-time throughput (episodes/hour)
   - Retry distribution (how many retries before success?)
   - Error type breakdown (PermanentError vs. TransientError)

---

### 4. Testing Strategy

**Before Migration**:
1. **Load test**: Simulate 10× worker count (20 workers) to find breaking points
2. **Chaos test**: Kill workers mid-task, restart FalkorDB, exhaust LLM quota
3. **Benchmark**: Measure current retry rates, DLQ growth, latency

**During Migration**:
1. **Shadow mode**: Run Temporal workflows alongside current system (no writes)
2. **Compare metrics**: Retry counts, latency, error rates
3. **Tune retry policies**: Adjust `initial_interval`, `maximum_attempts` based on production data

**After Migration**:
1. **Monitor DLQ**: Ensure DLQ growth rate stays below 1 episode/hour
2. **Tune timeouts**: Adjust activity timeouts based on p99 latency
3. **Optimize parallelism**: Run independent activities concurrently (extract + deduplicate)

---

## Summary

### Key Findings

1. **Error Classification**: Binary system (Permanent vs. Retryable) with 3 max retries
2. **Retry Strategy**: Exponential backoff (10s → 20s → 40s → 80s, capped at 300s)
3. **Rate Limiting**: Per-worker (uncoordinated), 100 req/sec global, 10 req/sec/group
4. **Checkpointing**: Stage-level (in-memory), lost on worker crash
5. **DLQ**: No automated alerting, messages persist indefinitely

### Temporal Advantages

1. **Automatic checkpointing**: Workflow state persisted between activities (vs. in-memory)
2. **Rich retry policies**: Per-activity configuration (vs. per-task global)
3. **Better observability**: Web UI, metrics, search (vs. manual polling)
4. **DLQ replay**: Re-run failed workflows from Web UI (vs. manual re-enqueue)
5. **Circuit breakers**: Fail fast when service is down (not implemented in current system)

### High-Priority Action Items

1. ✅ Add DLQ monitoring and alerting (>10 tasks threshold)
2. ✅ Add embedding service fallback (OpenAI API)
3. ✅ Implement circuit breaker for LLM service (5 consecutive failures → 60s open)
4. ✅ Export worker metrics to Prometheus (success rate, retry count, latency)
5. ✅ Load test at 10× current worker count (find breaking points)

---

**Document Status**: ✅ Complete (Task #5 of 8)

**Next Document**: `migration-phases.md` (Task #6)
