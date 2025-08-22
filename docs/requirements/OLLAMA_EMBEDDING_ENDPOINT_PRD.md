# PRD: Separate Ollama Endpoint for Embedding Operations

## Executive Summary

This PRD outlines the implementation of dedicated environment variables to configure a separate Ollama endpoint exclusively for embedding operations, allowing for independent scaling and optimization of LLM and embedding workloads.

## Problem Statement

Currently, Graphiti uses a single `OLLAMA_BASE_URL` for both LLM operations and embedding generation. This creates several limitations:

1. **Resource Contention**: LLM and embedding operations compete for the same Ollama instance resources
2. **Scaling Constraints**: Cannot independently scale embedding vs LLM workloads
3. **Performance Optimization**: Cannot optimize different Ollama instances for different workload types
4. **Deployment Flexibility**: Limited ability to deploy embedding services on different hardware/locations

## Current State Analysis

### Existing Environment Variables
```bash
# Current Ollama Configuration
USE_OLLAMA=true
OLLAMA_BASE_URL=http://100.81.139.20:11434/v1
OLLAMA_MODEL=gemma3:12b
OLLAMA_SMALL_MODEL=gemma3:12b
OLLAMA_EMBEDDING_MODEL=mxbai-embed-large:latest
USE_OLLAMA_EMBEDDINGS=true
```

### Current Implementation
- `GraphitiClientFactory.create_embedder()` uses `OLLAMA_BASE_URL` for embedding operations
- `GraphitiClientFactory.create_llm_client()` uses `OLLAMA_BASE_URL` for LLM operations
- Both share the same Ollama instance endpoint

## Proposed Solution

### New Environment Variables

Add the following environment variables to support dedicated embedding endpoints:

```bash
# Dedicated Embedding Endpoint Configuration
OLLAMA_EMBEDDING_BASE_URL=http://embedding-server:11434/v1
OLLAMA_EMBEDDING_API_KEY=ollama  # Optional, for future auth support
USE_DEDICATED_EMBEDDING_ENDPOINT=true  # Feature flag

# Fallback behavior configuration
EMBEDDING_ENDPOINT_FALLBACK=true  # Fall back to main OLLAMA_BASE_URL if dedicated fails
```

### Implementation Requirements

#### 1. Environment Variable Priority
```
Priority Order for Embedding Endpoint:
1. OLLAMA_EMBEDDING_BASE_URL (if USE_DEDICATED_EMBEDDING_ENDPOINT=true)
2. OLLAMA_BASE_URL (fallback or when dedicated endpoint disabled)
```

#### 2. Modified GraphitiClientFactory

Update `graphiti_core/client_factory.py`:

```python
@staticmethod
def create_embedder() -> Optional[EmbedderClient]:
    """Create embedder client with dedicated endpoint support."""
    if os.getenv('USE_OLLAMA', '').lower() == 'true':
        # Determine embedding endpoint
        embedding_base_url = GraphitiClientFactory._get_embedding_endpoint()
        ollama_embed_model = os.getenv('OLLAMA_EMBEDDING_MODEL', 'mxbai-embed-large:latest')
        
        # Create embedder with dedicated endpoint
        # ... implementation details
        
@staticmethod
def _get_embedding_endpoint() -> str:
    """Determine the appropriate embedding endpoint."""
    use_dedicated = os.getenv('USE_DEDICATED_EMBEDDING_ENDPOINT', 'false').lower() == 'true'
    
    if use_dedicated:
        dedicated_url = os.getenv('OLLAMA_EMBEDDING_BASE_URL')
        if dedicated_url:
            return dedicated_url
        elif os.getenv('EMBEDDING_ENDPOINT_FALLBACK', 'true').lower() == 'true':
            logger.warning("Dedicated embedding endpoint not configured, falling back to main Ollama URL")
            return os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1')
        else:
            raise ValueError("Dedicated embedding endpoint required but not configured")
    
    return os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1')
```

#### 3. Configuration Validation

Add validation logic to ensure:
- Embedding endpoint is reachable when configured
- Fallback behavior works correctly
- Clear error messages for misconfigurations

#### 4. Logging and Monitoring

Enhanced logging to track:
- Which endpoint is being used for embeddings
- Fallback events
- Endpoint health status
- Performance metrics per endpoint

### Configuration Examples

#### Example 1: Dedicated Embedding Server
```bash
# Main Ollama for LLM operations
USE_OLLAMA=true
OLLAMA_BASE_URL=http://llm-server:11434/v1
OLLAMA_MODEL=gemma3:12b

# Dedicated embedding server
USE_DEDICATED_EMBEDDING_ENDPOINT=true
OLLAMA_EMBEDDING_BASE_URL=http://embedding-server:11434/v1
OLLAMA_EMBEDDING_MODEL=mxbai-embed-large:latest
USE_OLLAMA_EMBEDDINGS=true
```

#### Example 2: Same Server, Different Ports
```bash
# Main Ollama instance
USE_OLLAMA=true
OLLAMA_BASE_URL=http://100.81.139.20:11434/v1
OLLAMA_MODEL=gemma3:12b

# Dedicated embedding instance on same server
USE_DEDICATED_EMBEDDING_ENDPOINT=true
OLLAMA_EMBEDDING_BASE_URL=http://100.81.139.20:11435/v1
OLLAMA_EMBEDDING_MODEL=mxbai-embed-large:latest
```

#### Example 3: Fallback Configuration
```bash
# Enable fallback to main endpoint if dedicated fails
USE_DEDICATED_EMBEDDING_ENDPOINT=true
OLLAMA_EMBEDDING_BASE_URL=http://embedding-server:11434/v1
EMBEDDING_ENDPOINT_FALLBACK=true
```

## Implementation Plan

### Phase 1: Core Implementation
1. Add new environment variables to configuration
2. Update `GraphitiClientFactory.create_embedder()` method
3. Implement endpoint selection logic
4. Add basic validation and error handling

### Phase 2: Enhanced Features
1. Add health checking for dedicated endpoints
2. Implement automatic failover logic
3. Add performance monitoring and metrics
4. Update documentation and examples

### Phase 3: Testing and Validation
1. Unit tests for endpoint selection logic
2. Integration tests with multiple Ollama instances
3. Performance testing and benchmarking
4. Documentation updates

## Files to Modify

### Core Implementation
- `graphiti_core/client_factory.py` - Main implementation
- `.env` - Add new environment variables
- `server/graph_service/zep_graphiti.py` - Update server configuration

### Documentation Updates
- `README.md` - Update configuration examples
- `OLLAMA_INTEGRATION_GUIDE.md` - Add dedicated endpoint section
- `DEPLOYMENT_PROCESS.md` - Update deployment examples

### Testing
- Add tests in `tests/` directory for new functionality
- Update existing integration tests

## Success Criteria

1. **Functional Requirements**
   - Embeddings can use a different Ollama endpoint than LLM operations
   - Fallback to main endpoint works when dedicated endpoint fails
   - Configuration is backward compatible

2. **Performance Requirements**
   - No performance degradation when using single endpoint
   - Improved performance when using optimized dedicated endpoints
   - Graceful handling of endpoint failures

3. **Operational Requirements**
   - Clear logging of which endpoints are being used
   - Easy configuration and troubleshooting
   - Comprehensive documentation

## Risk Mitigation

1. **Backward Compatibility**: All existing configurations continue to work
2. **Fallback Mechanisms**: Automatic fallback to main endpoint if dedicated fails
3. **Validation**: Clear error messages for configuration issues
4. **Testing**: Comprehensive test coverage for all scenarios

## Future Considerations

1. **Authentication**: Support for different API keys per endpoint
2. **Load Balancing**: Multiple embedding endpoints with load balancing
3. **Health Monitoring**: Advanced health checking and alerting
4. **Auto-scaling**: Integration with container orchestration for auto-scaling
