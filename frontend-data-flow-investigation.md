# Frontend Data Flow Investigation

## Issue
User reports that after refreshing the frontend, they still see the old node count despite the backend API showing the correct updated count (3773 nodes).

## Data Flow Architecture

The frontend has a complex multi-layered data fetching system with multiple sources and caching layers:

### 1. Main Components
- **GraphViz.tsx** - Main visualization component
- **GraphNavBar.tsx** - Displays node count: `totalNodes={data?.nodes.length || 0}`
- **useGraphDataQuery.ts** - Primary data fetching hook

### 2. Data Sources (in priority order)
1. **DuckDB Data** (preferred) - Arrow format from `/api/arrow/nodes` and `/api/arrow/edges`
2. **JSON Data** (fallback) - From `/api/visualize?query_type=entire_graph&limit=100000`
3. **WebSocket Updates** - Real-time delta updates

### 3. Data Flow Chain

```
useGraphDataQuery.ts
├── duckDBData (from DuckDB service)
├── jsonData (from React Query + GraphClient)
└── WebSocket real-time updates
    └── useRealtimeDataSync
        └── RustWebSocketProvider
```

## Root Cause Analysis

### Problem 1: React Query Caching
- React Query uses `queryKey: ['graphData']` with no cache invalidation
- When new nodes are added, the cache isn't invalidated
- Frontend continues to serve stale cached data

### Problem 2: DuckDB Data Refresh
- DuckDB service fetches from `/api/arrow/nodes` and `/api/arrow/edges`
- Uses cache-busting with timestamps but may not be triggered properly
- `refreshDuckDBData()` function exists but may not be called

### Problem 3: WebSocket Notification Chain
- WebSocket receives delta updates via `RustWebSocketProvider`
- Should trigger `useRealtimeDataSync` → `refreshDuckDBData()`
- Chain may be broken or not properly connected

## Key Code Locations

### Data Fetching
- `frontend/src/hooks/useGraphDataQuery.ts:85-102` - React Query setup
- `frontend/src/api/graphClient.ts:89-102` - API endpoint calls
- `frontend/src/services/duckdb-service.ts:108-136` - Arrow data fetching

### WebSocket Updates
- `frontend/src/contexts/RustWebSocketProvider.tsx:88-105` - WebSocket connection
- `frontend/src/hooks/useRealtimeDataSync.ts:74-94` - Update handling
- `frontend/src/hooks/useGraphDataQuery.ts:318-322` - Refresh trigger

### Display Components
- `frontend/src/components/GraphViz.tsx:349` - Node count display
- `frontend/src/components/GraphNavBar.tsx:61` - Virtualization badge
- `frontend/src/components/GraphOverlays.tsx:40` - Live count overlay

## API Endpoints Used by Frontend

### Primary Data Endpoints
- `GET /api/visualize?query_type=entire_graph&limit=100000` - JSON format
- `GET /api/arrow/nodes` - Arrow format (binary)
- `GET /api/arrow/edges` - Arrow format (binary)

### Cache Management
- `POST /api/arrow/refresh` - Refresh Arrow cache
- `POST /api/cache/clear` - Clear all caches

### WebSocket
- `GET /ws` - WebSocket connection for real-time updates
- Subscription message: `{"type": "subscribe:deltas"}`

## Debugging Steps

### 1. Check WebSocket Connection
```javascript
// In browser console
console.log('WebSocket connected:', window.rustWebSocket?.isConnected);
```

### 2. Force Cache Invalidation
```bash
curl -X POST http://localhost:3000/api/cache/clear
curl -X POST http://localhost:3000/api/arrow/refresh
```

### 3. Check Data Sources
```bash
# Check JSON API
curl -s "http://localhost:3000/api/visualize?query_type=entire_graph&limit=100000" | jq '.data.nodes | length'

# Check stats API
curl -s "http://localhost:3000/api/stats" | jq '.total_nodes'
```

### 4. React Query DevTools
- Check if `['graphData']` query is stale
- Force refetch from DevTools

## Potential Solutions

### 1. Immediate Fix - Force Refresh
```javascript
// In useGraphDataQuery.ts, add cache invalidation
const queryClient = useQueryClient();
const invalidateCache = () => {
  queryClient.invalidateQueries(['graphData']);
};
```

### 2. WebSocket Fix - Ensure Proper Triggering
```javascript
// In useRealtimeDataSync.ts, ensure refresh is called
const handleDataUpdate = useCallback(() => {
  logger.log('[useRealtimeDataSync] Real-time update triggered, refreshing data');
  queryClient.invalidateQueries(['graphData']); // Add this
  refreshDuckDBData();
}, [refreshDuckDBData, queryClient]);
```

### 3. DuckDB Service Fix - Better Cache Busting
```javascript
// In duckdb-service.ts, add more aggressive cache busting
const cacheBuster = `?t=${Date.now()}&r=${Math.random()}`;
```

## Next Steps

1. **Test WebSocket connectivity** - Verify real-time updates are being received
2. **Add React Query invalidation** - Ensure cache is cleared on updates
3. **Implement proper error handling** - Better fallback when data sources fail
4. **Add debugging logs** - Track data flow through the entire chain
5. **Consider simplifying architecture** - Reduce complexity of multi-source data fetching

## Files to Modify

1. `frontend/src/hooks/useGraphDataQuery.ts` - Add cache invalidation
2. `frontend/src/hooks/useRealtimeDataSync.ts` - Ensure proper refresh triggering
3. `frontend/src/services/duckdb-service.ts` - Improve cache busting
4. `frontend/src/contexts/RustWebSocketProvider.tsx` - Add connection debugging
