# Graphiti Container Deployment Process - COMPLETE GUIDE

## ⚠️ CRITICAL WARNINGS - READ FIRST

### DO NOT MAKE THESE MISTAKES AGAIN:
1. **NEVER** test destructive endpoints like `/clear` on live data
2. **NEVER** guess at configuration - use the documented working values
3. **NEVER** assume wheel builds work - they cause import issues
4. **ALWAYS** verify Ollama configuration before starting
5. **ALWAYS** check available models before deployment

---

## Prerequisites Checklist

### 1. Verify Ollama Setup
```bash
# Check Ollama is running
curl -s http://100.81.139.20:11434/api/tags | jq '.models[].name'

# Expected models:
# - "qwen3:32b" (LLM)  
# - "mxbai-embed-large:latest" (embeddings)
```

### 2. Verify Neo4j Setup
```bash
# Check Neo4j is accessible
curl -s http://192.168.50.90:7474 | jq .

# Credentials: neo4j / demodemo
```

---

## Build Process

### 1. Fix the Dockerfile (Development Mode)
The original Dockerfile uses wheel builds which cause import failures. Use this fixed version:

```dockerfile
# Simple single-stage build using development mode
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin:$PATH"

# Configure uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Copy entire project source
COPY ./pyproject.toml ./README.md ./
COPY ./graphiti_core ./graphiti_core
COPY ./server ./server

# Install graphiti-core in development mode (uses source directly)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -e .

# Install server dependencies and ensure it uses our development graphiti-core
WORKDIR /app/server
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev
# Install our development graphiti-core into server venv to override PyPI version
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python .venv/bin/python -e /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:/app/server/.venv/bin:$PATH"

# Set port
ENV PORT=8000
EXPOSE $PORT

# Use server venv python with proper path setup
CMD ["/app/server/.venv/bin/python", "-c", "import sys; sys.path.insert(0, '/app'); import uvicorn; uvicorn.run('graph_service.main:app', host='0.0.0.0', port=8000)"]
```

### 2. Build the Container
```bash
DOCKER_BUILDKIT=1 docker build -t graphiti-server-final . --progress=plain
```

---

## Deployment Process

### 1. Start Container with Correct Configuration
```bash
docker run -d -p 8005:8000 \
-e OPENAI_API_KEY=sk-dummy \
-e USE_OLLAMA=true \
-e OLLAMA_BASE_URL=http://100.81.139.20:11434/v1 \
-e OLLAMA_MODEL=qwen3:32b \
-e OLLAMA_EMBEDDING_MODEL=mxbai-embed-large:latest \
-e USE_OLLAMA_EMBEDDINGS=true \
-e NEO4J_URI=bolt://192.168.50.90:7687 \
-e NEO4J_USER=neo4j \
-e NEO4J_PASSWORD=demodemo \
--name graphiti-production \
graphiti-server-final
```

### 2. Verify Container Startup
```bash
# Check container is running
docker ps | grep graphiti-production

# Check logs for successful startup
docker logs graphiti-production | grep "Application startup complete"
```

### 3. Test Basic Functionality
```bash
# Health check
curl -s http://localhost:8005/healthcheck

# Expected: {"status":"healthy"}
```

---

## Testing Data Ingestion

### 1. Test Message Ingestion
```bash
curl -X POST http://localhost:8005/messages \
-H "Content-Type: application/json" \
-d '{
  "user_id": "test-user",
  "group_id": "test-group", 
  "messages": [
    {
      "content": "Alice works at Acme Corporation as a senior software engineer. She leads the backend development team and reports to the CTO Bob Chen.",
      "role": "user",
      "role_type": "user",
      "timestamp": "2024-01-01T10:00:00Z"
    }
  ]
}'
```

### 2. Verify Processing
```bash
# Check container logs for successful processing
docker logs --tail 10 graphiti-production

# Look for: "Got a job: (size of remaining queue: 0)"
# This indicates successful processing completion
```

### 3. Verify Data in Neo4j
- Open Neo4j browser: http://192.168.50.90:7474
- Run: `MATCH (n) RETURN count(n)`
- Should show nodes > 0

---

## Testing Centrality Endpoints

### 1. PageRank Centrality
```bash
curl -X POST http://localhost:8005/centrality/pagerank \
-H "Content-Type: application/json" \
-d '{"group_id": "test-group", "store_results": false}' | jq .
```

### 2. Degree Centrality
```bash
curl -X POST http://localhost:8005/centrality/degree \
-H "Content-Type: application/json" \
-d '{"group_id": "test-group", "store_results": false}' | jq .
```

### 3. Betweenness Centrality
```bash
curl -X POST http://localhost:8005/centrality/betweenness \
-H "Content-Type: application/json" \
-d '{"group_id": "test-group", "store_results": false}' | jq .
```

### 4. All Centralities
```bash
curl -X POST http://localhost:8005/centrality/all \
-H "Content-Type: application/json" \
-d '{"group_id": "test-group", "store_results": false}' | jq .
```

---

## Troubleshooting Guide

### Problem: Import Errors for Centrality Functions
**Cause**: Using wheel builds instead of development mode  
**Solution**: Use the fixed Dockerfile above with development mode installation

### Problem: Data Ingestion Fails with OpenAI Errors
**Cause**: Missing or incorrect Ollama configuration  
**Solution**: Ensure all Ollama environment variables are set correctly

### Problem: Embedding Failures
**Cause**: Not configured to use Ollama embeddings  
**Solution**: Add `USE_OLLAMA_EMBEDDINGS=true` and `OLLAMA_EMBEDDING_MODEL=mxbai-embed-large:latest`

### Problem: Container Won't Start
**Cause**: Usually missing required environment variables  
**Solution**: Check container logs and ensure all env vars are set

### Problem: Centrality Endpoints Timeout
**Cause**: No data in graph or incorrect group_id  
**Solution**: Verify data ingestion worked and use correct group_id

---

## Critical Configuration Values

### Working Ollama Configuration
```bash
OLLAMA_BASE_URL=http://100.81.139.20:11434/v1
OLLAMA_MODEL=qwen3:32b
OLLAMA_EMBEDDING_MODEL=mxbai-embed-large:latest
USE_OLLAMA=true
USE_OLLAMA_EMBEDDINGS=true
```

### Working Neo4j Configuration
```bash
NEO4J_URI=bolt://192.168.50.90:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=demodemo
```

---

## Maintenance __init__.py Fix

If centrality imports fail, ensure `/opt/stacks/graphiti/graphiti_core/utils/maintenance/__init__.py` contains:

```python
from .edge_operations import build_episodic_edges, extract_edges
from .graph_data_operations import clear_data, retrieve_episodes
from .node_operations import extract_nodes
from .centrality_operations import (
    calculate_all_centralities,
    calculate_betweenness_centrality,
    calculate_degree_centrality,
    calculate_pagerank,
    store_centrality_scores,
)

__all__ = [
    'extract_edges',
    'build_episodic_edges',
    'extract_nodes',
    'clear_data',
    'retrieve_episodes',
    'calculate_all_centralities',
    'calculate_betweenness_centrality',
    'calculate_degree_centrality',
    'calculate_pagerank',
    'store_centrality_scores',
]
```

---

## Success Criteria

✅ Container starts without errors  
✅ Health endpoint returns {"status":"healthy"}  
✅ Message ingestion accepts data  
✅ Data appears in Neo4j  
✅ All 4 centrality endpoints return results  
✅ No import errors in logs  

**If all criteria pass, deployment is successful.**