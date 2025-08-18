## FalkorDB Similarity Search: Implementation Plan

### Goal
Eliminate the “Type: mismatch: expected Null or Vectorf32 but was List” error in similarity search by:
- Normalizing all existing embeddings to Vectorf32 in FalkorDB
- Ensuring all future writes use Vectorf32
- Verifying behavior end-to-end and preventing regressions

---

## 1) Validate current state (pre‑migration)
Run these read-only queries to understand scope. Replace `graphiti_migration` with your graph name.

- Count embeddings present
```
GRAPH.QUERY graphiti_migration "MATCH (n:Entity) WHERE n.name_embedding IS NOT NULL RETURN count(n)"
GRAPH.QUERY graphiti_migration "MATCH ()-[r:RELATES_TO]->() WHERE r.fact_embedding IS NOT NULL RETURN count(r)"
```

- Quick type sniff (Vectorf32 typically prints like `<...>`, List like `[...]`)
```
GRAPH.QUERY graphiti_migration "MATCH (n:Entity) WHERE n.name_embedding IS NOT NULL RETURN toString(n.name_embedding) LIMIT 3"
GRAPH.QUERY graphiti_migration "MATCH ()-[r:RELATES_TO]->() WHERE r.fact_embedding IS NOT NULL RETURN toString(r.fact_embedding) LIMIT 3"
```

Optional sampling counts (if `substring` is available):
```
GRAPH.QUERY graphiti_migration "MATCH (n:Entity) WHERE n.name_embedding IS NOT NULL WITH toString(n.name_embedding) AS s RETURN substring(s,0,1) AS first, count(*) ORDER BY count(*) DESC"
GRAPH.QUERY graphiti_migration "MATCH ()-[r:RELATES_TO]->() WHERE r.fact_embedding IS NOT NULL WITH toString(r.fact_embedding) AS s RETURN substring(s,0,1) AS first, count(*) ORDER BY count(*) DESC"
```

---

## 2) One‑time data migration
Normalize all embeddings to Vectorf32. Prefer batch-safe queries.

- Edges first (fact embeddings):
```
GRAPH.QUERY graphiti_migration "MATCH ()-[r:RELATES_TO]->() WHERE r.fact_embedding IS NOT NULL SET r.fact_embedding = vecf32(r.fact_embedding) RETURN count(r)"
```

- Nodes second (name embeddings):
```
GRAPH.QUERY graphiti_migration "MATCH (n:Entity) WHERE n.name_embedding IS NOT NULL SET n.name_embedding = vecf32(n.name_embedding) RETURN count(n)"
```

If double-casting errors occur, filter only list-shaped values (heuristic):
```
GRAPH.QUERY graphiti_migration "MATCH ()-[r:RELATES_TO]->() WHERE r.fact_embedding IS NOT NULL WITH r, toString(r.fact_embedding) AS s WHERE substring(s,0,1)='[' SET r.fact_embedding = vecf32(r.fact_embedding) RETURN count(r)"
GRAPH.QUERY graphiti_migration "MATCH (n:Entity) WHERE n.name_embedding IS NOT NULL WITH n, toString(n.name_embedding) AS s WHERE substring(s,0,1)='[' SET n.name_embedding = vecf32(n.name_embedding) RETURN count(n)"
```

Notes
- Make a snapshot/backup if needed; this is an in-place update.
- If you have extremely large graphs, run in chunks (e.g., by LIMIT or by time window) to avoid long locks.

---

## 3) Code changes to prevent regressions

A) Patch ad‑hoc update scripts to always cast to Vectorf32 when using FalkorDB
- In `batch_generate_embeddings.py`, update to:
```
MATCH (n:Entity {uuid: $uuid})
SET n.name_embedding = vecf32($embedding)
RETURN n.uuid
```

B) Keep Graphiti core writes as-is (already uses vecf32)
- Nodes: `graphiti_core/models/nodes/node_db_queries.py`
  - `SET n.name_embedding = vecf32($entity_data.name_embedding)`
- Edges: `graphiti_core/models/edges/edge_db_queries.py`
  - `SET r.fact_embedding = vecf32($edge_data.fact_embedding)`
- Bulk helpers in `graphiti_core/graph_queries.py` already include vecf32.

C) Optional: driver-aware helper (if you update embeddings via generic paths)
- Emit `vecf32($embedding)` only for FalkorDB; plain arrays for Neo4j.
- Centralize this in a small helper to avoid duplication and mistakes.

---

## 4) Verification after migration

A) Re-run state checks
```
GRAPH.QUERY graphiti_migration "MATCH (n:Entity) WHERE n.name_embedding IS NOT NULL RETURN count(n)"
GRAPH.QUERY graphiti_migration "MATCH ()-[r:RELATES_TO]->() WHERE r.fact_embedding IS NOT NULL RETURN count(r)"
GRAPH.QUERY graphiti_migration "MATCH (n:Entity) WHERE n.name_embedding IS NOT NULL RETURN toString(n.name_embedding) LIMIT 3"
GRAPH.QUERY graphiti_migration "MATCH ()-[r:RELATES_TO]->() WHERE r.fact_embedding IS NOT NULL RETURN toString(r.fact_embedding) LIMIT 3"
```
- Expect `toString(...)` samples to resemble `<...>` for vectors.

B) Python direct similarity test
- Use the existing `test_direct_query.py` pattern with:
```
WITH n, (2 - vec.cosineDistance(n.name_embedding, vecf32($search_vector)))/2 AS score
```
- Expect successful execution and sensible scores.

C) Rust service E2E
- Trigger node and edge similarity endpoints from the Rust microservice (port 3004) via the Python proxy.
- Confirm:
  - HTTP 200
  - No “expected Null or Vectorf32 but was List” in logs
  - Non-empty, ordered results for known queries

---

## 5) Monitoring and tests

- Add a small maintenance check you can run periodically:
```
MATCH (n:Entity) WHERE n.name_embedding IS NOT NULL WITH toString(n.name_embedding) AS s RETURN substring(s,0,1) AS first, count(*)
MATCH ()-[r:RELATES_TO]->() WHERE r.fact_embedding IS NOT NULL WITH toString(r.fact_embedding) AS s RETURN substring(s,0,1) AS first, count(*)
```
- Optional Rust smoke test: call similarity endpoints with a known vector and assert 200 + no errors in response.
- Ensure CI/code review checklist includes “FalkorDB writes must use vecf32 for embeddings”.

---

## 6) Rollout plan

1. Staging
- Run validation queries
- Apply migration (edges then nodes)
- Run verification (Python direct + Rust E2E)
- Patch any ad‑hoc scripts; rerun verification

2. Production
- Off-peak window recommended
- Apply migration with monitoring; if large, run in batches
- Verify via health checks and a small canary search

3. Rollback
- If needed, you can re-run the migration with the original list values only if you took a snapshot/backup. Otherwise, Vectorf32 is a superset for our usage—sticking with the migrated state is recommended.

---

## 7) Ownership and timeline

- Data migration: Graph/data ops (one window, 15–45 minutes depending on size)
- Code patches:
  - batch_generate_embeddings.py: 10 minutes + PR
  - Optional helper for driver-aware writes: 30–60 minutes + PR
- Verification: 30 minutes
- Total: ~1/2 day including change management

---

## 8) Risks and mitigations

- Long-running writes on large graphs
  - Mitigation: run in batches; schedule off-peak
- Double-casting errors if some values already Vectorf32
  - Mitigation: use substring heuristic to target list-shaped values only
- Hidden scripts writing lists
  - Mitigation: code audit and helper function; add periodic maintenance check

---

## 9) References in repo

- Rust queries (use vecf32 on the query vector): `graphiti-search-rs/src/falkor/client.rs`
- Core save queries (already casting to Vectorf32):
  - `graphiti_core/models/nodes/node_db_queries.py`
  - `graphiti_core/models/edges/edge_db_queries.py`
  - `graphiti_core/graph_queries.py`
- Potential regression source to patch: `batch_generate_embeddings.py`

---

## 10) Success criteria

- Rust similarity searches run without type mismatch errors
- Queries return stable scores and results
- All embeddings in DB are Vectorf32 (spot checks show `<...>` string form)
- No reappearance of list-typed embeddings over time

