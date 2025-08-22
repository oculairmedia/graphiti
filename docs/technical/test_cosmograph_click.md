# Testing Cosmograph Click Handler

## Changes Made
1. Moved onClick handler to root level of config object (as per Cosmograph documentation)
2. Enhanced canvas click handler with selection API as backup
3. Added nodeDataMap to preserve original node data

## Test Steps
1. Open http://192.168.50.90:3000/cosmograph in browser
2. Wait for graph to load
3. Open browser console (F12)
4. Click on any node
5. Check console for:
   - "onClick event fired - node:" message (if onClick works)
   - "Canvas clicked at coordinates:" message (backup handler)
   - Node details panel should appear with information

## Expected Behavior
- Clicking a node should show the node details panel
- Panel should display node properties including:
  - Name/Title
  - Summary
  - Entity type
  - Created/Updated timestamps
  - UUID
  - Centrality scores

## Console Commands for Testing
```javascript
// Check if cosmograph instance exists
console.log('Cosmograph instance:', window.cosmographInstance);

// Get selected nodes programmatically
window.cosmographInstance.getSelectedNodes();

// Test node selection
window.cosmographInstance.selectNodeByIndex(0);

// Get all nodes
const nodes = window.cosmographInstance.getAdjacentNodes(0);
console.log('Adjacent nodes:', nodes);
```