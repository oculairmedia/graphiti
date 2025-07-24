# High Priority Issue #005: Stale Closures in useEffect Hook

## Severity
🟠 **High**

## Component
`GraphCanvas.tsx` - Lines 102-161 (Size mapping animation useEffect)

## Issue Description
The useEffect hook for size mapping transitions captures outdated values of `transformedData.nodes` and `calculateSizeValues` in its closure. This leads to animations using stale data, incorrect calculations, and potential crashes when the component state changes during animation.

## Technical Details

### Current Implementation with Stale Closures
```typescript
// GraphCanvas.tsx - Lines 102-161
useEffect(() => {
  if (config.sizeMapping !== prevSizeMapping && transformedData.nodes.length > 0) {
    // ❌ These values are captured at useEffect creation time
    const oldValues = calculateSizeValues(transformedData.nodes, prevSizeMapping);
    const newValues = calculateSizeValues(transformedData.nodes, config.sizeMapping);
    
    const animate = (currentTime: number) => {
      // ❌ This closure captures stale transformedData.nodes
      const nodeIndex = transformedData.nodes.findIndex(n => n.id === node.id);
      
      if (progress < 1) {
        tweenTimeoutRef.current = setTimeout(() => requestAnimationFrame(animate), 33);
      }
    };
    
    requestAnimationFrame(animate);
  }
}, [config.sizeMapping, prevSizeMapping, transformedData.nodes, calculateSizeValues]);
//   ^^^^^^^^^^^^^^^^^^^^ These dependencies don't prevent stale closures
```

### Stale Closure Problems

#### 1. Captured Node Data
```typescript
// When useEffect runs, it captures current transformedData.nodes
const oldValues = calculateSizeValues(transformedData.nodes, prevSizeMapping);

// Later, if transformedData.nodes changes (new API data, filtered nodes, etc.)
// The animation still uses the OLD captured nodes array
const animate = (currentTime: number) => {
  // ❌ transformedData.nodes here is STALE - from when useEffect first ran
  const nodeIndex = transformedData.nodes.findIndex(n => n.id === node.id);
};
```

#### 2. Stale Function References
```typescript
// calculateSizeValues is captured in closure
const oldValues = calculateSizeValues(transformedData.nodes, prevSizeMapping);

// If calculateSizeValues is recreated (due to deps change), 
// animation still uses OLD version of the function
```

#### 3. State Updates with Stale Values
```typescript
setTweenState({
  isActive: true,
  oldMapping: prevSizeMapping,        // ❌ Captured at closure creation
  oldValues,                          // ❌ Calculated with stale nodes
  newValues,                          // ❌ Calculated with stale nodes
  oldRange: { min: oldMin, max: oldMax, range: oldMax - oldMin },
  newRange: { min: newMin, max: newMax, range: newMax - newMin }
});
```

## Root Cause Analysis

### 1. useEffect Dependency Array Misunderstanding
The dependency array `[config.sizeMapping, prevSizeMapping, transformedData.nodes, calculateSizeValues]` **does NOT** prevent stale closures inside the animation function. It only controls when the useEffect runs.

### 2. Long-Running Animation Closures
The `animate` function creates a long-running closure that continues to reference the initial captured values, even after the component state has changed.

### 3. Async Animation with Stale State
```typescript
// Timeline of the problem:
// T0: useEffect runs, captures nodes = [A, B, C]
// T1: Animation starts with captured nodes
// T2: New API data arrives, transformedData.nodes = [A, B, C, D, E]
// T3: Animation continues using OLD nodes [A, B, C]
// T4: Animation tries to find node D in OLD array → not found → error
```

## Scenarios Where This Fails

### Scenario 1: API Data Updates During Animation
```typescript
// Initial render: 100 nodes
useEffect(() => {
  const oldValues = calculateSizeValues(transformedData.nodes, 'uniform'); // 100 values
  
  const animate = () => {
    // API returns 150 nodes while animation runs
    // transformedData.nodes now has 150 nodes
    // But oldValues still has 100 values
    // → Array index mismatch → crash
  };
});
```

### Scenario 2: Node Filtering During Animation
```typescript
// User changes node type visibility during animation
// transformedData.nodes changes from [Entity, Agent, Community] to [Entity only]
// Animation continues with stale node references
// → Nodes that no longer exist are still being animated
```

### Scenario 3: Component Re-render with New Props
```typescript
// Parent component passes new nodes prop
// useEffect dependencies detect change and re-run
// But previous animation is still running with OLD nodes
// → Multiple animations with different node sets running simultaneously
```

## Impact Assessment

### Runtime Errors
```javascript
// Common errors from stale closures:
TypeError: Cannot read property 'id' of undefined
// → Trying to access node that no longer exists

TypeError: Cannot read property 'findIndex' of undefined  
// → transformedData.nodes is undefined in closure

RangeError: Invalid array length
// → Array length mismatch between stale and current data
```

### Visual Glitches
- **Nodes disappearing**: Animated nodes no longer in current dataset
- **Size inconsistencies**: Some nodes use old size mapping, others use new
- **Animation freezing**: Animation gets stuck when node references break

### Performance Issues
- **Multiple simultaneous animations**: Old animations don't stop when new ones start
- **Memory leaks**: Closures hold references to large old datasets
- **CPU waste**: Calculations on stale/irrelevant data

## Reproduction Steps
1. Start graph with initial dataset (e.g., 50 nodes)
2. Begin size mapping animation (uniform → degree)
3. While animation is running, trigger data refresh (new API call)
4. Observe animation glitches or console errors
5. Try rapid size mapping changes during data updates

## Proposed Solutions

### Solution 1: Use Refs for Current Values
```typescript
const transformedDataRef = useRef(transformedData);
const calculateSizeValuesRef = useRef(calculateSizeValues);

// Update refs when values change
useEffect(() => {
  transformedDataRef.current = transformedData;
}, [transformedData]);

useEffect(() => {
  calculateSizeValuesRef.current = calculateSizeValues;
}, [calculateSizeValues]);

// Animation uses current values via refs
const animate = (currentTime: number) => {
  const currentNodes = transformedDataRef.current.nodes;
  const currentCalculateSize = calculateSizeValuesRef.current;
  
  // Now always uses fresh data
};
```

### Solution 2: Abort Animation on Dependency Change
```typescript
const abortControllerRef = useRef<AbortController | null>(null);

useEffect(() => {
  // Abort previous animation
  if (abortControllerRef.current) {
    abortControllerRef.current.abort();
  }
  
  abortControllerRef.current = new AbortController();
  const { signal } = abortControllerRef.current;
  
  const animate = (currentTime: number) => {
    if (signal.aborted) return; // Stop if aborted
    
    // Animation logic
    if (progress < 1 && !signal.aborted) {
      requestAnimationFrame(animate);
    }
  };
  
  requestAnimationFrame(animate);
  
  return () => {
    abortControllerRef.current?.abort();
  };
}, [config.sizeMapping, prevSizeMapping, transformedData.nodes, calculateSizeValues]);
```

### Solution 3: Move Animation Logic Outside useEffect
```typescript
const startAnimation = useCallback((fromMapping: string, toMapping: string) => {
  // Always use current values when called
  const currentNodes = transformedData.nodes;
  const oldValues = calculateSizeValues(currentNodes, fromMapping);
  const newValues = calculateSizeValues(currentNodes, toMapping);
  
  // Animation logic here
}, [transformedData.nodes, calculateSizeValues]);

useEffect(() => {
  if (config.sizeMapping !== prevSizeMapping) {
    startAnimation(prevSizeMapping, config.sizeMapping);
  }
}, [config.sizeMapping, prevSizeMapping, startAnimation]);
```

## Recommended Solution
**Combination of Solutions 1 and 2**: Use refs for current values AND abort previous animations to prevent conflicts.

### Benefits
- **Always Fresh Data**: Animation uses current node data
- **No Stale Calculations**: Function references are always current
- **Clean Transitions**: Previous animations are properly cancelled
- **Error Prevention**: No more undefined/stale reference errors

## Testing Strategy
1. **Data Change During Animation**: Trigger API refresh mid-animation
2. **Rapid State Changes**: Quickly change multiple settings during animation
3. **Component Lifecycle**: Mount/unmount component during animations
4. **Memory Leak Testing**: Verify old closures are properly cleaned up

## Priority Justification
This is High Priority because:
- **Reliability**: Causes crashes and unpredictable behavior
- **Data Integrity**: Animations may use incorrect/outdated data
- **User Experience**: Visual glitches and freezing animations
- **Development**: Makes animation system difficult to debug and maintain

## Related Issues
- [Issue #004: Race Condition in Animation State](./004-race-condition-animation.md)
- [Issue #006: Infinite Re-renders](./006-infinite-re-renders.md)
- [Issue #001: Memory Leak in GraphCanvas](../critical/001-memory-leak-graphcanvas.md)

## Dependencies
- React useRef and useCallback patterns
- Understanding of JavaScript closures
- Component lifecycle management
- Animation cancellation patterns

## Estimated Fix Time
**2-3 hours** for implementing ref-based solution with proper cleanup