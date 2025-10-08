# Vector Dimension Mismatch Investigation (1024 vs 2560)

Purpose: Track findings and steps to identify why Redis/FalkorDB operations report "expected 1024 but got 2560" despite moving to 2560-dim embeddings.

Status: Ongoing

---

## 1) Working Hypotheses

- H1: A FalkorDB vector index was created with DIM=1024 and still exists. Any similarity op hitting that index expects 1024.
- H2: A service still constructs 1024-dim vectors at query time (tests or fallback code), causing mismatch with stored 2560.
- H3: Legacy code still defaults to 1024 in core embedder config, leaking into pipelines that build vectors.
- H4: A cached configuration in a long-running service (or Redis) retains 1024.

---

## 2) Evidence Collected From Codebase

### 2.1 Critical defaults still at 1024
- File: graphiti_core/embedder/client.py — hardcoded default

Example:
```python
EMBEDDING_DIM = 1024  # <- hardcoded
class EmbedderConfig(BaseModel):
    embedding_dim: int = Field(default=EMBEDDING_DIM, frozen=True)
```

Implication: Any place that instantiates EmbedderConfig without env override will assume 1024.

### 2.2 Test code creating 1024-dim vectors
- File: graphiti-search-rs/tests/test_falkordb_sdk.rs
  - `let test_vector: Vec<f32> = (0..1024)...`
- File: testing/integration/test_direct_v2.py
  - `np.random.randn(1024)`
- File: test_vector_wrapping.py
  - `[0.1] * 1024`
- File: test_vector_error_investigation.py
  - `[0.1] * 1024`

Implication: Running these tests against a 2560-dim dataset can reproduce the exact error.

### 2.3 Docs still anchoring to 1024
- File: docs/investigations/falkordb_similarity_type_mismatch.md
  - Mentions mxbai-embed-large = 1024 as the reference dimension.

### 2.4 Envs generally set to 2560
- docker-compose.yml sets `EMBEDDING_DIMENSION=${EMBEDDING_DIMENSION:-2560}`
- Rust search service uses `EMBEDDING_DIMENSION=2560` in compose

Implication: Runtime services should be on 2560 unless falling back to legacy defaults.

---

## 3) Where Vector Indexes Might Be Defined

Observed in codebase:
- Range and fulltext indexes are defined for FalkorDB (graphiti_core/graph_queries.py).
- No explicit vector index creation found in repo (no `CALL db.idx.vector...` in code).

Implication: Any vector indexes likely created manually or via a separate script/session. These can persist in FalkorDB and continue to influence query planning.

---

## 4) Live DB Checks To Run (Non-destructive)

Use redis-cli (adjust host/port/database):

1) List existing indexes
```bash
redis-cli -h <host> -p <port> GRAPH.QUERY <graph_name> "CALL db.indexes()"
```
- Look for any vector-specific entries, and check if DIM (or equivalent) shows 1024.

2) Inspect label/property presence
```bash
redis-cli -h <host> -p <port> GRAPH.QUERY <graph_name> "CALL db.labels()"
redis-cli -h <host> -p <port> GRAPH.QUERY <graph_name> "CALL db.propertyKeys()"
```

3) Sample vector dimension sanity check
- If supported, try a tiny diagnostic query that computes cosine distance between an existing node vector and a 2560-dim query vector (should succeed if dimensions match). If it errors with "expected 1024", the stored vector or an index expects 1024.

Example pattern (pseudo-Cypher):
```cypher
MATCH (n:Entity)
WHERE n.name_embedding IS NOT NULL
WITH n, (2 - vec.cosineDistance(n.name_embedding, vecf32($vec)))/2 AS score
RETURN score LIMIT 1
```
Bind `$vec` to a 2560-dim vector and see if it errors.

Note: If there's a function to read vector dim (vendor-specific, e.g., `vec.dim(n.name_embedding)`), use it to confirm stored vector length.

---

## 5) Likely Remediations (to be validated)

- Update core default:
  - graphiti_core/embedder/client.py: Remove hardcoded 1024; read from env/centralized config; default to 2560.
- Ensure all services use centralized config or `EMBEDDING_DIMENSION` env.
- Drop/recreate any FalkorDB vector indexes pointing at 1024 with 2560 instead.
  - Exact procedure depends on FalkorDB version; typically via `CALL db.indexes()` to identify and corresponding `DROP`/`CREATE` calls.
- Update tests to use 2560 or to derive dimension dynamically from config.
- Restart long-running services to flush cached defaults.

---

## 6) Action Items / Next Steps

- [ ] Confirm if any vector indexes exist and their configured dimension (via `CALL db.indexes()`).
- [ ] Confirm stored vector dimensions for a sample of nodes/edges.
- [ ] Patch core default in graphiti_core/embedder/client.py.
- [ ] Identify all ingestion/write paths to ensure they are writing 2560-dim embeddings.
- [ ] Update test suites that still assume 1024.
- [ ] Document vector index creation procedure (correct DIM=2560) for FalkorDB.

---

## 7) Open Questions

- Does FalkorDB expose vector index DIM via `CALL db.indexes()` (name varies by version)?
- Is there a dedicated `CALL db.idx.vector.*` API in the deployed FalkorDB version, and what are the exact create/drop commands?
- Is there any service that still connects to a different graph where 1024-dim embeddings exist?

---

## 8) Append Findings Here (running log)

- T+0: Found hardcoded `EMBEDDING_DIM = 1024` in graphiti_core/embedder/client.py; several tests use 1024-dim vectors; docs reference 1024.
- T+? (pending): Results of `CALL db.indexes()` and vector DIM confirmation.
- T+? (pending): Confirmation whether stored vectors are 2560-dim (via diagnostic query).

---

## 9) Reference Code Spots

- Core default:
  - graphiti_core/embedder/client.py
- Test vectors at 1024:
  - graphiti-search-rs/tests/test_falkordb_sdk.rs
  - testing/integration/test_direct_v2.py
  - test_vector_wrapping.py
  - test_vector_error_investigation.py
- Docs anchoring 1024:
  - docs/investigations/falkordb_similarity_type_mismatch.md

(We will update this document as we gather live DB evidence and apply fixes.)
