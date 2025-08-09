# Rust Search Service Integration Guide

## Overview

The Rust search service provides a **43x performance improvement** over the Python implementation, achieving:
- **7.52ms median latency** (vs 323.53ms Python)
- **132.9 req/s throughput** (vs 3.1 req/s Python)

## Quick Start

### 1. Start the Service

```bash
# Start all services including Rust search
docker-compose up -d

# Or start just the Rust search service
docker-compose up -d graphiti-search-rs
```

### 2. Verify Health

```bash
# Check service health
curl http://localhost:3004/health

# Response:
# {"status":"healthy","database":"graphiti_migration"}
```

### 3. Test Search Endpoints

```bash
# Direct access to Rust service
curl -X POST http://localhost:3004/search/edges \
  -H "Content-Type: application/json" \
  -d '{
    "query": "test",
    "config": {
      "search_methods": ["fulltext"],
      "reranker": "rrf",
      "bfs_max_depth": 2,
      "sim_min_score": 0.5,
      "mmr_lambda": 0.5
    },
    "filters": {}
  }'

# Access through Nginx proxy
curl -X POST http://localhost:8088/search-rs/search/edges \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "config": {...}}'
```

## Architecture

### Service Ports
- **3004**: Rust search service (direct access)
- **8088**: Nginx proxy (unified access point)
- **8003**: Python graph service
- **6389**: FalkorDB

### Request Flow
```
Client Request
    ↓
Nginx (8088)
    ├─→ /search-rs/* → Rust Service (3004)  [43x faster]
    └─→ /graphiti/* → Python Service (8003)  [Legacy]
```

## Gradual Migration Strategy

### Phase 1: Testing (Current)
- Rust service available at `/search-rs/` endpoint
- Python service remains at `/graphiti/`
- A/B testing with feature flags

### Phase 2: Partial Migration
```bash
# Enable Rust search for 10% of traffic
export RUST_SEARCH_ENABLED=true
export RUST_SEARCH_PERCENTAGE=10
docker-compose up -d
```

### Phase 3: Full Migration
```bash
# Route all search traffic to Rust
export RUST_SEARCH_ENABLED=true
export RUST_SEARCH_PERCENTAGE=100
docker-compose up -d
```

## API Endpoints

### Rust Search Service

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/search` | POST | Combined search across all entities |
| `/search/edges` | POST | Search edges/relationships |
| `/search/nodes` | POST | Search nodes/entities |
| `/search/episodes` | POST | Search episodes |
| `/search/communities` | POST | Search communities |

### Request Format

```json
{
  "query": "search term",
  "config": {
    "search_methods": ["fulltext", "similarity", "bfs"],
    "reranker": "rrf" | "mmr" | "node_distance",
    "bfs_max_depth": 3,
    "sim_min_score": 0.5,
    "mmr_lambda": 0.5
  },
  "filters": {
    // Optional filters
  },
  "query_vector": [/* Optional embedding vector */]
}
```

### Response Format

```json
{
  "edges": [...],
  "nodes": [...],
  "episodes": [...],
  "communities": [...],
  "total": 100,
  "latency_ms": 7.52
}
```

## Configuration

### Environment Variables

```bash
# docker-compose.yml
environment:
  - FALKORDB_HOST=falkordb
  - FALKORDB_PORT=6379
  - GRAPH_NAME=graphiti_migration
  - REDIS_URL=redis://falkordb:6379/1
  - PORT=3004
  - RUST_LOG=graphiti_search=info
  - RUST_SEARCH_ENABLED=false      # Feature flag
  - RUST_SEARCH_PERCENTAGE=0       # A/B testing percentage
```

### Performance Tuning

```bash
# Increase connection pool size
- MAX_CONNECTIONS=64

# Enable SIMD optimizations
- ENABLE_SIMD=true

# Adjust cache TTL
- CACHE_TTL=600

# Set parallel processing threshold
- PARALLEL_THRESHOLD=100
```

## Monitoring

### Metrics Endpoints

```bash
# Service metrics
curl http://localhost:3004/metrics

# Request latency histogram
curl http://localhost:3004/metrics/latency

# Throughput metrics
curl http://localhost:3004/metrics/throughput
```

### Log Levels

```bash
# Set log level
export RUST_LOG=graphiti_search=debug,tower_http=info

# View logs
docker-compose logs -f graphiti-search-rs
```

## Development

### Local Development

```bash
# Build and run locally
cd graphiti-search-rs
cargo build --release
FALKORDB_HOST=localhost \
  FALKORDB_PORT=6389 \
  GRAPH_NAME=graphiti_migration \
  REDIS_URL=redis://localhost:6380 \
  ./target/release/graphiti-search-rs
```

### Running Tests

```bash
# Run unit tests
cargo test

# Run integration tests
cargo test --features integration

# Run performance benchmarks
cargo bench
```

### Building Docker Image

```bash
# Build locally
docker-compose build graphiti-search-rs

# Or use pre-built image (after GitHub Actions)
docker pull ghcr.io/oculairmedia/graphiti-search-rs:latest
```

## Performance Comparison

| Metric | Python | Rust | Improvement |
|--------|--------|------|-------------|
| Median Latency | 323.53ms | 7.52ms | **43x faster** |
| Throughput | 3.1 req/s | 132.9 req/s | **42x higher** |
| P95 Latency | 500ms+ | 11.4ms | **44x faster** |
| P99 Latency | 600ms+ | 11.9ms | **50x faster** |
| Memory Usage | 500MB | 50MB | **10x lower** |
| CPU Usage | 80% | 15% | **5x lower** |

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker-compose logs graphiti-search-rs

# Verify FalkorDB is running
docker-compose ps falkordb

# Test FalkorDB connection
redis-cli -h localhost -p 6389 ping
```

### High Latency

1. Check connection pool saturation
2. Verify Redis cache is working
3. Monitor FalkorDB query performance
4. Check for network issues

### Build Failures

```bash
# Update Rust version
docker pull rust:latest

# Clear Docker cache
docker system prune -a

# Rebuild from scratch
docker-compose build --no-cache graphiti-search-rs
```

## Migration Checklist

- [ ] Deploy Rust service alongside Python
- [ ] Test all search endpoints
- [ ] Monitor performance metrics
- [ ] Enable for 10% of traffic
- [ ] Monitor error rates
- [ ] Increase to 50% of traffic
- [ ] Full production rollout
- [ ] Deprecate Python search endpoints

## Support

For issues or questions:
- GitHub Issues: https://github.com/oculairmedia/graphiti/issues
- Documentation: https://docs.graphiti.dev
- Performance Dashboard: http://localhost:3004/metrics