#!/bin/bash

# Test real-time graph updates

echo "Testing real-time graph update..."
echo "Adding a test node via API..."

# Generate a unique ID for the test node
NODE_ID="test-node-$(date +%s)"
TIMESTAMP=$(date -Iseconds)

# Add a test node
curl -X POST http://localhost:3000/api/updates/nodes \
  -H "Content-Type: application/json" \
  -d "{
    \"nodes\": [{
      \"id\": \"$NODE_ID\",
      \"label\": \"TEST NODE - $TIMESTAMP\",
      \"node_type\": \"TestNode\",
      \"summary\": \"This is a test node added at $TIMESTAMP to verify real-time updates\",
      \"properties\": {
        \"test\": true,
        \"created_at\": \"$TIMESTAMP\",
        \"degree_centrality\": 0.5
      }
    }]
  }" | jq '.'

echo ""
echo "Test node added with ID: $NODE_ID"
echo "Check the graph visualization - the node should appear WITHOUT refreshing the page!"
echo ""
echo "To add an edge to connect this test node to an existing node, run:"
echo "curl -X POST http://localhost:3000/api/updates/edges -H \"Content-Type: application/json\" -d '{\"edges\": [{\"from\": \"$NODE_ID\", \"to\": \"<existing-node-id>\", \"edge_type\": \"test_connection\", \"weight\": 1}]}'"