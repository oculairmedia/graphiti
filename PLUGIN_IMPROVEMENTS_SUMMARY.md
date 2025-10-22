# Graphiti OpenCode Plugin - Hardening Summary

## Critical Fix: SDK Endpoint Auto-Detection

### Problem Identified
**Original Issue**: Plugin hung OpenCode after first message round due to hardcoded `localhost:4096` SDK endpoint being unreachable, causing infinite wait with no timeout.

### Solution Implemented

#### 1. Smart SDK URL Resolution (Lines 27-43)
```javascript
const resolveOpencodeSdkBaseUrl = () => {
  // Priority 1: Explicit environment variable
  const explicit = process.env.GRAPHITI_SDK_URL?.trim()
  if (explicit) {
    return { url: explicit.replace(/\/$/, ""), source: "env" }
  }

  // Priority 2: Auto-detect from OpenCode client config
  try {
    const base = client?._client?.getConfig?.()?.baseUrl
    if (typeof base === "string" && base.length > 0) {
      return { url: base.replace(/\/$/, ""), source: "client" }
    }
  } catch (error) {
    console.warn("[Graphiti] Failed to read OpenCode client config", error)
  }

  // Priority 3: Safe fallback
  return { url: "http://127.0.0.1:4096", source: "default" }
}
```

**Resolution Priority:**
1. `GRAPHITI_SDK_URL` environment variable (explicit override)
2. `client._client.getConfig().baseUrl` (auto-detected from running OpenCode)
3. `http://127.0.0.1:4096` (safe fallback)

#### 2. Runtime Logging (Lines 81-95)
```javascript
if (SDK_URL_SOURCE === "default") {
  log("warn", "[Graphiti] OpenCode SDK URL fallback in use", {
    sdkUrl: GRAPHITI_SDK_URL,
  })
} else if (SDK_URL_SOURCE === "client") {
  log("debug", "[Graphiti] OpenCode SDK URL resolved from client config", {
    sdkUrl: GRAPHITI_SDK_URL,
  })
} else {
  log("debug", "[Graphiti] OpenCode SDK URL provided via environment", {
    sdkUrl: GRAPHITI_SDK_URL,
  })
}
```

**Benefits:**
- Immediate visibility into which endpoint is being used
- Warning when fallback is active (potential misconfiguration)
- Debug logging shows successful auto-detection

#### 3. SDK Timeout Protection (Lines 207-242)
```javascript
async function summarizeWithSDK(conversationText) {
  const { signal, cleanup } = createTimeoutController(10000) // 10s timeout

  try {
    const response = await fetch(`${GRAPHITI_SDK_URL}/api/v1/session/prompt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        parts: [{ type: "text", text: summaryPrompt }],
      }),
      ...(signal ? { signal } : {}), // Timeout enforced
    })
    // ... handle response
  } catch (error) {
    log("debug", "[Graphiti] SDK summarization failed, using fallback", {
      message: error.message,
      sdkUrl: GRAPHITI_SDK_URL,
    })
    return conversationText.substring(0, 500) + "..."
  } finally {
    cleanup()
  }
}
```

**Protection:**
- 10-second timeout prevents infinite hangs
- Graceful fallback to truncation if SDK unavailable
- Logs include SDK URL for debugging

## Complete Hardening Checklist

✅ **Bounded Buffers** (Lines 32, 283-290, 369-374, 391-396)
- `MAX_BUFFER_CAP` prevents memory exhaustion
- FIFO truncation on overflow
- Warnings logged when cap hit

✅ **Retry with Exponential Backoff** (Lines 111-183)
- Up to 3 retries for API calls
- Exponential delays: 2s, 4s, 6s
- All retries logged with attempt number

✅ **Lifecycle Management** (Lines 11-20, 299-325, 457-466)
- `dispose()` hook for clean shutdowns
- Timer cleanup on session end
- `globalThis` tracking prevents duplicate instances

✅ **Execution Lock** (Lines 327-344, 355-455)
- `withLock()` serializes event handlers
- Prevents race conditions
- Catches all handler exceptions

✅ **Config Validation** (Lines 22-56)
- `toInt()` validates all numeric env vars
- Safe fallbacks for malformed input
- **NEW**: `resolveOpencodeSdkBaseUrl()` for smart endpoint detection

✅ **Error Recovery** (Lines 227-294)
- Failed flushes restore buffer snapshots
- No silent data loss
- Full error context in logs

✅ **Tool Deduplication** (Lines 399-405)
- Prevents duplicate tool tracking
- Clean per-turn tool lists

✅ **SDK Timeout** (Lines 207-242)
- **NEW**: 10-second timeout on summarization
- Graceful fallback to truncation
- Detailed error logging

## Configuration Reference

```bash
# Core Settings
export GRAPHITI_API_URL="http://192.168.50.90:8003"
export GRAPHITI_AUTO_COLLECT="true"
export GRAPHITI_GROUP_ID="opencode-graphiti"

# SDK Auto-Detection (NEW)
export GRAPHITI_SDK_URL=""  # Empty = auto-detect from OpenCode client

# Buffer Management
export GRAPHITI_BUFFER_SIZE="6"      # Messages before flush
export GRAPHITI_BUFFER_CAP="100"     # Absolute max buffer size
export GRAPHITI_FLUSH_INTERVAL="60000"  # Auto-flush interval (ms)

# Retry Logic
export GRAPHITI_SEND_RETRIES="3"     # Max API retry attempts
export GRAPHITI_RETRY_DELAY="2000"   # Base retry delay (ms)

# Logging
export GRAPHITI_LOG_LEVEL="info"     # error|warn|info|debug
```

## Testing

```bash
✓ node --check .opencodes/plugin/graphiti-context-collector.js
✓ node --check graphiti-context-collector-fixed.js
```

**Both files:**
- 507 lines
- Syntax validated
- Identical content (mirrored for parity)

## Deployment Status

- **Active Plugin**: `.opencodes/plugin/graphiti-context-collector.js`
- **Reference Copy**: `graphiti-context-collector-fixed.js`
- **Backup**: `.opencode.backup/plugin/` (TypeScript versions)

## Expected Behavior

When OpenCode starts with the plugin enabled:

```
[Graphiti] Context collector enabled for graphiti
[Graphiti] Group ID: opencode-graphiti
[Graphiti] OpenCode SDK URL resolved from client config {"sdkUrl":"http://127.0.0.1:4096"}
[Graphiti] Grouping 6 messages, auto-flush every 60000ms
```

If SDK is unavailable:
```
[Graphiti] SDK summarization failed, using fallback {"message":"...","sdkUrl":"http://127.0.0.1:4096"}
```

## Next Steps

1. **Deploy**: Copy to `/root/.config/opencode/plugin/`
2. **Test**: Run full conversation cycle
3. **Monitor**: Check logs for SDK resolution source
4. **Verify**: Confirm no hangs after message rounds

---

**Status**: Ready for production testing
**Last Updated**: 2025-10-10
**Test Status**: Syntax validated, ready for runtime verification
