# Centrality Calculation Update Plan

## Objectives
- Ensure eigenvector centrality is correctly computed and persisted to the database.
- Make centrality computation robust regardless of Rust service availability (add a Python fallback or skip‑less trigger).
- Standardize filtering so audit edges and merged/tombstone nodes do not distort metrics.
- Align API/DB property names and storage behavior across services.
- Add tests, observability, and a safe rollout/backfill plan.

## Current behavior (summary)
- Ingestion triggers a debounced centrality job only when Rust centrality is enabled. If disabled, centrality is skipped entirely.
- Rust service computes PageRank, Degree, Betweenness, and Eigenvector centrality and returns scores.
- Storage bug: Rust client writes the composite `importance` value into `n.eigenvector_centrality`.
- Python centrality paths exist but do not compute eigenvector; they are used as a fallback in some functions but not from ingestion.
- Centrality calculations (Python and Rust) include `IS_DUPLICATE_OF` edges and merged tombstones by default.

## Issues identified
1. Eigenvector centrality missing/incorrect in DB due to storage bug (importance stored instead of eigenvector).
2. Ingestion skips centrality entirely when Rust is disabled; no Python fallback is executed.
3. Metrics include audit edges (`IS_DUPLICATE_OF` typed relation and RELATES_TO{name:'IS_DUPLICATE_OF'}) and merged nodes (`is_merged=true`).
4. Inconsistent representation of duplicate edges causes double counting (typed relation vs. property‑based name).
5. Inconsistent property naming for composite metric; no clear separation between `eigenvector_centrality` and `importance_score`.

## Design changes

### 1) Fix storage mapping in Rust client (blocking)
- File: `graphiti-centrality-rs/src/client.rs`
- Change mapping to write the true eigenvector score:
  - Replace `let eigenvector = node_scores.get("importance")...` with `node_scores.get("eigenvector")...`.
  - Keep writing composite importance to a separate property `n.importance_score` (new), not to `eigenvector_centrality`.
- Batch update query sets:
  - `n.pagerank_centrality`, `n.degree_centrality`, `n.betweenness_centrality`, `n.eigenvector_centrality`, and `n.importance_score`.

### 2) Standardize filtering rules (Rust + Python)
- Exclude audit edges and merged nodes from all centrality computations:
  - Nodes: filter out `n.is_merged = true`.
  - Edges: exclude both encodings of duplicate relationships:
    - Relationship type `:IS_DUPLICATE_OF`
    - `:RELATES_TO { name: 'IS_DUPLICATE_OF' }`
- Apply these filters in:
  - Rust algorithms adjacency queries and degree queries.
  - Python fallback queries (degree, pagerank, betweenness if used).
- Optional: Add a configuration flag `centrality.exclude_audit=true` and `centrality.exclude_merged=true` (default true).

### 3) Ingestion trigger resilience
- File: `server/graph_service/routers/ingest.py`
- If Rust service is disabled/unreachable, do NOT skip entirely. Options:
  - A) Call Python centrality path for at least degree + pagerank (and eigenvector if added to Python).
  - B) Enqueue a retry job (e.g., background task) rather than skipping.
- Add structured logs around debounce trigger, groups processed, and outcomes.

### 4) API alignment
- File: `server/graph_service/routers/centrality.py`
- Ensure `/centrality/all` proxies through and supports `store_results=true/false` and `group_id`.
- Confirm response includes `{ pagerank, degree, betweenness, eigenvector, importance }` per node.
- If Python fallback is used, bring parity with Rust response shape.

### 5) Schema and properties
- Node properties used:
  - `degree_centrality: float` (normalized 0–1 for v2; document normalization)
  - `pagerank_centrality: float`
  - `betweenness_centrality: float`
  - `eigenvector_centrality: float`
  - `importance_score: float` (composite metric; new)
- Migration considerations:
  - If current `eigenvector_centrality` values were actually importance, either recompute or migrate:
    - Option A (preferred): Recompute all metrics after storage fix (backfill step).
    - Option B: If recompute is costly, copy existing `eigenvector_centrality` to `importance_score` before recompute.

### 6) Configuration
- `USE_RUST_CENTRALITY` / `settings.use_rust_centrality` (existing)
- New (with defaults):
  - `centrality.exclude_audit = true`
  - `centrality.exclude_merged = true`
  - `centrality.max_iterations_eigen = 100`
  - `centrality.tolerance_eigen = 1e-6`
  - `centrality.batch_size_store = 100`
  - `centrality.timeout_seconds = 30`

### 7) Testing plan
- Rust integration test:
  - Call `/centrality/all` with `store_results=true` on a small seeded graph.
  - Validate DB writes: `eigenvector_centrality` equals returned `scores[node].eigenvector`.
  - Ensure `importance_score` is present and separate.
  - Ensure excluded edges/nodes are actually excluded by constructing a graph with `IS_DUPLICATE_OF` edges and `is_merged=true` nodes.
- Python service test:
  - If fallback path is added, verify parity of response and storage off/on Rust.
- Frontend smoke:
  - Visualizer queries should read `eigenvector_centrality` and not break if `importance_score` exists.

### 8) Rollout and backfill
1. Land Rust client storage fix; deploy Rust service.
2. Land filtering updates (Rust first, then Python fallback if used).
3. Enable ingestion-triggered centrality without hard skip; add logs.
4. Backfill centrality for all groups:
   - Call `/centrality/all` with `store_results=true` (with `group_id` batches if needed).
   - Monitor progress logs and DB write success rates.
5. Remove any temporary migration code once backfill completes.

### 9) Observability
- Add `CENTRALITY_DEBUG` logs already present, plus:
  - Count of nodes processed per metric.
  - Timings for adjacency fetch, compute, and storage.
  - Error counts and retry counts in batch storage.
- Consider a `/centrality/stats` endpoint in Python proxy mirroring Rust stats.

## Acceptance criteria
- `eigenvector_centrality` exists and matches service‑returned `scores[node].eigenvector`.
- `importance_score` stored separately and used where composite is needed.
- Centrality runs on ingestion even if Rust is disabled (fallback or queued retry).
- Audit edges and merged nodes are excluded from all centrality metrics.
- Comprehensive tests pass; smoke run on staging shows expected distributions.

## Open questions
- Do we need Python to compute eigenvector in fallback mode, or can we queue until Rust is available?
- Should we hard delete merged nodes to simplify centrality graph, or keep filtering long‑term?
- What SLA/latency do we require for centrality updates post‑ingestion (debounce window)?

