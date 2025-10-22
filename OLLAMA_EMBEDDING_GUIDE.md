# Ollama Embedding Generation Guide

This document explains how Ollama is used for generating embeddings in the Graphiti codebase and provides scripts for regenerating edge embeddings.

## Overview

Graphiti uses embeddings to enable semantic search and similarity matching for both nodes and edges. The system supports multiple embedding providers, with Ollama being a popular choice for local, self-hosted embedding generation.

## Your Current Infrastructure

Your environment is configured with:

- **Dedicated Embedding Server**: `192.168.50.80:11434` - Optimized for embedding generation
- **Main Ollama Server**: `100.81.139.20:11434` - Used for LLM operations
- **FalkorDB**: `falkordb:6379` - Vector database for storing embeddings
- **Embedding Model**: `mxbai-embed-large:latest` - High-quality embedding model
- **Fallback Support**: Automatic fallback from dedicated to main server if needed

## How Ollama Embeddings Work

### Architecture

1. **Ollama Server**: Runs locally or on a remote server, providing an OpenAI-compatible API
2. **Embedding Models**: Various models like `mxbai-embed-large`, `nomic-embed-text`, etc.
3. **AsyncOpenAI Client**: Used to communicate with Ollama's OpenAI-compatible endpoint
4. **Batch Processing**: Supports both single and batch embedding generation

### Key Components

#### OllamaEmbedder Class
```python
class OllamaEmbedder(EmbedderClient):
    def __init__(self, base_url: str, model: str = 'mxbai-embed-large'):
        self.base_url = base_url
        self.model = model
        self.client = AsyncOpenAI(base_url=base_url, api_key='ollama')
    
    async def create(self, input_data: str | list[str]) -> list[float]:
        # Single embedding generation
    
    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        # Batch embedding generation
```

#### Configuration
The system uses environment variables for configuration (already set in your .env):

- `USE_OLLAMA_EMBEDDINGS`: Set to "true" to use Ollama for embeddings
- `USE_DEDICATED_EMBEDDING_ENDPOINT`: Use dedicated embedding server (recommended)
- `OLLAMA_EMBEDDING_BASE_URL`: Dedicated embedding server (`http://192.168.50.80:11434/v1`)
- `OLLAMA_BASE_URL`: Main Ollama server (`http://100.81.139.20:11434/v1`)
- `OLLAMA_EMBEDDING_MODEL`: Model to use (`mxbai-embed-large:latest`)
- `FALKORDB_HOST`: FalkorDB host (`falkordb`)
- `FALKORDB_PORT`: FalkorDB port (`6379`)
- `DEFAULT_DATABASE`: Database name (`falkordb`)

## Node and Edge Embeddings

### Node Embeddings

Node embeddings are vector representations of the `name` field in EntityNode objects. These embeddings enable:

- Semantic search across entities
- Similarity matching between entity names
- Deduplication of similar nodes
- Enhanced entity retrieval capabilities

#### Node Structure
```python
class EntityNode:
    name: str  # The text that gets embedded
    name_embedding: list[float] | None  # The generated embedding vector
    # ... other fields
```

### Edge Embeddings

Edge embeddings are vector representations of the `fact` field in EntityEdge relationships. These embeddings enable:

- Semantic search across relationships
- Similarity matching between facts
- Deduplication of similar edges
- Enhanced retrieval capabilities

#### Edge Structure
```python
class EntityEdge:
    fact: str  # The text that gets embedded
    fact_embedding: list[float] | None  # The generated embedding vector
    # ... other fields
```

### Storage in FalkorDB
Both types of embeddings are stored using FalkorDB's vector type:
```cypher
# Node embeddings
SET n.name_embedding = vecf32($embedding)

# Edge embeddings
SET e.fact_embedding = vecf32($embedding)
```

## Available Scripts

### 1. Generate Missing Edge Embeddings
**File**: `generate_missing_embeddings.py`

Generates embeddings only for edges that don't have them:
```bash
# Dry run to see what would be processed
python generate_missing_embeddings.py --dry-run

# Process missing embeddings
python generate_missing_embeddings.py --batch-size 50

# Process with limit
python generate_missing_embeddings.py --limit 1000
```

### 2. Regenerate All Edge Embeddings
**File**: `regenerate_edge_embeddings_ollama.py`

Regenerates embeddings for all edges (useful when switching models):
```bash
# Dry run
python regenerate_edge_embeddings_ollama.py --dry-run

# Regenerate only missing embeddings
python regenerate_edge_embeddings_ollama.py --batch-size 50

# Force regenerate ALL embeddings
python regenerate_edge_embeddings_ollama.py --force-regenerate --batch-size 50

# Process with limit
python regenerate_edge_embeddings_ollama.py --limit 500 --force-regenerate
```

### 3. Regenerate All Node Embeddings
**File**: `regenerate_node_embeddings_ollama.py`

Regenerates embeddings for all nodes (useful when switching models):
```bash
# Dry run
python regenerate_node_embeddings_ollama.py --dry-run

# Regenerate only missing embeddings
python regenerate_node_embeddings_ollama.py --batch-size 50

# Force regenerate ALL embeddings
python regenerate_node_embeddings_ollama.py --force-regenerate --batch-size 50

# Process with limit
python regenerate_node_embeddings_ollama.py --limit 500 --force-regenerate
```

### 4. Batch Generate Node Embeddings
**File**: `batch_generate_embeddings.py`

Legacy script for generating missing node embeddings:
```bash
python batch_generate_embeddings.py
```

## Environment Setup

### Current Infrastructure

Your environment is already configured with the following Ollama instances:

- **Main Ollama Server**: `http://100.81.139.20:11434/v1` (for LLM operations)
- **Dedicated Embedding Server**: `http://192.168.50.80:11434/v1` (for embeddings)
- **FalkorDB**: `falkordb:6379` (database)

### Environment Variables (Already Configured)

Your `.env` file contains:
```env
# Ollama Embedding Configuration
USE_OLLAMA_EMBEDDINGS=true
OLLAMA_EMBEDDING_BASE_URL=http://192.168.50.80:11434/v1
OLLAMA_EMBEDDING_MODEL=mxbai-embed-large:latest
USE_DEDICATED_EMBEDDING_ENDPOINT=true
EMBEDDING_ENDPOINT_FALLBACK=true

# FalkorDB Configuration
FALKORDB_HOST=falkordb
FALKORDB_PORT=6379
USE_FALKORDB=true
```

### Verification

Test your Ollama embedding server:
```bash
# Check if embedding server is accessible
curl http://192.168.50.80:11434/api/tags

# Test embedding generation
curl -X POST http://192.168.50.80:11434/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"input": "test text", "model": "mxbai-embed-large"}'
```

## Embedding Models

### Popular Ollama Embedding Models

1. **mxbai-embed-large** (Recommended)
   - High quality embeddings
   - Good for general purpose use
   - Dimensions: 1024

2. **nomic-embed-text**
   - Fast and efficient
   - Good for text similarity
   - Dimensions: 768

3. **all-minilm**
   - Lightweight option
   - Faster processing
   - Dimensions: 384

### Switching Models
To switch embedding models:
1. Pull the new model: `ollama pull <model-name>`
2. Update `OLLAMA_EMBEDDING_MODEL` environment variable
3. Run regeneration script with `--force-regenerate`

## Performance Considerations

### Batch Processing
- Default batch size: 50 edges
- Adjust based on your hardware and Ollama server capacity
- Larger batches = faster processing but more memory usage

### Rate Limiting
- Scripts include small delays (0.1s) between batches
- Prevents overwhelming the Ollama server
- Adjust if needed for your setup

### Monitoring
Scripts provide detailed progress information:
- Edges processed per second
- Estimated time to completion
- Success/failure counts
- Memory usage (via logs)

## Troubleshooting

### Common Issues

1. **Connection Refused**
   - Check if dedicated embedding server is running: `curl http://192.168.50.80:11434/api/tags`
   - Check if main Ollama server is running: `curl http://100.81.139.20:11434/api/tags`
   - Verify network connectivity to the servers

2. **Model Not Found**
   - Pull the model: `ollama pull <model-name>`
   - Check available models: `ollama list`

3. **Out of Memory**
   - Reduce batch size
   - Use a smaller embedding model
   - Increase system RAM or swap

4. **Slow Performance**
   - Check Ollama server resources
   - Reduce batch size
   - Use GPU acceleration if available

### Verification Queries

Check embedding status:
```cypher
// Count nodes with embeddings
MATCH (n:Entity)
WHERE n.name_embedding IS NOT NULL
RETURN count(n) as nodes_with_embeddings

// Count nodes without embeddings
MATCH (n:Entity)
WHERE n.name_embedding IS NULL AND n.name IS NOT NULL
RETURN count(n) as nodes_missing_embeddings

// Count edges with embeddings
MATCH ()-[e:RELATES_TO]->()
WHERE e.fact_embedding IS NOT NULL
RETURN count(e) as edges_with_embeddings

// Count edges without embeddings
MATCH ()-[e:RELATES_TO]->()
WHERE e.fact_embedding IS NULL AND e.fact IS NOT NULL
RETURN count(e) as edges_missing_embeddings

// Sample embedded node
MATCH (n:Entity)
WHERE n.name_embedding IS NOT NULL
RETURN n.name, size(n.name_embedding) as embedding_dim
LIMIT 1

// Sample embedded edge
MATCH ()-[e:RELATES_TO]->()
WHERE e.fact_embedding IS NOT NULL
RETURN e.fact, size(e.fact_embedding) as embedding_dim
LIMIT 1

// Overall embedding status
MATCH (n:Entity)
OPTIONAL MATCH ()-[e:RELATES_TO]->()
RETURN
  count(DISTINCT n) as total_nodes,
  count(DISTINCT CASE WHEN n.name_embedding IS NOT NULL THEN n END) as nodes_with_embeddings,
  count(DISTINCT e) as total_edges,
  count(DISTINCT CASE WHEN e.fact_embedding IS NOT NULL THEN e END) as edges_with_embeddings
```

## Integration with Graphiti

### Automatic Embedding Generation
When new edges are created through normal Graphiti operations, embeddings are automatically generated using the configured embedder.

### Search and Retrieval
Embeddings enable semantic search capabilities:
- Finding similar facts
- Deduplication during ingestion
- Enhanced retrieval for queries

### Maintenance
Regular maintenance tasks:
- Monitor for missing embeddings
- Regenerate when switching models
- Verify embedding quality and dimensions

## Best Practices

1. **Model Selection**: Choose based on your use case and hardware
2. **Batch Size**: Start with 50, adjust based on performance
3. **Monitoring**: Regularly check for missing embeddings
4. **Backup**: Backup your database before major regeneration
5. **Testing**: Use dry-run mode to verify operations
6. **Resources**: Ensure adequate RAM and CPU for your chosen model
