# Graph Layout System Analysis & Fix Guide

## Current State: Complete UI, Missing Algorithms

### ✅ What's Working
- **LayoutPanel.tsx**: Complete UI with 6 layout types (force-directed, hierarchical, radial, circular, temporal, cluster)
- **GraphConfigContext**: Proper state management and configuration
- **Visual Integration**: All physics parameters properly connected to Cosmograph

### ❌ Critical Gap: No Layout Algorithms
The current `applyLayout` function only changes **physics parameters** but never actually **calculates and positions nodes**.

## The Problem

```typescript
// Current implementation (GraphConfigContext.tsx)
const applyLayout = (layoutType: string, options?: any) => {
  switch (layoutType) {
    case 'hierarchical':
      // ❌ Only changes physics - no actual node positioning
      updateConfig({
        layout: layoutType,
        gravity: 0.1,
        centerForce: 0.3,
        repulsion: 0.2,
        linkDistance: 4
      });
      break;
  }
};
```

**This is just a "physics preset" - not a true layout algorithm.**

## What We Need: Actual Layout Algorithms

### Required Implementation Pattern

```typescript
const applyLayout = async (layoutType: string, options?: any) => {
  // 1. Calculate actual node positions
  const positions = calculateLayoutPositions(layoutType, nodes, edges, options);
  
  // 2. Apply positions to Cosmograph
  if (cosmographRef.current) {
    const positionedNodes = nodes.map((node, i) => ({
      ...node,
      x: positions[i][0],
      y: positions[i][1]
    }));
    
    // 3. Set data with positions, disable simulation for fixed layouts
    cosmographRef.current.setData(positionedNodes, edges, false);
  }
  
  // 4. Update config
  updateConfig({ layout: layoutType });
};
```

## Missing Layout Algorithm Functions

We need to implement these core functions:

### 1. Hierarchical Layout
```typescript
function calculateHierarchicalLayout(
  nodes: GraphNode[], 
  edges: GraphEdge[], 
  options: { direction: 'top-down' | 'left-right' | 'bottom-up' | 'right-left' }
): [number, number][] {
  // BFS/DFS traversal to create tree structure
  // Assign levels and positions within levels
  // Return [x, y] positions for each node
}
```

### 2. Radial Layout
```typescript
function calculateRadialLayout(
  nodes: GraphNode[], 
  edges: GraphEdge[], 
  centerNodeId?: string
): [number, number][] {
  // Place center node at origin
  // Arrange other nodes in concentric circles by distance from center
  // Use graph shortest path algorithms
}
```

### 3. Circular Layout
```typescript
function calculateCircularLayout(
  nodes: GraphNode[], 
  options: { ordering: 'degree' | 'centrality' | 'type' | 'alphabetical' }
): [number, number][] {
  // Sort nodes by specified criteria
  // Arrange in perfect circle with equal angular spacing
}
```

### 4. Temporal Layout
```typescript
function calculateTemporalLayout(
  nodes: GraphNode[], 
  edges: GraphEdge[]
): [number, number][] {
  // Extract temporal information from node properties
  // Arrange nodes along timeline axis
  // Group by time periods
}
```

### 5. Cluster Layout
```typescript
function calculateClusterLayout(
  nodes: GraphNode[], 
  edges: GraphEdge[], 
  options: { clusterBy: 'type' | 'community' | 'centrality' | 'temporal' }
): [number, number][] {
  // Group nodes by specified criteria
  // Apply force-directed layout within clusters
  // Separate clusters spatially
}
```

## Integration Points

### 1. GraphConfigContext Changes
```typescript
// Add layout state
const [isApplyingLayout, setIsApplyingLayout] = useState(false);

// Add cosmograph ref access
const [cosmographRef, setCosmographRef] = useState<RefObject<CosmographRef> | null>(null);

// Update applyLayout to actually position nodes
const applyLayout = async (layoutType: string, options?: any) => {
  if (!cosmographRef?.current || !data) return;
  
  setIsApplyingLayout(true);
  
  try {
    const positions = await calculateLayoutPositions(layoutType, data.nodes, data.edges, options);
    
    const positionedNodes = data.nodes.map((node, i) => ({
      ...node,
      x: positions[i][0],
      y: positions[i][1]
    }));
    
    cosmographRef.current.setData(positionedNodes, data.edges, false);
    updateConfig({ layout: layoutType });
  } finally {
    setIsApplyingLayout(false);
  }
};
```

### 2. GraphCanvas Integration
```typescript
// In GraphCanvas.tsx - expose setData method via ref
React.useImperativeHandle(ref, () => ({
  clearSelection: clearCosmographSelection,
  selectNode: selectCosmographNode,
  selectNodes: selectCosmographNodes,
  zoomIn,
  zoomOut,
  fitView,
  // Add layout methods
  setData: (nodes: GraphNode[], edges: GraphEdge[], runSimulation = true) => {
    if (cosmographRef.current) {
      cosmographRef.current.setData(nodes, edges, runSimulation);
    }
  },
  restart: () => cosmographRef.current?.restart(),
}), [/* dependencies */]);
```

## Implementation Priority

### Phase 1: Core Infrastructure
1. ✅ Add layout algorithm utility functions
2. ✅ Update GraphConfigContext with position calculation logic
3. ✅ Add Cosmograph setData integration
4. ✅ Add loading states for layout application

### Phase 2: Layout Algorithms
1. ✅ Implement circular layout (simplest)
2. ✅ Implement radial layout
3. ✅ Implement hierarchical layout
4. ✅ Implement cluster layout
5. ✅ Implement temporal layout

### Phase 3: Advanced Features
1. ✅ Add layout animation/transitions
2. ✅ Add layout persistence
3. ✅ Add custom layout options
4. ✅ Add layout presets with real positioning

## Files to Modify

1. **`contexts/GraphConfigContext.tsx`** - Add layout calculation logic
2. **`components/GraphCanvas.tsx`** - Add setData method to ref interface
3. **`utils/layoutAlgorithms.ts`** - Create new file with layout functions
4. **`components/LayoutPanel.tsx`** - Add loading states and better feedback

## Reference Implementation

The working layout system can be found in the Rust HTML files:
- `graph-visualizer-rust/static/cosmograph.html` - Contains working layout algorithms
- Look for functions like `applyHierarchicalLayout()`, `applyRadialLayout()`, etc.

## Next Steps

1. **Create `utils/layoutAlgorithms.ts`** with the core layout calculation functions
2. **Update GraphConfigContext** to call these functions and apply positions
3. **Test with simple circular layout first** to validate the integration
4. **Port remaining algorithms** from the working Rust implementation

The UI is production-ready - we just need to connect it to actual geometric layout algorithms!