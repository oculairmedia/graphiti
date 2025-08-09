# Graph Service Search Performance Optimization Plan

## Executive Summary
Current search latency likely 200-500ms. Target: <50ms p50, <100ms p99.

## Key Performance Bottlenecks Identified

### 1. **Synchronous Webhook Emissions** (Impact: High)
- Webhook calls block the request path
- Network I/O adds 50-200ms latency per request
- No retry mechanism causing potential data loss

### 2. **No Caching Layer** (Impact: Critical)
- Every search hits the database
- Embeddings generated for every query
- No result caching for repeated queries
- No pre-computed search indices

### 3. **Inefficient Database Access** (Impact: High)
- Multiple concurrent queries without connection pooling
- No query batching
- Full object hydration for all results
- Multiple round trips for edge/node resolution

### 4. **Expensive Operations in Request Path** (Impact: Medium)
- Cross-encoder reranking synchronous
- getattr() calls in hot loops
- Deep copying of search configs
- Multiple list comprehensions creating intermediate objects

## Proposed Solutions

### Phase 1: Quick Wins (1-2 days)

#### 1.1 Async Webhook Dispatch
```python
# Create background task queue
from asyncio import Queue, create_task

class AsyncWebhookDispatcher:
    def __init__(self):
        self.queue = Queue(maxsize=10000)
        self.worker_task = None
    
    async def start(self):
        self.worker_task = create_task(self._worker())
    
    async def emit(self, event):
        # Non-blocking add to queue
        await self.queue.put(event)
    
    async def _worker(self):
        while True:
            event = await self.queue.get()
            try:
                await self._dispatch(event)
            except Exception as e:
                logger.error(f"Webhook dispatch failed: {e}")
```

#### 1.2 Response Object Pooling
```python
# Pre-allocate response objects
class ResponsePool:
    def __init__(self, size=100):
        self.pool = [NodeResult() for _ in range(size)]
        self.index = 0
    
    def get(self):
        obj = self.pool[self.index]
        self.index = (self.index + 1) % len(self.pool)
        return obj
```

#### 1.3 Remove getattr() from Hot Paths
```python
# Before
summary = getattr(node, 'summary', '')
labels = getattr(node, 'labels', [])

# After (use __dict__ access)
node_dict = node.__dict__
summary = node_dict.get('summary', '')
labels = node_dict.get('labels', [])
```

### Phase 2: Caching Layer (3-5 days)

#### 2.1 Redis-based Multi-tier Cache
```python
from redis import asyncio as aioredis
import msgpack

class SearchCache:
    def __init__(self):
        self.redis = aioredis.from_url("redis://localhost")
        self.local_cache = {}  # L1 cache
        
    async def get_cached_result(self, query_hash):
        # L1: Local memory (5ms)
        if query_hash in self.local_cache:
            return self.local_cache[query_hash]
        
        # L2: Redis (10-20ms)
        cached = await self.redis.get(query_hash)
        if cached:
            result = msgpack.unpackb(cached)
            self.local_cache[query_hash] = result
            return result
        
        return None
    
    async def cache_result(self, query_hash, result, ttl=300):
        packed = msgpack.packb(result)
        await self.redis.setex(query_hash, ttl, packed)
        self.local_cache[query_hash] = result
```

#### 2.2 Embedding Cache
```python
class EmbeddingCache:
    def __init__(self):
        self.cache = {}  # query -> embedding
        self.lru = OrderedDict()
        self.max_size = 10000
    
    async def get_or_compute(self, query, embedder):
        if query in self.cache:
            # Move to end (most recently used)
            self.lru.move_to_end(query)
            return self.cache[query]
        
        embedding = await embedder.create([query])
        self.cache[query] = embedding
        self.lru[query] = True
        
        # Evict oldest if cache full
        if len(self.cache) > self.max_size:
            oldest = next(iter(self.lru))
            del self.cache[oldest]
            del self.lru[oldest]
        
        return embedding
```

### Phase 3: Database Optimization (1 week)

#### 3.1 Connection Pooling with Circuit Breaker
```python
class OptimizedDatabasePool:
    def __init__(self, min_size=10, max_size=50):
        self.pool = asyncio.Queue(maxsize=max_size)
        self.semaphore = asyncio.Semaphore(max_size)
        self.circuit_breaker = CircuitBreaker()
        
    async def acquire(self):
        if self.circuit_breaker.is_open():
            raise ServiceUnavailable()
        
        async with self.semaphore:
            try:
                conn = await asyncio.wait_for(
                    self.pool.get(), 
                    timeout=1.0
                )
                return conn
            except asyncio.TimeoutError:
                self.circuit_breaker.record_failure()
                raise
```

#### 3.2 Query Batching
```python
class QueryBatcher:
    def __init__(self, batch_size=50, wait_time_ms=10):
        self.batch = []
        self.batch_size = batch_size
        self.wait_time = wait_time_ms / 1000
        self.lock = asyncio.Lock()
        
    async def add_query(self, query):
        async with self.lock:
            self.batch.append(query)
            
            if len(self.batch) >= self.batch_size:
                return await self._execute_batch()
            
            # Wait for more queries or timeout
            await asyncio.sleep(self.wait_time)
            return await self._execute_batch()
    
    async def _execute_batch(self):
        if not self.batch:
            return []
        
        queries = self.batch[:]
        self.batch.clear()
        
        # Execute all queries in single round trip
        return await self.driver.execute_batch(queries)
```

### Phase 4: Pre-computed Indices (2 weeks)

#### 4.1 Materialized Search Views
```sql
-- Pre-compute common search patterns
CREATE MATERIALIZED VIEW search_index AS
SELECT 
    e.uuid,
    e.name,
    e.fact,
    e.embedding,
    n1.name as source_name,
    n2.name as target_name,
    ts_rank(to_tsvector('english', e.fact), query) as text_rank,
    1 - (e.embedding <=> query_embedding) as vector_similarity
FROM edges e
JOIN nodes n1 ON e.source_uuid = n1.uuid
JOIN nodes n2 ON e.target_uuid = n2.uuid;

-- Refresh every 5 minutes
CREATE INDEX idx_search_rank ON search_index(text_rank DESC, vector_similarity DESC);
```

#### 4.2 Bloom Filters for Existence Checks
```python
from pybloom_live import BloomFilter

class NodeExistenceFilter:
    def __init__(self, capacity=1000000, error_rate=0.001):
        self.filter = BloomFilter(capacity=capacity, error_rate=error_rate)
        
    def add(self, node_uuid):
        self.filter.add(node_uuid)
    
    def might_exist(self, node_uuid):
        return node_uuid in self.filter
```

### Phase 5: Advanced Optimizations (1 month)

#### 5.1 GPU-Accelerated Vector Search
```python
import faiss

class FAISSVectorIndex:
    def __init__(self, dimension=1536):
        # Use GPU if available
        self.index = faiss.IndexFlatIP(dimension)
        if faiss.get_num_gpus() > 0:
            self.index = faiss.index_cpu_to_gpu(
                faiss.StandardGpuResources(), 
                0, 
                self.index
            )
    
    async def search(self, query_vector, k=100):
        # Search happens on GPU
        scores, indices = self.index.search(query_vector, k)
        return indices, scores
```

#### 5.2 Request Coalescing
```python
class RequestCoalescer:
    def __init__(self):
        self.pending = {}  # query_hash -> Future
        
    async def search(self, query_hash, search_fn):
        if query_hash in self.pending:
            # Wait for existing request
            return await self.pending[query_hash]
        
        # Create new request
        future = asyncio.create_future()
        self.pending[query_hash] = future
        
        try:
            result = await search_fn()
            future.set_result(result)
            return result
        finally:
            del self.pending[query_hash]
```

## Performance Metrics & Monitoring

### Key Metrics to Track
- **p50, p95, p99 latency** per endpoint
- **Cache hit rate** (target: >80%)
- **Database connection pool utilization**
- **Webhook queue depth**
- **Error rates by component**

### Monitoring Implementation
```python
from prometheus_client import Histogram, Counter, Gauge

search_latency = Histogram(
    'search_latency_seconds',
    'Search request latency',
    ['endpoint', 'cache_hit']
)

cache_hits = Counter(
    'cache_hits_total',
    'Number of cache hits',
    ['cache_level']
)

db_pool_size = Gauge(
    'db_connection_pool_size',
    'Current database connection pool size'
)
```

## Expected Performance Gains

| Optimization | Latency Reduction | Implementation Effort |
|-------------|------------------|----------------------|
| Async webhooks | -50ms to -200ms | Low (1 day) |
| Response pooling | -5ms to -10ms | Low (2 hours) |
| Redis caching | -100ms to -300ms | Medium (3 days) |
| Embedding cache | -50ms to -100ms | Low (1 day) |
| Connection pooling | -20ms to -50ms | Medium (2 days) |
| Query batching | -30ms to -60ms | Medium (3 days) |
| Pre-computed indices | -100ms to -200ms | High (2 weeks) |
| GPU vector search | -50ms to -150ms | High (1 week) |

## Total Expected Improvement
- **Current**: 200-500ms average
- **After Phase 1**: 150-300ms (-25% to -40%)
- **After Phase 2**: 80-150ms (-60% to -70%)
- **After Phase 3**: 50-100ms (-75% to -80%)
- **After Phase 4**: 30-60ms (-85% to -88%)
- **After Phase 5**: 20-40ms (-90% to -92%)

## Implementation Priority
1. **Immediate**: Async webhooks, response pooling
2. **Week 1**: Redis caching, embedding cache
3. **Week 2**: Connection pooling, query batching
4. **Week 3-4**: Pre-computed indices
5. **Month 2**: GPU acceleration, advanced optimizations

## Testing Strategy
- Load testing with k6 or Locust
- A/B testing with feature flags
- Gradual rollout with canary deployments
- Synthetic monitoring with Datadog/New Relic