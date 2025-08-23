# Docker Compose Configuration Guide

This directory contains a consolidated Docker Compose configuration system designed for different deployment scenarios. The configuration is split into a base file and override files for specific use cases.

## Quick Start

### Development (Default)
```bash
# Uses docker-compose.base.yml + docker-compose.override.yml automatically
docker-compose up -d
```

### Production
```bash
# Full production deployment with queue and workers
docker-compose -f docker-compose.base.yml -f docker-compose.prod.override.yml up -d
```

### Frontend-Only (Visualization)
```bash
# Visualization-focused deployment
docker-compose -f docker-compose.base.yml -f docker-compose.frontend.override.yml up -d
```

### Queue-Only (Lightweight Processing)
```bash
# Minimal queue and worker deployment
docker-compose -f docker-compose.base.yml -f docker-compose.queue.override.yml up -d
```

## File Structure

### Base Configuration
- **`docker-compose.base.yml`** - Core services shared across all deployments
  - FalkorDB (graph database)
  - Redis (caching)
  - Rust services (visualization, centrality, search)

### Override Files
- **`docker-compose.override.yml`** - Development configuration (auto-loaded)
  - Development API server with hot reload
  - Development MCP server
  - Development frontend with volume mounts
  - Debug tools (RedisInsight)

- **`docker-compose.prod.override.yml`** - Production configuration
  - Message queue (queued)
  - Scalable workers with resource limits
  - Production API server
  - Monitoring dashboard
  - Production frontend with Nginx proxy

- **`docker-compose.frontend.override.yml`** - Frontend-only deployment
  - Production React frontend
  - Graph visualization services only
  - Optional load balancer
  - Database management UI

- **`docker-compose.queue.override.yml`** - Lightweight queue processing
  - Simple message queue
  - Single worker instance
  - Minimal resource usage

### Legacy Files (Deprecated)
The following files are deprecated and replaced by the new structure:
- `docker-compose.complete.yml` → Use `docker-compose.prod.override.yml`
- `docker-compose.production.yml` → Use `docker-compose.prod.override.yml`
- `docker-compose.frontend.yml` → Use `docker-compose.frontend.override.yml`
- `docker-compose.queue-simple.yml` → Use `docker-compose.queue.override.yml`

## Environment Variables

All configurations use the same environment variables from `.env`. Key variables:

### Database Configuration
```bash
FALKORDB_HOST=localhost
FALKORDB_PORT=6379
FALKORDB_DATABASE=graphiti_migration
NEO4J_DATABASE=neo4j
```

### Service Ports
```bash
API_PORT=8003           # Main API server
FRONTEND_PORT=8080      # React frontend
MCP_PORT=3010          # MCP server
QUEUE_PORT=8080        # Message queue
DASHBOARD_PORT=8091    # Queue dashboard
```

### LLM Configuration
```bash
USE_CEREBRAS=false
USE_OLLAMA=true
OLLAMA_MODEL=gemma3:12b
OPENAI_API_KEY=sk-dummy
```

### Performance Tuning
```bash
WORKER_COUNT=4         # Number of worker processes
BATCH_SIZE=10          # Batch size for operations
NODE_LIMIT=100000      # Graph visualization limits
CACHE_ENABLED=true     # Enable caching
```

## Service Profiles

Some services use Docker Compose profiles for optional components:

### Development Profiles
```bash
# Include development tools (RedisInsight, etc.)
docker-compose --profile tools up -d

# Include frontend development server
docker-compose --profile frontend up -d
```

### Production Profiles
```bash
# Include Nginx reverse proxy
docker-compose -f docker-compose.base.yml -f docker-compose.prod.override.yml --profile proxy up -d

# Include load balancer for frontend
docker-compose -f docker-compose.base.yml -f docker-compose.frontend.override.yml --profile load-balancer up -d
```

## Health Checks and Monitoring

All services include health checks with appropriate intervals:

- **Database services**: 5-10 second intervals
- **API services**: 10-30 second intervals
- **Frontend services**: 30-60 second intervals

### Monitoring Endpoints
- FalkorDB: `http://localhost:6379` (Redis protocol)
- API Health: `http://localhost:8003/healthcheck`
- Queue Status: `http://localhost:8080/queues`
- Frontend Health: `http://localhost:8080/health`

## Resource Management

Production configurations include resource limits:

### Memory Limits
- **FalkorDB**: 3G limit, 2G reservation
- **Workers**: 2G limit, 1G reservation
- **API Server**: 2G limit, 1G reservation
- **Frontend**: 256M limit
- **Queue**: 1G limit

### CPU Limits
- **Database services**: 1-2 CPUs
- **Worker services**: 1-2 CPUs
- **Frontend/Proxy**: 0.5 CPUs

## Migration from Legacy Configurations

To migrate from legacy compose files:

### 1. Update Scripts
Replace old compose file references:
```bash
# Old
docker-compose -f docker-compose.complete.yml up -d

# New
docker-compose -f docker-compose.base.yml -f docker-compose.prod.override.yml up -d
```

### 2. Environment Variables
Ensure your `.env` file includes the new variables:
```bash
FALKORDB_DATABASE=graphiti_migration
NEO4J_DATABASE=neo4j
API_PORT=8003
FRONTEND_PORT=8080
```

### 3. Volume Compatibility
Volume names remain consistent across configurations.

## Troubleshooting

### Common Issues

1. **Service dependencies not ready**
   - Check health checks: `docker-compose ps`
   - View logs: `docker-compose logs <service-name>`

2. **Port conflicts**
   - Update port mappings in `.env`
   - Check for running services: `netstat -tulpn`

3. **Resource constraints**
   - Adjust limits in production overrides
   - Monitor usage: `docker stats`

### Debugging Commands

```bash
# Check service status
docker-compose ps

# View service logs
docker-compose logs -f <service-name>

# Test health endpoints
curl http://localhost:8003/healthcheck
curl http://localhost:8080/queues

# Restart specific service
docker-compose restart <service-name>

# Rebuild and restart
docker-compose up -d --build <service-name>
```

## Development Workflow

### Local Development
1. Start base services: `docker-compose up -d`
2. Access development API: `http://localhost:8003`
3. Access frontend: `http://localhost:8080`

### Testing Changes
1. Build specific service: `docker-compose build <service>`
2. Restart service: `docker-compose up -d <service>`
3. Check logs: `docker-compose logs -f <service>`

### Production Deployment
1. Update environment: `cp .env.example .env`
2. Start production: `docker-compose -f docker-compose.base.yml -f docker-compose.prod.override.yml up -d`
3. Monitor dashboard: `http://localhost:8091`

## Best Practices

1. **Always use override files** for specific deployments
2. **Set resource limits** in production
3. **Use health checks** to ensure service readiness
4. **Monitor logs** during deployment
5. **Test configurations** in development first
6. **Keep `.env` files** out of version control
7. **Document custom configurations** in project-specific override files