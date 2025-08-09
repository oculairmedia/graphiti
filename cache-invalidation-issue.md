# Cache Invalidation Issue: StatsPanel Not Updating After WebSocket Updates

## Problem Summary

The StatsPanel in the Graph Control Panel shows stale node and edge counts even after new data is added via WebSocket updates. A hard refresh of the browser also fails to pull the correct updated information, indicating this is a backend caching issue rather than a frontend memoization problem.

## Root Cause Analysis

### Data Flow Architecture

The application has a complex data flow with multiple caching layers:

```
FalkorDB (Source of Truth)
    ↓
Rust Server (/api/visualize endpoint)
    ↓ (caches in graph_cache)
Frontend (useGraphDataQuery)
    ↓
StatsPanel (displays counts)
```

**Parallel Update Path:**
```
WebSocket Updates → DuckDB Store → Frontend Delta Updates
```

### The Core Issue

1. **Frontend fetches initial data** via `graphClient.getGraphData()` which calls `/api/visualize`
2. **`/api/visualize` queries FalkorDB directly** and caches results in `graph_cache`
3. **WebSocket updates only update DuckDB**, not FalkorDB
4. **Cache invalidation has timing issues** between FalkorDB updates and cache clearing

### Key Evidence

#### Frontend Data Fetching
```typescript
// frontend/src/hooks/useGraphDataQuery.ts
const { data: jsonData, isLoading: isJsonLoading, error } = useQuery({
  queryKey: ['graphData'],
  queryFn: async () => {
    const result = await graphClient.getGraphData({ 
      query_type: 'entire_graph',
      limit: 100000 
    });
    return result;
  },
  // ...
});
```

#### Rust Server Cache Logic
```rust
// graph-visualizer-rust/src/main.rs
async fn visualize(State(state): State<AppState>, Query(params): Query<QueryParams>) {
    // Check cache first - PROBLEM: Returns stale data
    let cache_key = format!("{:?}", params);
    if let Some(cached) = state.graph_cache.get(&cache_key) {
        return Ok(Json(QueryResponse {
            data: cached.value().clone(), // ← STALE DATA
            has_more: false,
            execution_time_ms: 0,
        }));
    }
    
    // Query FalkorDB (not DuckDB where updates are applied)
    let query = build_query(&params.query_type, limit, offset, params.search.as_deref());
    match execute_graph_query(&state.client, &state.graph_name, &query).await {
        Ok(data) => {
            state.graph_cache.insert(cache_key, data.clone()); // ← CACHES STALE DATA
            // ...
        }
    }
}
```

#### Cache Clearing Logic
```rust
// Cache is cleared after WebSocket updates
match state.duckdb_store.process_updates().await {
    Ok(Some(update)) => {
        let _ = state.update_tx.send(update.clone());
        
        // Clear caches to ensure fresh data
        state.graph_cache.clear();           // ← Clears cache
        let mut arrow_cache = state.arrow_cache.write().await;
        *arrow_cache = None;
        drop(arrow_cache);
    }
}
```

## The Race Condition

1. **WebSocket update arrives** → Updates DuckDB → Clears caches
2. **Frontend refreshes** → Calls `/api/visualize` 
3. **`/api/visualize` queries FalkorDB** (which may not be updated yet)
4. **Returns stale data** → Caches it again
5. **StatsPanel shows old counts**

## Multiple Data Sources Problem

The application uses **two different data sources**:

- **FalkorDB**: Queried by `/api/visualize` (used by StatsPanel)
- **DuckDB**: Updated by WebSocket deltas (used by GraphCanvas)

This creates inconsistency when updates only flow to one source.

## Solutions

### Option 1: Fix Cache Invalidation Timing (Recommended)

Ensure FalkorDB is updated before clearing caches:

```rust
// In webhook/update handlers
async fn process_webhook_data(state: AppState, data: WebhookData) {
    // 1. Update FalkorDB first
    update_falkordb(&state.client, &data).await?;
    
    // 2. Update DuckDB
    state.duckdb_store.process_updates().await?;
    
    // 3. Clear caches AFTER both are updated
    state.graph_cache.clear();
    let mut arrow_cache = state.arrow_cache.write().await;
    *arrow_cache = None;
}
```

### Option 2: Use DuckDB as Single Source

Modify `/api/visualize` to query DuckDB instead of FalkorDB:

```rust
async fn visualize(State(state): State<AppState>, Query(params): Query<QueryParams>) {
    // Query DuckDB instead of FalkorDB
    let nodes = state.duckdb_store.get_nodes_as_arrow().await?;
    let edges = state.duckdb_store.get_edges_as_arrow().await?;
    // Convert and return
}
```

### Option 3: Real-time Count Tracking (Frontend)

Pass live counts from GraphCanvas to StatsPanel:

```typescript
// In GraphCanvas.tsx
const [liveStats, setLiveStats] = useState({ nodeCount: 0, edgeCount: 0 });

// Update after delta processing
useEffect(() => {
  // After applying deltas
  setLiveStats({
    nodeCount: currentNodeCount,
    edgeCount: currentEdgeCount
  });
}, [deltaUpdates]);

// Pass to StatsPanel
<StatsPanel data={data} liveStats={liveStats} />
```

## Immediate Fix

The quickest fix is **Option 1** - ensuring proper cache invalidation timing by updating FalkorDB before clearing caches.

## Files to Modify

1. `graph-visualizer-rust/src/main.rs` - Fix cache invalidation timing
2. `graph-visualizer-rust/src/duckdb_store.rs` - Coordinate updates
3. `server/graph_service/routers/ingest.py` - Ensure FalkorDB updates

## Additional Technical Details

### Browser Cache Headers

The Rust server uses ETags and cache headers for Arrow endpoints:

```rust
// /api/arrow/nodes and /api/arrow/edges use ETags
if let Some(if_none_match) = headers.get(header::IF_NONE_MATCH) {
    if client_etag == cached.nodes_etag {
        return Ok(Response::builder()
            .status(StatusCode::NOT_MODIFIED)
            .header(header::ETAG, &cached.nodes_etag)
            .body(Body::empty())
            .unwrap());
    }
}
```

However, `/api/visualize` doesn't use ETags, relying only on server-side caching.

### Frontend Caching Layers

1. **React Query Cache** - 5 minute stale time, 10 minute cache time
2. **DuckDB Service Cache** - Browser-side Arrow data caching
3. **Browser HTTP Cache** - Standard browser caching

### StatsPanel Memoization Issue

The StatsPanel was also memoized incorrectly:

```typescript
// PROBLEM: Only re-renders when isOpen changes
}, (prevProps, nextProps) => {
  return prevProps.isOpen === nextProps.isOpen;
});
```

This should check data changes too, but the root issue is backend caching.

### WebSocket Update Flow

```
1. Webhook → Python Server → Rust Server (/api/webhook/data)
2. Rust Server → DuckDB Store → process_updates()
3. process_updates() → Broadcast WebSocket → Clear Caches
4. Frontend → Receives Delta → Updates GraphCanvas
5. Frontend → StatsPanel still shows old data (from stale cache)
```

## Debugging Commands

### Check Rust Server Cache Status
```bash
curl http://localhost:4543/api/cache/stats
```

### Clear Rust Server Cache
```bash
curl -X POST http://localhost:4543/api/cache/clear
```

### Monitor WebSocket Messages
```javascript
// In browser console
const ws = new WebSocket('ws://localhost:4543/ws');
ws.onmessage = (event) => console.log('WS:', JSON.parse(event.data));
```

### Check DuckDB vs FalkorDB Counts
```bash
# DuckDB count (via Rust server)
curl "http://localhost:4543/api/arrow/nodes" | wc -c

# FalkorDB count (via /api/visualize)
curl "http://localhost:4543/api/visualize?query_type=entire_graph&limit=100000"
```

## Testing

1. Add new nodes via webhook
2. Check Rust server logs for cache clearing
3. Refresh frontend and verify StatsPanel shows correct counts
4. Monitor WebSocket delta updates in browser dev tools
5. Compare DuckDB vs FalkorDB counts using debug commands above
