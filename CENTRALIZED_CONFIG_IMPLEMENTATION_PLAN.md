# Centralized Configuration Implementation Plan

## Overview
This document outlines the steps to centralize embedding dimension configuration and eliminate the "expected 1024 but got 2560" error by creating a unified configuration system.

## Current Problem
- Scattered hardcoded embedding dimensions (1024) across multiple files
- No centralized configuration management for embedding settings
- Environment variables not consistently used as primary source
- Model changes require manual updates in multiple locations

## Proposed Solution
Create a centralized configuration system that:
1. Auto-detects embedding dimensions from model names
2. Uses environment variables as primary source
3. Provides sensible defaults for current models
4. Validates configuration consistency
5. Eliminates hardcoded dimension values

## Implementation Steps

### Phase 1: Create Centralized Configuration Foundation

#### Step 1.1: Create Core Configuration Module
**File:** `graphiti_core/config/__init__.py`
```python
# Empty init file to make it a package
```

**File:** `graphiti_core/config/settings.py`
```python
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from typing import Optional, Dict

class EmbeddingConfig(BaseModel):
    """Centralized embedding configuration."""
    dimension: int = Field(description="Embedding vector dimension")
    model: str = Field(description="Embedding model name")
    base_url: Optional[str] = Field(default=None, description="Embedding service base URL")
    api_key: str = Field(default="ollama", description="API key for embedding service")
    
    # Model dimension mapping
    MODEL_DIMENSIONS: Dict[str, int] = {
        "mxbai-embed-large": 1024,
        "mxbai-embed-large:latest": 1024,
        "dengcao/Qwen3-Embedding-4B": 2560,
        "dengcao/Qwen3-Embedding-4B:Q4_K_M": 2560,
        "nomic-embed-text": 768,
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }
    
    @classmethod
    def from_environment(cls) -> "EmbeddingConfig":
        """Create config from environment variables with auto-detection."""
        import os
        
        # Get model from environment
        model = os.getenv('OLLAMA_EMBEDDING_MODEL', 'dengcao/Qwen3-Embedding-4B:Q4_K_M')
        
        # Auto-detect dimension or use override
        dimension = int(os.getenv('EMBEDDING_DIMENSION', 0))
        if dimension == 0:  # No override, auto-detect
            dimension = cls.MODEL_DIMENSIONS.get(model, 2560)
        
        base_url = os.getenv('OLLAMA_EMBEDDING_BASE_URL')
        api_key = os.getenv('OLLAMA_EMBEDDING_API_KEY', 'ollama')
        
        return cls(
            dimension=dimension,
            model=model,
            base_url=base_url,
            api_key=api_key
        )

class GraphitiConfig(BaseSettings):
    """Global Graphiti configuration."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.embedding = EmbeddingConfig.from_environment()
    
    class Config:
        env_file = '.env'
        case_sensitive = False
        
# Global config instance
_global_config: Optional[GraphitiConfig] = None

def get_global_config() -> GraphitiConfig:
    """Get or create global configuration instance."""
    global _global_config
    if _global_config is None:
        _global_config = GraphitiConfig()
    return _global_config
```

#### Step 1.2: Create Configuration Utilities
**File:** `graphiti_core/config/utils.py`
```python
from .settings import get_global_config

def get_embedding_dimension() -> int:
    """Get embedding dimension from centralized config."""
    return get_global_config().embedding.dimension

def get_embedding_model() -> str:
    """Get embedding model from centralized config."""
    return get_global_config().embedding.model

def validate_embedding_config() -> bool:
    """Validate embedding configuration consistency."""
    config = get_global_config()
    
    # Check if dimension matches model
    expected_dim = config.embedding.MODEL_DIMENSIONS.get(config.embedding.model)
    if expected_dim and expected_dim != config.embedding.dimension:
        print(f"Warning: Model {config.embedding.model} typically uses {expected_dim} dimensions, but config specifies {config.embedding.dimension}")
        return False
    
    return True
```

### Phase 2: Update Core Components

#### Step 2.1: Fix Primary Embedder Client
**File:** `graphiti_core/embedder/client.py`

**Changes:**
1. Remove hardcoded `EMBEDDING_DIM = 1024`
2. Import centralized config
3. Update `get_embedding_dimension()` function
4. Update `EmbedderConfig` to use centralized config

```python
# Replace existing imports and constants
from graphiti_core.config.utils import get_embedding_dimension

# Remove: EMBEDDING_DIM = 1024
# Replace with dynamic function call in EmbedderConfig
```

#### Step 2.2: Update Client Factory
**File:** `graphiti_core/client_factory.py`

**Changes:**
1. Import centralized config
2. Use config for embedder creation
3. Add validation logging

```python
from graphiti_core.config.settings import get_global_config
from graphiti_core.config.utils import validate_embedding_config

class GraphitiClientFactory:
    @staticmethod
    def create_embedder() -> Optional[EmbedderClient]:
        config = get_global_config()
        
        # Validate configuration
        if not validate_embedding_config():
            logger.warning("Embedding configuration validation failed")
        
        # Use config.embedding.dimension, config.embedding.model, etc.
```

### Phase 3: Update Test Files and Documentation

#### Step 3.1: Update Test Files
**Files to update:**
- `graphiti-search-rs/tests/test_falkordb_sdk.rs`
- `testing/integration/test_direct_v2.py`
- `test_vector_wrapping.py`
- `test_vector_error_investigation.py`

**Changes:**
- Replace hardcoded `1024` with dynamic dimension retrieval
- Add test configuration setup
- Ensure tests use consistent dimensions

#### Step 3.2: Update Documentation
**Files to update:**
- `docs/investigations/falkordb_similarity_type_mismatch.md`
- `OLLAMA_EMBEDDING_GUIDE.md`
- `README.md`

**Changes:**
- Update model dimension references
- Document new configuration system
- Add troubleshooting guide for dimension mismatches

### Phase 4: Add Validation and Error Handling

#### Step 4.1: Add Configuration Validation
**File:** `graphiti_core/config/validation.py`
```python
def validate_system_configuration():
    """Comprehensive system configuration validation."""
    # Check environment variables
    # Validate model availability
    # Test embedding dimension consistency
    # Verify database compatibility
```

#### Step 4.2: Add Startup Validation
**Integration points:**
- Add validation to `GraphitiClientFactory`
- Add validation to service startup
- Add validation to test setup

### Phase 5: Migration and Cleanup

#### Step 5.1: Gradual Migration
1. **Week 1**: Implement centralized config (Phase 1-2)
2. **Week 2**: Update tests and documentation (Phase 3)
3. **Week 3**: Add validation and error handling (Phase 4)
4. **Week 4**: Remove legacy hardcoded values

#### Step 5.2: Cleanup Tasks
- Remove hardcoded dimension values
- Update Docker compose environment variables
- Update deployment documentation
- Add configuration examples

## Implementation Priority

### High Priority (Immediate Fix)
1. ✅ Create centralized config module
2. ✅ Update `graphiti_core/embedder/client.py`
3. ✅ Update `GraphitiClientFactory`
4. ✅ Test basic functionality

### Medium Priority (Consistency)
1. Update all test files
2. Add configuration validation
3. Update documentation
4. Add error handling

### Low Priority (Enhancement)
1. Add model auto-detection
2. Add configuration file support
3. Add advanced validation
4. Add configuration migration tools

## Success Criteria

### Immediate Success
- [ ] No more "expected 1024 but got 2560" errors
- [ ] Single source of truth for embedding dimensions
- [ ] Environment variables properly respected

### Long-term Success
- [ ] Model changes require no code updates
- [ ] Clear error messages for configuration issues
- [ ] Consistent configuration across all services
- [ ] Easy onboarding for new embedding models

## Rollback Plan

If issues arise:
1. **Quick fix**: Update hardcoded default from 1024 to 2560
2. **Partial rollback**: Keep centralized config but disable auto-detection
3. **Full rollback**: Revert to environment variable only approach

## Testing Strategy

1. **Unit tests**: Test configuration loading and validation
2. **Integration tests**: Test with different model configurations
3. **End-to-end tests**: Test full embedding pipeline
4. **Regression tests**: Ensure existing functionality works

## Additional Configuration Values to Centralize

### Performance & Scaling
```python
class PerformanceConfig(BaseModel):
    # Batch processing
    batch_size: int = Field(default=100, description="Default batch size for processing")
    cerebras_batch_size: int = Field(default=2, description="Batch size for Cerebras LLM")
    ollama_batch_size: int = Field(default=1, description="Batch size for Ollama LLM")
    max_workers: int = Field(default=4, description="Maximum worker threads")
    worker_count: int = Field(default=1, description="Number of worker processes")

    # Connection limits
    max_connections: int = Field(default=200, description="Maximum database connections")
    connection_pool_size: int = Field(default=32, description="Connection pool size")

    # Timeouts (in seconds)
    default_timeout: int = Field(default=30, description="Default operation timeout")
    llm_timeout: int = Field(default=120, description="LLM operation timeout")
    centrality_timeout: int = Field(default=120, description="Centrality calculation timeout")
    cache_invalidation_timeout: int = Field(default=5, description="Cache invalidation timeout")
```

### Search & Similarity
```python
class SearchConfig(BaseModel):
    # Similarity thresholds
    similarity_threshold: float = Field(default=0.3, description="Minimum similarity score")
    high_relevance_threshold: float = Field(default=0.7, description="High relevance threshold")
    sim_min_score: float = Field(default=0.3, description="Minimum similarity score for search")

    # Search limits
    search_limit: int = Field(default=50, description="Default search result limit")
    max_search_results: int = Field(default=100, description="Maximum search results")
    bfs_max_depth: int = Field(default=3, description="Maximum BFS search depth")

    # MMR parameters
    mmr_lambda: float = Field(default=0.5, description="MMR diversity parameter")
    centrality_boost_factor: float = Field(default=1.0, description="Centrality boost factor")

    # RRF parameters
    rrf_k: int = Field(default=60, description="RRF K parameter")
```

### Cache Configuration
```python
class CacheConfig(BaseModel):
    # Cache sizes
    l1_cache_size: int = Field(default=1000, description="L1 cache maximum size")
    cache_size: int = Field(default=1000, description="General cache size")

    # TTL settings (in seconds)
    cache_ttl: int = Field(default=300, description="Default cache TTL")
    cache_ttl_seconds: int = Field(default=3600, description="Cache TTL for high relevance")

    # Cache behavior
    enable_cache: bool = Field(default=True, description="Enable caching")
    cache_high_relevance: bool = Field(default=True, description="Cache high relevance items")
```

### Retry & Resilience
```python
class ResilienceConfig(BaseModel):
    # Retry settings
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    retry_attempts: int = Field(default=3, description="Number of retry attempts")
    retry_delay: int = Field(default=1000, description="Retry delay in milliseconds")

    # Exponential backoff
    retry_min_wait: int = Field(default=5, description="Minimum retry wait time")
    retry_max_wait: int = Field(default=120, description="Maximum retry wait time")
    retry_multiplier: int = Field(default=10, description="Retry backoff multiplier")

    # Validation timeouts
    max_validation_time: int = Field(default=300, description="Maximum validation time")
```

### Service URLs & Endpoints
```python
class ServiceConfig(BaseModel):
    # Internal service URLs
    rust_server_url: str = Field(default="http://graph-visualizer-rust:3000", description="Rust server URL")
    rust_centrality_url: str = Field(default="http://graphiti-centrality-rs:3003", description="Rust centrality service URL")
    queue_url: str = Field(default="http://queued:8080", description="Queue service URL")

    # Service ports
    rust_search_port: int = Field(default=3004, description="Rust search service port")
    health_port: int = Field(default=8080, description="Health check port")
    metrics_port: int = Field(default=8081, description="Metrics port")

    # Feature flags
    use_rust_centrality: bool = Field(default=True, description="Use Rust centrality service")
    use_queue_for_ingestion: bool = Field(default=False, description="Use queue for ingestion")
    enable_cache_invalidation: bool = Field(default=True, description="Enable cache invalidation")
```

### Processing Limits
```python
class ProcessingConfig(BaseModel):
    # Query limits
    max_query_length: int = Field(default=10000, description="Maximum Cypher query length")
    max_array_size: int = Field(default=100, description="Maximum array size to process")

    # Entity limits
    max_entities_per_episode: int = Field(default=50, description="Maximum entities per episode")

    # Sync intervals
    sync_interval_seconds: int = Field(default=300, description="Sync interval in seconds")
    batch_progress_interval: int = Field(default=50, description="Progress reporting interval")
    poll_interval: float = Field(default=2.0, description="Polling interval in seconds")
```

## Dependencies

- Pydantic (already in use)
- Environment variable access
- No new external dependencies required

## Timeline

- **Phase 1**: 2-3 days
- **Phase 2**: 2-3 days
- **Phase 3**: 3-4 days
- **Phase 4**: 2-3 days
- **Phase 5**: 1-2 days

**Total estimated time**: 10-15 days
