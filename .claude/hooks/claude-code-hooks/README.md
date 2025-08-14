# Claude Code Hooks for Graphiti Integration

This directory contains hooks that enable automatic ingestion of Claude Code conversations into the Graphiti knowledge graph.

## Features

- **Automatic Conversation Capture**: Every exchange between you and Claude is automatically captured
- **Personalized Attribution**: Conversations are attributed to the user by name (configurable)
- **Smart Filtering**: Skips system commands, errors, and very short exchanges
- **Works with Approvals**: Captures Claude's work even when you just hit enter or approve
- **Ollama Integration**: Sends conversations to Ollama for entity extraction and knowledge graph building

## Files

### `graphiti-ingestion.py`
The main ingestion hook that:
- Parses Claude Code transcript files
- Extracts user prompts and assistant responses
- Sends conversations to Graphiti API for processing
- Properly attributes conversations to user and assistant names

### `ingestion-wrapper.sh`
A bash wrapper that:
- Logs hook execution for debugging
- Captures stdin for troubleshooting
- Passes data to the Python ingestion script
- Records exit codes and errors

### `example-settings.json`
Example Claude Code settings showing how to configure the Stop hook to trigger automatic ingestion.

## Setup

1. **Configure User Name** (optional):
   ```bash
   export GRAPHITI_USER_NAME="Your Name"
   ```
   Default is "Emmanuel Umukoro"

2. **Configure Graphiti API** (if not using default):
   ```bash
   export GRAPHITI_API_URL="http://localhost:8003"
   ```

3. **Add to Claude Code Settings**:
   Copy the Stop hook configuration from `example-settings.json` to your `.claude/settings.json`:
   ```json
   {
     "hooks": {
       "Stop": [
         {
           "hooks": [
             {
               "type": "command",
               "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/claude-code-hooks/ingestion-wrapper.sh",
               "timeout": 5
             }
           ]
         }
       ]
     }
   }
   ```

4. **Restart Claude Code** to load the new hooks

## How It Works

1. **Stop Event**: When Claude finishes responding, the Stop hook fires
2. **Transcript Reading**: The hook reads the conversation transcript
3. **Content Extraction**: Extracts the last user prompt and Claude's response
4. **Attribution**: Adds user and assistant names to the content
5. **API Submission**: Sends to Graphiti's `/messages` endpoint
6. **Processing**: Graphiti uses Ollama to extract entities and relationships
7. **Storage**: Knowledge is stored in FalkorDB graph database

## Monitoring

Check ingestion activity:
```bash
# View ingestion logs
tail -f /tmp/graphiti-ingest-hook.log

# Check Stop hook activity
tail -f /tmp/stop-hook-fired.log

# Monitor Graphiti processing
docker logs graphiti-graph-1 --tail 20

# Query the knowledge graph
docker exec graphiti-falkordb-1 redis-cli GRAPH.QUERY graphiti_migration "MATCH (n:Entity) RETURN n.name ORDER BY n.created_at DESC LIMIT 10"
```

## Troubleshooting

### Hook Not Firing
- Check if Stop event is configured: `/hooks` in Claude Code
- Verify settings.json has correct path to wrapper
- Restart Claude Code after configuration changes

### Ingestion Not Working
- Check `/tmp/graphiti-ingest-hook.log` for errors
- Verify Graphiti API is running: `curl http://localhost:8003/health`
- Ensure Ollama is accessible for entity extraction

### No GPU Activity
- Verify Ollama connection in Graphiti logs
- Check if messages are reaching processing queue
- Ensure FalkorDB is healthy and accepting connections

## Customization

### Change User Name
Edit `graphiti-ingestion.py` line 29:
```python
USER_NAME = os.getenv("GRAPHITI_USER_NAME", "Your Name Here")
```

### Adjust Filtering
Modify the `should_ingest()` function to change what gets captured.

### Change Group ID
Edit line 28 to organize conversations differently:
```python
GROUP_ID = os.getenv("GRAPHITI_GROUP_ID", "your_custom_group")
```

## Requirements

- Claude Code with hooks support
- Graphiti API running on port 8003
- FalkorDB for graph storage
- Ollama for entity extraction
- Python 3.x with requests library

## License

Part of the Graphiti project