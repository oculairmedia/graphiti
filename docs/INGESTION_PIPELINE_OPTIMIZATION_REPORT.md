# Graphiti Ingestion Pipeline Optimization Report

**Date**: 2025-01-XX  
**Status**: Analysis & Recommendations  
**Priority**: High - Performance Critical

---

## Executive Summary

This report analyzes the current Graphiti ingestion pipeline and identifies optimization opportunities to improve throughput, reduce latency, and minimize LLM API costs. The current pipeline processes episodes sequentially with multiple LLM calls per episode, creating bottlenecks that can be addressed through batching, parallelization, and intelligent caching.

**Key Findings**:
- ✅ Prompt compression **IS implemented** but may not be fully utilized
- ⚠️ Batch processing exists but is **not enabled by default**
- ⚠️ Sequential processing creates **unnecessary latency**
- ⚠️ Multiple LLM calls per episode (extraction, deduplication, attribute extraction)
- ⚠️ Embedding generation happens serially
- ✅ Parallel infrastructure exists (`semaphore_gather`) but underutilized

---

## Current Pipeline Architecture

### Episode Processing Flow

```
1. Episode Creation
   └─> Save EpisodicNode to database
   
2. Entity Extraction (LLM Call #1)
   └─> extract_nodes() → ExtractedEntities
   └─> Reflexion loop (optional, LLM Call #2-N)
   
3. Entity Deduplication (LLM Call #N+1)
   └─> resolve_extracted_nodes() → Search similar entities
   └─> LLM deduplication for each entity with candidates
   
4. Attribute Extraction (LLM Call #N+2 per entity)
   └─> extract_attributes_from_node() → Custom entity attributes
   
5. Embedding Generation (Sequential)
   └─> create_entity_node_embeddings() → One embedding per entity
   
6. Edge Extraction (LLM Call #N+3)
   └─> extract_edges() → Relationships between entities
   
7. Edge Deduplication (LLM Call #N+4)
   └─> resolve_extracted_edges() → Similar to entity dedup
   
8. Edge Embedding Generation (Sequential)
   └─> create_entity_edge_embeddings() → One embedding per edge
   
9. Centrality Calculation (Async, non-blocking)
   └─> Update PageRank, betweenness, degree centrality
```

**Total LLM Calls per Episode**: 4-10+ depending on entities/edges  
**Total Processing Time**: 10-30 seconds per episode (varies by LLM provider)

---

## Performance Bottlenecks

### 1. **Sequential Episode Processing**
- **Issue**: Episodes processed one at a time in worker queue
- **Impact**: Underutilizes LLM API rate limits and concurrent capacity
- **Evidence**: Worker processes tasks sequentially from queue

### 2. **Multiple LLM Calls per Episode**
- **Issue**: Each step requires separate LLM API call
- **Impact**: High latency, increased costs, rate limit pressure
- **Breakdown**:
  - Entity extraction: 1-2 calls (with reflexion)
  - Entity deduplication: 1 call per entity with candidates
  - Attribute extraction: 1 call per entity
  - Edge extraction: 1 call
  - Edge deduplication: 1 call per edge with candidates

### 3. **Serial Embedding Generation**
- **Issue**: Embeddings generated one at a time
- **Impact**: Unnecessary latency when embedding APIs support batching
- **Evidence**: `create_entity_node_embeddings()` calls embedder sequentially

### 4. **Deduplication Overhead**
- **Issue**: LLM-based deduplication for every entity/edge
- **Impact**: Expensive and slow, especially with large graphs
- **Current Threshold**: 0.8 for nodes, 0.6 for edges (semantic similarity)

### 5. **Prompt Compression Underutilization**
- **Issue**: Compression implemented but not consistently applied
- **Impact**: Larger prompts = higher costs and slower responses
- **Evidence**: `GraphitiPromptCompressor` exists but usage unclear

---

## Optimization Strategies

### Strategy 1: **Batch Episode Processing** 🚀
**Priority**: HIGH | **Impact**: 5-10x throughput improvement | **Effort**: Medium

#### Implementation
Enable batch processing for multiple episodes in a single LLM call:

```python
# Current: Sequential processing
for episode in episodes:
    result = await graphiti.add_episode(episode)

# Optimized: Batch processing
results = await graphiti.add_episodes_batch(episodes, batch_size=5)
```

#### Benefits
- **80% reduction in API calls** (proven in `test_chutes_batch_deduplication.py`)
- **5-6 episodes per API call** is optimal batch size
- Amortizes LLM overhead across multiple episodes
- Better utilization of context window

#### Implementation Files
- ✅ **Already exists**: `ChutesClient.extract_entities_batch()`
- ✅ **Already exists**: `ChutesClient.extract_entities_batch_parallel()`
- ⚠️ **Not enabled**: Set `CHUTES_ENABLE_BATCH_PROCESSING=true`

#### Action Items
1. Enable batch processing in environment: `CHUTES_ENABLE_BATCH_PROCESSING=true`
2. Modify worker to accumulate episodes before processing
3. Add batch size configuration (default: 5-6 episodes)
4. Implement batch timeout (process partial batches after N seconds)

---

### Strategy 2: **Parallel Episode Processing** ⚡
**Priority**: HIGH | **Impact**: 3-5x throughput improvement | **Effort**: Low

#### Implementation
Process multiple episodes concurrently using existing `semaphore_gather`:

```python
# Current: Sequential
for episode in episodes:
    await process_episode(episode)

# Optimized: Parallel with semaphore
await semaphore_gather(
    *[process_episode(ep) for ep in episodes],
    max_coroutines=10  # Configurable concurrency
)
```

#### Benefits
- Utilizes full LLM API rate limits
- Reduces wall-clock time significantly
- Already implemented in `semaphore_gather()` helper
- No changes to LLM client needed

#### Configuration
```bash
# Environment variables
MAX_CONCURRENT_EPISODES=10  # Parallel episode processing
SEMAPHORE_LIMIT=50          # Max concurrent coroutines (already exists)
```

#### Action Items
1. Modify worker to process episodes in parallel batches
2. Add concurrency configuration
3. Implement backpressure handling for queue overflow
4. Monitor LLM API rate limits

---

### Strategy 3: **Embedding Batch Generation** 📦
**Priority**: MEDIUM | **Impact**: 2-3x embedding speed | **Effort**: Low

#### Implementation
Batch embedding API calls instead of one-by-one:

```python
# Current: Sequential
for entity in entities:
    entity.name_embedding = await embedder.create([entity.name])

# Optimized: Batch
texts = [entity.name for entity in entities]
embeddings = await embedder.create_batch(texts, batch_size=100)
for entity, embedding in zip(entities, embeddings):
    entity.name_embedding = embedding
```

#### Benefits
- Most embedding APIs support batching (OpenAI: 2048 inputs)
- Reduces API calls by 100x
- Lower latency and cost

#### Action Items
1. Add `create_batch()` method to `EmbedderClient`
2. Update `create_entity_node_embeddings()` to use batching
3. Update `create_entity_edge_embeddings()` to use batching
4. Configure optimal batch size per provider

---

### Strategy 4: **Smart Deduplication Caching** 🧠
**Priority**: MEDIUM | **Impact**: 50-70% dedup cost reduction | **Effort**: Medium

#### Implementation
Cache deduplication decisions to avoid redundant LLM calls:

```python
# Deduplication cache key: (entity_name, candidate_name, similarity_score)
cache_key = f"{entity.name}:{candidate.name}:{similarity:.2f}"

if cache_key in dedup_cache:
    return dedup_cache[cache_key]

# Only call LLM if not cached
result = await llm_client.dedupe_entities(entity, candidate)
dedup_cache[cache_key] = result
return result
```

#### Benefits
- Avoids re-deduplicating same entity pairs
- Especially effective for common entities (e.g., "Claude", "Python")
- Can use Redis for distributed caching

#### Action Items
1. Implement deduplication cache with TTL (24 hours)
2. Add cache hit/miss metrics
3. Configure cache size limits
4. Consider Redis for multi-worker deployments

---

### Strategy 5: **Aggressive Prompt Compression** 📉
**Priority**: MEDIUM | **Impact**: 30-40% token reduction | **Effort**: Low

#### Implementation
Ensure prompt compression is applied to all large context prompts:

```python
# Already implemented in graphiti_core/utils/prompt_compression.py
compressor = get_prompt_compressor()

# Apply to deduplication context
compressed_context, stats = compressor.compress_existing_entities(
    existing_entities,
    target_tokens=2000,
    compression_ratio=0.6  # 40% reduction
)
```

#### Benefits
- 60-80% compression with minimal quality loss (LLMLingua)
- Reduces costs and latency
- Already implemented, just needs consistent usage

#### Action Items
1. Audit all LLM calls for compression opportunities
2. Enable compression for deduplication prompts
3. Enable compression for attribute extraction
4. Monitor compression stats and quality impact

---

### Strategy 6: **Deferred Attribute Extraction** ⏱️
**Priority**: LOW | **Impact**: 20-30% latency reduction | **Effort**: Low

#### Implementation
Extract attributes asynchronously after episode is saved:

```python
# Current: Synchronous
entities = await extract_nodes(episode)
entities = await extract_attributes_from_nodes(entities)  # Blocks
await save_entities(entities)

# Optimized: Deferred
entities = await extract_nodes(episode)
await save_entities(entities)  # Save with empty attributes

# Background task
asyncio.create_task(extract_and_update_attributes(entities))
```

#### Benefits
- Faster episode ingestion response time
- Attributes extracted in background
- Better user experience (faster feedback)

#### Trade-offs
- Attributes not immediately available
- Requires update mechanism
- May complicate retrieval logic

---

### Strategy 7: **Incremental Deduplication** 🔄
**Priority**: LOW | **Impact**: Variable | **Effort**: High

#### Implementation
Only deduplicate against recent entities instead of entire graph:

```python
# Current: Search entire graph
candidates = await search_similar_entities(entity, limit=100)

# Optimized: Time-windowed search
candidates = await search_similar_entities(
    entity, 
    limit=50,
    created_after=now - timedelta(days=7)  # Only recent entities
)
```

#### Benefits
- Reduces deduplication search space
- Faster for large graphs
- Lower LLM costs

#### Trade-offs
- May miss older duplicates
- Requires periodic full deduplication
- Complexity in managing time windows

---

## Recommended Implementation Roadmap

### Phase 1: Quick Wins (Week 1)
**Goal**: 3-5x throughput improvement with minimal changes

1. ✅ **Enable batch processing**: Set `CHUTES_ENABLE_BATCH_PROCESSING=true`
2. ✅ **Enable parallel processing**: Modify worker to process 5-10 episodes concurrently
3. ✅ **Batch embedding generation**: Update embedding calls to use batching
4. ✅ **Apply prompt compression**: Ensure compression is used in deduplication

**Expected Impact**: 
- Throughput: 1 episode/10s → 5-10 episodes/10s
- Cost: 30-40% reduction in LLM tokens
- Latency: 50-60% reduction in wall-clock time

### Phase 2: Optimization (Week 2-3)
**Goal**: Further improve efficiency and reduce costs

1. ⚙️ **Implement deduplication caching**: Redis-backed cache for dedup decisions
2. ⚙️ **Deferred attribute extraction**: Background attribute processing
3. ⚙️ **Monitoring and metrics**: Track batch sizes, cache hits, compression ratios
4. ⚙️ **Auto-tuning**: Dynamically adjust batch sizes based on performance

**Expected Impact**:
- Cost: Additional 20-30% reduction
- Latency: Additional 20-30% reduction
- Reliability: Better handling of rate limits and failures

### Phase 3: Advanced (Week 4+)
**Goal**: Scale to high-volume production workloads

1. 🔬 **Incremental deduplication**: Time-windowed dedup with periodic full scans
2. 🔬 **Adaptive batching**: ML-based batch size optimization
3. 🔬 **Distributed caching**: Multi-worker cache coordination
4. 🔬 **Pipeline profiling**: Detailed performance analysis and bottleneck identification

---

## Configuration Reference

### Environment Variables

```bash
# Batch Processing
CHUTES_ENABLE_BATCH_PROCESSING=true
BATCH_SIZE=5                          # Episodes per batch
BATCH_TIMEOUT_SECONDS=10              # Max wait for batch accumulation

# Parallel Processing  
MAX_CONCURRENT_EPISODES=10            # Parallel episode processing
SEMAPHORE_LIMIT=50                    # Max concurrent coroutines

# Deduplication
DEDUP_SIMILARITY_THRESHOLD=0.6        # Similarity threshold
DEDUP_CACHE_TTL_HOURS=24             # Cache expiration
DEDUP_CACHE_MAX_SIZE=10000           # Max cache entries

# Prompt Compression
ENABLE_PROMPT_COMPRESSION=true
COMPRESSION_TARGET_TOKENS=2000
COMPRESSION_RATIO=0.6                 # 40% reduction

# Embedding
EMBEDDING_BATCH_SIZE=100              # Embeddings per API call
```

---

## Monitoring Metrics

### Key Performance Indicators

1. **Throughput**: Episodes processed per minute
2. **Latency**: Average time per episode (P50, P95, P99)
3. **LLM Costs**: Total tokens per episode
4. **API Calls**: LLM calls per episode
5. **Cache Hit Rate**: Deduplication cache effectiveness
6. **Compression Ratio**: Average token reduction
7. **Batch Utilization**: Average batch size vs. target
8. **Error Rate**: Failed episodes / total episodes

### Alerting Thresholds

```yaml
alerts:
  - metric: throughput
    threshold: < 5 episodes/minute
    severity: warning
    
  - metric: latency_p95
    threshold: > 30 seconds
    severity: warning
    
  - metric: llm_cost_per_episode
    threshold: > $0.10
    severity: info
    
  - metric: error_rate
    threshold: > 5%
    severity: critical
```

---

## Conclusion

The Graphiti ingestion pipeline has significant optimization opportunities that can deliver **5-10x throughput improvements** with relatively low effort. The infrastructure for batching and parallelization already exists but is not fully utilized.

**Immediate Actions**:
1. Enable batch processing (`CHUTES_ENABLE_BATCH_PROCESSING=true`)
2. Implement parallel episode processing in worker
3. Batch embedding generation
4. Ensure prompt compression is consistently applied

**Expected Results**:
- **Throughput**: 5-10x improvement
- **Cost**: 40-60% reduction
- **Latency**: 50-70% reduction
- **Scalability**: Support for 100+ episodes/minute

These optimizations will make Graphiti production-ready for high-volume workloads while significantly reducing operational costs.

