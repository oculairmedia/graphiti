# Graphiti Performance Optimization - Master Index

## 📚 Overview

This directory contains comprehensive performance optimization documentation for all major Graphiti components.

---

## 🎯 Quick Navigation

### Want to optimize RIGHT NOW?
1. **Ingestion Pipeline:** Read `INGESTION_OPTIMIZATION_QUICK_REFERENCE.md`
2. **Sync Service:** Read `SYNC_TUNING_QUICK_REFERENCE.md`

### Want to understand the bottlenecks?
1. **Ingestion Pipeline:** Read `INGESTION_PIPELINE_ANALYSIS.md`
2. **Sync Service:** Read `SYNC_OPTIMIZATION_VISUAL_GUIDE.md`

### Want complete details?
1. **Ingestion Pipeline:** Read `INGESTION_PIPELINE_ANALYSIS.md`
2. **Sync Service:** Read `SYNC_PERFORMANCE_TUNING_GUIDE.md`

---

## 📊 Performance Summary

| Component | Current | Optimized | Speedup | Effort |
|-----------|---------|-----------|---------|--------|
| **Ingestion Pipeline** | 290s/episode | 20-40s/episode | 7-15x | 5 min - 1 week |
| **Sync Service** | 140s (4000 nodes) | 13s (4000 nodes) | 10x | 5 min |
| **Centrality Storage** | 94s | 20-30s* | 3-5x* | TBD |

*Estimated based on analysis

---

## 🚀 Optimization Documentation

### 1. Ingestion Pipeline Optimization

#### Quick Reference ⚡
**File:** `INGESTION_OPTIMIZATION_QUICK_REFERENCE.md`  
**Reading Time:** 5 minutes  
**Best For:** Quick implementation

**Quick Win (5 minutes, 30-50% speedup):**
```bash
MAX_CONTEXT_EPISODES=3
MAX_EPISODE_CONTENT_CHARS=4000
MAX_DEDUP_CANDIDATES=3
COMPRESSION_TARGET_TOKENS=1500
```

#### Comprehensive Analysis 📘
**File:** `INGESTION_PIPELINE_ANALYSIS.md`  
**Reading Time:** 30 minutes  
**Best For:** Deep understanding

**Contents:**
- Detailed pipeline flow diagram
- Performance baseline (290s per episode)
- 4 major bottlenecks identified
- 4 optimization strategies
- 3-phase optimization plan

#### Summary 📋
**File:** `../INGESTION_OPTIMIZATION_SUMMARY.md`  
**Reading Time:** 5 minutes  
**Best For:** Executive overview

---

### 2. Sync Service Optimization

#### Quick Reference ⚡
**File:** `SYNC_TUNING_QUICK_REFERENCE.md`  
**Reading Time:** 5 minutes  
**Best For:** Quick implementation

**Quick Win (5 minutes, 5-10x speedup):**
```bash
MIGRATION_BATCH_SIZE=2000
SYNC_BATCH_SIZE=2000
SYNC_OPTIMIZATION_ENABLED=true
```

#### Visual Guide 📊
**File:** `SYNC_OPTIMIZATION_VISUAL_GUIDE.md`  
**Reading Time:** 10 minutes  
**Best For:** Understanding impact visually

**Contents:**
- ASCII diagrams showing performance differences
- Batch size impact visualization
- Real-world performance examples
- Decision tree for configuration

#### Comprehensive Guide 📘
**File:** `SYNC_PERFORMANCE_TUNING_GUIDE.md`  
**Reading Time:** 30 minutes  
**Best For:** Complete parameter reference

**Contents:**
- All 15+ tunable parameters
- 3 pre-configured profiles
- Implementation steps
- Troubleshooting guide
- Advanced optimization ideas

#### Index 📑
**File:** `SYNC_OPTIMIZATION_INDEX.md`  
**Reading Time:** 5 minutes  
**Best For:** Navigation and overview

#### Summary 📋
**File:** `../SYNC_OPTIMIZATION_SUMMARY.md`  
**Reading Time:** 5 minutes  
**Best For:** Executive overview

---

## 🎯 Optimization Priorities

### Priority 1: Ingestion Pipeline (CRITICAL)
**Why:** Slowest component (290s per episode)  
**Impact:** 7-15x speedup potential  
**Effort:** 5 minutes to 1 week  
**Start with:** Quick wins (reduce context size)

### Priority 2: Sync Service (HIGH)
**Why:** Needed for Neo4j → FalkorDB migration  
**Impact:** 5-10x speedup potential  
**Effort:** 5 minutes  
**Start with:** Increase batch sizes

### Priority 3: Centrality Storage (MEDIUM)
**Why:** Identified bottleneck (4.5x slower than calculation)  
**Impact:** 3-5x speedup potential  
**Effort:** TBD (not yet documented)  
**Start with:** Analysis and documentation

---

## 📈 Expected Performance Gains

### Ingestion Pipeline

| Phase | Configuration | Time | Speedup |
|-------|--------------|------|---------|
| Baseline | gemma3:12b, full context | 290s | 1x |
| Phase 1 | Reduced context | 145-200s | 1.5-2x |
| Phase 2 | + gemma2:2b | 60-100s | 3-5x |
| Phase 3 | + async dedup | 50-85s | 3.5-6x |
| Phase 4 | + batch processing | 20-40s | 7-15x |

### Sync Service

| Configuration | Time (4000 nodes) | Speedup |
|--------------|-------------------|---------|
| Default | 140s | 1x |
| Conservative | 60s | 2.3x |
| Balanced | 13s | 10.7x |
| Maximum | 8s | 17.5x |

---

## 🚀 Quick Start Paths

### Path 1: Optimize Everything (Recommended)

**Time:** 10 minutes  
**Expected Speedup:** 5-10x for both components

```bash
# 1. Optimize Ingestion Pipeline
cat >> .env << 'EOF'
# Ingestion Optimization
MAX_CONTEXT_EPISODES=3
MAX_EPISODE_CONTENT_CHARS=4000
MAX_DEDUP_CANDIDATES=3
COMPRESSION_TARGET_TOKENS=1500
EOF

# 2. Optimize Sync Service
cat >> .env << 'EOF'
# Sync Optimization
MIGRATION_BATCH_SIZE=2000
SYNC_BATCH_SIZE=2000
SYNC_OPTIMIZATION_ENABLED=true
NEO4J_POOL_SIZE=20
FALKORDB_POOL_SIZE=15
EOF

# 3. Rebuild and restart
docker-compose build graphiti-worker sync-service
docker-compose up -d graphiti-worker sync-service

# 4. Monitor
docker-compose logs -f graphiti-worker | grep "Completed resilient"
docker-compose logs -f sync-service | grep "batch"
```

---

### Path 2: Optimize Ingestion Only

**Time:** 5 minutes  
**Expected Speedup:** 1.5-2x

```bash
# Add to .env
MAX_CONTEXT_EPISODES=3
MAX_EPISODE_CONTENT_CHARS=4000
MAX_DEDUP_CANDIDATES=3
COMPRESSION_TARGET_TOKENS=1500

# Rebuild
docker-compose build graphiti-worker
docker-compose up -d graphiti-worker

# Monitor
docker-compose logs -f graphiti-worker | grep "Completed resilient"
```

---

### Path 3: Optimize Sync Only

**Time:** 5 minutes  
**Expected Speedup:** 5-10x

```bash
# Add to .env
MIGRATION_BATCH_SIZE=2000
SYNC_BATCH_SIZE=2000
SYNC_OPTIMIZATION_ENABLED=true

# Rebuild
docker-compose build sync-service
docker-compose up -d sync-service

# Monitor
docker-compose logs -f sync-service
```

---

## 📁 File Structure

```
graphiti/
├── docs/
│   ├── OPTIMIZATION_MASTER_INDEX.md              ← You are here
│   │
│   ├── Ingestion Pipeline Optimization/
│   │   ├── INGESTION_PIPELINE_ANALYSIS.md        ← Comprehensive analysis
│   │   └── INGESTION_OPTIMIZATION_QUICK_REFERENCE.md  ← Quick start
│   │
│   ├── Sync Service Optimization/
│   │   ├── SYNC_OPTIMIZATION_INDEX.md            ← Navigation guide
│   │   ├── SYNC_TUNING_QUICK_REFERENCE.md        ← Quick start
│   │   ├── SYNC_OPTIMIZATION_VISUAL_GUIDE.md     ← Visual explanations
│   │   └── SYNC_PERFORMANCE_TUNING_GUIDE.md      ← Comprehensive guide
│   │
│   └── Other Documentation/
│       ├── DRY_RUN_BENCHMARKING_GUIDE.md
│       └── eigenvector-centrality-continuous-architecture.md
│
├── INGESTION_OPTIMIZATION_SUMMARY.md             ← Ingestion summary
├── SYNC_OPTIMIZATION_SUMMARY.md                  ← Sync summary
├── .env                                          ← Your configuration
└── docker-compose.yml                            ← Service definitions
```

---

## 🔧 Monitoring Commands

### Ingestion Pipeline

```bash
# Watch episode processing time
docker-compose logs -f graphiti-worker | grep "Completed resilient"

# Watch entity extraction
docker-compose logs -f graphiti-worker | grep "entities created"

# Watch LLM token usage
docker-compose logs -f graphiti-worker | grep "LLM Request"
```

### Sync Service

```bash
# Watch sync progress
docker-compose logs -f sync-service | grep -E "batch|completed"

# Check memory usage
docker stats sync-service

# Check health
curl http://localhost:8082/health
```

---

## ⚠️ Important Notes

### Before Optimizing

1. **Backup your data** - Always backup before configuration changes
2. **Measure baseline** - Record current performance
3. **Test in non-production** - Verify compatibility
4. **Monitor quality** - Check entity extraction quality

### Quality vs. Speed Trade-offs

**Safe Optimizations (Low Risk):**
- ✅ Reducing context size (ingestion)
- ✅ Increasing batch sizes (sync)
- ✅ Enabling optimization mode (sync)

**Risky Optimizations (Test First):**
- ⚠️ Smaller LLM model (ingestion) - May reduce quality
- ⚠️ Async deduplication (ingestion) - Temporary duplicates
- ⚠️ Optimization mode (sync) - May have Cypher compatibility issues

---

## 🧪 Testing Checklist

Before deploying optimizations:

- [ ] Measure baseline performance
- [ ] Record baseline quality metrics
- [ ] Apply optimization
- [ ] Measure new performance
- [ ] Compare quality metrics
- [ ] Validate data integrity
- [ ] Monitor for errors
- [ ] Document results

---

## 📞 Support

For questions or issues:

1. **Ingestion:** Check `INGESTION_PIPELINE_ANALYSIS.md`
2. **Sync:** Check `SYNC_PERFORMANCE_TUNING_GUIDE.md`
3. **General:** Check this master index
4. **Logs:** `docker-compose logs <service-name>`

---

## 🎓 Learning Paths

### Beginner (Just want it faster)
1. Read quick reference for your component
2. Apply quick win configuration
3. Monitor results

### Intermediate (Want to understand why)
1. Read visual guides and summaries
2. Understand bottlenecks
3. Apply balanced configuration
4. Validate quality

### Advanced (Want complete control)
1. Read comprehensive guides
2. Understand all parameters
3. Customize configuration
4. Consider implementing advanced optimizations

---

## 📈 Contribution

If you discover better configurations:

1. Document your findings
2. Test thoroughly
3. Update this documentation
4. Share with the team

---

## 🎯 TL;DR

**Want 5-10x faster performance in 10 minutes?**

```bash
# Add to .env
MAX_CONTEXT_EPISODES=3
MAX_EPISODE_CONTENT_CHARS=4000
MIGRATION_BATCH_SIZE=2000
SYNC_BATCH_SIZE=2000

# Rebuild
docker-compose build graphiti-worker sync-service
docker-compose up -d

# Done!
```

**Want to understand what you just did?**

Read the quick references:
- `INGESTION_OPTIMIZATION_QUICK_REFERENCE.md`
- `SYNC_TUNING_QUICK_REFERENCE.md`

---

**Created:** 2025-10-04  
**Last Updated:** 2025-10-04  
**Status:** Complete and ready for use

