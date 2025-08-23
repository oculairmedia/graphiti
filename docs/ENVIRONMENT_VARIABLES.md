# Environment Variables Reference

This document provides comprehensive information about all environment variables used in Graphiti.

## Quick Start

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your specific configuration values

3. Validate your configuration (when available):
   ```bash
   make validate-config
   ```

## Variable Categories

| Category | Description | Required Variables |
|----------|-------------|-------------------|
| **API Keys** | External service authentication | `OPENAI_API_KEY` |
| **Databases** | Graph and caching databases | `FALKORDB_HOST`, `NEO4J_URI` |
| **LLM Services** | Language model configuration | `OLLAMA_BASE_URL`, `CEREBRAS_API_KEY` |
| **Performance** | Caching and optimization | `CACHE_ENABLED`, `NODE_LIMIT` |
| **Services** | Microservice endpoints | `RUST_SERVER_URL`, `QUEUE_URL` |
| **Development** | Debugging and dev tools | `LOG_LEVEL`, `ENABLE_DEBUG_LOGGING` |

## Critical Configuration Patterns

### Database Selection
```bash
# Use FalkorDB (recommended for production)
USE_FALKORDB=true
FALKORDB_HOST=localhost
FALKORDB_PORT=6379
FALKORDB_DATABASE=graphiti_production

# OR use Neo4j (alternative)
USE_FALKORDB=false
NEO4J_URI=bolt://localhost:7687
NEO4J_DATABASE=graphiti
```

### LLM Provider Hierarchy
```bash
# Primary: Cerebras (fast, paid)
USE_CEREBRAS=true
CEREBRAS_API_KEY=csk-...

# Fallback: Ollama (slower, local)  
USE_OLLAMA=true
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=gemma3:12b
```

### Performance Optimization
```bash
# High-performance setup
CACHE_ENABLED=true
CACHE_STRATEGY=aggressive
USE_RUST_CENTRALITY=true
USE_RUST_SEARCH=true
USE_QUEUE_FOR_INGESTION=true
WORKER_COUNT=4
```

## Environment-Specific Configurations

### Development
```bash
# .env.development
NODE_ENV=development
LOG_LEVEL=DEBUG
ENABLE_DEBUG_LOGGING=true
ENABLE_DEV_TOOLS=true
CORS_ORIGINS=*
```

### Production
```bash
# .env.production  
NODE_ENV=production
LOG_LEVEL=INFO
ENABLE_DEBUG_LOGGING=false
CORS_ORIGINS=https://yourdomain.com
ENABLE_SECURITY_HEADERS=true
```

### Testing
```bash
# .env.test
USE_FALKORDB=true
FALKORDB_DATABASE=graphiti_test
MOCK_EXTERNAL_SERVICES=true
QUEUE_FALLBACK_TO_DIRECT=true
```

## Common Configuration Issues

### 1. Database Connection Failures
**Problem**: Services can't connect to database
**Check**:
- `FALKORDB_HOST` and `FALKORDB_PORT` are correct
- Database service is running
- Firewall allows connections

### 2. LLM Service Errors
**Problem**: "Invalid API key" or "Model not found"
**Check**:
- API keys are valid and not expired
- Model names match available models
- Service endpoints are accessible

### 3. Cache Performance Issues
**Problem**: Slow response times
**Check**:
- `CACHE_ENABLED=true`
- Redis service is running
- `CACHE_TTL_SECONDS` appropriate for your use case

### 4. Worker Queue Failures
**Problem**: Ingestion tasks not processing
**Check**:
- `USE_QUEUE_FOR_INGESTION=true`
- Queue service is healthy
- Worker processes are running

## Security Considerations

### Sensitive Variables
These variables contain sensitive data and should never be committed to version control:

- `OPENAI_API_KEY`
- `CEREBRAS_API_KEY`
- `ANTHROPIC_API_KEY`
- `NEO4J_PASSWORD`
- `FALKORDB_PASSWORD`
- `S3_ACCESS_KEY`
- `S3_SECRET_KEY`

### Production Hardening
```bash
# Restrict CORS origins
CORS_ORIGINS=https://yourdomain.com,https://admin.yourdomain.com

# Enable security headers
ENABLE_SECURITY_HEADERS=true

# Use strong authentication
NEO4J_PASSWORD=your-strong-password-here
FALKORDB_PASSWORD=another-strong-password
```

## Variable Validation

Future versions will include configuration validation. Expected format:

```bash
# Check all required variables are set
make validate-config

# Check configuration values are valid
make validate-config --strict

# Generate configuration documentation
make config-docs
```

## Migration Guide

### From v1.x to v2.x
- `DATABASE_URL` → `FALKORDB_URI` or `NEO4J_URI`
- `MODEL_NAME` → `OLLAMA_MODEL`
- `CACHE_TTL` → `CACHE_TTL_SECONDS`

### Docker Compose Changes
- Environment variables now use consistent naming
- Default values moved to `.env.example`
- Service-specific variables clearly labeled

## Troubleshooting

### Configuration Issues
1. **Check syntax**: Ensure no spaces around `=` in variable assignments
2. **Validate values**: Use the validation commands when available
3. **Check logs**: Look for configuration error messages in service logs
4. **Test connections**: Verify database and API connectivity

### Getting Help
1. Check this documentation for common issues
2. Validate your configuration matches the examples
3. Review service logs for specific error messages
4. Consult the main README for additional setup information