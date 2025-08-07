# Performance Optimizations for Graphiti Frontend

## Current Optimizations (Already Implemented)

### 1. Server-Side (Rust)
- **Apache Arrow Format**: Binary columnar format, ~10x faster than JSON
- **Pre-rendering on Startup**: Arrow cache created at server start
- **In-Memory DuckDB**: Fast querying with indexes on key fields
- **HTTP Compression**: Gzip/Brotli via CompressionLayer
- **Result Caching**: DashMap cache for query results
- **5-second Arrow Cache**: Prevents redundant conversions

### 2. Client-Side (React)
- **Arrow Format Loading**: Using DuckDB-WASM for efficient data loading
- **React.memo**: Components wrapped to prevent unnecessary re-renders
- **useMemo/useCallback**: Expensive computations and callbacks memoized
- **Lazy Loading**: Heavy components loaded on-demand
- **Map-based Lookups**: O(1) node lookups instead of O(n) array searches

## Proposed Optimizations

### 1. Progressive Data Loading with Viewport Culling
**Impact**: High | **Effort**: Medium

```typescript
// Only render nodes visible in viewport + buffer zone
const visibleNodes = useMemo(() => {
  const viewport = cosmographRef.current?.getViewport();
  if (!viewport) return nodes;
  
  return nodes.filter(node => {
    const { x, y } = node;
    const buffer = 100; // pixels
    return x >= viewport.left - buffer &&
           x <= viewport.right + buffer &&
           y >= viewport.top - buffer &&
           y <= viewport.bottom + buffer;
  });
}, [nodes, viewportBounds]);
```

### 2. ETags for Client-Side Caching
**Impact**: Medium | **Effort**: Low

```rust
// In Rust server
let etag = format!("W/\"{}\"", hash(&data));
response.header("ETag", etag);
response.header("Cache-Control", "private, max-age=300");

// In React client
const headers = {
  'If-None-Match': localStorage.getItem('graphDataETag')
};
```

### 3. Delta Updates via WebSocket
**Impact**: High | **Effort**: High

Instead of re-fetching entire graph, send only changes:
```typescript
interface GraphDelta {
  added: { nodes: Node[], edges: Edge[] };
  updated: { nodes: Node[], edges: Edge[] };
  removed: { nodeIds: string[], edgeIds: string[] };
  timestamp: number;
}
```

### 4. Service Worker for Offline Caching
**Impact**: Medium | **Effort**: Medium

```javascript
// service-worker.js
self.addEventListener('fetch', event => {
  if (event.request.url.includes('/api/arrow/')) {
    event.respondWith(
      caches.match(event.request).then(response => {
        return response || fetch(event.request).then(response => {
          return caches.open('arrow-cache-v1').then(cache => {
            cache.put(event.request, response.clone());
            return response;
          });
        });
      })
    );
  }
});
```

### 5. Optimize Initial Render with requestIdleCallback
**Impact**: Low | **Effort**: Low

```typescript
// Defer non-critical updates
requestIdleCallback(() => {
  // Update secondary UI elements
  updateStats();
  updateFilters();
  loadPanels();
}, { timeout: 2000 });
```

### 6. Virtual Scrolling for Large Node Lists
**Impact**: Medium | **Effort**: Medium

Use react-window for control panel node lists:
```typescript
import { FixedSizeList } from 'react-window';

<FixedSizeList
  height={600}
  itemCount={nodes.length}
  itemSize={35}
  width='100%'
>
  {NodeRow}
</FixedSizeList>
```

### 7. Web Workers for Heavy Computations
**Impact**: High | **Effort**: High

Move centrality calculations and filtering to Web Workers:
```typescript
// centrality.worker.ts
self.addEventListener('message', (e) => {
  const { nodes, edges, metric } = e.data;
  const result = calculateCentrality(nodes, edges, metric);
  self.postMessage(result);
});
```

### 8. Optimistic UI Updates
**Impact**: Medium | **Effort**: Medium

Update UI immediately, reconcile with server later:
```typescript
const updateNode = (nodeId, updates) => {
  // Update local state immediately
  setNodes(prev => prev.map(n => 
    n.id === nodeId ? { ...n, ...updates } : n
  ));
  
  // Send to server in background
  api.updateNode(nodeId, updates).catch(() => {
    // Rollback on failure
    setNodes(originalNodes);
  });
};
```

## Quick Wins (Implement First)

1. **Increase Arrow Cache TTL** (5s → 30s)
   - Location: `graph-visualizer-rust/src/main.rs:1202`
   - Change: `Duration::from_secs(5)` → `Duration::from_secs(30)`

2. **Add HTTP Cache Headers**
   - Add `Cache-Control: public, max-age=300` to Arrow endpoints
   - Add `Last-Modified` headers based on data timestamp

3. **Batch DOM Updates**
   - Use `requestAnimationFrame` for coordinated updates
   - Batch state updates with `unstable_batchedUpdates`

4. **Lazy Load Timeline**
   - Only load timeline data when timeline is visible
   - Use intersection observer to detect visibility

## Monitoring

Add performance metrics:
```typescript
// Track load times
performance.mark('data-fetch-start');
await fetchData();
performance.mark('data-fetch-end');
performance.measure('data-fetch', 'data-fetch-start', 'data-fetch-end');

// Report to analytics
const measure = performance.getEntriesByName('data-fetch')[0];
console.log(`Data fetch took ${measure.duration}ms`);
```

## Testing Performance

1. Use Chrome DevTools Performance tab
2. Enable CPU throttling (4x slowdown)
3. Test with large datasets (10k+ nodes)
4. Monitor memory usage over time
5. Check for memory leaks with heap snapshots

## Expected Improvements

- Initial load: 2-3s → <1s
- Pan/zoom: 16ms → 8ms (60fps → 120fps)
- Memory usage: -30% with viewport culling
- Network usage: -80% with caching
- Subsequent loads: <100ms with Service Worker