# System Architecture

> **Keywords**: `architecture`, `services`, `data-flow`, `components`, `overview`

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Clients                                   │
│  (Web Browser, Claude Desktop, API Consumers)                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Nginx (8088/8443)                           │
│              Reverse Proxy + SSL Termination                    │
└─────────────────────────────────────────────────────────────────┘
           │                    │                    │
           ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   Frontend      │  │   Graph API     │  │   MCP Server    │
│   (React)       │  │   (FastAPI)     │  │   (Port 8001)   │
│   Port 8085     │  │   Port 8003     │  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
                              │                    │
                              ▼                    │
┌─────────────────────────────────────────────────────────────────┐
│                 Graph Visualizer (Rust)                         │
│                     Port 3000                                   │
│         In-Memory Graph + DuckDB Cache                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FalkorDB                                   │
│                     Port 6379                                   │
│            Primary Data Store (RDB Persistence)                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Temporal.io                                  │
│                   (Optional, Port 7233)                         │
│         Ingestion Workflows + Consolidation                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Services

### FalkorDB (Primary Data Store)

- **Role**: Graph database for storing entities, edges, and episodes
- **Persistence**: RDB snapshots (every 60s if 1+ changes)
- **Memory**: 16GB limit, 8GB runtime
- **Protocol**: Redis-compatible

**Why FalkorDB**:
- Fast in-memory graph operations
- Native vector index (HNSW)
- Redis-compatible API
- RDB persistence for durability

### Graph Visualizer (Rust)

- **Role**: Serves graph data to frontend
- **Implementation**: Rust + Actix
- **Caching**: DuckDB for query results (17GB cache)
- **Batch Size**: 5000 edges per batch

**Data Flow**:
1. Loads all edges from FalkorDB on startup (~2s)
2. Stores in memory for fast queries
3. Caches results in DuckDB

### Graph API (FastAPI)

- **Role**: REST API for graph operations
- **Framework**: FastAPI
- **Endpoints**: Episodes, Search, Nodes, Edges, Centrality

**Key Files**:
- `server/main.py` - Entry point
- `server/routes/` - API handlers

### MCP Server

- **Role**: Model Context Protocol server for Claude integration
- **Port**: 8001
- **Tools**: add_memory, search_memory, get_entity, etc.

**Key Files**:
- `mcp_server/server.py` - Server implementation

### Frontend (React)

- **Role**: Web UI for graph visualization
- **Framework**: React + TypeScript + Vite
- **Dependencies**: Graph Visualizer (Rust)

---

## Optional: Temporal Integration

When `TEMPORAL_INGESTION_ENABLED=true`, ingestion flows through Temporal:

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  API Call   │────▶│   Temporal   │────▶│  FalkorDB   │
│ (add_episode│     │   Workflow   │     │  (Persist)  │
└─────────────┘     └──────────────┘     └─────────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
      ┌─────────┐   ┌─────────┐   ┌─────────┐
      │ Extract │   │ Resolve │   │  Edge   │
      │ Worker  │   │ Worker  │   │ Worker  │
      └─────────┘   └─────────┘   └─────────┘
```

**Benefits**:
- Automatic retries on failures
- Full observability via Temporal UI
- Rate limiting to prevent LLM API throttling
- Parallel processing across workers

---

## Data Flow

### Episode Ingestion

```
Input Text
    │
    ▼
┌─────────────────┐
│  Entity         │  LLM extracts entities
│  Extraction     │  
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  Node           │  Deduplicate by name
│  Resolution     │  
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  Edge           │  LLM extracts relationships
│  Extraction     │  
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  Persistence    │  Write to FalkorDB
│                 │  
└─────────────────┘
```

### Search Query

```
Search Query
    │
    ├──▶ Keyword Search (BM25)
    │
    ├──▶ Semantic Search (HNSW Vector)
    │
    └──▶ Graph Traversal (optional)
           │
           ▼
    Merge Results
           │
           ▼
    Rerank by Graph Distance (optional)
           │
           ▼
    Return Top N
```

---

## Deployment Architecture

### Docker Compose Profiles

```bash
# Core services (always)
docker-compose up -d

# With Temporal ingestion
docker-compose --profile temporal-staged up -d

# With consolidation
docker-compose --profile temporal-consolidation up -d

# All together
docker-compose --profile temporal-staged --profile temporal-consolidation up -d
```

### Volume Persistence

| Volume | Purpose | Backup |
|--------|---------|--------|
| `graphiti_falkordb_data` | Primary data | RDB snapshots |
| `graphiti_visualizer_duckdb` | Query cache | Rebuildable |

---

## Scalability Considerations

### Current Limits

- **Graph Size**: ~125K edges, ~20K entities (Mar 2026)
- **Visualizer Memory**: Loads all edges (~2s)
- **FalkorDB Memory**: 16GB container limit

### Scaling Strategies

1. **Horizontal**: Add more Temporal workers
2. **Vertical**: Increase FalkorDB memory
3. **Partitioning**: Use group_id for data isolation

---

## Files to Know

| Directory | Purpose |
|-----------|---------|
| `graphiti_core/` | Core library |
| `server/` | REST API |
| `mcp_server/` | MCP integration |
| `graph-visualizer-rust/` | Visualization |
| `frontend/` | Web UI |
| `worker/` | Temporal workers |

---

## See Also

- [ingestion-pipeline.md](ingestion-pipeline.md) - Data flow details
- [consolidation-system.md](consolidation-system.md) - Graph cleanup
- [../how-to/run-docker.md](../how-to/run-docker.md) - Service management
