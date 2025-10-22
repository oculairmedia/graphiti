# HULY ISSUE: Fix Unbounded Prompt Growth in Entity Deduplication

## Issue Details
- **Project**: GRAPH (Graphiti Knowledge Graph Platform)
- **Priority**: High
- **Type**: Bug/Performance
- **Component**: Core Deduplication System
- **Affects**: Ingestion Performance, LLM Token Usage, System Scalability

## Problem Summary

As the knowledge graph grows beyond 1000+ entities, the ingestion process slows dramatically and creates unconnected episodes with no entities. The root cause is **unbounded prompt growth** in the final stage of the 4-stage deduplication pipeline, where LLM prompts can exceed 50,000+ tokens.

## Impact

- **Performance Degradation**: Ingestion becomes extremely slow with large graphs
- **Quality Issues**: Creates unconnected episodes without entities
- **Cost Impact**: Exponential increase in LLM token usage
- **Scalability Blocker**: System becomes unusable with graphs >10,000 entities

## Root Cause Analysis

Graphiti implements a sophisticated 4-stage deduplication pipeline, but Stage 4 suffers from unbounded growth:

### ✅ Stages 1-3 (Working Correctly)
1. **Within-Episode Deduplication** - Bounded to episode size
2. **Exact Database Match** - Returns single result (LIMIT 1)
3. **Fuzzy Fallback** - Limited to 50 candidates with SequenceMatcher

### ❌ Stage 4 (Unbounded Problem)
4. **LLM-Based Hybrid Search** - No effective limits on search results

## Technical Details

### Critical Code Locations

1. **Primary Issue**: `graphiti_core/utils/maintenance/node_operations.py:528-540`
   ```python
   search_results: list[SearchResults] = await semaphore_gather(
       *[
           search(
               clients=clients,
               query=node.name,
               config=NODE_HYBRID_SEARCH_RRF,  # ❌ NO EXPLICIT LIMIT
           )
           for node in nodes_needing_llm_resolution
       ]
   )
   ```

2. **Search Multipliers**: `graphiti_core/search/search.py:315-327`
   ```python
   # Each method returns 2 * limit results
   node_fulltext_search(driver, query, ..., 2 * limit),     # 20 results
   node_similarity_search(driver, query, ..., 2 * limit),   # 20 results  
   node_bfs_search(driver, ..., 2 * limit),                 # 20 results
   # Total: Up to 60 candidates before reranking
   ```

3. **No Final Limit**: `graphiti_core/search/search.py:328-378`
   ```python
   # ❌ ALL reranked results passed to LLM
   return reranked_results  # Can be 50+ entities
   ```

4. **Batch Processing**: `graphiti_core/utils/maintenance/node_operations.py:823-838`
   ```python
   # Up to 100 entities per batch prompt
   LIMIT 100  # ❌ TOO HIGH FOR BATCH PROCESSING
   ```

### Prompt Growth Pattern

- **Small Graph** (100 entities): ~10 entities per prompt = manageable
- **Medium Graph** (1,000 entities): ~30 entities per prompt = slow
- **Large Graph** (10,000 entities): ~50+ entities per prompt = unusable

## Proposed Solution

### Immediate Fixes (No New Variables)

#### Fix 1: Limit Search Results in Deduplication
**File**: `graphiti_core/utils/maintenance/node_operations.py:528-540`
```python
# Create limited search config for deduplication
search_config = NODE_HYBRID_SEARCH_RRF.model_copy(deep=True)
search_config.limit = 10  # Explicit limit for deduplication

search_results: list[SearchResults] = await semaphore_gather(
    *[
        search(
            clients=clients,
            query=node.name,
            group_ids=None if enable_cross_graph_deduplication else [node.group_id],
            search_filter=SearchFilters(),
            config=search_config,  # Use limited config
        )
        for node in nodes_needing_llm_resolution
    ]
)
```

#### Fix 2: Reduce Batch Processing Context
**File**: `graphiti_core/utils/maintenance/node_operations.py:823-838`
```python
# Reduce existing entity limit for batch processing
existing_query = """
MATCH (n:Entity)
WHERE n.group_id IN $group_ids
RETURN n
LIMIT 20  # Reduced from 100 to 20
"""
```

#### Fix 3: Apply Final Limit to Search Results
**File**: `graphiti_core/search/search.py:328-378`
```python
# Apply final limit after reranking
final_limit = config.limit or DEFAULT_SEARCH_LIMIT
return reranked_results[:final_limit]
```

## Testing Strategy

### Before Fix
1. Create graph with 5,000+ entities
2. Monitor prompt token counts during ingestion
3. Measure ingestion time per episode
4. Track unconnected episode creation

### After Fix
1. Verify prompt sizes stay under 8,000 tokens
2. Confirm ingestion performance remains consistent
3. Ensure deduplication quality is maintained
4. Test with various graph sizes (100, 1K, 10K entities)

## Success Criteria

- [ ] Prompt token counts bounded to <8,000 tokens
- [ ] Ingestion time scales linearly with content, not graph size
- [ ] No unconnected episodes created
- [ ] Deduplication quality maintained (>95% accuracy)
- [ ] System usable with 10,000+ entity graphs

## Implementation Notes

- **No Breaking Changes**: All fixes use existing configuration patterns
- **Backward Compatible**: Existing behavior preserved for small graphs
- **Minimal Risk**: Changes only affect prompt size limits
- **Easy Rollback**: Simple to revert if issues arise

## Related Files

- `graphiti_core/utils/maintenance/node_operations.py` (Primary)
- `graphiti_core/search/search.py` (Secondary)
- `graphiti_core/search/search_config_recipes.py` (Configuration)
- `graphiti_core/prompts/dedupe_nodes.py` (Prompt Template)

## Dependencies

- No external dependencies required
- No new environment variables needed
- No database schema changes required

## Estimated Effort

- **Development**: 4-6 hours
- **Testing**: 8-10 hours  
- **Documentation**: 2 hours
- **Total**: 1-2 days

## Risk Assessment

- **Low Risk**: Changes are conservative limits on existing functionality
- **High Impact**: Fixes critical scalability blocker
- **Easy Validation**: Clear metrics for success/failure
