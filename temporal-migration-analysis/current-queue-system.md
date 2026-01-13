# Current Queue System Architecture

## Overview
The current ingestion pipeline uses Wilson Lin's `queued` service - a high-performance, LevelDB-backed message queue written in TypeScript/Rust.

## Queue Service (`queued`)

### Location
- **Service Name**: `queued` (Docker Compose service)
- **Port**: 8093 (HTTP API)
- **Protocol**: HTTP + MessagePack
- **Storage**: LevelDB (persistent on-disk queue)

### Client Implementation
- **File**: `/opt/stacks/graphiti/graphiti_core/ingestion/queue_client.py`
- **Class**: `QueuedClient`
- **Client Library**: `httpx` (async HTTP) + `msgpack` (binary serialization)

### API Operations

#### 1. Push (Enqueue)
```python
async def push(tasks: List[IngestionTask], queue_name: str = "ingestion") -> List[int]
```
- **Endpoint**: `POST /queue/{queue_name}/messages/push`
- **Payload**: MessagePack-encoded batch of tasks
- **Returns**: List of message IDs
- **Batch Size**: Unlimited (efficient batch operations)

#### 2. Poll (Dequeue)
```python
async def poll(queue_name: str, count: int = 10, visibility_timeout: int = 300) -> List[tuple[int, IngestionTask, int]]
```
- **Endpoint**: `POST /queue/{queue_name}/messages/poll`
- **Behavior**: 
  - Returns up to `count` messages
  - Messages become invisible for `visibility_timeout` seconds
  - Returns empty list (HTTP 204) if no messages available
- **Returns**: List of `(message_id, task, poll_tag)` tuples
- **Sorting**: Client-side priority sorting (HIGH → CRITICAL → NORMAL → LOW)

#### 3. Delete (Acknowledge)
```python
async def delete(message_id: int, poll_tag: int) -> bool
```
- **Endpoint**: `POST /queue/{queue_name}/messages/delete`
- **Purpose**: Confirm successful processing (removes from queue)
- **Poll Tag**: Required for optimistic locking (prevents double-deletion)

#### 4. Update (Extend Visibility)
```python
async def update(message_id: int, poll_tag: int, visibility_timeout: int) -> Optional[int]
```
- **Endpoint**: `POST /queue/{queue_name}/messages/update`
- **Purpose**: Extend visibility timeout for long-running tasks
- **Returns**: New poll tag if successful
- **Use Case**: Retry with exponential backoff

### Queue Guarantees
- **Durability**: LevelDB with fsync ensures messages survive crashes
- **At-Least-Once Delivery**: Visibility timeout ensures messages are retried if worker crashes
- **No Built-in DLQ**: Failed messages must be manually retried or logged
- **Performance**: Advertised 300K ops/sec capability

## Message Structure

### IngestionTask (Python)
```python
@dataclass
class IngestionTask:
    id: str                    # UUID of the episode
    type: TaskType             # EPISODE, ENTITY, BATCH, etc.
    payload: Dict[str, Any]    # Episode data (content, metadata)
    group_id: Optional[str]    # Graphiti group (namespace)
    priority: TaskPriority     # LOW, NORMAL, HIGH, CRITICAL
    retry_count: int           # Current retry attempt
    max_retries: int           # Fail after N retries
    created_at: datetime       # UTC timestamp
    visibility_timeout: int    # Seconds (default 300 = 5 min)
    metadata: Dict[str, Any]   # Extra context
```

### Wire Format (MessagePack)
```json
{
  "priority": 1,
  "task": "{\"id\": \"...\", \"type\": \"episode\", ...}"
}
```
- Priority stored separately for efficient sorting
- Task JSON-serialized within MessagePack envelope

## Task Types

### Current Usage
```python
class TaskType(str, Enum):
    EPISODE = "episode"           # Primary use case
    ENTITY = "entity"              # Not currently used
    BATCH = "batch"                # Not currently used
    RELATIONSHIP = "relationship" # Not currently used
    DEDUPLICATION = "deduplication" # Not currently used
```

**Reality**: Only `EPISODE` tasks are being enqueued. Other types are placeholders for future work.

## Priority Levels

```python
class TaskPriority(int, Enum):
    LOW = 0       # Batch operations, analytics
    NORMAL = 1    # Regular message ingestion (DEFAULT)
    HIGH = 2      # User-initiated operations
    CRITICAL = 3  # System operations
```

**Current Behavior**: All episodes use `NORMAL` priority. No priority-based routing exists.

## Queue Configuration

### Environment Variables (from docker-compose.yml)
- **QUEUED_URL**: `http://queued:8080` (internal Docker network)
- **Queue Name**: Hardcoded as `"ingestion"` in code

### Client Configuration
```python
QueuedClient(base_url="http://localhost:8093", timeout=30.0)
```
- 30-second HTTP timeout for long operations
- Keep-alive HTTP client (reused across requests)

## Error Handling

### Retry Logic
1. **Task-Level Retries**: 
   - `max_retries` = 3 (hardcoded in `IngestionTask` default)
   - Exponential backoff via `update()` extending visibility timeout
   - **Not implemented in worker code** - no automatic retry

2. **HTTP-Level Retries**:
   - None - `httpx` client has no built-in retry
   - Relies on visibility timeout to requeue failed tasks

3. **Failure Modes**:
   - **Network failure**: Message remains in queue, becomes visible after timeout
   - **Worker crash**: Message becomes visible after timeout
   - **Processing failure**: Worker must manually call `update()` or let timeout expire
   - **Poison messages**: No automatic DLQ - will retry forever unless manually removed

## Observability

### Metrics Endpoint
```python
async def get_stats() -> Dict[str, Any]
```
- **Endpoint**: `GET /metrics`
- **Format**: MessagePack
- **Metrics**: Queue depth, message counts, etc. (exact schema unknown)

### Client-Side Metrics
```python
class QueueMetrics:
    tasks_pushed: int
    tasks_polled: int
    tasks_completed: int
    tasks_failed: int
    tasks_retried: int
```
- Not currently used in production
- No integration with Prometheus/Grafana

### Logging
- Client logs push/poll/delete operations at `DEBUG` level
- No structured logging (plain text)
- No correlation IDs across operations

## Queue Lifecycle

### Message Flow
1. **Enqueue**: `push()` → LevelDB → returns message ID
2. **Poll**: Worker calls `poll()` → message hidden for 300s → returns task
3. **Process**: Worker calls Graphiti `add_episode()`
4. **Success**: Worker calls `delete()` → message removed from queue
5. **Failure**: Worker crashes → message reappears after 300s → retried

### Visibility Timeout Behavior
- **Default**: 300 seconds (5 minutes)
- **Purpose**: Prevents lost messages if worker crashes mid-processing
- **Trade-off**: Failed tasks wait 5 minutes before retry
- **Current issue**: No exponential backoff - same task fails repeatedly every 5 min

## Comparison to Temporal

| Feature | Current (queued) | Temporal |
|---------|------------------|----------|
| **Queue Type** | LevelDB message queue | Task queue + workflow engine |
| **Retry Logic** | Manual (visibility timeout) | Automatic with exponential backoff |
| **DLQ** | None | Built-in failed workflow tracking |
| **Observability** | Minimal (basic metrics) | Rich (Web UI, metrics, traces) |
| **Workflow State** | None (fire-and-forget) | Full workflow history |
| **Timeouts** | Single visibility timeout | Multiple (schedule-to-start, start-to-close, heartbeat) |
| **Worker Scaling** | Manual (WORKER_COUNT env var) | Dynamic (task queue workers) |
| **Idempotency** | Manual (episode UUID dedup) | Built-in (workflow IDs) |
| **Long-running tasks** | Limited (5 min visibility timeout) | Unlimited (heartbeats) |

## Pain Points

1. **No Automatic Retries**: Failures rely on visibility timeout, no exponential backoff
2. **No DLQ**: Poison messages retry forever or require manual intervention
3. **Poor Observability**: No structured logging, no traces, no Web UI
4. **No Workflow State**: Can't inspect in-flight episodes or pause/resume processing
5. **Hard to Debug**: No correlation IDs, hard to trace episode through pipeline
6. **Single Point of Failure**: If `queued` service crashes, entire ingestion stops
7. **Manual Scaling**: Must manually adjust `WORKER_COUNT` env var

## Files to Review

### Queue Implementation
- `/opt/stacks/graphiti/queued/queued-client-js/src/main.ts` - JS client (if exists)
- `/opt/stacks/graphiti/queued/` - Server implementation (TypeScript/Rust?)

### Client Integration
- `/opt/stacks/graphiti/graphiti_core/ingestion/queue_client.py` - Python client wrapper
- `/opt/stacks/graphiti/worker/worker_service.py` - Worker that polls the queue
- `/opt/stacks/graphiti/graphiti_core/ingestion/worker.py` - Worker pool logic

## Next Steps
1. Document worker pool architecture (how tasks are distributed across workers)
2. Map episode processing pipeline (what happens after `poll()`)
3. Identify retry/failure handling gaps
4. Design Temporal equivalent (workflow + activities)
