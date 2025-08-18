# Sizing Strategies: Why They’re Not Connected (and How to Fix)

This guide documents why the node sizing strategies aren’t driving point sizes in the current UI, and provides implementation-ready fixes with code snippets.

---

## Executive summary

- Multiple sizing systems exist (GraphCanvas, VisualizationStrategies, Optimized/Refactored canvases, legacy Cosmograph HTML).
- The main path (frontend/src/components/GraphCanvas.tsx) doesn’t consume the refactored VisualizationStrategies.
- Default fallbacks reference a non-existent field (`centrality`), so size mapping can silently fall back to uniform.
- Under DuckDB mode, we pass `pointSizeBy="size"`, but the `size` we set in mapping is just `degree_centrality` (0–1) and may not reflect the intended strategy.
- Result: The strategy you set in the UI may not affect the final rendered size, or sizes appear uniform/inconsistent.

---

## Where sizes are determined today

1) Main GraphCanvas (current production path)

- Chooses a column name for size based on `config.sizeMapping`:

```ts
// frontend/src/components/GraphCanvas.tsx
const pointSizeBy = React.useMemo(() => {
  switch (config.sizeMapping) {
    case 'uniform': return undefined;                    // handled later
    case 'degree': return 'degree_centrality';
    case 'betweenness': return 'betweenness_centrality';
    case 'pagerank': return 'pagerank_centrality';
    case 'importance': return 'eigenvector_centrality';
    case 'connections': return 'degree_centrality';
    case 'custom': return 'centrality';                  // FALLBACK PROBLEM
    default: return 'centrality';                        // FALLBACK PROBLEM
  }
}, [config.sizeMapping]);
```

- Feeds it into the DataKit config (preprocessing) and the renderer props:

```ts
// DataKit config
points: {
  pointSizeBy: pointSizeBy || 'centrality',              // FALLBACK PROBLEM
  pointIncludeColumns: [
    'degree_centrality', 'pagerank_centrality',
    'betweenness_centrality', 'eigenvector_centrality',
    'created_at', 'created_at_timestamp'
  ]
}

// Renderer props
<Cosmograph
  pointSizeBy={useDuckDBTables ? 'size' : pointSizeBy}
  pointSizeStrategy={'auto'}
  pointSizeRange={[config.minNodeSize * config.sizeMultiplier, config.maxNodeSize * config.sizeMultiplier]}
/>
```

- Under DuckDB mode, we force `pointSizeBy="size"`, but mapping sets `node.size` like this:

```ts
// frontend/src/hooks/useGraphDataQuery.ts (current mapping)
size: plainNode.degree_centrality || 1,
```

2) Refactored strategies (not wired into main path)

- VisualizationStrategies defines multiple size strategies (degree, centrality, pagerank, custom):

```tsx
// frontend/src/components/graph-refactored/features/VisualizationStrategies.tsx
const size = applySizeStrategy(node, fullConfig.size) // supports degree/log, centrality, pagerank, etc.
```

- It’s used in GraphViewportEnhancedFixed.tsx with IsolatedCosmographCanvas, but not in the main GraphCanvas path used by the app’s primary view.

```tsx
// frontend/src/components/GraphViewportEnhancedFixed.tsx
<VisualizationStrategies nodes={nodes} edges={links} config={vizConfig}>
  <IsolatedCosmographCanvas ... />
</VisualizationStrategies>
```

3) Optimized/Refactored canvases (separate path)

- These canvases compute a size function, but are not used by the main GraphCanvas:

```tsx
// frontend/src/components/graph-refactored/GraphCanvas.tsx
const getNodeSize = useCallback((node) => 2 + ((node.properties?.centrality as number) || 0.5) * 8, [])
```

---

## What’s wrong (key disconnects)

1) Non-existent `centrality` field fallback
- When `sizeMapping` is `custom` or an unexpected value, we fall back to `'centrality'` as the column name, but nodes don’t have a `centrality` property by default.
- This causes the size mapping to be undefined, and the renderer silently uses uniform or a default value.

2) For DuckDB, `size` is not a strategy result
- We pass `pointSizeBy="size"` when using DuckDB tables.
- But `size` is set to `degree_centrality` (0–1), not the chosen strategy, so the UI setting may not impact sizes.

3) VisualizationStrategies isn’t connected to the main path
- The richer strategies in `VisualizationStrategies.tsx` are only used in the experimental/refactored viewport, not the main `GraphCanvas.tsx` path.

4) DataKit config vs renderer mismatch
- DataKit uses `pointSizeBy: pointSizeBy || 'centrality'` and doesn’t include `size` in `pointIncludeColumns`.
- Renderer switches to `'size'` (DuckDB case), so the preprocessed data may lack the column expected by the renderer.

---

## Fix options

### Option A (recommended): Unify on `size` as the authoritative field

- Compute `node.size` during node mapping based on `config.sizeMapping`.
- Always set `pointSizeBy='size'` for the renderer and include `'size'` in `pointIncludeColumns`.
- This keeps one source of truth and ensures UI changes take effect everywhere.

Implementation snippets:

1) Compute `size` in `useGraphDataQuery.ts` when mapping nodes

```ts
// frontend/src/hooks/useGraphDataQuery.ts
function computeSizeFromStrategy(node: any, cfg: any): number {
  const min = 0; // normalized metric expected (0..1); renderer handles pixel scaling
  switch (cfg.sizeMapping) {
    case 'degree': return node.degree_centrality || 0;
    case 'betweenness': return node.betweenness_centrality || 0;
    case 'pagerank': return node.pagerank_centrality || 0;
    case 'importance': return node.eigenvector_centrality || 0;
    case 'connections': return node.degree_centrality || 0;
    case 'uniform': return 0.5; // mid value → mid of pointSizeRange
    default: return node.eigenvector_centrality || node.pagerank_centrality || node.degree_centrality || 0; // safest
  }
}

// In the node return object:
size: computeSizeFromStrategy(plainNode, config),
```

2) Make renderer always use `size`

```tsx
// frontend/src/components/GraphCanvas.tsx
const pointSizeBy = 'size'; // force unified field

const dataKitConfig = React.useMemo(() => ({
  points: {
    pointIdBy: 'id',
    pointIndexBy: 'index',
    pointLabelBy: 'label',
    pointColorBy: pointColorBy || 'node_type',
    pointSizeBy: 'size',                             // unified
    pointIncludeColumns: [
      'size',                                        // include it
      'degree_centrality', 'pagerank_centrality',
      'betweenness_centrality', 'eigenvector_centrality',
      'created_at', 'created_at_timestamp'
    ]
  },
  // ...
}), [pointColorBy /*, removed config.linkWidthBy if unchanged */]);

<Cosmograph
  // ...
  pointSizeBy={'size'}
  pointSizeStrategy={'auto'}
  pointSizeRange={[config.minNodeSize * config.sizeMultiplier, config.maxNodeSize * config.sizeMultiplier]}
/>
```

Pros:
- Simple mental model; one place computes size.
- UI `sizeMapping` immediately affects size.

Cons:
- Slight duplication if other renderers compute size in shaders; but clarity wins here.

### Option B: Wire `VisualizationStrategies` into the main path

- Use `VisualizationStrategies` to style nodes and pass its `styledNodes` (with computed `size`) to the Cosmograph component.
- This centralizes visual logic and reuses your advanced strategies.

Implementation sketch:

```tsx
// frontend/src/components/GraphCanvas.tsx
import { VisualizationStrategies } from './graph-refactored/features/VisualizationStrategies';

return (
  <VisualizationStrategies
    nodes={nodes}
    edges={links}
    config={{
      size: {
        strategy: config.sizeMapping || 'degree',
        minSize: config.minNodeSize,
        maxSize: config.maxNodeSize,
      },
      color: { scheme: 'type' },
      shape: { strategy: 'circle' }
    }}
  >
    <Cosmograph
      // Expect `size` field on nodes; keep `pointSizeBy='size'`
      pointSizeBy={'size'}
      pointSizeRange={[config.minNodeSize * config.sizeMultiplier, config.maxNodeSize * config.sizeMultiplier]}
      // ...other props
    />
  </VisualizationStrategies>
)
```

Pros:
- Leverages the already-built strategy system (degree/log scaling, pagerank, etc.).
- One place to evolve visualization logic.

Cons:
- Slightly larger refactor; ensure the `VisualizationStrategies`’ styled nodes flow into the Cosmograph data pipeline.

---

## Additional cleanups (do regardless of option)

1) Remove `'centrality'` fallback

```ts
// Replace any uses of pointSizeBy || 'centrality' with a valid key or 'size'
pointSizeBy: 'size'
```

2) Include `'size'` in DataKit `pointIncludeColumns`

```ts
pointIncludeColumns: ['size', 'degree_centrality', 'pagerank_centrality', 'betweenness_centrality', 'eigenvector_centrality', 'created_at', 'created_at_timestamp']
```

3) Ensure DuckDB path and JSON path both set `size`
- For JSON/API loaded nodes, also compute `size` in their mapping to avoid path divergence.

4) Keep pixel scaling in the renderer
- Continue using `pointSizeStrategy='auto'` + `pointSizeRange=[min,max]`. We’re standardizing the input value (`size`), not removing renderer scaling.


---

## Appendix: Aligning with CosmographConfig API

Based on the Cosmograph 2.0 config docs:
- pointSizeBy: string column whose numeric values are used for sizing and label weight.
- pointSizeStrategy:
  - 'auto' (default): symmetric log scaling with quantile boundaries, uses pointSizeRange.
  - 'direct': uses raw values (or pointSizeByFn) as absolute sizes, falls back to pointSize if invalid or not provided.
  - 'degree': sizes by degree (needs links), scaled into pointSizeRange.
- pointSizeRange: [minPx, maxPx] remaps the numeric values from pointSizeBy when using 'auto' or 'degree'.
- pointSizeByFn: function to compute sizes from pointSizeBy values; used when pointSizeStrategy is undefined.

Implications for our wiring:
- Always provide a valid numeric column via pointSizeBy. Using a non-existent fallback key like 'centrality' causes Cosmograph to ignore size mapping and revert to defaults.
- Prefer pointSizeStrategy='auto' with a normalized 0..1 size column and set pointSizeRange to user-configured [min, max] pixels.
- If we need raw pixel control from data, use pointSizeStrategy='direct' and ensure pointSizeBy values are in pixels.
- If we want Cosmograph to compute by graph degree, we can set pointSizeStrategy='degree' (but then keep pointSizeBy unset and ensure links are provided). For consistency with UI strategies, we generally recommend computing 'size' ourselves and using 'auto'.

Recommended final config (after unifying on size):

```tsx
<Cosmograph
  pointIdBy="id"
  pointIndexBy={useDuckDBTables ? 'idx' : 'index'}
  pointSizeBy={'size'}             // authoritative size column
  pointSizeStrategy={'auto'}       // symmetric log scaling into range
  pointSizeRange={[config.minNodeSize * config.sizeMultiplier, config.maxNodeSize * config.sizeMultiplier]}
  // ... other props
/>
```

---

## Quick test plan

1) Switch `sizeMapping` across degree/pagerank/importance and verify visual changes immediately.
2) Toggle DuckDB mode on/off and verify the sizes remain consistent.
3) Confirm that no console warnings appear about missing `centrality` or `size` columns.
4) Stress-test a large graph: sizes should compress reasonably with the existing range settings.

---

## TL;DR

- The strategies aren’t “hooked up” because the main canvas doesn’t use `VisualizationStrategies`, and the current fallbacks reference a non-existent `centrality` field. In DuckDB mode, we ignore the strategy and just use `size = degree_centrality`.
- Fix by unifying on a single authoritative `size` field computed during mapping, and make both DataKit and the renderer use `pointSizeBy='size'`. Optionally, adopt `VisualizationStrategies` so the strategy logic is centralized and reusable.

