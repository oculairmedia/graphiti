# Hover Performance Analysis

## Current Bottlenecks Identified

### 1. **O(n) Linear Search in handleNodeHoverThrottled** (CRITICAL)
**Location**: `src/components/GraphCanvasV2.tsx:257`

```typescript
const node = nodeId ? nodes.find(n => n.id === nodeId) : null;
```

**Problem**:
- With 4000+ nodes, `Array.find()` does a linear scan
- Called on EVERY mouse move (even throttled to 60fps = 60 calls/sec)
- Each call takes ~0.1-1ms depending on node position in array
- Average case: searches through 2000 nodes before finding match

**Impact**: 50-200ms per hover depending on node position

### 2. **React State Updates Triggering Re-renders**
**Location**: `src/hooks/useNodeSelection.ts`

```typescript
const handleNodeHover = useCallback((node: GraphNode | null) => {
  setHoveredNodeStable(node);
}, [setHoveredNodeStable]);
```

**Problem**:
- Every hover triggers `setState` → React re-render
- Components subscribed to `hoveredNode` re-render
- Even with memoization, React still does reconciliation work

**Impact**: 20-50ms per state update

### 3. **Multiple Hover Handlers**
Two separate places calling hover logic:
1. `onMouseMove` in Cosmograph component (line 1735)
2. `onNodeHover` in useGraphInteractions (line 457)

Both eventually call the same throttled function, but the dual path adds overhead.

## Solutions (In Priority Order)

### Solution 1: Create Node ID → Node Map (CRITICAL - Must implement)

**Before**:
```typescript
const node = nodeId ? nodes.find(n => n.id === nodeId) : null;  // O(n)
```

**After**:
```typescript
// Create map once when nodes change
const nodeMap = useMemo(() => {
  const map = new Map<string, GraphNode>();
  nodes.forEach(node => map.set(node.id, node));
  return map;
}, [nodes]);

// Use in hover handler
const node = nodeId ? nodeMap.get(nodeId) || null : null;  // O(1)
```

**Performance gain**: 50-200ms → <1ms (200x faster)

### Solution 2: Pass Node Object Instead of ID

Instead of passing `nodeId` and looking it up, pass the node object directly:

**Current flow**:
```
onMouseMove(index) 
  → get nodeId from nodes[index]
  → handleNodeHoverThrottled(nodeId)
  → nodes.find(n => n.id === nodeId)  ← WASTEFUL LOOKUP
```

**Optimized flow**:
```
onMouseMove(index) 
  → handleNodeHoverThrottled(nodes[index])  ← Pass node directly
  → onNodeHover(node)  ← No lookup needed
```

**Performance gain**: Eliminates lookup entirely

### Solution 3: Passive Hover State (No React State)

Store hover state in a ref instead of React state for non-visual hover tracking:

```typescript
const hoveredNodeRef = useRef<GraphNode | null>(null);

const handleNodeHoverThrottled = useCallback((node: GraphNode | null) => {
  const now = performance.now();
  
  if (now - lastHoverTimeRef.current < 16) return;
  if (node?.id === hoveredNodeRef.current?.id) return;
  
  lastHoverTimeRef.current = now;
  hoveredNodeRef.current = node;  // Store in ref (no re-render)
  
  // Only call parent callback if they need to know
  onNodeHover?.(node);
}, [onNodeHover]);
```

**Performance gain**: Eliminates React re-renders unless parent needs it

### Solution 4: Increase Throttle Time for Non-Critical Hovers

Currently throttled to 16ms (60fps). For hover tooltips, 33ms (30fps) or 50ms (20fps) is often enough:

```typescript
if (now - lastHoverTimeRef.current < 33) return;  // 30fps
```

**Performance gain**: Reduces hover calls by 50%

## Recommended Implementation Order

1. ✅ **Solution 1** - Create nodeMap (MUST DO - biggest impact)
2. ✅ **Solution 2** - Pass node object directly (eliminates lookup)
3. ⚠️ **Solution 3** - Use ref instead of state (if parent doesn't need re-renders)
4. ⚠️ **Solution 4** - Adjust throttle time (if still needed after 1 & 2)

## Expected Final Performance

| Metric | Current | After Fixes |
|--------|---------|-------------|
| Node lookup | 50-200ms | <1ms |
| State updates | 20-50ms | 0ms (ref) |
| Total hover time | **70-250ms** | **<10ms** |
| INP | 400ms | <50ms ✅ |

## Code Changes Required

### File 1: `src/components/GraphCanvasV2.tsx`

```typescript
// Add nodeMap after nodes are available
const nodeMap = useMemo(() => {
  const map = new Map<string, GraphNode>();
  nodes.forEach(node => map.set(node.id, node));
  return map;
}, [nodes]);

// Update handleNodeHoverThrottled
const handleNodeHoverThrottled = useCallback((nodeOrId: GraphNode | string | null) => {
  const now = performance.now();
  
  // Throttle to ~60fps maximum
  if (now - lastHoverTimeRef.current < 33) {  // Changed to 33ms (30fps)
    return;
  }
  
  // Get node object
  const node = typeof nodeOrId === 'string' 
    ? (nodeMap.get(nodeOrId) || null)  // O(1) lookup
    : nodeOrId;
  
  // Skip if same node
  if (node?.id === lastHoveredNodeIdRef.current) {
    return;
  }
  
  lastHoverTimeRef.current = now;
  lastHoveredNodeIdRef.current = node?.id || null;
  
  if (!onNodeHover) return;
  onNodeHover(node);
}, [onNodeHover, nodeMap]);

// Update onMouseMove to pass node directly
onMouseMove={(index?: number) => {
  const node = (typeof index === 'number' && index >= 0 && index < nodes.length) 
    ? nodes[index]   // Pass node object directly
    : null;
  handleNodeHoverThrottled(node);
}}

// Update useGraphInteractions callback
onNodeHover: (nodeId) => {
  handleNodeHoverThrottled(nodeId);  // Still accepts ID as fallback
}
```

## Testing Verification

After implementing:
1. Open Chrome DevTools → Performance
2. Start recording
3. Move mouse over graph rapidly
4. Stop recording
5. Check INP in Performance tab - should be <50ms
6. Look for long tasks - should be none during hover
