# Cerebras/Qwen Test Suite for Graphiti

This directory contains a comprehensive test suite for evaluating Cerebras/Qwen integration with the Graphiti knowledge graph platform. The tests are designed to validate performance, reliability, and optimization of the Qwen model for entity extraction and knowledge graph construction.

## Test Files Overview

### Core Integration Tests

1. **`test_minimal_cerebras.py`** - Basic connectivity and client initialization
   - Tests Cerebras API connection
   - Validates basic LLM functionality  
   - Checks embedder integration
   - Simple database connectivity

2. **`test_cerebras_structured.py`** - JSON structure validation and Qwen capabilities
   - Tests structured output generation
   - Validates multilingual extraction
   - Tests reasoning chains
   - Qwen-specific feature validation

3. **`test_cerebras_debug.py`** - Component-by-component debugging
   - Step-by-step system validation
   - Detailed error diagnostics
   - Performance profiling
   - Configuration verification

### Full Integration Tests

4. **`test_full_cerebras.py`** - Complete Graphiti integration
   - End-to-end episode processing
   - Concurrent request testing
   - Qwen-specific capability testing
   - Performance metrics collection

5. **`test_cerebras_ingestion.py`** - Pipeline ingestion testing
   - AI research data scenarios
   - Quality assessment metrics
   - Graph statistics analysis
   - Extraction validation

6. **`test_cerebras_retrieval.py`** - Data retrieval and search
   - Technical concept searches
   - Complex relationship queries
   - Semantic search validation
   - Entity type analysis

### Advanced Testing

7. **`test_cerebras_optimization.py`** - Parameter optimization
   - Temperature sweep testing
   - Token limit optimization
   - Prompt variation testing
   - Rate limiting analysis

8. **`test_cerebras_vs_ollama_comparison.py`** - Performance comparison
   - Head-to-head benchmarking
   - Extraction quality comparison
   - Speed and reliability metrics
   - Recommendation generation

9. **`test_cerebras_pipeline_integration.py`** - End-to-end pipeline
   - Complete pipeline validation
   - Data integrity checking
   - Performance bottleneck identification
   - Production readiness assessment

### Test Suite Runner

10. **`run_cerebras_test_suite.py`** - Comprehensive test orchestration
    - Sequential test execution
    - Prerequisite checking
    - Comprehensive reporting
    - Error categorization

## Prerequisites

### Required Environment Variables

```bash
# Required for Cerebras/Qwen LLM functionality
export CEREBRAS_API_KEY="your-cerebras-api-key"

# Optional - for comparison tests
export OPENAI_API_KEY="your-openai-key-for-fallback"
```

### Required Services

1. **FalkorDB** - Graph database (port 6389)
   ```bash
   # Start FalkorDB with Docker
   docker run -p 6389:6379 falkordb/falkordb:latest
   ```

2. **Ollama** - For embeddings (hybrid approach, port 11434)
   ```bash
   # Start Ollama and pull embedding model
   ollama serve
   ollama pull mxbai-embed-large
   ```

### Python Dependencies

```bash
# Install Graphiti with dependencies
pip install graphiti-core[all]

# Additional test dependencies
pip install aiohttp
pip install falkordb
```

## Quick Start

### Run All Tests
```bash
cd testing/demos
python run_cerebras_test_suite.py
```

### Run Critical Tests Only
```bash
python run_cerebras_test_suite.py --critical-only
```

### Run Individual Tests
```bash
# Basic connectivity
python test_minimal_cerebras.py

# Structured output validation
python test_cerebras_structured.py

# Full integration test
python test_full_cerebras.py
```

## Test Categories

### Critical Tests (Must Pass)
- ✅ Minimal Connection Test
- ✅ Structured Output Test  
- ✅ Full Integration Test
- ✅ Ingestion Pipeline Test
- ✅ Retrieval and Search Test
- ✅ End-to-End Pipeline Integration

### Optional Tests (Performance & Comparison)
- 🔧 Debug and Diagnostics
- 🔧 Parameter Optimization
- 🔧 Cerebras vs Ollama Comparison

## Key Features Tested

### Qwen Model Capabilities
- **Code Analysis**: Technical content extraction
- **Mathematical Reasoning**: Complex problem solving
- **Multilingual Support**: Cross-language entity extraction
- **Structured Output**: Reliable JSON generation
- **Long Context**: Extended text processing

### Integration Points
- **Cerebras API**: Rate limiting, error handling
- **FalkorDB**: Graph storage and querying
- **Hybrid Embeddings**: Ollama for semantic search
- **Knowledge Graph**: Entity and relationship extraction

### Performance Metrics
- **Extraction Quality**: Entity and relationship accuracy
- **Processing Speed**: Time-to-completion measurements
- **Reliability**: Success rates and error analysis
- **Scalability**: Large data volume handling

## Expected Results

### Production Readiness Criteria
- ✅ Critical test success rate: ≥90%
- ✅ Average processing time: <30s per episode
- ✅ Entity extraction accuracy: ≥85%
- ✅ Zero critical failures

### Performance Benchmarks
- **Simple Episodes** (1-2 paragraphs): 5-15 seconds
- **Complex Episodes** (3-5 paragraphs): 15-45 seconds  
- **Technical Content**: 20-60 seconds (higher accuracy)
- **Search Queries**: <3 seconds per query

## Troubleshooting

### Common Issues

1. **API Key Problems**
   ```
   Error: CEREBRAS_API_KEY not found
   Solution: Set environment variable with valid key
   ```

2. **Database Connection**
   ```
   Error: FalkorDB connection failed
   Solution: Start FalkorDB service on port 6389
   ```

3. **Embedding Service**
   ```
   Error: Ollama connection failed  
   Solution: Start Ollama service with mxbai-embed-large
   ```

4. **Timeout Issues**
   ```
   Error: Request timed out
   Solution: Use --timeout-multiplier 2.0 for slower systems
   ```

### Debug Steps

1. Run minimal test first: `python test_minimal_cerebras.py`
2. Check debug output: `python test_cerebras_debug.py`
3. Validate each component individually
4. Review comprehensive logs from test suite runner

## Optimization Recommendations

### For Production Deployment

1. **Temperature Settings**: 0.2-0.3 for extraction tasks
2. **Token Limits**: 1500-2000 for complex content
3. **Timeout Values**: 60-120s depending on content complexity
4. **Batch Processing**: Process multiple episodes concurrently
5. **Error Handling**: Implement retry logic with exponential backoff

### Performance Tuning

1. **Database Optimization**: Use appropriate indices
2. **Embedding Caching**: Cache frequently used embeddings
3. **Rate Limiting**: Respect Cerebras API limits
4. **Memory Management**: Monitor for memory leaks in long runs

## Contributing

When adding new tests:

1. Follow naming convention: `test_cerebras_[feature].py`
2. Include both success and failure scenarios
3. Add comprehensive error handling
4. Document expected behavior and performance
5. Update test suite runner configuration

## Support

For issues with:
- **Cerebras Integration**: Check API documentation and rate limits
- **Graphiti Core**: Review main project documentation
- **FalkorDB**: Consult FalkorDB documentation
- **Test Framework**: Review test logs and error messages