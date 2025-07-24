# High Priority Issue #006: Infinite Re-renders Due to Inline Object Creation

## Severity
🟠 **High**

## Component
`GraphViz.tsx` - Lines 49-73 (transformedData useMemo)

## Issue Description
The `transformedData` useMemo in GraphViz creates new objects inline on every recalculation, which can cause infinite re-renders or unnecessary re-computations. The issue stems from object spread operations and map functions that create new object references even when the underlying data hasn't changed.

## Technical Details

### Current Implementation with Re-render Issues
```typescript
// GraphViz.tsx - Lines 49-73
const transformedData = React.useMemo(() => {
  if (!data) return { nodes: [], links: [] };
  
  // Filter nodes based on visibility settings
  const visibleNodes = data.nodes.filter(node => {
    const nodeType = node.node_type as keyof typeof config.nodeTypeVisibility;
    return config.nodeTypeVisibility[nodeType] !== false;
  });
  
  const visibleNodeIds = new Set(visibleNodes.map(n => n.id));
  
  return {
    // ❌ Problem 1: Always creates new objects even if node data unchanged
    nodes: visibleNodes.map(node => ({
      id: node.id,
      ...node,  // ← Creates new object reference every time
    })),
    // ❌ Problem 2: Creates new objects for links even when unchanged
    links: data.edges
      .filter(edge => visibleNodeIds.has(edge.from) && visibleNodeIds.has(edge.to))
      .map(edge => ({
        source: edge.from,
        target: edge.to,
        ...edge,  // ← Creates new object reference every time
      })),
  };
}, [data, config.nodeTypeVisibility]);
```

### Why This Causes Re-renders

#### 1. Object Reference Inequality
```typescript
// Even if the underlying data is identical, these create new objects:
const node1 = { id: 'A', ...existingNode }; // New object reference
const node2 = { id: 'A', ...existingNode }; // Different object reference

// React sees node1 !== node2 and triggers re-render
```

#### 2. Dependency Chain Reactions
```typescript
// GraphViz.tsx → transformedData changes (new object references)
// ↓
// GraphCanvas.tsx → props change, component re-renders
// ↓
// Cosmograph → new nodes/links props, entire graph re-renders
// ↓
// Animation calculations re-run, tweening restarts
// ↓ 
// Performance degrades, animations stutter
```

#### 3. Cascading useMemo Invalidations
```typescript
// In GraphCanvas.tsx - this depends on transformedData
const currentMappingData = React.useMemo(() => {
  // When transformedData changes (even with same data), this recalculates
  const values = calculateSizeValues(transformedData.nodes, config.sizeMapping);
  return { values, min, max, range };
}, [transformedData.nodes, config.sizeMapping, calculateSizeValues]);
//   ^^^^^^^^^^^^^^^^^^^^ This dependency changes on every transformedData update
```

## Root Cause Analysis

### 1. Unnecessary Object Spread Operations
```typescript
// Current problematic pattern:
nodes: visibleNodes.map(node => ({
  id: node.id,
  ...node,  // This spread is unnecessary - could return node directly
}))

// The spread operation creates a new object even when not needed
```

### 2. Redundant Data Transformation
```typescript
// Links transformation adds fields that may already exist:
links: data.edges.map(edge => ({
  source: edge.from,
  target: edge.to,
  ...edge,  // edge might already have source/target properties
}))
```

### 3. Filter Operations Creating New Arrays
```typescript
// These operations always create new arrays:
const visibleNodes = data.nodes.filter(...);
const filteredEdges = data.edges.filter(...);

// Even if filter result is identical, new array reference is created
```

## Impact Assessment

### Performance Issues
- **Unnecessary Re-renders**: Components re-render even when data hasn't changed
- **Animation Stuttering**: Size mapping animations restart due to data changes
- **CPU Waste**: Expensive graph calculations re-run unnecessarily
- **Memory Churn**: Constant object creation increases garbage collection

### User Experience
- **Visual Glitches**: Graph "flickers" during re-renders
- **Interaction Lag**: User actions delayed by unnecessary computations
- **Animation Interruption**: Smooth animations get interrupted and restart

### Development Issues
- **Debugging Difficulty**: Hard to identify why components keep re-rendering
- **Performance Profiling**: Makes performance optimization difficult
- **State Management**: Unpredictable when state updates occur

## Scenarios Where This Manifests

### Scenario 1: Config Changes
```typescript
// User changes any config value (e.g., node color, link width)
// → transformedData recalculates with identical data but new object references
// → GraphCanvas re-renders → Cosmograph re-renders → animations restart
```

### Scenario 2: Data Refetch
```typescript
// React Query refetches data every 30 seconds (line 45)
// Even if API returns identical data:
// → transformedData creates new objects → entire graph re-renders
```

### Scenario 3: Panel Collapse/Expand
```typescript
// User collapses/expands side panels
// → Parent re-renders → transformedData recalculates
// → Graph re-renders despite panels being unrelated to graph data
```

## Proposed Solutions

### Solution 1: Conditional Object Creation
```typescript
const transformedData = React.useMemo(() => {
  if (!data) return { nodes: [], links: [] };
  
  const visibleNodes = data.nodes.filter(node => {
    const nodeType = node.node_type as keyof typeof config.nodeTypeVisibility;
    return config.nodeTypeVisibility[nodeType] !== false;
  });
  
  const visibleNodeIds = new Set(visibleNodes.map(n => n.id));
  
  return {
    // Only transform if necessary
    nodes: visibleNodes.map(node => {
      // Only create new object if we need to add/modify properties
      if (node.source || node.target) {
        return node; // Return original if already has required properties
      }
      return { ...node }; // Only spread if needed
    }),
    
    links: data.edges
      .filter(edge => visibleNodeIds.has(edge.from) && visibleNodeIds.has(edge.to))
      .map(edge => {
        // Check if edge already has source/target
        if (edge.source === edge.from && edge.target === edge.to) {
          return edge; // Return original
        }
        return {
          ...edge,
          source: edge.from,
          target: edge.to,
        };
      }),
  };
}, [data, config.nodeTypeVisibility]);
```

### Solution 2: Separate Filtering and Transformation
```typescript
// Split into two separate memos for better caching
const filteredData = React.useMemo(() => {
  if (!data) return { nodes: [], edges: [] };
  
  const visibleNodes = data.nodes.filter(node => {
    const nodeType = node.node_type as keyof typeof config.nodeTypeVisibility;
    return config.nodeTypeVisibility[nodeType] !== false;
  });
  
  const visibleNodeIds = new Set(visibleNodes.map(n => n.id));
  const filteredEdges = data.edges.filter(edge => 
    visibleNodeIds.has(edge.from) && visibleNodeIds.has(edge.to)
  );
  
  return { nodes: visibleNodes, edges: filteredEdges };
}, [data, config.nodeTypeVisibility]);

const transformedData = React.useMemo(() => {
  return {
    nodes: filteredData.nodes, // No transformation needed
    links: filteredData.edges.map(edge => ({
      ...edge,
      source: edge.from,
      target: edge.to,
    })),
  };
}, [filteredData]);
```

### Solution 3: Object Reference Equality Check
```typescript
const previousTransformedDataRef = useRef(null);

const transformedData = React.useMemo(() => {
  const newData = {
    nodes: visibleNodes.map(node => ({ id: node.id, ...node })),
    links: data.edges.map(edge => ({ source: edge.from, target: edge.to, ...edge })),
  };
  
  // Deep equality check to avoid unnecessary reference changes
  if (previousTransformedDataRef.current && 
      deepEqual(newData, previousTransformedDataRef.current)) {
    return previousTransformedDataRef.current; // Return same reference
  }
  
  previousTransformedDataRef.current = newData;
  return newData;
}, [data, config.nodeTypeVisibility]);
```

### Solution 4: Memoized Transformation Functions
```typescript
const transformNode = useCallback((node) => {
  // Return original node if no transformation needed
  return node;
}, []);

const transformEdge = useCallback((edge) => ({
  ...edge,
  source: edge.from,
  target: edge.to,
}), []);

const transformedData = React.useMemo(() => {
  if (!data) return { nodes: [], links: [] };
  
  const visibleNodes = data.nodes.filter(node => {
    const nodeType = node.node_type as keyof typeof config.nodeTypeVisibility;
    return config.nodeTypeVisibility[nodeType] !== false;
  });
  
  const visibleNodeIds = new Set(visibleNodes.map(n => n.id));
  
  return {
    nodes: visibleNodes.map(transformNode),
    links: data.edges
      .filter(edge => visibleNodeIds.has(edge.from) && visibleNodeIds.has(edge.to))
      .map(transformEdge),
  };
}, [data, config.nodeTypeVisibility, transformNode, transformEdge]);
```

## Recommended Solution
**Solution 2 (Separate Filtering and Transformation)** combined with **Solution 1 (Conditional Object Creation)** for optimal performance and clarity.

### Benefits
- **Reduces Re-renders**: Only recalculates when data actually changes
- **Better Performance**: Avoids unnecessary object creation
- **Clearer Dependencies**: Separate concerns for filtering vs transformation
- **Animation Stability**: Prevents animation restarts from data updates

## Testing Strategy
1. **Re-render Counting**: Use React DevTools Profiler to count re-renders
2. **Performance Monitoring**: Measure CPU usage during config changes
3. **Memory Profiling**: Check for object creation/garbage collection
4. **Visual Testing**: Verify animations don't restart unnecessarily

## Performance Impact Measurement
```typescript
// Add performance measuring:
const renderCount = useRef(0);
useEffect(() => {
  renderCount.current++;
  console.log(`GraphViz render count: ${renderCount.current}`);
});

// Monitor transformedData changes:
useEffect(() => {
  console.log('transformedData changed', { 
    nodeCount: transformedData.nodes.length,
    linkCount: transformedData.links.length 
  });
}, [transformedData]);
```

## Priority Justification
This is High Priority because:
- **Performance**: Directly impacts rendering performance and user experience
- **Animation Quality**: Causes visual glitches and interrupted animations
- **Scalability**: Problem worsens with larger datasets
- **Development**: Makes the app difficult to optimize and debug

## Related Issues
- [Issue #004: Race Condition in Animation State](./004-race-condition-animation.md)
- [Issue #005: Stale Closures in useEffect](./005-stale-closures-useeffect.md)
- [Issue #009: Performance Issues with Dynamic Styles](../medium/009-performance-dynamic-styles.md)

## Dependencies
- React useMemo optimization patterns
- Object reference equality understanding
- Performance profiling tools
- Deep equality comparison library (optional)

## Estimated Fix Time
**2-3 hours** for implementing optimized data transformation with proper memoization