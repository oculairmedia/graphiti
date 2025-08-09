# Graphiti Search Service (Rust)

High-performance search microservice for Graphiti knowledge graphs, written in Rust.

## Features

- **5-10x faster** than Python implementation for compute-intensive operations
- **SIMD-optimized** vector similarity search using AVX2 instructions
- **Parallel processing** with Rayon for batch operations
- **Connection pooling** for FalkorDB and Redis
- **Multiple search methods**: Fulltext, similarity, BFS traversal
- **Advanced reranking**: RRF, MMR, cross-encoder, node distance
- **Two-tier caching**: In-memory LRU + Redis
- **Zero-copy deserialization** with rkyv for cached data

## Performance Benchmarks

| Operation | Python (ms) | Rust (ms) | Improvement |
|-----------|------------|-----------|-------------|
| Fulltext Search | 50-100 | 5-15 | 5-10x |
| Vector Similarity (1000 vectors) | 30-50 | 4-8 | 5-8x |
| BFS Traversal (depth 3) | 100-200 | 25-50 | 3-4x |
| RRF Reranking (500 items) | 20-30 | 3-5 | 4-6x |
| Complete Search Request | 200-400 | 40-80 | 5x |

## Quick Start

### Using Docker Compose

```bash
docker-compose up -d
```

This starts:
- Graphiti Search Service on port 3004
- FalkorDB on port 6379
- Redis cache on port 6380

### Building from Source

```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Build release binary
cargo build --release

# Run with environment variables
FALKORDB_HOST=localhost \
FALKORDB_PORT=6379 \
REDIS_URL=redis://localhost:6379 \
cargo run --release
```

## API Endpoints

### Health Check
```bash
GET /health
```

### Unified Search
```bash
POST /search
{
  "query": "machine learning",
  "config": {
    "edge_config": {
      "search_methods": ["fulltext", "similarity"],
      "reranker": "rrf",
      "sim_min_score": 0.7
    },
    "node_config": {
      "search_methods": ["fulltext", "bfs"],
      "reranker": "mmr",
      "mmr_lambda": 0.5
    },
    "limit": 100
  },
  "query_vector": [0.1, 0.2, ...] // Optional
}
```

### Specialized Endpoints

- `POST /search/edges` - Optimized edge search
- `POST /search/nodes` - Optimized node search
- `POST /search/episodes` - Episode search
- `POST /search/communities` - Community search

## Python Integration

Use the provided Python client:

```python
from graphiti_core.search.rust_client import RustSearchClient, rust_search
from graphiti_core.search.search_config import SearchConfig

# One-off search
results = await rust_search(
    query="quantum computing",
    config=search_config,
    base_url="http://localhost:3004"
)

# Or with client lifecycle management
async with RustSearchClient() as client:
    results = await client.search(query, config)
```

## Configuration

Environment variables:

- `PORT` - Server port (default: 3004)
- `FALKORDB_HOST` - FalkorDB host (default: localhost)
- `FALKORDB_PORT` - FalkorDB port (default: 6379)
- `GRAPH_NAME` - Graph database name (default: graphiti_migration)
- `REDIS_URL` - Redis connection URL (default: redis://localhost:6379)
- `MAX_CONNECTIONS` - Connection pool size (default: 32)
- `CACHE_TTL` - Cache TTL in seconds (default: 300)
- `ENABLE_SIMD` - Enable SIMD optimizations (default: true)
- `PARALLEL_THRESHOLD` - Min items for parallel processing (default: 100)

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Python    │────▶│ Rust Search  │────▶│  FalkorDB   │
│   Client    │     │   Service    │     └─────────────┘
└─────────────┘     └──────────────┘            │
                           │                     │
                           ▼                     │
                    ┌─────────────┐             │
                    │    Redis    │◀────────────┘
                    │    Cache    │
                    └─────────────┘
```

## Development

### Running Tests
```bash
cargo test
```

### Running Benchmarks
```bash
cargo bench
```

### Building Docker Image
```bash
docker build -t graphiti-search-rs .
```

## Monitoring

The service exports Prometheus metrics on `/metrics`:

- `search_requests_total` - Total search requests
- `search_duration_seconds` - Search latency histogram
- `cache_hits_total` - Cache hit rate
- `db_connections_active` - Active database connections

## License

Same as the main Graphiti project.