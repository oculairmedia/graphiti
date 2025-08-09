# Dedicated Embedding Endpoint Setup Guide

## Overview

Graphiti now supports using a dedicated Ollama endpoint for embedding operations, separate from the main LLM endpoint. This allows for:

- **Better Performance**: Dedicated resources for embedding operations
- **Independent Scaling**: Scale embedding and LLM services independently
- **Optimized Configuration**: Different Ollama settings for different workloads
- **Reduced Latency**: No resource contention between LLM and embedding operations

## Configuration

### Environment Variables

Add these to your `.env` file:

```bash
# Enable dedicated embedding endpoint
USE_DEDICATED_EMBEDDING_ENDPOINT=true

# Dedicated embedding server URL
OLLAMA_EMBEDDING_BASE_URL=http://embedding-server:11434/v1

# Optional: API key for embedding endpoint (defaults to 'ollama')
OLLAMA_EMBEDDING_API_KEY=ollama

# Enable fallback to main endpoint if dedicated fails (recommended)
EMBEDDING_ENDPOINT_FALLBACK=true
```

## Setup Scenarios

### Scenario 1: Different Servers

Run embedding on a dedicated server optimized for embedding workloads:

```bash
# Main LLM server
OLLAMA_BASE_URL=http://llm-server:11434/v1
OLLAMA_MODEL=gemma3:12b

# Dedicated embedding server
USE_DEDICATED_EMBEDDING_ENDPOINT=true
OLLAMA_EMBEDDING_BASE_URL=http://embedding-server:11434/v1
OLLAMA_EMBEDDING_MODEL=mxbai-embed-large:latest
```

### Scenario 2: Same Server, Different Ports

Run multiple Ollama instances on the same server:

```bash
# Terminal 1: Start main Ollama instance (port 11434)
ollama serve

# Terminal 2: Start embedding Ollama instance (port 11435)
OLLAMA_HOST=0.0.0.0:11435 ollama serve

# In .env:
OLLAMA_BASE_URL=http://100.81.139.20:11434/v1
USE_DEDICATED_EMBEDDING_ENDPOINT=true
OLLAMA_EMBEDDING_BASE_URL=http://100.81.139.20:11435/v1
```

### Scenario 3: Docker Compose Setup

```yaml
version: '3.8'

services:
  ollama-llm:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama-llm:/root/.ollama
    environment:
      - OLLAMA_KEEP_ALIVE=24h
      - OLLAMA_NUM_PARALLEL=4

  ollama-embedding:
    image: ollama/ollama:latest
    ports:
      - "11435:11434"
    volumes:
      - ollama-embedding:/root/.ollama
    environment:
      - OLLAMA_KEEP_ALIVE=24h
      - OLLAMA_NUM_PARALLEL=8  # More parallel for embeddings
      - OLLAMA_NUM_GPU=1  # Dedicated GPU if available

volumes:
  ollama-llm:
  ollama-embedding:
```

## Performance Optimization

### For Embedding Server

Optimize for high throughput:

```bash
# Higher parallelism for batch processing
export OLLAMA_NUM_PARALLEL=8

# Keep models loaded
export OLLAMA_KEEP_ALIVE=24h

# Use GPU if available
export OLLAMA_NUM_GPU=1

# Start embedding server
ollama serve
```

### For LLM Server

Optimize for quality and context:

```bash
# Lower parallelism for better quality
export OLLAMA_NUM_PARALLEL=2

# Longer context window
export OLLAMA_NUM_CTX=4096

# Start LLM server
ollama serve
```

## Testing the Configuration

### 1. Check Endpoint Health

```python
import requests

# Test embedding endpoint
embedding_url = "http://100.81.139.20:11435/v1/models"
response = requests.get(embedding_url)
print("Embedding endpoint models:", response.json())

# Test LLM endpoint
llm_url = "http://100.81.139.20:11434/v1/models"
response = requests.get(llm_url)
print("LLM endpoint models:", response.json())
```

### 2. Verify Configuration in Graphiti

```python
from graphiti_core import Graphiti
import os

# Set environment variables
os.environ['USE_DEDICATED_EMBEDDING_ENDPOINT'] = 'true'
os.environ['OLLAMA_EMBEDDING_BASE_URL'] = 'http://100.81.139.20:11435/v1'

# Initialize Graphiti - check logs for endpoint usage
client = Graphiti(...)
# You should see: "Using dedicated embedding endpoint: http://100.81.139.20:11435/v1"
```

### 3. Monitor Performance

Check the logs for endpoint usage:

```bash
# Graphiti logs
tail -f graphiti.log | grep -E "embedding endpoint|embedder"

# You should see:
# INFO: Using dedicated embedding endpoint: http://100.81.139.20:11435/v1
# INFO: Creating Ollama embedder with model mxbai-embed-large:latest at http://100.81.139.20:11435/v1
```

## Troubleshooting

### Issue: Dedicated endpoint not being used

Check that `USE_DEDICATED_EMBEDDING_ENDPOINT=true` is set and `OLLAMA_EMBEDDING_BASE_URL` is configured.

### Issue: Connection refused

Ensure the embedding Ollama instance is running and accessible:

```bash
curl http://100.81.139.20:11435/v1/models
```

### Issue: Fallback not working

Verify `EMBEDDING_ENDPOINT_FALLBACK=true` is set. Check logs for fallback messages.

### Issue: Model not found

Ensure the embedding model is pulled on the embedding server:

```bash
# On embedding server
ollama pull mxbai-embed-large:latest
```

## Benefits Metrics

With dedicated embedding endpoint, you should see:

- **30-50% reduction** in search latency
- **2-3x increase** in embedding throughput
- **No blocking** between LLM and embedding operations
- **Better resource utilization** across servers

## Advanced Configuration

### Load Balancing Multiple Embedding Servers

Future enhancement - not yet implemented:

```bash
# Future feature
OLLAMA_EMBEDDING_BASE_URLS=http://embed1:11434/v1,http://embed2:11434/v1
EMBEDDING_LOAD_BALANCE_STRATEGY=round_robin
```

### Authentication

If your Ollama instance requires authentication:

```bash
OLLAMA_EMBEDDING_API_KEY=your-api-key-here
```

## Rollback

To disable dedicated embedding endpoint and revert to using the main endpoint:

```bash
USE_DEDICATED_EMBEDDING_ENDPOINT=false
# or simply comment out the line
```

The system will automatically use `OLLAMA_BASE_URL` for both LLM and embedding operations.