# Medium Priority Issue #013: Inefficient Memoization

## Severity
🟡 **Medium**

## Component
`GraphCanvas.tsx` - Lines 88-99 (currentMappingData useMemo)

## Issue Description
The `currentMappingData` useMemo hook in GraphCanvas recalculates expensive size mapping operations even when the inputs haven't meaningfully changed. The memoization strategy is inefficient because it depends on object references that change frequently, causing unnecessary recomputations of expensive operations.

## Technical Details

### Current Inefficient Memoization
```typescript
// GraphCanvas.tsx - Lines 88-99
const currentMappingData = React.useMemo(() => {
  if (transformedData.nodes.length === 0) {
    return { values: [], min: 1, max: 1, range: 1 };
  }
  
  // ❌ Expensive calculations performed even when data is identical
  const values = calculateSizeValues(transformedData.nodes, config.sizeMapping);
  const min = Math.min(...values);                    // ❌ O(n) operation
  const max = Math.max(...values);                    // ❌ O(n) operation  
  const range = max - min || 1;
  
  return { values, min, max, range };
}, [transformedData.nodes, config.sizeMapping, calculateSizeValues]);
//  ^^^^^^^^^^^^^^^^^^^^ This dependency changes on every render!
```

### Problems with Current Memoization

#### 1. Dependency Array Issues
```typescript
// Problematic dependencies:
[transformedData.nodes, config.sizeMapping, calculateSizeValues]

// transformedData.nodes - New array reference on every GraphViz render
// calculateSizeValues - New function reference (useCallback dependency issues)
// config.sizeMapping - Only this should trigger recalculation
```

#### 2. Object Reference Instability
```typescript
// In GraphViz.tsx - transformedData is recreated on every render:
const transformedData = React.useMemo(() => {
  return {
    nodes: visibleNodes.map(node => ({ id: node.id, ...node })), // ← New objects
    links: data.edges.map(edge => ({ source: edge.from, ...edge })) // ← New objects
  };
}, [data, config.nodeTypeVisibility]);

// Even if the underlying data is identical, new object references cause
// currentMappingData to recalculate expensive size operations
```

#### 3. Expensive Recalculations
```typescript
// On every dependency change, these expensive operations run:
const values = calculateSizeValues(transformedData.nodes, config.sizeMapping);
// ↑ O(n) operation where n = number of nodes (potentially 1000+)

const min = Math.min(...values);    // O(n) scan through all values
const max = Math.max(...values);    // O(n) scan through all values

// For a graph with 1000 nodes, this runs 1000+ operations unnecessarily
```

#### 4. Cascade Effect
```typescript
// currentMappingData changes trigger cascading recalculations:
// 1. currentMappingData recalculates (expensive)
// 2. nodeSize function uses currentMappingData (called for every node)
// 3. Animation system detects changes (triggers animation restarts)
// 4. Cosmograph re-renders entire graph (very expensive)
```

## Root Cause Analysis

### 1. Improper Memoization Strategy
The memoization depends on object references that change frequently rather than the actual data values that matter.

### 2. Upstream Object Creation
The `transformedData.nodes` dependency is unstable because upstream components create new object references even when data is identical.

### 3. Function Reference Instability
The `calculateSizeValues` function is recreated if its dependencies change, causing memoization invalidation.

### 4. Lack of Deep Equality Checks
The memoization uses shallow reference equality instead of deep value equality for complex objects.

## Impact Assessment

### Performance Issues
```javascript
// Performance impact on typical graph:
// - 500 nodes: ~5-10ms per recalculation
// - 1000 nodes: ~10-20ms per recalculation  
// - 2000+ nodes: ~20-50ms per recalculation

// With frequent re-renders (animations, interactions):
// - 10 renders/sec = 100-500ms/sec of unnecessary computation
// - Causes frame drops during animations
// - Makes interactions feel sluggish
```

### Memory Usage
```javascript
// Each recalculation creates:
// - New values array (n numbers)
// - New currentMappingData object
// - Garbage collection pressure from old objects
```

### User Experience
- **Animation Stuttering**: Size transitions appear jerky
- **Interaction Lag**: Node interactions feel unresponsive
- **Performance Degradation**: Noticeable slowdown with larger graphs

## Scenarios Where This Manifests

### Scenario 1: Panel Collapse/Expand
```typescript
// User collapses side panel
// → GraphViz re-renders (layout change)
// → transformedData gets new object references (same data)
// → currentMappingData recalculates unnecessarily
// → All node sizes recalculated
// → Graph re-renders
```

### Scenario 2: Frequent API Refetches
```typescript
// React Query refetches data every 30 seconds
// → Even if API returns identical data
// → New object references created
// → Expensive size calculations repeated
// → Animation system restarts
```

### Scenario 3: Configuration Changes
```typescript
// User changes unrelated config (e.g., node color)
// → Config context updates
// → Components re-render
// → transformedData recreated
// → Size mapping recalculated (unnecessary)
```

## Proposed Solutions

### Solution 1: Stable Reference with Deep Equality
```typescript
import { useMemo, useRef } from 'react';
import { isEqual } from 'lodash-es';

const useMemoizedSizeData = (nodes: any[], sizeMapping: string, calculateSizeValues: Function) => {
  const prevResultRef = useRef<any>(null);
  const prevInputsRef = useRef<any>(null);
  
  return useMemo(() => {
    const currentInputs = {
      nodeIds: nodes.map(n => n.id).sort(),  // Stable identifier
      sizeMapping,
      nodeData: nodes.map(n => ({  // Extract only size-relevant data
        id: n.id,
        degree_centrality: n.properties?.degree_centrality,
        betweenness_centrality: n.properties?.betweenness_centrality,
        pagerank_centrality: n.properties?.pagerank_centrality,
        size: n.size
      }))
    };
    
    // Deep equality check to avoid unnecessary recalculations
    if (prevInputsRef.current && isEqual(currentInputs, prevInputsRef.current)) {
      return prevResultRef.current;
    }
    
    // Only recalculate if inputs actually changed
    if (nodes.length === 0) {
      const result = { values: [], min: 1, max: 1, range: 1 };
      prevResultRef.current = result;
      prevInputsRef.current = currentInputs;
      return result;
    }
    
    const values = calculateSizeValues(nodes, sizeMapping);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    
    const result = { values, min, max, range };
    prevResultRef.current = result;
    prevInputsRef.current = currentInputs;
    
    return result;
  }, [nodes, sizeMapping, calculateSizeValues]);
};

// Usage in GraphCanvas
const currentMappingData = useMemoizedSizeData(
  transformedData.nodes, 
  config.sizeMapping, 
  calculateSizeValues
);
```

### Solution 2: Hash-Based Memoization
```typescript
import { useMemo } from 'react';

const createDataHash = (nodes: any[], sizeMapping: string) => {
  // Create a stable hash of the data that matters for size calculation
  const relevantData = nodes.map(node => ({
    id: node.id,
    degree: node.properties?.degree_centrality || 0,
    betweenness: node.properties?.betweenness_centrality || 0,
    pagerank: node.properties?.pagerank_centrality || 0,
    size: node.size || 1
  }));
  
  // Simple hash function (for production, use a proper hash library)
  return JSON.stringify({ nodes: relevantData, mapping: sizeMapping });
};

const currentMappingData = useMemo(() => {
  const dataHash = createDataHash(transformedData.nodes, config.sizeMapping);
  
  // Use hash as dependency instead of object references
  if (transformedData.nodes.length === 0) {
    return { values: [], min: 1, max: 1, range: 1 };
  }
  
  const values = calculateSizeValues(transformedData.nodes, config.sizeMapping);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  
  return { values, min, max, range };
}, [createDataHash(transformedData.nodes, config.sizeMapping)]);
```

### Solution 3: Separate Caching Layer
```typescript
// src/hooks/useSizeMappingCache.ts
import { useMemo, useRef } from 'react';

interface SizeMappingCache {
  [key: string]: {
    values: number[];
    min: number;
    max: number;
    range: number;
  };
}

export const useSizeMappingCache = () => {
  const cacheRef = useRef<SizeMappingCache>({});
  
  const getSizeMapping = (nodes: any[], mapping: string, calculateFn: Function) => {
    // Create cache key from stable data
    const cacheKey = `${mapping}-${nodes.length}-${nodes.map(n => n.id).join(',')}`;
    
    if (cacheRef.current[cacheKey]) {
      return cacheRef.current[cacheKey];
    }
    
    // Calculate only if not cached
    const values = calculateFn(nodes, mapping);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    
    const result = { values, min, max, range };
    cacheRef.current[cacheKey] = result;
    
    // Cleanup old cache entries to prevent memory leaks
    const cacheKeys = Object.keys(cacheRef.current);
    if (cacheKeys.length > 10) {
      const oldestKey = cacheKeys[0];
      delete cacheRef.current[oldestKey];
    }
    
    return result;
  };
  
  return { getSizeMapping };
};

// Usage in GraphCanvas
const { getSizeMapping } = useSizeMappingCache();

const currentMappingData = useMemo(() => {
  if (transformedData.nodes.length === 0) {
    return { values: [], min: 1, max: 1, range: 1 };
  }
  
  return getSizeMapping(transformedData.nodes, config.sizeMapping, calculateSizeValues);
}, [transformedData.nodes.length, config.sizeMapping]); // Simplified dependencies
```

### Solution 4: Optimized Dependency Management
```typescript
// Fix the upstream data stability issue
const stableTransformedData = useMemo(() => {
  if (!data) return { nodes: [], links: [] };
  
  // Use stable references when possible
  const visibleNodes = data.nodes.filter(node => {
    const nodeType = node.node_type as keyof typeof config.nodeTypeVisibility;
    return config.nodeTypeVisibility[nodeType] !== false;
  });
  
  // Only create new objects if necessary (avoid unnecessary spreading)
  return {
    nodes: visibleNodes, // Use original objects if no transformation needed
    links: data.edges.filter(edge => 
      visibleNodes.some(n => n.id === edge.from) && 
      visibleNodes.some(n => n.id === edge.to)
    )
  };
}, [data, config.nodeTypeVisibility]);

// Stable calculateSizeValues function
const calculateSizeValues = useCallback((nodes: any[], mapping: string) => {
  return nodes.map(node => {
    switch (mapping) {
      case 'uniform': return 1;
      case 'degree': return node.properties?.degree_centrality || 1;
      case 'betweenness': return node.properties?.betweenness_centrality || 1;
      case 'pagerank': return node.properties?.pagerank_centrality || 1;
      default: return node.size || 1;
    }
  });
}, []); // No dependencies - pure function

// Optimized memoization with stable dependencies
const currentMappingData = useMemo(() => {
  if (stableTransformedData.nodes.length === 0) {
    return { values: [], min: 1, max: 1, range: 1 };
  }
  
  const values = calculateSizeValues(stableTransformedData.nodes, config.sizeMapping);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  
  return { values, min, max, range };
}, [stableTransformedData.nodes, config.sizeMapping]); // Stable dependencies
```

## Recommended Solution
**Solution 4 (Optimized Dependency Management)** combined with elements of **Solution 1** for maximum efficiency.

### Benefits
- **Performance**: Eliminates unnecessary recalculations
- **Stability**: Stable object references prevent cascade effects
- **Simplicity**: Clean dependency management without complex caching
- **Memory Efficiency**: No reference accumulation or memory leaks

## Implementation Plan

### Phase 1: Fix Upstream Data Stability
1. Update `transformedData` in GraphViz to use stable references
2. Make `calculateSizeValues` a stable function reference
3. Remove unnecessary object spreading

### Phase 2: Optimize Memoization Dependencies
1. Use only truly changing values as dependencies
2. Add deep equality checks where necessary
3. Test performance improvements

### Phase 3: Add Performance Monitoring
1. Add performance measuring for size calculations
2. Monitor memoization hit/miss rates
3. Verify improvements with real datasets

## Testing Strategy
1. **Performance Testing**: Measure calculation times before/after optimization
2. **Stress Testing**: Test with large graphs (1000+ nodes)
3. **Interaction Testing**: Verify smooth animations and interactions
4. **Memory Testing**: Check for memory leaks or accumulation

## Priority Justification
This is Medium Priority because:
- **Performance**: Significantly impacts rendering performance on larger graphs
- **User Experience**: Causes animation stuttering and interaction lag
- **Scalability**: Problem worsens with graph size
- **Resource Usage**: Unnecessary CPU consumption affects battery life

## Related Issues
- [Issue #006: Infinite Re-renders](../high/006-infinite-re-renders.md)
- [Issue #009: Performance Issues with Dynamic Styles](./009-performance-dynamic-styles.md)
- [Issue #004: Race Condition in Animation State](../high/004-race-condition-animation.md)

## Dependencies
- React memoization patterns
- Deep equality comparison utilities
- Performance measurement tools
- Understanding of object reference stability

## Estimated Fix Time
**2-3 hours** for optimizing memoization strategy and fixing upstream data stability issues