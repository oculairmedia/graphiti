# Graphiti Ingestion Queue System Design

## Overview

Implementing a robust, high-performance queue-based ingestion system for Graphiti, inspired by Wilson Lin's search engine architecture using the `queued` library.

## Current Architecture Issues

1. **In-memory AsyncWorker**: Current implementation uses a simple `asyncio.Queue` that loses tasks on restart
2. **No persistence**: Messages are lost if the service crashes
3. **No retry logic**: Failed ingestions are not retried
4. **Limited scalability**: Single worker thread processes messages sequentially
5. **No rate limiting**: Can overwhelm downstream services (LLM, FalkorDB)
6. **No monitoring**: Difficult to track queue depth, processing rate, failures

## Proposed Architecture

### 1. Queue Service Integration

Use `queued` as a standalone service for durable message queuing:

```
Client → API Server → Queued Service → Worker Pool → Graphiti Core
                           ↓
                     Persistent Storage
```

### 2. Message Structure

```python
@dataclass
class IngestionTask:
    id: str  # Unique task ID
    type: Literal["episode", "entity", "batch"]
    payload: Dict[str, Any]
    group_id: Optional[str]
    priority: int = 0
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime
    visibility_timeout: int = 300  # 5 minutes
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 3. Worker Pool Design

```python
class IngestionWorker:
    """Process ingestion tasks from queue"""
    
    def __init__(self, 
                 queue_client: QueuedClient,
                 graphiti: Graphiti,
                 worker_id: str):
        self.queue = queue_client
        self.graphiti = graphiti
        self.worker_id = worker_id
        self.rate_limiter = RateLimiter()
        
    async def process_loop(self):
        """Main processing loop"""
        while True:
            # Poll for tasks with unique tag
            tasks = await self.queue.poll(
                count=10,  # Batch size
                visibility_timeout=300
            )
            
            for task in tasks:
                try:
                    await self.process_task(task)
                    await self.queue.delete(task.id)
                except RateLimitError:
                    # Return to queue with backoff
                    await self.queue.update(
                        task.id,
                        visibility_timeout=60 * (2 ** task.retry_count)
                    )
                except Exception as e:
                    await self.handle_failure(task, e)
```

### 4. Rate Limiting & Backpressure

```python
class RateLimiter:
    """Per-group and global rate limiting"""
    
    def __init__(self):
        self.group_windows = {}  # Sliding windows per group
        self.global_semaphore = asyncio.Semaphore(100)  # Global concurrency
        
    async def acquire(self, group_id: str):
        """Acquire permission to process"""
        # Check group-specific rate limit
        if not self.check_group_limit(group_id):
            raise RateLimitError(group_id)
            
        # Acquire global semaphore
        await self.global_semaphore.acquire()
```

### 5. Priority & Scheduling

- **Priority levels**:
  - 0: Low - Batch operations, analytics
  - 1: Normal - Regular message ingestion
  - 2: High - User-initiated operations
  - 3: Critical - System operations

- **Scheduling strategy**:
  - Poll high-priority queues more frequently
  - Batch low-priority tasks for efficiency
  - Dynamic worker allocation based on queue depth

### 6. Error Handling

```python
class ErrorHandler:
    """Centralized error handling with retry logic"""
    
    async def handle_failure(self, task: IngestionTask, error: Exception):
        task.retry_count += 1
        
        if isinstance(error, TransientError):
            # Exponential backoff for transient errors
            delay = min(300, 10 * (2 ** task.retry_count))
            await self.queue.update(task.id, visibility_timeout=delay)
            
        elif isinstance(error, PermanentError):
            # Move to dead letter queue
            await self.move_to_dlq(task, error)
            
        elif task.retry_count < task.max_retries:
            # Generic retry with backoff
            delay = 30 * task.retry_count
            await self.queue.update(task.id, visibility_timeout=delay)
            
        else:
            # Max retries exceeded
            await self.move_to_dlq(task, error)
```

### 7. Monitoring & Metrics

```python
class QueueMetrics:
    """Prometheus metrics for queue monitoring"""
    
    queue_depth = Gauge('graphiti_queue_depth', 'Current queue depth', ['queue_name'])
    processing_rate = Counter('graphiti_tasks_processed', 'Tasks processed', ['status'])
    processing_duration = Histogram('graphiti_task_duration', 'Task processing time')
    error_rate = Counter('graphiti_task_errors', 'Task errors', ['error_type'])
    
    @contextmanager
    def track_processing(self, task_type: str):
        """Track task processing metrics"""
        start = time.time()
        try:
            yield
            self.processing_rate.labels(status='success').inc()
        except Exception as e:
            self.processing_rate.labels(status='failure').inc()
            self.error_rate.labels(error_type=type(e).__name__).inc()
            raise
        finally:
            duration = time.time() - start
            self.processing_duration.observe(duration)
```

## Implementation Plan

### Phase 1: Queue Service Setup
1. Deploy `queued` service with Docker
2. Create Python client wrapper
3. Implement basic push/poll operations

### Phase 2: Worker Pool
1. Create worker pool manager
2. Implement task processing logic
3. Add health checks and graceful shutdown

### Phase 3: Rate Limiting
1. Implement sliding window rate limiter
2. Add per-group and global limits
3. Create backpressure mechanisms

### Phase 4: Error Handling
1. Implement retry logic with exponential backoff
2. Create dead letter queue
3. Add error monitoring and alerting

### Phase 5: Monitoring
1. Add Prometheus metrics
2. Create Grafana dashboards
3. Implement health endpoints

### Phase 6: Optimization
1. Batch processing for efficiency
2. Dynamic worker scaling
3. Performance tuning

## Configuration

```yaml
# queued-config.yaml
queue:
  service_url: "http://queued:8080"
  max_message_size: 10485760  # 10MB
  default_visibility_timeout: 300

workers:
  count: 4
  batch_size: 10
  poll_interval: 1.0

rate_limits:
  global:
    requests_per_second: 100
    burst_size: 200
  per_group:
    requests_per_minute: 60
    burst_size: 100

retry:
  max_attempts: 3
  base_delay: 10
  max_delay: 300
  exponential_base: 2

monitoring:
  metrics_port: 9090
  health_check_interval: 30
```

## Benefits

1. **Durability**: Messages persisted to disk with fsync
2. **Performance**: 300K ops/sec capability
3. **Scalability**: Horizontal scaling with multiple workers
4. **Reliability**: Automatic retries with exponential backoff
5. **Observability**: Comprehensive metrics and monitoring
6. **Rate Control**: Prevent overwhelming downstream services
7. **Priority**: Process important tasks first
8. **Recovery**: Graceful handling of failures and restarts

## Migration Strategy

1. Deploy queue service alongside existing system
2. Dual-write to both old and new systems
3. Gradually migrate read path to new system
4. Monitor and validate consistency
5. Deprecate old AsyncWorker

## Performance Targets

- **Throughput**: 10,000 messages/second sustained
- **Latency**: < 100ms p99 queue time
- **Durability**: Zero message loss on crash
- **Availability**: 99.9% uptime
- **Scale**: Support 1M queued messages