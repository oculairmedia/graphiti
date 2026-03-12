# Reference Documentation Index

> Comprehensive technical documentation. Full API surfaces, schemas, configurations.

## API Reference

| File | Keywords | Description |
|------|----------|-------------|
| [api-reference.md](api-reference.md) | `api`, `rest`, `fastapi`, `endpoints`, `server` | REST API endpoints and schemas |
| [schema-reference.md](schema-reference.md) | `schema`, `node`, `edge`, `falkordb`, `cypher`, `constraint` | Node/edge type definitions |
| [prompts.md](prompts.md) | `prompt`, `dspy`, `signature`, `optimization`, `docstring` | DSPy prompts and signatures |

## Configuration

| File | Keywords | Description |
|------|----------|-------------|
| [config-reference.md](config-reference.md) | `config`, `env`, `environment`, `docker`, `settings` | All environment variables |
| [llm-providers.md](llm-providers.md) | `llm`, `openai`, `anthropic`, `gemini`, `ollama`, `deepseek` | LLM provider configuration |
| [embedders.md](embedders.md) | `embedding`, `vector`, `dimensions`, `voyage`, `openai` | Embedding provider config |
| [temporal-config.md](temporal-config.md) | `temporal`, `workflow`, `activity`, `queue`, `concurrency` | Temporal configuration |

---

## Quick Reference

### Key Environment Variables

```bash
# LLM Configuration
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
LLM_SMALL_MODEL=gpt-4o-nano

# Database
FALKORDB_HOST=falkordb
FALKORDB_PORT=6379
FALKORDB_DATABASE=graphiti_migration

# Temporal (optional)
TEMPORAL_INGESTION_ENABLED=true
TEMPORAL_VISIBILITY_ADDRESS=192.168.50.90:7233
```

### Node Types

| Type | Description | Key Properties |
|------|-------------|----------------|
| `Entity` | Knowledge graph entity | `uuid`, `name`, `summary`, `name_embedding` |
| `Episodic` | Raw episode data | `uuid`, `name`, `content`, `source_description` |
| `Community` | Entity clusters | `uuid`, `name`, `summary` |

### Edge Types

| Type | Description | Key Properties |
|------|-------------|----------------|
| `RELATES_TO` | Entity relationships | `fact`, `source_node_uuid`, `target_node_uuid` |
| `MENTIONS` | Episode-to-entity links | `created_at` |
| `MEMBER_OF` | Entity-to-community | `created_at` |

### REST API Endpoints

```
POST /api/graph/search          # Search graph
POST /api/graph/nodes           # Add nodes
POST /api/graph/edges           # Add edges
GET  /api/graph/nodes/{uuid}    # Get node by UUID
GET  /api/health               # Health check
```

---

> **Tip**: For step-by-step guides, see [../how-to/](../how-to/). For architecture, see [../explanation/](../explanation/).
