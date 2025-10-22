# Graphiti OpenCode Plugins

Automatic context collection for Graphiti knowledge graph integration.

## Quick Start

### 1. Install Plugins Globally

```bash
# Copy to global plugin directory
cp /opt/stacks/graphiti/.opencode/plugin/*.js /root/.config/opencode/plugin/

# Or create symlinks for auto-updates
ln -s /opt/stacks/graphiti/.opencode/plugin/graphiti-context-collector.js /root/.config/opencode/plugin/
ln -s /opt/stacks/graphiti/.opencode/plugin/graphiti-integration.js /root/.config/opencode/plugin/
```

### 2. Start Graphiti Services

```bash
cd /opt/stacks/graphiti
docker-compose up -d graph
```

### 3. Use OpenCode Normally

The plugins will automatically capture and summarize your conversations!

## What Gets Captured

- ✅ User and assistant messages (buffered in groups of 6)
- ✅ AI-generated summaries of conversations
- ✅ Files mentioned in conversations
- ✅ Git context (branch, commit)
- ✅ Tools used during development
- ✅ Session start/end markers

## Configuration

### Environment Variables

```bash
# Optional - customize behavior
export GRAPHITI_API_URL="http://localhost:8003"      # API endpoint
export GRAPHITI_AUTO_COLLECT="true"                  # Enable/disable
export GRAPHITI_BUFFER_SIZE="6"                      # Messages before flush
export GRAPHITI_FLUSH_INTERVAL="60000"               # Auto-flush (ms)
export GRAPHITI_GROUP_ID="opencode-myproject"        # Override GROUP_ID
```

### Default Behavior

- **Buffer Size**: 6 messages (3 user + 3 assistant turns)
- **Auto-flush**: Every 60 seconds
- **GROUP_ID**: Automatically set to `opencode-{project-name}`
- **Enabled**: Yes (set `GRAPHITI_AUTO_COLLECT=false` to disable)

## Verify It's Working

When you start OpenCode, you should see:

```
[Graphiti] Context collector enabled for graphiti
[Graphiti] Group ID: opencode-graphiti
[Graphiti] Grouping 6 messages, auto-flush every 60000ms
```

After conversations, you'll see:

```
[Graphiti] ✓ Sent: User requested to fix build errors in frontend c...
```

## Query Your Knowledge

Use the Graphiti MCP server or API:

```bash
# Via Graphiti MCP (if configured in OpenCode)
/kg "What did I work on today?"

# Via API
curl -X POST http://localhost:8003/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "frontend refactoring",
    "group_ids": ["opencode-graphiti"],
    "max_facts": 10
  }'
```

## Files

- **`graphiti-context-collector.js`**: Main plugin - automatic capture with AI summarization
- **`graphiti-integration.js`**: Helper plugin - utility functions for Graphiti
- **`README.md`**: This file

## How It Works

1. **Buffer**: Collects 6 messages (configurable)
2. **Summarize**: Uses OpenCode SDK to create AI summary
3. **Extract**: Pulls out files, git info, tools used
4. **Send**: Posts single episode to Graphiti
5. **Organize**: Automatic GROUP_ID based on project

## Example Episode

```
Name: "User requested to fix build errors in frontend c..."
Content:
User requested to fix build errors in frontend components.
Assistant read error logs, identified TypeScript issues in
GraphCanvas.tsx, and applied fixes using Edit tool.

Project: graphiti
Branch: main
Commit: a1b2c3d
Messages: 6
Files: GraphCanvas.tsx, useGraphData.ts
Time: 2025-01-09T20:30:45.123Z
```

## Troubleshooting

### Plugins Not Loading

```bash
# Check they exist
ls -la /root/.config/opencode/plugin/

# Verify JavaScript (not TypeScript)
file /root/.config/opencode/plugin/graphiti-*.js

# Check permissions
chmod 644 /root/.config/opencode/plugin/*.js
```

### No Episodes in Graphiti

```bash
# Check API is running
curl http://localhost:8003/health

# Verify environment
echo $GRAPHITI_API_URL

# Check for errors in OpenCode console
# Look for [Graphiti] messages
```

### Line Ending Issues

If you see `/usr/bin/env: 'python3\r'`:

```bash
# Fix line endings
sed -i 's/\r$//' /root/.config/opencode/plugin/*.js
```

## Full Documentation

See [docs/integrations/OPENCODE_PLUGIN_INTEGRATION.md](../../docs/integrations/OPENCODE_PLUGIN_INTEGRATION.md) for:

- Detailed architecture
- Development history
- Advanced configuration
- Integration with MCP server
- Complete troubleshooting guide

## Related

- [Graphiti MCP Server](../../mcp_server/README.md)
- [Graphiti API Documentation](../../server/README.md)
- [Project Setup Guide](../../CLAUDE.md)

## Version

**Current**: v3 - JavaScript with AI Summarization
**Previous**: v2 - JavaScript Granular (deprecated)
**Original**: v1 - TypeScript with Custom Tools (deprecated)

See `.opencode.backup/plugin/` for old TypeScript versions.
