# Vector Type Mismatch Error Analysis

**Date**: 2025-10-06
**Issue**: Disconnected nodes in graph due to failed edge invalidation queries
**Severity**: High - Prevents proper entity deduplication and graph connectivity

---

## Executive Summary

The Graphiti worker is experiencing repeated failures during edge invalidation queries, resulting in disconnected nodes throughout the graph. The root cause is a **type mismatch error** where FalkorDB expects `Vectorf32` or `Null` types for vector embeddings, but receives Python `List` objects instead.

This failure prevents the system from:
- Detecting duplicate entities
- Merging similar edges
- Maintaining proper graph connectivity
- Creating relationships between related entities

---

## Error Evidence

### Primary Error Message
```
redis.exceptions.ResponseError: Type mismatch: expected Null or Vectorf32 but was List
```

### Error Frequency
Based on log analysis, this error occurs **multiple times per minute** during active ingestion periods.

### Example Log Entries

#### Error Instance 1 (2025-10-06 12:27:48)
```
2025-10-06 12:27:48,575 - graphiti_core.graphiti - ERROR - Resilient ingestion failed for episode 190cc9d2-9e04-489b-8d65-9f6b10bf1920: Type mismatch: expected Null or Vectorf32 but was List
2025-10-06 12:27:48,576 - graphiti_core.ingestion.worker - INFO - Task msg-new will retry in 20 seconds
```

#### Error Instance 2 (2025-10-06 12:28:00)
```
2025-10-06 12:28:00,284 - graphiti_core.graphiti - ERROR - Resilient ingestion failed for episode 190cc9d2-9e04-489b-8d65-9f6b10bf1920: Type mismatch: expected Null or Vectorf32 but was List
2025-10-06 12:28:00,286 - graphiti_core.ingestion.worker - ERROR - Task msg-new failed (attempt 1)
```

#### Error Instance 3 (2025-10-06 12:33:14)
```
2025-10-06 12:33:14,694 - graphiti_core.driver.falkordb_driver - ERROR - Error executing FalkorDB query: Type mismatch: expected Null or Vectorf32 but was List
2025-10-06 12:33:14,694 - graphiti_core.graphiti - ERROR - Resilient ingestion failed for episode 5dfd378a-6040-4d9a-8605-e7c7400ef1e4: Type mismatch: expected Null or Vectorf32 but was List
```

---

## Technical Stack Trace

### Full Error Stack
```python
File "/app/graphiti_core/ingestion/worker.py", line 283, in _process_loop
  await self._process_task(task)

File "/app/graphiti_core/ingestion/worker.py", line 330, in _process_task
  await self._process_episode(task)

File "/app/graphiti_core/ingestion/worker.py", line 369, in _process_episode
  result = await self.graphiti.add_episode_resilient(...)

File "/app/graphiti_core/graphiti.py", line 753, in add_episode_resilient
  raise e

File "/app/graphiti_core/graphiti.py", line 690, in add_episode_resilient
  (resolved_edges, invalidated_edges), hydrated_nodes = await semaphore_gather(...)

File "/app/graphiti_core/utils/maintenance/edge_operations.py", line 340, in resolve_extracted_edges
  search_results = await semaphore_gather(...)

File "/app/graphiti_core/search/search_utils.py", line 1013, in get_edge_invalidation_candidates
  return await get_edge_invalidation_candidates_batch(...)

File "/app/graphiti_core/search/search_utils.py", line 892, in get_edge_invalidation_candidates_batch
  batch_results = await get_edge_invalidation_candidates_single_batch(...)

File "/app/graphiti_core/search/search_utils.py", line 985, in get_edge_invalidation_candidates_single_batch
  raise e

File "/app/graphiti_core/search/search_utils.py", line 959, in get_edge_invalidation_candidates_single_batch
  results, _, _ = await driver.execute_query(...)

File "/app/graphiti_core/driver/falkordb_driver.py", line 217, in execute_query
  result = await graph.query(cypher_query_, params)

File "/usr/local/lib/python3.11/site-packages/falkordb/asyncio/graph.py", line 105, in query
  return await self._query(q, params=params, timeout=timeout, read_only=False)

redis.exceptions.ResponseError: Type mismatch: expected Null or Vectorf32 but was List
```

### Critical Code Path
1. **Entry Point**: `get_edge_invalidation_candidates_single_batch()` at `search_utils.py:959`
2. **Query Execution**: `falkordb_driver.py:217` - `await graph.query(cypher_query_, params)`
3. **Failure Point**: FalkorDB query execution with vector parameters

---

## Root Cause Analysis

### The Problem

When processing edges for invalidation checking, the system:

1. **Extracts edges** with embeddings as Python lists
2. **Prepares query parameters** containing edge data including `fact_embedding` fields
3. **Executes Cypher query** using `UNWIND $edges AS edge`
4. **Compares vectors** using `vec.cosineDistance(e.fact_embedding, edge.fact_embedding)`

### Where It Breaks

**Location**: `graphiti_core/search/search_utils.py:916-962`

```python
# Line 916: Generate cosine similarity function
cosine_func = get_vector_cosine_func_query('e.fact_embedding', 'edge.fact_embedding', driver.provider)

# Lines 952-956: Prepare edges data
edges_data = [edge.model_dump() for edge in edges]
for edge_values in edges_data:
    embedding = edge_values.get('fact_embedding')
    if isinstance(embedding, list) and len(embedding) == 0:
        edge_values['fact_embedding'] = None

# Lines 959-962: Execute query - THIS IS WHERE IT FAILS
results, _, _ = await driver.execute_query(
    query,
    params=query_params,
    edges=edges_data,  # Contains fact_embedding as Python list
    limit=limit,
    min_score=min_score,
    routing_='r',
)
```

### The Query Structure

```cypher
UNWIND $edges AS edge
MATCH (n:Entity)-[e:RELATES_TO {group_id: edge.group_id}]->(m:Entity)
WHERE n.uuid IN [edge.source_node_uuid, edge.target_node_uuid]
   OR m.uuid IN [edge.target_node_uuid, edge.source_node_uuid]
WITH edge, e, (2 - vec.cosineDistance(e.fact_embedding, vecf32(edge.fact_embedding)))/2 AS score
WHERE score > $min_score
...
```

### Why It Fails

1. **`$edges` parameter** contains a list of dictionaries
2. Each dictionary has a `fact_embedding` field as a **Python list** (e.g., `[0.123, 0.456, ...]`)
3. **`UNWIND $edges AS edge`** creates individual edge objects
4. **`edge.fact_embedding`** is accessed in the query as a nested field
5. Even though `get_vector_cosine_func_query()` wraps it with `vecf32(edge.fact_embedding)`, FalkorDB **cannot convert the nested list** to `Vectorf32` type
6. FalkorDB expects the data to already be in `Vectorf32` format or be properly convertible

---

## Follow-up Regression Identified (2025-10-07)

While verifying the per-edge refactor, two regressions were uncovered:

- The updated Cypher projection omitted `e.fact_embedding`, which meant `get_entity_edge_from_record()` raised a `KeyError` when materialising invalidation candidates.
- Test harness scripts (`test_edge_invalidation_fix.py`, `test_simple_batch_invalidation.py`) still imported the removed `get_edge_invalidation_candidates_single_batch()` helper, causing immediate import failures and masking regressions.

Both issues have now been addressed by restoring the projection field, switching call-sites to `get_edge_invalidation_candidates_batch()`, and supplying the required parameters in the tests.

### Vector Wrapping Logic

**Location**: `graphiti_core/graph_queries.py:98-121`

```python
def get_vector_cosine_func_query(vec1, vec2, db_type: str = 'neo4j') -> str:
    if db_type == 'falkordb':
        def should_wrap_in_vecf32(vec_param: str) -> bool:
            # Graph properties (n.*, e.*, r.*, etc.) are already Vectorf32 - DON'T wrap
            if '.' in vec_param and not vec_param.startswith(('edge.', 'node.', 'entity.', 'relationship.', 'item.')):
                return False
            # Query parameters ($*) need wrapping
            if vec_param.startswith('$'):
                return True
            # UNWIND parameters (edge.*, node.*, etc.) NEED wrapping
            if vec_param.startswith(('edge.', 'node.', 'entity.', 'relationship.', 'item.')):
                return True  # ← Correctly identifies need for wrapping
            return False

        falkor_vec1 = f'vecf32({vec1})' if should_wrap_in_vecf32(vec1) else vec1
        falkor_vec2 = f'vecf32({vec2})' if should_wrap_in_vecf32(vec2) else vec2
        return f'(2 - vec.cosineDistance({falkor_vec1}, {falkor_vec2}))/2'
```

**The code correctly identifies** that `edge.fact_embedding` needs wrapping, but:
- The wrapping happens **at the query string level**: `vecf32(edge.fact_embedding)`
- FalkorDB **cannot convert** the nested list from the UNWIND parameter at runtime
- The data structure itself needs to be converted **before** being passed to the query

---

## Impact on Graph Connectivity

### Consequences of Failed Edge Invalidation

When edge invalidation queries fail, the system **cannot detect** when:
- A new edge is similar to an existing edge (should be merged)
- A new entity is a duplicate of an existing entity (should be deduplicated)
- Relationships should be updated or invalidated

### Result: Disconnected Nodes

1. **Duplicate entities created**: Instead of merging with existing entities, new isolated nodes are created
2. **Missing relationships**: Edges that should connect entities are not created
3. **Failed deduplication**: The LLM identifies duplicates, but the system cannot validate them against existing data
4. **Graph fragmentation**: Related concepts exist as separate islands rather than connected subgraphs

### Evidence from Logs

#### Successful Processing (When It Works)
```
2025-10-06 12:32:58,157 - graphiti_core.utils.resilient_ingestion - INFO - Episode 5dfd378a-6040-4d9a-8605-e7c7400ef1e4: Nodes extracted (2 nodes)
2025-10-06 12:32:58,157 - graphiti_core.graphiti - INFO - Episode 5dfd378a-6040-4d9a-8605-e7c7400ef1e4: Resolving nodes (attempt 1)
2025-10-06 12:32:58,188 - graphiti_core.utils.resilient_ingestion - INFO - Episode 5dfd378a-6040-4d9a-8605-e7c7400ef1e4: Nodes resolved (2 nodes)
2025-10-06 12:32:58,188 - graphiti_core.graphiti - INFO - Episode 5dfd378a-6040-4d9a-8605-e7c7400ef1e4: Extracting edges (attempt 1)
```

#### Failed Processing (Vector Mismatch)
```
2025-10-06 12:33:14,094 - graphiti_core.search.search_utils - INFO - Processing 2 edges for invalidation in batches of 5
2025-10-06 12:33:14,694 - graphiti_core.driver.falkordb_driver - ERROR - Error executing FalkorDB query: Type mismatch: expected Null or Vectorf32 but was List
2025-10-06 12:33:14,715 - graphiti_core.ingestion.worker - INFO - Task msg-new will retry in 20 seconds
```

---

## Secondary Issues

### 1. Invalid LLM Resolution IDs

**Error Pattern**:
```
2025-10-06 12:33:30,626 - graphiti_core.utils.maintenance.node_operations - WARNING - Invalid resolution_id 5 for chunk starting at 0 (size 4). Skipping resolution.
2025-10-06 12:33:30,626 - graphiti_core.utils.maintenance.node_operations - WARNING - Invalid resolution_id 6 for chunk starting at 0 (size 4). Skipping resolution.
2025-10-06 12:33:30,626 - graphiti_core.utils.maintenance.node_operations - WARNING - Invalid resolution_id 7 for chunk starting at 0 (size 4). Skipping resolution.
```

**Context**:
```python
# LLM returned 11 entity resolutions but only 4 entities in chunk
2025-10-06 12:33:30,626 - graphiti_core.utils.maintenance.node_operations - INFO - LLM node dedupe response for chunk starting at 0: {
    'entity_resolutions': [
        {'id': 1, 'duplicate_idx': -1, 'name': 'GitHub', 'duplicates': []},
        {'id': 2, 'duplicate_idx': -1, 'name': 'src/tools/index.js', 'duplicates': []},
        {'id': 3, 'duplicate_idx': -1, 'name': '/opt/stacks/bookstack-mcp/...', 'duplicates': []},
        {'id': 4, 'duplicate_idx': -1, 'name': 'update_skills_tool.js', 'duplicates': []},
        {'id': 5, 'duplicate_idx': -1, 'name': 'update_languages_tool.js', 'duplicates': []},  # ← Out of bounds
        {'id': 6, 'duplicate_idx': -1, 'name': 'update_awards_tool.js', 'duplicates': []},      # ← Out of bounds
        ...
    ]
}
```

**Impact**: Entities that should be deduplicated are skipped, creating additional isolated nodes.

**Location**: `graphiti_core/utils/maintenance/node_operations.py:333`

### 2. Index Out of Range Errors

**Error**:
```
2025-10-06 12:32:35,208 - graphiti_core.utils.resilient_ingestion - ERROR - _extract_nodes_with_retry failed with unexpected error: list index out of range
IndexError: list index out of range
  File "/app/graphiti_core/utils/maintenance/node_operations.py", line 333, in extract_nodes
    entity_type_name = entity_types_context[extracted_entity.entity_type_id].get(...)
                       ~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

**Impact**: Complete episode ingestion failure, preventing any graph updates.

---

## Attempted Fixes in Codebase

### Vector Wrapping Mechanisms

**File**: `graphiti_core/driver/falkordb_driver.py`

#### 1. Query-Level Vector Wrapping (Lines 68-129)
```python
def _wrap_vector_params_in_query(query: str, params: dict[str, Any]) -> str:
    """Wrap any $key in the query with vecf32($key) when the param is a vector-like list."""

    # Handle top-level vector parameters
    for key, val in params.items():
        if _is_vector_list(val):
            needle = f"${key}"
            wrapped = f"vecf32({needle})"
            if wrapped not in query:
                query = query.replace(needle, wrapped)

    # Handle nested vector parameters in UNWIND operations
    def _wrap_unwind_vectors(query_text: str) -> str:
        unwind_vector_patterns = [
            r'\b(edge\.(?:fact_)?embedding)\b',
            r'\b(node\.(?:name_|summary_)?embedding)\b',
            ...
        ]

        for pattern in unwind_vector_patterns:
            matches = re.finditer(pattern, query_text)
            for match in matches:
                original = match.group(1)
                context = query_text[context_start:context_end]

                # If in vector operation and not already wrapped
                if ('vec.cosineDistance' in context or 'vector.similarity' in context) and \
                   f'vecf32({original})' not in context:
                    replacements.append((start, end, f'vecf32({original})'))

        return query_text

    return _wrap_unwind_vectors(query)
```

**Problem**: This wraps the **query string** but doesn't convert the **data structure** passed in parameters.

#### 2. Empty List Handling (Lines 953-956)
```python
edges_data = [edge.model_dump() for edge in edges]
for edge_values in edges_data:
    embedding = edge_values.get('fact_embedding')
    if isinstance(embedding, list) and len(embedding) == 0:
        edge_values['fact_embedding'] = None  # Convert empty lists to None
```

**Problem**: Only handles empty lists, not the actual conversion to Vectorf32.

---

## Why Current Fixes Don't Work

### The Fundamental Issue

FalkorDB requires vector embeddings to be in `Vectorf32` format when:
1. **Stored in the database** - ✅ Works (database properties are already Vectorf32)
2. **Passed as query parameters** - ❌ **Fails for nested structures**

### Current Approach
- Wraps parameter references with `vecf32()` in the query string
- Example: `vecf32(edge.fact_embedding)`

### Why It Fails
- FalkorDB cannot convert nested Python lists at runtime via `vecf32()` function
- The `vecf32()` function works for **top-level parameters** like `$embedding`
- But fails for **nested parameters** like `edge.fact_embedding` from `UNWIND $edges AS edge`

### Analogy
Think of it like:
- ✅ `vecf32($myVector)` - FalkorDB can convert this
- ❌ `vecf32(edge.fact_embedding)` where edge comes from `UNWIND $edges` - FalkorDB cannot convert this

---

## Proof of Concept: What Should Work

### Correct Approach (Not Implemented)

**Convert data BEFORE passing to query**:

```python
# Current (BROKEN):
edges_data = [edge.model_dump() for edge in edges]
await driver.execute_query(query, edges=edges_data)  # edges_data contains list

# Correct (WOULD WORK):
from falkordb import VectorF32  # hypothetical

edges_data = [edge.model_dump() for edge in edges]
for edge_values in edges_data:
    embedding = edge_values.get('fact_embedding')
    if embedding and isinstance(embedding, list):
        edge_values['fact_embedding'] = VectorF32(embedding)  # Convert to FalkorDB type

await driver.execute_query(query, edges=edges_data)  # edges_data contains VectorF32
```

**Problem**: FalkorDB Python client **doesn't support** `VectorF32` objects in Python (as noted in code comments).

---

## Reproduction Steps

1. **Start worker**: `docker-compose up graphiti-worker`
2. **Ingest episode** with entities that need deduplication
3. **Monitor logs**: `docker logs graphiti-graphiti-worker-1 --follow`
4. **Observe**: "Processing N edges for invalidation in batches of 5"
5. **Wait**: Within seconds, error appears: "Type mismatch: expected Null or Vectorf32 but was List"
6. **Result**: Episode retries, nodes remain disconnected

---

## Proposed Solutions

### Option 1: Pre-convert Embeddings in Python (Preferred)
- Convert `fact_embedding` lists to FalkorDB-compatible format before query execution
- Requires FalkorDB client support for `VectorF32` objects
- **Blocker**: FalkorDB 1.2.0 Python client doesn't support this

### Option 2: Refactor Query to Avoid UNWIND
- Pass individual edges as separate parameters
- Use multiple queries instead of batch processing
- **Tradeoff**: Performance hit from multiple queries

### Option 3: Use Alternative Search Strategy
- Store embeddings as strings and convert at query time
- Use FalkorDB procedures instead of inline vector operations
- **Tradeoff**: Complex query refactoring

### Option 4: Fix FalkorDB Client
- Contribute to FalkorDB Python client to support VectorF32 in parameters
- Add proper type conversion for nested structures
- **Tradeoff**: External dependency, timeline uncertain

### Option 5: Workaround with String Encoding
- Encode vectors as comma-separated strings
- Parse and convert in query using FalkorDB functions
- **Tradeoff**: Ugly hack, potential performance issues

---

## Immediate Recommendations

1. **Document the issue** (✅ This document)
2. **File GitHub issue** with FalkorDB Python client project
3. **Implement Option 2** (refactor to avoid UNWIND) as temporary fix
4. **Add better error handling** to prevent episode failures
5. **Monitor graph quality** metrics to quantify impact

---

## Metrics to Track

- **Error frequency**: Occurrences per hour
- **Retry success rate**: How often retries succeed
- **Disconnected node count**: Growth rate of isolated entities
- **Edge creation failure rate**: Percentage of edges that fail to create
- **Deduplication effectiveness**: Ratio of duplicate nodes vs. merged nodes

---

## References

### Code Locations
- Edge invalidation: `graphiti_core/search/search_utils.py:892-986`
- Vector wrapping: `graphiti_core/driver/falkordb_driver.py:68-129`
- Cosine function: `graphiti_core/graph_queries.py:98-121`
- Worker processing: `graphiti_core/ingestion/worker.py:283-369`

### Log Files
- Worker logs: `docker logs graphiti-graphiti-worker-1`
- Error patterns: Search for "Type mismatch" and "expected Null or Vectorf32"

### Related Issues
- Invalid resolution IDs
- Index out of range errors
- Memory exhaustion in large batches

---

**End of Analysis**

## Additional Mandatory Constraint Issues Discovered (2025-10-06 23:00+)

After fixing the initial edge and node save constraints, additional issues were found during node merge operations:

### Issue 3: Node Merge Edge Transfer Missing UUID
**Location**: `graphiti_core/utils/maintenance/node_operations.py:1393-1401`
**Error**: `mandatory constraint violation: edge with relationship-type RELATES_TO missing property uuid`

**Problem**: When transferring edges during node deduplication/merge, the CREATE statement doesn't provide a `uuid` for the new edge:
```python
create_query = f"""
MATCH (canonical:Entity {{uuid: $canonical_uuid}})
MATCH (target:Entity {{uuid: $target_uuid}})
CREATE (canonical)-[r:{rel_type}]->(target)  # Missing uuid!
SET r = $props
RETURN r
"""
```

**Required Fix**: Generate a UUID for the edge during transfer:
```python
import uuid
props['uuid'] = str(uuid.uuid4())
# Then the CREATE will have uuid in props
```

### Summary of All FalkorDB Mandatory Constraint Fixes Required

1. **✅ FIXED**: Edge save - include `group_id` in MERGE pattern (line 167)
2. **✅ FIXED**: Node save - include `name` and `group_id` in MERGE pattern (line 142)  
3. **✅ FIXED**: Node merge edge transfer - generate `uuid` before CREATE (line 1393)
4. **✅ FIXED**: Legacy list embeddings backfilled to `Vectorf32` for FalkorDB
5. **ℹ️ NOTE**: Per-edge invalidation now skips stale edges; guard log will surface if additional conversion is needed

The root cause is FalkorDB's strict mandatory constraints require all specified properties to be present at creation time, and vector values must be stored as `Vectorf32` rather than bare Python lists.

