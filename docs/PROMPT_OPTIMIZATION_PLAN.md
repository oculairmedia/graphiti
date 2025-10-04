# Prompt Optimization Plan - Detailed Implementation Strategy

**Date**: October 3, 2025  
**Status**: 📋 PENDING REVIEW  
**Priority**: 🔴 P0 - Critical Performance Issue  
**Expected Impact**: 10-15x performance improvement

---

## Executive Summary

**Problem**: Prompts are 36,000+ tokens (18x too large), causing 15-30 second LLM processing times  
**Solution**: Reduce context size by 90% through smart episode selection and summarization  
**Impact**: Episode processing time from 165s → 10-15s (10-15x faster)

---

## 📊 Current State Analysis

### Token Usage Breakdown

From live logs, we observed:

**Entity Extraction Prompts** (~36,000 tokens):
```
LLM Request: 2 messages, ~146,278 chars, ~36,569 tokens
LLM Request: 2 messages, ~147,287 chars, ~36,821 tokens
LLM Request: 2 messages, ~148,166 chars, ~37,041 tokens
```

**Edge Extraction Prompts** (~19,000 tokens):
```
LLM Request: 2 messages, ~76,004 chars, ~19,001 tokens
LLM Request: 2 messages, ~83,594 chars, ~20,898 tokens
```

**Deduplication Prompts** (~5,000 tokens):
```
LLM Request: 2 messages, ~22,565 chars, ~5,641 tokens
LLM Request: 2 messages, ~25,465 chars, ~6,366 tokens
```

### Estimated Composition

**Entity Extraction (36,000 tokens)**:
- System prompt + instructions: ~500 tokens (1.4%)
- Current episode content: ~1,000 tokens (2.8%)
- **Previous episodes context: ~34,500 tokens (95.8%)** ⚠️

**Edge Extraction (19,000 tokens)**:
- System prompt + instructions: ~500 tokens (2.6%)
- Extracted nodes: ~500 tokens (2.6%)
- **Existing graph context: ~18,000 tokens (94.7%)** ⚠️

---

## 🎯 Optimization Strategy

### Phase 1: Context Reduction (CRITICAL - Day 1)

#### 1.1 Limit Previous Episodes in Entity Extraction

**Current Behavior**:
```python
# In extract_nodes() - sends ALL previous episodes
previous_episodes = await get_previous_episodes(group_id)  # Could be 100+ episodes
context = build_context(previous_episodes)  # 34,500 tokens!
```

**Proposed Change**:
```python
# Limit to most recent N episodes
MAX_CONTEXT_EPISODES = 5  # Configurable via env var

previous_episodes = await get_previous_episodes(group_id, limit=MAX_CONTEXT_EPISODES)
context = build_context(previous_episodes)  # ~1,500 tokens (5 episodes × 300 tokens)
```

**Expected Impact**:
- Tokens: 36,000 → 3,000 (91.7% reduction)
- Processing time: 15-30s → 2-4s (85% reduction)

**Files to Modify**:
- `graphiti_core/prompts/extract_nodes.py` - Add episode limit
- `graphiti_core/search/search_utils.py` - Modify `get_previous_episodes()` to accept limit
- `.env` - Add `MAX_CONTEXT_EPISODES=5`

**Configuration**:
```bash
# .env
MAX_CONTEXT_EPISODES=5              # Number of previous episodes to include
MAX_CONTEXT_TOKENS=2000             # Maximum tokens for context
ENABLE_EPISODE_SUMMARIZATION=false  # For Phase 2
```

---

#### 1.2 Limit Graph Context in Edge Extraction

**Current Behavior**:
```python
# In extract_edges() - sends ALL related nodes and edges
existing_nodes = await get_all_nodes(group_id)  # Could be 1000+ nodes
existing_edges = await get_all_edges(group_id)  # Could be 5000+ edges
context = build_graph_context(existing_nodes, existing_edges)  # 18,000 tokens!
```

**Proposed Change**:
```python
# Only include nodes mentioned in current episode
mentioned_entities = extract_entity_names(current_episode)
existing_nodes = await get_nodes_by_names(mentioned_entities)  # Only relevant nodes
existing_edges = await get_edges_for_nodes(existing_nodes)     # Only relevant edges
context = build_graph_context(existing_nodes, existing_edges)  # ~500 tokens
```

**Expected Impact**:
- Tokens: 19,000 → 2,000 (89.5% reduction)
- Processing time: 15-30s → 2-4s (85% reduction)

**Files to Modify**:
- `graphiti_core/prompts/extract_edges.py` - Filter to relevant nodes only
- `graphiti_core/search/search_utils.py` - Add `get_nodes_by_names()` method

---

#### 1.3 Optimize Deduplication Context

**Current Behavior**:
```python
# In dedupe_nodes() - sends full node details
candidate_nodes = await get_similar_nodes(new_node)  # 50+ nodes
context = build_dedup_context(candidate_nodes)  # Full node details: 5,000 tokens
```

**Proposed Change**:
```python
# Only include essential fields
candidate_nodes = await get_similar_nodes(new_node, limit=10)  # Top 10 only
context = build_minimal_dedup_context(candidate_nodes)  # Name + summary only: ~500 tokens
```

**Expected Impact**:
- Tokens: 5,000 → 500 (90% reduction)
- Processing time: 5-10s → 1-2s (80% reduction)

**Files to Modify**:
- `graphiti_core/prompts/dedupe_nodes.py` - Limit candidates and fields
- `graphiti_core/search/search_utils.py` - Add limit parameter to similarity search

---

### Phase 2: Smart Context Selection (Week 1)

#### 2.1 Semantic Episode Selection

**Instead of**: Most recent 5 episodes  
**Use**: 5 most semantically relevant episodes

**Implementation**:
```python
async def get_relevant_episodes(current_episode: str, group_id: str, limit: int = 5):
    """Get episodes most relevant to current episode using semantic search"""
    
    # Generate embedding for current episode
    current_embedding = await embedder.create(current_episode)
    
    # Search for similar episodes
    similar_episodes = await search_episodes_by_embedding(
        embedding=current_embedding,
        group_id=group_id,
        limit=limit,
        min_similarity=0.7  # Only include if >70% similar
    )
    
    return similar_episodes
```

**Expected Impact**:
- Better context quality (more relevant information)
- Same token count (~1,500 tokens)
- Improved entity extraction accuracy

**Files to Modify**:
- `graphiti_core/search/search_utils.py` - Add `get_relevant_episodes()`
- `graphiti_core/prompts/extract_nodes.py` - Use semantic selection
- `.env` - Add `USE_SEMANTIC_EPISODE_SELECTION=true`

---

#### 2.2 Episode Summarization

**For episodes older than N days**: Use summaries instead of full text

**Implementation**:
```python
async def get_episode_context(episodes: list[Episode], max_age_days: int = 7):
    """Get episode context with summarization for old episodes"""
    
    context_parts = []
    cutoff_date = datetime.now() - timedelta(days=max_age_days)
    
    for episode in episodes:
        if episode.created_at > cutoff_date:
            # Recent episode: use full text
            context_parts.append(f"Episode: {episode.content}")
        else:
            # Old episode: use summary
            summary = await summarize_episode(episode)  # 50-100 tokens
            context_parts.append(f"Episode (summary): {summary}")
    
    return "\n\n".join(context_parts)
```

**Expected Impact**:
- Further token reduction for groups with long history
- Maintains context quality
- Tokens: ~1,500 → ~800 (47% additional reduction)

**Files to Modify**:
- `graphiti_core/prompts/extract_nodes.py` - Add summarization logic
- `graphiti_core/llm_client/` - Add `summarize_episode()` method
- `.env` - Add `EPISODE_SUMMARY_AGE_DAYS=7`

---

### Phase 3: Prompt Template Optimization (Week 1-2)

#### 3.1 Reduce Instruction Verbosity

**Current Prompts** (estimated):
- Long system prompts with detailed instructions
- Multiple examples
- Verbose formatting

**Proposed Changes**:
- Concise instructions
- Minimal examples (1-2 instead of 5+)
- Compact formatting

**Example - Entity Extraction**:

**Before** (~500 tokens):
```
You are an expert entity extraction system. Your task is to carefully analyze 
the provided text and extract all entities mentioned. For each entity, you should:

1. Identify the entity name
2. Determine the entity type (Person, Organization, Location, etc.)
3. Extract relevant attributes
4. Provide a detailed summary

Here are some examples:

Example 1: [Long example]
Example 2: [Long example]
Example 3: [Long example]

Please follow these guidelines:
- Be thorough and accurate
- Include all relevant details
- Use the exact format specified
...
```

**After** (~150 tokens):
```
Extract entities from the text. For each entity provide:
- name: entity name
- type: Person/Organization/Location/Event/Concept
- summary: brief description

Format: JSON array of entities.

Example: [{"name": "John", "type": "Person", "summary": "Software engineer"}]
```

**Expected Impact**:
- Tokens: ~500 → ~150 per prompt (70% reduction)
- Clearer instructions
- Faster processing

**Files to Modify**:
- `graphiti_core/prompts/extract_nodes.py`
- `graphiti_core/prompts/extract_edges.py`
- `graphiti_core/prompts/dedupe_nodes.py`
- `graphiti_core/prompts/resolve_nodes.py`

---

### Phase 4: Prompt Compression (Week 2)

#### 4.1 Verify and Enable LLMLingua

**Current Status**: `ENABLE_PROMPT_COMPRESSION=true` but not working

**Investigation Needed**:
1. Check if `GraphitiPromptCompressor` is being instantiated
2. Verify compression is called before LLM requests
3. Check compression logs
4. Validate compression quality

**Implementation**:
```python
# In openai_generic_client.py
async def _generate_response(self, messages, ...):
    # Build prompt
    prompt = build_prompt(messages)
    
    # Compress if enabled
    if self.enable_compression:
        original_length = len(prompt)
        prompt = await self.compressor.compress(
            prompt, 
            target_tokens=self.compression_target_tokens
        )
        compressed_length = len(prompt)
        logger.info(f"Compressed prompt: {original_length} → {compressed_length} chars "
                   f"({100*(1-compressed_length/original_length):.1f}% reduction)")
    
    # Send to LLM
    response = await self.client.chat.completions.create(...)
```

**Expected Impact**:
- Additional 30-40% token reduction
- Maintains semantic meaning
- Tokens: 3,000 → 1,800-2,100 (30-40% reduction)

**Files to Modify**:
- `graphiti_core/llm_client/openai_generic_client.py` - Add compression logging
- `graphiti_core/utils/prompt_compressor.py` - Verify implementation
- `.env` - Verify compression settings

---

## 📋 Implementation Checklist

### Phase 1: Context Reduction (Day 1) - CRITICAL

#### Entity Extraction Optimization
- [ ] Add `MAX_CONTEXT_EPISODES` environment variable
- [ ] Modify `get_previous_episodes()` to accept limit parameter
- [ ] Update `extract_nodes()` to use limited episodes
- [ ] Add logging for context size before/after
- [ ] Test with 5 episode limit
- [ ] Measure token reduction

#### Edge Extraction Optimization
- [ ] Add `get_nodes_by_names()` method
- [ ] Add `get_edges_for_nodes()` method
- [ ] Update `extract_edges()` to filter relevant nodes only
- [ ] Add logging for context size
- [ ] Test with filtered context
- [ ] Measure token reduction

#### Deduplication Optimization
- [ ] Add limit parameter to `get_similar_nodes()`
- [ ] Create `build_minimal_dedup_context()` function
- [ ] Update `dedupe_nodes()` to use minimal context
- [ ] Add logging for context size
- [ ] Test with limited candidates
- [ ] Measure token reduction

#### Testing & Validation
- [ ] Run test episode through pipeline
- [ ] Verify token counts in logs
- [ ] Confirm <3,000 tokens per request
- [ ] Verify entity extraction quality maintained
- [ ] Verify edge extraction quality maintained
- [ ] Measure processing time improvement

---

### Phase 2: Smart Context Selection (Week 1)

#### Semantic Episode Selection
- [ ] Implement `get_relevant_episodes()` function
- [ ] Add episode embedding search
- [ ] Add `USE_SEMANTIC_EPISODE_SELECTION` env var
- [ ] Test semantic vs recency selection
- [ ] Compare extraction quality
- [ ] Measure performance impact

#### Episode Summarization
- [ ] Implement `summarize_episode()` function
- [ ] Add `EPISODE_SUMMARY_AGE_DAYS` env var
- [ ] Update `get_episode_context()` to use summaries
- [ ] Test summarization quality
- [ ] Measure token reduction
- [ ] Verify context quality maintained

---

### Phase 3: Prompt Template Optimization (Week 1-2)

#### Template Refactoring
- [ ] Review all prompt templates
- [ ] Identify verbose sections
- [ ] Rewrite with concise instructions
- [ ] Reduce examples to 1-2 per prompt
- [ ] Test with new templates
- [ ] Verify output quality
- [ ] Measure token reduction

#### Specific Prompts to Optimize
- [ ] `extract_nodes.py` - Entity extraction
- [ ] `extract_edges.py` - Edge extraction
- [ ] `dedupe_nodes.py` - Deduplication
- [ ] `resolve_nodes.py` - Node resolution
- [ ] `summarize.py` - Summarization

---

### Phase 4: Prompt Compression (Week 2)

#### Compression Investigation
- [ ] Check if `GraphitiPromptCompressor` exists
- [ ] Verify compression is called
- [ ] Add compression logging
- [ ] Test compression quality
- [ ] Measure token reduction
- [ ] Validate semantic preservation

---

## 🎯 Success Metrics

### Before Optimization (Baseline)

| Metric | Value |
|--------|-------|
| Entity extraction prompt | 36,000 tokens |
| Edge extraction prompt | 19,000 tokens |
| Deduplication prompt | 5,000 tokens |
| LLM processing time | 15-30s per call |
| Episode processing time | 165 seconds |
| Throughput | 0.25 episodes/min |

### After Phase 1 (Target)

| Metric | Target | Improvement |
|--------|--------|-------------|
| Entity extraction prompt | 3,000 tokens | 91% reduction |
| Edge extraction prompt | 2,000 tokens | 89% reduction |
| Deduplication prompt | 500 tokens | 90% reduction |
| LLM processing time | 2-4s per call | 85% reduction |
| Episode processing time | 15-20 seconds | 88% reduction |
| Throughput | 3-4 episodes/min | 12-16x faster |

### After All Phases (Ultimate Target)

| Metric | Target | Improvement |
|--------|--------|-------------|
| Entity extraction prompt | 1,500-2,000 tokens | 94-95% reduction |
| Edge extraction prompt | 1,000-1,500 tokens | 92-95% reduction |
| Deduplication prompt | 300-400 tokens | 92-94% reduction |
| LLM processing time | 1-2s per call | 93% reduction |
| Episode processing time | 8-12 seconds | 93% reduction |
| Throughput | 5-7 episodes/min | 20-28x faster |

---

## ⚠️ Risks & Mitigations

### Risk 1: Reduced Context Quality

**Risk**: Limiting episodes may reduce entity extraction accuracy  
**Mitigation**: 
- Start with 5 episodes (reasonable context)
- Use semantic selection (Phase 2) for better relevance
- Monitor extraction quality metrics
- Make limit configurable for adjustment

**Rollback Plan**: Increase `MAX_CONTEXT_EPISODES` if quality degrades

---

### Risk 2: Missing Important Historical Context

**Risk**: Old but relevant information may be excluded  
**Mitigation**:
- Use semantic search to find relevant old episodes
- Implement summarization for old episodes
- Include entity relationship history separately

**Rollback Plan**: Revert to full context if critical information is missed

---

### Risk 3: Compression Artifacts

**Risk**: LLMLingua compression may distort meaning  
**Mitigation**:
- Test compression quality thoroughly
- Use conservative compression ratio (0.6)
- Monitor output quality
- Make compression optional

**Rollback Plan**: Disable compression if quality issues detected

---

### Risk 4: Breaking Changes

**Risk**: Changes may break existing functionality  
**Mitigation**:
- Make all changes backward compatible
- Use feature flags for new behavior
- Extensive testing before deployment
- Gradual rollout

**Rollback Plan**: Feature flags allow instant rollback

---

## 🔧 Configuration Changes

### New Environment Variables

```bash
# Phase 1: Context Reduction
MAX_CONTEXT_EPISODES=5                    # Limit previous episodes
MAX_GRAPH_CONTEXT_NODES=50                # Limit nodes in edge extraction
MAX_DEDUP_CANDIDATES=10                   # Limit deduplication candidates
MAX_CONTEXT_TOKENS=2000                   # Hard limit on context size

# Phase 2: Smart Selection
USE_SEMANTIC_EPISODE_SELECTION=true       # Use semantic search for episodes
EPISODE_SUMMARY_AGE_DAYS=7                # Summarize episodes older than N days
MIN_EPISODE_SIMILARITY=0.7                # Minimum similarity for inclusion

# Phase 3: Prompt Optimization
USE_CONCISE_PROMPTS=true                  # Use optimized prompt templates

# Phase 4: Compression
ENABLE_PROMPT_COMPRESSION=true            # Enable LLMLingua compression
COMPRESSION_TARGET_TOKENS=2000            # Target tokens after compression
COMPRESSION_RATIO=0.6                     # Compression ratio (0.6 = 40% reduction)

# Monitoring
LOG_PROMPT_SIZES=true                     # Log prompt sizes for monitoring
LOG_COMPRESSION_STATS=true                # Log compression statistics
```

---

## 📁 Files to Modify

### Core Changes

1. **`graphiti_core/prompts/extract_nodes.py`**
   - Add episode limit
   - Add semantic selection
   - Add summarization
   - Optimize prompt template

2. **`graphiti_core/prompts/extract_edges.py`**
   - Filter to relevant nodes
   - Optimize prompt template

3. **`graphiti_core/prompts/dedupe_nodes.py`**
   - Limit candidates
   - Use minimal context
   - Optimize prompt template

4. **`graphiti_core/search/search_utils.py`**
   - Add `get_previous_episodes(limit=N)`
   - Add `get_relevant_episodes()`
   - Add `get_nodes_by_names()`
   - Add `get_edges_for_nodes()`

5. **`graphiti_core/llm_client/openai_generic_client.py`**
   - Add compression logging
   - Verify compression is called

6. **`.env`**
   - Add new configuration variables

7. **`docker-compose.yml`**
   - Pass new environment variables to worker

---

## 📊 Testing Plan

### Unit Tests

- [ ] Test `get_previous_episodes()` with limit
- [ ] Test `get_relevant_episodes()` semantic search
- [ ] Test `summarize_episode()` quality
- [ ] Test `get_nodes_by_names()` filtering
- [ ] Test prompt compression

### Integration Tests

- [ ] Test full episode processing with limited context
- [ ] Verify entity extraction quality
- [ ] Verify edge extraction quality
- [ ] Verify deduplication accuracy
- [ ] Measure end-to-end performance

### Performance Tests

- [ ] Measure token counts for each prompt type
- [ ] Measure LLM processing time
- [ ] Measure episode processing time
- [ ] Measure throughput (episodes/minute)
- [ ] Compare before/after metrics

---

## 📅 Timeline

### Day 1 (Phase 1 - Critical)
- Morning: Implement context reduction
- Afternoon: Test and validate
- Evening: Deploy and monitor

### Week 1 (Phase 2)
- Days 2-3: Implement semantic selection
- Days 4-5: Implement summarization
- Weekend: Test and refine

### Week 2 (Phases 3-4)
- Days 8-10: Optimize prompt templates
- Days 11-12: Fix prompt compression
- Days 13-14: Final testing and deployment

---

## ✅ Approval Checklist

Before proceeding with implementation:

- [ ] **Technical Review**: Architecture and approach validated
- [ ] **Risk Assessment**: Risks identified and mitigations planned
- [ ] **Testing Strategy**: Comprehensive testing plan in place
- [ ] **Rollback Plan**: Clear rollback procedures defined
- [ ] **Monitoring**: Metrics and logging strategy defined
- [ ] **Timeline**: Schedule approved and resources allocated

---

## 📞 Next Steps

1. **Review this plan** with team
2. **Approve or request changes**
3. **Prioritize phases** (can skip Phase 2-4 if Phase 1 sufficient)
4. **Assign implementation** tasks
5. **Begin Phase 1** implementation

---

**Status**: 📋 **AWAITING APPROVAL**  
**Estimated Effort**: 2-3 days (Phase 1 only), 2 weeks (all phases)  
**Expected Impact**: 10-15x performance improvement  
**Risk Level**: Low (with proper testing and rollback plan)

