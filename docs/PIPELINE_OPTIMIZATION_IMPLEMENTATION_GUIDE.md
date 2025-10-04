# Pipeline Optimization Implementation Guide

**Phase 1: Quick Wins - Week 1**  
**Goal**: 3-5x throughput improvement with minimal code changes

---

## Overview

This guide provides step-by-step instructions to implement the high-impact, low-effort optimizations identified in the Ingestion Pipeline Optimization Report.

**Target Improvements**:
- ✅ Throughput: 1 episode/10s → 5-10 episodes/10s (5-10x)
- ✅ Cost: 30-40% reduction in LLM tokens
- ✅ Latency: 50-60% reduction in wall-clock time

---

## Optimization 1: Enable Batch Processing

### Current State
- Batch processing code exists in `ChutesClient` but is disabled
- Episodes processed one at a time
- Each episode makes 4-10+ LLM API calls

### Target State
- Process 5-6 episodes per LLM API call
- 80% reduction in API calls
- Batch deduplication enabled

### Implementation Steps

#### Step 1.1: Enable Batch Processing Flag

**File**: `.env` or environment configuration

```bash
# Add to .env
CHUTES_ENABLE_BATCH_PROCESSING=true
BATCH_SIZE=5
BATCH_TIMEOUT_SECONDS=10
```

#### Step 1.2: Verify Batch Processing Code

**File**: `graphiti_core/utils/bulk_utils.py`

Check that batch deduplication is properly configured:

```python
# Line 335-350
use_batch_dedup = (
    os.getenv('CHUTES_ENABLE_BATCH_PROCESSING', 'false').lower() == 'true' and
    hasattr(clients.llm_client, 'dedupe_entities_batch')
)

if use_batch_dedup:
    logger.debug(f"Using batch deduplication for {len(dedupe_tuples)} episodes")
    bulk_node_resolutions = await resolve_extracted_nodes_batch(...)
```

✅ **Already implemented** - just needs environment variable

#### Step 1.3: Modify Worker to Accumulate Episodes

**File**: `graphiti_core/ingestion/worker.py`

Add batch accumulation logic:

```python
class IngestionWorker:
    def __init__(self, ...):
        self.episode_batch = []
        self.batch_size = int(os.getenv('BATCH_SIZE', '5'))
        self.batch_timeout = int(os.getenv('BATCH_TIMEOUT_SECONDS', '10'))
        self.last_batch_time = time.time()
    
    async def _process_episode(self, task: IngestionTask):
        """Accumulate episodes for batch processing"""
        self.episode_batch.append(task)
        
        # Process batch if full or timeout reached
        should_process = (
            len(self.episode_batch) >= self.batch_size or
            time.time() - self.last_batch_time >= self.batch_timeout
        )
        
        if should_process:
            await self._process_episode_batch(self.episode_batch)
            self.episode_batch = []
            self.last_batch_time = time.time()
    
    async def _process_episode_batch(self, tasks: List[IngestionTask]):
        """Process a batch of episodes together"""
        logger.info(f"Processing batch of {len(tasks)} episodes")
        
        # Use bulk processing
        episodes = [self._task_to_episode(task) for task in tasks]
        results = await self.graphiti.add_episodes_bulk(episodes)
        
        logger.info(f"Batch processing complete: {len(results)} episodes processed")
```

#### Step 1.4: Test Batch Processing

```bash
# Set environment
export CHUTES_ENABLE_BATCH_PROCESSING=true
export BATCH_SIZE=5

# Restart worker
docker-compose restart graphiti-worker

# Monitor logs
docker logs -f graphiti-graphiti-worker-1 | grep "batch"
```

**Expected Output**:
```
Using batch deduplication for 5 episodes
Batch processing complete: 5 episodes processed
```

---

## Optimization 2: Parallel Episode Processing

### Current State
- Worker processes tasks sequentially from queue
- Only 1 episode processed at a time
- Underutilizes LLM API rate limits

### Target State
- Process 10 episodes concurrently
- Full utilization of API rate limits
- 3-5x throughput improvement

### Implementation Steps

#### Step 2.1: Add Concurrency Configuration

**File**: `.env`

```bash
MAX_CONCURRENT_EPISODES=10
SEMAPHORE_LIMIT=50  # Already exists, increase if needed
```

#### Step 2.2: Implement Parallel Processing

**File**: `graphiti_core/ingestion/worker.py`

Modify the worker run loop:

```python
from graphiti_core.helpers import semaphore_gather

class IngestionWorker:
    def __init__(self, ...):
        self.max_concurrent = int(os.getenv('MAX_CONCURRENT_EPISODES', '10'))
        self.processing_tasks = []
    
    async def run(self):
        """Process tasks with controlled concurrency"""
        logger.info(f"Worker started with max_concurrent={self.max_concurrent}")
        
        while True:
            try:
                # Accumulate tasks up to max_concurrent
                tasks_to_process = []
                
                for _ in range(self.max_concurrent):
                    try:
                        task = await asyncio.wait_for(
                            self.queue.get(), 
                            timeout=1.0
                        )
                        tasks_to_process.append(task)
                    except asyncio.TimeoutError:
                        break  # No more tasks available
                
                if not tasks_to_process:
                    await asyncio.sleep(0.1)
                    continue
                
                # Process tasks in parallel
                logger.info(f"Processing {len(tasks_to_process)} tasks in parallel")
                
                await semaphore_gather(
                    *[self._process_task_safe(task) for task in tasks_to_process],
                    max_coroutines=self.max_concurrent
                )
                
            except Exception as e:
                logger.error(f"Worker error: {e}")
                await asyncio.sleep(1.0)
    
    async def _process_task_safe(self, task: IngestionTask):
        """Process task with error handling"""
        try:
            await self._process_task(task)
        except Exception as e:
            logger.error(f"Task {task.id} failed: {e}")
            # Handle error (retry, dead letter queue, etc.)
```

#### Step 2.3: Test Parallel Processing

```bash
# Queue multiple episodes
for i in {1..20}; do
    curl -X POST http://localhost:8003/ingest/episode \
        -H "Content-Type: application/json" \
        -d "{\"content\": \"Test episode $i\", \"group_id\": \"test\"}"
done

# Monitor parallel processing
docker logs -f graphiti-graphiti-worker-1 | grep "Processing.*tasks in parallel"
```

**Expected Output**:
```
Processing 10 tasks in parallel
Processing 10 tasks in parallel
```

---

## Optimization 3: Batch Embedding Generation

### Current State
- Embeddings generated one at a time
- Each entity/edge requires separate API call
- High latency for episodes with many entities

### Target State
- Batch embedding API calls (100 texts per call)
- 100x reduction in embedding API calls
- 2-3x faster embedding generation

### Implementation Steps

#### Step 3.1: Add Batch Embedding Method

**File**: `graphiti_core/embedder/client.py`

```python
class EmbedderClient:
    async def create_batch(
        self, 
        input_data: List[str], 
        batch_size: int = 100
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches.
        
        Args:
            input_data: List of texts to embed
            batch_size: Number of texts per API call
            
        Returns:
            List of embedding vectors
        """
        all_embeddings = []
        
        for i in range(0, len(input_data), batch_size):
            batch = input_data[i:i + batch_size]
            
            # Call embedding API with batch
            embeddings = await self.create(batch)
            all_embeddings.extend(embeddings)
        
        return all_embeddings
```

#### Step 3.2: Update Entity Embedding Generation

**File**: `graphiti_core/utils/maintenance/node_operations.py`

```python
async def create_entity_node_embeddings(
    embedder: EmbedderClient, 
    nodes: list[EntityNode]
) -> None:
    """Generate embeddings for entity nodes in batch"""
    if not nodes:
        return
    
    # Collect all texts to embed
    texts = [node.name.replace('\n', ' ') for node in nodes]
    
    # Generate embeddings in batch
    batch_size = int(os.getenv('EMBEDDING_BATCH_SIZE', '100'))
    embeddings = await embedder.create_batch(texts, batch_size=batch_size)
    
    # Assign embeddings to nodes
    for node, embedding in zip(nodes, embeddings):
        node.name_embedding = embedding
    
    logger.debug(f"Generated {len(embeddings)} embeddings in batch")
```

#### Step 3.3: Update Edge Embedding Generation

**File**: `graphiti_core/utils/maintenance/edge_operations.py`

```python
async def create_entity_edge_embeddings(
    embedder: EmbedderClient,
    edges: list[EntityEdge]
) -> None:
    """Generate embeddings for entity edges in batch"""
    if not edges:
        return
    
    # Collect all facts to embed
    texts = [edge.fact.replace('\n', ' ') for edge in edges]
    
    # Generate embeddings in batch
    batch_size = int(os.getenv('EMBEDDING_BATCH_SIZE', '100'))
    embeddings = await embedder.create_batch(texts, batch_size=batch_size)
    
    # Assign embeddings to edges
    for edge, embedding in zip(edges, embeddings):
        edge.fact_embedding = embedding
    
    logger.debug(f"Generated {len(embeddings)} edge embeddings in batch")
```

#### Step 3.4: Configure and Test

**File**: `.env`

```bash
EMBEDDING_BATCH_SIZE=100
```

**Test**:
```bash
# Process episode with many entities
# Monitor logs for batch embedding
docker logs -f graphiti-graphiti-worker-1 | grep "embeddings in batch"
```

**Expected Output**:
```
Generated 15 embeddings in batch
Generated 12 edge embeddings in batch
```

---

## Optimization 4: Ensure Prompt Compression

### Current State
- Prompt compression implemented but may not be consistently used
- Large deduplication contexts sent to LLM
- Higher costs and slower responses

### Target State
- Compression applied to all large prompts
- 30-40% token reduction
- Faster LLM responses

### Implementation Steps

#### Step 4.1: Verify Compression is Enabled

**File**: `graphiti_core/utils/maintenance/node_operations.py`

Check that compression is used in deduplication:

```python
# Line 788
compressor = get_prompt_compressor()

# Line 217-222 (in resolve_extracted_nodes_batch)
compressed_context, compression_stats = compressor.compress_existing_entities(
    existing_nodes_raw,
    target_tokens=2000,
    compression_ratio=0.6
)
```

✅ **Already implemented** in batch deduplication

#### Step 4.2: Add Compression to Single Episode Dedup

**File**: `graphiti_core/utils/maintenance/node_operations.py`

Ensure compression is used in non-batch deduplication:

```python
async def resolve_extracted_nodes(
    clients: GraphitiClients,
    extracted_nodes: list[EntityNode],
    ...
) -> tuple[list[EntityNode], dict[str, str], list[tuple[EntityNode, EntityNode]]]:
    
    compressor = get_prompt_compressor()
    
    # ... existing code ...
    
    for i, (node, search_result) in enumerate(zip(nodes_needing_llm_resolution, search_results)):
        existing_nodes_raw = [
            {'name': n.name, 'labels': n.labels, 'uuid': n.uuid, 'summary': n.summary}
            for n in search_result.nodes
        ]
        
        # Apply compression
        compressed_context, stats = compressor.compress_existing_entities(
            existing_nodes_raw,
            target_tokens=2000,
            compression_ratio=0.6
        )
        
        # Log compression stats
        if stats.get('compression_ratio', 1.0) < 0.9:
            logger.info(f"Compressed dedup context: {stats}")
        
        # Use compressed context in LLM call
        # ... rest of deduplication logic ...
```

#### Step 4.3: Configure Compression

**File**: `.env`

```bash
ENABLE_PROMPT_COMPRESSION=true
COMPRESSION_TARGET_TOKENS=2000
COMPRESSION_RATIO=0.6
```

#### Step 4.4: Monitor Compression Stats

```bash
# Watch for compression logs
docker logs -f graphiti-graphiti-worker-1 | grep "Compressed"
```

**Expected Output**:
```
Compressed dedup context: {'original_tokens': 5234, 'compressed_tokens': 2100, 'compression_ratio': 0.40}
```

---

## Testing & Validation

### Performance Benchmarking

#### Before Optimization
```bash
# Baseline test
time python3 -c "
import asyncio
from test_ingestion.worker import IngestionWorker

async def test():
    # Process 20 episodes sequentially
    for i in range(20):
        await worker.process_episode(f'Episode {i}')

asyncio.run(test())
"
```

**Expected**: ~200-400 seconds (10-20s per episode)

#### After Optimization
```bash
# Optimized test
export CHUTES_ENABLE_BATCH_PROCESSING=true
export MAX_CONCURRENT_EPISODES=10
export BATCH_SIZE=5
export EMBEDDING_BATCH_SIZE=100

# Same test
time python3 -c "..."
```

**Expected**: ~40-80 seconds (2-4s per episode) - **5-10x improvement**

### Metrics to Track

```python
# Add to worker
class IngestionWorker:
    def __init__(self):
        self.metrics = {
            'episodes_processed': 0,
            'total_time': 0,
            'llm_calls': 0,
            'embedding_calls': 0,
            'batch_sizes': [],
            'compression_ratios': []
        }
    
    async def _process_episode_batch(self, tasks):
        start = time.time()
        
        # ... processing ...
        
        elapsed = time.time() - start
        self.metrics['episodes_processed'] += len(tasks)
        self.metrics['total_time'] += elapsed
        self.metrics['batch_sizes'].append(len(tasks))
        
        # Log metrics
        avg_time = self.metrics['total_time'] / self.metrics['episodes_processed']
        logger.info(f"Metrics: {self.metrics['episodes_processed']} episodes, "
                   f"avg {avg_time:.2f}s/episode, "
                   f"avg batch size {np.mean(self.metrics['batch_sizes']):.1f}")
```

---

## Rollout Plan

### Day 1: Enable Batch Processing
1. Set `CHUTES_ENABLE_BATCH_PROCESSING=true`
2. Restart worker
3. Monitor logs for batch processing
4. Verify no errors

### Day 2: Enable Parallel Processing
1. Set `MAX_CONCURRENT_EPISODES=5` (conservative)
2. Restart worker
3. Monitor for 24 hours
4. Increase to 10 if stable

### Day 3: Enable Batch Embeddings
1. Deploy embedding batch code
2. Set `EMBEDDING_BATCH_SIZE=100`
3. Monitor embedding generation
4. Verify correctness

### Day 4: Verify Compression
1. Check compression logs
2. Verify token reduction
3. Monitor LLM costs
4. Adjust compression ratio if needed

### Day 5: Full Optimization
1. All optimizations enabled
2. Run performance benchmarks
3. Compare before/after metrics
4. Document results

---

## Monitoring & Alerts

### Key Metrics Dashboard

```yaml
metrics:
  - name: throughput
    query: rate(episodes_processed[5m])
    target: "> 5 episodes/minute"
    
  - name: latency_p95
    query: histogram_quantile(0.95, episode_duration_seconds)
    target: "< 10 seconds"
    
  - name: batch_utilization
    query: avg(batch_size)
    target: "> 4 episodes/batch"
    
  - name: llm_cost_per_episode
    query: sum(llm_tokens) / sum(episodes_processed)
    target: "< 5000 tokens/episode"
```

### Alerts

```yaml
alerts:
  - name: LowThroughput
    condition: throughput < 3 episodes/minute
    severity: warning
    
  - name: HighLatency
    condition: latency_p95 > 30 seconds
    severity: warning
    
  - name: LowBatchUtilization
    condition: avg(batch_size) < 3
    severity: info
```

---

## Troubleshooting

### Issue: Batch processing not working
**Symptoms**: Still seeing sequential processing in logs  
**Solution**: 
1. Verify `CHUTES_ENABLE_BATCH_PROCESSING=true` is set
2. Check LLM client has `dedupe_entities_batch` method
3. Restart worker to pick up environment changes

### Issue: High error rate with parallel processing
**Symptoms**: Many failed tasks, rate limit errors  
**Solution**:
1. Reduce `MAX_CONCURRENT_EPISODES` to 5
2. Check LLM API rate limits
3. Add exponential backoff for rate limit errors

### Issue: Embedding batch failures
**Symptoms**: Embedding generation errors  
**Solution**:
1. Reduce `EMBEDDING_BATCH_SIZE` to 50
2. Check embedding API limits
3. Verify all texts are non-empty

---

## Success Criteria

✅ **Throughput**: 5-10 episodes processed per minute  
✅ **Latency**: P95 < 10 seconds per episode  
✅ **Cost**: 30-40% reduction in LLM tokens  
✅ **Reliability**: < 1% error rate  
✅ **Batch Utilization**: Average batch size > 4 episodes

---

## Next Steps

After Phase 1 is complete and stable:
1. Implement deduplication caching (Phase 2)
2. Add deferred attribute extraction (Phase 2)
3. Set up comprehensive monitoring (Phase 2)
4. Explore incremental deduplication (Phase 3)

