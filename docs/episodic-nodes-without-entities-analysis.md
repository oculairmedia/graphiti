# Analysis: Episodic Nodes Without Entities

## Problem Summary

- **86.6% of episodic nodes (1,462 out of 1,689) have no associated entities**
- Episodes contain rich content (code snippets, file paths, tool usage) but no entities are extracted
- Example: Episodes show "Claude read file: /opt/stacks/graphiti/frontend/src/components/GraphCanvas.tsx" but no entities for GraphCanvas, Cosmograph, etc.

## Root Cause

The server's `/messages` endpoint is not properly calling the full entity extraction pipeline:

1. **Current Flow (BROKEN)**:
   ```
   Claude Hook → /messages endpoint → add_messages_task → graphiti.add_episode() → Episode created
                                                                                    ↓
                                                                          NO ENTITY EXTRACTION
   ```

2. **Expected Flow**:
   ```
   Claude Hook → /messages endpoint → graphiti.add_episode() → Episode created
                                                             → Entity extraction
                                                             → Edge creation
                                                             → Knowledge graph updated
   ```

## Technical Details

### The Issue in `/server/graph_service/routers/ingest.py`

```python
async def add_messages_task(m: Message):
    await graphiti.add_episode(
        uuid=m.uuid,
        group_id=request.group_id,
        name=m.name,
        episode_body=f'{m.role or ""}({m.role_type}): {m.content}',
        reference_time=m.timestamp,
        source=EpisodeType.message,
        source_description=m.source_description,
    )
```

This IS calling `graphiti.add_episode()` which should extract entities, but the extraction might be failing due to:

1. **Missing entity_types parameter** - The core method supports custom entity types
2. **Async processing issues** - The async_worker might not be properly awaiting
3. **LLM failures** - Entity extraction LLM calls might be failing silently
4. **Configuration issues** - Entity extraction might be disabled

### Evidence from Core Code

In `graphiti_core/graphiti.py`, the `add_episode` method DOES include entity extraction:

```python
# Extract entities from episode
extracted_nodes = await extract_nodes(
    self.llm_client,
    self.embedder,
    episode,
    previous_episodes,
    entity_types,
    excluded_entity_types
)
```

## Impact

1. **Lost Knowledge**: Technical discussions about code, files, and tools aren't being captured
2. **No Graph Connections**: Episodes exist in isolation without relationships
3. **Search/Retrieval Issues**: Can't find information through entity-based queries
4. **Wasted Storage**: Storing episodes without extractable value

## Solutions

### Option 1: Debug Current Implementation
1. Add logging to trace entity extraction
2. Check if LLM calls are succeeding
3. Verify async worker is properly awaiting
4. Ensure entity extraction isn't disabled

### Option 2: Create Entity Extraction Script
1. Query all episodic nodes without entities
2. Re-run entity extraction on them
3. Create missing entities and edges
4. Similar to deduplication maintenance script

### Option 3: Fix and Re-ingest
1. Fix the root cause in the server
2. Delete current episodic nodes
3. Re-enable Claude hook to re-ingest with proper extraction

## Recommended Approach

1. **Immediate**: Create maintenance script to extract entities from existing episodes
2. **Short-term**: Debug why entity extraction is failing in the server
3. **Long-term**: Add monitoring to detect when episodes lack entities

## Sample Episodes Missing Entities

```
1. "Claude read file: /opt/stacks/graphiti/frontend/src/components/GraphCanvas.tsx"
   - Missing: GraphCanvas, Cosmograph, React components

2. "Claude modified file: /opt/stacks/graphiti/maintenance_dedupe_entities.py"
   - Missing: EntityDeduplicator, maintenance script references

3. "Claude executed command: python3 test_less_aggressive_dedupe.py"
   - Missing: Test script, deduplication references
```

These episodes contain valuable technical knowledge that should be captured as entities and relationships in the knowledge graph.