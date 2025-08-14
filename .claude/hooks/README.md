# Graphiti Knowledge Retrieval Hooks for Claude Code

These hooks integrate Claude Code with the Graphiti knowledge graph, enabling automatic retrieval of relevant context during conversations.

**API Endpoint**: http://192.168.50.90:8003

## Features

- **Automatic Context Retrieval**: Detects when knowledge graph information would be helpful
- **Smart Query Extraction**: Extracts relevant search terms from natural language
- **Multiple Search Types**: Entity search, episode search, relationship traversal
- **Caching**: Reduces API calls with intelligent caching
- **Session Context**: Loads recent context when resuming sessions

## Available Hooks

### 1. `graphiti-retrieval.py` (Recommended)
Full-featured Python hook with async support and comprehensive search capabilities.

**Features:**
- Pattern-based trigger detection
- Entity extraction from prompts
- Result caching (5-minute TTL)
- Formatted context injection
- Support for Task tool enhancement

### 2. `graphiti-integration.py` (Advanced)
Direct integration with Graphiti Python API for deep knowledge graph access.

**Features:**
- Native Graphiti API usage
- Entity relationship traversal
- Temporal filtering for episodes
- Comprehensive entity context
- Advanced search configurations

### 3. `graphiti-search.sh` (Lightweight)
Simple bash script for quick searches.

**Features:**
- Minimal dependencies (bash, curl, jq)
- Fast keyword-based triggers
- Basic entity and relationship formatting

## Installation

1. **Ensure hooks are executable:**
```bash
chmod +x /opt/stacks/graphiti/.claude/hooks/*.py
chmod +x /opt/stacks/graphiti/.claude/hooks/*.sh
```

2. **Configure environment variables:**
```bash
export GRAPHITI_API_URL="http://localhost:8003"
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="password"
```

3. **Install Python dependencies (if needed):**
```bash
pip install aiohttp
```

## Configuration

The hooks are configured in `.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/graphiti-retrieval.py",
            "timeout": 10
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Task|Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/graphiti-retrieval.py",
            "timeout": 5
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/graphiti-retrieval.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

## Usage

Once configured, the hooks automatically activate when:

### Explicit Triggers
- "What do you know about [entity]?"
- "Search the knowledge graph for..."
- "Remember when..."
- "Tell me about..."
- "Explain the relationship between..."

### Implicit Triggers
- Questions about previous context
- References to earlier work
- Requests for historical information
- Multiple knowledge-related keywords

## Hook Behavior

### UserPromptSubmit Hook
- Analyzes user prompts for knowledge needs
- Searches Graphiti for relevant context
- Injects context before Claude processes the prompt
- Context appears as XML-formatted data

### PreToolUse Hook (Task Tool)
- Enhances Task tool calls with relevant context
- Useful for subagent tasks that need knowledge
- Automatically approves enhanced tasks

### SessionStart Hook
- Loads recent context when resuming sessions
- Provides continuity across sessions
- Only activates for `--resume` sessions

## Example Interactions

### Example 1: Entity Search
```
User: What do you know about the GraphCanvas component?

<!-- Graphiti Knowledge Graph Context -->
<graphiti-context>
## Relevant Entities:
### GraphCanvas
- Type: Component
- Created: 2024-01-15
- Summary: Main visualization component for graph rendering
- Properties: {"framework": "React", "performance": "optimized"}
</graphiti-context>

Claude: Based on the knowledge graph, GraphCanvas is a React component...
```

### Example 2: Relationship Query
```
User: How is the WebSocket connected to real-time updates?

<!-- Retrieved from Graphiti Knowledge Graph -->
<graphiti-context>
## Relationships:
- WebSocket --[ENABLES]--> Real-time Updates
- Real-time Updates --[USES]--> Delta Updates
- Delta Updates --[OPTIMIZES]--> Performance
</graphiti-context>

Claude: The WebSocket enables real-time updates through...
```

## Debugging

Enable debug mode to see hook execution:
```bash
claude --debug
```

Check hook logs:
```bash
tail -f /tmp/graphiti-hook.log
```

Test hooks manually:
```bash
echo '{"hook_event_name":"UserPromptSubmit","prompt":"What is GraphCanvas?"}' | \
  python3 .claude/hooks/graphiti-retrieval.py
```

## Performance Considerations

- **Caching**: Results cached for 5 minutes to reduce API calls
- **Timeouts**: Hooks have configurable timeouts (default 10s for prompts, 5s for tools)
- **Limits**: Search results limited to prevent context overflow
- **Parallel Execution**: Multiple hooks run in parallel

## Customization

### Adjusting Search Sensitivity
Edit `SEARCH_TRIGGERS` and `KNOWLEDGE_KEYWORDS` in the Python hooks to control when searches trigger.

### Changing Result Limits
Modify `MAX_RESULTS` and `SIMILARITY_THRESHOLD` to adjust result quantity and quality.

### Custom Formatting
Update the `format_results()` or `format_context()` methods to change how results appear to Claude.

## Troubleshooting

### Hook not triggering
- Check if hook is executable: `ls -la .claude/hooks/`
- Verify settings.json syntax: `jq . .claude/settings.json`
- Use `claude --debug` to see hook execution

### No results returned
- Verify Graphiti API is running: `curl http://localhost:8003/health`
- Check environment variables are set
- Review search patterns and keywords

### Timeout errors
- Increase timeout in settings.json
- Check Graphiti API performance
- Consider using the bash hook for faster responses

## Security Notes

- Hooks run with your user permissions
- API credentials should use environment variables
- Review hook code before enabling
- Use timeout limits to prevent hanging

## Contributing

To add new search patterns or improve context extraction:
1. Edit the hook files in `.claude/hooks/`
2. Test manually with sample inputs
3. Update this README with new features