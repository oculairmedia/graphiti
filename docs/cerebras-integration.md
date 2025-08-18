# Cerebras Integration with Graphiti

This document describes the Cerebras LLM integration for Graphiti, enabling the use of Qwen Coder models for entity extraction and graph processing.

## Overview

Graphiti now supports Cerebras's high-performance Qwen Coder models as an alternative to OpenAI or Ollama for LLM operations. This integration provides:

- **Qwen-3-coder-480b**: Large 480B parameter model for complex extraction tasks
- **Qwen-3-32b**: Smaller 32B parameter model for simpler operations
- **Fast inference**: Cerebras's optimized hardware acceleration
- **Structured output**: Full support for JSON schema-based extraction

## Components Updated

### 1. Core Library (`graphiti_core`)
- **New File**: `graphiti_core/llm_client/cerebras_client.py` - CerebrasClient implementation
- **Modified**: `graphiti_core/client_factory.py` - Added Cerebras support to factory
- **Modified**: `graphiti_core/llm_client/__init__.py` - Exported CerebrasClient

### 2. Server Component (`server/graph_service`)
- **Modified**: `server/graph_service/factories.py` - Delegates to GraphitiClientFactory for Cerebras

### 3. Worker Component (`worker`)
- **Modified**: `worker/worker_service.py` - Uses GraphitiClientFactory for all LLM clients

## Configuration

### Environment Variables

```bash
# Enable Cerebras (required)
export USE_CEREBRAS=true

# API Key (required)
export CEREBRAS_API_KEY="your-api-key-here"

# Model selection (optional, these are defaults)
export CEREBRAS_MODEL="qwen-3-coder-480b"      # Large model
export CEREBRAS_SMALL_MODEL="qwen-3-32b"       # Small model

# Note: When USE_CEREBRAS=true, Ollama embeddings are still used by default
# To use a dedicated embedding endpoint:
export USE_DEDICATED_EMBEDDING_ENDPOINT=true
export OLLAMA_EMBEDDING_BASE_URL="http://your-embedding-server:11434/v1"
```

### Docker Compose Example

```yaml
services:
  graphiti-server:
    image: graphiti-server
    environment:
      - USE_CEREBRAS=true
      - CEREBRAS_API_KEY=${CEREBRAS_API_KEY}
      - CEREBRAS_MODEL=qwen-3-coder-480b
      - CEREBRAS_SMALL_MODEL=qwen-3-32b
      # Embeddings still use Ollama
      - USE_DEDICATED_EMBEDDING_ENDPOINT=true
      - OLLAMA_EMBEDDING_BASE_URL=http://ollama:11434/v1

  graphiti-worker:
    image: graphiti-worker
    environment:
      - USE_CEREBRAS=true
      - CEREBRAS_API_KEY=${CEREBRAS_API_KEY}
      - CEREBRAS_MODEL=qwen-3-coder-480b
      # Worker will use same configuration
```

## Usage Examples

### Python Script
```python
import os
from graphiti_core import Graphiti

# Set environment for Cerebras
os.environ['USE_CEREBRAS'] = 'true'
os.environ['CEREBRAS_API_KEY'] = 'your-api-key'

# Initialize Graphiti - will automatically use Cerebras
graphiti = Graphiti(uri="bolt://localhost:7687", user="neo4j", password="password")

# Use normally - all LLM operations will use Cerebras
await graphiti.add_episode(
    name="Test Event",
    episode_body="Alice collaborated with Bob on the project.",
    source_description="Test",
    reference_time=datetime.now()
)
```

### API Server
```bash
# Start server with Cerebras
USE_CEREBRAS=true \
CEREBRAS_API_KEY=your-api-key \
uvicorn graph_service.main:app --reload
```

### Worker Service
```bash
# Start worker with Cerebras
USE_CEREBRAS=true \
CEREBRAS_API_KEY=your-api-key \
python worker/main.py
```

## Technical Details

### JSON Schema Handling

Cerebras has strict requirements for JSON schemas:
1. All object types must have `additionalProperties: false`
2. All properties must be listed in the `required` array
3. Nested objects must also follow these rules

The CerebrasClient automatically handles these requirements by transforming Pydantic schemas.

### Rate Limiting

Cerebras enforces rate limits. The client includes:
- Automatic retry logic for rate limit errors
- Exponential backoff
- Proper error handling and logging

### Embedding Strategy

When using Cerebras for LLM operations, embeddings still default to:
- OpenAI embeddings (if no special config)
- Ollama embeddings (if `USE_DEDICATED_EMBEDDING_ENDPOINT=true`)

This hybrid approach leverages Cerebras for extraction while using proven embedding models.

## Limitations

1. **Synchronous SDK**: Cerebras SDK is synchronous, so async calls use `run_in_executor`
2. **No streaming**: Streaming responses not yet implemented
3. **Fixed models**: Only Qwen models currently supported
4. **Rate limits**: Subject to Cerebras API rate limiting

## Testing

Run integration tests:
```bash
# Test basic Cerebras client
python test_cerebras_qwen.py

# Test Graphiti integration
python test_cerebras_integration.py

# Test all components
python test_cerebras_all_components.py
```

## Troubleshooting

### "additionalProperties" error
- **Cause**: Cerebras requires strict JSON schemas
- **Solution**: Already handled by CerebrasClient

### Rate limit errors
- **Cause**: Too many requests per second
- **Solution**: Reduce batch size or add delays between requests

### Connection refused
- **Cause**: Invalid API key or network issues
- **Solution**: Verify CEREBRAS_API_KEY and network connectivity

## Future Enhancements

1. Add streaming support when Cerebras SDK supports it
2. Implement native async client when available
3. Add support for other Cerebras models
4. Optimize batch processing for rate limits
5. Add Cerebras-specific embeddings when available