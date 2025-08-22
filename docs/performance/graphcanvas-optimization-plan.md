# GraphCanvas Data Management Optimization Plan

## Current Problem: Multiple Redundant Data Copies

The GraphCanvas component currently maintains 5+ redundant data structures that create unnecessary memory overhead:

1. **currentNodes/currentLinks state** - Tracks current data for incremental updates
2. **cosmographData state** - Processed data for Cosmograph component  
3. **memoizedNodes/memoizedLinks** - Memoized transformations of props
4. **transformedData** - Legacy compatibility layer
5. **transformedDataNodeMap** - Map for O(1) node lookups

## Optimization Strategy: Single Source of Truth with Derived Views

### Phase 1: Consolidate Core Data State

**Goal**: Replace multiple state variables with a single authoritative data store

```typescript
// BEFORE: Multiple states
const [currentNodes, setCurrentNodes] = useState<GraphNode[]>([]);
const [currentLinks, setCurrentLinks] = useState<GraphLink[]>([]);
const [cosmographData, setCosmographData] = useState<{nodes: any[], links: any[]}>();

// AFTER: Single source of truth
const [graphData, setGraphData] = useState<{
  nodes: GraphNode[];
  links: GraphLink[];
  transformedNodes?: TransformedNode[];
  transformedLinks?: TransformedLink[];
  nodeMap?: Map<string, GraphNode>;
  linkMap?: Map<string, GraphLink>;
}>({ nodes: [], links: [] });
```

### Phase 2: Lazy Computed Properties with Refs

**Goal**: Replace useMemo with ref-based caching to avoid re-computation triggers

```typescript
// Use refs for expensive computations that don't need to trigger re-renders
const transformedDataRef = useRef<{
  nodes: TransformedNode[];
  links: TransformedLink[];
  nodeMap: Map<string, GraphNode>;
  version: number;
} | null>(null);

const getTransformedData = useCallback(() => {
  const currentVersion = graphData.nodes.length + graphData.links.length;
  
  if (!transformedDataRef.current || transformedDataRef.current.version !== currentVersion) {
    // Only recompute when data actually changes
    transformedDataRef.current = {
      nodes: transformNodes(graphData.nodes),
      links: transformLinks(graphData.links),
      nodeMap: createNodeMap(graphData.nodes),
      version: currentVersion
    };
  }
  
  return transformedDataRef.current;
}, [graphData]);
```

### Phase 3: Optimized Data Flow Architecture

**New Data Flow**:
```
Props (nodes/links) 
  ↓
Single graphData state
  ↓
Lazy computed refs (only when accessed)
  ↓
Direct Cosmograph data (pointsData/linksData)
```

### Phase 4: Implementation Steps

#### Step 1: Create Unified Data Manager Hook
```typescript
// hooks/useOptimizedGraphData.ts
export function useOptimizedGraphData(nodes: GraphNode[], links: GraphLink[]) {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const computedDataRef = useRef(null);
  
  // Update only when props actually change (deep comparison)
  useEffect(() => {
    if (!isEqual(graphData.nodes, nodes) || !isEqual(graphData.links, links)) {
      setGraphData({ nodes, links });
      computedDataRef.current = null; // Invalidate cache
    }
  }, [nodes, links]);
  
  const getCosmographData = useCallback(() => {
    if (!computedDataRef.current) {
      computedDataRef.current = {
        pointsData: transformNodes(graphData.nodes),
        linksData: transformLinks(graphData.links),
        nodeMap: createNodeMap(graphData.nodes)
      };
    }
    return computedDataRef.current;
  }, [graphData]);
  
  return { graphData, getCosmographData };
}
```

#### Step 2: Replace State Variables in GraphCanvas
- Remove `currentNodes`, `currentLinks`, `cosmographData` states
- Remove `memoizedNodes`, `memoizedLinks`, `transformedData` useMemo calls
- Replace with single `useOptimizedGraphData` hook

#### Step 3: Update Cosmograph Integration
```typescript
// Instead of multiple data sources
const pointsData = useDuckDBTables ? duckDBData?.points : cosmographData.nodes;
const linksData = useDuckDBTables ? duckDBData?.links : cosmographData.links;

// Use single computed source
const { pointsData, linksData } = getCosmographData();
```

#### Step 4: Optimize Incremental Updates
```typescript
// Use direct data mutations with invalidation
const updateNodes = useCallback((updatedNodes: GraphNode[]) => {
  setGraphData(prev => ({ ...prev, nodes: updatedNodes }));
  computedDataRef.current = null; // Invalidate cache
}, []);
```

### Phase 5: Memory Benefits

**Before Optimization**:
- 5 copies of node data (currentNodes, memoizedNodes, cosmographData.nodes, transformedData.nodes, transformedDataNodeMap)
- 4 copies of link data (currentLinks, memoizedLinks, cosmographData.links, transformedData.links)
- Multiple useMemo dependencies causing unnecessary re-computations

**After Optimization**:
- 1 authoritative copy of raw data (graphData)
- 1 cached copy of transformed data (computedDataRef)
- Lazy computation only when data changes or is accessed
- ~60-80% reduction in memory usage for large graphs

### Phase 6: Performance Improvements

1. **Reduced Re-renders**: Fewer state changes = fewer component re-renders
2. **Lazy Computation**: Expensive transformations only run when needed
3. **Cache Invalidation**: Smart invalidation based on data version
4. **Memory Pressure**: Significant reduction in memory footprint

### Phase 7: Backward Compatibility

Maintain existing API surface:
```typescript
// Legacy methods still work but use optimized internals
const transformedDataNodeMap = useMemo(() => {
  return getCosmographData().nodeMap;
}, [getCosmographData]);
```

### Phase 8: Testing Strategy

1. **Unit Tests**: Verify data transformations produce identical results
2. **Performance Tests**: Measure memory usage before/after
3. **Integration Tests**: Ensure Cosmograph still receives correct data
4. **Memory Leak Tests**: Verify no new memory leaks introduced

### Phase 9: Rollout Plan

1. **Week 1**: Implement `useOptimizedGraphData` hook
2. **Week 2**: Replace state variables in GraphCanvas
3. **Week 3**: Update incremental update methods
4. **Week 4**: Performance testing and optimization
5. **Week 5**: Production deployment with monitoring

## Expected Outcomes

- **Memory Usage**: 60-80% reduction in data copies
- **Performance**: Faster initial renders and updates
- **Maintainability**: Simpler data flow, easier to debug
- **Scalability**: Better handling of large graphs (10k+ nodes)

## Risk Mitigation

- Feature flag for gradual rollout
- Comprehensive test coverage
- Performance monitoring in production
- Rollback plan if issues arise
