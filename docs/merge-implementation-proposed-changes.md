# Merge Implementation: Review Findings and Proposed Changes

Back to overview: [Graph Build, Deduplication, and Merge Design](./graph-build-deduplication-and-merge.md)

This document outlines the issues identified in the current merge implementation and proposes concrete, safe changes with code snippets to address them.

## TL;DR (Summary of required changes)

1. Implement Neo4j support in `merge_node_into` (APOC-based preferred, Cypher fallback)
2. Remove all non-audit relationships incident to the duplicate after transfer
3. Wrap merge sequence in a transaction for atomicity
4. Add group/partition awareness to existence checks and set `group_id` on created edges
5. Define and apply an edge attribute merge policy when a same-type edge exists
6. Integrate merges into `add_episode_bulk` (post-persist), mirroring single-episode
7. Expand logging/telemetry; add comprehensive tests (merge semantics, partitions, providers)

---

## 1) Implement Neo4j path in `merge_node_into`

File: `graphiti_core/utils/maintenance/node_operations.py`

Current behavior transfers edges only when `driver.provider == 'falkordb'`. For Neo4j, implement an APOC-based path (preferred) and provide a Cypher fallback if APOC is unavailable.

### Option A: APOC (recommended)

```cypher
// Neo4j APOC-based merge
MATCH (c:Entity {uuid: $canonical_uuid}), (d:Entity {uuid: $duplicate_uuid})
CALL apoc.refactor.mergeNodes([c,d], {
  properties: "combine",
  mergeRels: true,
  produceSelfRel: false
}) YIELD node
RETURN node
```

- properties: "combine" merges properties; configure per policy (see Section 5)
- mergeRels: true consolidates relationships, avoiding duplicates

### Option B: Pure Cypher fallback (outline)

```cypher
// Transfer incoming edges
MATCH (s)-[r]->(d:Entity {uuid: $duplicate_uuid})
WITH s, r, d
MATCH (c:Entity {uuid: $canonical_uuid})
MERGE (s)-[r2:RELATES_TO {uuid: coalesce(r.uuid, randomUUID())}]->(c)
SET r2 += r
DELETE r;

// Transfer outgoing edges
MATCH (d:Entity {uuid: $duplicate_uuid})-[r]->(t)
WITH d, r, t
MATCH (c:Entity {uuid: $canonical_uuid})
MERGE (c)-[r2:RELATES_TO {uuid: coalesce(r.uuid, randomUUID())}]->(t)
SET r2 += r
DELETE r;
```

Notes:
- In pure Cypher, dynamic relationship types aren’t straightforward; prefer APOC for exact type preservation (`apoc.refactor.to`/`mergeNodes`).
- If we must emulate per-type, UNWIND over distinct `type(r)` and issue per-type `MERGE` queries.

### Python integration sketch

```python
if driver.provider == 'neo4j':
    try:
        await driver.execute_query("""
        MATCH (c:Entity {uuid: $canonical_uuid}), (d:Entity {uuid: $duplicate_uuid})
        CALL apoc.refactor.mergeNodes([c,d], {
          properties: 'combine', mergeRels: true, produceSelfRel: false
        }) YIELD node
        RETURN node
        """, canonical_uuid=canonical_uuid, duplicate_uuid=duplicate_uuid)
        stats['edges_transferred'] = 'unknown_apoc'  # optional estimation
    except Exception as apoc_err:
        # Fallback to per-edge transfer (UNWIND by rel type)
        # TODO: Implement safe per-type transfer; or re-raise with clear message
        raise
```

---

## 2) Remove all non-audit relationships from the duplicate after transfer

Problem: Current code excludes deletion of edges where the other endpoint is the canonical node, leaving residual edges like `(dup)-[r]->(canonical)` or `(canonical)-[r]->(dup)`.

Add a final cleanup step that removes all relationships to/from the duplicate except the audit edge:

```cypher
// Remove any remaining non-audit relationships from/to duplicate
MATCH (dup:Entity {uuid: $duplicate_uuid})-[r]-()
WHERE type(r) <> 'IS_DUPLICATE_OF'
DELETE r
```

Ensure you `MERGE` the `IS_DUPLICATE_OF` audit edge after cleanup (Section 4 below).

---

## 3) Wrap the merge sequence in a transaction

Reason: Multiple discrete writes risk partial state on failure.

Approach:
- If the driver exposes a transactional API, wrap the entire merge in a single transaction.
- Otherwise, group queries logically and ensure idempotency.

Python pseudocode:

```python
async def merge_node_into(...):
    async with driver.transaction() as tx:  # implement this helper if missing
        await tx.run(<transfer_incoming>)
        await tx.run(<transfer_outgoing>)
        await tx.run(<cleanup_non_audit>)
        await tx.run(<merge_audit_edge>)
        await tx.run(<tombstone_duplicate>)
```

If `transaction()` isn’t available, consider a single multi-part query per phase or add a small transactional helper to the driver.

---

## 4) Respect partitions (group_id) and set on created edges

- Existence checks should include `group_id` to avoid cross-partition collisions.
- Always set `group_id` on created relationships to the canonical node’s `group_id`.

Example check and create:

```cypher
// Check
MATCH (s:Entity {uuid: $source_uuid, group_id: $group_id})
MATCH (c:Entity {uuid: $canonical_uuid, group_id: $group_id})
OPTIONAL MATCH (s)-[r:RELATES_TO]->(c)
RETURN COUNT(r) as count;

// Create with group_id
MATCH (s:Entity {uuid: $source_uuid}), (c:Entity {uuid: $canonical_uuid})
CREATE (s)-[r:RELATES_TO]->(c)
SET r = $props, r.group_id = $group_id
```

Strategy: derive `$group_id` from the canonical node to ensure consistency.

---

## 5) Edge attribute merge policy

When a same-type relationship already exists between endpoints, define how to merge properties:

- episodes: union (unique, preserve order optionally)
- created_at: keep earliest; valid_at: pick min; invalid_at: pick max
- fact and fact_embedding: prefer canonical if identical; else keep the more recent or higher-confidence
- attributes map: merge keys; on conflict, prefer canonical or append arrays when applicable

Example merge in Python (before deciding to skip/create):

```python
def merge_edge_properties(existing: dict, incoming: dict) -> dict:
    out = dict(existing)
    # episodes
    out['episodes'] = sorted(set((existing.get('episodes') or []) + (incoming.get('episodes') or [])))
    # timestamps
    for k, fn in [('created_at', min), ('valid_at', min), ('invalid_at', max)]:
        if existing.get(k) and incoming.get(k):
            out[k] = fn([existing[k], incoming[k]])
        else:
            out[k] = existing.get(k) or incoming.get(k)
    # attributes map
    attrs = {**(existing.get('attributes') or {}), **(incoming.get('attributes') or {})}
    out['attributes'] = attrs
    return out
```

In Cypher, this can be approximated with `coalesce`, lists + `apoc.coll.toSet`, and conditional updates.

---

## 6) Integrate merges into `add_episode_bulk`

File: `graphiti_core/graphiti.py` (bulk method)

After collecting `node_duplicates` from bulk `resolve_extracted_nodes`, mirror single-episode merge execution:

```python
# After resolved_nodes/uuid_map/node_duplicates are aggregated
from graphiti_core.utils.maintenance.edge_operations import build_duplicate_of_edges, execute_merge_operations

# Build IS_DUPLICATE_OF edges and merge ops
duplicate_of_edges, merge_operations = build_duplicate_of_edges(episodes[0], now, node_duplicates)

# Persist nodes/edges as done today
await add_nodes_and_edges_bulk(
    self.driver, episodes, resolved_episodic_edges, final_hydrated_nodes,
    resolved_edges + invalidated_edges + duplicate_of_edges, self.embedder,
)

# Execute merges (post-persist)
if merge_operations:
    await execute_merge_operations(self.driver, merge_operations)
```

Note: Choose an appropriate `episode` for the `IS_DUPLICATE_OF` edges (e.g., any episode in the batch, or create per-episode edges if desired).

---

## 7) Logging, telemetry, and safeguards

- Log per-merge stats `{edges_transferred, conflicts_resolved, duration_ms, centrality_method}`
- Emit telemetry via `capture_event` if available
- Validate inputs: ensure `canonical_uuid != duplicate_uuid`; verify both nodes exist and label checks
- Sanitize/validate relationship types if building dynamic Cypher queries

---

## 8) Tests to implement

1. Merge semantics (FalkorDB):
   - Transfers all incoming/outgoing edges
   - Removes all non-audit edges from duplicate
   - Leaves only `IS_DUPLICATE_OF` between duplicate→canonical
   - Properties merged per policy (episodes union, timestamps min/max)

2. Merge semantics (Neo4j):
   - APOC path: verify relationships consolidated and properties combined
   - Fallback path (if implemented): equivalence to FalkorDB behavior

3. Partitions:
   - No cross-group conflation; `group_id` set on created edges matches canonical’s

4. Idempotency:
   - Re-running merge on the same pair is a no-op and does not duplicate edges

5. Pipeline integration:
   - Single episode and bulk: after pipeline completes, canonical has all edges; duplicate is tombstoned with only `IS_DUPLICATE_OF`

6. Centrality recalculation:
   - Degree increases appropriately; service fallback path covered

---

## Implementation checklist

- [ ] Neo4j merge path (APOC + fallback or clear error)
- [ ] Final cleanup of non-audit relationships on duplicate
- [ ] Transactional wrapper for merge sequence
- [ ] Partition-aware checks and group_id propagation
- [ ] Edge attribute merge policy (code + docs)
- [ ] Bulk pipeline merge integration
- [ ] Tests and CI coverage

Once these changes are in, we’ll have robust, provider-aware merging that preserves connectivity and metrics, eliminates dangling relationships, and scales across both single and bulk ingestion paths.

