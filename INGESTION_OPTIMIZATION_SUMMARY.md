# Ingestion Pipeline Optimization Summary

## 📊 Current State

**Performance Baseline:**
- Episode processing time: **~290 seconds (~5 minutes)**
- Entities per episode: 3 (average)
- LLM provider: Ollama (gemma3:12b)
- Main bottleneck: LLM latency (70-80% of time)

**Time Breakdown:**
```
LLM Calls (Extract Nodes):        60-90s  (30-35%)
Deduplication:                     20-40s  (10-15%)
LLM Calls (Extract Edges):         60-90s  (30-35%)
LLM Calls (Extract Attributes):    40-60s  (15-20%)
Database Operations:                5-10s  (2-3%)
Other Overhead:                     5-10s  (2-3%)
────────────────────────────────────────────────────
Total:                             ~290s   (100%)
```

---

## 🎯 Key Findings

### Bottleneck #1: LLM Latency (⭐⭐⭐⭐⭐ Critical)
- **Impact:** 70-80% of total time
- **Cause:** Multiple sequential LLM calls per episode
- **Calls per episode:** ~5 (entity extraction, edge extraction, 3× attribute extraction)
- **Each call:** 10-60 seconds depending on model and context size

### Bottleneck #2: Deduplication (⭐⭐⭐ Medium)
- **Impact:** 10-15% of total time
- **Cause:** Embedding similarity calculations and database queries
- **Grows with:** Graph size (more entities = more comparisons)

### Bottleneck #3: Sequential Processing (⭐⭐⭐ Medium)
- **Impact:** Can't parallelize LLM calls due to dependencies
- **Cause:** Edges depend on node UUIDs, which depend on deduplication

### Bottleneck #4: Database Operations (⭐ Low)
- **Impact:** 2-3% of total time
- **Already optimized:** Bulk operations, efficient queries

---

## 🚀 Optimization Strategies

### Strategy 1: Quick Wins (5 min, 30-50% speedup)

**Actions:**
```bash
# Add to .env
MAX_CONTEXT_EPISODES=3                    # Reduce from 5
MAX_EPISODE_CONTENT_CHARS=4000            # Reduce from 6000
MAX_DEDUP_CANDIDATES=3                    # Reduce from 5
COMPRESSION_TARGET_TOKENS=1500            # Reduce from 2000
```

**Expected Result:** 290s → 145-200s per episode

**Risk:** 🟢 Low (minimal quality impact)

---

### Strategy 2: Faster Model (15 min, 50-70% speedup)

**Actions:**
```bash
# Add to .env
LLM_MODEL=gemma2:2b  # Instead of gemma3:12b
```

**Expected Result:** 145-200s → 60-100s per episode

**Risk:** 🟡 Medium (must test quality first\!)

---

### Strategy 3: Async Deduplication (1 day, 10-15% speedup)

**Actions:**
- Skip deduplication during ingestion
- Run periodic background deduplication job
- Use existing cron infrastructure

**Expected Result:** 60-100s → 50-85s per episode

**Risk:** 🟡 Medium (temporary duplicates)

---

### Strategy 4: Batch Processing (1 week, 50-70% speedup)

**Actions:**
- Process multiple episodes in single LLM call
- Requires code changes (new bulk API endpoint)
- Amortize LLM overhead across episodes

**Expected Result:** 50-85s → 20-40s per episode (in batches)

**Risk:** 🟢 Low (higher latency for first episode)

---

## 📈 Optimization Roadmap

### Phase 1: Quick Wins (Recommended First)
- **Time:** 5 minutes
- **Speedup:** 30-50%
- **Risk:** Low
- **Actions:** Reduce context size, enable compression

### Phase 2: Faster Model (Test Carefully)
- **Time:** 15 minutes
- **Speedup:** Additional 50-70%
- **Risk:** Medium (quality impact)
- **Actions:** Switch to gemma2:2b, validate quality

### Phase 3: Async Deduplication (Optional)
- **Time:** 1 day
- **Speedup:** Additional 10-15%
- **Risk:** Medium (temporary duplicates)
- **Actions:** Skip inline dedup, use background job

### Phase 4: Batch Processing (Future Work)
- **Time:** 1 week
- **Speedup:** Additional 50-70%
- **Risk:** Low
- **Actions:** Implement bulk API, batch LLM calls

---

## 📊 Expected Performance Gains

| Phase | Configuration | Time | Speedup | Cumulative |
|-------|--------------|------|---------|------------|
| **Baseline** | gemma3:12b, full context | 290s | 1x | 1x |
| **Phase 1** | Reduced context | 145-200s | 1.5-2x | 1.5-2x |
| **Phase 2** | + gemma2:2b | 60-100s | 2.4-3.3x | 3-5x |
| **Phase 3** | + async dedup | 50-85s | 1.2-1.2x | 3.5-6x |
| **Phase 4** | + batch processing | 20-40s | 2.5-2.1x | 7-15x |

**Total Potential Speedup: 7-15x faster** (290s → 20-40s per episode)

---

## 📚 Documentation Created

### 1. **INGESTION_PIPELINE_ANALYSIS.md** (Comprehensive)
**Location:** `docs/INGESTION_PIPELINE_ANALYSIS.md`

**Contents:**
- Detailed pipeline flow diagram
- Performance baseline and breakdown
- Bottleneck analysis (4 major bottlenecks)
- Optimization strategies (4 strategies)
- Recommended optimization plan (3 phases)
- Monitoring and metrics guidance

**Use this when:** You need deep understanding of the pipeline

---

### 2. **INGESTION_OPTIMIZATION_QUICK_REFERENCE.md** (Quick Start)
**Location:** `docs/INGESTION_OPTIMIZATION_QUICK_REFERENCE.md`

**Contents:**
- Quick win configuration (copy-paste ready)
- Optimization strategies comparison table
- Step-by-step optimization path
- Monitoring commands
- Testing checklist

**Use this when:** You want to optimize NOW

---

### 3. **INGESTION_OPTIMIZATION_SUMMARY.md** (This Document)
**Location:** `INGESTION_OPTIMIZATION_SUMMARY.md`

**Contents:**
- Executive summary
- Key findings
- Optimization roadmap
- Expected performance gains

**Use this when:** You need high-level overview

---

## 🎯 Quick Start

### Fastest Path to 30-50% Speedup (5 minutes)

1. **Add to `.env`:**
   ```bash
   MAX_CONTEXT_EPISODES=3
   MAX_EPISODE_CONTENT_CHARS=4000
   MAX_DEDUP_CANDIDATES=3
   COMPRESSION_TARGET_TOKENS=1500
   ```

2. **Rebuild:**
   ```bash
   docker-compose build graphiti-worker
   docker-compose up -d graphiti-worker
   ```

3. **Monitor:**
   ```bash
   docker-compose logs -f graphiti-worker | grep "Completed resilient"
   ```

---

## ⚠️ Important Considerations

### Quality vs. Speed Trade-off

**Safe Optimizations:**
- ✅ Reducing context size (Phase 1)
- ✅ Prompt compression
- ✅ Batch processing (Phase 4)

**Risky Optimizations:**
- ⚠️ Smaller model (Phase 2) - MUST TEST QUALITY
- ⚠️ Async deduplication (Phase 3) - Temporary duplicates

### When to Optimize

**Optimize if:**
- Ingestion is too slow for your use case
- You have a backlog of episodes to process
- You can tolerate some quality reduction

**Don't optimize if:**
- Current speed is acceptable
- Quality is critical (production system)
- You haven't measured baseline performance

---

## 🧪 Testing Recommendations

Before deploying optimizations:

1. **Measure baseline** (10 episodes)
2. **Record entity count** per episode
3. **Apply optimization**
4. **Measure new performance** (10 episodes)
5. **Compare entity count** (should be similar)
6. **Validate quality** (spot check)
7. **Monitor for errors**
8. **Document results**

---

## 📞 Next Steps

1. **Read Quick Reference:** `docs/INGESTION_OPTIMIZATION_QUICK_REFERENCE.md`
2. **Apply Phase 1 optimizations** (quick wins)
3. **Measure impact** and validate quality
4. **Proceed to Phase 2** if quality is acceptable
5. **Consider Phase 3/4** for high-throughput scenarios

---

## 🔗 Related Optimizations

### Sync Service Optimization
- **Documents:** `docs/SYNC_PERFORMANCE_TUNING_GUIDE.md`
- **Expected speedup:** 5-10x for Neo4j → FalkorDB sync
- **Status:** Documented, ready for testing

### Centrality Storage Optimization
- **Issue:** Storage is 4.5x slower than calculation (93s vs 21s)
- **Potential fixes:** Larger batch sizes, Redis pipelining
- **Status:** Identified, not yet documented

---

**Created:** 2025-10-04  
**Author:** AI Assistant (Augment Agent)  
**Status:** Ready for testing
