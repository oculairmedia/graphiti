# Graphiti Embedding Ingestion Expectations

This document captures the technical expectations we place on every service or
script that writes data into Graphiti’s FalkorDB instance. Share it with any
partner team or vendor (CocoIndex, Huly, BookStack, etc.) that touches the
graph so we stop reintroducing list-based embeddings or malformed ingestion
payloads.

## 1. Why This Matters

- FalkorDB’s vector functions (`vec.cosineDistance`, `vec.euclideanDistance`,
  vector indexes, etc.) require **`VectorF32`** values.
- Historical migrations and early ingestion pipelines stored raw **Python
  lists** in `fact_embedding`, `name_embedding`, `summary_embedding`, etc.
  Those rows trigger `Type mismatch: expected Null or Vectorf32 but was List`
  errors during search, dedupe, and invalidation.
- We ran a one-time backfill (`scripts/fix_falkor_fact_embeddings.py`) on
  2025-10-10 that converted **19,127** legacy edges to `VectorF32`. From this
  point forward, any source that writes list embeddings will immediately break
  ingestion.

## 2. Supported Ingestion Paths (and Their Guarantees)

| Path | Example Producers | Guarantee |
| --- | --- | --- |
| Graphiti API (`POST /messages`, `/entity-node`, etc.) | OpenCode hooks, MCP server | Driver layer converts nested lists ⇢ `VectorF32` before hitting Falkor. |
| Worker queue (`graphiti-worker`) | OpenCode context collector | Same driver patch as above. |
| Sync service (`graphiti-sync-service`) | Neo4j ⇢ Falkor replication | `_safe_value_for_query()` wraps known embedding properties with `vecf32([...])`. |
| Backfill utilities (`scripts/backfill_cocoindex_embeddings.py`) | CocoIndex / BookStack refresh | Uses `vecf32($embedding)` on updates. |

❗ Anything that bypasses these paths must implement the conversion rules in
Section 3.

## 3. Embedding Conversion Requirements

For every write into FalkorDB (nodes or edges):

1. **Detect embedding fields.** The canonical set:
   - `name_embedding`
   - `summary_embedding`
   - `fact_embedding`
   - `content_embedding`
   - `embedding` / `embeddings`
2. **Convert lists ⇢ `VectorF32`.** You have two options:
   - Wrap the value in Cypher with `vecf32([...])`, e.g.
     ```cypher
     SET r.fact_embedding = vecf32($embedding)
     ```
   - Or, from Python, instantiate `VectorF32(list_value)` (available from the
     `falkordb` client) before passing parameters.
3. **Do not leave the property unset.** If the embedder is offline, either
   retry later or omit the embedding property entirely. Never store the list
   with the intent to “fix it later.”

## 4. Expectations for Specific Producers

### 4.1 CocoIndex Pipelines (BookStack and Huly Exports)

- Use the Cypher templates in
  `COCOINDEX_GRAPHITI_FALKORDB_INTEGRATION.md` which already apply
  `vecf32(...)`.
- If you generate Cypher dynamically, ensure the function that formats query
  values mirrors the sync service’s `_safe_value_for_query()` logic.
- When backfilling previously ingested nodes or edges, run:
  ```bash
  python scripts/backfill_cocoindex_embeddings.py \
      --groups <group-ids> --include-episodes --batch-size 100
  ```
- Reset local caches (HuggingFace, Polly, etc.) after embedding model upgrades
  to avoid mismatched dimensions.

### 4.2 Huly MCP / BookStack MCP Integrations

- The MCP servers should call the Graphiti API; they must **not** write
  directly to FalkorDB.
- When batching historical data, run it through Graphiti’s ingestion endpoints
  or reuse the backfill scripts above.

### 4.3 Custom Scripts / One-Off Migrations

- Use `GraphitiClientFactory` to obtain the embedder so you match runtime
  configuration (model, dimension, authentication).
- If you must connect straight to FalkorDB, import `VectorF32` from the
  `falkordb` package and convert manually before executing the query.
- Never embed on the client and defer conversion to an operator—ship the data
  in the correct shape the first time.

## 5. Validation & Monitoring Checklist

| Step | Command / Tool | Purpose |
| --- | --- | --- |
| Post-ingestion sample | `MATCH ()-[r:RELATES_TO]->() RETURN r.fact_embedding LIMIT 5` | Confirm the type prints as `VectorF32`. |
| Backfill drift | `python scripts/fix_falkor_fact_embeddings.py --dry-run` | Detect new list embeddings without modifying data. |
| Worker logs | `docker logs graphiti-graphiti-worker-1` | Alert on `Type mismatch: expected Null or Vectorf32` immediately. |
| Sync health | `curl http://localhost:8082/health` | Ensure reverse sync isn’t faulting on vector type errors. |

Set up alerting (Grafana/Loki/CloudWatch) on the specific error string so we
catch regressions the moment they appear.

## 6. Communication Template

Use the following when engaging partner teams:

> Please ensure your ingestion pipeline converts all embeddings to FalkorDB’s
> `VectorF32` type. Acceptable patterns are `vecf32([...])` in Cypher or
> `VectorF32(list)` in Python before executing the query. Storing raw lists will
> break ingestion and trigger continuous retries. If you’ve already written
> list embeddings, run `scripts/fix_falkor_fact_embeddings.py` or
> `scripts/backfill_cocoindex_embeddings.py` (for CocoIndex groups) to
> normalize existing data.

## 7. Incident Response

1. **Immediately stop** the offending pipeline.
2. Run `scripts/fix_falkor_fact_embeddings.py` to normalize edges (and any
   equivalent script for nodes if necessary).
3. Restart the worker (`docker compose restart graphiti-worker`).
4. Notify ingestion stakeholders with the root cause and remediation steps.
5. Update this document if new patterns emerge.

---

Maintainer: *@Graphiti Infra*  
Last Updated: 2025-10-10
