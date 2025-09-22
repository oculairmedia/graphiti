# Graphiti Ingestion System Prompt Audit

## Executive Summary

The Graphiti ingestion system experiences performance degradation as the knowledge graph grows due to **unbounded dynamic prompts** during entity deduplication. As the graph accumulates more entities, the deduplication process includes increasingly large lists of existing entities in LLM prompts, causing inference time to spike dramatically and reducing extraction effectiveness.

## Ingestion Pipeline Overview

When a new episode (message, text, or JSON) is ingested, Graphiti follows this process:

1. **Episode Creation**: Store the raw content as an episodic node
2. **Entity Extraction**: Use LLM to extract entities from the content
3. **Entity Deduplication**: Compare extracted entities against existing entities
4. **Edge Extraction**: Extract relationships between entities
5. **Edge Deduplication**: Compare extracted relationships against existing ones
6. **Graph Storage**: Save new/updated entities and relationships

## Prompt Components Analysis

### 1. Entity Extraction Prompts

**Template Structure:**
```
<PREVIOUS MESSAGES>
{previous_episodes}  // Up to 10 previous episodes
</PREVIOUS MESSAGES>

<CURRENT MESSAGE>
{episode_content}    // The new content being processed
</CURRENT MESSAGE>

<ENTITY TYPES>
{entity_types}       // Available entity type definitions
</ENTITY TYPES>
```

**Context Size:** 
- **Previous Episodes**: Limited by `RELEVANT_SCHEMA_LIMIT = 10`
- **Episode Content**: Variable, depends on input size
- **Entity Types**: Fixed, small set of type definitions

**Growth Pattern:** ✅ **Bounded** - Previous episodes are limited to 10 most recent

### 2. Entity Deduplication Prompts (⚠️ PROBLEM AREA)

**Template Structure:**
```
<PREVIOUS MESSAGES>
{previous_episodes}  // Up to 10 previous episodes
</PREVIOUS MESSAGES>

<CURRENT MESSAGE>
{episode_content}    // The new content
</CURRENT MESSAGE>

<NEW ENTITY>
{extracted_node}     // Single newly extracted entity
</NEW ENTITY>

<EXISTING ENTITIES>
{existing_nodes}     // ⚠️ ALL SIMILAR EXISTING ENTITIES
</EXISTING ENTITIES>
```

**Context Size:**
- **Previous Episodes**: Limited to 10 (bounded)
- **Episode Content**: Variable input size (bounded by input)
- **New Entity**: Single entity (bounded)
- **Existing Entities**: ⚠️ **UNBOUNDED** - Grows with graph size

**Growth Pattern:** ❌ **UNBOUNDED** - The `existing_nodes` list grows as more entities are added to the graph

### 3. Edge Extraction Prompts

**Template Structure:**
```
<PREVIOUS_MESSAGES>
{previous_episodes}  // Up to 10 previous episodes
</PREVIOUS_MESSAGES>

<CURRENT_MESSAGE>
{episode_content}    // The new content
</CURRENT_MESSAGE>

<ENTITIES>
{nodes}              // Entities extracted from current episode
</ENTITIES>
```

**Context Size:**
- **Previous Episodes**: Limited to 10 (bounded)
- **Episode Content**: Variable input size (bounded by input)
- **Entities**: Only entities from current episode (bounded)

**Growth Pattern:** ✅ **Bounded** - Only includes entities from current episode

## Critical Constants and Limits

### Current Hardcoded Limits
```python
RELEVANT_SCHEMA_LIMIT = 10          # Previous episodes in context
EPISODE_WINDOW_LEN = 3              # Episodes for bulk processing
DEFAULT_SEARCH_LIMIT = 50           # Default search result limit
DEFAULT_MIN_SCORE = 0.6             # Similarity threshold
SEMAPHORE_LIMIT = 20                # Concurrent operations
MAX_REFLEXION_ITERATIONS = 0        # Reflexion attempts
```

### Search Operation Limits
```python
# Node search operations use "2 * limit" pattern
node_fulltext_search(limit=2*50)    # Up to 100 results
node_similarity_search(limit=2*50)  # Up to 100 results
```

### Deduplication Limits (⚠️ NO LIMITS)
```python
# Entity deduplication retrieval - NO EXPLICIT LIMITS
existing_nodes = await search_for_similar_entities(...)
# This can return hundreds or thousands of entities
```

## Problem Areas Identified

### 1. Entity Deduplication Context Explosion

**Issue**: During entity deduplication, the system searches for similar existing entities and includes ALL results in the prompt.

**Code Location**: `graphiti_core/utils/maintenance/node_operations.py` - `resolve_extracted_nodes()`

**Prompt Growth**: As the graph grows from 100 → 1000 → 10000 entities, the deduplication prompts can include hundreds of existing entities for comparison.

**Impact**: 
- Prompt sizes can exceed 50,000+ tokens
- LLM inference time increases exponentially
- Model performance degrades with excessive context
- Creates unconnected episodes when deduplication fails

### 2. Search Result Accumulation

**Issue**: Multiple search operations (fulltext, similarity, BFS) each return up to `2 * limit` results that get combined.

**Code Location**: `graphiti_core/search/search.py` - `node_search()`

**Prompt Growth**: 
- Fulltext search: up to 100 results
- Similarity search: up to 100 results  
- BFS search: up to 100 results
- Combined: potentially 300+ entities in context

### 3. Bulk Processing Context

**Issue**: Bulk ingestion processes multiple episodes simultaneously, accumulating context across episodes.

**Code Location**: `graphiti_core/utils/bulk_utils.py` - `dedupe_nodes_bulk()`

**Prompt Growth**: Cross-episode deduplication can create massive context when processing multiple episodes with overlapping entities.

## Recommendations

### Immediate Fixes (High Priority)

1. **Limit Deduplication Context**
   ```python
   # Add explicit limit to existing entity retrieval
   MAX_DEDUP_ENTITIES = 20  # Limit existing entities in dedup prompts
   ```

2. **Implement Staged Deduplication**
   - First pass: Use embedding similarity to get top 10 candidates
   - Second pass: Use LLM only on high-confidence matches
   - Avoid sending 100+ entities to LLM for comparison

3. **Add Context Size Monitoring**
   ```python
   # Track and log prompt token counts
   if prompt_tokens > MAX_PROMPT_TOKENS:
       logger.warning(f"Large prompt detected: {prompt_tokens} tokens")
   ```

### Medium-Term Improvements

1. **Hierarchical Deduplication**
   - Group entities by type/category
   - Only compare within same category
   - Reduces comparison space significantly

2. **Caching and Memoization**
   - Cache deduplication results
   - Avoid re-comparing known non-duplicates
   - Use bloom filters for quick negative lookups

3. **Adaptive Context Sizing**
   - Dynamically adjust context based on graph size
   - Reduce previous episode count for large graphs
   - Implement context budget management

### Long-Term Architecture Changes

1. **Separate Deduplication Service**
   - Move deduplication to dedicated service
   - Use specialized algorithms (LSH, clustering)
   - Reduce LLM dependency for similarity detection

2. **Incremental Processing**
   - Process entities in smaller batches
   - Maintain deduplication indices
   - Avoid full graph scans

## Monitoring and Metrics

### Key Metrics to Track
- Average prompt token count per operation
- Deduplication context size over time
- Entity extraction success rate vs. graph size
- Inference time per episode

### Alert Thresholds
- Prompt size > 30,000 tokens
- Deduplication context > 50 entities
- Inference time > 30 seconds per episode
- Episode creation without entities > 10%

## Best Practices from Industry Standards

### 1. Prompt Compression (LLMLingua)

**Microsoft's LLMLingua** provides proven techniques for managing large context prompts:

```python
from llmlingua import PromptCompressor

# Compress deduplication context to manageable size
llm_lingua = PromptCompressor()
compressed_prompt = llm_lingua.compress_prompt(
    existing_entities_context,
    target_token=2000,  # Limit context to 2000 tokens
    force_tokens=["Entity:", "Name:", "Type:"],
    drop_consecutive=True,
    use_context_level_filter=True
)
```

**Key Benefits:**
- Reduces prompt size by 60-80% while maintaining performance
- Preserves critical information through selective compression
- Configurable token budgets for different operations

### 2. Staged Entity Resolution (Zingg)

**Zingg's entity resolution framework** demonstrates industry best practices:

```python
# Stage 1: Fast similarity filtering
fname = FieldDefinition("name", "string", MatchType.FUZZY)
entity_type = FieldDefinition("type", "string", MatchType.EXACT)

# Stage 2: Deterministic matching rules
detMatchNameType = DeterministicMatching('name', 'type')
args.setDeterministicMatchingCondition(detMatchNameType)

# Stage 3: ML-based similarity only for high-confidence candidates
args.setLabelDataSampleSize(0.5)  # Limit training data
```

**Key Principles:**
- **Hierarchical filtering**: Use fast exact/fuzzy matching first
- **Deterministic rules**: Apply business logic before ML
- **Bounded candidate sets**: Limit entities sent to LLM

### 3. Incremental Knowledge Graph Construction (iText2KG)

**iText2KG's approach** to incremental graph building:

```python
# Build graph with controlled thresholds
kg = itext2kg.build_graph(
    sections=semantic_blocks,
    ent_threshold=0.7,        # Higher threshold = fewer candidates
    rel_threshold=0.7,        # Control relationship extraction
    existing_knowledge_graph=existing_kg,  # Incremental updates
    max_tries=3,              # Limit LLM retries
    max_tries_isolated_entities=2  # Separate limit for edge cases
)
```

**Key Features:**
- **Threshold-based filtering**: Reduce candidate entities before LLM
- **Incremental updates**: Avoid reprocessing entire graph
- **Retry limits**: Prevent infinite loops and hallucinations

### 4. Context Budget Management

**Recommended context allocation strategy:**

```python
# Context budget allocation for deduplication
CONTEXT_BUDGET = {
    "previous_episodes": 1000,      # 10 episodes max
    "current_episode": 2000,        # Input content
    "entity_types": 500,            # Type definitions
    "existing_entities": 3000,      # ⚠️ CRITICAL: Limit this
    "instructions": 500,            # Prompt instructions
    "total_max": 7000              # Hard limit
}

# Dynamic context sizing based on graph size
def get_entity_limit(total_entities):
    if total_entities < 100:
        return 20  # Small graph: more context OK
    elif total_entities < 1000:
        return 10  # Medium graph: reduce context
    else:
        return 5   # Large graph: minimal context
```

## Recommended Implementation Strategy

### Phase 1: Immediate Fixes (1-2 weeks)

1. **Add hard limits to deduplication context**
   ```python
   MAX_DEDUP_ENTITIES = 20
   MAX_PROMPT_TOKENS = 8000
   ```

2. **Implement prompt compression**
   ```python
   # Use LLMLingua for large contexts
   if len(existing_entities) > MAX_DEDUP_ENTITIES:
       compressed_context = compress_entity_context(existing_entities)
   ```

3. **Add monitoring and alerts**
   ```python
   # Track prompt sizes and performance
   if prompt_tokens > MAX_PROMPT_TOKENS:
       logger.warning(f"Large prompt: {prompt_tokens} tokens")
       metrics.increment("large_prompt_count")
   ```

### Phase 2: Architectural Improvements (2-4 weeks)

1. **Implement staged deduplication**
   - Stage 1: Embedding similarity (fast, no LLM)
   - Stage 2: Deterministic rules (business logic)
   - Stage 3: LLM comparison (limited candidates)

2. **Add context-aware thresholds**
   ```python
   # Adaptive thresholds based on graph size
   similarity_threshold = min(0.9, 0.7 + (graph_size / 10000))
   ```

3. **Implement incremental processing**
   - Cache deduplication results
   - Use bloom filters for negative lookups
   - Batch similar entities together

### Phase 3: Advanced Optimizations (4-8 weeks)

1. **Separate deduplication service**
   - Dedicated microservice for entity resolution
   - Specialized algorithms (LSH, clustering)
   - Reduced LLM dependency

2. **Graph-aware deduplication**
   - Use graph structure for candidate selection
   - Leverage existing relationships
   - Community-based grouping

## Conclusion

The primary cause of Graphiti's performance degradation is **unbounded entity deduplication prompts** that grow linearly with graph size. Industry best practices from Microsoft (LLMLingua), Zingg, and iText2KG provide proven solutions:

1. **Prompt compression** to manage large contexts
2. **Staged deduplication** to reduce LLM load
3. **Context budgets** to prevent unbounded growth
4. **Incremental processing** to avoid full graph scans

Implementing these practices will immediately improve performance and prevent the creation of unconnected episodes.
