# Graphiti Frontend Performance Audit (Cosmograph/WebGL)

Reference: Cosmograph v2 docs — https://next.cosmograph.app/docs-lib/

## Executive summary

Targeted changes below are expected to reduce initial time-to-first-frame and interaction jank by 15–35% on medium datasets (50k–200k nodes) and prevent worst-case O(N) reprocessing on incremental updates.

- Replace full setData fallbacks in delta path with Cosmograph dataManager operations to avoid full rebinds. See [processDeltaBatch()](frontend/src/components/GraphCanvas.tsx:485) and [setData](frontend/src/components/GraphCanvas.tsx:2423). Est. -10–20% TTI and -30–60% GC pressure on interactive sessions.
- Move transformation, clustering, and indexing off main thread using workers. Current transformations in [GraphCanvas.tsx](frontend/src/components/GraphCanvas.tsx) lines [1102–1217](frontend/src/components/GraphCanvas.tsx:1102) run on the main thread. Use [graphProcessor.worker.ts](frontend/src/workers/graphProcessor.worker.ts) and [dataProcessor.worker.ts](frontend/src/workers/dataProcessor.worker.ts). Est. -8–25% on initial prep, -5–15% on heavy filters.
- Replace polling-based viewport updates with Cosmograph onViewportChange to remove 10 Hz timer in [useVirtualRendering()](frontend/src/hooks/useVirtualRendering.ts:248). Est. -2–5% CPU continuous.
- Cap pixel ratio adaptively and disable simulation on large graphs. See [OptimizedGraphCanvas.tsx](frontend/src/components/OptimizedGraphCanvas.tsx) and [GraphCanvasNew.tsx](frontend/src/components/GraphCanvasNew.tsx). Est. -5–20% GPU time; improved thermals.
- Stabilize Cosmograph prop identities and callbacks via useMemo/useCallback to reduce React re-renders of the WebGL host. Multiple inline callbacks in [GraphCanvas.tsx](frontend/src/components/GraphCanvas.tsx) recreate every render. Est. -2–8% main-thread work.
- Throttle live stats and logger output. Excess console and frequent setState in [processDeltaBatch()](frontend/src/components/GraphCanvas.tsx:739) contribute to jank. Est. -1–4% on heavy update streams.
- Guard simulation restarts; avoid frequent restart() after small deltas. See [restart](frontend/src/components/GraphCanvas.tsx:734). Est. smoother interactions, fewer long frames.
- Memory: ensure worker termination and map clearing; remove large properties before passing to Cosmograph; ensure event listener detach; already good cleanup in [unmount effect](frontend/src/components/GraphCanvas.tsx:2748).

## Detailed findings

### 1) Initial load and data ingestion

- Main-thread transforms: link indexing and clustering run in React effect on the main thread in [GraphCanvas.tsx](frontend/src/components/GraphCanvas.tsx) around [1102–1217](frontend/src/components/GraphCanvas.tsx:1102). This blocks first paint under large payloads.
- Worker capabilities exist but are underused: [graphProcessor.worker.ts](frontend/src/workers/graphProcessor.worker.ts) supports TRANSFORM_DATA and CALCULATE_LAYOUT; [dataProcessor.worker.ts](frontend/src/workers/dataProcessor.worker.ts) chunks nodes/links to avoid blocking.
- setData full replacements: multiple update paths call [setData](frontend/src/components/GraphCanvas.tsx:2476) / [2528](frontend/src/components/GraphCanvas.tsx:2528) / [2633](frontend/src/components/GraphCanvas.tsx:2633) on any change. For N nodes this rebuilds GPU buffers and invalidates indices.
- Cosmograph identity: Your v2 usage correctly sets id/index/sourceIndex/targetIndex in [GraphCanvasNew.tsx](frontend/src/components/GraphCanvasNew.tsx:214)–[224](frontend/src/components/GraphCanvasNew.tsx:224). Keep those stable across updates to leverage internal caching.
- Data kit bypass: Logic acknowledges issues and bypasses DataKit ([GraphCanvas.tsx](frontend/src/components/GraphCanvas.tsx:1187)), but still performs heavy transforms synchronously.

Recommendations

- Move transforms and clustering to workers:
  - Use dataProcessor.worker chunked pipeline to compute nodeIndexMap and typed arrays. Send with postMessage using transferables to avoid copies.
  - Only setData once after worker completes; for subsequent deltas, use dataManager.
- Ensure dataManager availability before rendering:
  - On mount, feature-detect dataManager and store a boolean to avoid branching per batch. See [processDeltaBatch()](frontend/src/components/GraphCanvas.tsx:503).
- Stream/prepare in phases:
  - First paint: nodes only, minimal fields {id,index,x,y,node_type}. Links later. Call fitView then progressively add links via dataManager.addLinks in batches of 10–50k.
- Prefer Arrow/typed routes end-to-end for ingestion (workers can decode via apache-arrow, see [graphProcessor.worker.ts](frontend/src/workers/graphProcessor.worker.ts)).

### 2) Main-thread blocking and data transformation efficiency

- Polling loop: [useVirtualRendering()](frontend/src/hooks/useVirtualRendering.ts:268) sets a 100 ms interval plus debounced timers. Prefer Cosmograph onViewportChange and only compute culling when the view changes.
- Repeated O(N) rebuilds: updateNodes/updateLinks/removeNodes/removeLinks in [GraphCanvas.tsx](frontend/src/components/GraphCanvas.tsx:2439) rebuild arrays and call setData. This is O(N) per operation and triggers GC and GPU churn.
- Logging: Extensive console logs in hot paths (e.g., [console.log()](frontend/src/components/GraphCanvas.tsx:715), [500–505](frontend/src/components/GraphCanvas.tsx:500)). Gate under a DEBUG flag and strip in production.
- Synchronous clustering: [applyClusteringToGraphData()](frontend/src/components/GraphCanvas.tsx:1102) runs inline. Offload to worker.

Recommendations

- Replace polling with events:
  - Cosmograph exposes onViewportChange; wire to updateViewport and remove setInterval in [useVirtualRendering()](frontend/src/hooks/useVirtualRendering.ts:270).
- Use dataManager for incremental ops:
  - Batch pointsToAdd/linksToAdd/pointIdsToDelete/linkPairsToDelete as already implemented in [processDeltaBatch()](frontend/src/components/GraphCanvas.tsx:564)–[723](frontend/src/components/GraphCanvas.tsx:723); then remove the setData fallback once dataManager guaranteed.
- Coalesce updates:
  - Debounce delta queue flushing with rAF or a 16–33 ms timer; never more than 1 Promise.all per frame.
- Thin payloads:
  - Strip large properties before passing to Cosmograph; keep only fields used by shaders and interactions.

### 3) React render performance and component architecture

- Prop identity churn: Inline callbacks and objects passed to Cosmograph cause prop diffs and potential subtree work. Stabilize with useMemo/useCallback bundles.
- Stats and state churn: setLiveStats in [processDeltaBatch()](frontend/src/components/GraphCanvas.tsx:739) updates per batch. Throttle to one update per animation frame.
- Alternative canvas components: [OptimizedGraphCanvas.tsx](frontend/src/components/OptimizedGraphCanvas.tsx) demonstrates better memoization (capped DPR, quadtree, worker layout) but is not wired as default.

Recommendations

- Memoize Cosmograph props:
  - Build a single useMemo for visual config and callbacks. Avoid recreating functions each render.
- Switch GraphViewport to use OptimizedGraphCanvas where possible, or port its strategies into [GraphCanvas.tsx](frontend/src/components/GraphCanvas.tsx).
- Use React.memo on GraphCanvas and ensure parent props are stable.

Example: stable Cosmograph props

```ts
// Build once per relevant dependency set
const cosmographProps = useMemo(() => ({
  pointIdBy: 'id',
  pointIndexBy: 'index',
  linkSourceBy: 'source',
  linkSourceIndexBy: 'sourceIndex',
  linkTargetBy: 'target',
  linkTargetIndexBy: 'targetIndex',
  pixelRatio: Math.min(window.devicePixelRatio, largeGraph ? 2 : 2.5),
  onViewportChange: handleViewportChange, // memoized
  onClick: handleNodeClick,               // memoized
}), [largeGraph, handleViewportChange, handleNodeClick]);

return <Cosmograph ref={cosmoRef} {...cosmographProps} />;
```

### 4) Cosmograph/WebGL-specific optimizations

- Stable identity: You correctly set id/index/sourceIndex/targetIndex in [GraphCanvasNew.tsx](frontend/src/components/GraphCanvasNew.tsx:214)–[224](frontend/src/components/GraphCanvasNew.tsx:224). Ensure those values never change order across incremental updates.
- Simulation control: Frequent restart() in [processDeltaBatch()](frontend/src/components/GraphCanvas.tsx:734) can cause long frames. Use start(alpha) sparingly; prefer resume at low alpha and decay.
- Pixel ratio: [OptimizedGraphCanvas.tsx](frontend/src/components/OptimizedGraphCanvas.tsx:257) caps DPR at 2. [GraphCanvasNew.tsx](frontend/src/components/GraphCanvasNew.tsx:271) uses 2.5; consider adaptive cap by node count/fps.
- Quadtree/Large graphs: Enable useQuadtree and disable simulation automatically when node count exceeds thresholds; this exists in [OptimizedGraphCanvas.tsx](frontend/src/components/OptimizedGraphCanvas.tsx:255) — replicate in the primary canvas.
- Event wiring: Prefer Cosmograph events (onViewportChange, onClick) over polling in [useVirtualRendering()](frontend/src/hooks/useVirtualRendering.ts:268).

Example: adaptive DPR and simulation gating

```ts
const largeGraph = nodeCount > 200_000 || edgeCount > 400_000;
const pixelRatio = Math.min(window.devicePixelRatio || 1, largeGraph ? 1.5 : 2);
const enableSimulation = !largeGraph && !config.disableSimulation;

<Cosmograph pixelRatio={pixelRatio} enableSimulation={enableSimulation} />
```

Example: delta updates with dataManager (no setData fallback)

```ts
// Early feature-detect once
const hasDM = useRef(false);
useEffect(() => { hasDM.current = !!cosmographRef.current?.dataManager; }, []);

// Flush batched deltas at most once per frame
const flush = useRef(false);
const scheduleFlush = () => {
  if (flush.current) return;
  flush.current = true;
  requestAnimationFrame(async () => {
    flush.current = false;
    const { addPts, addLks, delPtIds, delLinkPairs } = drainQueues();
    const dm = cosmographRef.current!.dataManager!;
    const ops = [];
    if (delPtIds.length) ops.push(dm.removePointsByIds(delPtIds));
    if (delLinkPairs.length) ops.push(dm.removeLinksByPointIdPairs(delLinkPairs));
    if (addPts.length) ops.push(dm.addPoints(addPts));
    if (addLks.length) ops.push(dm.addLinks(addLks));
    await Promise.all(ops);
  });
};
```

### 5) Memory management and potential leak sources

- Cleanup is mostly robust: unmount effect clears timers/refs in [GraphCanvas.tsx](frontend/src/components/GraphCanvas.tsx:2748).
- WeakMap usage prevents double-init across canvases: [cosmographInitializationMap](frontend/src/components/GraphCanvas.tsx:175).
- Potential growth:
  - deltaQueueRef may grow if flush stalls; guard with maximum size/backpressure.
  - predictive-prefetcher caches up to 50 items for 60s; OK, but ensure abortable fetch and eviction on tab hide.
  - nodeIndexMap and transformed arrays should be scoped inside workers to avoid accidental retention on main thread.
- Avoid passing large properties to Cosmograph buffers. Only include rendering-critical fields.

Example: trimming payloads before send

```ts
// Before posting to worker or passing to Cosmograph
const pointsThin = nodes.map(n => ({
  id: String(n.id),
  index: n.index ?? idxMap.get(n.id),
  node_type: String(n.node_type || 'Unknown'),
  x: n.x, y: n.y
}));

const linksThin = edges.map(e => ({
  source: String(e.source ?? e.from),
  target: String(e.target ?? e.to),
  sourceIndex: idxMap.get(String(e.source ?? e.from)),
  targetIndex: idxMap.get(String(e.target ?? e.to)),
  weight: Number(e.weight ?? 1)
}));
```

## Actionable recommendations (prioritized)

1) Eliminate setData fallback in deltas
- On mount, detect dataManager and hard-require it for deltas; if unavailable, delay deltas until mount completes rather than performing full replace. Touch points: [processDeltaBatch()](frontend/src/components/GraphCanvas.tsx:503), [updateNodes()](frontend/src/components/GraphCanvas.tsx:2439), [updateLinks()](frontend/src/components/GraphCanvas.tsx:2486), [removeNodes()](frontend/src/components/GraphCanvas.tsx:2539), [removeLinks()](frontend/src/components/GraphCanvas.tsx:2592).
- KPI: 30–60% reduction in GC and frame spikes during interactive edits.

2) Offload transforms/clustering to workers
- Move node index building and link mapping currently in [GraphCanvas.tsx](frontend/src/components/GraphCanvas.tsx:1131)–[1173](frontend/src/components/GraphCanvas.tsx:1173) into [dataProcessor.worker.ts](frontend/src/workers/dataProcessor.worker.ts).
- KPI: 8–25% faster dataPreparation stage; improved input responsiveness.

3) Replace polling with onViewportChange
- Remove interval in [useVirtualRendering()](frontend/src/hooks/useVirtualRendering.ts:270) and wire Cosmograph’s viewport event.
- KPI: 2–5% continuous CPU reduction.

4) Memoize WebGL host props and cap DPR adaptively
- Apply patterns from [OptimizedGraphCanvas.tsx](frontend/src/components/OptimizedGraphCanvas.tsx:243)–[258](frontend/src/components/OptimizedGraphCanvas.tsx:258) to [GraphCanvas.tsx](frontend/src/components/GraphCanvas.tsx).
- KPI: 5–20% GPU time reduction on HiDPI; fewer WebGL state changes.

5) Throttle live stats/logger
- Update [setLiveStats](frontend/src/components/GraphCanvas.tsx:739) at most once per rAF; gate logger behind env flag.
- KPI: 1–4% CPU reduction in sustained updates.

6) Simulation hygiene
- Replace restart() with start(alpha) only when structure meaningfully changes; skip for small additions in [processDeltaBatch()](frontend/src/components/GraphCanvas.tsx:731).
- KPI: fewer long frames; improved FPS stability.

## Code changes – examples and patches

1) Remove polling; use viewport event

```ts
// useVirtualRendering.ts
// Replace setInterval polling with Cosmograph's onViewportChange
useEffect(() => {
  if (!cosmographRef.current || !shouldVirtualize) return;
  const off = cosmographRef.current.onViewportChange?.(() => updateViewport());
  updateViewport(); // initial
  return () => { off?.(); };
}, [cosmographRef, shouldVirtualize, updateViewport]);
```

2) Single-frame delta flushing

```ts
// GraphCanvas.tsx
const enqueueDelta = (delta: Delta) => {
  deltaQueueRef.current.push(delta);
  scheduleFlush(); // rAF-batched
};
```

3) Throttled live stats

```ts
const statsRAF = useRef<number | null>(null);
const updateStats = (d: {nodesAdded:number, linksAdded:number, nodesDel:number, linksDel:number}) => {
  if (statsRAF.current !== null) return;
  statsRAF.current = requestAnimationFrame(() => {
    statsRAF.current = null;
    setLiveStats(prev => ({
      nodeCount: prev.nodeCount + d.nodesAdded - d.nodesDel,
      edgeCount: prev.edgeCount + d.linksAdded - d.linksDel,
      lastUpdated: Date.now()
    }));
  });
};
```

4) Worker-based data prep

```ts
// On data load
const res = await worker.send('TRANSFORM_DATA', { nodes, links, filterConfig });
cosmographRef.current.setData(res.nodes, res.links, true);
```

## Measurement plan

- Add performance marks around dataPreparation and delta flush boundaries in [GraphCanvas.tsx](frontend/src/components/GraphCanvas.tsx).
- Capture FPS and CPU via PerformanceObserver; verify >10% reduction in TTI and fewer long tasks.
- A/B test DPR cap and simulation gating thresholds using a query param or localStorage flag.

## Risk notes

- dataManager dependency ties you to Cosmograph >= 2.0.0-beta.25; verify API stability before removing fallbacks.
- Worker serialization: keep payloads thin and prefer transferables for Arrow buffers and typed arrays.
- Event availability: ensure onViewportChange exists in your Cosmograph wrapper; if not, add a minimal bridge rather than polling.

## Appendix: key code hotspots

- Deltas and setData fallbacks: [processDeltaBatch()](frontend/src/components/GraphCanvas.tsx:485) and [setData calls](frontend/src/components/GraphCanvas.tsx:2415)
- Main-thread transforms: [GraphCanvas.tsx](frontend/src/components/GraphCanvas.tsx:1131)–[1173](frontend/src/components/GraphCanvas.tsx:1173)
- Polling-based viewport culling: [useVirtualRendering()](frontend/src/hooks/useVirtualRendering.ts:268)
- Optimized patterns to reuse: [OptimizedGraphCanvas.tsx](frontend/src/components/OptimizedGraphCanvas.tsx:243)–[258](frontend/src/components/OptimizedGraphCanvas.tsx:258)
- Cleanup done well: [Unmount cleanup](frontend/src/components/GraphCanvas.tsx:2748)