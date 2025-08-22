# Cross-Graph Deduplication Implementation Steps

## Problem Analysis

Cross-graph deduplication is currently not working because the deduplication logic is **restricted to the same `group_id`** in multiple places. The system only looks for duplicates within the same graph/group, preventing entities from different groups from being merged even when they represent the same real-world entity.

## Root Cause

The issue is in the `resolve_extracted_nodes` function in `graphiti_core/utils/maintenance/node_operations.py` at two critical points:

### 1. Exact Match Query (Lines 275-284)
```python
exact_query = """
MATCH (n:Entity)
WHERE n.name = $name AND n.group_id = $group_id  # ← RESTRICTS TO SAME GROUP
RETURN n
ORDER BY n.created_at
LIMIT 1
"""
```

### 2. Search Function Call (Lines 326-332)
```python
search(
    clients=clients,
    query=node.name,
    group_ids=[node.group_id],  # ← RESTRICTS TO SAME GROUP
    search_filter=SearchFilters(),
    config=NODE_HYBRID_SEARCH_RRF,
)
```

### 3. Merge Safety Check (Lines 653-657)
```python
if canonical_group_id != duplicate_group_id:
    raise ValueError(
        f'Cannot merge across partitions: canonical group_id={canonical_group_id}, '
        f'duplicate group_id={duplicate_group_id}'
    )
```

## Implementation Steps

### Step 1: Modify `resolve_extracted_nodes` Function

**File**: `graphiti_core/utils/maintenance/node_operations.py`

#### 1.1 Add Cross-Graph Parameter
**Location**: Lines 255-262

**Change**: Add a new parameter to the function signature:
```python
async def resolve_extracted_nodes(
    clients: GraphitiClients,
    extracted_nodes: list[EntityNode],
    episode: EpisodicNode | None = None,
    previous_episodes: list[EpisodicNode] | None = None,
    entity_types: dict[str, BaseModel] | None = None,
    existing_nodes_override: list[EntityNode] | None = None,
    enable_cross_graph_deduplication: bool = False,  # ← ADD THIS
) -> tuple[list[EntityNode], dict[str, str], list[tuple[EntityNode, EntityNode]]]:
```

#### 1.2 Modify Exact Match Query
**Location**: Lines 275-284

**Change**: Replace the exact match query logic with conditional logic:
```python
# Query for exact name matches
if enable_cross_graph_deduplication:
    # Cross-graph deduplication: search across all groups
    exact_query = """
    MATCH (n:Entity)
    WHERE n.name = $name
    RETURN n
    ORDER BY n.created_at
    LIMIT 1
    """
    records, _, _ = await driver.execute_query(
        exact_query, name=node.name
    )
else:
    # Standard deduplication: only within same group
    exact_query = """
    MATCH (n:Entity)
    WHERE n.name = $name AND n.group_id = $group_id
    RETURN n
    ORDER BY n.created_at
    LIMIT 1
    """
    records, _, _ = await driver.execute_query(
        exact_query, name=node.name, group_id=node.group_id
    )
```

#### 1.3 Modify Search Function Call
**Location**: Lines 326-332

**Change**: Make group_ids conditional:
```python
search_results: list[SearchResults] = await semaphore_gather(
    *[
        search(
            clients=clients,
            query=node.name,
            group_ids=None if enable_cross_graph_deduplication else [node.group_id],  # ← CHANGE THIS
            search_filter=SearchFilters(),
            config=NODE_HYBRID_SEARCH_RRF,
        )
        for node in nodes_needing_llm_resolution
    ]
)
```

### Step 2: Modify `merge_node_into` Function

**File**: `graphiti_core/utils/maintenance/node_operations.py`

#### 2.1 Add Cross-Graph Merge Parameter
**Location**: Lines 589-595

**Change**: Add parameter to function signature:
```python
async def merge_node_into(
    driver,
    canonical_uuid: str,
    duplicate_uuid: str,
    maintain_audit_trail: bool = True,
    recalculate_centrality: bool = True,
    allow_cross_graph_merge: bool = False,  # ← ADD THIS
) -> dict[str, Any]:
```

#### 2.2 Modify Cross-Graph Safety Check
**Location**: Lines 653-657

**Change**: Make the safety check conditional:
```python
duplicate_group_id = duplicate_result[0].get('group_id')

if canonical_group_id != duplicate_group_id and not allow_cross_graph_merge:
    raise ValueError(
        f'Cannot merge across partitions: canonical group_id={canonical_group_id}, '
        f'duplicate group_id={duplicate_group_id}. Set allow_cross_graph_merge=True to enable cross-graph merging.'
    )

# Log cross-graph merge if it's happening
if canonical_group_id != duplicate_group_id:
    logger.info(
        f'Performing cross-graph merge: {duplicate_uuid} (group: {duplicate_group_id}) -> '
        f'{canonical_uuid} (group: {canonical_group_id})'
    )
```

### Step 3: Update Bulk Deduplication

**File**: `graphiti_core/utils/bulk_utils.py`

#### 3.1 Modify `dedupe_nodes_bulk` Function
**Location**: Lines 254-266

**Change**: Pass the cross-graph parameter to `resolve_extracted_nodes`:
```python
bulk_node_resolutions: list[
    tuple[list[EntityNode], dict[str, str], list[tuple[EntityNode, EntityNode]]]
] = await semaphore_gather(
    *[
        resolve_extracted_nodes(
            clients,
            dedupe_tuple[0],
            episode_tuples[i][0],
            episode_tuples[i][1],
            entity_types,
            # Add cross-graph deduplication parameter
            enable_cross_graph_deduplication=True,  # ← ADD THIS
        )
        for i, dedupe_tuple in enumerate(dedupe_tuples)
    ]
)
```

### Step 4: Update Main Graphiti Class

**File**: `graphiti_core/graphiti.py`

#### 4.1 Add Configuration Parameter
**Location**: Class initialization

**Change**: Add cross-graph deduplication configuration:
```python
class Graphiti:
    def __init__(
        self,
        # ... existing parameters ...
        enable_cross_graph_deduplication: bool = False,  # ← ADD THIS
    ):
        # ... existing code ...
        self.enable_cross_graph_deduplication = enable_cross_graph_deduplication
```

#### 4.2 Update `add_episode` Method
**Location**: Around line 480

**Change**: Pass the parameter to `resolve_extracted_nodes`:
```python
resolved_nodes, uuid_map, node_duplicates = await resolve_extracted_nodes(
    self.clients, 
    extracted_nodes, 
    episode, 
    previous_episodes, 
    entity_types,
    enable_cross_graph_deduplication=self.enable_cross_graph_deduplication,  # ← ADD THIS
)
```

#### 4.3 Update Merge Operations
**Location**: Around line 525

**Change**: Pass the parameter to merge operations:
```python
if merge_operations:
    from graphiti_core.utils.maintenance.edge_operations import execute_merge_operations
    await execute_merge_operations(
        self.driver, 
        merge_operations,
        allow_cross_graph_merge=self.enable_cross_graph_deduplication,  # ← ADD THIS
    )
```

### Step 5: Update Edge Operations

**File**: `graphiti_core/utils/maintenance/edge_operations.py`

#### 5.1 Modify `execute_merge_operations` Function
**Location**: Lines 47-70

**Change**: Add and pass through the cross-graph parameter:
```python
async def execute_merge_operations(
    driver,
    merge_operations: list[tuple[str, str]],
    allow_cross_graph_merge: bool = False,  # ← ADD THIS
) -> dict[str, Any]:
    # ... existing code ...
    
    # When calling merge_node_into, pass the parameter:
    merge_stats = await merge_node_into(
        driver,
        canonical_uuid,
        duplicate_uuid,
        allow_cross_graph_merge=allow_cross_graph_merge,  # ← ADD THIS
    )
```

### Step 6: Update Maintenance Scripts

**File**: `maintenance_dedupe_entities.py`

#### 6.1 Add Cross-Graph Option
**Location**: `run_deduplication` method

**Change**: Add parameter to enable cross-graph deduplication:
```python
async def run_deduplication(
    self,
    group_id: str = None,
    dry_run: bool = False,
    batch_size: int = 10,
    max_groups: int = None,
    enable_cross_graph: bool = False,  # ← ADD THIS
) -> Dict[str, any]:
```

#### 6.2 Modify Duplicate Detection Query
**Location**: Lines 51-58

**Change**: Make group filtering conditional:
```python
query = """
MATCH (n:Entity)
WHERE ($group_id IS NULL OR n.group_id = $group_id OR $enable_cross_graph = true)
RETURN n.uuid as uuid, n.name as name, n.name_embedding as name_embedding,
       n.group_id as group_id, n.summary as summary, n.created_at as created_at,
       labels(n) as labels
ORDER BY n.name
"""

records, _, _ = await self.driver.execute_query(
    query, 
    group_id=group_id, 
    enable_cross_graph=enable_cross_graph
)
```

## Configuration and Usage

### Environment Variable
Add a new environment variable to control cross-graph deduplication:
```bash
ENABLE_CROSS_GRAPH_DEDUPLICATION=true
```

### Usage Examples

#### Enable Cross-Graph Deduplication
```python
graphiti = Graphiti(
    # ... other parameters ...
    enable_cross_graph_deduplication=True
)
```

#### Run Maintenance with Cross-Graph
```python
deduplicator = EntityDeduplicator(graphiti)
result = await deduplicator.run_deduplication(
    enable_cross_graph=True
)
```

## Important Considerations

### 1. Performance Impact
- Cross-graph searches are more expensive
- Consider adding indexes on entity names
- Monitor query performance

### 2. Data Consistency
- Ensure proper handling of different group contexts
- Consider implications of merging entities from different domains

### 3. Security and Privacy
- Verify that cross-graph merging doesn't violate data isolation requirements
- Add proper access controls if needed

### 4. Testing
- Test with entities from different groups
- Verify that existing same-group deduplication still works
- Test edge transfer across groups

### 5. Rollback Plan
- Keep the `enable_cross_graph_deduplication=False` as default
- Ensure backward compatibility
- Document how to disable if issues arise

## Validation Steps

1. **Test same-group deduplication still works**
2. **Test cross-group deduplication with simple cases**
3. **Verify edge transfers work correctly across groups**
4. **Check that audit trails are maintained**
5. **Monitor performance impact**
6. **Test with maintenance scripts**

This implementation provides a configurable approach to cross-graph deduplication while maintaining backward compatibility and safety checks.
