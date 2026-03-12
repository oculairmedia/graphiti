# How-to Guides Index

> Step-by-step guides for common tasks. Files are keyword-rich for fast discovery.

## Data Operations

| File | Keywords | Task |
|------|----------|------|
| [add-episode.md](add-episode.md) | `episode`, `ingest`, `entity`, `add`, `data`, `temporal`, `message` | Add data/episodes to knowledge graph |
| [search-graph.md](search-graph.md) | `search`, `query`, `hybrid`, `semantic`, `keyword`, `node`, `edge` | Search the knowledge graph |
| [query-falkordb.md](query-falkordb.md) | `falkordb`, `query`, `cypher`, `graph`, `redis`, `direct`, `raw` | Direct FalkorDB queries |
| [embeddings.md](embeddings.md) | `embedding`, `vector`, `vecf32`, `similarity`, `hnsw`, `index` | Work with embeddings |
| [consolidation.md](consolidation.md) | `consolidation`, `prune`, `merge`, `cleanup`, `nightly`, `dedup` | Run graph consolidation |

## Infrastructure

| File | Keywords | Task |
|------|----------|------|
| [run-docker.md](run-docker.md) | `docker`, `start`, `stop`, `restart`, `compose`, `deploy`, `service` | Docker service management |
| [temporal-workflows.md](temporal-workflows.md) | `temporal`, `workflow`, `ingestion`, `consolidation`, `activity`, `queue` | Temporal.io workflows |

## Development

| File | Keywords | Task |
|------|----------|------|
| [write-tests.md](write-tests.md) | `test`, `pytest`, `unit`, `fixture`, `mock`, `integration` | Write and run tests |
| [add-api-endpoint.md](add-api-endpoint.md) | `api`, `rest`, `fastapi`, `endpoint`, `route`, `handler` | Add REST API endpoints |
| [mcp-tools.md](mcp-tools.md) | `mcp`, `tool`, `server`, `claude`, `cursor` | Add/modify MCP server tools |
| [add-llm-provider.md](add-llm-provider.md) | `llm`, `provider`, `openai`, `anthropic`, `gemini`, `ollama` | Add new LLM provider |

## Debugging

| File | Keywords | Task |
|------|----------|------|
| [debug-ingestion.md](debug-ingestion.md) | `debug`, `ingestion`, `error`, `trace`, `logs`, `temporal` | Debug ingestion issues |

---

## Quick Reference

### Adding Data

```python
from graphiti_core import Graphiti

# Basic episode addition
await graphiti.add_episode(
    name="conversation_1",
    source_description="User conversation",
    source_content="Kendra loves Adidas shoes",
)
```

### Searching

```python
# Hybrid search (semantic + keyword)
results = await graphiti.search(query="shoe preferences", num_results=10)
```

### Docker Commands

```bash
# Safe restart (preserves dependencies)
docker restart graphiti-graph-1

# Check status
docker-compose ps
```

### FalkorDB Queries

```bash
# Count edges
redis-cli -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" --csv

# Count nodes
redis-cli -p 6379 GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)" --csv
```

---

> **Tip**: For architecture understanding, see [../explanation/](../explanation/). For API details, see [../reference/](../reference/).
