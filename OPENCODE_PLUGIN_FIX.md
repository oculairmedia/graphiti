# OpenCode Graphiti Plugin Fix

## Problem
The plugin was using the wrong API endpoint: `/v1/add-episode` (which doesn't exist)

## Solution
Changed to use the correct Graphiti API endpoint: `/messages`

## Changes Made

### API Endpoint
- **Before**: `POST /v1/add-episode`
- **After**: `POST /messages`

### Request Format
- **Before**:
```json
{
  "name": "...",
  "episode_body": "...",
  "source": "...",
  "group_id": "..."
}
```

- **After**:
```json
{
  "group_id": "...",
  "messages": [{
    "content": "...",
    "name": "...",
    "role_type": "system",
    "role": "opencode",
    "timestamp": "2025-10-09T20:00:00.000Z",
    "source_description": "..."
  }]
}
```

## Testing
```bash
curl -X POST http://localhost:8003/messages \
  -H "Content-Type: application/json" \
  -d '{
    "group_id": "opencode-test",
    "messages": [{
      "content": "Test message",
      "name": "Test",
      "role_type": "system",
      "role": "opencode",
      "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%S.000Z)'",
      "source_description": "test"
    }]
  }'
```

Expected response:
```json
{"message":"Queued 1 messages for processing","success":true}
```

## Files Changed
- `/root/.config/opencode/plugin/graphiti-context-collector.js`
- Backup: `graphiti-context-collector.js.bak`

## Next Steps
Restart OpenCode to load the fixed plugin.
