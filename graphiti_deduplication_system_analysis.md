# Graphiti Deduplication System - Comprehensive Analysis

## Overview

Graphiti implements a sophisticated multi-stage deduplication system that operates at both node and edge levels. The system uses a combination of exact matching, fuzzy matching, embedding similarity, and LLM-based resolution to identify and merge duplicate entities across the knowledge graph.

## Key Components

### 1. Main Deduplication Functions

- **`dedupe_nodes_bulk`**: Bulk node deduplication across multiple episodes
- **`dedupe_edges_bulk`**: Bulk edge deduplication across multiple episodes  
- **`resolve_extracted_nodes`**: Core node resolution and deduplication logic
- **`resolve_extracted_edges`**: Edge resolution and conflict detection
- **`dedupe_node_list`**: LLM-based node deduplication for lists
- **`dedupe_edge_list`**: LLM-based edge deduplication for lists

### 2. Supporting Functions

- **`normalize_entity_name`**: Standardizes entity names for consistent matching
- **`calculate_fuzzy_similarity`**: Computes string similarity using SequenceMatcher
- **`generate_deterministic_uuid`**: Creates consistent UUIDs to prevent race conditions
- **`merge_node_into`**: Physically merges duplicate nodes by transferring edges
- **`build_duplicate_of_edges`**: Creates IS_DUPLICATE_OF relationships

## Deduplication Process

### Stage 1: Exact Name Matching

The system first attempts exact name matches within the database:

```python
# Cross-graph deduplication (default: enabled)
if enable_cross_graph_deduplication:
    exact_query = """
    MATCH (n:Entity)
    WHERE n.name = $name
    RETURN n
    ORDER BY n.created_at
    LIMIT 1
    """
else:
    # Same-group only deduplication
    exact_query = """
    MATCH (n:Entity)
    WHERE n.name = $name AND n.group_id = $group_id
    RETURN n
    ORDER BY n.created_at
    LIMIT 1
    """
```

### Stage 2: Fuzzy Name Matching

For near-misses, the system uses fuzzy string matching:

```python
def calculate_fuzzy_similarity(name1: str, name2: str) -> float:
    # Normalize both names for comparison
    norm1 = normalize_entity_name(name1)
    norm2 = normalize_entity_name(name2)
    
    # Calculate similarity using SequenceMatcher
    return SequenceMatcher(None, norm1, norm2).ratio()
```

**Default threshold**: 0.9 (configurable via `DEDUP_FUZZY_THRESHOLD`)

### Stage 3: Embedding-Based Similarity

The system generates embeddings for entity names and compares using cosine similarity:

```python
# Node deduplication threshold
min_score = 0.8  # Very high similarity required

# Edge deduplication threshold  
min_score = 0.6  # Moderate similarity required
```

### Stage 4: LLM-Based Resolution

For ambiguous cases, the system uses LLM to make final deduplication decisions through structured prompts.

## Configuration Parameters

### Core Thresholds

| Parameter | Default | Description |
|-----------|---------|-------------|
| `DEDUP_SIMILARITY_THRESHOLD` | 0.6 | Main embedding similarity threshold |
| `DEDUP_FUZZY_THRESHOLD` | 0.9 | Fuzzy name matching threshold |
| Node embedding threshold | 0.8 | Embedding similarity for nodes |
| Edge embedding threshold | 0.6 | Embedding similarity for edges |
| Background dedup threshold | 0.6 | Lower threshold for background processing |

### Feature Flags

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ENABLE_CROSS_GRAPH_DEDUPLICATION` | true | Enable deduplication across different group_ids |
| `ENABLE_AGGRESSIVE_DEDUP` | true | Enable fuzzy matching |
| `DEDUP_NORMALIZE_NAMES` | true | Enable name normalization |
| `CHUTES_ENABLE_BATCH_PROCESSING` | false | Enable batch LLM deduplication |

## Cross-Graph Deduplication

**Important**: Cross-graph deduplication is **enabled by default** in recent versions.

```python
class Graphiti:
    def __init__(
        self,
        # ... other parameters ...
        enable_cross_graph_deduplication: bool = True,  # DEFAULT IS TRUE
    ):
```

When enabled:
- Entities can be deduplicated across different `group_id` values
- Search operations span all groups instead of being restricted to same group
- Merge operations can combine entities from different graphs

## Deduplication Workflows

### 1. Real-time Deduplication (During Ingestion)

1. **Extract entities** from new episodes
2. **Generate embeddings** for all entities
3. **Apply exact matching** first (fastest)
4. **Apply fuzzy matching** for near-misses
5. **Use LLM resolution** for complex cases
6. **Create IS_DUPLICATE_OF edges** between duplicates
7. **Merge duplicate nodes** by transferring all edges

### 2. Background Deduplication

Runs automatically after every few episodes:
- Uses lower threshold (0.6) for broader matching
- Processes up to 100 entities per group
- Triggered based on episode count

### 3. Manual Deduplication

Can be triggered via worker messages:
- Configurable similarity thresholds
- Supports both nodes and edges
- Can target specific groups or run globally

## Merge Operations

When duplicates are identified, the system:

1. **Creates IS_DUPLICATE_OF edges** for audit trail
2. **Transfers all incoming edges** from duplicate to canonical node
3. **Transfers all outgoing edges** from duplicate to canonical node
4. **Merges edge properties** using defined policies
5. **Updates centrality scores** for affected nodes
6. **Optionally deletes** or tombstones duplicate nodes

### Edge Property Merging Policy

- **episodes**: Union of lists (preserve unique values)
- **created_at**: Keep earliest timestamp
- **valid_at**: Use minimum timestamp
- **invalid_at**: Use maximum timestamp
- **fact/fact_embedding**: Prefer existing (canonical) unless empty
- **attributes**: Merge dictionaries, prefer existing on conflict

## Potential Issues and Troubleshooting

### Why You Might Still See Subtle Duplication

1. **High similarity thresholds**: 0.8 threshold for nodes is very conservative
2. **Embedding quality**: Similar entities might have different embeddings
3. **Name normalization gaps**: Normalization might not catch all variations
4. **LLM inconsistency**: Different decisions for similar cases
5. **Timing issues**: Entities in different batches might not be compared
6. **Configuration overrides**: Cross-graph deduplication might be disabled

### Debugging Steps

1. **Check environment variables**:
   ```bash
   ENABLE_CROSS_GRAPH_DEDUPLICATION=true
   DEDUP_SIMILARITY_THRESHOLD=0.6
   ENABLE_AGGRESSIVE_DEDUP=true
   ```

2. **Lower thresholds temporarily** to see if more duplicates are caught

3. **Check logs** for deduplication path being taken

4. **Run integration tests**:
   ```bash
   python testing/integration/test_cross_graph_dedup.py
   ```

5. **Monitor worker logs** for deduplication activity

### Performance Considerations

- **Batch processing**: Use `CHUTES_ENABLE_BATCH_PROCESSING=true` for efficiency
- **Centrality recalculation**: Can be expensive after large merges
- **Memory usage**: Large embedding comparisons can be memory-intensive
- **Database load**: Cross-graph queries are more expensive than single-group

## File Locations

### Core Implementation
- `graphiti_core/utils/maintenance/node_operations.py` - Main node deduplication logic
- `graphiti_core/utils/maintenance/edge_operations.py` - Edge deduplication and merging
- `graphiti_core/utils/bulk_utils.py` - Bulk processing functions
- `graphiti_core/graphiti.py` - Main orchestration

### Configuration
- `graphiti_core/ingestion/worker.py` - Worker-based deduplication
- `docker-compose.queue-prod.yml` - Environment variable examples
- `testing/integration/test_cross_graph_dedup.py` - Cross-graph testing

### Maintenance Scripts
- `run_deduplication.py` - Standalone deduplication script
- `maintenance_dedupe_entities.py` - Advanced deduplication utilities

## Best Practices

1. **Monitor deduplication logs** regularly for effectiveness
2. **Tune thresholds** based on your data characteristics
3. **Enable cross-graph deduplication** unless you specifically need isolation
4. **Use batch processing** for better performance with compatible LLM clients
5. **Test deduplication** with representative data before production deployment
6. **Consider centrality impact** when planning large deduplication operations

## Conclusion

Graphiti's deduplication system is sophisticated and configurable, with cross-graph deduplication enabled by default. The multi-stage approach (exact → fuzzy → embedding → LLM) provides robust duplicate detection while the configurable thresholds allow tuning for different use cases. If you're experiencing subtle duplication, focus on threshold tuning and ensuring cross-graph deduplication is properly enabled.
