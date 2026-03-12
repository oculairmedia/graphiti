# Consolidation System ("Graph Sleep")

> **Keywords**: `consolidation`, `prune`, `merge`, `cleanup`, `nightly`, `dedup`

## Overview

The consolidation system runs nightly to improve graph quality — like biological memory consolidation during sleep.

```
┌─────────────────────────────────────────────────────────────┐
│                    Nightly Schedule                          │
│                   (3 AM UTC Daily)                           │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                 GraphConsolidationWorkflow                   │
│                                                              │
│  Phase 1: PRUNE                                             │
│  Phase 2: MERGE                                             │
│  Phase 3: ENRICH                                            │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              ConsolidationReport (graphiti_prompts)          │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: PRUNE

Removes noise and outdated data.

### 1.1 Orphaned Entities

Entities with zero edges are removed:

```cypher
MATCH (e:Entity)
WHERE NOT (e)-[:RELATES_TO]-() 
  AND NOT (:Episodic)-[:MENTIONS]->(e)
DELETE e
```

### 1.2 Junk Entities

Generic names with minimal connections are pruned:

```python
JUNK_NAMES = {
    "medium", "high", "low", "priority", 
    "important", "urgent", "today", "yesterday"
}

# Prune if: name in JUNK_NAMES AND edges <= 2
```

### 1.3 Old Episodic Nodes

Episodic nodes older than retention period (default 90 days) are removed:

```cypher
MATCH (e:Episodic)
WHERE e.created_at < $cutoff_date
DETACH DELETE e
```

Note: MENTIONS edges are detached, but entities and RELATES_TO edges remain.

### 1.4 Invalidated Edges

RELATES_TO edges with `t_invalid_at` set (contradicted facts) are removed:

```cypher
MATCH ()-[r:RELATES_TO]->()
WHERE r.t_invalid_at IS NOT NULL
DELETE r
```

---

## Phase 2: MERGE

Deduplicates entities to reduce redundancy.

### 2.1 IS_DUPLICATE_OF Edges

Pre-existing duplicate relationships are resolved:

```cypher
MATCH (duplicate:Entity)-[d:IS_DUPLICATE_OF]->(canonical:Entity)
// Merge duplicate into canonical
// Delete IS_DUPLICATE_OF edge
```

### 2.2 Same-Name Entities

Case-insensitive name grouping with canonical selection:

```python
def select_canonical(entities: list[Entity]) -> Entity:
    """
    Selection priority:
    1. Most edges (most connected)
    2. Longest summary (most information)
    3. Earliest created_at (first occurrence)
    """
    return sorted(entities, key=lambda e: (
        -edge_count(e),
        -len(e.summary or ""),
        e.created_at
    ))[0]
```

**Merge Process**:
1. Group entities by case-insensitive name
2. Select canonical for each group
3. Transfer all edges to canonical
4. Delete duplicates

### Merge Mechanics

```python
# graphiti_core/node_operations.py

async def merge_node_into(duplicate_uuid: str, canonical_uuid: str):
    """
    Transfers all edges from duplicate to canonical.
    
    1. Update incoming edges: target_uuid = canonical_uuid
    2. Update outgoing edges: source_uuid = canonical_uuid
    3. Merge edge properties (combine facts, episodes lists)
    4. Delete duplicate entity
    """
```

---

## Phase 3: ENRICH

Improves data quality and consistency.

### 3.1 Regenerate Entity Summaries

Entities with NULL/empty summaries get regenerated:

```python
# Gather connected RELATES_TO edge facts
facts = get_entity_facts(entity_uuid)

# Generate summary via LLM
summary = await llm.generate(f"Summarize entity from facts: {facts}")

# Update entity
SET entity.summary = summary
```

### 3.2 Backfill Entity Embeddings

Safety net for entities with NULL `name_embedding`:

```cypher
MATCH (e:Entity)
WHERE e.name_embedding IS NULL
SET e.name_embedding = vecf32($generated_embedding)
```

### 3.3 Semantic Entity Dedup

Uses HNSW vector index for similarity-based dedup:

```python
# For each entity without a match:
# 1. Query HNSW index for similar embeddings
similar = await falkordb.query("""
    CALL db.idx.vector.queryNodes('Entity', 'name_embedding', $embedding, 10)
    YIELD node, score
    WHERE score > 0.92
    RETURN node
""")

# 2. Select canonical (same priority as name merge)
# 3. Merge via merge_node_into()
```

**Similarity Threshold**: 0.92 (conservative, can tune)

### 3.4 Recalculate Centrality

Full PageRank, degree, and betweenness recalculation:

```python
from graphiti_core.utils import calculate_all_centralities

await calculate_all_centralities(driver, store_results=True)
```

---

## Consolidation Reports

After each run, a report is stored in `graphiti_prompts`:

```cypher
(:ConsolidationReport {
  run_id: STRING,
  started_at: DATETIME,
  completed_at: DATETIME,
  
  # Phase 1: Prune counts
  orphaned_pruned: INT,
  junk_pruned: INT,
  episodic_pruned: INT,
  invalidated_edges_pruned: INT,
  
  # Phase 2: Merge counts
  duplicate_of_merged: INT,
  same_name_merged: INT,
  edges_transferred: INT,
  
  # Phase 3: Enrich counts
  summaries_regenerated: INT,
  embeddings_backfilled: INT,
  semantic_merged: INT,
  centrality_recalculated: BOOLEAN,
  
  # Health metrics
  pre_node_count: INT,
  post_node_count: INT,
  pre_edge_count: INT,
  post_edge_count: INT,
  
  # Errors
  failed_merges: INT,
  errors: LIST
})
```

### Query Reports

```bash
redis-cli -p 6379 GRAPH.QUERY graphiti_prompts \
  "MATCH (r:ConsolidationReport) 
   RETURN r.run_id, r.started_at, r.total_pruned, r.total_merged 
   ORDER BY r.started_at DESC 
   LIMIT 10" --csv
```

---

## Scheduling

### Manual Run

```bash
# One-off run
python3 scripts/schedule_consolidation.py --once

# Custom settings
python3 scripts/schedule_consolidation.py --once \
  --retention-days 60 \
  --batch-size 200
```

### Scheduled Run

```bash
# Create nightly schedule (3 AM UTC)
python3 scripts/schedule_consolidation.py --schedule

# Custom cron
python3 scripts/schedule_consolidation.py --schedule --cron "0 5 * * *"

# Delete schedule
python3 scripts/schedule_consolidation.py --delete-schedule
```

---

## Configuration

```bash
# .env
TEMPORAL_CONSOLIDATION_TASK_QUEUE=graphiti-consolidation
TEMPORAL_CONSOLIDATION_MAX_ACTIVITIES=2
```

---

## First Run Results (Feb 2026)

| Metric | Value |
|--------|-------|
| Entities before | 12,715 |
| Entities after | 11,924 |
| Entities merged | 721 |
| Edges transferred | 2,669 |

---

## Troubleshooting

### Issue: Merge failures ("canonical not found")

**Cause**: Canonical was deleted before merge
**Fix**: Logged and retried on next run (self-healing)

### Issue: High memory usage during merge

**Cause**: Loading too many entities at once
**Fix**: Reduce `--batch-size`

### Issue: Consolidation stuck

**Check**: Temporal UI for workflow status
```bash
open http://192.168.50.90:8080
# Search: consolidation-*
```

---

## Files to Know

| File | Purpose |
|------|---------|
| `worker/temporal_consolidation_worker.py` | Temporal worker |
| `graphiti_core/temporal/consolidation_workflow.py` | Workflow definition |
| `scripts/schedule_consolidation.py` | Scheduler script |

---

## See Also

- [../how-to/consolidation.md](../how-to/consolidation.md) - Usage guide
- [architecture.md](architecture.md) - System overview
- [ingestion-pipeline.md](ingestion-pipeline.md) - Data flow
