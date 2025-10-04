# Prompt Optimization - Executive Summary

**Date**: October 3, 2025  
**Status**: 📋 Awaiting Approval  
**Priority**: 🔴 P0 Critical

---

## 🎯 The Problem

**Current State**: Ollama is receiving **36,000+ token prompts** (18x too large)

```
┌─────────────────────────────────────────────────────────────┐
│  Current Prompt Composition (36,000 tokens)                 │
├─────────────────────────────────────────────────────────────┤
│  System Prompt:        500 tokens  (1.4%)   ▓               │
│  Current Episode:    1,000 tokens  (2.8%)   ▓               │
│  Previous Episodes: 34,500 tokens (95.8%)   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │
└─────────────────────────────────────────────────────────────┘
```

**Impact**:
- 15-30 seconds per LLM call
- 165 seconds per episode
- 0.25 episodes/minute throughput

---

## 💡 The Solution

**Reduce context by 90%** - Only include 5 most recent episodes

```
┌─────────────────────────────────────────────────────────────┐
│  Optimized Prompt Composition (3,000 tokens)                │
├─────────────────────────────────────────────────────────────┤
│  System Prompt:        500 tokens  (16.7%)  ▓▓▓             │
│  Current Episode:    1,000 tokens  (33.3%)  ▓▓▓▓▓▓▓         │
│  Previous Episodes:  1,500 tokens  (50.0%)  ▓▓▓▓▓▓▓▓▓▓      │
└─────────────────────────────────────────────────────────────┘
```

**Expected Impact**:
- 2-4 seconds per LLM call (85% faster)
- 10-15 seconds per episode (90% faster)
- 3-6 episodes/minute (12-24x throughput)

---

## 📋 Implementation Plan

### Phase 1: Context Reduction (Day 1) - CRITICAL ⚡

**Changes**:
1. Limit previous episodes to 5 most recent
2. Filter graph context to relevant nodes only
3. Limit deduplication candidates to top 10

**Files Modified**:
- `graphiti_core/prompts/extract_nodes.py`
- `graphiti_core/prompts/extract_edges.py`
- `graphiti_core/prompts/dedupe_nodes.py`
- `graphiti_core/search/search_utils.py`
- `.env` - Add `MAX_CONTEXT_EPISODES=5`

**Expected Result**:
- 91% token reduction (36K → 3K)
- 85% faster LLM processing
- 88% faster episode processing

---

### Phase 2: Smart Selection (Week 1) - Optional 🎯

**Changes**:
1. Use semantic search for relevant episodes (not just recent)
2. Summarize old episodes instead of full text

**Expected Result**:
- Better context quality
- Additional 40% token reduction
- Improved extraction accuracy

---

### Phase 3: Template Optimization (Week 1-2) - Optional 📝

**Changes**:
1. Shorten system prompts
2. Reduce examples
3. Concise instructions

**Expected Result**:
- 70% reduction in instruction tokens
- Clearer prompts
- Faster processing

---

### Phase 4: Compression (Week 2) - Optional 🗜️

**Changes**:
1. Verify LLMLingua compression is working
2. Add compression logging

**Expected Result**:
- Additional 30-40% token reduction
- Maintains semantic meaning

---

## 📊 Performance Projections

### Before Optimization

| Metric | Value |
|--------|-------|
| Prompt Size | 36,000 tokens |
| LLM Time | 15-30s per call |
| Episode Time | 165 seconds |
| Throughput | 0.25 episodes/min |

### After Phase 1 Only

| Metric | Value | Improvement |
|--------|-------|-------------|
| Prompt Size | 3,000 tokens | **91% ↓** |
| LLM Time | 2-4s per call | **85% ↓** |
| Episode Time | 15-20 seconds | **88% ↓** |
| Throughput | 3-4 episodes/min | **12-16x ↑** |

### After All Phases

| Metric | Value | Improvement |
|--------|-------|-------------|
| Prompt Size | 1,500-2,000 tokens | **94-95% ↓** |
| LLM Time | 1-2s per call | **93% ↓** |
| Episode Time | 8-12 seconds | **93% ↓** |
| Throughput | 5-7 episodes/min | **20-28x ↑** |

---

## ⚠️ Risks & Mitigations

| Risk | Mitigation | Rollback |
|------|------------|----------|
| Reduced context quality | Start with 5 episodes, monitor quality | Increase limit |
| Missing historical info | Use semantic search (Phase 2) | Revert to full context |
| Breaking changes | Feature flags, backward compatible | Instant rollback |

---

## ✅ Recommendation

**Proceed with Phase 1 immediately** - Critical performance fix

**Phases 2-4 are optional** - Implement if Phase 1 results are insufficient

**Estimated Timeline**:
- Phase 1: 1 day
- All Phases: 2 weeks

**Expected ROI**:
- Phase 1 alone: **12-16x faster** (165s → 15s per episode)
- All phases: **20-28x faster** (165s → 8s per episode)

---

## 📁 Documentation

**Detailed Plan**: `docs/PROMPT_OPTIMIZATION_PLAN.md`  
**Token Analysis**: `docs/PROMPT_TOKEN_ANALYSIS.md`  
**Performance Test**: `docs/PERFORMANCE_TEST_RESULTS.md`

---

## 🚀 Next Steps

1. ✅ Review this summary
2. ✅ Review detailed plan (`docs/PROMPT_OPTIMIZATION_PLAN.md`)
3. ⏳ **Approve or request changes**
4. ⏳ Begin Phase 1 implementation
5. ⏳ Test and validate
6. ⏳ Deploy and monitor

---

**Status**: 📋 **AWAITING APPROVAL TO PROCEED**  
**Contact**: Optimization Team  
**Priority**: 🔴 **P0 - Blocking Performance Issue**

