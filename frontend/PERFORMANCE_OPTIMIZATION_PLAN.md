# Visualizer Performance Optimization Plan
## Goal: Make it as fast as physically possible

## Current State Analysis

### Known Issues
1. **WebGL memory leak** - No cleanup on unmount
2. **Reconciliation blocking** - WebSocket updates block render
3. **Re-render storms** - Unnecessary React re-renders

### Performance Budget
- **Target**: 60 FPS (16.67ms per frame)
- **Current**: Unknown (need to measure)

## Phase 1: Measurement & Profiling (Week 1)

### 1.1 Chrome DevTools Profiling
```bash
# Record performance profile
1. Open visualizer with 10K nodes
2. Start Chrome DevTools Performance recording
3. Interact: pan, zoom, select nodes
4. Stop recording
5. Analyze:
   - Identify functions taking >5ms
   - Find allocation spikes
   - Track frame drops
   - Measure GC pauses
```

### 1.2 Performance Metrics Collection
```typescript
// Add performance markers
performance.mark('render-start');
// ... render code ...
performance.mark('render-end');
performance.measure('render', 'render-start', 'render-end');

// Report metrics
const measures = performance.getEntriesByType('measure');
console.log('Render time:', measures.find(m => m.name === 'render').duration);
```

### 1.3 Baseline Metrics
Capture current performance:
- Render time (initial load)
- Update time (add 100 nodes)
- Frame rate (during pan/zoom)
- Memory usage (heap size over time)
- GC frequency (pauses per minute)

## Phase 2: Hot Path Optimization (Week 2)

### 2.1 Cosmograph Data Preparation (Hot Path #1)

**Current Code** (likely allocates every update):
```typescript
const cosmographData = useMemo(() => ({
  nodes: nodes.map(n => ({ ...n, ... })),
  links: links.map(l => ({ ...l, ... }))
}), [nodes, links]);
```

**Optimized** (typed arrays, zero-copy):
```typescript
// Pre-allocate buffers
const nodeBuffer = useRef<Float32Array>();
const linkBuffer = useRef<Uint32Array>();

const cosmographData = useMemo(() => {
  // Reuse buffers if size matches
  if (!nodeBuffer.current || nodeBuffer.current.length !== nodes.length * 6) {
    nodeBuffer.current = new Float32Array(nodes.length * 6);
  }
  
  // Fill buffer directly (no intermediate objects)
  for (let i = 0; i < nodes.length; i++) {
    const offset = i * 6;
    nodeBuffer.current[offset] = nodes[i].x;
    nodeBuffer.current[offset + 1] = nodes[i].y;
    nodeBuffer.current[offset + 2] = nodes[i].size;
    // ... etc
  }
  
  return {
    nodeBuffer: nodeBuffer.current,
    linkBuffer: linkBuffer.current,
    count: nodes.length
  };
}, [nodes, links]);
```

**Expected gain**: 50-70% reduction in allocation, 30% faster updates

### 2.2 Render Loop Optimization (Hot Path #2)

**WebGL Best Practices**:
```typescript
// Batch state changes
gl.disable(gl.DEPTH_TEST);
gl.enable(gl.BLEND);
gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

// Use vertex buffer objects (VBO)
const vbo = gl.createBuffer();
gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
gl.bufferData(gl.ARRAY_BUFFER, positionBuffer, gl.DYNAMIC_DRAW);

// Minimize draw calls
gl.drawArrays(gl.POINTS, 0, count); // Single call for all nodes
```

### 2.3 Selection/Hover Optimization (Hot Path #3)

**Current** (likely O(n) lookup):
```typescript
const isSelected = selectedNodes.includes(node.id); // O(n) every frame
```

**Optimized** (O(1) lookup):
```typescript
const selectedSet = useMemo(
  () => new Set(selectedNodes),
  [selectedNodes]
);
const isSelected = selectedSet.has(node.id); // O(1)
```

**Expected gain**: 95% faster for large selections

## Phase 3: Memory Management (Week 2)

### 3.1 Object Pooling
```typescript
// Pool for temporary vector calculations
class Vec3Pool {
  private pool: Float32Array[] = [];
  private size = 0;
  
  acquire(): Float32Array {
    return this.pool[this.size++] || new Float32Array(3);
  }
  
  release(vec: Float32Array) {
    this.pool[--this.size] = vec;
  }
  
  clear() {
    this.size = 0;
  }
}

const vec3Pool = new Vec3Pool();

// Use in render loop
function calculateForce(node) {
  const force = vec3Pool.acquire();
  // ... calculations ...
  vec3Pool.release(force);
}
```

### 3.2 WebGL Resource Cleanup
```typescript
// Track all WebGL resources
const resources = useRef<Set<WebGLBuffer | WebGLTexture>>>(new Set());

function createBuffer() {
  const buffer = gl.createBuffer();
  resources.current.add(buffer);
  return buffer;
}

// Cleanup on unmount
useEffect(() => {
  return () => {
    resources.current.forEach(resource => {
      if (resource instanceof WebGLBuffer) {
        gl.deleteBuffer(resource);
      } else if (resource instanceof WebGLTexture) {
        gl.deleteTexture(resource);
      }
    });
    resources.current.clear();
  };
}, []);
```

**Expected gain**: Zero memory leaks, stable heap size

### 3.3 Incremental Updates (Avoid Full Re-render)
```typescript
// Track dirty regions
const dirtyNodes = useRef<Set<string>>(new Set());

function updateNode(id: string, changes: Partial<Node>) {
  nodes.current.set(id, { ...nodes.current.get(id), ...changes });
  dirtyNodes.current.add(id);
}

// Only re-render dirty regions
function render() {
  if (dirtyNodes.current.size === 0) return;
  
  dirtyNodes.current.forEach(id => {
    const node = nodes.current.get(id);
    updateBufferRegion(node);
  });
  
  dirtyNodes.current.clear();
  gl.drawArrays(...);
}
```

## Phase 4: Advanced Optimizations (Week 3)

### 4.1 Web Workers for Heavy Computation
```typescript
// Offload force calculation to worker
const worker = new Worker('./physics-worker.ts');

worker.postMessage({
  nodes: nodeBuffer,
  links: linkBuffer,
  iterations: 10
});

worker.onmessage = (e) => {
  // Update positions from worker
  nodeBuffer.set(e.data.positions);
  render();
};
```

### 4.2 Level-of-Detail (LOD)
```typescript
// Reduce detail when zoomed out
function getLOD(zoomLevel: number) {
  if (zoomLevel < 0.1) return 'low';    // Just points
  if (zoomLevel < 0.5) return 'medium'; // Points + labels
  return 'high';                         // Full detail
}

function render() {
  const lod = getLOD(camera.zoom);
  
  if (lod === 'low') {
    // Skip labels, edge rendering
    renderNodesOnly();
  } else if (lod === 'medium') {
    renderNodesAndLabels();
  } else {
    renderFull();
  }
}
```

### 4.3 Spatial Indexing (Frustum Culling)
```typescript
// R-tree for fast spatial queries
const spatialIndex = new RTree();

nodes.forEach(node => {
  spatialIndex.insert({
    minX: node.x - node.size,
    minY: node.y - node.size,
    maxX: node.x + node.size,
    maxY: node.y + node.size,
    node
  });
});

// Only render visible nodes
function render() {
  const visible = spatialIndex.search({
    minX: viewport.left,
    minY: viewport.top,
    maxX: viewport.right,
    maxY: viewport.bottom
  });
  
  renderNodes(visible); // 10x fewer nodes
}
```

### 4.4 GPU Compute Shaders (WebGPU)
```wgsl
// Force-directed layout on GPU
@compute @workgroup_size(64)
fn calculateForces(
  @builtin(global_invocation_id) id: vec3<u32>
) {
  let node = nodes[id.x];
  var force = vec2<f32>(0.0);
  
  // Repulsion from all nodes
  for (var i = 0u; i < nodeCount; i++) {
    if (i == id.x) { continue; }
    let other = nodes[i];
    let delta = node.pos - other.pos;
    let dist = length(delta);
    force += normalize(delta) * (REPULSION / (dist * dist));
  }
  
  // Spring from connected edges
  for (var i = 0u; i < edgeCount; i++) {
    let edge = edges[i];
    if (edge.source == id.x) {
      let target = nodes[edge.target];
      let delta = target.pos - node.pos;
      force += normalize(delta) * SPRING;
    }
  }
  
  forces[id.x] = force;
}
```

## Phase 5: React-Specific Optimizations (Week 4)

### 5.1 Minimize Re-renders
```typescript
// Use React.memo for expensive components
const NodeDetails = React.memo(({ node }) => {
  // Only re-render if node changes
}, (prev, next) => prev.node.id === next.node.id);

// Use useCallback to prevent prop changes
const handleClick = useCallback((node) => {
  // Stable reference
}, []);
```

### 5.2 Virtualization for Large Lists
```typescript
// Only render visible DOM elements
import { FixedSizeList } from 'react-window';

<FixedSizeList
  height={600}
  itemCount={nodes.length}
  itemSize={50}
  width="100%"
>
  {({ index, style }) => (
    <NodeListItem node={nodes[index]} style={style} />
  )}
</FixedSizeList>
```

### 5.3 Debounce/Throttle User Input
```typescript
// Throttle pan/zoom updates
const handlePan = useThrottle((dx, dy) => {
  camera.pan(dx, dy);
}, 16); // ~60 FPS
```

## Expected Performance Gains

### Conservative Estimates
- **Render time**: 50% faster (better data structures)
- **Update time**: 70% faster (incremental updates, object pooling)
- **Memory**: 90% reduction in allocations (typed arrays, pooling)
- **Frame rate**: Solid 60 FPS for 50K nodes (vs current unknown)

### Stretch Goals (with WebGPU + all optimizations)
- **100K nodes** at 60 FPS
- **Sub-100ms** initial load
- **<50MB** heap size (stable over time)
- **Zero GC pauses** during interaction

## Implementation Priority

### P0 (Critical - Do First)
1. WebGL cleanup on unmount (memory leak fix)
2. Chrome DevTools profiling (measure current state)
3. Set → includes optimization (easy win)

### P1 (High Impact)
1. Typed array buffers
2. Object pooling
3. Incremental updates

### P2 (Medium Impact)
1. Web Workers
2. LOD system
3. Spatial indexing

### P3 (Advanced)
1. WebGPU compute shaders
2. WASM for physics
3. Shared memory workers

## Success Metrics

### Before
- Unknown (need baseline)

### After
- [ ] 60 FPS sustained for 50K nodes
- [ ] <200ms initial render
- [ ] <10ms update time for 100 node delta
- [ ] <100MB heap size (stable)
- [ ] Zero memory leaks
- [ ] <1 GC pause per minute

## Tools & Resources

### Profiling
- Chrome DevTools Performance
- React DevTools Profiler
- WebGL Inspector
- Spector.js (WebGL debugger)

### Libraries
- RBush (spatial indexing)
- gl-matrix (fast vector math)
- comlink (easy Web Workers)
- react-window (virtualization)

### References
- [WebGL Best Practices](https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API/WebGL_best_practices)
- [React Performance Optimization](https://react.dev/learn/render-and-commit#optimizing-performance)
- [High Performance Browser Networking](https://hpbn.co/)
