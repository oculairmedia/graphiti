# Ingestion Pipeline Optimization - Quick Reference

## 🎯 TL;DR

**Current Performance:** ~290 seconds (~5 minutes) per episode  
**Main Bottleneck:** LLM latency (70-80% of time)  
**Quick Win:** Reduce context size and use faster model → **30-50% faster**

---

## 📊 Current Performance Breakdown

```
┌─────────────────────────────────────────────────────┐
│ Episode Ingestion Time: ~290 seconds                │
├─────────────────────────────────────────────────────┤
│ LLM Calls (Extract Nodes):        60-90s  (30-35%) │
│ Deduplication:                     20-40s  (10-15%) │
│ LLM Calls (Extract Edges):         60-90s  (30-35%) │
│ LLM Calls (Extract Attributes):    40-60s  (15-20%) │
│ Database Operations:                5-10s  (2-3%)   │
│ Other Overhead:                     5-10s  (2-3%)   │
└─────────────────────────────────────────────────────┘

Total LLM Time: ~200s (70%)
Total Non-LLM Time: ~90s (30%)
```

---

## 🚀 Quick Win Optimization (5 minutes, 30-50% faster)

### Add to `.env`:

```bash
# ============================================================================
# INGESTION PIPELINE OPTIMIZATION - QUICK WINS
# ============================================================================

# Reduce LLM Context (BIGGEST IMPACT)
MAX_CONTEXT_EPISODES=3                    # Reduce from 5 (40% less context)
MAX_EPISODE_CONTENT_CHARS=4000            # Reduce from 6000 (33% less content)
MAX_DEDUP_CANDIDATES=3                    # Reduce from 5 (40% less dedup work)
MAX_DEDUP_EXISTING_NODES=5                # Reduce from 10 (50% less dedup work)

# Aggressive Prompt Compression
ENABLE_PROMPT_COMPRESSION=true            # Already enabled
COMPRESSION_TARGET_TOKENS=1500            # Reduce from 2000 (25% more compression)

# Consider Faster Model (TEST QUALITY FIRST!)
# LLM_MODEL=gemma2:2b                     # Much faster than gemma3:12b
# LLM_MODEL=llama3.2:3b                   # Alternative fast model
```

### Rebuild and Restart:

```bash
docker-compose build graphiti-worker
docker-compose up -d graphiti-worker
docker-compose logs -f graphiti-worker
```

### Expected Result:

- **Before:** ~290 seconds per episode
- **After:** ~145-200 seconds per episode
- **Speedup:** 30-50% faster

---

## 📈 Optimization Strategies Comparison

| Strategy | Effort | Speedup | Risk | Time Investment |
|----------|--------|---------|------|-----------------|
| **Quick Wins** (Reduce context) | Low | 30-50% | 🟢 Low | 5 min |
| **Faster Model** (gemma2:2b) | Low | 50-70% | 🟡 Medium* | 15 min |
| **Async Deduplication** | Medium | 10-15% | 🟡 Medium** | 1 day |
| **Batch Processing** | High | 50-70% | 🟢 Low | 1 week |
| **Speculative Execution** | High | 20-30% | 🔴 High | 1 week |

*Risk: Quality may decrease with smaller model  
**Risk: Temporary duplicates until background job runs

---

## 🔧 Detailed Optimization Options

### Option 1: Reduce LLM Context (Recommended First Step)

**What it does:** Reduces the amount of text sent to LLM

**Parameters:**
```bash
MAX_CONTEXT_EPISODES=3        # Previous episodes for context
MAX_EPISODE_CONTENT_CHARS=4000  # Truncate long episodes
MAX_DEDUP_CANDIDATES=3        # Limit deduplication comparisons
```

**Impact:**
- Fewer tokens → faster LLM response
- Less context → potentially lower quality
- **Speedup: 30-40%**

**Trade-off:** May miss some context, but usually acceptable

---

### Option 2: Use Faster LLM Model

**What it does:** Switches to smaller, faster model

**Current:** `gemma3:12b` (12 billion parameters)  
**Options:**
- `gemma2:2b` (2 billion parameters) - 5-6x faster
- `llama3.2:3b` (3 billion parameters) - 3-4x faster
- `qwen2.5:3b` (3 billion parameters) - 3-4x faster

**How to test:**
```bash
# Test with smaller model
LLM_MODEL=gemma2:2b

# Rebuild and restart
docker-compose build graphiti-worker
docker-compose up -d graphiti-worker

# Monitor quality
docker-compose logs -f graphiti-worker | grep "entities created"
```

**Impact:**
- Much faster inference
- May extract fewer/lower quality entities
- **Speedup: 50-70%**

**Trade-off:** Quality vs. speed - MUST TEST FIRST

---

### Option 3: Disable Inline Deduplication

**What it does:** Skips deduplication during ingestion, runs as background job

**How to implement:**
1. Add flag to skip deduplication:
   ```bash
   ENABLE_INLINE_DEDUPLICATION=false
   ```

2. Run periodic deduplication via cron (already exists):
   ```bash
   # Runs every 30 minutes
   */30 * * * * /app/scripts/deduplication_cron.sh
   ```

**Impact:**
- Faster ingestion (skip dedup stage)
- Temporary duplicates until cron runs
- **Speedup: 10-15%**

**Trade-off:** Duplicates exist for up to 30 minutes

---

### Option 4: Batch Episode Processing

**What it does:** Processes multiple episodes in single LLM call

**Status:** Not yet implemented (requires code changes)

**How it would work:**
```
Current: 1 episode → 1 LLM call → 1 episode processed
Batched: 10 episodes → 1 LLM call → 10 episodes processed
```

**Impact:**
- Amortize LLM overhead across episodes
- Better throughput, higher latency for first episode
- **Speedup: 50-70% per episode**

**Trade-off:** Requires development work

---

## 🎯 Recommended Optimization Path

### Step 1: Quick Wins (5 minutes)

```bash
# Add to .env
MAX_CONTEXT_EPISODES=3
MAX_EPISODE_CONTENT_CHARS=4000
MAX_DEDUP_CANDIDATES=3
COMPRESSION_TARGET_TOKENS=1500

# Rebuild
docker-compose build graphiti-worker
docker-compose up -d graphiti-worker
```

**Expected:** 290s → 145-200s (30-50% faster)

---

### Step 2: Test Faster Model (15 minutes)

```bash
# Add to .env
LLM_MODEL=gemma2:2b

# Rebuild
docker-compose build graphiti-worker
docker-compose up -d graphiti-worker

# Monitor quality for 10-20 episodes
docker-compose logs -f graphiti-worker
```

**If quality is acceptable:** 145-200s → 60-100s (additional 50-70% faster)  
**If quality is poor:** Revert to gemma3:12b

---

### Step 3: Async Deduplication (Optional, 1 day)

Only if you need more speed and can tolerate temporary duplicates.

**Expected:** 60-100s → 50-85s (additional 10-15% faster)

---

## 📊 Monitoring Commands

### Check Episode Processing Time

```bash
# Watch for "Completed resilient add_episode" messages
docker-compose logs -f graphiti-worker | grep "Completed resilient"

# Example output:
# Completed resilient add_episode in 145234.56 ms  (145 seconds)
```

### Check Entity Extraction Quality

```bash
# Watch for "entities created" messages
docker-compose logs -f graphiti-worker | grep "entities created"

# Example output:
# Processed episode: 3 entities created  (good)
# Processed episode: 0 entities created  (bad - no entities!)
```

### Check LLM Token Usage

```bash
# Watch for LLM request logs
docker-compose logs -f graphiti-worker | grep "LLM Request"

# Example output:
# LLM Request [entity_extraction]: 2 messages, ~8,000 chars, ~2,000 tokens
```

---

## ⚠️ Important Notes

### Quality vs. Speed Trade-off

**Reducing context:**
- ✅ Safe: Usually doesn't affect quality much
- ✅ Reversible: Easy to increase if needed
- ⚠️ Monitor: Check entity extraction quality

**Smaller model:**
- ⚠️ Risky: May significantly reduce quality
- ⚠️ Test first: Run 10-20 episodes and validate
- ❌ Not reversible: Once data is extracted poorly, it's hard to fix

### When to Optimize

**Optimize if:**
- ✅ Ingestion is too slow for your use case
- ✅ You have a backlog of episodes to process
- ✅ You can tolerate some quality reduction

**Don't optimize if:**
- ❌ Current speed is acceptable
- ❌ Quality is critical (e.g., production system)
- ❌ You haven't measured baseline performance

---

## 🧪 Testing Checklist

Before deploying optimizations:

- [ ] Measure baseline performance (10 episodes)
- [ ] Record baseline entity count per episode
- [ ] Apply optimization
- [ ] Measure new performance (10 episodes)
- [ ] Compare entity count (should be similar)
- [ ] Validate entity quality (spot check)
- [ ] Monitor for errors or warnings
- [ ] Document results

---

## 📚 Related Documentation

- **Full Analysis:** `INGESTION_PIPELINE_ANALYSIS.md`
- **Sync Optimization:** `SYNC_PERFORMANCE_TUNING_GUIDE.md`
- **Environment Variables:** `../.env`

---

## 🎯 Expected Results Summary

| Configuration | Episode Time | Speedup | Quality Impact |
|---------------|--------------|---------|----------------|
| **Baseline** (gemma3:12b, full context) | 290s | 1x | ⭐⭐⭐⭐⭐ |
| **Quick Wins** (reduced context) | 145-200s | 1.5-2x | ⭐⭐⭐⭐ |
| **Faster Model** (gemma2:2b) | 60-100s | 3-5x | ⭐⭐⭐ |
| **Async Dedup** (+ no inline dedup) | 50-85s | 3.5-6x | ⭐⭐⭐ |
| **Batch Processing** (future) | 20-40s | 7-15x | ⭐⭐⭐⭐ |

---

**Created:** 2025-10-04  
**Status:** Ready for testing

