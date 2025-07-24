# High Priority Issue #004: Race Condition in Animation State

## Severity
🟠 **High**

## Component
`GraphCanvas.tsx` - Lines 102-161 (Size mapping animation system)

## Issue Description
The size mapping animation system in GraphCanvas has race conditions when multiple rapid size mapping changes occur. This can cause animation state conflicts, visual glitches, and incorrect size calculations.

## Technical Details

### Current Animation Implementation
```typescript
// useEffect for handling size mapping changes
useEffect(() => {
  if (config.sizeMapping !== prevSizeMapping && transformedData.nodes.length > 0) {
    // Clear any existing animation
    if (tweenTimeoutRef.current) {
      clearTimeout(tweenTimeoutRef.current);
    }
    
    // Calculate old and new values on-demand
    const oldValues = calculateSizeValues(transformedData.nodes, prevSizeMapping);
    const newValues = calculateSizeValues(transformedData.nodes, config.sizeMapping);
    
    // Set up tween state
    setTweenState({
      isActive: true,
      oldMapping: prevSizeMapping,
      oldValues,
      newValues,
      // ... range calculations
    });
    
    // Start animation
    setTweenProgress(0);
    
    const animate = (currentTime: number) => {
      // Animation logic with setTimeout + requestAnimationFrame
      if (progress < 1) {
        tweenTimeoutRef.current = setTimeout(() => requestAnimationFrame(animate), 33);
      } else {
        setTweenState(prev => ({ ...prev, isActive: false }));
        setPrevSizeMapping(config.sizeMapping);
      }
    };
    
    requestAnimationFrame(animate);
  }
}, [config.sizeMapping, prevSizeMapping, transformedData.nodes, calculateSizeValues]);
```

### Race Condition Scenarios

#### 1. Rapid Size Mapping Changes
**Scenario**: User rapidly changes size mapping (uniform → degree → betweenness → pagerank)
**Problem**: 
- Multiple animations start simultaneously
- `tweenState` gets overwritten before previous animations complete
- Visual glitches as size values jump between different mappings
- Final size mapping may not match the selected option

#### 2. Component Re-render During Animation
**Scenario**: Parent component re-renders while animation is in progress
**Problem**:
- `transformedData.nodes` changes mid-animation
- Old animation references stale node data
- New animation starts with different node set
- Size calculations become invalid

#### 3. Cleanup Race Condition
**Scenario**: Animation cleanup occurs while new animation is starting
**Problem**:
- `clearTimeout` is called but animation continues via `requestAnimationFrame`
- State updates occur after cleanup
- Memory leak from orphaned animation frames

## Root Cause Analysis

### 1. Multiple Animation Sources
```typescript
// Problem: No coordination between multiple animations
// Animation 1 (uniform → degree): Still running
// Animation 2 (degree → betweenness): Starts and overwrites tweenState
// Animation 3 (betweenness → pagerank): Starts before Animation 2 completes
```

### 2. State Mutation During Animation
```typescript
// Problem: tweenState is directly mutated
setTweenState({
  isActive: true,
  oldValues,     // ← Can be from different node set
  newValues,     // ← Can be from different mapping
  // ... other values may be inconsistent
});
```

### 3. Asynchronous Animation Control
```typescript
// Problem: Animation control is split across multiple async operations
setTimeout(() => requestAnimationFrame(animate), 33);  // Async chain
setTweenProgress(easedProgress);                       // State update
setTweenState(prev => ({ ...prev, isActive: false })); // Another state update
```

## Observed Issues

### Visual Symptoms
1. **Size Jumping**: Nodes suddenly jump to different sizes mid-animation
2. **Animation Stuttering**: Animations appear to restart or freeze
3. **Incorrect Final Sizes**: Final node sizes don't match selected mapping
4. **Performance Degradation**: Multiple simultaneous animations consume CPU

### Console Warnings
```
Warning: Cannot update a component that is being unmounted
Switching from degree to betweenness
Switching from betweenness to pagerank  // ← Rapid changes
Switching from pagerank to uniform
```

## Impact Assessment
- **User Experience**: Jarring visual glitches during size mapping changes
- **Performance**: Multiple simultaneous animations impact rendering performance
- **Reliability**: Unpredictable final state after rapid interactions
- **Debugging**: Difficult to reproduce and debug timing-dependent issues

## Reproduction Steps
1. Open graph visualization with many nodes
2. Rapidly change size mapping options (click multiple options quickly)
3. Observe node size animations stuttering or jumping
4. Notice final sizes may not match selected mapping

## Proposed Solutions

### Solution 1: Animation Queue System
```typescript
const animationQueueRef = useRef<string[]>([]);
const currentAnimationRef = useRef<string | null>(null);

const queueAnimation = (newMapping: string) => {
  animationQueueRef.current.push(newMapping);
  processAnimationQueue();
};

const processAnimationQueue = () => {
  if (currentAnimationRef.current || animationQueueRef.current.length === 0) {
    return; // Animation in progress or queue empty
  }
  
  const nextMapping = animationQueueRef.current.shift();
  startAnimation(nextMapping);
};
```

### Solution 2: Animation Cancellation with Cleanup
```typescript
const animationIdRef = useRef<number | null>(null);
const cancelCurrentAnimation = () => {
  if (animationIdRef.current) {
    cancelAnimationFrame(animationIdRef.current);
    animationIdRef.current = null;
  }
  if (tweenTimeoutRef.current) {
    clearTimeout(tweenTimeoutRef.current);
    tweenTimeoutRef.current = null;
  }
};

const startAnimation = (targetMapping: string) => {
  cancelCurrentAnimation(); // Cancel any existing animation
  
  // Start new animation with proper cleanup
  const animate = (currentTime: number) => {
    // Animation logic
    if (progress < 1) {
      animationIdRef.current = requestAnimationFrame(animate);
    } else {
      // Animation complete
      currentAnimationRef.current = null;
      processAnimationQueue(); // Process next queued animation
    }
  };
  
  animationIdRef.current = requestAnimationFrame(animate);
};
```

### Solution 3: Debounced Animation with Final Target
```typescript
const debouncedAnimateRef = useRef<NodeJS.Timeout | null>(null);

useEffect(() => {
  if (debouncedAnimateRef.current) {
    clearTimeout(debouncedAnimateRef.current);
  }
  
  // Debounce rapid changes - only animate to final target
  debouncedAnimateRef.current = setTimeout(() => {
    if (config.sizeMapping !== prevSizeMapping) {
      startAnimation(config.sizeMapping);
    }
  }, 100); // 100ms debounce
  
  return () => {
    if (debouncedAnimateRef.current) {
      clearTimeout(debouncedAnimateRef.current);
    }
  };
}, [config.sizeMapping]);
```

## Recommended Solution
**Combination Approach**: Use debounced animation (Solution 3) for rapid changes, with proper cancellation (Solution 2) for immediate responsiveness.

### Benefits
- **Eliminates Race Conditions**: Only one animation runs at a time
- **Improved Performance**: Avoids unnecessary intermediate animations
- **Better UX**: Smooth animations that complete properly
- **Predictable State**: Final state always matches user selection

## Testing Strategy
1. **Rapid Interaction Testing**: Automated rapid size mapping changes
2. **Performance Monitoring**: CPU usage during animations
3. **Visual Regression Testing**: Screenshots of animation states
4. **Edge Case Testing**: Animation during component unmounting

## Priority Justification
This is High Priority because:
- **Visual Quality**: Directly affects user experience with animations
- **Performance Impact**: Multiple animations can cause performance issues
- **Reliability**: Unpredictable behavior in core functionality
- **User Frustration**: Glitchy animations feel broken to users

## Related Issues
- [Issue #001: Memory Leak in GraphCanvas](../critical/001-memory-leak-graphcanvas.md)
- [Issue #006: Infinite Re-renders](./006-infinite-re-renders.md)
- [Issue #009: Performance Issues with Dynamic Styles](../medium/009-performance-dynamic-styles.md)

## Dependencies
- React animation patterns
- requestAnimationFrame management
- Component lifecycle understanding

## Estimated Fix Time
**3-4 hours** including implementation and testing of debounced animation system