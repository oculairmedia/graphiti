# StatsPanel Real-time Update Implementation Plan

## Problem Statement

The StatsPanel shows stale node/edge counts because it receives data from `useGraphDataQuery` which fetches from `/api/visualize` (FalkorDB), while WebSocket updates only update DuckDB. This creates a data source inconsistency where:

- **StatsPanel** ← `useGraphDataQuery` ← `/api/visualize` ← **FalkorDB** (stale)
- **GraphCanvas** ← WebSocket deltas ← **DuckDB** (current)

## Solution: Real-time Count Tracking

Instead of fixing the complex cache invalidation issue, we'll implement a simpler solution where GraphCanvas (which receives live updates) tracks current counts and passes them to StatsPanel.

## Implementation Plan

### Phase 1: Add Live Stats Tracking to GraphCanvas

**File: `frontend/src/components/GraphCanvas.tsx`**

1. **Add state for live statistics:**
```typescript
// Add after existing state declarations
const [liveStats, setLiveStats] = useState<{
  nodeCount: number;
  edgeCount: number;
  lastUpdated: number;
}>({
  nodeCount: 0,
  edgeCount: 0,
  lastUpdated: Date.now()
});
```

2. **Update counts after delta processing:**
```typescript
// In processDeltaBatch function, after successful delta application
const updateLiveStats = useCallback(() => {
  if (cosmographRef.current) {
    try {
      // Get current counts from Cosmograph
      const nodeCount = cosmographRef.current.getNodes()?.length || 0;
      const edgeCount = cosmographRef.current.getLinks()?.length || 0;
      
      setLiveStats(prev => ({
        nodeCount,
        edgeCount,
        lastUpdated: Date.now()
      }));
      
      console.log('[GraphCanvas] Live stats updated:', { nodeCount, edgeCount });
    } catch (error) {
      console.warn('[GraphCanvas] Failed to get live stats:', error);
    }
  }
}, []);
```

3. **Call updateLiveStats after delta processing:**
```typescript
// At the end of processDeltaBatch function
try {
  // ... existing delta processing logic ...
  
  // Update live stats after successful processing
  updateLiveStats();
} catch (error) {
  console.error('[GraphCanvas] Error applying delta updates:', error);
}
```

4. **Update stats on initial data load:**
```typescript
// Add useEffect to update stats when initial data loads
useEffect(() => {
  if (transformedData && transformedData.nodes && transformedData.links) {
    setLiveStats({
      nodeCount: transformedData.nodes.length,
      edgeCount: transformedData.links.length,
      lastUpdated: Date.now()
    });
  }
}, [transformedData]);
```

### Phase 2: Expose Live Stats from GraphCanvas

**File: `frontend/src/types/components.ts`**

1. **Update GraphCanvasHandle interface:**
```typescript
export interface GraphCanvasHandle {
  // ... existing methods ...
  getLiveStats: () => { nodeCount: number; edgeCount: number; lastUpdated: number };
}
```

**File: `frontend/src/components/GraphCanvas.tsx`**

2. **Expose getLiveStats via imperative handle:**
```typescript
React.useImperativeHandle(ref, () => ({
  // ... existing methods ...
  getLiveStats: () => liveStats,
}), [/* ... existing deps ..., */ liveStats]);
```

### Phase 3: Pass Live Stats to StatsPanel

**File: `frontend/src/components/GraphViz.tsx`**

1. **Add state for live stats:**
```typescript
const [liveStats, setLiveStats] = useState<{
  nodeCount: number;
  edgeCount: number;
  lastUpdated: number;
} | null>(null);
```

2. **Poll live stats from GraphCanvas:**
```typescript
// Add useEffect to poll live stats
useEffect(() => {
  const interval = setInterval(() => {
    if (graphCanvasRef.current) {
      const stats = graphCanvasRef.current.getLiveStats();
      setLiveStats(stats);
    }
  }, 1000); // Update every second

  return () => clearInterval(interval);
}, []);
```

3. **Pass live stats to StatsPanel:**
```typescript
<StatsPanel 
  isOpen={showStatsPanel}
  onClose={() => setShowStatsPanel(false)}
  data={data ? {
    ...data,
    edges: data.edges || transformedData.links?.map(link => ({
      source: link.source,
      target: link.target,
      edge_type: link.edge_type || '',
      weight: link.weight || 1
    })) || []
  } : undefined}
  liveStats={liveStats} // ← Add this prop
/>
```

### Phase 4: Update StatsPanel to Use Live Stats

**File: `frontend/src/components/StatsPanel.tsx`**

1. **Update interface:**
```typescript
interface StatsPanelProps {
  isOpen: boolean;
  onClose: () => void;
  data?: GraphData;
  liveStats?: {
    nodeCount: number;
    edgeCount: number;
    lastUpdated: number;
  } | null;
}
```

2. **Modify computeGraphStats to use live stats:**
```typescript
const computeGraphStats = (
  data?: GraphData, 
  liveStats?: { nodeCount: number; edgeCount: number; lastUpdated: number } | null
): GraphStats | null => {
  console.log('[StatsPanel] Computing stats:', {
    hasData: !!data,
    hasLiveStats: !!liveStats,
    liveNodeCount: liveStats?.nodeCount,
    liveEdgeCount: liveStats?.edgeCount,
    dataNodeCount: data?.nodes?.length || 0,
    dataEdgeCount: data?.edges?.length || 0
  });
  
  if (!data || !data.nodes || !data.edges) {
    return null;
  }

  const { nodes, edges } = data;
  
  // Use live stats for counts if available and recent (within 5 seconds)
  const useLiveStats = liveStats && 
    (Date.now() - liveStats.lastUpdated) < 5000;
  
  const totalNodes = useLiveStats ? liveStats.nodeCount : nodes.length;
  const totalEdges = useLiveStats ? liveStats.edgeCount : edges.length;
  
  // ... rest of computation using totalNodes and totalEdges
};
```

3. **Update component to pass liveStats:**
```typescript
export const StatsPanel: React.FC<StatsPanelProps> = React.memo(({ 
  isOpen, 
  onClose,
  data,
  liveStats
}) => {
  // ... existing code ...
  
  const stats = React.useMemo(() => {
    const baseStats = computeGraphStats(data, liveStats);
    // ... rest of stats computation
  }, [data, liveStats, realPerformance]);
  
  // ... rest of component
});
```

4. **Update memoization comparison:**
```typescript
}, (prevProps, nextProps) => {
  // Re-render if panel visibility changes
  if (prevProps.isOpen !== nextProps.isOpen) {
    return false;
  }
  
  // Re-render if data changes
  if (prevProps.data !== nextProps.data) {
    return false;
  }
  
  // Re-render if live stats change
  if (prevProps.liveStats !== nextProps.liveStats) {
    return false;
  }
  
  // Check if live stats counts changed
  if (prevProps.liveStats && nextProps.liveStats) {
    if (prevProps.liveStats.nodeCount !== nextProps.liveStats.nodeCount ||
        prevProps.liveStats.edgeCount !== nextProps.liveStats.edgeCount) {
      return false;
    }
  }
  
  return true; // No relevant changes
});
```

## Benefits of This Approach

1. **Immediate Updates**: StatsPanel shows live counts as soon as GraphCanvas processes deltas
2. **No Cache Dependencies**: Bypasses all caching issues between FalkorDB/DuckDB
3. **Minimal Changes**: Doesn't require backend modifications
4. **Fallback Support**: Uses original data if live stats are unavailable
5. **Performance**: Only updates when counts actually change

## Testing Plan

1. **Initial Load**: Verify StatsPanel shows correct counts on page load
2. **WebSocket Updates**: Add nodes via webhook, verify counts update immediately
3. **Fallback**: Disable live stats, verify it falls back to original data
4. **Performance**: Monitor for excessive re-renders or polling overhead

## Files to Modify

1. `frontend/src/components/GraphCanvas.tsx` - Add live stats tracking
2. `frontend/src/types/components.ts` - Update interface
3. `frontend/src/components/GraphViz.tsx` - Pass live stats to StatsPanel
4. `frontend/src/components/StatsPanel.tsx` - Use live stats for counts

## Alternative: Event-Based Updates

Instead of polling, could use an event system:

```typescript
// In GraphCanvas
const onStatsUpdate = useCallback((stats) => {
  // Emit custom event
  window.dispatchEvent(new CustomEvent('graphStatsUpdate', { detail: stats }));
}, []);

// In GraphViz
useEffect(() => {
  const handleStatsUpdate = (event) => {
    setLiveStats(event.detail);
  };
  
  window.addEventListener('graphStatsUpdate', handleStatsUpdate);
  return () => window.removeEventListener('graphStatsUpdate', handleStatsUpdate);
}, []);
```

This would be more efficient than polling but adds complexity.
