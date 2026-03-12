# How-to: Add Episodes to the Knowledge Graph

> **Keywords**: `episode`, `ingest`, `entity`, `add`, `data`, `temporal`, `message`, `ingestion`

## Quick Start

```python
from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver

# Initialize
driver = FalkorDriver(host="localhost", port=6379, database="graphiti_migration")
graphiti = Graphiti(graph_driver=driver)

# Add a simple episode
await graphiti.add_episode(
    name="conversation_1",
    source_description="User conversation about preferences",
    source_content="Kendra loves Adidas shoes and follows NBA basketball",
)
```

---

## Episode Structure

An **episode** is a unit of information to be ingested into the knowledge graph.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `name` | Yes | Unique identifier for the episode |
| `source_content` | Yes | The text to extract entities/edges from |
| `source_description` | No | Context for the content |
| `reference_time` | No | When the facts became true (defaults to now) |
| `previous_episode_uuid` | No | Link to chronologically previous episode |
| `group_id` | No | Group episodes by topic/conversation |

---

## Common Patterns

### Basic Ingestion

```python
await graphiti.add_episode(
    name="ep_001",
    source_content="Alice works at Acme Corp as a software engineer.",
)
```

### With Reference Time

```python
from datetime import datetime

await graphiti.add_episode(
    name="ep_002",
    source_content="Bob joined the team yesterday.",
    reference_time=datetime(2026, 3, 10),  # When the fact became true
)
```

### Chained Episodes (Conversation Flow)

```python
ep1 = await graphiti.add_episode(
    name="conv_turn_1",
    source_content="User asked about product X",
)

ep2 = await graphiti.add_episode(
    name="conv_turn_2",
    source_content="Assistant explained product X features",
    previous_episode_uuid=ep1.uuid,
)
```

### Grouped Episodes

```python
await graphiti.add_episode(
    name="session_123_msg_1",
    source_content="User inquiry about order #456",
    group_id="session_123",
)
```

---

## Using Temporal Ingestion (Production)

For production workloads, use Temporal-based ingestion:

```python
# Enable Temporal ingestion
import os
os.environ["TEMPORAL_INGESTION_ENABLED"] = "true"
os.environ["TEMPORAL_VISIBILITY_ADDRESS"] = "192.168.50.90:7233"

# Episodes are automatically routed through Temporal
# This provides: retries, observability, rate limiting
```

### Temporal Configuration

```bash
# .env
TEMPORAL_INGESTION_ENABLED=true
TEMPORAL_VISIBILITY_ADDRESS=192.168.50.90:7233
TEMPORAL_INGESTION_NAMESPACE=graphiti

# Rate limiting (prevents LLM API throttling)
TEMPORAL_EXTRACT_MAX_CONCURRENT_ACTIVITIES=3
TEMPORAL_RESOLVE_MAX_CONCURRENT_ACTIVITIES=3
TEMPORAL_RATE_LIMIT_POST_LLM_DELAY=2.0
```

---

## What Happens During Ingestion

1. **Extract Nodes** - LLM identifies entities in content
2. **Resolve Nodes** - Deduplicates entities by name
3. **Extract Edges** - LLM identifies relationships
4. **Persist** - Stores nodes and edges in FalkorDB

### Via Temporal (when enabled)

```
Episode → Temporal Workflow
           ├── Activity: extract_nodes
           ├── Activity: resolve_nodes  
           ├── Activity: extract_edges
           └── Activity: resolve_edges_and_persist
```

---

## Custom Entity Types

Define custom entity types for domain-specific extraction:

```python
from graphiti_core import Graphiti
from pydantic import BaseModel

class PersonEntity(BaseModel):
    name: str
    role: str | None = None
    company: str | None = None

class CompanyEntity(BaseModel):
    name: str
    industry: str | None = None

# Pass to add_episode
await graphiti.add_episode(
    name="ep_custom",
    source_content="Alice Smith is a developer at TechCorp",
    entity_types=[PersonEntity, CompanyEntity],
)
```

---

## Troubleshooting

### Issue: Episodes not appearing in graph

**Check**:
```bash
# Count episodic nodes
redis-cli -p 6379 GRAPH.QUERY graphiti_migration \
  "MATCH (e:Episodic) RETURN count(e)" --csv
```

**Common causes**:
- LLM API errors (check logs)
- Rate limiting (reduce concurrency)
- Wrong database name

### Issue: Entities not extracted

**Check LLM response format**:
- Ensure LLM supports structured output
- Check `graphiti_core/prompts/extract_nodes.py` signature

### Issue: Temporal workflow stuck

**Check**:
```bash
# Temporal UI
open http://192.168.50.90:8080

# Worker logs
docker logs graphiti-graphiti-temporal-ingestion-worker-1
```

---

## Files to Know

| File | Purpose |
|------|---------|
| `graphiti_core/graphiti.py` | Main `add_episode()` implementation |
| `graphiti_core/extract_nodes.py` | Entity extraction logic |
| `graphiti_core/extract_edges.py` | Relationship extraction |
| `graphiti_core/node_operations.py` | Node resolution and merging |
| `worker/temporal_ingestion_worker.py` | Temporal ingestion worker |

---

## See Also

- [search-graph.md](search-graph.md) - Query the graph after ingestion
- [debug-ingestion.md](debug-ingestion.md) - Troubleshoot ingestion issues
- [temporal-workflows.md](temporal-workflows.md) - Temporal details
- [../explanation/ingestion-pipeline.md](../explanation/ingestion-pipeline.md) - Architecture
