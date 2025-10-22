# Constraint Violation Analysis: Missing UUID on RELATES_TO Edges

## Error
```
mandatory constraint violation: edge with relationship-type RELATES_TO missing property uuid
```

## Root Cause

### Location
**File**: `/opt/stacks/graphiti/graphiti_core/utils/maintenance/node_operations.py`  
**Function**: `merge_node_into()`  
**Section**: Step 3 - Maintain audit trail (around line 460-475)

### Problem Code
```python
# Step 3: Maintain audit trail if requested
if maintain_audit_trail:
    audit_query = """
    MATCH (duplicate:Entity {uuid: $duplicate_uuid})
    MATCH (canonical:Entity {uuid: $canonical_uuid})
    MERGE (duplicate)-[r:IS_DUPLICATE_OF]->(canonical)
    SET r.merged_at = $merged_at
    RETURN r
    """
```

### Why This Fails

1. **FalkorDB Mandatory Constraints** (from `graphiti_core/utils/constraints.py`):
   ```python
   'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY RELATIONSHIP RELATES_TO PROPERTIES 1 uuid',
   'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY RELATIONSHIP RELATES_TO PROPERTIES 1 group_id',
   ```

2. **IS_DUPLICATE_OF uses RELATES_TO relationship type** with `name='IS_DUPLICATE_OF'`

3. **MERGE creates edge without required properties** - The `uuid` and `group_id` must be present **at creation time**, not added via `SET` later

4. **Episodes still complete** - Error is caught and logged but doesn't fail the entire transaction

## Recommended Fix

### Option 1: Quick Fix - Add Required Properties to MERGE

```python
# Step 3: Maintain audit trail if requested
if maintain_audit_trail:
    from uuid import uuid4
    
    audit_uuid = str(uuid4())
    audit_query = """
    MATCH (duplicate:Entity {uuid: $duplicate_uuid})
    MATCH (canonical:Entity {uuid: $canonical_uuid})
    MERGE (duplicate)-[r:IS_DUPLICATE_OF {uuid: $audit_uuid, group_id: $group_id}]->(canonical)
    ON CREATE SET 
        r.merged_at = $merged_at,
        r.name = 'IS_DUPLICATE_OF'
    ON MATCH SET
        r.merged_at = $merged_at
    RETURN r
    """
    await driver.execute_query(
        audit_query,
        duplicate_uuid=duplicate_uuid,
        canonical_uuid=canonical_uuid,
        audit_uuid=audit_uuid,
        group_id=canonical_group_id,
        merged_at=utc_now()
    )
```

### Option 2: Robust Fix - Use EntityEdge Class

```python
# Step 3: Maintain audit trail if requested
if maintain_audit_trail:
    from graphiti_core.edges import EntityEdge
    
    # Check if edge already exists
    check_query = """
    MATCH (duplicate:Entity {uuid: $duplicate_uuid})-[r:RELATES_TO {name: 'IS_DUPLICATE_OF'}]->(canonical:Entity {uuid: $canonical_uuid})
    RETURN r.uuid as uuid
    """
    existing, _, _ = await driver.execute_query(
        check_query,
        duplicate_uuid=duplicate_uuid,
        canonical_uuid=canonical_uuid
    )
    
    if not existing:
        # Get node names for fact description
        duplicate_node_query = """
        MATCH (n:Entity {uuid: $uuid})
        RETURN n.name as name, n.group_id as group_id
        """
        dup_result, _, _ = await driver.execute_query(
            duplicate_node_query,
            uuid=duplicate_uuid
        )
        can_result, _, _ = await driver.execute_query(
            duplicate_node_query,
            uuid=canonical_uuid
        )
        
        if dup_result and can_result:
            duplicate_name = dup_result[0]['name']
            canonical_name = can_result[0]['name']
            
            audit_edge = EntityEdge(
                source_node_uuid=duplicate_uuid,
                target_node_uuid=canonical_uuid,
                name='IS_DUPLICATE_OF',
                group_id=canonical_group_id,
                fact=f'{duplicate_name} is a duplicate of {canonical_name}',
                episodes=[],
                created_at=utc_now(),
                valid_at=utc_now(),
            )
            await audit_edge.save(driver)
```

## Impact

- **Current**: Error logged but episodes complete successfully
- **After Fix**: No errors, proper audit trail with all required properties
- **Priority**: Medium (non-critical, but creates noise in logs)

## Related Files

- `/opt/stacks/graphiti/graphiti_core/utils/maintenance/node_operations.py` - Main fix location
- `/opt/stacks/graphiti/graphiti_core/utils/maintenance/edge_operations.py` - Reference for correct pattern
- `/opt/stacks/graphiti/graphiti_core/utils/constraints.py` - Constraint definitions

## Testing After Fix

```bash
# Monitor for constraint violations
docker compose logs -f graphiti-worker | grep "constraint violation"

# Should see: No errors after fix is deployed
```

---
**Analysis Date**: October 7, 2025  
**Status**: Root cause identified, fix ready to implement
