# FalkorDB Constraints Documentation

## Overview

This document outlines all database constraints enforced in the Graphiti FalkorDB implementation. These constraints ensure data integrity and prevent invalid data from being stored in the graph database.

## Current Error Analysis

**Error Pattern:**
```
❌ Error exporting to FalkorDB: mandatory constraint violation: node with label Entity missing property uuid
```

**Root Cause:** The cocodindex/HulyGraphiti system is attempting to create Entity nodes without providing the mandatory `uuid` property, violating FalkorDB's mandatory constraints.

## Mandatory Constraints (Existence Requirements)

These constraints ensure that required properties are always present when creating nodes or relationships.

### Node Constraints

#### Entity Nodes
- **uuid** (MANDATORY) - Unique identifier for the entity
- **name** (MANDATORY) - Entity name/label  
- **group_id** (MANDATORY) - Group/project identifier for data isolation

#### Episodic Nodes
- **uuid** (MANDATORY) - Unique identifier for the episode
- **group_id** (MANDATORY) - Group/project identifier for data isolation

#### Community Nodes
- **uuid** (MANDATORY) - Unique identifier for the community

### Relationship Constraints

#### RELATES_TO Relationships
- **uuid** (MANDATORY) - Unique identifier for the relationship
- **group_id** (MANDATORY) - Group/project identifier for data isolation

#### MENTIONS Relationships  
- **uuid** (MANDATORY) - Unique identifier for the relationship
- **group_id** (MANDATORY) - Group/project identifier for data isolation

#### HAS_MEMBER Relationships
- **uuid** (MANDATORY) - Unique identifier for the relationship

## Unique Constraints (Uniqueness Requirements)

These constraints prevent duplicate data from being created.

### Node Uniqueness

#### Entity Nodes
- **uuid** (UNIQUE) - No two entities can have the same UUID
- **name + group_id** (UNIQUE) - No two entities can have the same name within the same group

#### Episodic Nodes
- **uuid** (UNIQUE) - No two episodes can have the same UUID

#### Community Nodes
- **uuid** (UNIQUE) - No two communities can have the same UUID

### Relationship Uniqueness

#### HAS_MEMBER Relationships
- **uuid** (UNIQUE) - No two membership relationships can have the same UUID

**Note:** RELATES_TO and MENTIONS relationship UUID uniqueness constraints are intentionally disabled because episodes can legitimately relate to or mention the same entities multiple times.

## Required Fixes for Cocodindex

To resolve the constraint violations, the cocodindex system must:

### 1. UUID Generation
```python
import uuid

# Always generate UUID before creating Entity nodes
entity_uuid = str(uuid.uuid4())
```

### 2. Mandatory Property Validation
Before creating any node or relationship, ensure all mandatory properties are present:

```python
def validate_entity_properties(entity_data):
    required_props = ['uuid', 'name', 'group_id']
    for prop in required_props:
        if prop not in entity_data or entity_data[prop] is None:
            raise ValueError(f"Missing mandatory property: {prop}")
```

### 3. Group ID Assignment
Ensure all entities have proper group_id assignment:
```python
# Example from error logs
group_id = 'huly-ldts'  # or 'huly-lmp' based on project
```

## Constraint Management

### Creating Constraints
Constraints are created using the `create_falkor_constraints.py` script:

```bash
python create_falkor_constraints.py
```

### Checking Existing Constraints
Use the debug script to verify constraint status:

```bash
python debug_falkordb_constraints.py
```

### Constraint Creation Commands
FalkorDB constraints use this syntax:
```cypher
GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY NODE Entity PROPERTIES 1 uuid
GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE NODE Entity PROPERTIES 1 uuid
```

## Debugging Procedures

### 1. Verify Constraint Existence
```cypher
CALL db.constraints()
```

### 2. Test Node Creation
```cypher
// This should FAIL if constraints are working
CREATE (e:Entity {name: 'test'})

// This should SUCCEED
CREATE (e:Entity {uuid: 'test-uuid', name: 'test', group_id: 'test-group'})
```

### 3. Check Existing Data Compliance
```cypher
// Find entities missing UUID
MATCH (e:Entity) WHERE e.uuid IS NULL RETURN count(e)

// Find entities missing group_id  
MATCH (e:Entity) WHERE e.group_id IS NULL RETURN count(e)
```

## Implementation Priority

1. **CRITICAL:** Fix UUID generation in Entity creation
2. **HIGH:** Validate all mandatory properties before database operations
3. **MEDIUM:** Implement constraint verification in CI/CD pipeline
4. **LOW:** Add constraint monitoring and alerting

## Files Involved

- `graphiti_core/utils/constraints.py` - Constraint definitions
- `create_falkor_constraints.py` - Constraint creation script
- `debug_falkordb_constraints.py` - Constraint debugging tools

## Next Steps

1. Identify the exact location in cocodindex where Entity nodes are created without UUIDs
2. Implement UUID generation and validation
3. Test constraint compliance before deploying fixes
4. Monitor constraint violations in production logs
