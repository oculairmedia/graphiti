# How-to: Query FalkorDB Directly

> **Keywords**: `falkordb`, `query`, `cypher`, `graph`, `redis`, `direct`, `raw`

## Quick Start

```bash
# Count all nodes
redis-cli -p 6379 GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)" --csv

# Count all edges
redis-cli -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" --csv

# List entity names
redis-cli -p 6379 GRAPH.QUERY graphiti_migration "MATCH (e:Entity) RETURN e.name LIMIT 10" --csv
```

---

## Connection Info

| Setting | Value |
|---------|-------|
| Host | localhost (from host), falkordb (from containers) |
| Port | 6379 |
| Database | graphiti_migration |
| Protocol | Redis-compatible |

---

## Common Queries

### Node Counts

```bash
# Total nodes
redis-cli -p 6379 GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)" --csv

# Entity nodes
redis-cli -p 6379 GRAPH.QUERY graphiti_migration "MATCH (e:Entity) RETURN count(e)" --csv

# Episodic nodes
redis-cli -p 6379 GRAPH.QUERY graphiti_migration "MATCH (e:Episodic) RETURN count(e)" --csv

# Community nodes
redis-cli -p 6379 GRAPH.QUERY graphiti_migration "MATCH (c:Community) RETURN count(c)" --csv
```

### Edge Counts

```bash
# Total edges
redis-cli -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" --csv

# RELATES_TO edges
redis-cli -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r:RELATES_TO]->() RETURN count(r)" --csv

# MENTIONS edges
redis-cli -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r:MENTIONS]->() RETURN count(r)" --csv
```

### Find Specific Entity

```bash
redis-cli -p 6379 GRAPH.QUERY graphiti_migration \
  "MATCH (e:Entity {name: 'Alice'}) RETURN e.uuid, e.summary" --csv
```

### Entity Relationships

```bash
# All relationships for an entity
redis-cli -p 6379 GRAPH.QUERY graphiti_migration \
  "MATCH (e:Entity {name: 'Alice'})-[r:RELATES_TO]->(t) RETURN e.name, r.fact, t.name" --csv
```

### Recent Episodes

```bash
redis-cli -p 6379 GRAPH.QUERY graphiti_migration \
  "MATCH (e:Episodic) RETURN e.name, e.content ORDER BY e.created_at DESC LIMIT 10" --csv
```

---

## Python API

### Using FalkorDriver

```python
from graphiti_core.driver.falkordb_driver import FalkorDriver

driver = FalkorDriver(host="localhost", port=6379, database="graphiti_migration")

# Execute query
result = await driver.execute_query(
    "MATCH (e:Entity) RETURN e.name, e.summary LIMIT 10"
)

for record in result:
    print(record["e.name"], record["e.summary"])
```

### Using Redis Client

```python
import redis

client = redis.Redis(host="localhost", port=6379)

# Execute query
result = client.execute_command(
    "GRAPH.QUERY",
    "graphiti_migration",
    "MATCH (n) RETURN count(n)",
    "--compact"
)
print(result)
```

---

## Node Types

| Label | Description | Key Properties |
|-------|-------------|----------------|
| `Entity` | Knowledge graph entity | `uuid`, `name`, `summary`, `name_embedding` |
| `Episodic` | Raw episode data | `uuid`, `name`, `content`, `source_description` |
| `Community` | Entity clusters | `uuid`, `name`, `summary` |

### Entity Properties

```bash
redis-cli -p 6379 GRAPH.QUERY graphiti_migration \
  "MATCH (e:Entity) RETURN keys(e) LIMIT 1" --csv
```

Common: `uuid`, `name`, `summary`, `name_embedding`, `created_at`, `labels`

### Episodic Properties

```bash
redis-cli -p 6379 GRAPH.QUERY graphiti_migration \
  "MATCH (e:Episodic) RETURN keys(e) LIMIT 1" --csv
```

Common: `uuid`, `name`, `content`, `source_description`, `source`, `created_at`

---

## Edge Types

| Type | From | To | Description |
|------|------|-----|----|
| `RELATES_TO` | Entity | Entity | Relationship between entities |
| `MENTIONS` | Episodic | Entity | Episode mentions entity |
| `MEMBER_OF` | Entity | Community | Entity belongs to community |

### Edge Properties

```bash
redis-cli -p 6379 GRAPH.QUERY graphiti_migration \
  "MATCH ()-[r:RELATES_TO]->() RETURN keys(r) LIMIT 1" --csv
```

RELATES_TO: `uuid`, `fact`, `source_node_uuid`, `target_node_uuid`, `created_at`, `t_valid_at`, `t_invalid_at`, `episodes`

---

## Vector Operations

### Check Embeddings

```bash
# Check if entity has embedding
redis-cli -p 6379 GRAPH.QUERY graphiti_migration \
  "MATCH (e:Entity) WHERE e.name_embedding IS NOT NULL RETURN count(e)" --csv
```

### Validate Embeddings

```bash
# Check for corrupted embeddings
python3 scripts/validate_embeddings.py

# Fix corrupted embeddings
python3 scripts/validate_embeddings.py --fix
```

**Critical**: Always use `vecf32([...])` syntax for storing embeddings (see [../gotchas.md](../gotchas.md)).

---

## Indexes

### List Indexes

```bash
redis-cli -p 6379 GRAPH.QUERY graphiti_migration "CALL db.indexes()" --csv
```

### Expected Indexes

- UUID indexes on all node/edge types
- HNSW index on `Entity.name_embedding`

---

## Schema Operations

### List Node Labels

```bash
redis-cli -p 6379 GRAPH.QUERY graphiti_migration "CALL db.labels()" --csv
```

### List Relationship Types

```bash
redis-cli -p 6379 GRAPH.QUERY graphiti_migration "CALL db.relationshipTypes()" --csv
```

---

## Performance Tips

1. **Use LIMIT** - queries can return millions of rows
2. **Use indexes** - queries on `uuid` should be fast
3. **Avoid full scans** - filter early in query

```bash
# ❌ Slow - full scan
redis-cli -p 6379 GRAPH.QUERY graphiti_migration \
  "MATCH (e:Entity) WHERE e.summary CONTAINS 'Alice' RETURN e"

# ✅ Faster - indexed lookup
redis-cli -p 6379 GRAPH.QUERY graphiti_migration \
  "MATCH (e:Entity {name: 'Alice'}) RETURN e"
```

---

## Troubleshooting

### Issue: Connection refused

**Check**:
```bash
docker-compose ps falkordb
```

**Fix**:
```bash
docker-compose up -d falkordb
```

### Issue: Wrong database

**Symptom**: 0 nodes when expecting data

**Fix**: Check database name (default is `graphiti_migration`)

```bash
redis-cli -p 6379 GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)" --csv
```

### Issue: Vector search returns 0

**Causes**:
1. Embeddings stored as List not Vectorf32
2. HNSW index missing

**Fix**:
```bash
python3 scripts/validate_embeddings.py --fix
```

---

## Files to Know

| File | Purpose |
|------|---------|
| `graphiti_core/driver/falkordb_driver.py` | Python driver |
| `graphiti_core/driver/falkordb_utils.py` | Query utilities |
| `scripts/validate_embeddings.py` | Embedding validation |

---

## See Also

- [../reference/schema-reference.md](../reference/schema-reference.md) - Full schema docs
- [search-graph.md](search-graph.md) - Search API
- [../gotchas.md](../gotchas.md) - Vector type gotcha
