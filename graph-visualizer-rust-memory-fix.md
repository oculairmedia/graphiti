# Memory Leak Fix for Graphiti Rust Visualizer

## Issues Identified

### 1. DeltaTracker Memory Bloat
**Location**: `src/delta_tracker.rs`
**Problem**: Stores complete graph state in memory (HashMap of all nodes/edges)
```rust
current_nodes: Arc<RwLock<HashMap<String, Node>>>,  // 23,748 nodes
current_edges: Arc<RwLock<HashMap<(String, String), Edge>>>,  // 69,290 edges
delta_history: Arc<RwLock<VecDeque<GraphDelta>>>,  // 100 deltas × full graph = massive
```

**Memory Impact**: 
- 23,748 nodes × ~2KB each = ~47MB
- 69,290 edges × ~500B each = ~35MB
- 100 deltas × (47MB + 35MB) = **8.2GB potential**

### 2. Unbounded DashMap Cache
**Location**: `src/main.rs:42`
```rust
graph_cache: Arc<DashMap<String, GraphData>>,
```
**Problem**: Never expires, accumulates query results indefinitely

### 3. Background Monitoring Clone Loop
**Location**: `src/main.rs:566-584`
```rust
// Clones ENTIRE graph every 5 seconds when changes detected
if let Ok(graph_data) = execute_graph_query(&client_clone, &graph_name_clone, &query).await {
    // Reload DuckDB with fresh data
    store_clone.load_initial_data(graph_data.nodes.clone(), graph_data.edges.clone())
}
```

### 4. No Memory Limits on DuckDB
**Location**: `src/duckdb_store.rs`
**Problem**: In-memory DuckDB with no size constraints

## Solutions

### Solution 1: Add Memory Limits to Docker Compose
```yaml
graph-visualizer-rust:
  deploy:
    resources:
      limits:
        memory: 2G  # Hard limit
      reservations:
        memory: 512M  # Soft limit
```

### Solution 2: Implement Delta History Cap
**Edit**: `src/delta_tracker.rs:44`
```rust
max_history_size: 10, // Reduce from 100 to 10 deltas
```

### Solution 3: Add Cache TTL and Size Limit
**Add to**: `src/main.rs`
```rust
use std::time::Duration;

// Replace DashMap with LRU cache
use lru::LruCache;

pub struct AppState {
    // ... existing fields ...
    graph_cache: Arc<RwLock<LruCache<String, GraphData>>>,  // LRU with 100 entry limit
}

// In main():
graph_cache: Arc::new(RwLock::new(LruCache::new(NonZeroUsize::new(100).unwrap()))),
```

### Solution 4: Optimize DeltaTracker (Recommended)
**Replace HashMap storage with lightweight metadata**:

```rust
// BEFORE: Stores full nodes/edges
current_nodes: Arc<RwLock<HashMap<String, Node>>>,

// AFTER: Store only IDs and checksums
current_node_ids: Arc<RwLock<HashSet<String>>>,
current_edge_keys: Arc<RwLock<HashSet<(String, String)>>>,
```

### Solution 5: Add Periodic Cleanup Task
```rust
// In main.rs, add cleanup task
tokio::spawn(async move {
    let mut interval = tokio::time::interval(Duration::from_secs(300)); // 5 minutes
    loop {
        interval.tick().await;
        
        // Clear old cache entries
        state.graph_cache.clear();
        
        // Clear arrow cache
        let mut arrow_cache = state.arrow_cache.write().await;
        *arrow_cache = None;
        
        info!("Memory cleanup: cleared caches");
    }
});
```

### Solution 6: Disable Delta History Completely (Quick Fix)
```rust
// src/delta_tracker.rs:44
max_history_size: 0, // Disable history completely
```

## Immediate Quick Fix (No Code Changes)

1. **Restart container periodically** via cron:
```bash
0 */6 * * * docker restart graphiti-graph-visualizer-rust-1
```

2. **Add memory limit to docker-compose.yml**:
```yaml
graph-visualizer-rust:
  deploy:
    resources:
      limits:
        memory: 2G
  restart: on-failure
```

3. **Reduce cache TTL** in environment:
```yaml
environment:
  - CACHE_TTL_SECONDS=60  # From 300 to 60
  - CACHE_STRATEGY=disabled  # Disable caching entirely
```

## Recommended Action Plan

1. **Immediate** (no rebuild): Set memory limit + restart schedule
2. **Short-term** (quick rebuild): Reduce delta history to 10, disable caching
3. **Long-term** (proper fix): Replace DeltaTracker HashMap with lightweight metadata

## Verification

After applying fixes:
```bash
# Monitor memory over time
docker stats graphiti-graph-visualizer-rust-1

# Check memory usage
docker inspect graphiti-graph-visualizer-rust-1 --format '{{.HostConfig.Memory}}'
```
