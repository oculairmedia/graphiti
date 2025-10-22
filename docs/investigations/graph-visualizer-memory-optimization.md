# Graph Visualizer (Rust) Memory Audit

## Context

The `graph-visualizer-rust` service (`graph-visualizer-rust/src`) shows steady memory growth over long uptimes. A review of the implementation highlights several long-lived data structures and patterns that retain whole-graph payloads, plus redundant copies created during reloads and broadcasts. The notes below capture the main contributors and outline remediation ideas.

## Key Contributors

- **Unbounded query cache** – In-memory cache stores entire `GraphData` responses under distinct keys and never evicts entries (`graph-visualizer-rust/src/main.rs:680-754`). Distinct query parameter combinations (search terms, offsets, limits) steadily accumulate.
- **Arrow cache duplication** – `ArrowCache` retains both `RecordBatch` structs and their serialized `Bytes` representation simultaneously (`graph-visualizer-rust/src/main.rs:300-366`). Each reload duplicates the full graph footprint.
- **Broadcast buffers holding whole graphs** – The broadcast channels for websocket updates keep the last 100 messages (`graph-visualizer-rust/src/main.rs:219-221`). Payloads are full `GraphUpdate` / `GraphDelta` structs containing complete node and edge lists (`graph-visualizer-rust/src/websocket.rs:214-231`, `graph-visualizer-rust/src/delta_tracker.rs:8-32`).
- **Delta tracker history** – `DeltaTracker` stores the full current node/edge maps and a rolling history of 100 deltas (`graph-visualizer-rust/src/delta_tracker.rs:23-89`). Each delta clones large vectors, so history size multiplies memory needs.
- **Clone-heavy reload path** – Initial load and change detection rebuild the DuckDB store with multiple cloned vectors (`graph-visualizer-rust/src/main.rs:307-390`, `graph-visualizer-rust/src/duckdb_store.rs:182-267`). Transient allocations spike while persistent caches retain earlier copies.
- **Redis “enhanced cache” never activated** – The Bloom-filter check in `EnhancedCache` always returns `false` for unseen keys, which short-circuits caching and forces the heavy in-memory `DashMap` to carry the load (`graph-visualizer-rust/src/cache.rs:124-144`).
- **Pending edge buffer growth** – Edges that reference missing nodes are queued with retry metadata (`graph-visualizer-rust/src/duckdb_store.rs:648-720`). Without pruning, this array can keep growing if sources never arrive.

## Improvement Opportunities

### Contain long-lived replicas
1. Replace the raw `DashMap` query cache with a size- and TTL-bounded structure (e.g., `lru::LruCache` with `Arc<Node/Edge>` sharing). Provide `CACHE_MAX_ENTRIES` env controls.
2. Rework `ArrowCache` to store either `RecordBatch` *or* encoded `Bytes`, not both; regenerate on demand when stale.
3. Limit broadcast backlog size for heavy payloads, or broadcast diffs only. Consider storing deltas outside the channel and streaming references instead.
4. Reduce `DeltaTracker` history to shallow diffs (IDs + metadata) and persist full state only once. Alternatively, move history to disk-backed store or trim to a handful of entries.

### Reduce cloning and redundant loads
1. When refreshing DuckDB, consume vectors in place (take ownership from `GraphData`) instead of cloning (`graph-visualizer-rust/src/main.rs:334-367`, `graph-visualizer-rust/src/duckdb_store.rs:205-267`).
2. During paginated fetches, avoid `nodes_map.keys().cloned().collect()`; preserve identifiers as references or streaming iterators (`graph-visualizer-rust/src/main.rs:1000-1003`).
3. Revisit repeated JSON conversions in `falkor_value_to_json`; these produce fresh allocations per request (`graph-visualizer-rust/src/main.rs:1270-1320`). Cache or memoize frequent property subsets.

### Align caching layers
1. Activate Redis-backed caching by correcting the Bloom-filter logic (mark keys as existing after successful fetch) and add expiry/eviction policies (`graph-visualizer-rust/src/cache.rs:124-200`).
2. Expose cache metrics endpoints to track entry counts, hit rates, and serialized sizes (`graph-visualizer-rust/src/main.rs:800-828`).

### Housekeeping tasks
1. Add periodic pruning for `pending_edges` to prevent unbounded retry queues (`graph-visualizer-rust/src/duckdb_store.rs:648-720`).
2. Implement explicit cache clear hooks on shutdown signals to release `DashMap` contents.
3. Instrument memory usage (rss, heap allocations) via `metrics` or `tracing` to quantify improvements over time.

## Suggested Next Steps

1. Prototype an LRU/TTL-backed query cache and validate memory usage during load tests.
2. Refactor `ArrowCache` to single-representation storage and benchmark regeneration cost.
3. Convert websocket broadcasts to delta-only payloads with size guards; document contract changes for clients.
4. Harden `EnhancedCache` and add metrics to monitor hit rate vs. memory footprint.
5. Schedule a follow-up review after these changes are in place to confirm leak mitigation.
