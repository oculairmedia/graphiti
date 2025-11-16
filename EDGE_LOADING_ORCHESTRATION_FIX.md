# Edge Loading Orchestration Fix

## Problem Summary

The Graphiti frontend was displaying only 690 edges when there were actually 121,139 edges in Neo4j and the sync was still in progress.

### Root Cause Analysis

1. **Database State:**
   - Neo4j: 121,139 edges (source of truth)
   - FalkorDB: Syncing in progress (690 → 5,528 → 11,884+ edges)
   - DuckDB (Rust visualizer): 690 edges (loaded too early)
   - Frontend: 690 edges (showing what's in DuckDB)

2. **Startup Race Condition:**
   - The `graph-visualizer-rust` service depends on `falkordb: service_healthy`
   - BUT it does NOT depend on `graphiti-init: service_completed_successfully`
   - This means the visualizer starts and loads data as soon as FalkorDB is healthy
   - The `graphiti-init` service orchestrates the Neo4j → FalkorDB sync
   - The sync takes ~10-20 minutes to complete for large graphs with edges
   - The visualizer loaded initial data when only 690 edges had been synced

3. **Sync Progress Timeline:**
   ```
   22:11:58 - 32,456 nodes, 0 edges (nodes sync first)
   22:12:28 - 47,906 nodes, 381 edges (edge sync begins)
   22:12:58 - 47,906 nodes, 863 edges
   22:13:28 - 47,906 nodes, 1,453 edges
   22:14:29 - 47,906 nodes, 2,718 edges
   ... (visualizer loaded at ~690 edges)
   22:20:30 - 47,906 nodes, 10,588 edges (still syncing)
   Target: 47,906 nodes, 121,139 edges
   ```

## Solution

### Immediate Fix
Added `graphiti-init` dependency to `graph-visualizer-rust` in `docker-compose.yml`:

```yaml
graph-visualizer-rust:
  depends_on:
    falkordb:
      condition: service_healthy
    graphiti-centrality-rs:
      condition: service_healthy
    graphiti-init:                              # ← NEW
      condition: service_completed_successfully # ← NEW
```

### How It Works

1. **Startup Sequence (Before Fix):**
   ```
   Neo4j starts → FalkorDB starts → Rust Visualizer starts (TOO EARLY!)
                                  ↓
                            graphiti-init starts sync
                                  ↓
                            Sync takes 10-20 minutes
   ```

2. **Startup Sequence (After Fix):**
   ```
   Neo4j starts → FalkorDB starts → graphiti-init starts
                                  ↓
                            Waits for sync completion:
                            - Nodes stabilize
                            - Edges stabilize
                            - Both counts stable for 15 seconds
                                  ↓
                            graphiti-init completes
                                  ↓
                            Rust Visualizer starts (with ALL edges)
   ```

### Verification

The `graphiti-init` script (`scripts/cold-boot-init.sh`) ensures:
- Neo4j and FalkorDB are healthy
- FalkorDB is cleared
- Sync service is running
- **Both nodes AND edges are fully synced**
- Counts are stable for 15 seconds (3 consecutive checks)
- Creates ready marker file

## Testing

### Manual Restart Test
```bash
# Restart visualizer after sync completes
docker-compose restart graph-visualizer-rust

# Check stats
curl http://localhost:3000/api/duckdb/stats | jq
```

### Full Cold Boot Test
```bash
# Use automated cold boot script
./scripts/automated-cold-boot.sh

# Or manually:
docker-compose down
docker-compose up -d
# Wait for graphiti-init to complete
docker-compose logs -f graphiti-init
```

## Monitoring Sync Progress

```bash
# Watch sync progress
docker-compose logs -f graphiti-init

# Check current edge count
docker-compose exec falkordb redis-cli \
  GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)"

# Check visualizer stats
curl http://localhost:3000/api/duckdb/stats | jq
```

## Related Files

- `docker-compose.yml` - Service dependencies
- `scripts/automated-cold-boot.sh` - Automated orchestration
- `scripts/cold-boot-init.sh` - Init container logic
- `graph-visualizer-rust/src/main.rs` - Initial data loading (lines 299-496)

## Impact

- ✅ Ensures visualizer always loads complete dataset
- ✅ Prevents partial edge display (690 instead of 121,139)
- ✅ Maintains data consistency across restarts
- ✅ No code changes required - only orchestration
- ⚠️ Slightly longer startup time (waits for complete sync)

## Alternative Solutions Considered

1. **Dynamic reload in visualizer** - Too complex, adds runtime overhead
2. **Periodic sync checks** - Would miss initial load issue
3. **WebSocket push on sync complete** - Requires additional coordination
4. **This solution (dependency ordering)** - Simple, reliable, declarative ✅

## Future Enhancements

Consider adding:
- Progress indicator during initial sync
- Health check that validates edge count matches expectations
- Metrics endpoint showing sync completion percentage
- Alert if visualizer loads with suspiciously low edge count
