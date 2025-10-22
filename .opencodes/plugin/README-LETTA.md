# Letta API Client Plugin for OpenCode

Direct API integration with Letta server for agent and memory management - **no MCP middleware overhead**.

## Quick Start

```bash
# Copy to global plugin directory
cp .opencodes/plugin/letta-api-client.js /root/.config/opencode/plugin/

# Set environment variables
export LETTA_API_URL="https://letta.oculair.ca"
export LETTA_PASSWORD="your-token-here"
```

## Usage in OpenCode Session

The plugin exposes a `LettaApiClient` that you can use directly:

```javascript
// Example: List all agents
const agents = await LettaApiClient.listAgents()

// Create new agent
const agent = await LettaApiClient.createAgent({
  name: "coding-assistant",
  tools: ["tool-id-1", "tool-id-2"]
})

// Send message to agent
const response = await LettaApiClient.sendMessage(agent.id, [
  { role: "user", content: "Help me debug this code" }
])

// Manage memory
const memory = await LettaApiClient.getAgentMemory(agent.id)
await LettaApiClient.updateAgentMemory(agent.id, {
  core: { human: "Developer working on Graphiti project" }
})
```

## Available Methods

### Agents
- `listAgents()` - List all agents
- `getAgent(agentId)` - Get agent details
- `createAgent(config)` - Create new agent
- `updateAgent(agentId, updates)` - Update agent
- `deleteAgent(agentId)` - Delete agent

### Tools
- `listTools()` - List all available tools
- `getTool(toolId)` - Get tool details
- `createTool(toolConfig)` - Create new tool
- `attachToolToAgent(agentId, toolId)` - Attach tool to agent
- `detachToolFromAgent(agentId, toolId)` - Detach tool from agent
- `listAgentTools(agentId)` - List agent's tools

### MCP Integration
- `listMcpServers()` - List all MCP servers
- `listMcpServerTools(serverName)` - List tools from specific MCP server

### Memory Management
- `getAgentMemory(agentId)` - Get agent's core memory
- `updateAgentMemory(agentId, memory)` - Update core memory
- `listMemoryBlocks(agentId)` - List memory blocks
- `createMemoryBlock(agentId, block)` - Create memory block
- `updateMemoryBlock(agentId, blockId, updates)` - Update memory block
- `deleteMemoryBlock(agentId, blockId)` - Delete memory block

### Messages
- `sendMessage(agentId, messages)` - Send message to agent
- `listMessages(agentId, params)` - List agent messages
- `getMessage(agentId, messageId)` - Get specific message

### Utility
- `log(level, message, extra)` - Logging with level control

## Configuration

### Environment Variables

```bash
# Required
export LETTA_PASSWORD="your-bearer-token"

# Optional
export LETTA_API_URL="https://letta.oculair.ca"  # Default
export LETTA_LOG_LEVEL="debug"  # info (default), debug, warn, error
```

### Timeouts

- Default request timeout: 10 seconds
- Message processing timeout: 30 seconds

## Error Handling

All methods throw errors on failure. Use try-catch:

```javascript
try {
  const agent = await LettaApiClient.getAgent("agent-id")
} catch (error) {
  console.error("Failed to get agent:", error.message)
}
```

## Performance Benefits vs MCP

**Direct API calls:**
- ✅ No MCP protocol overhead
- ✅ No connection pooling issues
- ✅ Direct timeout control
- ✅ Simple HTTP error handling
- ✅ No startup health checks

**MCP middleware:**
- ❌ Network round-trips for MCP protocol
- ❌ Connection management complexity
- ❌ Health check overhead on startup
- ❌ Multiple layers of error handling

## Example Workflows

### Create Agent with Tools

```javascript
// List available tools
const tools = await LettaApiClient.listTools()

// Create agent
const agent = await LettaApiClient.createAgent({
  name: "graphiti-assistant",
  tools: tools.slice(0, 3).map(t => t.id)
})

// Send first message
const response = await LettaApiClient.sendMessage(agent.id, [
  { role: "user", content: "Help me with Graphiti development" }
])
```

### Memory Management

```javascript
// Get current memory
const memory = await LettaApiClient.getAgentMemory(agentId)

// Update core memory
await LettaApiClient.updateAgentMemory(agentId, {
  core: {
    human: "Senior developer",
    persona: "Expert in graph databases"
  }
})

// Create memory block
await LettaApiClient.createMemoryBlock(agentId, {
  name: "project-context",
  value: "Working on Graphiti visualization features"
})
```

### List MCP Tools

```javascript
// List MCP servers
const servers = await LettaApiClient.listMcpServers()

// Get tools from specific server
for (const server of servers) {
  const tools = await LettaApiClient.listMcpServerTools(server.name)
  console.log(`${server.name}: ${tools.length} tools`)
}
```

## Debugging

Enable debug logging:

```bash
export LETTA_LOG_LEVEL="debug"
```

You'll see:
```
[Letta] API Request: GET https://letta.oculair.ca/v1/agents/
[Letta] API Response: https://letta.oculair.ca/v1/agents/ {"status":200}
```

## Integration with Graphiti Plugin

The Letta plugin works alongside the Graphiti context collector:

- **Graphiti plugin**: Captures OpenCode sessions → knowledge graph
- **Letta plugin**: Agent management and memory operations

Both use direct API calls for optimal performance.
