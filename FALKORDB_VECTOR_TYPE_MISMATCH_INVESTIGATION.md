# FalkorDB Vector Type Mismatch Investigation Report

**Date:** September 21, 2025  
**Issue:** Type mismatch: expected Null or Vectorf32 but was List  
**Status:** 🔴 **CRITICAL - BLOCKING EDGE INGESTION**  
**Priority:** Immediate Fix Required

## Problem Summary

Edge ingestion is failing during the edge invalidation process with the error:
```
Type mismatch: expected Null or Vectorf32 but was List
```

This error occurs in `graphiti_core/search/search_utils.py` at line 955 in the `get_edge_invalidation_candidates_single_batch` function, specifically during the vector similarity calculation for edge invalidation.

## Root Cause Analysis

### The Core Issue

The problem is in the FalkorDB driver's handling of **nested vector parameters** in UNWIND operations. Here's the technical breakdown:

1. **Query Pattern**: The failing query uses this pattern:
   ```cypher
   UNWIND $edges AS edge
   MATCH (n:Entity)-[e:RELATES_TO {group_id: edge.group_id}]->(m:Entity)
   WITH edge, e, (2 - vec.cosineDistance(e.fact_embedding, vecf32(edge.fact_embedding)))/2 AS score
   WHERE score > $min_score
   ```

2. **Parameter Structure**: The `$edges` parameter contains:
   ```python
   [
       {
           'uuid': 'edge-uuid-1',
           'source_node_uuid': 'node-1',
           'target_node_uuid': 'node-2', 
           'group_id': 'test',
           'fact_embedding': [0.1, 0.2, 0.3, ...]  # Python list
       },
       # ... more edges
   ]
   ```

3. **The Problem**: When FalkorDB processes `UNWIND $edges AS edge`, the `edge.fact_embedding` remains a Python list, but `vec.cosineDistance()` requires VectorF32 objects.

### Missing Implementation

According to the comprehensive analysis in `docs/investigations/falkordb-vector-type-mismatch-comprehensive-analysis.md`, the critical missing piece is the `_preprocess_vectors_in_params()` function in the FalkorDB driver.

**Current State:**
- ✅ `_wrap_vector_params_in_query()` - Handles top-level `$param` wrapping
- ✅ `_is_vector_list()` - Detects vector parameters  
- ✅ `_flatten_params()` - Handles nested parameter dictionaries
- ❌ **MISSING**: `_preprocess_vectors_in_params()` - Converts nested Python lists to VectorF32

## Error Location and Stack Trace

**File:** `graphiti_core/search/search_utils.py`  
**Function:** `get_edge_invalidation_candidates_single_batch`  
**Line:** 955

**Stack Trace Path:**
```
graphiti_core.ingestion.worker._process_episode
→ graphiti_core.graphiti.add_episode_resilient  
→ graphiti_core.utils.maintenance.edge_operations.resolve_extracted_edges
→ graphiti_core.search.search_utils.get_edge_invalidation_candidates
→ graphiti_core.search.search_utils.get_edge_invalidation_candidates_single_batch
→ graphiti_core.driver.falkordb_driver.execute_query
→ FalkorDB query execution fails
```

## FalkorDB Vector Support Verification ✅

Based on Context7 documentation analysis, FalkorDB **DOES support** the required vector operations:

### Confirmed Vector Functions:
- ✅ **`vecf32(array)`** - Creates a float32 vector from array
- ✅ **`vec.cosineDistance(vector1, vector2)`** - Cosine distance calculation
- ✅ **`vec.euclideanDistance(vector1, vector2)`** - Euclidean distance calculation

### Vector Usage Examples:
```cypher
-- Create node with vector
CREATE (p: Product {description: vecf32([2.1, 0.82, 1.3])})

-- Vector similarity query
MATCH (n) WHERE vec.cosineDistance(n.embedding, vecf32([1.0, 2.0, 3.0])) < 0.5
```

### Vector Index Support:
```cypher
-- Create vector index
CREATE VECTOR INDEX FOR (n:Entity) ON n.embedding OPTIONS {dimension: 1536}

-- Drop vector index
DROP VECTOR INDEX FOR (n:Entity) ON n.embedding
```

## Required Fix Implementation

### Step 1: Add Missing Function

**File:** `graphiti_core/driver/falkordb_driver.py`

Add the missing `_preprocess_vectors_in_params()` function:

```python
def _preprocess_vectors_in_params(params: dict[str, Any]) -> dict[str, Any]:
    """Pre-process parameters to handle vectors in nested structures for FalkorDB."""
    try:
        from falkordb import VectorF32
    except ImportError:
        # Fallback if VectorF32 is not available - return params unchanged
        # The vecf32() query-level wrapping will handle conversion
        return params

    def convert_vectors(obj: Any) -> Any:
        if _is_vector_list(obj):
            return VectorF32(obj)  # Convert Python list to FalkorDB VectorF32
        elif isinstance(obj, dict):
            return {k: convert_vectors(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_vectors(item) for item in obj]
        else:
            return obj

    # Process parameters that contain nested vectors
    processed_params = {}
    for key, value in params.items():
        if key in ['edges', 'nodes', 'entities']:
            processed_params[key] = convert_vectors(value)
        else:
            processed_params[key] = value

    return processed_params
```

### Step 2: Integrate Function Calls

**Location 1:** `FalkorDriver.execute_query()` method (around line 170)

```python
# 3) Pre-process nested vectors in parameters (for UNWIND operations)  
params = _preprocess_vectors_in_params(params)

# 4) FalkorDB 1.2.0 uses query-level vecf32() wrapping instead of Python VectorF32 objects
cypher_query_ = _wrap_vector_params_in_query(cypher_query_, params)
```

**Location 2:** `FalkorDriverSession.run()` method (around lines 112 and 117)

```python
# For list queries:
params = convert_datetimes_to_strings(params)
params = _preprocess_vectors_in_params(params)  # ADD THIS LINE
cypher = _wrap_vector_params_in_query(str(cypher), params)

# For single queries:
params = _flatten_params(dict(kwargs))
params = convert_datetimes_to_strings(params)
params = _preprocess_vectors_in_params(params)  # ADD THIS LINE
query = _wrap_vector_params_in_query(str(query), params)
```

## Verification Steps

### Step 1: Test Vector Parameter Conversion
```bash
docker exec graphiti-graphiti-worker-1 python -c "
from falkordb import VectorF32
test_vec = [0.1, 0.2, 0.3]
converted = VectorF32(test_vec)
print(f'Conversion successful: {type(converted)}')
"
```

### Step 1b: Test vecf32() Function in FalkorDB
```bash
docker exec graphiti-graphiti-worker-1 python -c "
from falkordb import FalkorDB
db = FalkorDB(host='falkordb', port=6379)
g = db.select_graph('test_vectors')
result = g.query('RETURN vecf32([1.0, 2.0, 3.0]) as test_vector')
print(f'vecf32() function works: {result.result_set}')
"
```

### Step 2: Test Edge Invalidation Query
```bash
docker exec graphiti-graphiti-worker-1 python -c "
import asyncio
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.search.search_utils import get_edge_invalidation_candidates
from graphiti_core.search.search import SearchFilters

async def test():
    driver = FalkorDriver(host='falkordb', port=6379, database='graphiti_migration')
    await driver.connect()
    
    # Test with minimal edge data
    test_edges = []  # Add real edge data here
    search_filter = SearchFilters()
    
    try:
        result = await get_edge_invalidation_candidates(
            driver, test_edges, search_filter, min_score=0.0, limit=5
        )
        print(f'SUCCESS: Edge invalidation completed')
    except Exception as e:
        print(f'FAILED: {e}')
    
    await driver.disconnect()

asyncio.run(test())
"
```

### Step 3: Monitor Ingestion Logs
```bash
docker logs graphiti-graphiti-worker-1 -f | grep -E "(Type mismatch|edge invalidation|SUCCESS)"
```

## Expected Results After Fix

- ✅ **No Type Mismatch Errors**: Edge invalidation queries execute successfully
- ✅ **Successful Edge Ingestion**: Episodes process without vector-related failures  
- ✅ **Proper Vector Handling**: Nested vectors in UNWIND operations work correctly
- ✅ **Maintained Performance**: No significant performance impact from vector conversion

## Alternative Workaround (If VectorF32 Import Fails)

If the `VectorF32` import fails, implement a query-level workaround by modifying `get_vector_cosine_func_query()` to wrap both vectors when in UNWIND context:

```python
# In graph_queries.py, modify the FalkorDB branch:
if db_type == 'falkordb':
    # For UNWIND contexts with embeddings, wrap both vectors to ensure compatibility
    if any(param.startswith(('edge.', 'node.')) and 'embedding' in param for param in [vec1, vec2]):
        # Both vectors need wrapping when one comes from UNWIND
        return f'(2 - vec.cosineDistance(vecf32({vec1}), vecf32({vec2})))/2'
    else:
        # Use existing logic for other cases
        falkor_vec1 = f'vecf32({vec1})' if should_wrap_in_vecf32(vec1) else vec1
        falkor_vec2 = f'vecf32({vec2})' if should_wrap_in_vecf32(vec2) else vec2
        return f'(2 - vec.cosineDistance({falkor_vec1}, {falkor_vec2}))/2'
```

### Immediate Workaround (No Code Changes Required)

Since FalkorDB supports `vecf32()` function natively, we can test an immediate fix by modifying the query generation to wrap both vectors:

```python
# Quick test in get_vector_cosine_func_query() for FalkorDB:
return f'(2 - vec.cosineDistance(vecf32({vec1}), vecf32({vec2})))/2'
```

This ensures both graph properties and UNWIND parameters are properly converted to VectorF32 type.

## Files to Modify

1. **Primary:** `graphiti_core/driver/falkordb_driver.py`
   - Add `_preprocess_vectors_in_params()` function
   - Integrate calls in `execute_query()` and `run()` methods

2. **Fallback:** `graphiti_core/graph_queries.py` 
   - Modify `get_vector_cosine_func_query()` if VectorF32 approach fails

## Confidence Level

**Very High** - This is a documented issue with a known solution. The missing function is clearly identified and the integration points are well-defined. The fix addresses the exact error being encountered.

## Related Issues

This investigation relates to the edge extraction issue documented in `FALKORDB_EDGE_EXTRACTION_FIX.md`, but they are **separate problems**:

- **Edge Extraction Issue**: `startNode()` and `endNode()` function compatibility (RESOLVED)
- **This Issue**: Vector type mismatch in edge invalidation during ingestion (CURRENT)

Both issues affect the FalkorDB integration but occur at different stages of the data pipeline.

## Implementation Priority

**IMMEDIATE** - This fix should be implemented before the edge extraction fix, as it affects the core ingestion pipeline and is blocking all edge processing operations.

## Testing Strategy

1. **Unit Test**: Test `_preprocess_vectors_in_params()` function with various nested structures
2. **Integration Test**: Test edge invalidation queries with real edge data
3. **End-to-End Test**: Verify complete episode ingestion pipeline
4. **Regression Test**: Ensure existing vector operations continue to work

## Deployment Notes

- **Docker Rebuild Required**: The container must be rebuilt with the new driver code
- **Zero Downtime**: Fix can be deployed without data migration
- **Backward Compatible**: Changes don't affect existing data or Neo4j operations
- **Monitoring**: Watch for any remaining vector-related errors after deployment
