# Database Corruption Investigation Report

## Problem Summary
The database contains duplicate entities that are being detected and marked with `IS_DUPLICATE_OF` relationships, but the duplicates are **not being physically removed** from the database. This results in:
- 6 "assistant" entities with same name and group_id but different UUIDs
- 6 "Claude" entities with same name and group_id but different UUIDs
- `IS_DUPLICATE_OF` relationships exist, indicating detection is working
- Physical duplicate nodes remain in database, indicating cleanup is failing

## Root Cause Analysis

### 1. Deduplication Detection vs. Removal Gap

The system has **two separate phases** that are not properly coordinated:

#### Phase 1: Detection (Working ✅)
- `build_duplicate_of_edges()` creates `IS_DUPLICATE_OF` relationships
- `run_deduplication.py` script creates these audit edges
- Detection thresholds: 0.8 for nodes, 0.6 for edges

#### Phase 2: Physical Removal (Failing ❌)
- `merge_node_into()` should transfer edges and mark nodes as merged
- `_delete_duplicate_nodes()` should physically delete duplicates
- This phase is **not being executed** in the current workflow

### 2. Workflow Analysis

#### Current Broken Workflow:
```
1. Duplicates detected → IS_DUPLICATE_OF edges created
2. merge_operations generated but NOT executed
3. Duplicate nodes remain in database with tombstone flags
```

#### Expected Working Workflow:
```
1. Duplicates detected → IS_DUPLICATE_OF edges created
2. merge_operations executed → edges transferred
3. Duplicate nodes marked as merged (tombstone)
4. Optional: Physical deletion of duplicate nodes
```

### 3. Code Issues Identified

#### Issue 1: `run_deduplication.py` - Incomplete Execution
**File**: `run_deduplication.py` (Lines 164-168)
```python
# Execute merge operations
if merge_operations:
    from graphiti_core.utils.maintenance.edge_operations import execute_merge_operations
    await execute_merge_operations(graphiti.driver, merge_operations)
    print(f'Merged edges from {dup_node.name} into {primary_node.name}')
```
**Problem**: This code exists but may not be executing properly or completely.

#### Issue 2: `merge_node_into()` - Tombstone vs. Deletion
**File**: `graphiti_core/utils/maintenance/node_operations.py` (Lines 889-902)
```python
# Step 4: Mark duplicate node as merged (optional tombstone)
tombstone_query = """
MATCH (duplicate:Entity {uuid: $duplicate_uuid})
SET duplicate.merged_into = $canonical_uuid,
    duplicate.merged_at = $merged_at,
    duplicate.is_merged = true
RETURN duplicate
"""
```
**Problem**: The function marks nodes as merged but **does NOT delete them**. It creates tombstones instead.

#### Issue 3: `maintenance_dedupe_entities.py` - Deletion Logic Exists But Not Called
**File**: `maintenance_dedupe_entities.py` (Lines 346-370)
```python
async def _delete_duplicate_nodes(self, primary_uuid: str, uuid_map: Dict[str, str]):
    """Delete duplicate nodes that have been merged"""
    delete_query = """
    UNWIND $duplicate_uuids AS dup_uuid
    MATCH (n:Entity {uuid: dup_uuid})
    WHERE n.uuid <> $primary_uuid
    DETACH DELETE n
    RETURN count(n) as deleted_count
    """
```
**Problem**: This deletion function exists and is called in `merge_duplicate_group()` (line 296), but this workflow is separate from the main deduplication pipeline.

### 4. Configuration Issues

#### Issue 4: No Deletion Configuration
There's no configuration flag to control whether duplicates should be:
- A) Tombstoned only (current behavior)
- B) Physically deleted (desired behavior)

#### Issue 5: Worker Deduplication vs. Maintenance Scripts
**File**: `graphiti_core/ingestion/worker.py` (Lines 540-545)
The worker uses `dedupe_extracted_nodes()` which may have different behavior than the maintenance scripts.

## Technical Details

### Merge Process Flow
1. **Detection**: `find_duplicate_candidates()` identifies similar entities
2. **Edge Creation**: `build_duplicate_of_edges()` creates audit relationships
3. **Merge Operations**: `execute_merge_operations()` calls `merge_node_into()`
4. **Edge Transfer**: All edges moved from duplicate to canonical node
5. **Tombstone**: Duplicate marked as `is_merged=true, merged_into=canonical_uuid`
6. **Missing Step**: Physical deletion never occurs

### Database State Analysis
Based on the evidence:
- Multiple entities with identical names and group_ids exist
- `IS_DUPLICATE_OF` relationships are present
- Entities likely have `is_merged=true` flags set
- Physical nodes remain in database causing query confusion

## Recommendations

### Immediate Fix Options

#### Option A: Enable Physical Deletion
Modify `merge_node_into()` to actually delete nodes after tombstoning:
```python
# After tombstone step, add:
if delete_after_merge:  # New parameter
    delete_query = "MATCH (n:Entity {uuid: $duplicate_uuid}) DETACH DELETE n"
    await driver.execute_query(delete_query, duplicate_uuid=duplicate_uuid)
```

#### Option B: Fix Maintenance Script Execution
Ensure `maintenance_dedupe_entities.py` is being used instead of incomplete workflows:
- This script has proper deletion logic in `_delete_duplicate_nodes()`
- It's called in `merge_duplicate_group()` at line 296

#### Option C: Query Filtering
Modify all entity queries to exclude merged nodes:
```cypher
MATCH (n:Entity)
WHERE (n.is_merged IS NULL OR n.is_merged = false)
RETURN n
```

### Long-term Solutions

1. **Unified Deduplication Pipeline**: Consolidate the various deduplication approaches
2. **Configuration Management**: Add settings for deletion vs. tombstone behavior
3. **Monitoring**: Add metrics to track duplicate creation vs. removal rates
4. **Testing**: Comprehensive tests for the full deduplication lifecycle

## Files Requiring Investigation/Changes

1. `run_deduplication.py` - Verify merge operations execute completely
2. `graphiti_core/utils/maintenance/node_operations.py` - Add deletion option
3. `maintenance_dedupe_entities.py` - Ensure this is the primary deduplication tool
4. `graphiti_core/ingestion/worker.py` - Align worker deduplication with maintenance scripts
5. Query files - Add merged node filtering where needed

## Next Steps

1. **Verify Current State**: Check if duplicate nodes have `is_merged=true` flags
2. **Test Deletion**: Run `maintenance_dedupe_entities.py` to see if it properly deletes
3. **Configuration**: Add deletion vs. tombstone configuration options
4. **Monitoring**: Add logging to track when duplicates are created vs. removed


## Additional Investigation: Centrality and Persistence

### Centrality calculation and storage
- Centrality modules inspected:
  - graphiti_core/utils/maintenance/centrality_operations.py
  - graphiti_core/utils/maintenance/atomic_centrality_storage.py
  - server/graph_service/routers/centrality.py (proxy to Rust service)
  - graphiti-centrality-rs/src/algorithms.rs (Rust implementation)
- Storage writes use MATCH + SET only; they do not CREATE nodes/edges:
  - Atomic storage writes:
    - MATCH (n {uuid: item.uuid}) SET n.centrality_* = ...
  - No code path in centrality creates nodes or relationships.
- Data selection:
  - Python degree centrality query uses MATCH (n) OPTIONAL MATCH (n)-[e]-() and returns counts. It does not filter out IS_DUPLICATE_OF edges or merged tombstones.
  - Rust service calls FalkorDB native algorithms (algo.pageRank, algo.betweenness) on the entire graph; those include all relationships by default, likely including IS_DUPLICATE_OF unless pre-filtered (no evidence of filtering).
  - Group filtering is supported via optional group_id parameter, but when omitted, all nodes are included.
- Implications:
  - Centrality does not cause duplicate creation, but it can inflate metrics by counting audit edges (IS_DUPLICATE_OF) and duplicate nodes, making duplicates “look important.”
  - Fallback in merge_node_into recalculates canonical centrality via Cypher that counts all relationships without excluding IS_DUPLICATE_OF.

### Persistence flows and constraints
- Node save queries (graphiti_core/models/nodes/node_db_queries.py):
  - ENTITY_NODE_SAVE uses MERGE (n:Entity {uuid: $entity_data.uuid}) then SET n = $entity_data.
  - There is no MERGE by (name, group_id), so identical name+group_id with new UUID creates additional nodes (by design).
- Edge save queries (graphiti_core/models/edges/edge_db_queries.py):
  - ENTITY_EDGE_SAVE uses MERGE on edge UUID; edges are unique by UUID only.
- Bulk persistence (graphiti_core/utils/bulk_utils.py):
  - add_nodes_and_edges_bulk_tx forwards to get_entity_node_save_bulk_query which uses MERGE by uuid only.
  - build_duplicate_of_edges contributes both the IS_DUPLICATE_OF edges and ensures duplicate nodes are part of nodes-to-save.
- Indices/constraints (graphiti_core/graph_queries.py):
  - Indices exist on uuid, group_id, name, etc., but no uniqueness constraints enforcing name+group_id uniqueness.

### Worker ingestion and centrality triggers
- graphiti_core/ingestion/worker.py:
  - _process_entity saves nodes using provided uuid; if upstream provides varying uuids for the same (name, group_id), duplicates are created before any dedupe pipeline runs.
  - After creating nodes and edges, the worker schedules centrality updates; these include duplicates and audit edges.

### Conclusions regarding centrality
- Centrality pipelines (Python and Rust) do not create duplicates, but they:
  - Include duplicates and IS_DUPLICATE_OF edges in calculations by default.
  - Update centrality metrics on duplicate nodes as well, unless filtered elsewhere.
- Recommendation: Filter out merged nodes and IS_DUPLICATE_OF edges in centrality calculations and degree fallback queries, or compute metrics on a view of the canonical graph only.

### Additional assurance checks from source
- merge_node_into transfers edges and then explicitly deletes all non-audit edges from the duplicate, leaving only IS_DUPLICATE_OF and tombstone props. No deletion occurs by default.
- maintenance_dedupe_entities.py includes deletion logic post-merge in _delete_duplicate_nodes and is invoked by merge_duplicate_group, but this path is separate from the main ingestion pipeline.
- No code path in centrality or persistence automatically removes duplicates after merges.

### Likely sources of persistent duplicates
1. Upstream ingestion supplies new UUIDs for the same logical entity; persistence MERGE-by-uuid happily creates them.
2. Dedup flow marks duplicates but either:
   - a) Does not run execute_merge_operations consistently, or
   - b) Runs merges but retains tombstones (no deletion), and downstream queries do not exclude is_merged.
3. Centrality includes duplicates and IS_DUPLICATE_OF edges, amplifying their visibility/importance but not creating them.

### Actionable verification (no DB access required)
- Confirm query filters in read paths (APIs/UI/analytics) exclude is_merged=true.
- Confirm that ingestion provides stable UUIDs per logical entity; otherwise, implement a pre-save lookup by (group_id, normalized name) to reuse uuid or trigger immediate merge+delete.
- Consider adding configuration to centrality routines to exclude IS_DUPLICATE_OF and merged nodes.


### Important finding: Mixed representation of IS_DUPLICATE_OF edges
- There are two different representations in the codebase:
  1) As a RELATES_TO edge with name property 'IS_DUPLICATE_OF' (EntityEdge path)
  2) As a relationship type IS_DUPLICATE_OF (audit trail in merge)
- Evidence:
  - run_deduplication checks for typed relationship, so it may miss existing property-based edges and create duplicates repeatedly:
    <augment_code_snippet path="run_deduplication.py" mode="EXCERPT">
    ````python
    existing_check = await graphiti.driver.execute_query(
        """
        MATCH (n1:Entity {uuid: $uuid1})-[r:IS_DUPLICATE_OF]-(n2:Entity {uuid: $uuid2})
        RETURN r
        """,
    )
    ````
    </augment_code_snippet>
  - Duplicate edges are created via EntityEdge with name 'IS_DUPLICATE_OF' (saved as RELATES_TO):
    <augment_code_snippet path="graphiti_core/utils/maintenance/edge_operations.py" mode="EXCERPT">
    ````python
    EntityEdge(
        source_node_uuid=source_node.uuid,
        target_node_uuid=target_node.uuid,
        name='IS_DUPLICATE_OF',
    )
    ````
    </augment_code_snippet>
  - The audit trail in merge uses a typed relationship:
    <augment_code_snippet path="graphiti_core/utils/maintenance/node_operations.py" mode="EXCERPT">
    ````python
    MERGE (duplicate)-[r:IS_DUPLICATE_OF]->(canonical)
    SET r.merged_at = $merged_at
    ````
    </augment_code_snippet>
  - Other utilities search for the property-based encoding (RELATES_TO with name='IS_DUPLICATE_OF'):
    <augment_code_snippet path="graphiti_core/utils/maintenance/edge_operations.py" mode="EXCERPT">
    ````python
    MATCH (n:Entity)-[r:RELATES_TO {name: 'IS_DUPLICATE_OF'}]->(m:Entity)
    ````
    </augment_code_snippet>
- Impact:
  - Inconsistent checks mean maintenance may keep creating additional 'duplicate' edges on each run.
  - Centrality calculations include both the RELATES_TO(name='IS_DUPLICATE_OF') edges and the typed IS_DUPLICATE_OF edges, double-counting links.
  - Queries that expect one encoding may miss the other when filtering/validation.
- Recommendation: Standardize on one representation (prefer typed IS_DUPLICATE_OF for audit, and do not create RELATES_TO edges with that name), and update all queries accordingly. Also exclude IS_DUPLICATE_OF (both encodings) from centrality computations.

### Centrality-specific query details to review
- Degree centrality (Python fallback) counts all relationships indiscriminately:
  <augment_code_snippet path="graphiti_core/utils/maintenance/node_operations.py" mode="EXCERPT">
  ````python
  OPTIONAL MATCH (n)-[r]-(m)
  SET n.degree_centrality = CASE WHEN degree > 0 THEN toFloat(degree) / 10.0 ELSE 0.0 END
  ````
  </augment_code_snippet>
- Degree/PageRank (Python path) and Rust service do not filter IS_DUPLICATE_OF by default. Consider adding filters such as:
  - WHERE (n.is_merged IS NULL OR n.is_merged = false)
  - AND type(r) <> 'IS_DUPLICATE_OF' AND coalesce(r.name, '') <> 'IS_DUPLICATE_OF'


### Worker vs Graphiti orchestration discrepancy
- Graphiti.add_episode flow resolves and dedupes before persistence (resolve_extracted_nodes) and then builds duplicate edges and executes merges.
- Worker ingestion path (graphiti_core/ingestion/worker.py) calls save_entity_node directly, which merges by uuid only and bypasses pre-resolution by name/group_id. If upstream uuids are unstable, this path will create new Entity nodes for the same logical entity, relying on later maintenance to dedupe.
- This discrepancy increases duplicate creation risk during high-volume ingestion.


## Where duplicate nodes are created (by source code path)

The following code paths persist Entity nodes without pre-checking by (name, group_id). They MERGE by uuid only, so any new uuid for the same logical entity creates a new node.

1) Worker ingestion path creates nodes directly
- File: graphiti_core/ingestion/worker.py
  <augment_code_snippet path="graphiti_core/ingestion/worker.py" mode="EXCERPT">
  ````python
  node = await self.graphiti.save_entity_node(
      uuid=payload.get('uuid'),
      group_id=task.group_id,
      name=payload.get('name'),
      summary=payload.get('summary')
  )
  ````
  </augment_code_snippet>

- File: server/graph_service/zep_graphiti.py
  <augment_code_snippet path="server/graph_service/zep_graphiti.py" mode="EXCERPT">
  ````python
  async def save_entity_node(self, name: str, uuid: str, group_id: str, summary: str = '') -> EntityNode:
      new_node = EntityNode(name=name, uuid=uuid, group_id=group_id, summary=summary)
      await new_node.generate_name_embedding(self.embedder)
      await new_node.save(self.driver)
  ````
  </augment_code_snippet>

- File: worker/zep_graphiti.py
  <augment_code_snippet path="worker/zep_graphiti.py" mode="EXCERPT">
  ````python
  class ZepGraphiti(Graphiti):
      async def save_entity_node(self, name: str, uuid: str, group_id: str, summary: str = '') -> EntityNode:
          # similar: constructs EntityNode and saves by uuid
  ````
  </augment_code_snippet>

2) Persistence merges by uuid only (not by name/group)
- File: graphiti_core/models/nodes/node_db_queries.py
  <augment_code_snippet path="graphiti_core/models/nodes/node_db_queries.py" mode="EXCERPT">
  ````python
  ENTITY_NODE_SAVE = """
      MERGE (n:Entity {uuid: $entity_data.uuid})
      SET n = $entity_data
      SET n.name_embedding = vecf32($entity_data.name_embedding)
  """
  ````
  </augment_code_snippet>

- Bulk path: graphiti_core/graph_queries.py
  <augment_code_snippet path="graphiti_core/graph_queries.py" mode="EXCERPT">
  ````python
  def get_entity_node_save_bulk_query(...):
      return ENTITY_NODE_SAVE_BULK  # MERGE (n:Entity {uuid: node.uuid})
  ````
  </augment_code_snippet>

3) Orchestrated pipeline vs. worker path
- Graphiti.add_episode resolves duplicates BEFORE saving (by exact name and via LLM), but the worker path bypasses this and writes immediately.
  <augment_code_snippet path="graphiti_core/utils/maintenance/node_operations.py" mode="EXCERPT">
  ````python
  exact_query = """
  MATCH (n:Entity)
  WHERE n.name = $name AND n.group_id = $group_id
  RETURN n
  ORDER BY n.created_at
  LIMIT 1
  """
  ````
  </augment_code_snippet>

Summary: Duplicate nodes are created when ingestion supplies new UUIDs for the same (name, group_id) and uses the worker path, which saves by uuid without pre-deduplication. There is no uniqueness constraint on (name, group_id), so the DB accepts these as distinct entities until later dedup/merge.
