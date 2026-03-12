# Schema Reference

> **Keywords**: `schema`, `node`, `edge`, `falkordb`, `cypher`, `constraint`, `index`

## Database

- **Name**: `graphiti_migration`
- **Type**: FalkorDB (Redis Graph)
- **Protocol**: Redis-compatible

---

## Node Types

### Entity

Primary knowledge graph entity.

```cypher
(:Entity {
  uuid: STRING,           // Unique identifier
  name: STRING,           // Entity name
  summary: STRING,        // LLM-generated summary
  name_embedding: VECTOR, // 1536-dim embedding of name
  created_at: DATETIME,
  labels: LIST            // Entity type labels
})
```

**Indexes**:
- `uuid` (RANGE)
- `name_embedding` (HNSW, cosine similarity)

---

### Episodic

Raw episode data ingested into the graph.

```cypher
(:Episodic {
  uuid: STRING,
  name: STRING,
  content: STRING,           // Original content
  source_description: STRING,// Context description
  source: STRING,            // Source identifier
  created_at: DATETIME,
  group_id: STRING           // Optional grouping
})
```

**Indexes**:
- `uuid` (RANGE)

---

### Community

Entity clusters for community detection.

```cypher
(:Community {
  uuid: STRING,
  name: STRING,
  summary: STRING,
  created_at: DATETIME,
  rating: FLOAT            // Community importance
})
```

**Indexes**:
- `uuid` (RANGE)

---

## Edge Types

### RELATES_TO

Relationship between entities.

```cypher
()-[:RELATES_TO {
  uuid: STRING,
  fact: STRING,             // Natural language fact
  source_node_uuid: STRING,
  target_node_uuid: STRING,
  created_at: DATETIME,
  t_valid_at: DATETIME,     // When fact became true
  t_invalid_at: DATETIME,   // When fact was contradicted (NULL = still valid)
  episodes: LIST            // Source episode UUIDs
}]->()
```

**Indexes**:
- `uuid` (RANGE)
- `source_node_uuid`, `target_node_uuid` (RANGE)

---

### MENTIONS

Links episodes to entities they mention.

```cypher
(:Episodic)-[:MENTIONS {
  created_at: DATETIME
}]->(:Entity)
```

---

### MEMBER_OF

Links entities to communities.

```cypher
(:Entity)-[:MEMBER_OF {
  created_at: DATETIME
}]->(:Community)
```

---

## Auxiliary Graphs

### graphiti_prompts

Separate graph for DSPy optimization data.

**Node Types**:
- `PromptVersion` - Versioned prompts for LLM calls
- `TrainingExample` - Training data for optimization
- `ConsolidationReport` - Nightly consolidation metrics

**Indexes**:
- `PromptVersion`: task, version, status
- `TrainingExample`: task

---

## Bi-Temporal Model

Graphiti uses bi-temporal tracking:

| Field | Meaning |
|-------|---------|
| `created_at` | When record was inserted into database |
| `t_valid_at` | When the fact became true in reality |
| `t_invalid_at` | When the fact was contradicted (NULL = still valid) |

This enables:
- Point-in-time queries
- Historical fact tracking
- Contradiction handling

---

## Vector Embeddings

### Storage Format

**CRITICAL**: Must use `vecf32([...])` syntax.

```cypher
# ✅ CORRECT
SET n.name_embedding = vecf32([0.1, 0.2, ...])

# ❌ WRONG - breaks HNSW index
SET n.name_embedding = [0.1, 0.2, ...]
```

### Dimensions

| Provider | Default Dimension |
|----------|------------------|
| OpenAI | 1536 |
| Voyage | 1024 |
| Gemini | 768 |

### HNSW Index

```cypher
CALL db.idx.createNodeIndex({
  label: 'Entity',
  attribute: 'name_embedding',
  type: 'VECTOR',
  options: {
    dimension: 1536,
    similarityFunction: 'cosine'
  }
})
```

---

## Common Queries

### Count All Nodes

```cypher
MATCH (n) RETURN count(n)
```

### Count All Edges

```cypher
MATCH ()-[r]->() RETURN count(r)
```

### Get Entity by Name

```cypher
MATCH (e:Entity {name: 'Alice'}) RETURN e
```

### Get Entity Relationships

```cypher
MATCH (e:Entity {name: 'Alice'})-[r:RELATES_TO]->(t:Entity)
RETURN e.name, r.fact, t.name
```

### Find Active Facts (Not Invalidated)

```cypher
MATCH ()-[r:RELATES_TO]->()
WHERE r.t_invalid_at IS NULL
RETURN r.fact
```

### Vector Similarity Search

```cypher
CALL db.idx.vector.queryNodes('Entity', 'name_embedding', $query_vector, 10)
YIELD node, score
RETURN node.name, score
```

---

## Files to Know

| File | Purpose |
|------|---------|
| `graphiti_core/graph_queries.py` | Cypher query definitions |
| `graphiti_core/driver/falkordb_driver.py` | Driver implementation |
| `graphiti_core/utils/graph_utils.py` | Graph utilities |

---

## See Also

- [../how-to/query-falkordb.md](../how-to/query-falkordb.md) - Direct queries
- [../explanation/bi-temporal-model.md](../explanation/bi-temporal-model.md) - Bi-temporal tracking
- [../gotchas.md](../gotchas.md) - Vector type gotcha
