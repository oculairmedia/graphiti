#!/bin/bash

echo "=== Live Plugin Monitoring ==="
echo ""
echo "This will monitor Graphiti API logs in real-time."
echo "Start an OpenCode conversation and watch for activity."
echo ""
echo "What to look for:"
echo "  • '[Graphiti] Context collector enabled' - Plugin loaded"
echo "  • '[Graphiti] ✓ Sent message: ...' - Messages being sent"
echo "  • 'POST /messages' in API logs - API receiving requests"
echo ""
echo "Press Ctrl+C to stop monitoring"
echo ""
echo "Starting in 3 seconds..."
sleep 3

docker logs graphiti-graph-1 -f --tail=20 2>&1 | grep --line-buffered -E "POST /messages|messages|episode|group_id"
