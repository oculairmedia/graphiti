# Graphiti Ingestion System Analysis

## Overview
This document analyzes the structure of the Graphiti ingestion system and identifies the root cause of unique constraint violations on MENTIONS edges when deterministic UUID generation is enabled.

## System Architecture

### 1. Ingestion Flow
```
Message → Worker Queue → Episode Processing → Entity/Edge Extraction → Database Storage
```

#### Key Components:
- **Ingestion Worker** (`graphiti_core/ingestion/worker.py`): Processes queued tasks
- **Episode Processing** (`graphiti_core/graphiti.py`): Main `add_episode` method
- **Edge Creation** (`graphiti_core/utils/maintenance/edge_operations.py`): Builds episodic edges
- **Database Persistence** (`graphiti_core/models/edges/edge_db_queries.py`): Saves edges to Neo4j/FalkorDB

### 2. Edge Types

#### EpisodicEdge
- **Purpose**: Links episodes to entities they mention
- **Database Relationship**: `MENTIONS`
- **Fields**: `uuid`, `group_id`, `source_node_uuid`, `target_node_uuid`, `created_at`
- **Critical Issue**: **NO `name` field**

#### EntityEdge  
- **Purpose**: Represents relationships between entities
- **Database Relationship**: `RELATES_TO`
- **Fields**: Includes `name` field for relationship type (e.g., "works_at", "lives_in")

### 3. UUID Generation System

#### Current Implementation (`graphiti_core/edges.py` lines 77-97):
```python
@model_validator(mode='before')
@classmethod
def set_uuid(cls, values: dict[str, Any]) -> dict[str, Any]:
    if values.get('uuid'):
        return values
        
    use_deterministic_uuids = os.getenv('USE_DETERMINISTIC_UUIDS', 'false').lower() == 'true'
    
    if use_deterministic_uuids:
        source_uuid = values.get('source_node_uuid')
        target_uuid = values.get('target_node_uuid')
        group_id = values.get('group_id')
        
        # PROBLEM: This assumes ALL edges have a name field!
        edge_name = values.get('name', 'EDGE')  # EpisodicEdges get 'EDGE'
        
        if source_uuid and target_uuid and group_id:
            values['uuid'] = generate_deterministic_edge_uuid(source_uuid, target_uuid, edge_name, group_id)
            return values
    
    values['uuid'] = str(uuid4())
    return values
```

#### UUID Generation Function (`graphiti_core/utils/uuid_utils.py`):
```python
def generate_deterministic_edge_uuid(source_uuid: str, target_uuid: str, name: str, group_id: str) -> str:
    group_namespace = uuid5(NAMESPACE_DNS, f"graphiti.edge.{group_id}")
    edge_key = f"{source_uuid}|{target_uuid}|{name}"  # Problem: name is 'EDGE' for all EpisodicEdges
    edge_uuid = uuid5(group_namespace, edge_key)
    return str(edge_uuid)
```

## Root Cause Analysis

### The Core Problem
**EpisodicEdge class has NO `name` field**, but the deterministic UUID generation assumes all edges have one.

### Consequence Chain:
1. **EpisodicEdge Creation**: Multiple episodic edges created during episode processing
2. **UUID Generation**: All EpisodicEdges get fallback name `'EDGE'`
3. **Identical Parameters**: Same episode mentioning same entity multiple times creates:
   - Same `source_node_uuid` (episode UUID)
   - Same `target_node_uuid` (entity UUID)  
   - Same `group_id`
   - Same `name` ('EDGE' fallback)
4. **UUID Collision**: Identical UUIDs generated for different edge instances
5. **Database Constraint Violation**: Unique constraint on MENTIONS edge UUID fails

### Database Constraints (`graphiti_core/utils/constraints.py`):
```python
# FalkorDB
'GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE RELATIONSHIP MENTIONS PROPERTIES 1 uuid'

# Neo4j  
'CREATE CONSTRAINT mentions_uuid_unique IF NOT EXISTS FOR ()-[e:MENTIONS]-() REQUIRE e.uuid IS UNIQUE'
```

### Database vs Code Mismatch:
- **Database Query**: Uses `MENTIONS` relationship type
- **UUID Generation**: Uses generic `'EDGE'` name for EpisodicEdges
- **Result**: Semantic mismatch between database schema and UUID generation logic

## Why Other Components Work

### EntityNodes ✅
- Always have unique `name` field
- Deterministic UUIDs based on `(name, group_id)` are naturally unique

### EntityEdges ✅  
- Have `name` field containing relationship type
- Different relationship types create different UUIDs even between same nodes

### EpisodicEdges ❌
- NO `name` field → all get same fallback `'EDGE'`
- Same episode + same entity = identical UUID → constraint violation

## Evidence from Logs
```
redis.exceptions.ResponseError: unique constraint violation, on edge of relationship-type MENTIONS
```

This confirms the issue is specifically with MENTIONS edges (EpisodicEdges) and unique constraint violations.

## Impact Assessment

### Current State:
- ✅ EntityNode creation works correctly
- ✅ EntityEdge creation works correctly  
- ❌ EpisodicEdge creation fails with constraint violations
- ❌ Episode ingestion partially fails, causing retries and system instability

### Affected Workflows:
- Message ingestion via worker queue
- Episode processing in `add_episode`
- Any workflow creating episodic relationships

## Detailed Code Flow Analysis

### 1. Episode Processing (`graphiti_core/graphiti.py` line 679-682):
```python
# Create Episodic Edges
episodic_edges: list[EpisodicEdge] = []
for episode_uuid, nodes in nodes_by_episode.items():
    episodic_edges.extend(build_episodic_edges(nodes, episode_uuid, now))
```

### 2. Edge Building (`graphiti_core/utils/maintenance/edge_operations.py` line 115-123):
```python
def build_episodic_edges(
    entity_nodes: list[EntityNode],
    episode_uuid: str,
    created_at: datetime,
) -> list[EpisodicEdge]:
    episodic_edges: list[EpisodicEdge] = [
        EpisodicEdge(
            source_node_uuid=episode_uuid,
            target_node_uuid=node.uuid,
            created_at=created_at,
            group_id=node.group_id,  # NO name field set!
        )
        for node in entity_nodes
    ]
```

### 3. Database Persistence (`graphiti_core/models/edges/edge_db_queries.py` line 17-22):
```python
EPISODIC_EDGE_SAVE = """
        MATCH (episode:Episodic {uuid: $episode_uuid}) 
        MATCH (node:Entity {uuid: $entity_uuid}) 
        MERGE (episode)-[r:MENTIONS {uuid: $uuid}]->(node)
        SET r = {uuid: $uuid, group_id: $group_id, created_at: $created_at}
        RETURN r.uuid AS uuid"""
```

## Worker vs Direct Processing

### Worker Path (Current Issue):
1. Messages queued via `server/graph_service/routers/ingest.py`
2. Worker processes via `graphiti_core/ingestion/worker.py`
3. Calls `graphiti.add_episode()` without pre-deduplication
4. Creates EpisodicEdges with identical UUIDs → constraint violation

### Direct Processing Path:
1. Direct calls to `graphiti.add_episode()`
2. Includes entity resolution and deduplication
3. May still create duplicate EpisodicEdges if same episode mentions same entity multiple times

## Environment Configuration

### Required Setting:
```bash
USE_DETERMINISTIC_UUIDS=true
```

### Database Constraints:
- Unique constraints on edge UUIDs are enforced
- Both Neo4j and FalkorDB have similar constraint syntax
- Constraints prevent duplicate edges with same UUID

## Solutions Analysis

### Solution 1: Fix UUID Generation Logic (Recommended)
**Pros**: 
- Minimal code change
- Preserves existing architecture
- Addresses root cause directly

**Cons**: 
- Still relies on fallback logic
- Doesn't add semantic clarity

### Solution 2: Add Name Field to EpisodicEdge
**Pros**: 
- Makes schema consistent
- Adds semantic clarity
- Future-proof

**Cons**: 
- Requires database migration
- More extensive code changes
- Potential breaking changes

### Solution 3: Separate UUID Generation Strategy
**Pros**: 
- Clean separation of concerns
- Optimized for each edge type

**Cons**: 
- More complex codebase
- Duplicate logic
- Harder to maintain

## Recommended Implementation

### Immediate Fix (Solution 1):
Modify the UUID generation logic in `graphiti_core/edges.py` to detect EpisodicEdges and use 'MENTIONS' as the edge name:

```python
# Check if this is an EpisodicEdge (no name field)
if 'name' not in values:
    # For EpisodicEdges, use 'MENTIONS' as the edge type
    edge_name = 'MENTIONS'
else:
    # For EntityEdges, use the actual name
    edge_name = values.get('name', 'RELATES_TO')
```

### Testing Strategy:
1. Apply the fix
2. Clear existing problematic data or use new group_id
3. Test with multiple episodes mentioning same entities
4. Verify no constraint violations
5. Monitor edge creation in logs

### Long-term Improvements:
1. Add `name` field to EpisodicEdge class
2. Implement edge deduplication logic
3. Add comprehensive logging for edge operations
4. Consider edge normalization similar to entity names

## Technical Implementation Details

### Current EpisodicEdge Class Structure:
```python
class EpisodicEdge(Edge):
    # Inherits from Edge base class:
    # - uuid: str
    # - group_id: str
    # - source_node_uuid: str
    # - target_node_uuid: str
    # - created_at: datetime

    # NO additional fields - specifically NO name field!

    async def save(self, driver: GraphDriver):
        result = await driver.execute_query(
            EPISODIC_EDGE_SAVE,
            episode_uuid=self.source_node_uuid,
            entity_uuid=self.target_node_uuid,
            uuid=self.uuid,
            group_id=self.group_id,
            created_at=self.created_at,
        )
```

### EntityEdge Class Structure (for comparison):
```python
class EntityEdge(Edge):
    name: str = Field(description='name of the edge, relation name')  # HAS name field!
    fact: str = Field(description='fact representing the edge and nodes that it connects')
    fact_embedding: list[float] | None = Field(default=None)
    episodes: list[str] = Field(default=[])
    expired_at: datetime | None = Field(default=None)
    valid_at: datetime | None = Field(default=None)
    invalid_at: datetime | None = Field(default=None)
```

### Ingestion Worker Flow:
```python
# In graphiti_core/ingestion/worker.py line 364-373
result = await self.graphiti.add_episode(
    group_id=effective_group_id,
    name=payload.get('name'),
    episode_body=payload.get('content'),
    reference_time=timestamp,
    source=EpisodeType.message,
    source_description=payload.get('source_description')
)
```

### Edge Creation During Episode Processing:
```python
# In graphiti_core/utils/maintenance/edge_operations.py
def build_episodic_edges(
    entity_nodes: list[EntityNode],
    episode_uuid: str,
    created_at: datetime,
) -> list[EpisodicEdge]:
    episodic_edges: list[EpisodicEdge] = [
        EpisodicEdge(
            source_node_uuid=episode_uuid,      # Episode UUID
            target_node_uuid=node.uuid,         # Entity UUID
            created_at=created_at,
            group_id=node.group_id,             # Same group_id
            # NO name field set - this is the problem!
        )
        for node in entity_nodes
    ]
    return episodic_edges
```

### UUID Collision Scenario:
```
Episode A mentions Entity X and Entity Y
Episode A mentions Entity X again (in different context)

EpisodicEdge 1: episode_a_uuid|entity_x_uuid|EDGE|group_id → UUID_1
EpisodicEdge 2: episode_a_uuid|entity_x_uuid|EDGE|group_id → UUID_1 (COLLISION!)
```

### Database Constraint Enforcement:
```cypher
-- FalkorDB constraint
GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE RELATIONSHIP MENTIONS PROPERTIES 1 uuid

-- Neo4j constraint
CREATE CONSTRAINT mentions_uuid_unique IF NOT EXISTS FOR ()-[e:MENTIONS]-() REQUIRE e.uuid IS UNIQUE
```

## Specific Fix Implementation

### File: `graphiti_core/edges.py`
**Location**: Lines 77-97 (the `set_uuid` method)

**Current Code**:
```python
@model_validator(mode='before')
@classmethod
def set_uuid(cls, values: dict[str, Any]) -> dict[str, Any]:
    if values.get('uuid'):
        return values

    use_deterministic_uuids = os.getenv('USE_DETERMINISTIC_UUIDS', 'false').lower() == 'true'

    if use_deterministic_uuids:
        source_uuid = values.get('source_node_uuid')
        target_uuid = values.get('target_node_uuid')
        group_id = values.get('group_id')

        # PROBLEM LINE: All EpisodicEdges get 'EDGE'
        edge_name = values.get('name', 'EDGE')

        if source_uuid and target_uuid and group_id:
            values['uuid'] = generate_deterministic_edge_uuid(source_uuid, target_uuid, edge_name, group_id)
            return values

    values['uuid'] = str(uuid4())
    return values
```

**Fixed Code**:
```python
@model_validator(mode='before')
@classmethod
def set_uuid(cls, values: dict[str, Any]) -> dict[str, Any]:
    if values.get('uuid'):
        return values

    use_deterministic_uuids = os.getenv('USE_DETERMINISTIC_UUIDS', 'false').lower() == 'true'

    if use_deterministic_uuids:
        source_uuid = values.get('source_node_uuid')
        target_uuid = values.get('target_node_uuid')
        group_id = values.get('group_id')

        # FIX: Detect EpisodicEdge vs EntityEdge
        if 'name' not in values:
            # EpisodicEdge - use MENTIONS as edge type
            edge_name = 'MENTIONS'
        else:
            # EntityEdge - use actual name
            edge_name = values.get('name', 'RELATES_TO')

        if source_uuid and target_uuid and group_id:
            values['uuid'] = generate_deterministic_edge_uuid(source_uuid, target_uuid, edge_name, group_id)
            return values

    values['uuid'] = str(uuid4())
    return values
```

### Expected Result After Fix:
```
Episode A mentions Entity X: episode_a_uuid|entity_x_uuid|MENTIONS|group_id → UUID_1
Episode A mentions Entity Y: episode_a_uuid|entity_y_uuid|MENTIONS|group_id → UUID_2
Episode B mentions Entity X: episode_b_uuid|entity_x_uuid|MENTIONS|group_id → UUID_3

No more collisions! ✅
```

## Verification Steps

### 1. Environment Check:
```bash
echo $USE_DETERMINISTIC_UUIDS  # Should be 'true'
```

### 2. Test Scenario:
- Create episode that mentions multiple entities
- Create another episode that mentions same entities
- Verify no constraint violations in logs

### 3. Log Monitoring:
```bash
docker logs graphiti-worker-1 --tail 20 | grep -E "(constraint|MENTIONS|uuid)"
```

### 4. Database Verification:
```cypher
MATCH ()-[r:MENTIONS]->()
RETURN r.uuid, count(*) as count
ORDER BY count DESC
```

Should show no duplicate UUIDs after fix.
