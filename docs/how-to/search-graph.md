# How-to: Search the Knowledge Graph

> **Keywords**: `search`, `query`, `hybrid`, `semantic`, `keyword`, `node`, `edge`, `rerank`

## Quick Start

```python
from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver

driver = FalkorDriver(host="localhost", port=6379, database="graphiti_migration")
graphiti = Graphiti(graph_driver=driver)

# Hybrid search (semantic + keyword)
results = await graphiti.search(
    query="What does Alice do?",
    num_results=10,
)
```

---

## Search Types

### 1. Hybrid Search (Default)

Combines semantic (vector) and keyword (BM25) search:

```python
results = await graphiti.search(
    query="software engineer preferences",
    num_results=10,
)
```

### 2. Semantic Search

Vector similarity only:

```python
results = await graphiti.search(
    query="basketball fan",
    search_type="semantic",
    num_results=10,
)
```

### 3. Keyword Search

BM25 only:

```python
results = await graphiti.search(
    query="Alice Acme Corp",
    search_type="keyword",
    num_results=10,
)
```

---

## Search Results

### Edge Results (Default)

Returns relationships between entities:

```python
for edge in results.edges:
    print(f"{edge.source_node.name} --[{edge.fact}]--> {edge.target_node.name}")
```

### Node Results

```python
nodes = await graphiti.search_nodes(
    query="Alice",
    num_results=10,
)

for node in nodes:
    print(f"{node.name}: {node.summary}")
```

---

## Reranking

Improve relevance by reranking based on graph distance:

```python
from graphiti_core.search import SearchConfig

results = await graphiti.search(
    query="tech companies",
    num_results=20,
    search_type="hybrid",
    reranker="graph_distance",  # Rerank by graph proximity
)

# Top results are now more relevant based on graph structure
```

---

## Advanced Options

### Filter by Group

```python
results = await graphiti.search(
    query="order status",
    group_ids=["session_123"],
    num_results=10,
)
```

### Temporal Range

```python
from datetime import datetime

results = await graphiti.search(
    query="project updates",
    min_created_at=datetime(2026, 1, 1),
    max_created_at=datetime(2026, 3, 1),
    num_results=10,
)
```

### Filter by Entity Type

```python
results = await graphiti.search(
    query="engineers",
    entity_types=["Person"],
    num_results=10,
)
```

---

## Search Recipes

Pre-built search configurations for common patterns:

```python
from graphiti_core.search import SearchRecipy

# Most relevant edges
results = await graphiti.search(
    query="...",
    recipe=SearchRecipy.HYBRID_SEARCH_RERANK,
)

# Fast keyword lookup
results = await graphiti.search(
    query="...",
    recipe=SearchRecipy.KEYWORD_SEARCH,
)

# Semantic similarity
results = await graphiti.search(
    query="...",
    recipe=SearchRecipy.SEMANTIC_SEARCH,
)
```

---

## Direct FalkorDB Queries

For complex queries not supported by search API:

```python
# Via driver
cypher = """
MATCH (e:Entity)-[r:RELATES_TO]->(t:Entity)
WHERE e.name CONTAINS 'Alice'
RETURN e, r, t
LIMIT 10
"""
result = await driver.execute_query(cypher)

# Via redis-cli
import subprocess
result = subprocess.run([
    "redis-cli", "-p", "6379",
    "GRAPH.QUERY", "graphiti_migration",
    cypher,
    "--csv"
], capture_output=True, text=True)
```

See [query-falkordb.md](query-falkordb.md) for more.

---

## Performance Tips

1. **Use smaller `num_results`** for faster queries
2. **Filter early** with `group_ids` or `entity_types`
3. **Rerank after search** rather than increasing `num_results`
4. **Check HNSW index** exists on embeddings

```bash
# Verify vector index
redis-cli -p 6379 GRAPH.QUERY graphiti_migration \
  "CALL db.indexes()" --csv
```

---

## Troubleshooting

### Issue: 0 results from semantic search

**Causes**:
1. Embeddings stored as List not Vectorf32 (see [../gotchas.md](../gotchas.md))
2. No entities with embeddings
3. Query embedding failed

**Fix**:
```bash
python3 scripts/validate_embeddings.py
```

### Issue: Results not relevant

**Solutions**:
1. Use hybrid search (default)
2. Enable reranking
3. Check query specificity

### Issue: Slow queries

**Check**:
1. HNSW index exists
2. Number of results requested
3. FalkorDB memory usage

---

## Files to Know

| File | Purpose |
|------|---------|
| `graphiti_core/search.py` | Search implementation |
| `graphiti_core/search_utils/` | Search utilities |
| `graphiti_core/cross_encoder/` | Reranking logic |

---

## See Also

- [add-episode.md](add-episode.md) - Add data to search
- [query-falkordb.md](query-falkordb.md) - Direct database queries
- [../explanation/vector-search.md](../explanation/vector-search.md) - How vector search works
