# OpenCode Plugin Integration

This document describes the OpenCode plugin integration for automatic Graphiti knowledge graph population.

## Overview

The OpenCode plugins automatically capture development conversations and send AI-summarized episodes to Graphiti's knowledge graph. This enables:

- **Automatic Context Collection**: No manual intervention needed
- **AI-Powered Summarization**: Uses OpenCode SDK to create concise summaries
- **Project-Based Organization**: Dynamic GROUP_ID based on current project
- **Intelligent Grouping**: Buffers conversations before summarization
- **Git Context Tracking**: Captures branch, commit, and file information

## Architecture

### Plugin Locations

1. **Global Plugins**: `/root/.config/opencode/plugin/` (recommended)
   - Load for all OpenCode sessions
   - No per-project configuration needed

2. **Project Plugins**: `.opencode/plugin/` (optional)
   - Project-specific customization
   - Can override global settings

### Plugin Files

- **`graphiti-context-collector.js`**: Main automatic context collection plugin
- **`graphiti-integration.js`**: Helper plugin with utility functions

## Installation

### 1. Copy Plugins to Global Location

```bash
# Copy from repository to global location
cp /opt/stacks/graphiti/.opencode/plugin/*.js /root/.config/opencode/plugin/

# Or create symlinks
ln -s /opt/stacks/graphiti/.opencode/plugin/graphiti-context-collector.js /root/.config/opencode/plugin/
ln -s /opt/stacks/graphiti/.opencode/plugin/graphiti-integration.js /root/.config/opencode/plugin/
```

### 2. Ensure Graphiti Services are Running

```bash
cd /opt/stacks/graphiti
docker-compose up -d graph  # Start Graphiti API server (port 8003)
```

### 3. Start Using OpenCode

The plugins will automatically:
- Detect when you start an OpenCode session
- Buffer conversation turns (default: 6 messages)
- Generate AI summaries using OpenCode SDK
- Send grouped episodes to Graphiti
- Organize by project name automatically

## Configuration

### Environment Variables

Configure via environment variables or add to your shell profile:

```bash
# Graphiti API endpoint
export GRAPHITI_API_URL="http://localhost:8003"

# Enable/disable automatic collection (default: true)
export GRAPHITI_AUTO_COLLECT="true"

# Number of messages to buffer before summarization (default: 6)
export GRAPHITI_BUFFER_SIZE="6"

# Auto-flush interval in milliseconds (default: 60000 = 1 minute)
export GRAPHITI_FLUSH_INTERVAL="60000"

# Override automatic GROUP_ID (default: opencode-{project-name})
export GRAPHITI_GROUP_ID="my-custom-group"
```

### Dynamic GROUP_ID

By default, the plugin creates a unique GROUP_ID for each project:

- Working in `/opt/stacks/graphiti` → `GROUP_ID: opencode-graphiti`
- Working in `/home/user/my-app` → `GROUP_ID: opencode-my-app`
- Unknown project → `GROUP_ID: opencode-unknown`

This automatically organizes your Graphiti episodes by project.

## How It Works

### 1. Message Buffering

The plugin buffers user and assistant messages in memory:

```javascript
conversationBuffer = [
  { role: "user", content: "...", timestamp: "..." },
  { role: "assistant", content: "...", tools: ["Read", "Edit"], timestamp: "..." },
  // ... up to BUFFER_SIZE messages
]
```

### 2. AI Summarization

When the buffer is full or auto-flush triggers, the plugin:

1. Combines buffered messages into conversation text
2. Sends to OpenCode SDK with summarization prompt
3. Receives 2-3 sentence AI-generated summary
4. Extracts files mentioned in conversation
5. Gathers git context (branch, commit)

### 3. Episode Creation

Creates a single episode with format:

```
Name: "{AI summary first 60 chars}..."
Content:
{Full AI summary}

Project: graphiti
Branch: main
Commit: a1b2c3d
Messages: 6
Files: graphiti.py, nodes.py, edges.py
Time: 2025-01-09T20:30:45.123Z
```

### 4. Graphiti Ingestion

Sends to Graphiti API:
- Endpoint: `POST /v1/add-episode`
- GROUP_ID: `opencode-{project-name}`
- Source: `opencode-conversation`

## Episode Types

The plugin creates three types of episodes:

### 1. Session Start
```
Name: "Session started: graphiti"
Source: "opencode-session"
```

### 2. Conversation Summary
```
Name: "{AI summary}..."
Source: "opencode-conversation"
```

### 3. Session End
```
Name: "Session ended: graphiti"
Source: "opencode-session"
```

## Usage Examples

### Check Plugin Status

When you start OpenCode, you should see:

```
[Graphiti] Context collector enabled for graphiti
[Graphiti] Group ID: opencode-graphiti
[Graphiti] Grouping 6 messages, auto-flush every 60000ms
```

### Query Collected Knowledge

Use the Graphiti MCP server or API:

```bash
# Via MCP (if configured)
# Search for recent conversations
/kg "What did I work on in the graphiti project?"

# Via direct API
curl -X POST http://localhost:8003/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "frontend refactoring",
    "group_ids": ["opencode-graphiti"],
    "max_facts": 10
  }'
```

### Disable for a Session

```bash
# Temporarily disable
GRAPHITI_AUTO_COLLECT=false claude

# Or permanently in your shell profile
echo 'export GRAPHITI_AUTO_COLLECT=false' >> ~/.bashrc
```

## Troubleshooting

### Plugins Not Loading

**Problem**: No `[Graphiti]` messages in console

**Solutions**:
1. Check plugin location: `ls -la /root/.config/opencode/plugin/`
2. Ensure files are JavaScript (.js not .ts)
3. Check file permissions: `chmod 644 /root/.config/opencode/plugin/*.js`
4. Verify no duplicate in project: `rm -rf .opencode/plugin/`

### Episodes Not Appearing in Graphiti

**Problem**: Plugins load but no episodes in Graphiti

**Solutions**:
1. Check Graphiti API is running: `curl http://localhost:8003/health`
2. Verify environment variables: `echo $GRAPHITI_API_URL`
3. Check plugin console output for errors
4. Ensure buffer is flushing: wait 60 seconds or send 6+ messages

### Line Ending Errors

**Problem**: `/usr/bin/env: 'python3\r': No such file or directory`

**Cause**: Windows line endings (CRLF) in hook or plugin files

**Solution**:
```bash
# Fix all hooks
find .claude/hooks -type f \( -name "*.py" -o -name "*.sh" \) -exec sed -i 's/\r$//' {} \;

# Fix plugins
sed -i 's/\r$//' /root/.config/opencode/plugin/*.js
```

### TypeScript Import Errors

**Problem**: `Cannot find module '@opencode-ai/plugin'`

**Cause**: TypeScript plugins can't resolve npm packages in global location

**Solution**: Use JavaScript versions (already done in repository)

### SDK Summarization Failing

**Problem**: Episodes are just truncated text, not AI summaries

**Cause**: OpenCode SDK not responding or not running

**Solutions**:
1. Check OpenCode is running: `curl http://localhost:4096/health`
2. Restart OpenCode server
3. Plugin will fallback to truncation (first 500 chars + "...")

### Duplicate Episodes

**Problem**: Each conversation creates multiple episodes

**Possible Causes**:
1. Both global and project plugins loaded
2. Plugin loaded multiple times
3. Old granular version still running

**Solutions**:
```bash
# Remove project-level plugins
rm -rf /opt/stacks/graphiti/.opencode/plugin/

# Or rename to backup
mv /opt/stacks/graphiti/.opencode /opt/stacks/graphiti/.opencode.backup

# Verify only one instance
ls -la /root/.config/opencode/plugin/graphiti-*.js
```

## Development History

### Evolution of the Plugin

#### v1: TypeScript with Custom Tools (Deprecated)
- Created as TypeScript plugins
- Included custom tools for manual Graphiti queries
- Had granular episode creation (every message/tool)
- **Issues**: Module import errors, duplicate loading

#### v2: JavaScript Granular (Deprecated)
- Converted to JavaScript to fix imports
- Still created individual episodes per message
- **Issue**: Created 30+ episodes per session (too granular)

#### v3: JavaScript with AI Summarization (Current)
- Buffers conversations before summarization
- Uses OpenCode SDK for AI-powered summaries
- Creates ~3 episodes per session
- Dynamic GROUP_ID based on project
- **Result**: Clean, concise knowledge graph

### Key Design Decisions

1. **JavaScript over TypeScript**: Global plugins can't resolve npm packages
2. **Buffering over Immediate**: Reduces API calls and improves summary quality
3. **AI Summary over Raw**: More meaningful knowledge graph entries
4. **Dynamic GROUP_ID**: Automatic project-based organization
5. **MCP for Queries, Plugin for Capture**: Complementary not redundant

## Integration with MCP Server

The OpenCode plugins complement the Graphiti MCP server:

- **Plugin**: Automatic context collection (passive)
- **MCP Server**: Manual queries and analysis (active)

Both use the same Graphiti API but serve different purposes:

```
OpenCode Session
       ↓
    Plugin (automatic)
       ↓
  Graphiti API ← MCP Server (manual queries)
       ↓
  Knowledge Graph
```

## Files in Repository

```
/opt/stacks/graphiti/
├── .opencode/
│   └── plugin/
│       ├── graphiti-context-collector.js  # Main plugin (JavaScript)
│       ├── graphiti-integration.js        # Helper plugin
│       └── README.md                      # Quick start guide
├── .opencode.backup/
│   └── plugin/
│       ├── graphiti-context-collector.ts  # Old TypeScript version
│       ├── graphiti-integration.ts        # Old TypeScript version
│       └── README.md                      # Migration notes
└── docs/
    └── integrations/
        └── OPENCODE_PLUGIN_INTEGRATION.md # This file
```

## Related Documentation

- [Graphiti MCP Server](../../mcp_server/README.md)
- [OpenCode Plugin Documentation](https://docs.opencode.ai/plugins)
- [Graphiti API Documentation](../../server/README.md)
- [CLAUDE.md](../../CLAUDE.md) - Project setup guide

## Support

For issues or questions:

1. Check Troubleshooting section above
2. Review plugin console output for error messages
3. Check Graphiti API logs: `docker logs graphiti-graph-1`
4. Open an issue in the Graphiti repository

## License

Same as parent Graphiti project (Apache 2.0)
