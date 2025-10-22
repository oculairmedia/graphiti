# Graphiti Plugin Testing Guide

## Prerequisites

1. **Update Global Plugin** (if not already done):
```bash
cp /opt/stacks/graphiti/.opencodes/plugin/graphiti-context-collector.js \
   /root/.config/opencode/plugin/
```

2. **Verify File Size**:
```bash
wc -l /root/.config/opencode/plugin/graphiti-context-collector.js
# Should show: 507 lines
```

## Testing Steps

### 1. Quick Health Check
```bash
cd /opt/stacks/graphiti
./test_plugin_health.sh
```

**Expected Output:**
- ✓ API is UP
- ✓ Message endpoint works
- ✓ Plugin installed

### 2. Start OpenCode with Logging

Open a **new terminal** and start monitoring:
```bash
cd /opt/stacks/graphiti
./monitor_plugin_live.sh
```

### 3. Start OpenCode Session

In **another terminal**, start OpenCode:
```bash
cd /opt/stacks/graphiti
opencode
```

**Look for startup messages:**
```
[Graphiti] Context collector enabled for graphiti
[Graphiti] Group ID: opencode-graphiti
[Graphiti] OpenCode SDK URL resolved from client config {"sdkUrl":"..."}
[Graphiti] Grouping 6 messages, auto-flush every 60000ms
```

### 4. Test Conversation

Send messages to Claude in OpenCode. After **6 messages** (3 user + 3 assistant), the buffer should flush.

**What to watch for in monitor terminal:**
```
INFO:     127.0.0.1:xxxxx - "POST /messages HTTP/1.1" 202 Accepted
```

### 5. Verify Ingestion

After sending 6+ messages, check if data was stored:
```bash
./test_plugin_health.sh
```

Look at section **"6. Searching for OpenCode episodes"** - should show new episodes.

### 6. Check Detailed Logs

If something's wrong, check OpenCode console output:
```bash
# Look for plugin errors
grep -i "graphiti" ~/.opencode/logs/* | tail -20

# Or check console where you ran opencode
# Look for [Graphiti] log messages
```

## What Success Looks Like

### ✅ Successful Operation

**Console (OpenCode startup):**
```
[Graphiti] Context collector enabled for graphiti
[Graphiti] Group ID: opencode-graphiti
[Graphiti] OpenCode SDK URL resolved from client config {"sdkUrl":"http://127.0.0.1:4096"}
[Graphiti] Grouping 6 messages, auto-flush every 60000ms
```

**Console (after 6 messages):**
```
[Graphiti] ✓ Sent message: Updated plugin configuration to improve...
```

**API Logs (monitor_plugin_live.sh):**
```
INFO:     127.0.0.1:50123 - "POST /messages HTTP/1.1" 202 Accepted
```

**Health Check:**
```
6. Searching for OpenCode episodes in Graphiti...
   ✓ Found 8 OpenCode episodes
   Recent episodes:
     - Updated plugin configuration to improve stability...
     - Fixed SDK endpoint auto-detection...
```

### ❌ Common Issues

#### Issue: "SDK unreachable (plugin will use truncation fallback)"
**Impact:** Low - Summaries will be truncated instead of AI-generated
**Fix:** This is expected if OpenCode SDK isn't running. Plugin will still work.

#### Issue: No "[Graphiti] Context collector enabled" message
**Problem:** Plugin not loading
**Check:**
1. Plugin file in correct location: `/root/.config/opencode/plugin/`
2. File is named `graphiti-context-collector.js`
3. Syntax is valid: `node --check /root/.config/opencode/plugin/graphiti-context-collector.js`

#### Issue: Messages sent but not in Graphiti
**Problem:** Queue worker not processing
**Check:**
```bash
docker logs graphiti-graphiti-worker-1 -f
# Should show processing activity
```

#### Issue: "[Graphiti] Failed to send" errors
**Problem:** API connection issues
**Check:**
```bash
curl http://192.168.50.90:8003/docs
# Should return HTML
```

## Environment Variables

Optional configuration (set before running OpenCode):

```bash
# Core Settings
export GRAPHITI_API_URL="http://192.168.50.90:8003"
export GRAPHITI_AUTO_COLLECT="true"  # Set to "false" to disable
export GRAPHITI_GROUP_ID="opencode-custom"  # Custom group ID

# SDK Endpoint (usually auto-detected)
export GRAPHITI_SDK_URL="http://127.0.0.1:4096"

# Buffer Tuning
export GRAPHITI_BUFFER_SIZE="6"      # Messages before flush (lower = more frequent)
export GRAPHITI_BUFFER_CAP="100"     # Max buffer size
export GRAPHITI_FLUSH_INTERVAL="60000"  # Auto-flush every 60s

# Retry Settings
export GRAPHITI_SEND_RETRIES="3"
export GRAPHITI_RETRY_DELAY="2000"

# Logging
export GRAPHITI_LOG_LEVEL="debug"    # For verbose output
```

## Troubleshooting Commands

```bash
# Check API health
curl http://192.168.50.90:8003/docs

# Check if messages are queued
docker logs graphiti-graphiti-queued-1 --tail 50

# Check worker processing
docker logs graphiti-graphiti-worker-1 -f

# Search for your episodes
curl -X POST http://192.168.50.90:8003/search \
  -H "Content-Type: application/json" \
  -d '{"query":"opencode","group_ids":["opencode-graphiti"],"limit":10}' | jq .

# Check plugin file size
wc -l /root/.config/opencode/plugin/graphiti-context-collector.js

# Validate plugin syntax
node --check /root/.config/opencode/plugin/graphiti-context-collector.js
```

## Quick Test Sequence

```bash
# 1. Update plugin
cp /opt/stacks/graphiti/.opencodes/plugin/graphiti-context-collector.js \
   /root/.config/opencode/plugin/

# 2. Verify installation
wc -l /root/.config/opencode/plugin/graphiti-context-collector.js
# Should show: 507 lines

# 3. Run health check
cd /opt/stacks/graphiti && ./test_plugin_health.sh

# 4. Start monitoring (in separate terminal)
cd /opt/stacks/graphiti && ./monitor_plugin_live.sh

# 5. Start OpenCode (in separate terminal)
cd /opt/stacks/graphiti && opencode

# 6. Send 6+ messages to Claude

# 7. Check health again
./test_plugin_health.sh
```

## Expected Timeline

- **Immediately on startup:** Plugin initialization logs
- **After 6 messages:** First buffer flush
- **Every 60 seconds:** Auto-flush of pending messages
- **On session end:** Final flush of remaining buffer

---

**Next Steps:** Run through the Quick Test Sequence above to verify everything works.
