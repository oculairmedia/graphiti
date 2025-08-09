# Rust Search Service Deployment Guide

## Overview

The Rust search service is a high-performance microservice that can be deployed as a standalone container alongside the existing Graphiti Python services.

## Deployment Options

### 1. Docker Compose (Development/Testing)

#### Quick Start
```bash
# Build and start the service
cd graphiti-search-rs
make docker-compose-up

# Check health
curl http://localhost:3004/health
```

#### With Existing Stack
```bash
# Run alongside existing Graphiti services
docker-compose -f docker-compose.yml -f docker-compose.rust-search.yml up -d
```

### 2. Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: graphiti-search-rs
spec:
  replicas: 3
  selector:
    matchLabels:
      app: graphiti-search-rs
  template:
    metadata:
      labels:
        app: graphiti-search-rs
    spec:
      containers:
      - name: graphiti-search-rs
        image: ghcr.io/oculairmedia/graphiti-search-rs:latest
        ports:
        - containerPort: 3004
        env:
        - name: FALKORDB_HOST
          value: "falkordb-service"
        - name: REDIS_URL
          value: "redis://redis-service:6379"
        resources:
          requests:
            memory: "1Gi"
            cpu: "1"
          limits:
            memory: "2Gi"
            cpu: "2"
        livenessProbe:
          httpGet:
            path: /health
            port: 3004
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 3004
          initialDelaySeconds: 10
          periodSeconds: 5
```

### 3. Docker Swarm

```bash
docker service create \
  --name graphiti-search-rs \
  --replicas 3 \
  --publish published=3004,target=3004 \
  --env FALKORDB_HOST=falkordb \
  --env REDIS_URL=redis://redis:6379 \
  --limit-cpu 2 \
  --limit-memory 2G \
  --reserve-cpu 1 \
  --reserve-memory 1G \
  --health-cmd "curl -f http://localhost:3004/health || exit 1" \
  --health-interval 30s \
  ghcr.io/oculairmedia/graphiti-search-rs:latest
```

### 4. AWS ECS Task Definition

```json
{
  "family": "graphiti-search-rs",
  "taskRoleArn": "arn:aws:iam::ACCOUNT:role/ecsTaskRole",
  "executionRoleArn": "arn:aws:iam::ACCOUNT:role/ecsTaskExecutionRole",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "2048",
  "memory": "4096",
  "containerDefinitions": [
    {
      "name": "graphiti-search-rs",
      "image": "ghcr.io/oculairmedia/graphiti-search-rs:latest",
      "portMappings": [
        {
          "containerPort": 3004,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "FALKORDB_HOST",
          "value": "falkordb.internal.domain"
        },
        {
          "name": "REDIS_URL",
          "value": "redis://redis.internal.domain:6379"
        }
      ],
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:3004/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      },
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/graphiti-search-rs",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `PORT` | Service port | 3004 | No |
| `FALKORDB_HOST` | FalkorDB hostname | localhost | Yes |
| `FALKORDB_PORT` | FalkorDB port | 6379 | No |
| `GRAPH_NAME` | Graph database name | graphiti_migration | No |
| `REDIS_URL` | Redis connection URL | redis://localhost:6379 | Yes |
| `MAX_CONNECTIONS` | Max DB connections | 32 | No |
| `CACHE_TTL` | Cache TTL (seconds) | 300 | No |
| `ENABLE_SIMD` | Enable SIMD optimizations | true | No |
| `PARALLEL_THRESHOLD` | Min items for parallel processing | 100 | No |
| `RUST_LOG` | Log level | graphiti_search=debug,info | No |

### Resource Requirements

#### Minimum
- CPU: 1 core
- Memory: 1GB
- Disk: 100MB

#### Recommended
- CPU: 2-4 cores
- Memory: 2-4GB
- Disk: 500MB

#### For High Load
- CPU: 8+ cores (for SIMD operations)
- Memory: 8GB+
- Disk: 1GB (for caching)

## Load Balancing

### Using Nginx (Included)

The included nginx configuration provides:
- Load balancing between Rust and Python services
- Response caching
- Rate limiting
- Health checks

```bash
# Start nginx router
docker-compose -f docker-compose.rust-search.yml up search-router
```

### Using HAProxy

```haproxy
global
    maxconn 4096

defaults
    mode http
    timeout connect 5000ms
    timeout client 30000ms
    timeout server 30000ms

backend search_servers
    balance roundrobin
    option httpchk GET /health
    server rust1 graphiti-search-rs-1:3004 check weight 3
    server rust2 graphiti-search-rs-2:3004 check weight 3
    server python1 graphiti-python-api:8000 check weight 1 backup

frontend search_frontend
    bind *:3005
    default_backend search_servers
```

## Monitoring

### Prometheus Metrics

The service exposes metrics at `/metrics`:

```yaml
# Prometheus scrape config
scrape_configs:
  - job_name: 'graphiti-search-rs'
    static_configs:
      - targets: ['graphiti-search-rs:3004']
    metrics_path: /metrics
```

### Health Checks

```bash
# Basic health check
curl http://localhost:3004/health

# Expected response
{
  "status": "healthy",
  "service": "graphiti-search-rs",
  "database": "connected"
}
```

### Logging

Configure log levels via `RUST_LOG`:
- `error` - Only errors
- `warn` - Warnings and errors
- `info` - Informational messages
- `debug` - Debug output
- `trace` - Detailed trace output

Example:
```bash
RUST_LOG=graphiti_search=debug,tower_http=info,redis=warn
```

## Migration Strategy

### Phase 1: Shadow Mode (Recommended)
1. Deploy Rust service alongside Python
2. Configure load balancer to send 10% traffic to Rust
3. Monitor performance and errors
4. Gradually increase traffic percentage

### Phase 2: Canary Deployment
```bash
# Update load balancer weights
# Rust service: 50%, Python service: 50%
docker exec nginx-router nginx -s reload
```

### Phase 3: Full Migration
```bash
# Rust service: 100%, Python as backup
# Keep Python service running for rollback capability
```

## Rollback Procedure

1. **Immediate Rollback**
```bash
# Switch traffic back to Python
docker exec nginx-router sh -c "sed -i 's/weight=8/weight=0/' /etc/nginx/nginx.conf && nginx -s reload"
```

2. **Gradual Rollback**
```bash
# Reduce Rust traffic percentage
# Monitor and adjust as needed
```

## Performance Tuning

### FalkorDB Connection Pool
```bash
# Increase for high concurrency
MAX_CONNECTIONS=64

# Decrease for resource-constrained environments
MAX_CONNECTIONS=16
```

### Redis Cache
```bash
# Increase TTL for stable data
CACHE_TTL=600

# Decrease for frequently changing data
CACHE_TTL=60
```

### SIMD Optimizations
```bash
# Disable on older CPUs without AVX2
ENABLE_SIMD=false

# Check CPU support
grep avx2 /proc/cpuinfo
```

## Troubleshooting

### Service Won't Start
```bash
# Check logs
docker logs graphiti-search-rs

# Verify connectivity
nc -zv falkordb-host 6379
nc -zv redis-host 6379
```

### High Memory Usage
```bash
# Reduce connection pool size
MAX_CONNECTIONS=16

# Reduce cache size
CACHE_TTL=60
```

### Slow Performance
```bash
# Enable SIMD if supported
ENABLE_SIMD=true

# Adjust parallel threshold
PARALLEL_THRESHOLD=50

# Check CPU throttling
docker stats graphiti-search-rs
```

## Security

### Network Isolation
```yaml
# Docker Compose network configuration
networks:
  graphiti-network:
    driver: bridge
    internal: true
```

### TLS Configuration
```nginx
# Add to nginx config for TLS
server {
    listen 443 ssl http2;
    ssl_certificate /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;
    # ... rest of config
}
```

### API Authentication
Consider adding authentication middleware:
- JWT tokens
- API keys
- OAuth2

## Backup and Recovery

### Data Persistence
The search service is stateless, but caches can be persisted:

```yaml
volumes:
  - redis-data:/data
  - nginx-cache:/var/cache/nginx
```

### Disaster Recovery
1. Service is stateless - can be redeployed anytime
2. Cache will rebuild automatically
3. No data migration required

## Support

For issues or questions:
1. Check logs: `docker logs graphiti-search-rs`
2. Run health check: `curl http://localhost:3004/health`
3. Review metrics: `curl http://localhost:3004/metrics`
4. Open issue on GitHub