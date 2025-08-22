# Real-Time Update Investigation

## Problem Statement

The real-time graph update mechanism is working correctly for data flow (webhook → Rust server → frontend), but fails when applying updates to the Cosmograph visualization with the error:

```
Error: Binder Error: table cosmograph_points has 11 columns but 7 values were supplied
```

## Current Status

✅ **Working Components:**
- Graphiti API → Rust Server webhook delivery
- Rust Server webhook processing and DuckDB updates  
- WebSocket broadcasting from Rust Server to Frontend
- Frontend delta message reception and queuing

❌ **Failing Component:**
- Cosmograph `addPoints()` call with incomplete data structure

## Data Flow Analysis

### 1. Graphiti API → Rust Server
**Webhook Payload:**
```json
{
  "event_type": "data_ingestion",
  "operation": "add_episode", 
  "nodes": [{
    "uuid": "realtime-node-001",
    "name": "Real-time Update Node 1",
    "labels": ["Entity"],
    "summary": "Test node for real-time updates",
    "attributes": {...}
  }]
}
```

### 2. Rust Server Transformation
**File:** `graph-visualizer-rust/src/main.rs:1920-1947`
```rust
fn transform_graphiti_nodes(graphiti_nodes: Vec<GraphitiNode>) -> Vec<Node> {
    graphiti_nodes.into_iter().map(|gn| {
        Node {
            id: gn.uuid,
            label: gn.name,
            node_type: gn.labels.first().unwrap_or(&"Unknown".to_string()).clone(),
            summary: gn.summary,
            properties: {...}
        }
    }).collect()
}
```

### 3. Frontend Delta Processing (INCOMPLETE)
**File:** `frontend/src/components/GraphCanvas.tsx:535-541`
```typescript
// Current transformation - MISSING REQUIRED FIELDS
pointsToAdd.push({
  id: node.id,
  label: node.label || node.id,
  node_type: node.node_type || 'Unknown',
  size: node.size || 1,
  ...node.properties
});
```

### 4. Cosmograph Expected Structure
**File:** `frontend/src/components/GraphCanvas.tsx:2281-2295`
```typescript
// Complete transformation used in setData (11 fields)
const transformedNodes = updatedNodes.map(node => ({
  id: String(node.id),
  label: String(node.label || node.id),
  node_type: String(node.node_type || 'Unknown'),
  centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
  cluster: String(node.node_type || 'Unknown'),
  clusterStrength: 0.7,
  degree_centrality: Number(node.properties?.degree_centrality || 0),
  pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
  betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
  eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0),
  created_at: node.properties?.created_at || node.created_at || node.properties?.created || null,
  created_at_timestamp: (node.properties?.created_at || node.created_at || node.properties?.created) ? new Date(node.properties?.created_at || node.created_at || node.properties?.created).getTime() : null
}));
```

## Root Cause

The **delta update transformation** in `GraphCanvas.tsx` only provides 7 fields, but Cosmograph's internal DuckDB table `cosmograph_points` expects 11 columns. The frontend has two different transformation paths:

1. **Initial Load Path:** Uses complete 11-field transformation (working)
2. **Delta Update Path:** Uses incomplete 7-field transformation (broken)

## Solution Options

### Option 1: Fix Frontend Transformation (Recommended)
**Approach:** Update delta processing to use the same complete transformation as `setData`
**Files to modify:** `frontend/src/components/GraphCanvas.tsx:535-541`
**Pros:** Minimal change, leverages existing working code
**Cons:** None

### Option 2: Use setData Instead of addPoints  
**Approach:** Fall back to `setData` with complete dataset for real-time updates
**Pros:** Guaranteed compatibility
**Cons:** Less efficient, requires full data reload

### Option 3: Fix Rust Server Output
**Approach:** Ensure Rust server calculates and sends all required centrality fields
**Files to modify:** `graph-visualizer-rust/src/main.rs`
**Pros:** More complete data from source
**Cons:** Requires centrality calculations in Rust

### Option 4: Investigate Cosmograph Schema
**Approach:** Determine exact 11 columns Cosmograph expects
**Pros:** Perfect compatibility
**Cons:** Requires Cosmograph internals investigation

## Recommended Fix

Update the delta transformation in `GraphCanvas.tsx` to match the complete transformation:

```typescript
// Replace lines 535-541 with:
pointsToAdd.push({
  id: String(node.id),
  label: String(node.label || node.id),
  node_type: String(node.node_type || 'Unknown'),
  centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
  cluster: String(node.node_type || 'Unknown'),
  clusterStrength: 0.7,
  degree_centrality: Number(node.properties?.degree_centrality || 0),
  pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
  betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
  eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0),
  created_at: node.properties?.created_at || node.created_at || node.properties?.created || null,
  created_at_timestamp: (node.properties?.created_at || node.created_at || node.properties?.created) ? new Date(node.properties?.created_at || node.created_at || node.properties?.created).getTime() : null
});
```

## Testing

After implementing the fix:

1. **Test real-time updates:**
   ```bash
   curl -X POST http://192.168.50.90:8003/add-episode \
     -H "Content-Type: application/json" \
     -d '{"name": "Test Episode", "content": "Real-time test", "source": "manual"}'
   ```

2. **Verify in browser console:**
   - No DuckDB binder errors
   - Successful delta application logs
   - Visual node appearance in graph

3. **Check Rust server logs:**
   ```bash
   docker logs graphiti-graph-visualizer-rust-1
   ```

## Files Involved

- `frontend/src/components/GraphCanvas.tsx` - Delta processing (needs fix)
- `frontend/src/hooks/useGraphDataQuery.ts` - Data fetching and transformation
- `graph-visualizer-rust/src/main.rs` - Webhook processing and node transformation
- `server/graph_service/webhooks.py` - Webhook emission
- `server/graph_service/routers/ingest.py` - Data ingestion triggers
