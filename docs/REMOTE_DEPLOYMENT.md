# Remote Production Deployment Guide

This guide covers deploying Graphiti to the remote production box at **192.168.50.219** (16GB RAM).

## Architecture

The remote stack is optimized for a 16GB RAM system with the following services:

### Core Services
- **FalkorDB** (6379) - Graph database (8GB memory limit)
- **Graph API** (8003) - FastAPI server for graph operations
- **Search Service** (3004) - Rust-based high-performance search
- **Centrality Service** (3003) - Graph centrality calculations
- **MCP Server** (3010) - Model Context Protocol server

### Visualization Services (NEW)
- **Graph Visualizer** (3000) - Rust-based graph visualization backend
- **Frontend** (8084) - React UI for graph exploration

### Infrastructure
- **Nginx** (8088) - Reverse proxy
- **Temporal Workers** - Background ingestion processing (optional profiles)

## Memory Allocation

Total memory budget: ~14GB (leaving 2GB for system)

| Service | Memory Limit | Notes |
|---------|-------------|-------|
| FalkorDB | 8GB | Includes headroom for BGSAVE fork |
| Visualizer | 2GB | DuckDB cache limited to 1GB |
| Search Service | 1.5GB | |
| Centrality Service | 1GB | |
| Frontend | 256MB | Static nginx serving |
| Graph API | ~1GB | Soft limit via Python |
| Nginx | 128MB | |

## Deployment Steps

### 1. Prerequisites

Ensure you have access to the remote box:
```bash
ssh root@192.168.50.219
```

### 2. Clone/Update Repository

```bash
cd /opt/stacks
git clone https://github.com/oculairmedia/graphiti.git
# OR update existing
cd /opt/stacks/graphiti
git pull origin main
```

### 3. Configure Environment

Create `.env` file:
```bash
cat > .env <<'EOF'
# Core Configuration
FALKORDB_HOST=falkordb
FALKORDB_PORT=6379
FALKORDB_DATABASE=graphiti_migration

# API Keys
CHUTES_API_KEY=your_chutes_key_here
OPENAI_API_KEY=sk-dummy

# LLM Configuration
USE_CHUTES=true
CHUTES_MODEL=zai-org/GLM-4.7-FP8
CHUTES_SMALL_MODEL=glm-4.5-air
CHUTES_BASE_URL=https://api.z.ai/api/coding/paas/v4

# Embedding Configuration
USE_OLLAMA_EMBEDDINGS=true
USE_DEDICATED_EMBEDDING_ENDPOINT=true
OLLAMA_EMBEDDING_BASE_URL=http://192.168.50.247:11450/v1
OLLAMA_EMBEDDING_MODEL=qwen3-embedding
EMBEDDING_DIMENSION=2560

# Reranker
RERANKER_ENABLED=true
RERANKER_URL=http://192.168.50.247:11435

# Rust Services
USE_RUST_SEARCH=true
USE_RUST_CENTRALITY=true
RUST_SEARCH_URL=http://graphiti-search-rs:3004
RUST_CENTRALITY_URL=http://graphiti-centrality-rs:3003

# Ports
API_PORT=8003
RUST_SEARCH_PORT=3004
RUST_CENTRALITY_PORT=3003
RUST_SERVER_PORT=3000
FRONTEND_PORT=8084
NGINX_HTTP_PORT=8088
MCP_SERVER_PORT=3010

# Temporal (optional)
TEMPORAL_VISIBILITY_ADDRESS=192.168.50.90:7233
TEMPORAL_VISIBILITY_NAMESPACE=graphiti
EOF
```

### 4. Deploy Stack

```bash
# Pull latest images
docker compose -f docker-compose.remote.yml pull

# Start core services
docker compose -f docker-compose.remote.yml up -d

# Check status
docker compose -f docker-compose.remote.yml ps
```

### 5. Verify Deployment

```bash
# Check FalkorDB
redis-cli -h localhost -p 6379 PING

# Check API
curl http://localhost:8003/api/graph/ping

# Check Search Service
curl http://localhost:3004/health

# Check Visualizer
curl http://localhost:3000/health

# Check Frontend
curl http://localhost:8084/
```

### 6. Access Services

From your local network:
- **Frontend UI**: http://192.168.50.219:8084
- **API Docs**: http://192.168.50.219:8003/docs
- **Visualizer**: http://192.168.50.219:3000
- **Nginx Proxy**: http://192.168.50.219:8088

## Optional: Temporal Workers

To enable background ingestion processing:

```bash
# Start temporal workers
docker compose -f docker-compose.remote.yml --profile temporal-staged up -d

# Check worker status
docker compose -f docker-compose.remote.yml ps | grep temporal
```

## Monitoring

### Check Logs
```bash
# All services
docker compose -f docker-compose.remote.yml logs -f

# Specific service
docker compose -f docker-compose.remote.yml logs -f frontend
docker compose -f docker-compose.remote.yml logs -f graph-visualizer-rust
```

### Check Resource Usage
```bash
docker stats
```

### Graph Statistics
```bash
redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)"
redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)"
```

## Troubleshooting

### Frontend Not Loading
1. Check visualizer health: `curl http://localhost:3000/health`
2. Check frontend logs: `docker compose -f docker-compose.remote.yml logs frontend`
3. Verify nginx config is mounted correctly

### Visualizer Performance Issues
1. Check DuckDB cache size: `docker exec -it graphiti-graph-visualizer-rust-1 ls -lh /app/data/`
2. Reduce DUCKDB_MEMORY_LIMIT in .env if needed
3. Disable cache: `CACHE_ENABLED=false`

### Out of Memory
1. Check current usage: `docker stats`
2. Reduce FalkorDB maxmemory: Edit REDIS_ARGS in docker-compose.remote.yml
3. Disable temporal workers if not needed
4. Consider reducing NODE_LIMIT and EDGE_LIMIT

## Maintenance

### Update Services
```bash
cd /opt/stacks/graphiti
git pull origin main
docker compose -f docker-compose.remote.yml pull
docker compose -f docker-compose.remote.yml up -d
```

### Backup Graph Data
```bash
# Backup FalkorDB RDB file
docker compose -f docker-compose.remote.yml exec falkordb redis-cli SAVE
docker cp graphiti-falkordb-1:/var/lib/falkordb/data/falkordb.rdb ./backup-$(date +%Y%m%d).rdb
```

### Restore Graph Data
```bash
# Stop services
docker compose -f docker-compose.remote.yml down

# Copy backup to volume
docker run --rm -v graphiti_falkordb_data:/data -v $(pwd):/backup alpine cp /backup/falkordb.rdb /data/

# Start services
docker compose -f docker-compose.remote.yml up -d
```

## Performance Tuning

### For Heavy Read Workloads
- Increase `CACHE_ENABLED=true` and `CACHE_TTL_SECONDS`
- Increase `DUCKDB_MEMORY_LIMIT` if RAM available
- Enable more temporal workers

### For Heavy Write Workloads
- Increase FalkorDB `QUERY_MEM_CAPACITY`
- Reduce `save` frequency in REDIS_ARGS
- Increase temporal worker concurrency

## Support

For issues or questions:
- GitHub Issues: https://github.com/oculairmedia/graphiti/issues
- Documentation: https://github.com/oculairmedia/graphiti/tree/main/docs
