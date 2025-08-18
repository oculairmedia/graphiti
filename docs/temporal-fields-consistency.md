# Temporal Fields Consistency Guide (created, date, created_at)

This document explains the current mismatch between DuckDB, Rust, and the frontend for node temporal fields, and provides implementation-ready steps and snippets for both a quick frontend-only fix and a robust backend + frontend solution.

- Immediate fix (recommended to do now): Frontend-only conversion/fallback that ensures `created_at` (ISO string) is always available and `created_at_timestamp` is a safe number.
- Long-term fix (recommended overall): Extend DuckDB schema to also store a `created_at` string alongside the numeric timestamp, and write both consistently from Rust.

---

## Problem Summary

- DuckDB `nodes` table stores `created_at_timestamp` (DOUBLE), not `created_at` (string).
- The frontend expects `created_at` in several places (properties panel, temporal layouts, data prep), leading to `undefined` displays.
- JSON/API paths may include `created_at` as a string; DuckDB path currently does not.

---

## Current State (Confirmed)

- DuckDB schema (no `created_at` string):
  - File: `graph-visualizer-rust/src/duckdb_store.rs`
  - `CREATE TABLE nodes (... created_at_timestamp DOUBLE, ...)`

- Inserts write only the numeric timestamp:
  - `INSERT OR REPLACE INTO nodes (..., created_at_timestamp, ...) VALUES (...)

- Frontend loads directly from DuckDB via Arrow:
  - File: `frontend/src/hooks/useGraphDataQuery.ts`
  - Maps `created_at` from row value, which is missing in DuckDB rows

- UI consumers expecting/using `created_at`:
  - Node details: `frontend/src/components/NodeDetailsPanel.tsx`
  - Transforms/layouts: `frontend/src/utils/graphDataTransform.ts`, `frontend/src/utils/layouts/temporal.ts`
  - Data preparer: `frontend/src/utils/cosmographDataPreparer.ts`

---

## Option 2: Immediate Frontend-only Fix

Goal: Ensure `created_at` exists as an ISO string and `created_at_timestamp` is a number for all nodes fetched from DuckDB.

### 1) Add a fallback in `useGraphDataQuery.ts`

Right after you construct `plainNode` from the Arrow row (before returning the mapped node), convert numeric `created_at_timestamp` to an ISO string if `created_at` is missing.

```ts
// Fallback: convert numeric timestamp to ISO if created_at is missing
if (!plainNode.created_at && (plainNode.created_at_timestamp !== undefined && plainNode.created_at_timestamp !== null)) {
  const ts = Number(plainNode.created_at_timestamp);
  if (!Number.isNaN(ts)) {
    // DuckDB column is DOUBLE in milliseconds
    plainNode.created_at = new Date(ts).toISOString();
  }
}
```

Then, when returning the mapped node, keep `created_at` and `created_at_timestamp` as you do, but harden the timestamp field type handling in `properties`:

```ts
properties: {
  // ...centrality and other fields...
  created: plainNode.created_at || plainNode.created || undefined,
  date: plainNode.created_at || plainNode.date || undefined,
  created_at: plainNode.created_at || undefined,
  created_at_timestamp:
    typeof plainNode.created_at_timestamp === 'number'
      ? plainNode.created_at_timestamp
      : (plainNode.created_at ? new Date(plainNode.created_at).getTime() : Date.now())
}
```

Notes:
- This keeps downstream code working even if the Arrow row has no `created_at` (string) but has a numeric timestamp.
- If both are missing, we provide a reasonable fallback to `Date.now()` to avoid `NaN`.

### 2) Harden `cosmographDataPreparer.ts`

Current logic assumes `created_at_timestamp` is a parseable date string. Make it robust to number or string and fall back to `created_at`:

```ts
const cat = (node as any).created_at_timestamp;
if (typeof cat === 'number' && Number.isFinite(cat)) {
  sanitizedNode.created_at_timestamp = cat;
} else if (typeof cat === 'string') {
  const parsed = new Date(cat).getTime();
  sanitizedNode.created_at_timestamp = Number.isFinite(parsed)
    ? parsed
    : (node.created_at ? new Date(node.created_at).getTime() : Date.now());
} else {
  sanitizedNode.created_at_timestamp = node.created_at ? new Date(node.created_at).getTime() : Date.now();
}
```

### 3) Optional UI polish

Node details panel already prefers `node.created_at`; with the fallback above, it will render consistently. To be extra defensive, you can also check `node.properties?.created_at` as another fallback:

```ts
created: node.created_at || node.properties?.created_at || node.properties?.created || new Date().toISOString()
```

### 4) Quick verification

- Load the app with DuckDB data; open a node. The properties/timestamps should not show `undefined`.
- Check console logs in `useGraphDataQuery` where `firstNode` is logged to verify `created_at` exists.
- If using a temporal layout, confirm nodes lay out over time without NaN.

---

## Option 1: Long-term Backend + Frontend Fix

Goal: Store both `created_at` (ISO string) and `created_at_timestamp` (DOUBLE) in DuckDB. Continue to keep frontend fallbacks for resilience.

### 1) Extend DuckDB schema

In `graph-visualizer-rust/src/duckdb_store.rs`, add a `created_at` column:

```rust
// Best-effort migration for existing instances (safe no-op if column already exists)
let _ = conn.execute("ALTER TABLE nodes ADD COLUMN created_at VARCHAR", params![]);

// For new DBs, include created_at in CREATE TABLE
duckdb.execute(
  "CREATE TABLE nodes (
      id VARCHAR PRIMARY KEY,
      idx INTEGER NOT NULL,
      label VARCHAR NOT NULL,
      node_type VARCHAR NOT NULL,
      summary VARCHAR,
      degree_centrality DOUBLE,
      pagerank_centrality DOUBLE,
      betweenness_centrality DOUBLE,
      eigenvector_centrality DOUBLE,
      x DOUBLE,
      y DOUBLE,
      color VARCHAR,
      size DOUBLE,
      created_at VARCHAR,             -- NEW
      created_at_timestamp DOUBLE,
      cluster VARCHAR,
      clusterStrength DOUBLE
  )",
  params![],
)?;
```

### 2) Write both fields on insert/update

Update the insert column list(s) to include both fields (initial load and updates):

```rust
let stmt_node = "INSERT OR REPLACE INTO nodes (
    id, idx, label, node_type, summary,
    degree_centrality, pagerank_centrality, betweenness_centrality, eigenvector_centrality,
    x, y, color, size,
    created_at, created_at_timestamp,   -- NEW
    cluster, clusterStrength
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)";
```

Compute both values based on properties (or synthesize if absent):

```rust
let (created_str_opt, timestamp) = if let Some(created_str) = node.properties.get("created_at").and_then(|v| v.as_str()) {
    let ts = chrono::DateTime::parse_from_rfc3339(created_str)
        .map(|dt| dt.timestamp_millis() as f64)
        .unwrap_or_else(|_| (idx as f64) * 86_400_000.0);
    (Some(created_str.to_string()), ts)
} else {
    let ts = (idx as f64) * 86_400_000.0; // deterministic synthetic
    let d = chrono::DateTime::<chrono::Utc>::from_timestamp_millis(ts as i64)
        .unwrap_or_else(chrono::Utc::now);
    (Some(d.to_rfc3339()), ts)
};

// ... in params
params![
  &node.id,
  idx as u32,
  &node.label,
  &node.node_type,
  &node.summary,
  degree,
  pagerank,
  betweenness,
  eigenvector,
  Option::<f64>::None,
  Option::<f64>::None,
  color,
  size,
  created_str_opt.as_deref(), // NEW
  timestamp,                  // NEW
  cluster,
  cluster_strength
]
```

Apply the same changes in the code path that handles incremental updates/inserts.

### 3) Reads remain compatible

- `SELECT * FROM nodes` will now include `created_at` (string) and `created_at_timestamp` (DOUBLE).
- The frontend’s immediate fallback (Option 2) should remain in place for resilience and backward compatibility.

---

## Cross-layer Contract (Canonical Fields)

- `created_at`: ISO-8601 UTC string (e.g., from `toISOString()` / `to_rfc3339()`)
- `created_at_timestamp`: number, milliseconds since epoch (DOUBLE in DuckDB)

Rules:
- Backend writes both; if only one is available, derive the other.
- Frontend prefers:
  - Display: `created_at`
  - Computation: `created_at_timestamp`; if missing, parse `created_at`; if still missing, synthesize a safe fallback.

### Optional TS helper

```ts
export function normalizeTemporal<T extends { created_at?: string; created_at_timestamp?: number }>(node: T): T & { created_at: string; created_at_timestamp: number } {
  let created_at = node.created_at;
  let ts = node.created_at_timestamp;

  if (typeof ts !== 'number' || !Number.isFinite(ts)) {
    ts = created_at ? new Date(created_at).getTime() : Date.now();
  }
  if (!created_at) {
    created_at = new Date(ts).toISOString();
  }
  return { ...node, created_at, created_at_timestamp: ts };
}
```

Use this in `useGraphDataQuery` just before returning each node, or in a shared transformation step.

---

## Rollout Checklist

Immediate (frontend-only):
- [ ] Add the fallback conversion in `useGraphDataQuery.ts` (Option 2, step 1)
- [ ] Harden `cosmographDataPreparer.ts` numeric/string handling (Option 2, step 2)
- [ ] Manual UI check: properties panel shows non-undefined dates; temporal features work

Long-term (backend + frontend):
- [ ] Add `created_at` VARCHAR to DuckDB schema; keep `created_at_timestamp` DOUBLE
- [ ] Update both insert paths in `duckdb_store.rs` to write both
- [ ] Keep frontend fallback for resilience and mixed data sources
- [ ] Manual verification: DuckDB rows include both fields; frontend displays correctly

---

## Risks and Mitigations

- Non-ISO strings upstream: backend parsing falls back to deterministic synthetic timestamp; frontend still guards.
- Timezones: standardize on UTC in both directions (`toISOString` / `to_rfc3339`).
- Mixed data sources: frontend fallbacks ensure consistent fields even when data comes from JSON/WebSocket vs DuckDB.
- Type mismatches: robust type checks prevent NaN/invalid timestamps.

---

## Verification Steps

- Open app with DuckDB sourcing nodes; ensure properties/timestamps are present.
- Inspect one node in console logs (from `useGraphDataQuery`) for the presence of both fields.
- Exercise any time-based UI (timeline/temporal layout) and ensure stable rendering (no NaN, no clustering at 1970-01-01 unless expected).
- (Optional) Unit tests:
  - Transform a node with only `created_at_timestamp` and assert `created_at` is populated.
  - Transform a node with only `created_at` and assert `created_at_timestamp` is numeric.
  - Ensure `cosmographDataPreparer` handles number/string gracefully.

