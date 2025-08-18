## Migration Plan: graphiti-search-rs → falkordb-rs (official FalkorDB Rust client)

### Objective
Migrate the Rust search microservice from raw redis::Client + GRAPH.QUERY to the official FalkorDB Rust client (falkordb-rs) to gain:
- First-class parameter binding and safer query construction
- Stronger typing for values (e.g., VectorF32)
- Simpler, more reliable result parsing
- Reduced risk of type mismatches (List vs Vectorf32)

This plan focuses on graphiti-search-rs; it won’t change Python Graphiti core. A one-time DB normalization (List → Vectorf32) remains recommended for legacy data.

---

## 1) Current state snapshot

- Code paths
  - graphiti-search-rs/src/falkor/client.rs uses redis::aio::Connection + GRAPH.QUERY
  - Queries are built via string interpolation (e.g., embedding vectors inline)
  - Custom parsing converts redis::Value → internal Node/Edge models

- Risks
  - Manual string interpolation is brittle (escaping, injection surface)
  - No typed parameter passing; vector types may arrive as List if not cast in query
  - Custom parsing is error-prone and duplicates logic available in falkordb-rs

---

## 2) Target architecture with falkordb-rs

- Use falkordb::{FalkorClientBuilder, FalkorConnectionInfo, FalkorValue}
- Create a FalkorConnection wrapper in graphiti-search-rs mirroring the current interface (ping, fulltext, similarity, bfs)
- Initialize a single async client per service instance; select graph by name from config
- Prefer parameter binding over string interpolation for values
- Represent query vectors as FalkorValue::VectorF32 when supported, else bind as arrays and cast in Cypher via vecf32($param)

---

## 3) Dependency and setup

- Add dependency to graphiti-search-rs/Cargo.toml:
```
falkordb = "<latest>"
```
- If TLS/Auth is needed, configure via FalkorConnectionInfo
- Keep redis crate during transition behind a feature flag; remove after cutover

---

## 4) Query migration strategy

A) Fulltext search (nodes/edges/episodes)
- Replace manual string interpolation with bound params where possible
- Example (conceptual):
```
let mut graph = client.select_graph(&graph_name);
let result = graph
    .query("MATCH (n:Entity) WHERE toLower(n.name) CONTAINS $q RETURN n LIMIT $limit")
    .param("q", FalkorValue::String(query.to_lowercase()))
    .param("limit", FalkorValue::Integer(limit as i64))
    .execute()
    .await?;
```

B) Similarity search (nodes)
- Use property typed as VectorF32; bind query vector as param and cast with vecf32 in Cypher if needed
```
WITH n, (2 - vec.cosineDistance(n.name_embedding, vecf32($query_vector)))/2 AS score
```
- Bind $query_vector as FalkorValue::VectorF32 if available; fallback: FalkorValue::Array(Float) with vecf32($query_vector)

C) Similarity search (edges)
- Same pattern with r.fact_embedding
```
WITH a, r, b, (2 - vec.cosineDistance(r.fact_embedding, vecf32($query_vector)))/2 AS score
```

D) BFS
- Parameterize start uuids and depth
```
MATCH (start:Entity) WHERE start.uuid IN $uuids
CALL algo.BFS(start, $max_depth, 'RELATES_TO') YIELD nodes
UNWIND nodes AS n RETURN DISTINCT n LIMIT $limit
```

---

## 5) Result parsing

- Replace custom redis::Value parsing with falkordb-rs result handling:
  - Access `result.header` for column names
  - Iterate rows (`result.data` or crate-provided row access) to map values by header
  - Convert FalkorValue into internal models (Node, Edge, Episode) in a small adapter layer

- Implement a single converter utility to keep mapping logic DRY across endpoints

---

## 6) Backward-compatibility & feature flag

- Introduce a runtime flag: `FALKOR_DRIVER_IMPL = { "redis_raw" | "falkordb_rs" }`
- Implement the new Falkor client side-by-side, behind the flag
- Default to "falkordb_rs" in staging; keep "redis_raw" as a rollback path during the rollout

---

## 7) Work breakdown

1) Scaffolding (0.5 day)
- Add falkordb dependency
- Create FalkorConnection wrapper using falkordb-rs
- Implement ping/select graph lifecycle

2) Queries (1–1.5 days)
- Port fulltext (nodes, edges, episodes) with params
- Port node similarity (vec.cosineDistance + vecf32($query_vector))
- Port edge similarity (same pattern)
- Port BFS

3) Parsing adapters (0.5 day)
- Map FalkorValue rows to internal Node/Edge/Episode structs
- Add unit tests with sample rows

4) Feature flag & config (0.25 day)
- Wire selection in config/ENV and service startup

5) Verification (0.5–1 day)
- Unit tests: parsing, query builders
- Integration: local FalkorDB, verify all endpoints
- Compare responses vs current implementation on a small dataset

6) Cleanup (0.25 day)
- Remove redis_raw path if no longer needed after a bake-in period

Total estimate: ~3–4 days including review and bake-in

---

## 8) Verification plan

- Build & unit tests pass
- Local integration against FalkorDB (port 6389)
  - Fulltext returns results
  - Node similarity returns ordered results and no type mismatch errors
  - Edge similarity returns ordered results
  - BFS returns nodes up to max_depth
- Compare first-page results and scores between old/new implementations where possible
- Log inspection: no “Type: mismatch: expected Null or Vectorf32 but was List”

Note: If legacy List-typed embeddings exist, the new driver won’t mask that. Run the separate data normalization first.

---

## 9) Risks and mitigations

- API differences for parameter binding
  - Mitigation: consult falkordb-rs docs; fallback to vecf32($param) casting for vectors
- Performance deltas
  - Mitigation: baseline perf before/after; tune connection reuse
- Unexpected result mapping differences
  - Mitigation: golden test outputs on small dataset; adapters that normalize values
- Legacy data type issues persist
  - Mitigation: run data migration to VectorF32 before cutover

---

## 10) Rollout & rollback

- Staging
  - Enable falkordb_rs via flag
  - Run full test suite + manual smoke
- Production
  - Gradual rollout
  - Monitor errors, latency, result counts
  - Rollback: flip flag back to redis_raw if issues arise

---

## 11) Next steps

- Approve plan
- I’ll add the scaffolding module (new Falkor client wrapper) and flag wiring
- Then port similarity queries first (highest impact), followed by fulltext and BFS
- After verification, plan removal of the old path

