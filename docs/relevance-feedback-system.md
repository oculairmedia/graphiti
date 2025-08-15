# Graphiti Relevance Feedback System Documentation

## Overview

The Graphiti Relevance Feedback System is an adaptive learning mechanism that improves knowledge graph retrieval quality over time by tracking and scoring the usefulness of retrieved memories. It integrates with Claude Code hooks to automatically evaluate context relevance and store feedback in FalkorDB.

## Architecture

### Components

1. **Python API** (`/feedback/relevance`)
   - FastAPI endpoint for receiving relevance feedback
   - Stores scores in FalkorDB with usage tracking
   - Supports manual and automatic scoring methods

2. **Claude Hooks**
   - `graphiti-context-with-feedback.py`: Caches context during queries
   - `graphiti-feedback-evaluator.py`: Evaluates and submits feedback after responses

3. **FalkorDB Storage**
   - Persists relevance scores as node properties
   - Tracks usage counts, success rates, and timestamps
   - Supports decay factors for time-based score adjustment

4. **Relevance Scorer** (`graphiti_core/relevance/scorer.py`)
   - Core scoring logic with LLM and heuristic methods
   - Reciprocal Rank Fusion (RRF) for combining rankings
   - Configurable scoring parameters

## How It Works

### 1. Context Caching Phase
When a query is made to Graphiti:
```python
# graphiti-context-with-feedback.py saves:
{
    "query_id": "unique_id",
    "query_text": "user's question",
    "memories": {
        "memory_id": {
            "content": "memory text",
            "type": "entity/fact"
        }
    },
    "timestamp": "ISO timestamp"
}
```

### 2. Response Evaluation Phase
After Claude generates a response:
- The feedback evaluator analyzes which memories were useful
- Scores are calculated based on:
  - Content appearance in response (0.4 weight)
  - Partial word matches (0.2 weight)
  - Entity mentions (0.1 weight)
  - Base retrieval score (0.3)

### 3. Feedback Submission Phase
Scores are sent to the Python API:
```python
# Request format (wrapped for FastAPI)
{
    "feedback_request": {
        "query_id": "unique_id",
        "query_text": "original query",
        "memory_scores": {
            "memory_id": 0.85  # Score 0.0-1.0
        },
        "response_text": "generated response",
        "metadata": {"source": "claude_hooks"}
    },
    "settings": {}  # Empty object required by API
}
```

### 4. Storage Phase
FalkorDB stores feedback as node properties:
```cypher
MATCH (n {uuid: $memory_id})
SET 
    n.relevance_scores = $scores,      # Historical scores array
    n.avg_relevance = $avg_score,      # Exponential moving average
    n.usage_count = $count,             # Total retrievals
    n.successful_uses = $successes,    # Useful retrievals
    n.last_accessed = $timestamp,      # Last retrieval time
    n.last_scored = $timestamp,        # Last evaluation time
    n.decay_factor = $decay            # Time-based decay
```

## Integration Guide

### Prerequisites

1. **Services Running**
   - Graphiti Python API on port 8003
   - FalkorDB on port 6389
   - Claude Code with hooks enabled

2. **Environment Variables**
   ```bash
   export GRAPHITI_API_URL="http://192.168.50.90:8003"
   export ENABLE_GRAPHITI_FEEDBACK="true"
   ```

### Installation

1. **Deploy the fixed Python API**
   ```bash
   cd /opt/stacks/graphiti
   docker-compose build graph
   docker-compose up -d graph
   ```

2. **Install Claude Hooks**
   ```bash
   # Copy hooks to Claude directory
   cp .claude/hooks/graphiti-context-with-feedback.py ~/.claude/hooks/
   cp .claude/hooks/graphiti-feedback-evaluator.py ~/.claude/hooks/
   
   # Enable in settings
   claude settings set hooks.enabled true
   ```

### API Usage

#### Submit Relevance Feedback
```python
import requests

url = "http://localhost:8003/feedback/relevance"
data = {
    "feedback_request": {
        "query_id": "unique_query_id",
        "query_text": "What is Graphiti?",
        "memory_scores": {
            "memory_uuid_1": 0.9,
            "memory_uuid_2": 0.6
        },
        "response_text": "Graphiti is a knowledge graph...",
        "metadata": {"source": "api_client"}
    },
    "settings": {}
}

response = requests.post(url, json=data)
```

#### Query Memories with Scores
```python
# GET /feedback/memories?group_id=default&min_relevance=0.5
```

#### Bulk Recalculate Scores
```python
data = {
    "memory_ids": ["uuid1", "uuid2"],
    "recalculation_method": "hybrid",
    "force": True
}
response = requests.post(url + "/recalculate", json=data)
```

### Direct FalkorDB Integration

```python
import redis
from redis.commands.graph import Graph

client = redis.Redis(host='localhost', port=6389)
graph = Graph(client, 'graphiti_migration')

# Store feedback directly
query = """
MATCH (n {uuid: $uuid})
SET n.avg_relevance = $score,
    n.usage_count = n.usage_count + 1,
    n.last_scored = $timestamp
RETURN n.name, n.avg_relevance
"""

result = graph.query(query, {
    'uuid': 'memory_uuid',
    'score': 0.85,
    'timestamp': datetime.utcnow().isoformat()
})
```

## Configuration

### Scoring Configuration (`ScoringConfig`)
```python
{
    "enable_llm_scoring": true,        # Use LLM for evaluation
    "enable_heuristic_scoring": true,  # Use heuristic methods
    "enable_decay": true,              # Apply time-based decay
    "half_life_days": 30.0,           # Decay half-life
    "min_relevance_threshold": 0.3,   # Minimum score to return
    "high_relevance_threshold": 0.7,  # High relevance cutoff
    "rrf_k": 60,                      # RRF constant
    "semantic_weight": 0.4,           # Semantic similarity weight
    "keyword_weight": 0.3,            # Keyword match weight
    "graph_weight": 0.2,              # Graph traversal weight
    "historical_weight": 0.1          # Historical score weight
}
```

### Hook Configuration
```python
# In graphiti-context-with-feedback.py
GRAPHITI_API_URL = "http://192.168.50.90:8003"
ENABLE_FEEDBACK = True
MAX_CONTEXT_SIZE = 10  # Max memories to cache

# In graphiti-feedback-evaluator.py
CONTEXT_CACHE_FILE = "/tmp/graphiti_context_cache.json"
FEEDBACK_PENDING_FILE = "/tmp/graphiti_feedback_pending.json"
```

## Monitoring

### Check Feedback Logs
```bash
tail -f /tmp/graphiti_feedback.log
```

### Query Scored Nodes
```bash
redis-cli -p 6389 'GRAPH.QUERY' 'graphiti_migration' \
  'MATCH (n) WHERE n.avg_relevance IS NOT NULL 
   RETURN n.name, n.avg_relevance, n.usage_count 
   ORDER BY n.avg_relevance DESC LIMIT 10'
```

### API Health Check
```bash
curl http://localhost:8003/health
```

## Troubleshooting

### Common Issues

1. **API Returns 422 Error**
   - Ensure request is wrapped with `feedback_request` and `settings` fields
   - Check all required fields are present

2. **Scores Not Persisting**
   - Verify FalkorDB connection (port 6389)
   - Check node UUIDs exist in graph
   - Review `/tmp/graphiti_feedback.log` for errors

3. **Hooks Not Triggering**
   - Verify hooks are enabled in Claude settings
   - Check `/tmp/graphiti_feedback_pending.json` exists
   - Ensure transcript path is accessible

4. **Low Relevance Scores**
   - Adjust scoring weights in configuration
   - Consider context quality and response matching
   - Review evaluation heuristics

### Testing

Run the test script to verify integration:
```bash
python3 /tmp/test_hook_feedback.py
```

Expected output:
- Context cached successfully
- Feedback evaluated and sent
- Scores stored in FalkorDB
- Nodes show updated relevance values

## Best Practices

1. **Score Interpretation**
   - 0.0-0.3: Low relevance, rarely useful
   - 0.3-0.7: Moderate relevance, sometimes useful
   - 0.7-1.0: High relevance, frequently useful

2. **Decay Management**
   - Adjust `half_life_days` based on knowledge freshness needs
   - Run periodic recalculation for active nodes

3. **Performance Optimization**
   - Batch feedback submissions when possible
   - Use async scoring for large memory sets
   - Cache high-relevance memories

4. **Integration Patterns**
   - Always wrap API requests in expected format
   - Handle errors gracefully (don't block on feedback)
   - Log feedback events for debugging

## Future Enhancements

- [ ] Machine learning models for relevance prediction
- [ ] User-specific relevance profiles
- [ ] Cross-query relevance correlation
- [ ] Automatic threshold adjustment
- [ ] Relevance visualization dashboard
- [ ] A/B testing framework for scoring methods

## Related Documentation

- [Graphiti Core Documentation](../README.md)
- [FalkorDB Integration Guide](./falkordb-setup.md)
- [Claude Hooks Reference](../.claude/hooks/README.md)
- [Python API Reference](../server/README.md)