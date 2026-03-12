# Graphiti Documentation Index

> **For AI Coding Agents**: Read this ONE file, then follow links to relevant guides.
> Goal: Reduce orientation from 15-20 tool calls to 1-3.

## Quick Task-to-File Mapping

| I want to... | Read this file |
|-------------|----------------|
| Add data/episodes to the graph | [how-to/add-episode.md](how-to/add-episode.md) |
| Search/query the knowledge graph | [how-to/search-graph.md](how-to/search-graph.md) |
| Start/stop/restart Docker services | [how-to/run-docker.md](how-to/run-docker.md) |
| Query FalkorDB directly | [how-to/query-falkordb.md](how-to/query-falkordb.md) |
| Work with Temporal workflows | [how-to/temporal-workflows.md](how-to/temporal-workflows.md) |
| Write or run tests | [how-to/write-tests.md](how-to/write-tests.md) |
| Add a new REST API endpoint | [how-to/add-api-endpoint.md](how-to/add-api-endpoint.md) |
| Add/modify MCP server tools | [how-to/mcp-tools.md](how-to/mcp-tools.md) |
| Add a new LLM provider | [how-to/add-llm-provider.md](how-to/add-llm-provider.md) |
| Work with embeddings | [how-to/embeddings.md](how-to/embeddings.md) |
| Debug ingestion issues | [how-to/debug-ingestion.md](how-to/debug-ingestion.md) |
| Run graph consolidation | [how-to/consolidation.md](how-to/consolidation.md) |
| Understand the API surface | [reference/api-reference.md](reference/api-reference.md) |
| Check node/edge schemas | [reference/schema-reference.md](reference/schema-reference.md) |
| Configure environment variables | [reference/config-reference.md](reference/config-reference.md) |
| Understand system architecture | [explanation/architecture.md](explanation/architecture.md) |
| Learn about ingestion pipeline | [explanation/ingestion-pipeline.md](explanation/ingestion-pipeline.md) |
| Understand consolidation system | [explanation/consolidation-system.md](explanation/consolidation-system.md) |
| Get started with Graphiti | [tutorials/getting-started.md](tutorials/getting-started.md) |
| Set up local development | [tutorials/local-development.md](tutorials/local-development.md) |

## Critical: Read This First

**[gotchas.md](gotchas.md)** - Top pitfalls that waste hours of debugging

Key gotchas:
- FalkorDB vector type must use `vecf32([...])` syntax
- Docker dependency chains - use `docker restart` not `docker-compose`
- Healthcheck timing - services have start periods
- Temporal rate limits - configure per-activity concurrency

---

## How-to Guides (`how-to/`)

**Step-by-step task guides.** Each file is keyword-rich for fast discovery.

| File | Keywords | Description |
|------|----------|-------------|
| [add-episode.md](how-to/add-episode.md) | `episode`, `ingest`, `entity`, `add`, `data`, `temporal` | Ingest messages into knowledge graph |
| [search-graph.md](how-to/search-graph.md) | `search`, `query`, `hybrid`, `semantic`, `keyword` | Query the knowledge graph |
| [run-docker.md](how-to/run-docker.md) | `docker`, `start`, `stop`, `restart`, `compose`, `deploy` | Docker service management |
| [query-falkordb.md](how-to/query-falkordb.md) | `falkordb`, `query`, `cypher`, `graph`, `redis` | Direct FalkorDB operations |
| [temporal-workflows.md](how-to/temporal-workflows.md) | `temporal`, `workflow`, `ingestion`, `consolidation` | Temporal.io workflows |
| [write-tests.md](how-to/write-tests.md) | `test`, `pytest`, `unit`, `fixture`, `mock` | Writing and running tests |
| [add-api-endpoint.md](how-to/add-api-endpoint.md) | `api`, `rest`, `fastapi`, `endpoint`, `route` | Add REST API endpoints |
| [mcp-tools.md](how-to/mcp-tools.md) | `mcp`, `tool`, `server`, `claude` | MCP server tools |
| [add-llm-provider.md](how-to/add-llm-provider.md) | `llm`, `provider`, `openai`, `anthropic`, `gemini` | Add LLM providers |
| [embeddings.md](how-to/embeddings.md) | `embedding`, `vector`, `vecf32`, `similarity` | Embedding operations |
| [debug-ingestion.md](how-to/debug-ingestion.md) | `debug`, `ingestion`, `error`, `trace`, `logs` | Debug ingestion issues |
| [consolidation.md](how-to/consolidation.md) | `consolidation`, `prune`, `merge`, `cleanup` | Graph consolidation |

---

## Reference Documentation (`reference/`)

**Comprehensive technical documentation.** Full API surfaces, schemas, configurations.

| File | Keywords | Description |
|------|----------|-------------|
| [api-reference.md](reference/api-reference.md) | `api`, `rest`, `fastapi`, `endpoints` | REST API reference |
| [schema-reference.md](reference/schema-reference.md) | `schema`, `node`, `edge`, `falkordb`, `cypher` | Node/edge schemas |
| [config-reference.md](reference/config-reference.md) | `config`, `env`, `environment`, `docker` | Configuration reference |
| [llm-providers.md](reference/llm-providers.md) | `llm`, `openai`, `anthropic`, `gemini`, `ollama` | LLM provider config |
| [embedders.md](reference/embedders.md) | `embedding`, `vector`, `dimensions` | Embedding provider config |
| [temporal-config.md](reference/temporal-config.md) | `temporal`, `workflow`, `activity`, `queue` | Temporal configuration |
| [prompts.md](reference/prompts.md) | `prompt`, `dspy`, `signature`, `optimization` | Prompt/DSL reference |

---

## Explanations (`explanation/`)

**Architecture concepts and design decisions.** Understanding-oriented.

| File | Keywords | Description |
|------|----------|-------------|
| [architecture.md](explanation/architecture.md) | `architecture`, `services`, `data-flow` | System architecture overview |
| [ingestion-pipeline.md](explanation/ingestion-pipeline.md) | `ingestion`, `pipeline`, `extraction`, `resolution` | How data flows through |
| [consolidation-system.md](explanation/consolidation-system.md) | `consolidation`, `prune`, `merge`, `sleep` | Nightly graph cleanup |
| [bi-temporal-model.md](explanation/bi-temporal-model.md) | `temporal`, `t_valid_at`, `t_invalid_at` | Bi-temporal tracking |
| [vector-search.md](explanation/vector-search.md) | `vector`, `hnsw`, `similarity`, `search` | Vector search mechanics |
| [centrality.md](explanation/centrality.md) | `centrality`, `pagerank`, `eigenvector` | Graph centrality algorithms |

---

## Tutorials (`tutorials/`)

**Learning-oriented guides.** Start here if new to the codebase.

| File | Keywords | Description |
|------|----------|-------------|
| [getting-started.md](tutorials/getting-started.md) | `start`, `quick`, `first`, `episode` | Quick start guide |
| [local-development.md](tutorials/local-development.md) | `local`, `dev`, `setup`, `environment` | Local dev setup |

---

## Project Context

**Project**: Graphiti Knowledge Graph Platform (`GRAPH`)
**Path**: `/opt/stacks/graphiti`
**PM Agent**: `agent-80ac3bb8-1087-412d-a19c-7c8c6aeb5916` (GraphitiExplorer)

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `graphiti_core/` | Core library - entities, edges, ingestion, search |
| `server/` | FastAPI REST server |
| `mcp_server/` | MCP server for Claude integration |
| `graph-visualizer-rust/` | Rust visualizer backend |
| `frontend/` | React/TypeScript frontend |
| `worker/` | Temporal workers and scripts |
| `docs/` | Documentation (you are here) |

### Current Graph Stats (Mar 2026)

- **Entities**: ~19,852
- **Episodes**: ~28,094
- **Edges**: ~125,307

---

*This documentation follows the [Diátaxis framework](https://diataxis.fr/) for structured, intent-based organization.*
