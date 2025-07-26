# Backend Data Structure Analysis

## Sample from Rust Backend API (`/api/visualize`)

The backend returns data in this structure:

```json
{
  "data": {
    "nodes": [
      {
        "id": "d45a99cf-9b62-40f5-9521-b3b8a213f5b5",
        "label": "claude_code", 
        "node_type": "Entity",
        "properties": {
          "created_at": "2025-07-25T20:44:05.563697+00:00",
          "labels": ["Entity"],
          "group_id": "claude_conversations",
          "degree_centrality": 0,
          "name_embedding": "Vec32(...)",
          "type": "Entity",
          "name": "claude_code",
          "summary": "...",
          "uuid": "d45a99cf-9b62-40f5-9521-b3b8a213f5b5"
        }
      }
    ],
    "edges": [...],
    "stats": {
      "total_nodes": 131,
      "total_edges": 151,
      "node_types": {...},
      "avg_degree": 2.3
    }
  },
  "has_more": false,
  "execution_time_ms": 25
}
```

## Key Observations for Cosmograph Data Kit

1. **Node Structure**: 
   - `id`: String UUID ✅
   - `label`: String ✅  
   - `node_type`: String ✅
   - `properties.degree_centrality`: Number ✅
   - `properties.type`: String (same as node_type) ✅

2. **Data Ready for Cosmograph**: The structure matches what we're preparing in GraphCanvasV2:
   ```javascript
   const rawPoints = nodes.map(node => ({
     id: String(node.id),                    // ✅ Available
     label: String(node.label || node.id),   // ✅ Available  
     type: String(node.node_type || 'Entity'), // ✅ Available
     degree_centrality: Number(node.properties?.degree_centrality || 0) // ✅ Available
   }));
   ```

3. **Issue Hypothesis**: Data structure is correct. The "points configuration is invalid" error is likely due to:
   - Configuration nesting issue (fixed in latest code)
   - Callback function format
   - Missing fields in some nodes

## Backend Cleanup Needed

The Rust backend has unused website generation code:
- `/cosmos` route - HTML page generation
- `/cosmos-test` route - Test page
- `/cosmograph` route - Another HTML page
- Static file serving for old website

These should be removed as we now use the React frontend exclusively.