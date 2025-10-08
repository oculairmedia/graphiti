# Fixing Incorrect "Related Nodes" Count

This document explains why the "Related Nodes" count can be incorrect and provides minimal, implementation-ready fixes.

---

## Symptoms

- Node Details panel shows a "Related Nodes" count that is 0 or otherwise incorrect, even when the node clearly has connections.

---

## Root Causes

1) "Connections" is derived from normalized degree centrality, not actual edges

- In `useGraphDataQuery.ts`, we currently set:
  - `degree = Math.round(degree_centrality * 100)`
  - `connections = Math.round(degree_centrality * 100)`
- `degree_centrality` is normalized to [0,1] (neighbors / (N−1)). Multiplying by 100 is just a guess and varies with graph size. This leads to incorrect counts.

2) Edge endpoint mixing (UUID vs idx) breaks counting by node.id

- When mapping edges from DuckDB, the code sometimes falls back to `targetidx` if `target` (UUID) is missing.
- That mixes string UUIDs with numeric indices for endpoints, so counting edges by `node.id` (UUID) can miss edges.

---

## Where This Happens

- Incorrect derivation of connections (normalized centrality → integer count):

```ts
// frontend/src/hooks/useGraphDataQuery.ts (current)
properties: {
  // ...
  degree: plainNode.degree_centrality ? Math.round(plainNode.degree_centrality * 100) : 0,
  connections: plainNode.degree_centrality ? Math.round(plainNode.degree_centrality * 100) : 0,
}
```

- Node Details panel uses that property when an explicit `connections` prop isn’t provided:

```tsx
// frontend/src/components/NodeDetailsPanel.tsx (current)
connections: connections !== undefined
  ? connections
  : (deferredProperties?.degree || deferredProperties?.connections || 0)
```

- Edge mapping mixes UUID and idx:

```ts
// frontend/src/hooks/useGraphDataQuery.ts (current)
return {
  id: `${e.source}-${e.target}`,
  source: e.source,
  target: e.target || e.targetidx, // ← fallback to idx (bad for UUID-based counts)
  from: e.source,
  to: e.target || e.targetidx,
  sourceIndex: nodeIndexMap.get(String(e.source)) ?? -1,
  targetIndex: nodeIndexMap.get(String(e.target || e.targetidx)) ?? -1,
  // ...
};
```

---

## Minimal Fixes

A) Compute "Related Nodes" from actual edges (UUID endpoints)

- Use the existing utility to compute degrees from edges (by UUID), and pass that count to the `NodeDetailsPanel`.

```ts
// frontend/src/components/GraphViz.tsx (suggested change)
import { calculateNodeDegrees } from '@/utils/graphNodeOperations';

// ... inside component, when you have `data` and `selectedNode`:
const degreeMap = useMemo(() => calculateNodeDegrees(data.nodes, data.edges), [data.nodes, data.edges]);
const relatedCount = selectedNode ? (degreeMap.get(selectedNode.id) || 0) : 0;

<NodeDetailsPanel
  node={selectedNode}
  connections={relatedCount}
  onClose={() => clearAllSelections()}
  onShowNeighbors={handleShowNeighbors}
/>
```

B) Keep edge endpoints as UUIDs; use indices separately for GPU

- Always set `source`/`target` (and `from`/`to`) to the UUID strings.
- Keep `sourceIndex`/`targetIndex` for numeric indices.

```ts
// frontend/src/hooks/useGraphDataQuery.ts (suggested change)
return {
  id: `${e.source}-${e.target}`,
  // Endpoints as UUIDs
  source: e.source,
  target: e.target,
  from: e.source,
  to: e.target,
  // Separate numeric indices
  sourceIndex: nodeIndexMap.get(String(e.source)) ?? -1,
  targetIndex: nodeIndexMap.get(String(e.target)) ?? -1,
  edge_type: edgeType,
  weight: e.weight || 1,
  strength,
  created_at: e.created_at,
  updated_at: e.updated_at
};
```

C) Stop deriving `properties.connections` from normalized degree centrality

- Remove or ignore this derivation for display. The authoritative count should come from edge-based degree.

```ts
// frontend/src/hooks/useGraphDataQuery.ts (suggested edit)
properties: {
  // ... keep centrality values as-is
  degree_centrality: plainNode.degree_centrality || 0,
  // Remove these two derived fields or keep them separate for legacy UI only
  // degree: Math.round((plainNode.degree_centrality || 0) * 100),
  // connections: Math.round((plainNode.degree_centrality || 0) * 100),
}
```

---

## Why This Fix Works

- Counting edges by UUID endpoints gives the true neighbor count, independent of graph size and normalization.
- Consistent UUID endpoints ensure edge-node joins work reliably.
- The UI will show actual relationships, even if centrality jobs haven’t run yet.

---

## Optional Enhancements

- If you need the degree count in more places, memoize the degree map in a context or selector.
- Add a small badge tooltip explaining the count: "Number of edges incident to this node in the current graph view."
- Keep `degree_centrality` for metrics and filtering; use degree-count strictly for display.

---

## Quick Test Plan

1. Open a node you know has several edges; confirm the "Related Nodes" count matches the visible connections.
2. Select a node with no edges; count should be 0.
3. Toggle filters (node types/edge types) and ensure the count updates with the filtered graph.
4. Verify no errors in the console about mismatched endpoint types.

