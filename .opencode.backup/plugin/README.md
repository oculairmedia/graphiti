# OpenCode Graphiti Plugin (DEPRECATED - TypeScript Version)

> **⚠️ MIGRATION NOTICE**
>
> This directory contains the **deprecated TypeScript versions** of the OpenCode plugins.
>
> **Current Version**: JavaScript (v3) with AI Summarization
> **Location**: `../.opencode/plugin/`
> **Documentation**: `../docs/integrations/OPENCODE_PLUGIN_INTEGRATION.md`
>
> **Migration Path**:
> - TypeScript v1: Custom tools + granular episodes → **Issues: Module imports**
> - TypeScript → JavaScript v2: Fixed imports, still granular → **Issues: Too many episodes**
> - JavaScript v3 (Current): AI summarization + grouped episodes → **✅ Production Ready**
>
> See the current plugins at `../.opencode/plugin/` for the working JavaScript versions.

---

## Historical Documentation (TypeScript v1)

Advanced integration between OpenCode and the Graphiti knowledge graph, providing enterprise-grade long-term memory and context retention across sessions.

## Features

### 🚀 Core Capabilities
- **Automatic Context Capture**: File operations, bash commands, and git information
- **Dual Protocol Support**: REST API and MCP server integration
- **Production-Ready**: Retry logic, rate limiting, health checks, timeouts
- **Git-Aware**: Captures branch, commit, and remote information
- **Flexible Configuration**: Environment-based setup with sensible defaults

### 🛡️ Reliability Features
- **Exponential Backoff**: Automatic retry with configurable delays (1s → 10s max)
- **Rate Limiting**: Token bucket algorithm (10 req/sec default)
- **Request Timeouts**: 30-second timeout for API calls, 5-second for health checks
- **Graceful Degradation**: Continues working even if Graphiti is unavailable
- **Silent Auto-Capture**: Non-disruptive background operation

## Installation

The plugin is automatically loaded from `.opencode/plugin/graphiti-integration.ts`.

## Configuration

Configure via environment variables:

```bash
# Graphiti REST API endpoint (default: http://localhost:8003)
export GRAPHITI_API_URL="http://localhost:8003"

# Graphiti MCP server endpoint (default: http://localhost:3010)
export GRAPHITI_MCP_URL="http://localhost:3010"

# Use MCP server instead of REST API (default: false)
export GRAPHITI_USE_MCP="true"

# Group ID for organizing memories (default: opencode-session)
export GRAPHITI_GROUP_ID="my-project-context"

# Enable/disable automatic capture (default: true)
export GRAPHITI_AUTO_CAPTURE="true"
```

## Available Tools

### 1. `graphiti_add_memory`

Store information in the knowledge graph with automatic context enrichment.

**Arguments:**
- `name` (string, required): Short name/title for this memory
- `content` (string, required): The content to store
- `source` (string, optional): Source type (default: "opencode")

**Features:**
- Automatically adds timestamp
- Includes git branch and project context
- Retry logic on failure

**Example:**
```typescript
await graphiti_add_memory({
  name: "API endpoint documentation",
  content: "The /v1/search endpoint accepts POST requests with query, group_ids, and max_facts parameters",
  source: "documentation"
})
```

### 2. `graphiti_search`

Search the knowledge graph for relevant context and facts.

**Arguments:**
- `query` (string, required): Search query
- `max_results` (number, optional): Maximum results to return (default: 10)

**Features:**
- Supports both REST and MCP protocols
- Returns relevance scores
- Rate-limited to prevent API overload

**Example:**
```typescript
await graphiti_search({
  query: "How to configure the API server?",
  max_results: 5
})
// Returns:
// Found 5 relevant facts:
//
// 1. API server configured on port 8003 (relevance: 0.95)
// 2. Configuration stored in .env file (relevance: 0.87)
// ...
```

### 3. `graphiti_get_context`

Get recent context from Graphiti for the current project and git branch.

**Arguments:**
- `limit` (number, optional): Number of recent items (default: 5)

**Features:**
- Branch-aware searching
- Automatically includes project name
- Filters by current git context

**Example:**
```typescript
await graphiti_get_context({
  limit: 10
})
// Returns:
// Recent project context (graphiti, main):
//
// 1. Created OpenCode plugin for Graphiti integration
// 2. Fixed hook line ending issues
// ...
```

### 4. `graphiti_health`

Check Graphiti API health and view current configuration.

**Arguments:** None

**Features:**
- Tests API connectivity
- Shows configuration details
- Displays current git context
- Rate limiter status

**Example:**
```typescript
await graphiti_health()
// Returns:
// Graphiti Health Status
// =====================
// API Endpoint: http://localhost:8003
// Connection Type: REST API
// Status: ✓ Healthy
// Group ID: opencode-session
// Auto-capture: Enabled
// Rate Limit: 10 req/sec
//
// Current Context:
// - Project: graphiti
// - Directory: /opt/stacks/graphiti
// - Git Branch: main
// - Git Commit: efef0a5
```

## Automatic Hooks

The plugin automatically captures:

### File Operations
When you edit or create files:
```
[2025-01-08T21:30:00Z] OpenCode edited file: src/plugin.ts
Project: graphiti
Branch: feature/opencode-plugin
Commit: abc1234
```

### Bash Commands
When you run shell commands:
```
[2025-01-08T21:30:00Z] Executed in /opt/stacks/graphiti:
Command: npm run build
Project: graphiti
Branch: main
```

### Session Events
When sessions complete:
```
Session completed at 2025-01-08T21:30:00Z.
Project: graphiti, Branch: main, Directory: /opt/stacks/graphiti
```

All captured information is stored in Graphiti with the configured `GROUP_ID`.

## Usage with OpenCode

Once installed, use the tools naturally in OpenCode conversations:

```
> Search Graphiti for information about the API endpoints
> Store this function documentation in Graphiti memory
> What context does Graphiti have about this project?
> Check Graphiti health status
```

OpenCode will automatically use the Graphiti tools when relevant.

## Technical Details

### Retry Logic
- **Max Retries**: 3 attempts
- **Initial Delay**: 1000ms
- **Max Delay**: 10000ms
- **Backoff Multiplier**: 2x (exponential)
- **Timeout**: 30 seconds per request

### Rate Limiting
- **Algorithm**: Token bucket
- **Capacity**: 10 tokens
- **Refill Rate**: 10 tokens/second
- **Behavior**: Automatic waiting when rate exceeded

### Protocol Support

**REST API Mode** (default):
- Direct HTTP calls to Graphiti API server
- Endpoints: `/v1/add-episode`, `/v1/search`
- Best for: Single-server deployments

**MCP Server Mode** (`GRAPHITI_USE_MCP=true`):
- JSON-RPC 2.0 protocol
- Tools: `add_memory`, `search_memory_facts`
- Best for: Claude integration, standardized tooling

### Context Enrichment

All stored memories are automatically enriched with:
- ISO 8601 timestamps
- Git branch name
- Git commit SHA (short)
- Git remote URL
- Project name
- Working directory

## Requirements

- Graphiti API server running (default: http://localhost:8003)
- **OR** Graphiti MCP server (default: http://localhost:3010)
- Node.js/Bun runtime for TypeScript plugin
- `@opencode-ai/plugin` package (provided by OpenCode)
- Git repository (optional, for git context features)

## Troubleshooting

### Plugin fails to load

1. Check that OpenCode recognizes the plugin directory:
   ```bash
   ls -la .opencode/plugin/
   ```

2. Verify TypeScript syntax:
   ```bash
   npx tsc --noEmit .opencode/plugin/graphiti-integration.ts
   ```

3. Check OpenCode logs for plugin errors

### Tools aren't working

1. Verify Graphiti API is running:
   ```bash
   curl http://localhost:8003/health
   # or for MCP server
   curl http://localhost:3010/health
   ```

2. Check environment variables:
   ```bash
   echo $GRAPHITI_API_URL
   echo $GRAPHITI_USE_MCP
   echo $GRAPHITI_GROUP_ID
   ```

3. Run health check tool:
   ```
   > Check Graphiti health status
   ```

### Automatic capture not working

1. Verify `GRAPHITI_AUTO_CAPTURE` is not set to `false`
2. Check console logs for errors (silent by design)
3. Test manual memory storage with `graphiti_add_memory`

### Rate limiting issues

If you see "waiting for rate limit" messages:
- Reduce operation frequency
- Increase rate limit capacity in plugin code
- Use MCP mode for better performance

### Connection errors

Common errors and solutions:

**"Failed after 4 attempts"**
- Check Graphiti server is running
- Verify network connectivity
- Check firewall rules

**"Request timeout"**
- Increase timeout in plugin code (line 168, 206, 248, 284)
- Check Graphiti server performance
- Verify database connectivity

**"Health check failed"**
- Non-fatal, plugin continues working
- Features may be unavailable
- Fix connectivity and reload

## Performance Considerations

- **Rate Limiting**: Default 10 req/sec suitable for most workloads
- **Auto-Capture**: Silent failures prevent workflow disruption
- **Batch Operations**: Consider disabling auto-capture for bulk operations
- **MCP Mode**: Generally faster for high-frequency operations

## Security

- No credentials stored in plugin code
- All configuration via environment variables
- Rate limiting prevents accidental DoS
- Timeouts prevent hanging operations
- Graceful degradation on failures

## Contributing

To modify the plugin:

1. Edit `.opencode/plugin/graphiti-integration.ts`
2. Test changes with OpenCode
3. Update this README with new features
4. Document environment variables

## License

Follows the Graphiti project license.
