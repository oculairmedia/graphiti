#!/bin/bash

# Test script for version tracking and sync functionality

echo "=== Testing Version Tracking and Sync ==="
echo

# Test 1: Get current sequence
echo "Test 1: Getting current sequence number..."
curl -s http://localhost:3000/api/graph/sequence | jq .
echo

# Test 2: Get changes since sequence 0
echo "Test 2: Getting all changes (since sequence 0)..."
curl -s "http://localhost:3000/api/graph/changes?since=0&limit=5" | jq '.[] | {sequence, operation, nodes_added: .nodes_added | length, edges_added: .edges_added | length}'
echo

# Test 3: Get recent changes
echo "Test 3: Getting recent changes (last 3 deltas)..."
CURRENT_SEQ=$(curl -s http://localhost:3000/api/graph/sequence | jq -r .sequence)
SINCE_SEQ=$((CURRENT_SEQ - 3))
if [ $SINCE_SEQ -lt 0 ]; then
    SINCE_SEQ=0
fi
echo "Current sequence: $CURRENT_SEQ, fetching since: $SINCE_SEQ"
curl -s "http://localhost:3000/api/graph/changes?since=$SINCE_SEQ&limit=10" | jq '.[] | {sequence, timestamp, operation}'
echo

# Test 4: Get specific nodes by IDs (if they exist)
echo "Test 4: Testing node fetch endpoint..."
# First, get some node IDs from the graph
NODE_IDS=$(curl -s http://localhost:3000/api/graph/data | jq -r '.nodes[0:3] | .[].id' | tr '\n' ',' | sed 's/,$//')
if [ -n "$NODE_IDS" ]; then
    echo "Fetching nodes: $NODE_IDS"
    curl -s "http://localhost:3000/api/graph/nodes?ids=$NODE_IDS" | jq '.[] | {id, label, node_type}'
else
    echo "No nodes available to test"
fi
echo

# Test 5: Get specific edges by pairs
echo "Test 5: Testing edge fetch endpoint..."
# Get some edge pairs from the graph
EDGE_PAIRS=$(curl -s http://localhost:3000/api/graph/data | jq -r '.edges[0:3] | .[] | "\(.from),\(.to)"' | head -1)
if [ -n "$EDGE_PAIRS" ]; then
    echo "Fetching edge pairs: $EDGE_PAIRS"
    curl -s "http://localhost:3000/api/graph/edges?pairs=$EDGE_PAIRS" | jq '.[] | {from, to, edge_type, weight}'
else
    echo "No edges available to test"
fi
echo

echo "=== Version Sync Tests Complete ==="