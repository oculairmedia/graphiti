# CocoIndex `created_at` Timestamp Issue

## Summary
- The graph visualizer backend (`graph_visualizer_backend::duckdb_store`) is repeatedly warning that `created_at` values such as `"1758337688098"` contain invalid characters and are being replaced with the current time.
- Inspection of FalkorDB confirms that entity records coming from the CocoIndex ingestion pipeline store `created_at` as millisecond epoch integers instead of ISO8601 timestamps.
- These integer strings violate the schema documented in `COCOINDEX_GRAPHITI_FALKORDB_INTEGRATION.md`, which requires `created_at` to be a datetime, and they break any component that expects ISO/RFC3339 timestamps (graph visualizer, DuckDB export, analytics jobs).

## Evidence
### Visualizer Logs
```
2025-09-23T16:41:06.247785Z  WARN graph_visualizer_backend::duckdb_store: Failed to parse created_at '1758333632434': input contains invalid characters, using current time
2025-09-23T16:41:06.262397Z  WARN graph_visualizer_backend::duckdb_store: Failed to parse created_at '1758464228762': input contains invalid characters, using current time
```

### FalkorDB Query
```
MATCH (n:Entity)
RETURN n.uuid, n.created_at
ORDER BY n.created_at DESC
LIMIT 5;
```
Example result (run 2025-09-23):
```
[
  ['aa25d261-8aa0-5a88-b46d-bd7db0c0bbb4', 1758464374756],
  ['08a3b8e0-5e18-57cd-ac8f-99ec529d32fc', 1758464374751],
  ['8c0285ea-a330-54ec-b67c-b6953d231901', 1758464374747]
]
```
All three rows show an integer millisecond value instead of a datetime string.

## Expected vs Actual
| Property      | Expected (per integration spec)            | Actual value ingested |
|---------------|--------------------------------------------|-----------------------|
| `created_at`  | ISO8601 / RFC3339 timestamp (e.g. `2025-09-23T16:37:01Z`) | 13-digit epoch in milliseconds (`1758464374756`) |

## Likely Source
- The CocoIndex → Graphiti integration that writes directly to FalkorDB appears to populate `created_at` with `int(time.time() * 1000)` (or similar) rather than a formatted datetime.  The warnings only occur for nodes/groups originating from CocoIndex imports, and other ingestion paths (standard Graphiti episodes) continue to emit proper ISO timestamps.

## Impact
- Graph visualizer falls back to "current time" for affected rows, making timeline views inaccurate.
- DuckDB exports/pipelines that rely on `created_at` for ordering receive inconsistent data.
- Any downstream analytics or retention policies keyed off `created_at` will misbehave for CocoIndex content.

## Recommended Fix
1. **Update CocoIndex ingestion code** to emit ISO8601 timestamps (e.g. `datetime.utcnow().isoformat()` or `datetime.fromtimestamp(ms/1000, tz=timezone.utc)`) before writing to FalkorDB.
2. **Backfill existing records**: run a one-time script that converts integer `created_at` values to proper ISO strings for nodes/edges inserted by CocoIndex.
3. **Add validation** in the FalkorDB writing layer (or sync service) to reject non-string timestamps so future regressions are caught early.

## Next Steps
- Locate the CocoIndex ingestion script/service (see `COCOINDEX_GRAPHITI_FALKORDB_INTEGRATION.md`) and patch the timestamp serialization.
- Plan a cleanup job to normalize historical data once the write path is corrected.
