# Ingestion Pipeline Performance Analysis

## Overview

This document analyzes the Graphiti ingestion pipeline performance, identifies bottlenecks, and proposes optimization strategies.

## Current Pipeline Architecture

### Episode Ingestion Flow (`add_episode_resilient`)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. CREATE EPISODIC NODE                                     │
│    - Validate group_id                                      │
│    - Create EpisodicNode object                             │
│    - Initialize resilient ingestion state                   │
│    Time: <1ms                                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. STAGE 1: EXTRACT NODES (LLM CALL)                       │
│    - Retrieve previous episodes for context                 │
│    - Call LLM for entity extraction                         │
│    - Parse and validate extracted entities                  │
│    - Retry on failure (up to 3 attempts)                    │
│    Time: 10-60s (LLM dependent)                             │
│    Bottleneck: ⭐⭐⭐⭐⭐                                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. STAGE 2: RESOLVE NODES (DEDUPLICATION)                  │
│    - Check for duplicate entities in database               │
│    - Calculate embedding similarities                       │
│    - Merge duplicates                                       │
│    - Create UUID mapping                                    │
│    Time: 5-30s (depends on # of existing entities)          │
│    Bottleneck: ⭐⭐⭐                                         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. STAGE 3: EXTRACT EDGES (LLM CALL)                       │
│    - Call LLM for relationship extraction                   │
│    - Parse extracted relationships                          │
│    - Resolve edge pointers using UUID map                   │
│    - Retry on failure (up to 3 attempts)                    │
│    Time: 10-60s (LLM dependent)                             │
│    Bottleneck: ⭐⭐⭐⭐⭐                                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. RESOLVE EDGES & EXTRACT ATTRIBUTES (PARALLEL)           │
│    ├─ Resolve extracted edges                              │
│    └─ Extract node attributes (LLM CALL)                   │
│    Time: 10-60s (LLM dependent, but parallel)               │
│    Bottleneck: ⭐⭐⭐⭐                                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. BUILD EPISODIC EDGES                                     │
│    - Create MENTIONS edges (episode → entities)             │
│    - Build IS_DUPLICATE_OF edges                            │
│    - Calculate episode statistics                           │
│    Time: <1s                                                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. SAVE TO DATABASE (BULK)                                 │
│    - Save episode node                                      │
│    - Save entity nodes (bulk)                               │
│    - Save edges (bulk)                                      │
│    - Execute merge operations                               │
│    Time: 1-5s                                               │
│    Bottleneck: ⭐                                            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 8. UPDATE CENTRALITY (ASYNC, NON-BLOCKING)                 │
│    - Call Rust centrality service for new nodes            │
│    - Update degree, pagerank, betweenness                   │
│    Time: 2-10s (async, doesn't block)                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Performance Baseline

### Observed Performance (from logs)

**Single Episode:**
- Total time: **293.91 seconds (~5 minutes)**
- Entities created: 3
- LLM provider: Ollama (gemma3:12b)

**Time Breakdown (Estimated):**
```
Stage 1 (Extract Nodes):      60-90s   (30-35%)
Stage 2 (Resolve Nodes):       20-40s   (10-15%)
Stage 3 (Extract Edges):       60-90s   (30-35%)
Stage 5 (Extract Attributes):  40-60s   (15-20%)
Database Operations:           5-10s    (2-3%)
Other (overhead):              5-10s    (2-3%)
────────────────────────────────────────────────
Total:                         ~290s    (100%)
```

**LLM Calls per Episode:**
- Entity extraction: 1 call
- Edge extraction: 1 call
- Attribute extraction: 1 call per entity (3 calls for 3 entities)
- **Total: ~5 LLM calls per episode**

---

## Bottleneck Analysis

### 1. LLM Latency (⭐⭐⭐⭐⭐ Critical)

**Impact:** 70-80% of total ingestion time

**Current State:**
- Using Ollama with gemma3:12b model
- Each LLM call takes 10-60 seconds
- Sequential LLM calls (can't parallelize easily)

**Why It's Slow:**
- Large context windows (previous episodes for context)
- Complex prompts with examples
- Model inference time (especially for larger models)
- Network latency (if Ollama is remote)

**Optimization Opportunities:**
1. **Reduce Context Size**
   - Limit previous episodes (currently using `RELEVANT_SCHEMA_LIMIT`)
   - Truncate episode content (use `MAX_EPISODE_CONTENT_CHARS`)
   - Reduce deduplication candidates

2. **Faster LLM Provider**
   - Switch to faster models (smaller models, quantized versions)
   - Use streaming responses
   - Consider cloud providers (OpenAI, Anthropic) for speed

3. **Prompt Optimization**
   - Shorter prompts with fewer examples
   - Enable prompt compression (`ENABLE_PROMPT_COMPRESSION=true`)
   - Use structured output formats (JSON mode)

4. **Batch Processing**
   - Extract entities and edges in a single LLM call
   - Process multiple episodes in one batch

---

### 2. Deduplication Overhead (⭐⭐⭐ Medium)

**Impact:** 10-15% of total ingestion time

**Current State:**
- Checks for duplicates on every episode
- Calculates embedding similarities
- Queries database for existing entities

**Why It's Slow:**
- Embedding similarity calculations (CPU intensive)
- Database queries for candidate entities
- Grows with graph size (more entities = more comparisons)

**Optimization Opportunities:**
1. **Reduce Deduplication Frequency**
   - Don't deduplicate on every episode
   - Run periodic batch deduplication instead
   - Use `MAX_DEDUP_CANDIDATES` to limit comparisons

2. **Smarter Candidate Selection**
   - Use BM25 keyword search first (faster than embeddings)
   - Only calculate embeddings for top candidates
   - Cache embedding similarities

3. **Async Deduplication**
   - Skip deduplication during ingestion
   - Run deduplication as background job
   - Trade-off: temporary duplicates vs. faster ingestion

---

### 3. Sequential Processing (⭐⭐⭐ Medium)

**Impact:** Can't parallelize LLM calls due to dependencies

**Current State:**
- Must extract nodes before extracting edges
- Must resolve nodes before resolving edges
- Some parallelism exists (edge resolution + attribute extraction)

**Why It's Sequential:**
- Edges depend on node UUIDs
- Deduplication affects UUID mapping
- Logical dependencies between stages

**Optimization Opportunities:**
1. **Speculative Execution**
   - Start edge extraction before node resolution completes
   - Adjust edge pointers after resolution
   - Risk: wasted LLM calls if nodes change

2. **Batch Multiple Episodes**
   - Process multiple episodes together
   - Share context across episodes
   - Amortize LLM overhead

3. **Pipeline Parallelism**
   - Process different stages of different episodes in parallel
   - Episode 1: Stage 3, Episode 2: Stage 2, Episode 3: Stage 1
   - Requires careful orchestration

---

### 4. Database Operations (⭐ Low)

**Impact:** 2-3% of total ingestion time

**Current State:**
- Already using bulk operations
- Efficient MERGE queries
- Connection pooling

**Why It's Fast:**
- Bulk inserts/updates
- Optimized Cypher queries
- FalkorDB is fast for writes

**Optimization Opportunities:**
1. **Larger Batches**
   - Combine multiple episodes into single transaction
   - Trade-off: all-or-nothing on failure

2. **Async Writes**
   - Return success before database write completes
   - Write to queue, process in background
   - Risk: data loss on failure

---

## Current Optimization Settings

### Environment Variables (from .env)

```bash
# Prompt Optimization
MAX_CONTEXT_EPISODES=5                    # Limit previous episodes
MAX_DEDUP_CANDIDATES=5                    # Limit dedup candidates
MAX_EPISODE_CONTENT_CHARS=6000            # Truncate content
MAX_DEDUP_EXISTING_NODES=10               # Limit existing nodes

# Embedding Optimization
EMBEDDING_BATCH_SIZE=100

# Prompt Compression
ENABLE_PROMPT_COMPRESSION=true
COMPRESSION_TARGET_TOKENS=2000

# Rate Limiting
GLOBAL_RATE_LIMIT=200
GROUP_RATE_LIMIT=50
```

### Code-Level Optimizations

1. **Resilient Ingestion** (`add_episode_resilient`)
   - Granular retry logic per stage
   - Caches progress to avoid re-doing work
   - Prevents data loss on LLM failures

2. **Parallel Operations**
   - Edge resolution + attribute extraction run in parallel
   - Uses `semaphore_gather` for controlled concurrency

3. **Bulk Database Operations**
   - `add_nodes_and_edges_bulk` for efficient writes
   - Single transaction for all episode data

---

## Optimization Strategies

### Strategy 1: Reduce LLM Latency (Quick Wins)

**Goal:** Reduce LLM call time by 30-50%

**Actions:**
1. **Use Faster Model**
   ```bash
   # Switch to smaller, faster model
   LLM_MODEL=gemma2:2b  # Instead of gemma3:12b
   ```

2. **Reduce Context**
   ```bash
   MAX_CONTEXT_EPISODES=3           # Reduce from 5
   MAX_EPISODE_CONTENT_CHARS=4000   # Reduce from 6000
   ```

3. **Enable All Optimizations**
   ```bash
   ENABLE_PROMPT_COMPRESSION=true
   COMPRESSION_TARGET_TOKENS=1500   # More aggressive
   ```

**Expected Impact:** 30-50% faster (290s → 145-200s)

---

### Strategy 2: Async Deduplication (Medium Effort)

**Goal:** Skip deduplication during ingestion, run as background job

**Actions:**
1. **Disable Inline Deduplication**
   - Modify `add_episode_resilient` to skip Stage 2
   - Save entities without deduplication

2. **Background Deduplication Job**
   - Run periodic deduplication (every 5-10 minutes)
   - Process all entities in batch
   - More efficient than per-episode deduplication

**Expected Impact:** 10-15% faster (290s → 245-260s)

**Trade-off:** Temporary duplicates until background job runs

---

### Strategy 3: Batch Episode Processing (High Effort)

**Goal:** Process multiple episodes in single LLM call

**Actions:**
1. **Batch API Endpoint**
   - Accept multiple episodes in one request
   - Extract entities from all episodes together
   - Share context across episodes

2. **Bulk Extraction**
   - Single LLM call for all episodes
   - Parse results and split by episode
   - Bulk database write

**Expected Impact:** 50-70% faster per episode (290s → 90-145s per episode)

**Trade-off:** Higher latency for first episode, but better throughput

---

### Strategy 4: Speculative Edge Extraction (High Risk)

**Goal:** Start edge extraction before node resolution completes

**Actions:**
1. **Parallel Stages**
   - Start Stage 3 (edge extraction) while Stage 2 (node resolution) runs
   - Use preliminary node UUIDs
   - Adjust edge pointers after resolution

2. **Optimistic Execution**
   - Assume no duplicates will be found
   - Rollback if assumption is wrong

**Expected Impact:** 20-30% faster (290s → 200-230s)

**Trade-off:** Wasted LLM calls if duplicates are found

---

## Recommended Optimization Plan

### Phase 1: Quick Wins (1 hour, 30-50% speedup)

1. **Optimize LLM Settings**
   ```bash
   # Add to .env
   MAX_CONTEXT_EPISODES=3
   MAX_EPISODE_CONTENT_CHARS=4000
   COMPRESSION_TARGET_TOKENS=1500
   ```

2. **Consider Faster Model**
   - Test with smaller model (gemma2:2b or llama3.2:3b)
   - Measure quality vs. speed trade-off

3. **Monitor Results**
   - Check logs for new timing
   - Validate entity extraction quality

**Expected Result:** 290s → 145-200s per episode

---

### Phase 2: Async Deduplication (1 day, additional 10-15% speedup)

1. **Add Configuration Flag**
   ```bash
   ENABLE_INLINE_DEDUPLICATION=false
   ```

2. **Modify `add_episode_resilient`**
   - Skip Stage 2 if flag is false
   - Save entities without deduplication

3. **Background Deduplication Job**
   - Use existing cron job infrastructure
   - Run every 5-10 minutes
   - Process all groups

**Expected Result:** 145-200s → 125-170s per episode

---

### Phase 3: Batch Processing (1 week, additional 50-70% speedup)

1. **New Bulk API Endpoint**
   - `/ingest/episodes/bulk`
   - Accept array of episodes

2. **Bulk Extraction Logic**
   - Combine episodes into single prompt
   - Parse and split results
   - Bulk database write

3. **Worker Support**
   - Process batches from queue
   - Configurable batch size

**Expected Result:** 125-170s → 40-85s per episode (in batches)

---

## Monitoring and Metrics

### Key Metrics to Track

1. **Episode Processing Time**
   - Total time per episode
   - Time per stage
   - LLM call latency

2. **LLM Performance**
   - Tokens per request
   - Response time
   - Error rate

3. **Deduplication Efficiency**
   - Duplicates found per episode
   - Time spent on deduplication
   - False positive rate

4. **Throughput**
   - Episodes per minute
   - Entities per minute
   - Queue depth

### Logging Enhancements

Add detailed timing logs:
```python
logger.info(f"Stage 1 (Extract Nodes): {stage1_time:.2f}s")
logger.info(f"Stage 2 (Resolve Nodes): {stage2_time:.2f}s")
logger.info(f"Stage 3 (Extract Edges): {stage3_time:.2f}s")
logger.info(f"Stage 5 (Extract Attributes): {stage5_time:.2f}s")
logger.info(f"Database Operations: {db_time:.2f}s")
```

---

## Conclusion

**Current State:**
- Episode processing: ~290 seconds (~5 minutes)
- Main bottleneck: LLM latency (70-80% of time)
- Secondary bottleneck: Deduplication (10-15% of time)

**Optimization Potential:**
- **Phase 1 (Quick Wins):** 30-50% faster → 145-200s
- **Phase 2 (Async Dedup):** Additional 10-15% → 125-170s
- **Phase 3 (Batch Processing):** Additional 50-70% → 40-85s

**Total Potential Speedup:** 3-7x faster (290s → 40-85s per episode)

**Next Steps:**
1. Implement Phase 1 optimizations (quick wins)
2. Measure impact and validate quality
3. Proceed to Phase 2 if quality is acceptable
4. Consider Phase 3 for high-throughput scenarios

---

**Created:** 2025-10-04  
**Status:** Analysis complete, ready for optimization

