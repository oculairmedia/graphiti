# Ingestion Pipeline

> **Keywords**: `ingestion`, `pipeline`, `extraction`, `resolution`, `temporal`, `workflow`

## Overview

The ingestion pipeline transforms raw text into a structured knowledge graph:

```
Text → Extract Entities → Resolve Entities → Extract Edges → Persist
```

---

## Pipeline Stages

### Stage 1: Entity Extraction

**Input**: Raw text from episode
**Output**: List of entities with names and types
**Method**: LLM (DSPy signature)

```python
# graphiti_core/extract_nodes.py

class ExtractNodes(dspy.Signature):
    """Extract entities from text."""
    
    current_message: str = dspy.InputField(desc="Text to extract from")
    entity_types: str = dspy.InputField(desc="Entity type definitions")
    extracted_entities: list[Entity] = dspy.OutputField()
```

**What happens**:
1. LLM analyzes text for entity mentions
2. Returns entities with names, types, and summaries
3. Embeddings generated for each entity name

---

### Stage 2: Node Resolution

**Input**: Extracted entities
**Output**: Deduplicated entities
**Method**: Name-based matching + optional semantic similarity

```python
# graphiti_core/node_operations.py

async def resolve_nodes(entities: list[Entity]) -> list[Entity]:
    """
    Resolve entities by name.
    
    Matching rules:
    1. Exact name match → merge
    2. Case-insensitive match → merge
    3. Semantic similarity (if enabled) → merge if > 0.92
    """
```

**Resolution Strategies**:
- **Name-based**: Default, exact/case-insensitive matching
- **Semantic**: Optional, uses embeddings for fuzzy matching

---

### Stage 3: Edge Extraction

**Input**: Text + resolved entities
**Output**: Relationships between entities
**Method**: LLM (DSPy signature)

```python
# graphiti_core/extract_edges.py

class ExtractEdges(dspy.Signature):
    """Extract relationships between entities."""
    
    current_message: str = dspy.InputField()
    entities: list[dict] = dspy.InputField()
    extracted_edges: list[Edge] = dspy.OutputField()
```

**What happens**:
1. LLM identifies relationships between entities
2. Each edge has: source, target, fact (natural language)
3. Edges link to source episode

---

### Stage 4: Persistence

**Input**: Resolved nodes + extracted edges
**Output**: Saved to FalkorDB
**Method**: Cypher queries

```cypher
# Create/merge entity
MERGE (e:Entity {uuid: $uuid})
SET e.name = $name,
    e.summary = $summary,
    e.name_embedding = vecf32($embedding)

# Create edge
CREATE (r:RELATES_TO {
  uuid: $uuid,
  fact: $fact,
  source_node_uuid: $source_uuid,
  target_node_uuid: $target_uuid,
  t_valid_at: $valid_at
})

# Link episode
CREATE (episode)-[:MENTIONS]->(entity)
```

---

## Temporal Mode

When `TEMPORAL_INGESTION_ENABLED=true`, each stage is a Temporal Activity:

```python
# worker/temporal_ingestion_worker.py

@activity.defn
async def extract_nodes(input: dict) -> list[Entity]:
    """Activity: Extract entities"""
    return await extract_entities(input)

@activity.defn
async def resolve_nodes(entities: list[Entity]) -> list[Entity]:
    """Activity: Resolve entities"""
    return await resolve_entities(entities)

@activity.defn
async def extract_edges(input: dict) -> list[Edge]:
    """Activity: Extract relationships"""
    return await extract_relationships(input)

@activity.defn
async def persist(input: dict) -> None:
    """Activity: Save to database"""
    await save_to_falkordb(input)
```

### Workflow Definition

```python
@workflow.defn
class IngestEpisodeWorkflow:
    @workflow.run
    async def run(self, input: EpisodeInput) -> EpisodeOutput:
        # Stage 1
        entities = await workflow.execute_activity(
            extract_nodes,
            input,
            start_to_close_timeout=timedelta(minutes=5)
        )
        
        # Stage 2
        resolved = await workflow.execute_activity(
            resolve_nodes,
            entities,
            start_to_close_timeout=timedelta(minutes=2)
        )
        
        # Stage 3
        edges = await workflow.execute_activity(
            extract_edges,
            {"text": input.text, "entities": resolved},
            start_to_close_timeout=timedelta(minutes=5)
        )
        
        # Stage 4
        await workflow.execute_activity(
            persist,
            {"entities": resolved, "edges": edges},
            start_to_close_timeout=timedelta(minutes=2)
        )
        
        return EpisodeOutput(uuid=input.uuid)
```

### Rate Limiting

Configure to prevent LLM API throttling:

```bash
# Reduce concurrent LLM calls
TEMPORAL_EXTRACT_MAX_CONCURRENT_ACTIVITIES=3
TEMPORAL_RESOLVE_MAX_CONCURRENT_ACTIVITIES=3
TEMPORAL_EDGE_MAX_CONCURRENT_ACTIVITIES=2

# Add delay between calls
TEMPORAL_RATE_LIMIT_POST_LLM_DELAY=2.0
```

---

## Legacy vs Temporal Mode

| Aspect | Legacy (Direct) | Temporal |
|--------|-----------------|----------|
| Retries | Manual | Automatic |
| Observability | Logs | Temporal UI |
| Rate Limiting | None | Configurable |
| Parallelism | Single process | Distributed workers |
| Recovery | Restart | Resume from failure |

---

## Error Handling

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| LLM timeout | Model overload | Increase timeout |
| Rate limit (429) | Too many requests | Reduce concurrency |
| Embedding failure | Invalid input | Check text encoding |
| DB connection | FalkorDB down | Check Docker status |

### Temporal Retries

Activities retry automatically with exponential backoff:

```python
retry_policy = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=100),
    maximum_attempts=5,
)
```

---

## Performance

### Typical Latencies

| Stage | Typical Time | Bottleneck |
|-------|--------------|------------|
| Extract entities | 2-5s | LLM |
| Resolve nodes | <1s | DB query |
| Extract edges | 2-5s | LLM |
| Persist | <1s | DB write |

**Total**: ~5-12s per episode (varies by text length)

### Optimization Tips

1. **Batch episodes**: Group small texts together
2. **Use Temporal**: Parallelize across workers
3. **Tune rate limits**: Match LLM provider limits
4. **Cache embeddings**: For repeated entities

---

## Files to Know

| File | Purpose |
|------|---------|
| `graphiti_core/graphiti.py` | Main `add_episode()` |
| `graphiti_core/extract_nodes.py` | Entity extraction |
| `graphiti_core/extract_edges.py` | Edge extraction |
| `graphiti_core/node_operations.py` | Resolution logic |
| `worker/temporal_ingestion_worker.py` | Temporal worker |

---

## See Also

- [../how-to/add-episode.md](../how-to/add-episode.md) - Usage guide
- [architecture.md](architecture.md) - System overview
- [consolidation-system.md](consolidation-system.md) - Graph cleanup
