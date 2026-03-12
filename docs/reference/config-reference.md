# Configuration Reference

> **Keywords**: `config`, `env`, `environment`, `docker`, `settings`, `variables`

## Environment Variables

### LLM Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | Required | OpenAI API key |
| `LLM_MODEL` | `gpt-4o-mini` | Main LLM model |
| `LLM_SMALL_MODEL` | `gpt-4o-nano` | Small model for simple tasks |
| `LLM_BASE_URL` | - | Custom LLM endpoint |
| `LLM_API_VERSION` | - | Azure API version |
| `LLM_TEMPERATURE` | `0.0` | LLM temperature |
| `LLM_MAX_TOKENS` | - | Max tokens per response |

### Anthropic

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | - | Anthropic API key |

### Google Gemini

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_API_KEY` | - | Google API key |

### Groq

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | - | Groq API key |

---

### Embedding Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `EMBEDDING_DIM` | `1536` | Embedding dimensions |
| `EMBEDDING_BASE_URL` | - | Custom embedding endpoint |

---

### Database Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `FALKORDB_HOST` | `falkordb` | FalkorDB host |
| `FALKORDB_PORT` | `6379` | FalkorDB port |
| `FALKORDB_DATABASE` | `graphiti_migration` | Database name |
| `FALKORDB_USER` | - | Username (optional) |
| `FALKORDB_PASSWORD` | - | Password (optional) |

**Neo4j (alternative)**:

| Variable | Default | Description |
|----------|---------|-------------|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection URI |
| `NEO4J_USER` | `neo4j` | Username |
| `NEO4J_PASSWORD` | - | Password |

---

### Temporal Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `TEMPORAL_INGESTION_ENABLED` | `false` | Enable Temporal ingestion |
| `TEMPORAL_VISIBILITY_ADDRESS` | - | Temporal server address |
| `TEMPORAL_INGESTION_NAMESPACE` | `graphiti` | Temporal namespace |
| `TEMPORAL_INGESTION_WORKFLOW_TIMEOUT_HOURS` | `8` | Workflow timeout |

**Task Queues (Staged Mode)**:

| Variable | Default | Description |
|----------|---------|-------------|
| `TEMPORAL_INGESTION_WORKFLOW_TASK_QUEUE` | - | Workflow task queue |
| `TEMPORAL_INGESTION_EXTRACT_TASK_QUEUE` | - | Extract activity queue |
| `TEMPORAL_INGESTION_RESOLVE_TASK_QUEUE` | - | Resolve activity queue |
| `TEMPORAL_INGESTION_EDGE_TASK_QUEUE` | - | Edge activity queue |
| `TEMPORAL_INGESTION_PERSIST_TASK_QUEUE` | - | Persist activity queue |

**Rate Limiting**:

| Variable | Default | Description |
|----------|---------|-------------|
| `TEMPORAL_MAX_CONCURRENT_ACTIVITIES` | `5` | Max concurrent activities |
| `TEMPORAL_EXTRACT_MAX_CONCURRENT_ACTIVITIES` | `3` | Max extract activities |
| `TEMPORAL_RESOLVE_MAX_CONCURRENT_ACTIVITIES` | `3` | Max resolve activities |
| `TEMPORAL_EDGE_MAX_CONCURRENT_ACTIVITIES` | `2` | Max edge activities |
| `TEMPORAL_PERSIST_MAX_CONCURRENT_ACTIVITIES` | `5` | Max persist activities |
| `TEMPORAL_RATE_LIMIT_POST_LLM_DELAY` | `0.0` | Delay after LLM calls |

**Consolidation**:

| Variable | Default | Description |
|----------|---------|-------------|
| `TEMPORAL_CONSOLIDATION_TASK_QUEUE` | `graphiti-consolidation` | Consolidation queue |
| `TEMPORAL_CONSOLIDATION_MAX_ACTIVITIES` | `2` | Max consolidation activities |

---

### Graph Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `NODE_LIMIT` | `100000` | Max nodes to return |
| `EDGE_LIMIT` | `100000` | Max edges to return |

---

### Telemetry

| Variable | Default | Description |
|----------|---------|-------------|
| `GRAPHITI_TELEMETRY_ENABLED` | `true` | Enable telemetry |
| `GRAPHITI_TELEMETRY_ANONYMOUS_ID` | Auto-generated | Anonymous ID |

---

## Docker Compose Services

### Core Services

| Service | Port | Description |
|---------|------|-------------|
| `falkordb` | 6379 | Primary database |
| `graph` | 8003 | REST API |
| `graph-visualizer-rust` | 3000 | Visualization backend |
| `frontend` | 8085 | React frontend |
| `nginx` | 8088, 8443 | Reverse proxy |
| `graphiti-mcp` | 8001 | MCP server |

### Optional Services (Profiles)

| Service | Profile | Description |
|---------|---------|-------------|
| `graphiti-temporal-ingestion-worker-*` | `temporal-staged` | Temporal workers |
| `graphiti-temporal-consolidation-worker` | `temporal-consolidation` | Consolidation worker |

---

## Memory Configuration

### FalkorDB

```yaml
services:
  falkordb:
    deploy:
      resources:
        limits:
          memory: 16G
    command:
      - --maxmemory
      - 8gb
      - --save
      - 60 1
      - 300 5
```

**Explanation**:
- 16GB container limit (handles RDB reload overhead)
- 8GB runtime maxmemory
- Save every 60s if 1+ changes, every 300s if 5+ changes

---

## Healthcheck Configuration

### graph-visualizer-rust

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
  interval: 15s
  timeout: 10s
  retries: 10
  start_period: 120s
```

**Total time to healthy**: Up to 4.5 minutes (120s + 10 × 15s)

---

## Files to Know

| File | Purpose |
|------|---------|
| `.env` | Environment variables |
| `docker-compose.yml` | Service definitions |
| `server/.env.example` | Example server config |

---

## See Also

- [../how-to/run-docker.md](../how-to/run-docker.md) - Docker operations
- [temporal-config.md](temporal-config.md) - Detailed Temporal config
- [llm-providers.md](llm-providers.md) - LLM provider setup
