# Worker Pool & Concurrency Model

## Overview
The Graphiti ingestion system uses a **worker pool** pattern with independent workers polling a shared queue. Workers coordinate via the queue's visibility timeout mechanism, not via direct communication.

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                     WorkerService                            │
│  (Orchestration Layer - worker_service.py)                  │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ├─ Initializes: QueueClient, Graphiti, WorkerPool
                      └─ Handles: SIGINT/SIGTERM for graceful shutdown
                      
┌─────────────────────┴───────────────────────────────────────┐
│                     WorkerPool                               │
│  (Pool Manager - worker.py:914-962)                         │
│                                                              │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐           │
│  │  Worker 0  │  │  Worker 1  │  │  Worker N  │           │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘           │
└────────┼────────────────┼────────────────┼──────────────────┘
         │                │                │
         └────────────────┴────────────────┴─────────────────┐
                                                               │
┌──────────────────────────────────────────────────────────────┤
│                   Queued Service (LevelDB)                   │
│  - Shared queue: "ingestion"                                 │
│  - Visibility timeout prevents duplicate processing          │
│  - Poll returns different messages to each worker            │
└──────────────────────────────────────────────────────────────┘
```

## WorkerPool Class

**Location**: `/opt/stacks/graphiti/graphiti_core/ingestion/worker.py:914-962`

### Initialization

```python
class WorkerPool:
    def __init__(
        self,
        queue_client: QueuedClient,
        graphiti: Graphiti,
        worker_count: int = 4,
        batch_size: int = 1,
    ):
        self.queue = queue_client
        self.graphiti = graphiti
        self.worker_count = worker_count
        self.batch_size = batch_size
        self.workers: list[IngestionWorker] = []
```

**Configuration** (from environment):
- `WORKER_COUNT=2` (default: 4) - Number of parallel workers
- `BATCH_SIZE=10` (default: 1) - Messages polled per worker per iteration
- `POLL_INTERVAL=1.0` (default: 1.0) - Seconds between polls if queue empty

**Current Production Settings**:
- Worker count: 2
- Batch size: 1 (sequential processing within worker)
- Total parallelism: 2 concurrent episodes

### Lifecycle

#### 1. Start (Lines 932-944)
```python
async def start(self):
    """Start all workers in the pool"""
    for i in range(self.worker_count):
        worker = IngestionWorker(
            worker_id=f'worker_{i}',
            queue_client=self.queue,
            graphiti=self.graphiti,
            batch_size=self.batch_size,
        )
        await worker.start()
        self.workers.append(worker)
    
    logger.info(f'Started worker pool with {self.worker_count} workers')
```

**Behavior**:
- Creates N independent workers
- Each worker gets unique ID (`worker_0`, `worker_1`, etc.)
- All workers share the same `queue_client` and `graphiti` instances
- Workers start immediately and begin polling

#### 2. Stop (Lines 946-954)
```python
async def stop(self):
    """Stop all workers gracefully"""
    logger.info('Stopping worker pool...')
    
    # Stop all workers concurrently
    await asyncio.gather(
        *[worker.stop() for worker in self.workers],
        return_exceptions=True
    )
    
    self.workers.clear()
    logger.info('Worker pool stopped')
```

**Graceful Shutdown**:
- Waits for all workers to finish current task
- `return_exceptions=True` prevents one worker's error from blocking others
- Workers complete in-flight episodes before stopping

---

## IngestionWorker Class

**Location**: `/opt/stacks/graphiti/graphiti_core/ingestion/worker.py:215-912`

### Worker State

```python
class IngestionWorker:
    def __init__(
        self,
        worker_id: str,
        queue_client: QueuedClient,
        graphiti: Graphiti,
        batch_size: int = 1,
        poll_interval: float = 1.0,
    ):
        self.worker_id = worker_id
        self.queue = queue_client
        self.graphiti = graphiti
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self.rate_limiter = RateLimiter()  # Per-worker rate limiter
        self.centrality_client = CentralityClient()
        self.metrics = QueueMetrics()
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self.episode_count = 0  # Track for background deduplication
        self.dedup_interval = int(os.getenv('DEDUP_EPISODE_INTERVAL', '10'))
        self._post_success_jobs: list[Coroutine] = []  # Background jobs
```

**Key Attributes**:
- `worker_id`: Unique identifier for logging/debugging
- `rate_limiter`: **Per-worker** rate limiting (shared limits across workers)
- `episode_count`: Tracks episodes for periodic deduplication
- `_post_success_jobs`: Queue for async tasks (centrality updates, dedup)

### Processing Loop

#### Main Loop (Lines 300-344)
```python
async def _process_loop(self):
    """Main processing loop"""
    logger.info(f'Worker {self.worker_id} entering process loop')
    
    while self.running:
        try:
            # 1. Poll for tasks (batch_size messages, 20 min visibility)
            tasks = await self.queue.poll(
                queue_name='ingestion',
                count=self.batch_size,
                visibility_timeout=1200,  # 20 minutes
            )
            
            if tasks:
                self.metrics.record_poll(len(tasks))
                logger.debug(f'Worker {self.worker_id} polled {len(tasks)} tasks')
                
                # 2. Process each task sequentially
                for message_id, task, poll_tag in tasks:
                    try:
                        await self._process_task(task)
                        
                        # 3. Delete from queue on success
                        await self.queue.delete(message_id, poll_tag)
                        self.metrics.record_completion()
                        
                    except RateLimitError as e:
                        # Return to queue with backoff
                        retry_after = min(300, e.retry_after * (2**task.retry_count))
                        await self.queue.update(message_id, poll_tag, retry_after)
                        self.metrics.record_retry()
                        
                    except Exception as e:
                        await self._handle_failure(message_id, poll_tag, task, e)
            else:
                # No tasks available, wait before polling again
                await asyncio.sleep(self.poll_interval)
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f'Worker {self.worker_id} loop error: {e}')
            await asyncio.sleep(5)  # Back off on errors
```

**Flow**:
1. **Poll**: Request `batch_size` messages from queue
2. **Process**: Handle each message sequentially
3. **Acknowledge**: Delete successful messages, retry failed ones
4. **Sleep**: Wait 1 second if queue empty

**Visibility Timeout**: 1200 seconds (20 minutes)
- Message becomes invisible to other workers for 20 minutes
- If worker crashes, message reappears after 20 minutes
- Prevents duplicate processing during normal operation

---

## Coordination Mechanisms

### 1. Queue-Based Coordination (Primary)

**Mechanism**: Visibility timeout in LevelDB queue

```python
# Worker A polls
tasks = await queue.poll(count=10, visibility_timeout=1200)
# → Gets messages [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
# → These messages are hidden from other workers for 20 minutes

# Worker B polls (at same time)
tasks = await queue.poll(count=10, visibility_timeout=1200)
# → Gets messages [11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
# → CANNOT get messages 1-10 (they're invisible)
```

**Guarantees**:
- **At-most-once** during visibility window: Only one worker processes message
- **At-least-once** overall: Message reappears if worker crashes

### 2. Rate Limiting (Shared State)

**Location**: `/opt/stacks/graphiti/graphiti_core/ingestion/worker.py:149-213`

```python
class RateLimiter:
    def __init__(self, global_rps: int = 100, group_rpm: int = 60, burst_multiplier: float = 1.5):
        self.global_window = RateLimitWindow([], global_rps, 1)  # 100 req/sec
        self.group_windows: Dict[str, RateLimitWindow] = {}      # 60 req/min per group
        self.burst_multiplier = burst_multiplier
        self.suspended_groups: Dict[str, datetime] = {}
```

**Limits**:
- **Global**: 100 requests/second (shared across all workers)
- **Per-Group**: 60 requests/minute per `group_id`
- **Burst**: 1.5x multiplier for short bursts

**Problem**: Each worker has its own `RateLimiter` instance
- **No shared state** between workers
- Global limit is actually **100 × worker_count** req/sec
- Per-group limit is actually **60 × worker_count** req/min

**Implication**: With 2 workers, actual limits are:
- Global: 200 req/sec (not 100)
- Per-group: 120 req/min (not 60)

### 3. Idempotency (Episode UUID)

**Location**: `/opt/stacks/graphiti/graphiti_core/ingestion/worker.py:388-428`

```python
async def _episode_already_ingested(self, episode_uuid: str, group_id: str) -> bool:
    """Best-effort idempotency check"""
    query = """
    MATCH (e:Episodic {uuid: $uuid})
    OPTIONAL MATCH (e)-[m:MENTIONS]->()
    RETURN
        e.group_id AS group_id,
        size(coalesce(e.entity_edges, [])) AS entity_edges_count,
        count(m) AS mentions_count
    """
    
    records, _, _ = await self.graphiti.driver.execute_query(
        query, uuid=episode_uuid, routing_='r'
    )
    
    if not records:
        return False
    
    # Check if episode has made progress
    entity_edges_count = int(record.get('entity_edges_count') or 0)
    mentions_count = int(record.get('mentions_count') or 0)
    
    return entity_edges_count > 0 or mentions_count > 0
```

**Purpose**: Prevent duplicate work if message is reprocessed

**Checks**:
1. Does episode exist in graph?
2. Does it have MENTIONS edges?
3. Does it have entity_edges list populated?

**If yes to any**: Skip reprocessing (episode already completed)

**Used when**:
- Queue retry after visibility timeout
- Manual requeue of failed episode
- Worker crash and message reappears

---

## Concurrency Model

### Sequential Within Worker, Parallel Across Workers

```
Worker 0: [Episode A] → [Episode B] → [Episode C] → ...
          (sequential)

Worker 1: [Episode D] → [Episode E] → [Episode F] → ...
          (sequential)

Worker 2: [Episode G] → [Episode H] → [Episode I] → ...
          (sequential)

Parallelism = worker_count × batch_size (but batch processed sequentially)
```

**Current Config** (batch_size=1, worker_count=2):
- Total parallelism: 2 concurrent episodes
- Each worker processes 1 episode at a time
- No parallelism within episode (stages run sequentially)

### Why Sequential Within Worker?

**Reason**: Graphiti's `add_episode()` is not thread-safe
- Shared state in LLM client (caching)
- FalkorDB connection pool (limited connections)
- Deduplication logic assumes sequential processing

**Future Optimization**: 
- Could parallelize within stages (e.g., extract multiple entities concurrently)
- Requires refactoring `add_episode()` to be stage-aware

---

## Scaling Characteristics

### Horizontal Scaling (Add More Workers)

**How to scale**:
```bash
# Edit .env
WORKER_COUNT=4  # Double the workers

# Restart service
docker-compose restart graphiti-worker
```

**Effect**:
- Throughput: ~Linear scaling up to queue throughput limit
- 2 workers = ~32 episodes/hour
- 4 workers = ~64 episodes/hour (estimated)
- 8 workers = ~128 episodes/hour (estimated)

**Bottlenecks**:
1. **LLM API rate limits** (10K RPM OpenAI Tier 2)
   - 20 LLM calls/episode × 128 episodes/hour = 2,560 calls/hour
   - Well under limit (600,000 calls/hour)

2. **FalkorDB connection pool** (limited by `maxmemory`)
   - Current: 16GB memory, 8GB runtime limit
   - Each episode ~5MB memory footprint
   - Can handle ~1,600 concurrent episodes (way more than needed)

3. **Queue throughput** (300K ops/sec advertised)
   - 128 episodes/hour = 0.036 episodes/sec
   - 3 queue ops/episode (poll, delete, update) = 0.1 ops/sec
   - Negligible compared to capacity

**Conclusion**: Can scale to 10-20 workers before hitting external limits

### Vertical Scaling (Increase Batch Size)

**How to scale**:
```bash
BATCH_SIZE=10  # Process 10 episodes per poll
```

**Effect**:
- **Within worker**: Still sequential (no parallelism gain)
- **Across workers**: More messages fetched per poll
- **Advantage**: Fewer queue polls (reduce latency overhead)
- **Disadvantage**: Longer visibility timeout needed (risk of timeout)

**Current bottleneck**: Episode processing time (226s) >> poll latency (50ms)
- Increasing batch size has minimal impact
- Better to increase worker count

---

## Background Jobs & Post-Processing

### Post-Success Jobs (Lines 278-298)

```python
def _schedule_post_success_job(self, job: Coroutine[Any, Any, None]) -> None:
    """Queue a coroutine to run after the primary ingestion work succeeds."""
    self._post_success_jobs.append(job)

async def _run_post_success_jobs(self) -> None:
    """Execute and clear queued post-success jobs."""
    if not self._post_success_jobs:
        return
    
    jobs = self._post_success_jobs
    self._post_success_jobs = []
    
    for job in jobs:
        try:
            await job
        except Exception as exc:
            logger.error(f'Post-success job failed: {exc}')
```

**Purpose**: Run non-critical tasks after episode ingestion succeeds

**Jobs**:
1. **Centrality Updates** (Lines 509-510)
   ```python
   self._schedule_post_success_job(
       self._update_centrality_async(centrality_uuids)
   )
   ```
   - Update PageRank, degree centrality for new nodes
   - Calls Rust centrality service (`graphiti-centrality-rs:3003`)
   - **Non-blocking**: Failure doesn't fail episode

2. **Background Deduplication** (Lines 514-518)
   ```python
   if self.episode_count % self.dedup_interval == 0:
       self._schedule_post_success_job(
           self._run_background_deduplication(effective_group_id)
       )
   ```
   - Runs every 10 episodes (configurable via `DEDUP_EPISODE_INTERVAL`)
   - Deduplicates last 100 entities in group
   - **Non-blocking**: Failure doesn't fail episode

**Benefit**: Keeps critical path fast, offloads non-critical work

---

## Metrics & Observability

### QueueMetrics (Lines 357-390 in queue_client.py)

```python
class QueueMetrics:
    def __init__(self):
        self.tasks_pushed = 0
        self.tasks_polled = 0
        self.tasks_completed = 0
        self.tasks_failed = 0
        self.tasks_retried = 0
    
    def get_stats(self) -> Dict[str, int]:
        return {
            "pushed": self.tasks_pushed,
            "polled": self.tasks_polled,
            "completed": self.tasks_completed,
            "failed": self.tasks_failed,
            "retried": self.tasks_retried,
            "success_rate": (self.tasks_completed / max(1, self.tasks_polled)) * 100
        }
```

**Per-Worker Metrics**:
- Each worker tracks its own metrics
- **No aggregation** across workers
- **No persistence** (lost on restart)

### Worker Metrics Endpoint (Lines 906-911)

```python
def get_metrics(self) -> Dict[str, Any]:
    """Get worker metrics"""
    stats = self.metrics.get_stats()
    stats['worker_id'] = self.worker_id
    stats['running'] = self.running
    return stats
```

**WorkerPool Aggregation** (Lines 956-961):
```python
def get_metrics(self) -> Dict[str, Any]:
    """Get aggregated metrics from all workers"""
    return {
        'pool_size': self.worker_count,
        'workers': [worker.get_metrics() for worker in self.workers],
    }
```

**Current State**: Metrics exist but **not exposed via API**
- No Prometheus integration
- No Grafana dashboards
- Only accessible via code

---

## Failure Modes & Recovery

### Worker Crash Scenarios

#### 1. Worker Crashes Mid-Episode
**What happens**:
1. Worker stops responding
2. Episode remains "invisible" in queue for 20 minutes
3. After 20 minutes, visibility timeout expires
4. Message reappears in queue
5. Another worker picks it up
6. Idempotency check prevents duplicate work

**Recovery time**: 20 minutes (visibility timeout)

#### 2. All Workers Crash
**What happens**:
1. Queue service keeps running (independent service)
2. Messages accumulate in queue
3. When workers restart, they resume processing
4. No messages lost (durable LevelDB storage)

**Recovery**: Automatic (workers restart and poll)

#### 3. Queue Service Crashes
**What happens**:
1. Workers can't poll (HTTP errors)
2. Workers back off and retry
3. Episodes not ingested until queue service recovers

**Recovery**: Manual restart of `queued` service

#### 4. FalkorDB Crashes
**What happens**:
1. Episode processing fails at Stage 5 (persistence)
2. Worker marks episode as failed
3. Episode retried (exponential backoff)
4. After 3 retries, moved to DLQ

**Recovery**: 
- Automatic (retries)
- Manual (restart FalkorDB, replay DLQ)

---

## Comparison: Current vs. Temporal

| Aspect | Current (Worker Pool) | Temporal |
|--------|----------------------|----------|
| **Coordination** | Queue visibility timeout | Task queue + workflow state |
| **Parallelism** | Worker-level only | Activity-level within workflow |
| **Scaling** | Manual (env var) | Dynamic (auto-scaling) |
| **Failure Recovery** | 20-min timeout → retry | Immediate retry with backoff |
| **State Management** | Stateless (except queue) | Durable workflow state |
| **Observability** | Basic metrics (not exposed) | Rich Web UI, traces, history |
| **Rate Limiting** | Per-worker (uncoordinated) | Centralized (workflow-aware) |
| **Idempotency** | Manual (episode UUID check) | Built-in (workflow ID) |
| **Background Jobs** | Ad-hoc coroutines | Async activities |

---

## Optimization Opportunities

### 1. Increase Worker Count
**Current**: 2 workers
**Recommendation**: 4-8 workers (until hitting LLM rate limits)
**Expected gain**: 2-4× throughput

### 2. Pipeline Stage Parallelism
**Current**: Stages run sequentially
**Recommendation**: Parallelize independent stages (extract entities + edges concurrently)
**Expected gain**: 20-30% faster per episode

### 3. Batch Embeddings
**Current**: 1 embedding per entity (sequential)
**Recommendation**: Batch 50 entities per embedding call
**Expected gain**: 50% faster embedding generation

### 4. Centralized Rate Limiting
**Current**: Per-worker rate limiters (uncoordinated)
**Recommendation**: Shared rate limiter (Redis or Temporal)
**Expected gain**: Predictable rate limiting, prevent thundering herd

### 5. Expose Metrics
**Current**: Metrics exist but not exposed
**Recommendation**: Prometheus exporter + Grafana dashboards
**Expected gain**: Better observability, proactive alerts

---

## Files Referenced

1. `/opt/stacks/graphiti/graphiti_core/ingestion/worker.py` - IngestionWorker and WorkerPool
2. `/opt/stacks/graphiti/worker/worker_service.py` - Service orchestration
3. `/opt/stacks/graphiti/graphiti_core/ingestion/queue_client.py` - Queue client and metrics
4. `/opt/stacks/graphiti/.env` - Configuration (WORKER_COUNT, BATCH_SIZE)

---

## Key Takeaways

1. **Simple Architecture**: Independent workers + shared queue = easy to reason about
2. **Limited Parallelism**: Only 2 concurrent episodes (could be 10-20×)
3. **Coordination via Queue**: Visibility timeout prevents duplicate processing
4. **No Shared State**: Workers don't communicate (good for simplicity, bad for rate limiting)
5. **Graceful Degradation**: Worker crashes don't lose data (queue durability)
6. **Temporal Would Help**: Dynamic scaling, better observability, activity-level parallelism
