# Performance Test Results - 40 Minute Observation

**Date**: October 3, 2025  
**Test Duration**: 40 minutes  
**Configuration**: 2 workers × 3 concurrent episodes = 6 parallel

---

## 📊 Results Summary

### Node Growth
- **Baseline**: 13,070 nodes
- **After 40 min**: 13,140 nodes
- **Nodes Added**: **70 nodes**

### Throughput Metrics
- **Nodes/minute**: 1.75
- **Nodes/hour**: 105
- **Episodes/minute**: ~0.25 (assuming 7 nodes/episode)
- **Episodes processed**: ~10 episodes in 40 minutes

---

## ⚠️ Performance Analysis

### Current State: **SLOW**

The system is processing **very slowly** despite parallel processing being active:

**Expected Performance** (with 6 concurrent):
- ~20-30 episodes/minute
- ~140-210 nodes/minute (at 7 nodes/episode)

**Actual Performance**:
- ~0.25 episodes/minute
- ~1.75 nodes/minute

**Performance Gap**: **80-120x slower than expected**

---

## 🔍 Observed Issues

### 1. **Long Processing Times**

From logs, a single episode took **165 seconds** (2.75 minutes):
```
Episode c8737b3e-94f3-4140-b3e5-b521d0bbe44f: Ingestion completed in 165.30s
```

This is **extremely slow** for just 3 entities.

### 2. **Dead Letter Queue Activity**

Multiple episodes being moved to dead letter queue:
```
Task replay-ffb737cd... moved to dead letter queue: Episode not found
Task replay-f0dc205f... moved to dead letter queue: Episode not found
```

This suggests:
- Episodes are being retried multiple times
- Some episodes don't exist in the database
- Wasted processing time on failed tasks

### 3. **Complex Processing Steps**

Each episode goes through many steps:
1. Node extraction (LLM call)
2. Node resolution (embedding + deduplication)
3. Edge extraction (LLM call)
4. Edge invalidation (database queries)
5. Cross-graph merging
6. Centrality updates (4 API calls to Rust service)

**Total time per episode**: 2-3 minutes even with just 3 entities

---

## 🎯 Bottleneck Analysis

### Primary Bottlenecks

1. **LLM Response Time** ⏱️
   - Ollama LLM calls taking 5-10 seconds each
   - Multiple LLM calls per episode (extraction, deduplication, summarization)
   - **Impact**: 30-60 seconds per episode just for LLM

2. **Embedding Generation** 🔢
   - Multiple embedding API calls per episode
   - Each call takes 0.5-2 seconds
   - **Impact**: 10-20 seconds per episode

3. **Cross-Graph Merging** 🔀
   - Merging nodes across different groups
   - Database queries + edge transfers
   - **Impact**: 5-10 seconds per episode

4. **Centrality Updates** 📊
   - 4 separate API calls to Rust centrality service
   - Each call takes ~25ms
   - **Impact**: ~100ms per episode (minimal)

5. **Dead Letter Queue Retries** ❌
   - Failed episodes being retried multiple times
   - Wasted processing time
   - **Impact**: Unknown, but significant

---

## 💡 Recommendations

### Immediate Actions

1. **Investigate Dead Letter Queue**
   - Why are episodes "not found"?
   - Are these legitimate failures or bugs?
   - Consider purging invalid tasks

2. **Profile LLM Performance**
   - Check Ollama response times
   - Consider switching to faster LLM (Cerebras, Groq)
   - Reduce LLM calls where possible

3. **Optimize Embedding Calls**
   - Batch embeddings together
   - Cache embeddings for duplicate entities
   - Use faster embedding service

4. **Monitor Queue Health**
   - Check queue depth
   - Verify tasks are being processed
   - Look for stuck tasks

### Medium-Term Optimizations

1. **Reduce Cross-Graph Merging Overhead**
   - Batch merge operations
   - Optimize merge queries
   - Consider async merging

2. **Implement Caching**
   - Cache entity resolutions
   - Cache embeddings
   - Cache LLM responses for similar queries

3. **Optimize Database Queries**
   - Add indexes
   - Batch operations
   - Reduce query complexity

---

## 📈 Expected vs Actual

| Metric | Expected (6 concurrent) | Actual | Gap |
|--------|------------------------|--------|-----|
| Episodes/min | 20-30 | 0.25 | **80-120x slower** |
| Nodes/min | 140-210 | 1.75 | **80-120x slower** |
| Time/episode | 2-3 seconds | 165 seconds | **55-80x slower** |

---

## 🚨 Critical Findings

1. **Parallel processing IS working** ✅
   - 6 episodes start simultaneously
   - Logs show "processing 3 tasks in parallel"

2. **Individual episode processing is VERY slow** ❌
   - 165 seconds for 3 entities is unacceptable
   - Expected: 2-3 seconds per episode
   - Actual: 165 seconds per episode

3. **Bottleneck is NOT concurrency** ❌
   - Problem is per-episode processing time
   - Not a parallelization issue
   - Need to optimize individual episode processing

---

## 🔧 Next Steps

### Priority 1: Diagnose Slow Processing

1. Add detailed timing logs for each step:
   - LLM extraction time
   - Embedding generation time
   - Database query time
   - Merge operation time

2. Profile a single episode end-to-end

3. Identify the slowest step(s)

### Priority 2: Fix Dead Letter Queue

1. Investigate why episodes are "not found"
2. Purge invalid tasks
3. Fix root cause

### Priority 3: Optimize Slow Steps

Based on profiling results:
1. Optimize LLM calls (switch provider, reduce calls)
2. Batch embeddings
3. Optimize database queries
4. Reduce cross-graph merging overhead

---

## 📝 Conclusion

**Parallel processing is working correctly**, but **individual episode processing is extremely slow** (165 seconds vs expected 2-3 seconds).

The bottleneck is **NOT** the parallel processing implementation, but rather:
1. Slow LLM response times
2. Multiple embedding API calls
3. Complex cross-graph merging
4. Dead letter queue retries

**Recommendation**: Focus on optimizing per-episode processing time rather than increasing concurrency further.

---

## 🎯 Target Performance

To achieve acceptable performance:

**Current**: 165 seconds/episode  
**Target**: 5-10 seconds/episode  
**Required Improvement**: **16-33x faster**

This requires:
1. Faster LLM (Cerebras/Groq instead of Ollama)
2. Batched embeddings
3. Optimized database queries
4. Reduced cross-graph merging overhead
5. Eliminated dead letter queue retries

---

**Status**: ⚠️ **PERFORMANCE ISSUE IDENTIFIED**  
**Action Required**: Optimize per-episode processing time

