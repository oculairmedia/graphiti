#!/bin/bash

echo "=== Graphiti Plugin Health Check ==="
echo ""

# 1. Check if Graphiti API is accessible
echo "1. Checking Graphiti API (http://192.168.50.90:8003)..."
if curl -s -f http://192.168.50.90:8003/docs > /dev/null 2>&1; then
    echo "   ✓ API is UP"
else
    echo "   ✗ API is DOWN or unreachable"
    exit 1
fi

# 2. Test message endpoint
echo ""
echo "2. Testing /messages endpoint..."
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST http://192.168.50.90:8003/messages \
  -H "Content-Type: application/json" \
  -d '{
    "group_id": "test-health-check",
    "messages": [{
      "content": "Health check test message",
      "name": "Plugin health check",
      "role": "assistant",
      "role_type": "assistant",
      "timestamp": "'$(date -Iseconds)'",
      "source_description": "health-check"
    }]
  }')

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 201 ]; then
    echo "   ✓ Message endpoint working (HTTP $HTTP_CODE)"
else
    echo "   ✗ Message endpoint failed (HTTP $HTTP_CODE)"
    echo "   Response: $BODY"
fi

# 3. Check recent ingestion
echo ""
echo "3. Checking recent message ingestion..."
RECENT=$(docker logs graphiti-graph-1 2>&1 | grep -i "POST /messages" | tail -5)
if [ -n "$RECENT" ]; then
    echo "   ✓ Recent API activity detected:"
    echo "$RECENT" | sed 's/^/     /'
else
    echo "   ⚠ No recent /messages activity in logs"
fi

# 4. Check OpenCode SDK availability
echo ""
echo "4. Checking OpenCode SDK (localhost:4096)..."
if timeout 2 curl -s -f http://localhost:4096/ > /dev/null 2>&1; then
    echo "   ✓ SDK is accessible"
else
    echo "   ⚠ SDK unreachable (plugin will use truncation fallback)"
fi

# 5. Check plugin file
echo ""
echo "5. Checking plugin installation..."
if [ -f "/root/.config/opencode/plugin/graphiti-context-collector.js" ]; then
    echo "   ✓ Plugin installed at /root/.config/opencode/plugin/"
    SIZE=$(wc -l < /root/.config/opencode/plugin/graphiti-context-collector.js)
    echo "   File size: $SIZE lines"
else
    echo "   ✗ Plugin NOT installed in global location"
    echo "   Run: cp .opencodes/plugin/*.js /root/.config/opencode/plugin/"
fi

# 6. Query Graphiti for test episodes
echo ""
echo "6. Searching for OpenCode episodes in Graphiti..."
SEARCH_RESULT=$(curl -s -X POST http://192.168.50.90:8003/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "opencode",
    "group_ids": ["opencode-graphiti"],
    "limit": 5
  }')

EPISODE_COUNT=$(echo "$SEARCH_RESULT" | grep -o '"uuid"' | wc -l)
if [ "$EPISODE_COUNT" -gt 0 ]; then
    echo "   ✓ Found $EPISODE_COUNT OpenCode episodes"
    echo "   Recent episodes:"
    echo "$SEARCH_RESULT" | jq -r '.edges[]? | "     - \(.fact)"' 2>/dev/null | head -3
else
    echo "   ⚠ No OpenCode episodes found yet (plugin may not have flushed)"
fi

echo ""
echo "=== Summary ==="
echo "Plugin should be working if:"
echo "  • API is UP ✓"
echo "  • Message endpoint works ✓"
echo "  • Plugin file installed ✓"
echo ""
echo "To verify live operation:"
echo "  1. Start a new OpenCode session"
echo "  2. Look for '[Graphiti] Context collector enabled' in console"
echo "  3. Send 6+ messages to trigger a flush"
echo "  4. Run: docker logs graphiti-graph-1 -f | grep 'POST /messages'"
echo "  5. Check this script again to see new episodes"
