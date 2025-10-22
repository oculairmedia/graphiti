# Vector Type Mismatch - Deep Investigation Results

## Root Cause Analysis

**Problem**: FalkorDB rejects Python lists when expecting Vectorf32 type
**Error**: "Type mismatch: expected Null or Vectorf32 but was List"

## Key Findings

### 1. FalkorDB Python Client Limitation
- FalkorDB 1.2.0 Python client does NOT have a `Vectorf32` class
- Attempt to `from falkordb import Vectorf32` raises `ImportError`
- Vectors must be passed as Python lists and converted in Cypher using `vecf32()`

### 2. Current Approach
- Keep embeddings as Python lists in code
- Use `vecf32($param)` in Cypher queries for query parameters
- Use `vecf32(edge.fact_embedding)` / `vecf32(node.name_embedding)` for UNWIND parameters in SET operations
- Graph properties (e.*, n.*, r.*) when reading from DB are already Vectorf32 - don't wrap

### 3. Automatic Wrapping Logic
The driver has `_wrap_vector_params_in_query()` that should automatically wrap:
- Query parameters ($param) that are vector lists
- BUT: Only wraps UNWIND parameters when in `vec.cosineDistance` context
- Does NOT wrap UN WIND params in SET/MERGE operations

### 4. Manual Fixes Applied
- Line 174 in graph_queries.py: `r.fact_embedding = vecf32(edge.fact_embedding)`
- Line 148 in graph_queries.py: `SET n.name_embedding = vecf32(node.name_embedding)`
- Line 110 in graph_queries.py: Restored wrapping for $params in cosine similarity

## Remaining Issue

**Status**: STILL FAILING with same error after all fixes

**Hypothesis**: There may be OTHER query paths we haven't identified:
1. Edge invalidation queries (get_edge_invalidation_candidates)
2. Node deduplication queries  
3. Edge attribute updates
4. Episodic edge saves (though they shouldn't have embeddings)

## Next Steps

1. **Add Debug Logging**:
   - Log the actual Cypher query being executed when error occurs
   - Log the params being passed
   - Identify which specific query/operation is failing

2. **Search All Cypher Queries**:
   - Grep for all UNWIND operations
   - Find all SET operations that touch embeddings
   - Check edge/node update queries

3. **Test Isolated Operations**:
   - Test just saving a node with embedding
   - Test just saving an edge with embedding
   - Test edge invalidation in isolation
   - Identify which specific operation fails

4. **Consider Alternative**:
   - Disable embedding-based operations temporarily
   - Focus on getting basic graph writes working first
   - Add embeddings back incrementally

## Files Modified This Session

1. `/opt/stacks/graphiti/graphiti_core/driver/falkordb_driver.py`
   - Added database logging (not yet visible in logs)
   - Fixed bug: database not set when falkor_db parameter provided

2. `/opt/stacks/graphiti/graphiti_core/graph_queries.py`
   - Restored `vecf32()` wrapping for $params (line 110)
   - Added `vecf32(edge.fact_embedding)` to edge save (line 174)
   - Added `vecf32(node.name_embedding)` to node save (line 148)

3. `/opt/stacks/graphiti/graphiti_core/utils/bulk_utils.py`
   - Attempted Vectorf32 conversion (later removed)
   - All embedding fields now pass as raw Python lists

## Current Worker Image

- **Image**: graphiti-worker-local:latest (5377148761c8)
- **Status**: Running, processing episodes
- **Result**: All episodes failing with vector type mismatch

## Database State

- **Target DB**: graphiti_migration (44K edges, populated)
- **Worker writes to**: graphiti_migration (correct)  
- **Empty DB**: default_db, graph (not used)
