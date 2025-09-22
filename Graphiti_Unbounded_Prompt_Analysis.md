# Graphiti Unbounded Prompt Growth Analysis

## Executive Summary

Graphiti **already implements a sophisticated 4-stage deduplication pipeline**, but the final LLM stage still suffers from unbounded prompt growth. The staging successfully filters out most duplicates through fast operations, but the remaining candidates that reach the LLM can still number in the hundreds, causing prompt explosion.

## Existing Staged Deduplication Architecture

### Stage 1: Within-Episode Deduplication (✅ Bounded)
**Location**: `graphiti_core/utils/maintenance/node_operations.py:389-402`

```python
# Track nodes we've already resolved within this episode to prevent duplicates
episode_resolved_nodes: dict[str, EntityNode] = {}

for i, node in enumerate(extracted_nodes):
    # First check if we've already resolved this name within this episode
    episode_key = f"{node.name}|{node.group_id}" if not enable_cross_graph_deduplication else node.name
    if episode_key in episode_resolved_nodes:
        # Found within this episode - use the already resolved node
        existing_node = episode_resolved_nodes[episode_key]
        resolved_nodes.append(existing_node)
        uuid_map[node.uuid] = existing_node.uuid
        node_duplicates.append((node, existing_node))
        continue
```

**Effectiveness**: Prevents exact duplicates within the same episode from hitting the database or LLM.

### Stage 2: Exact Database Match (✅ Bounded)
**Location**: `graphiti_core/utils/maintenance/node_operations.py:404-447`

```python
# Query for exact name match in database
if enable_cross_graph_deduplication:
    exact_query = """
    MATCH (n:Entity)
    WHERE n.name = $name
    RETURN n
    ORDER BY n.created_at
    LIMIT 1
    """
else:
    exact_query = """
    MATCH (n:Entity)
    WHERE n.name = $name AND n.group_id = $group_id
    RETURN n
    ORDER BY n.created_at
    LIMIT 1
    """

records, _, _ = await driver.execute_query(exact_query, name=node.name, group_id=node.group_id)
```

**Effectiveness**: Returns only the first exact match, preventing exact duplicates from reaching the LLM.

### Stage 3: Fuzzy Fallback (✅ Bounded)
**Location**: `graphiti_core/utils/maintenance/node_operations.py:458-514`

```python
if os.getenv('ENABLE_AGGRESSIVE_DEDUP', 'true').lower() == 'true':
    # Query for potential fuzzy matches (get more candidates)
    if enable_cross_graph_deduplication:
        fuzzy_query = """
        MATCH (n:Entity)
        RETURN n
        ORDER BY n.created_at
        LIMIT 50  # ✅ BOUNDED TO 50 CANDIDATES
        """
    else:
        fuzzy_query = """
        MATCH (n:Entity)
        WHERE n.group_id = $group_id
        RETURN n
        ORDER BY n.created_at
        LIMIT 50  # ✅ BOUNDED TO 50 CANDIDATES
        """
    
    fuzzy_records, _, _ = await driver.execute_query(fuzzy_query, group_id=node.group_id)
    
    # Check each candidate with SequenceMatcher
    for record in fuzzy_records:
        existing_node = EntityNode.model_validate(record['n'])
        similarity = calculate_fuzzy_similarity(node.name, existing_node.name)
        
        fuzzy_threshold = float(os.getenv('DEDUP_FUZZY_THRESHOLD', '0.8'))
        if similarity >= fuzzy_threshold:
            # Found fuzzy match - resolve immediately
            resolved_nodes.append(existing_node)
            uuid_map[node.uuid] = existing_node.uuid
            node_duplicates.append((node, existing_node))
            fuzzy_match_found = True
            break
```

**Effectiveness**: Limited to 50 candidates and uses fast SequenceMatcher for similarity.

### Stage 4: LLM-Based Hybrid Search (❌ UNBOUNDED)
**Location**: `graphiti_core/utils/maintenance/node_operations.py:528-585`

```python
# For remaining nodes, use the existing LLM-based resolution
search_results: list[SearchResults] = await semaphore_gather(
    *[
        search(
            clients=clients,
            query=node.name,
            group_ids=None if enable_cross_graph_deduplication else [node.group_id],
            search_filter=SearchFilters(),
            config=NODE_HYBRID_SEARCH_RRF,  # ❌ NO EXPLICIT LIMIT
        )
        for node in nodes_needing_llm_resolution
    ]
)
```

**Problem**: The `search()` function uses `NODE_HYBRID_SEARCH_RRF` configuration which has no explicit limit, defaulting to `DEFAULT_SEARCH_LIMIT = 10` but applying `2 * limit` multipliers.

## Search System Analysis

### Search Configuration Limits
**Location**: `graphiti_core/search/search_config.py:29`

```python
DEFAULT_SEARCH_LIMIT = 10  # Base limit
```

**Location**: `graphiti_core/search/search_config_recipes.py:156-161`

```python
# performs a hybrid search over nodes with rrf reranking
NODE_HYBRID_SEARCH_RRF = SearchConfig(
    node_config=NodeSearchConfig(
        search_methods=[NodeSearchMethod.bm25, NodeSearchMethod.cosine_similarity],
        reranker=NodeReranker.rrf,
    )
    # ❌ NO EXPLICIT LIMIT - uses DEFAULT_SEARCH_LIMIT = 10
)
```

### Search Execution with 2x Multipliers
**Location**: `graphiti_core/search/search.py:315-327`

```python
search_results: list[list[EntityNode]] = list(
    await semaphore_gather(
        *[
            node_fulltext_search(driver, query, search_filter, group_ids, 2 * limit),  # 20 results
            node_similarity_search(
                driver, query_vector, search_filter, group_ids, 2 * limit, config.sim_min_score  # 20 results
            ),
            node_bfs_search(
                driver, bfs_origin_node_uuids, search_filter, config.bfs_max_depth, 2 * limit  # 20 results
            ),
        ]
    )
)
```

**Result**: Each search method can return up to 20 results, totaling up to 60 candidates before reranking.

### Reranking and Final Selection
**Location**: `graphiti_core/search/search.py:328-378`

```python
# Combine and deduplicate search results
combined_results = []
seen_uuids = set()
for result_list in search_results:
    for result in result_list:
        if result.uuid not in seen_uuids:
            combined_results.append(result)
            seen_uuids.add(result.uuid)

# Apply reranking (RRF, MMR, etc.)
reranked_results = await rerank_nodes(...)

# ❌ NO FINAL LIMIT APPLIED - ALL RERANKED RESULTS PASSED TO LLM
return reranked_results
```

**Problem**: After deduplication and reranking, ALL results are passed to the LLM prompt, which can be 50+ entities.

## Prompt Construction Analysis

### Deduplication Prompt Template
**Location**: `graphiti_core/prompts/dedupe_nodes.py:79-81`

```python
<EXISTING ENTITIES>
{json.dumps(context['existing_nodes'], indent=2)}  # ❌ UNBOUNDED LIST
</EXISTING ENTITIES>
```

### Context Building
**Location**: `graphiti_core/utils/maintenance/node_operations.py:541-585`

```python
# Build context for LLM deduplication
for i, (node, search_result) in enumerate(zip(nodes_needing_llm_resolution, search_results)):
    existing_nodes = [
        {
            'name': n.name,
            'labels': n.labels,
            'uuid': n.uuid,
            'summary': n.summary,
        }
        for n in search_result.nodes  # ❌ ALL SEARCH RESULTS INCLUDED
    ]
    
    # Call LLM with potentially large context
    response = await llm_client.dedupe_entities(...)
```

**Problem**: All search results (potentially 50+ entities) are included in the LLM prompt for each node being deduplicated.

## Bulk Processing Analysis

### Batch Deduplication Context
**Location**: `graphiti_core/utils/maintenance/node_operations.py:823-838`

```python
# Get existing entities for batch processing
existing_query = """
MATCH (n:Entity)
WHERE n.group_id IN $group_ids
RETURN n
LIMIT 100  # ✅ BOUNDED TO 100 FOR BATCH
"""

records, _, _ = await driver.execute_query(existing_query, group_ids=all_group_ids)

existing_nodes = [
    {
        'name': record['n']['name'],
        'labels': record['n'].get('labels', []),
        'uuid': record['n']['uuid'],
        'summary': record['n'].get('summary', '')
    }
    for record in records  # Up to 100 entities
]

# Make single batch LLM call
llm_response = await llm_client.dedupe_entities_batch(
    episodes_nodes_for_llm,
    episode_contents,
    existing_nodes  # ❌ UP TO 100 ENTITIES IN PROMPT
)
```

**Problem**: Batch processing can include up to 100 existing entities in a single prompt, multiplied by the number of episodes being processed.

## Critical Code Locations Requiring Changes

### 1. Individual Search Limit (HIGH PRIORITY)
**File**: `graphiti_core/utils/maintenance/node_operations.py:528-540`
**Issue**: No limit on search results passed to LLM
**Fix**: Add explicit limit to search configuration

### 2. Batch Processing Limit (HIGH PRIORITY)  
**File**: `graphiti_core/utils/maintenance/node_operations.py:823-838`
**Issue**: Up to 100 entities in batch prompts
**Fix**: Reduce limit or implement staged filtering

### 3. Search Configuration Defaults (MEDIUM PRIORITY)
**File**: `graphiti_core/search/search_config_recipes.py:156-161`
**Issue**: No explicit limits in search configs
**Fix**: Add explicit limits to search configurations

### 4. Search Result Processing (MEDIUM PRIORITY)
**File**: `graphiti_core/search/search.py:328-378`
**Issue**: No final limit after reranking
**Fix**: Apply final limit before returning results

## Recommended Fixes (No New Variables)

### Fix 1: Limit Search Results in Deduplication
```python
# In resolve_extracted_nodes(), modify search call:
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

### Fix 2: Reduce Batch Processing Context
```python
# In resolve_extracted_nodes_batch(), reduce existing entity limit:
existing_query = """
MATCH (n:Entity)
WHERE n.group_id IN $group_ids
RETURN n
LIMIT 20  # Reduced from 100 to 20
"""
```

### Fix 3: Apply Final Limit to Search Results
```python
# In search.py, add final limit after reranking:
# Apply final limit based on config
final_limit = config.limit or DEFAULT_SEARCH_LIMIT
return reranked_results[:final_limit]
```

## Conclusion

Graphiti's staged deduplication is well-designed and effectively filters most duplicates through fast operations. The unbounded growth occurs specifically in the final LLM stage where search results are not limited. The fixes require minimal changes to existing code and no new configuration variables.
