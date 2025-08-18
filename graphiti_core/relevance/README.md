# Relevance Scoring System for Graphiti

## Overview

The relevance scoring system enhances Graphiti's retrieval capabilities by tracking and learning from user interactions with memories. It provides both manual and automated scoring mechanisms to improve search quality over time.

## Features

### Core Capabilities
- **LLM-based Scoring**: Automatic relevance evaluation using language models
- **Heuristic Scoring**: Fast keyword-based relevance calculation
- **Hybrid Scoring**: Combines LLM and heuristic methods for balanced results
- **Time Decay**: Reduces scores over time to favor fresh content
- **Reciprocal Rank Fusion (RRF)**: Combines multiple ranking sources
- **Historical Tracking**: Maintains score history for pattern analysis

### API Endpoints

#### Submit Manual Feedback
```http
POST /feedback/relevance
{
  "query_id": "uuid",
  "memory_scores": {
    "memory_id_1": 0.9,
    "memory_id_2": 0.3
  }
}
```

#### Auto-Score Memories
```http
POST /feedback/relevance/auto-score
{
  "query_id": "uuid",
  "original_query": "What is machine learning?",
  "memory_contents": {
    "mem_1": "Machine learning is...",
    "mem_2": "AI involves..."
  },
  "agent_response": "Machine learning is a subset of AI..."
}
```

#### Retrieve with Scores
```http
GET /feedback/memories?group_id=xxx&include_scores=true&min_relevance=0.5
```

#### Bulk Recalculation
```http
POST /feedback/recalculate
{
  "group_id": "xxx",
  "recalculation_method": "hybrid"
}
```

#### Apply RRF
```http
POST /feedback/rrf
{
  "rankings": {
    "semantic": ["mem1", "mem2", "mem3"],
    "keyword": ["mem2", "mem1", "mem4"]
  },
  "k": 60
}
```

## Architecture

### Components

1. **RelevanceScorer**: Core scoring engine
   - LLM-based evaluation
   - Heuristic scoring
   - Score combination logic

2. **MemoryFeedback**: Feedback data model
   - Historical scores
   - Usage statistics
   - Decay tracking

3. **ScoringConfig**: Configuration management
   - Scoring parameters
   - Decay settings
   - Threshold values

4. **RelevanceEnhancedSearch**: Search integration
   - Score-based filtering
   - Result reranking
   - Automatic feedback

### Data Flow

```
Query → Search → Results → Scoring → Feedback → Storage
                    ↓
                User/Agent
```

## Configuration

### Environment Variables
```bash
# Enable/disable scoring methods
RELEVANCE_LLM_SCORING=true
RELEVANCE_HEURISTIC_SCORING=true

# Decay settings
RELEVANCE_DECAY_ENABLED=true
RELEVANCE_HALF_LIFE_DAYS=30

# Thresholds
RELEVANCE_MIN_THRESHOLD=0.3
RELEVANCE_HIGH_THRESHOLD=0.7

# RRF parameter
RELEVANCE_RRF_K=60
```

### Scoring Weights
```python
config = ScoringConfig(
    semantic_weight=0.4,    # Embedding similarity
    keyword_weight=0.3,     # BM25 score
    graph_weight=0.2,       # Graph traversal
    historical_weight=0.1   # Past relevance
)
```

## Usage Examples

### Basic Scoring
```python
from graphiti_core.relevance import RelevanceScorer, ScoringContext

scorer = RelevanceScorer(driver, llm_client)

context = ScoringContext(
    original_query="Tell me about Python",
    memory_content="Python is a programming language",
    memory_id="mem-123"
)

score = await scorer.score_memory(context, method="hybrid")
```

### Enhanced Search
```python
from graphiti_core.search.search_with_relevance import RelevanceEnhancedSearch

search = RelevanceEnhancedSearch(clients)

results = await search.search_with_relevance(
    query="machine learning applications",
    include_relevance_scores=True,
    apply_relevance_filter=True,
    auto_update_scores=True
)
```

### Apply RRF
```python
# Combine rankings from different sources
fused = await scorer.apply_reciprocal_rank_fusion({
    "semantic": ["mem1", "mem2", "mem3"],
    "keyword": ["mem2", "mem1", "mem4"],
    "graph": ["mem3", "mem4", "mem1"]
})
```

## Score Calculation

### LLM Scoring
The LLM evaluates relevance based on:
- Query-memory topical alignment
- Information usefulness
- Contribution to response

### Heuristic Scoring
Fast scoring using:
- Jaccard similarity of keywords
- Presence in agent response
- Term frequency analysis

### Decay Formula
```python
score * exp(-time_delta / half_life)
```

### Combined Score
```python
weighted_avg = Σ(score_i * weight_i) / Σ(weight_i)
```

## Database Schema

### Added Fields
```cypher
// Entity and Edge nodes
n.relevance_scores     // JSON array of historical scores
n.avg_relevance        // Float: average relevance (0-1)
n.usage_count          // Integer: retrieval count
n.successful_uses      // Integer: successful applications
n.last_accessed        // Datetime: last retrieval
n.last_scored          // Datetime: last scoring
n.decay_factor         // Float: current decay multiplier
n.query_embeddings     // Array: query vectors
```

## Performance Considerations

### Caching Strategy
- Cache high-relevance memories (score > 0.7)
- TTL: 1 hour default
- LRU eviction policy

### Batch Processing
- Score updates batched (size: 10)
- Async processing for large sets
- Background decay updates

### Optimization Tips
1. Use heuristic scoring for real-time needs
2. Schedule LLM scoring during low-load periods
3. Adjust decay half-life based on content freshness needs
4. Cache frequently accessed high-score memories

## Testing

Run tests:
```bash
pytest tests/test_relevance_scoring.py -v
```

Test coverage includes:
- Model validation
- Scoring methods
- Decay calculations
- RRF algorithm
- Integration workflows

## Future Enhancements

### Planned Features
- [ ] Reinforcement learning from user feedback
- [ ] A/B testing for scoring parameters
- [ ] Multi-modal relevance (text + image)
- [ ] Personalized scoring per user
- [ ] Active learning for score improvement

### Research Areas
- Contrastive learning for better embeddings
- Graph neural networks for structural relevance
- Temporal patterns in score evolution
- Cross-lingual relevance scoring

## Troubleshooting

### Common Issues

1. **Low LLM scores**: Check prompt quality and context completeness
2. **Decay too aggressive**: Increase half-life parameter
3. **RRF not converging**: Adjust k parameter (default: 60)
4. **Cache misses**: Increase cache size or TTL

### Debug Logging
```python
import logging
logging.getLogger("graphiti_core.relevance").setLevel(logging.DEBUG)
```

## Contributing

When adding new scoring methods:
1. Extend `RelevanceScorer` class
2. Add method to `ScoringContext`
3. Update combine_scores logic
4. Add tests
5. Document in this README

## References

- [Reciprocal Rank Fusion Paper](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)
- [RAGAS Metrics](https://docs.ragas.io/)
- [LangChain Reranking](https://python.langchain.com/docs/integrations/retrievers/)
- [Time Decay in Recommender Systems](https://dl.acm.org/doi/10.1145/2043932.2043989)