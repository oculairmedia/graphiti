# Environment Configuration Guide

This guide explains how to configure Graphiti's environment variables for different deployment scenarios.

## Quick Start

1. **Copy the example file:**
   ```bash
   cp .env.example .env
   ```

2. **Edit the `.env` file** with your specific configuration

3. **Validate your configuration:**
   ```bash
   ./scripts/validate-env-simple.sh
   ```

4. **Start the services:**
   ```bash
   docker-compose up -d
   ```

## Configuration Categories

### 🧠 AI/LLM Configuration

Graphiti supports multiple LLM providers for maximum flexibility:

#### Cerebras (Recommended for Production)
```bash
USE_CEREBRAS=true
CEREBRAS_API_KEY=csk-your-api-key-here
CEREBRAS_MODEL=qwen-3-coder-480b
ENABLE_FALLBACK=true  # Use Ollama as backup
```

#### Ollama (Local/Self-hosted)
```bash
USE_OLLAMA=true
OLLAMA_BASE_URL=http://your-ollama-server:11434/v1
OLLAMA_MODEL=gemma3:12b
USE_OLLAMA_EMBEDDINGS=true
```

#### OpenAI (Alternative)
```bash
OPENAI_API_KEY=sk-your-openai-key
```

### 📊 Database Configuration

#### FalkorDB (Recommended)
```bash
USE_FALKORDB=true
FALKORDB_HOST=falkordb
FALKORDB_PORT=6379
FALKORDB_DATABASE=graphiti_migration
```

#### Neo4j (Alternative)
```bash
USE_FALKORDB=false
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
```

### 🔌 Service Ports

Configure external ports for each service:

```bash
API_PORT=8003          # Main Graph API
FRONTEND_PORT=8084     # React Frontend  
RUST_SERVER_PORT=3000  # Graph Visualizer
QUEUE_PORT=8093        # Message Queue
NGINX_HTTP_PORT=8088   # Nginx Proxy
```

### 🌐 Network Configuration

```bash
HOMEPAGE_HOST=192.168.50.90  # Your Docker host IP
OLLAMA_EXTERNAL_HOST=your-ollama-server-ip
```

### ⚡ Performance Tuning

```bash
# Graph limits (prevent memory issues)
NODE_LIMIT=100000
EDGE_LIMIT=100000

# Processing limits
SEMAPHORE_LIMIT=5
WORKER_COUNT=2
BATCH_SIZE=5

# Memory settings (for FalkorDB)
REDIS_ARGS="--maxmemory 2g --maxmemory-policy allkeys-lru"
```

## Common Scenarios

### Development Setup (Local)
```bash
USE_CEREBRAS=false
USE_OLLAMA=true
OLLAMA_BASE_URL=http://localhost:11434/v1
HOMEPAGE_HOST=localhost
NODE_LIMIT=10000  # Smaller limits for dev
```

### Production Setup (High Performance)
```bash
USE_CEREBRAS=true
CEREBRAS_API_KEY=your-key
ENABLE_FALLBACK=true
USE_OLLAMA=true  # As fallback
NODE_LIMIT=100000
SEMAPHORE_LIMIT=10
WORKER_COUNT=4
```

### Self-hosted Setup (No External APIs)
```bash
USE_CEREBRAS=false
USE_OLLAMA=true
OLLAMA_BASE_URL=http://your-internal-server:11434/v1
USE_OLLAMA_EMBEDDINGS=true
```

## Environment Validation

### Automatic Validation

Run the validation script before starting services:

```bash
./scripts/validate-env-simple.sh
```

This will check:
- ✅ Required API keys are set
- ✅ Service URLs are accessible  
- ✅ Port configurations are valid
- ✅ No conflicting settings

### Manual Validation

You can also manually verify key settings:

```bash
# Check if Ollama is accessible
curl http://your-ollama-server:11434/api/tags

# Check if FalkorDB is running
redis-cli -h your-falkordb-host ping

# Test Cerebras API
curl -H "Authorization: Bearer $CEREBRAS_API_KEY" \
     https://api.cerebras.net/v1/models
```

## Troubleshooting

### Common Issues

#### "No LLM provider enabled"
- Make sure either `USE_CEREBRAS=true` or `USE_OLLAMA=true`
- Verify API keys are set correctly

#### "Connection refused" errors
- Check that service URLs are accessible from Docker containers
- Verify firewall settings and port bindings
- Use `docker-compose logs service-name` to debug

#### "Out of memory" errors
- Reduce `NODE_LIMIT` and `EDGE_LIMIT`
- Increase FalkorDB memory limit in `REDIS_ARGS`
- Consider scaling up your host machine

#### Frontend shows empty graph
- Check that `HOMEPAGE_HOST` matches your actual host IP
- Verify WebSocket connections aren't blocked
- Check browser developer console for errors

### Performance Optimization

#### For Large Datasets
```bash
NODE_LIMIT=50000        # Reduce visualization load
SEMAPHORE_LIMIT=10      # More concurrent operations  
WORKER_COUNT=4          # More worker processes
BATCH_SIZE=10           # Larger batch sizes
```

#### For Low-Memory Systems
```bash
NODE_LIMIT=5000         # Smaller graph limits
REDIS_ARGS="--maxmemory 1g"  # Less memory for database
WORKER_COUNT=1          # Fewer workers
CACHE_ENABLED=false     # Disable caching
```

## Security Considerations

### API Keys
- Keep API keys in `.env` file (never commit to git)
- Use environment-specific keys for dev/staging/prod
- Rotate keys regularly

### Network Security
- Restrict `CORS_ORIGINS` in production
- Use HTTPS in production (`NGINX_HTTPS_PORT`)
- Consider VPN for external Ollama servers

### Data Protection
- Use strong passwords for Neo4j
- Enable Redis AUTH if FalkorDB supports it
- Regular database backups

## Docker Compose Integration

The environment variables integrate with Docker Compose:

```yaml
# Example docker-compose.yml snippet
services:
  graph:
    environment:
      - FALKORDB_HOST=${FALKORDB_HOST:-falkordb}
      - SEMAPHORE_LIMIT=${SEMAPHORE_LIMIT:-5}
    ports:
      - "${API_PORT:-8003}:8000"
```

This allows easy customization without editing compose files.

## Advanced Configuration

### Custom Ollama Models
```bash
OLLAMA_MODEL=your-custom-model:latest
OLLAMA_EMBEDDING_MODEL=your-embedding-model:latest
```

### Multi-GPU Setup
```bash
# For Ollama with multiple GPUs
OLLAMA_NUM_GPU=2
CUDA_VISIBLE_DEVICES=0,1
```

### Load Balancing
```bash
# Multiple Ollama instances
OLLAMA_BASE_URL=http://ollama-1:11434/v1,http://ollama-2:11434/v1
```

## Getting Help

If you encounter issues:

1. Run `./scripts/validate-env-simple.sh` first
2. Check Docker logs: `docker-compose logs service-name`  
3. Verify network connectivity to external services
4. Check the main README.md for additional troubleshooting

For questions about specific variables, see the detailed comments in `.env.example`.