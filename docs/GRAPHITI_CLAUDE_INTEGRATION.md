# Graphiti + Claude: Smart Contextual Memory Integration

## Executive Summary

This document presents innovative approaches for integrating Graphiti's temporal knowledge graph capabilities with Claude agents to create intelligent, context-aware AI assistants with persistent memory. By leveraging hooks, slash commands, and MCP servers, we can build a seamless memory layer that enhances Claude's understanding of conversations, relationships, and temporal context.

## Core Concepts

### 1. Temporal Context Injection
Graphiti's bi-temporal model (event time + knowledge time) provides unique opportunities for context-aware memory retrieval:

- **Time-Aware Queries**: Automatically inject relevant historical context based on temporal proximity
- **Event Sequencing**: Understand cause-and-effect relationships in user interactions
- **Knowledge Evolution**: Track how information changes over time

### 2. Semantic + Graph Hybrid Retrieval
Combine Graphiti's hybrid search capabilities (embeddings + BM25 + graph traversal) for intelligent context retrieval:

- **Multi-hop Reasoning**: Follow entity relationships to gather comprehensive context
- **Relevance Scoring**: Use centrality metrics to prioritize important entities
- **Dynamic Context Windows**: Adjust retrieval depth based on query complexity

## Implementation Strategies

### A. Hook-Based Automatic Context Injection

#### 1. UserPromptSubmit Hook
Automatically enrich user prompts with relevant context from Graphiti:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "type": "command",
        "command": "graphiti-context-inject.sh \"$USER_PROMPT\""
      }
    ]
  }
}
```

**graphiti-context-inject.sh**:
```bash
#!/bin/bash
PROMPT="$1"

# Extract entities from prompt
ENTITIES=$(curl -X POST http://localhost:8000/extract-entities \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"$PROMPT\"}" | jq -r '.entities[]')

# Search for related context
CONTEXT=$(curl -X POST http://localhost:8000/search/nodes \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"$PROMPT\", \"max_nodes\": 5}" | jq -r '.nodes[].summary')

# Inject context into prompt
echo -e "$PROMPT\n\n<context>\n$CONTEXT\n</context>"
```

#### 2. PostToolUse Memory Capture
Automatically capture important interactions as knowledge:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "graphiti-capture-edit.sh \"$TOOL_NAME\" \"$TOOL_INPUT\" \"$TOOL_OUTPUT\""
          }
        ]
      }
    ]
  }
}
```

### B. Intelligent Slash Commands

#### 1. `/remember` - Active Memory Storage
Store important information with semantic understanding:

```bash
#!/bin/bash
# ~/.claude/commands/remember
CONTENT="$ARGUMENTS"

# Extract and store in Graphiti
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d "{
    \"messages\": [{
      \"content\": \"$CONTENT\",
      \"role\": \"user\",
      \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
    }],
    \"group_id\": \"claude_memory_$(date +%Y%m%d)\"
  }"

echo "Remembered: $CONTENT"
```

#### 2. `/recall` - Contextual Memory Retrieval
Retrieve memories with temporal and semantic awareness:

```bash
#!/bin/bash
# ~/.claude/commands/recall
QUERY="$ARGUMENTS"

# Search with temporal decay
RESULTS=$(curl -X POST http://localhost:8000/search/nodes \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"$QUERY\",
    \"max_nodes\": 10,
    \"group_ids\": [\"claude_memory_*\"]
  }")

echo "## Relevant Memories:"
echo "$RESULTS" | jq -r '.nodes[] | "- [\(.created_at | split("T")[0])] \(.name): \(.summary)"'
```

#### 3. `/context` - Deep Context Analysis
Analyze relationships and provide comprehensive context:

```bash
#!/bin/bash
# ~/.claude/commands/context
ENTITY="$ARGUMENTS"

# Find entity
NODE_ID=$(curl -X POST http://localhost:8000/search/nodes \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"$ENTITY\", \"max_nodes\": 1}" | jq -r '.nodes[0].uuid')

# Get relationships
EDGES=$(curl -X GET "http://localhost:8000/edges/by-node/$NODE_ID")

echo "## Context for: $ENTITY"
echo "### Direct Relationships:"
echo "$EDGES" | jq -r '.edges[] | "- \(.name): \(.fact)"'
```

### C. MCP Server Integration

#### 1. Graphiti MCP Server Enhancements
Extend the existing MCP server with smart retrieval prompts:

```python
@mcp_server.prompt()
async def contextual_search(
    query: str,
    temporal_window: Optional[str] = "7d",
    relationship_depth: int = 2,
    entity_types: Optional[List[str]] = None
) -> str:
    """
    Smart contextual search that considers:
    - Temporal relevance (recent > old)
    - Entity centrality (important > peripheral)
    - Relationship proximity (close > distant)
    """
    # Implementation details...
```

#### 2. Memory-Aware Prompts
Create MCP prompts that leverage Graphiti's capabilities:

```python
@mcp_server.prompt()
async def memory_aware_response(
    user_query: str,
    session_id: str
) -> str:
    """
    Generate a response with full session context:
    1. Retrieve session history from Graphiti
    2. Extract key entities and relationships
    3. Identify temporal patterns
    4. Generate contextually aware response
    """
    # Implementation details...
```

## Advanced Features

### 1. Conversation Threading
Track conversation threads across sessions:

```python
class ConversationThread:
    def __init__(self, graphiti_client):
        self.graphiti = graphiti_client
    
    async def link_messages(self, message_id: str, parent_id: str):
        """Create FOLLOWS relationship between messages"""
        await self.graphiti.add_edge(
            source_id=message_id,
            target_id=parent_id,
            relationship="FOLLOWS",
            properties={"thread_id": self.thread_id}
        )
```

### 2. Entity Resolution & Deduplication
Automatically merge duplicate entities across conversations:

```bash
# Hook for entity deduplication
{
  "hooks": {
    "PostConversation": [
      {
        "type": "command",
        "command": "cd /opt/stacks/graphiti && uv run python maintenance_dedupe_entities.py"
      }
    ]
  }
}
```

### 3. Adaptive Context Windows
Dynamically adjust context based on query complexity:

```python
def calculate_context_depth(query: str) -> dict:
    """
    Determine optimal context retrieval parameters:
    - Simple queries: 1-hop, 5 nodes
    - Complex queries: 3-hop, 20 nodes
    - Research queries: 5-hop, 50 nodes
    """
    complexity = analyze_query_complexity(query)
    
    return {
        "max_hops": min(complexity.depth_required, 5),
        "max_nodes": min(complexity.nodes_required, 50),
        "time_window": complexity.temporal_range
    }
```

### 4. Memory Importance Scoring
Use Graphiti's centrality metrics for memory prioritization:

```python
async def get_important_memories(group_id: str, limit: int = 10):
    """
    Retrieve memories ranked by importance:
    - PageRank centrality: overall importance
    - Betweenness centrality: bridge concepts
    - Degree centrality: highly connected
    - Temporal decay: recent > old
    """
    nodes = await graphiti.search(
        group_ids=[group_id],
        sort_by=[
            ("pagerank_centrality", "desc"),
            ("created_at", "desc")
        ],
        limit=limit
    )
    return nodes
```

## Use Case Examples

### 1. Project Knowledge Assistant
Track project evolution and decisions:

```bash
# Slash command: /project-summary
#!/bin/bash
PROJECT="$ARGUMENTS"

# Get project timeline
curl -X POST http://localhost:8000/search/nodes \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"$PROJECT decisions milestones\",
    \"entity\": \"Entity\",
    \"group_ids\": [\"project_$PROJECT\"]
  }" | jq -r '.nodes[] | "[\(.created_at | split("T")[0])] \(.summary)"' | sort
```

### 2. Personal Knowledge Management
Build a personal knowledge graph:

```json
{
  "hooks": {
    "ConversationEnd": [
      {
        "type": "command",
        "command": "graphiti-extract-learnings.sh \"$CONVERSATION_ID\""
      }
    ]
  }
}
```

### 3. Code Review Memory
Remember code review patterns and decisions:

```bash
# Hook for code reviews
{
  "matcher": "review",
  "hooks": [
    {
      "type": "command",
      "command": "graphiti-store-review.sh \"$FILE_PATH\" \"$REVIEW_COMMENTS\""
    }
  ]
}
```

## Performance Optimizations

### 1. Caching Strategy
- Cache frequently accessed entities in Redis
- Pre-compute entity embeddings for common queries
- Maintain hot/cold memory tiers

### 2. Batch Processing
- Queue memory updates for batch processing
- Deduplicate entities periodically
- Recompute centrality metrics on schedule

### 3. Smart Indexing
- Create specialized indexes for time-based queries
- Maintain entity type indexes for filtered searches
- Use bloom filters for existence checks

## Security & Privacy Considerations

### 1. Memory Isolation
- Separate memory graphs by user/project
- Implement access control at the graph level
- Encrypt sensitive memories

### 2. Data Retention
- Automatic memory expiration policies
- Right-to-forget implementation
- Audit trail for memory access

## Future Enhancements

### 1. Multi-Modal Memory
- Store and retrieve images in knowledge graph
- Link code snippets to explanations
- Audio/video transcript integration

### 2. Predictive Context
- Anticipate needed context based on patterns
- Pre-fetch likely relevant memories
- Suggest related topics proactively

### 3. Collaborative Memory
- Shared team knowledge graphs
- Memory synchronization across agents
- Distributed knowledge consensus

## Implementation Roadmap

1. **Phase 1**: Basic Integration (Week 1-2)
   - Implement core hooks for memory capture
   - Create essential slash commands
   - Set up automated entity extraction

2. **Phase 2**: Smart Retrieval (Week 3-4)
   - Implement adaptive context windows
   - Add temporal decay algorithms
   - Create importance scoring system

3. **Phase 3**: Advanced Features (Week 5-6)
   - Build conversation threading
   - Implement predictive context
   - Add collaborative memory features

4. **Phase 4**: Optimization (Week 7-8)
   - Performance tuning
   - Caching implementation
   - Security hardening

## Conclusion

By combining Graphiti's powerful knowledge graph capabilities with Claude's conversational AI through hooks and slash commands, we can create a truly intelligent assistant with persistent, contextual memory. This integration enables:

- Natural memory formation from conversations
- Intelligent context retrieval based on relationships
- Temporal awareness of information evolution
- Seamless knowledge accumulation over time

The result is an AI assistant that truly remembers and learns from every interaction, providing increasingly valuable and personalized assistance.