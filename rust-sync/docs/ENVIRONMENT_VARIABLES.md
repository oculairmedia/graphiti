# Environment Variables Configuration

This document describes all environment variables supported by the Graphiti Rust Sync Service.

## Quick Reference

All configuration settings can be controlled via environment variables with the `SYNC_` prefix, following the pattern: `SYNC_<SECTION>_<SETTING>`.

## Core Configuration

### Neo4j Connection

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SYNC_NEO4J_URI` | Neo4j connection URI (bolt:// or neo4j://) | `bolt://localhost:7687` | No |
| `SYNC_NEO4J_USER` | Neo4j username | `neo4j` | No |
| `SYNC_NEO4J_PASSWORD` | Neo4j password | `password` | No |
| `SYNC_NEO4J_DATABASE` | Neo4j database name | `neo4j` | No |
| `SYNC_NEO4J_POOL_SIZE` | Connection pool size | `10` | No |

**Example:**
```bash
export SYNC_NEO4J_URI=bolt://neo4j.example.com:7687
export SYNC_NEO4J_USER=admin
export SYNC_NEO4J_PASSWORD=secretpassword
export SYNC_NEO4J_DATABASE=graphiti
export SYNC_NEO4J_POOL_SIZE=20
```

### FalkorDB Connection

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SYNC_FALKORDB_HOST` | FalkorDB hostname or IP | `localhost` | No |
| `SYNC_FALKORDB_PORT` | FalkorDB port | `6379` | No |
| `SYNC_FALKORDB_DATABASE` | FalkorDB graph database name | `graphiti` | No |

**Example:**
```bash
export SYNC_FALKORDB_HOST=falkordb.example.com
export SYNC_FALKORDB_PORT=6379
export SYNC_FALKORDB_DATABASE=knowledge_graph
```

## Sync Configuration

### Performance & Batching

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SYNC_SYNC_BATCH_SIZE` | Batch size for node/edge operations | `400` | No |
| `SYNC_SYNC_MAX_QUERY_LIMIT` | Maximum query result limit | `1000000` | No |
| `SYNC_SYNC_PARALLEL_WORKERS` | Number of parallel loading workers | `4` | No |

**Example:**
```bash
export SYNC_SYNC_BATCH_SIZE=500
export SYNC_SYNC_MAX_QUERY_LIMIT=5000000
export SYNC_SYNC_PARALLEL_WORKERS=8
```

### Timing & Intervals

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SYNC_SYNC_INTERVAL_SECONDS` | Sync interval for continuous mode (seconds) | `180` | No |
| `SYNC_SYNC_QUERY_TIMEOUT_MS` | Query execution timeout (milliseconds) | `300000` (5 min) | No |
| `SYNC_SYNC_OPERATION_TIMEOUT_SECONDS` | Overall operation timeout (seconds) | `3600` (1 hour) | No |

**Example:**
```bash
export SYNC_SYNC_INTERVAL_SECONDS=300
export SYNC_SYNC_QUERY_TIMEOUT_MS=600000
export SYNC_SYNC_OPERATION_TIMEOUT_SECONDS=7200
```

### Retry & Resilience

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SYNC_SYNC_RETRY_ATTEMPTS` | Number of retry attempts on failure | `3` | No |
| `SYNC_SYNC_RETRY_BACKOFF_MS` | Initial backoff delay (milliseconds) | `500` | No |

**Example:**
```bash
export SYNC_SYNC_RETRY_ATTEMPTS=5
export SYNC_SYNC_RETRY_BACKOFF_MS=1000
```

### Safety Validation

| Variable | Description | Default | Required | Valid Values |
|----------|-------------|---------|----------|--------------|
| `SYNC_SAFETY_ENABLED` | Enable/disable safety validation | `true` | No | `true`, `false` |
| `SYNC_SAFETY_NODE_THRESHOLD_PCT` | Maximum acceptable node reduction (%) | `50.0` | No | `0.0` - `100.0` |
| `SYNC_SAFETY_EDGE_THRESHOLD_PCT` | Maximum acceptable edge reduction (%) | `50.0` | No | `0.0` - `100.0` |
| `FORCE_UNSAFE_SYNC` | Override safety checks (DANGEROUS) | `false` | No | `true`, `false` |

**Example:**
```bash
# Production settings (strict)
export SYNC_SAFETY_ENABLED=true
export SYNC_SAFETY_NODE_THRESHOLD_PCT=25.0
export SYNC_SAFETY_EDGE_THRESHOLD_PCT=30.0

# Override for emergency recovery (USE WITH CAUTION)
export FORCE_UNSAFE_SYNC=true
```

**Safety Validation Behavior:**

The safety validator prevents accidental data loss by:
1. **Comparing counts** before sync: Entity nodes, Episodic nodes, Community nodes, and Edges
2. **Blocking syncs** that would reduce data beyond the threshold
3. **Logging detailed reports** showing what would be lost
4. **Allowing override** with `FORCE_UNSAFE_SYNC=true` for intentional operations

**Example Safety Report:**
```
🛡️  Safety Validation Report
   Direction: falkor-to-neo4j
   Status: UNSAFE ❌

   ✅ SAFE: Entity nodes counts match (1000 = 1000)
   ❌ UNSAFE: Episodic nodes would lose 75.0% of data (800 → 200). Threshold: 50.0%
   ✅ SAFE: Community nodes will gain data (50 → 75)
   ✅ SAFE: Edges within acceptable threshold (5000 → 4800)

   ❌ BLOCKED: 1 of 4 safety checks failed for falkor-to-neo4j sync
```

**When to Use Force Override:**
- ⚠️ **Intentional data migration** from old to new database
- ⚠️ **Disaster recovery** after catastrophic failure
- ⚠️ **Testing** in non-production environments

**Never Use in Production Without Understanding:**
- Setting `FORCE_UNSAFE_SYNC=true` bypasses ALL safety checks
- This can lead to permanent data loss
- Always backup before using this option

## Monitoring & Observability

### Health Check Server

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SYNC_HEALTH_PORT` | Health check HTTP server port | `8080` | No |
| `SYNC_HEALTH_PATH` | Primary health check endpoint path | `/health` | No |
| `HEALTH_PORT` | Override for health port (legacy) | `8080` | No |

**Example:**
```bash
export SYNC_HEALTH_PORT=9090
export SYNC_HEALTH_PATH=/healthz
```

**Health Endpoints:**
- `GET /health` - Full health check with database connectivity
- `GET /healthz` - Alias for /health
- `GET /live` - Liveness probe (always 200 if running)
- `GET /ready` - Readiness probe (checks database connectivity)
- `GET /metrics` - Prometheus metrics

### Metrics Server

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SYNC_METRICS_PORT` | Prometheus metrics HTTP server port | `8081` | No |

**Example:**
```bash
export SYNC_METRICS_PORT=9091
```

**Metrics Endpoint:**
- `GET /metrics` - Prometheus text format metrics

**Available Metrics:**
- `graphiti_sync_attempts_total{direction}` - Total sync attempts
- `graphiti_sync_success_total{direction}` - Successful syncs
- `graphiti_sync_failure_total{direction}` - Failed syncs
- `graphiti_sync_nodes_total{direction}` - Total nodes synced
- `graphiti_sync_edges_total{direction}` - Total edges synced
- `graphiti_sync_duration_seconds{direction}` - Sync duration histogram
- `graphiti_sync_active{direction}` - Active sync operations (gauge)

### Logging

| Variable | Description | Default | Required | Valid Values |
|----------|-------------|---------|----------|--------------|
| `LOG_LEVEL` | Logging verbosity level | `INFO` | No | `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR` |

**Example:**
```bash
export LOG_LEVEL=DEBUG
```

## Advanced Configuration

### Parallel Workers Override

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SYNC_NUM_WORKERS` | Override parallel workers (used in test commands) | `SYNC_SYNC_PARALLEL_WORKERS` | No |

**Example:**
```bash
export SYNC_NUM_WORKERS=16
```

## Configuration Validation

The service validates configuration on startup and will:
1. Log all configuration values (passwords sanitized)
2. Fail fast on invalid configuration
3. Show clear error messages for missing required settings

**Example startup logs:**
```
INFO Starting Graphiti Rust Sync Service
INFO Configuration loaded successfully
INFO   Neo4j URI: bolt://localhost:7687
INFO   FalkorDB: localhost:6379
INFO   Batch size: 400
INFO   Query limit: 1000000
```

## Complete Production Example

```bash
# Neo4j
export SYNC_NEO4J_URI=bolt://production-neo4j:7687
export SYNC_NEO4J_USER=graphiti_sync
export SYNC_NEO4J_PASSWORD=secure_password_here
export SYNC_NEO4J_DATABASE=production
export SYNC_NEO4J_POOL_SIZE=20

# FalkorDB
export SYNC_FALKORDB_HOST=production-falkor
export SYNC_FALKORDB_PORT=6379
export SYNC_FALKORDB_DATABASE=graphiti_prod

# Performance
export SYNC_SYNC_BATCH_SIZE=500
export SYNC_SYNC_PARALLEL_WORKERS=8
export SYNC_SYNC_INTERVAL_SECONDS=300
export SYNC_SYNC_RETRY_ATTEMPTS=5

# Timeouts
export SYNC_SYNC_QUERY_TIMEOUT_MS=600000
export SYNC_SYNC_OPERATION_TIMEOUT_SECONDS=7200

# Safety (prevent accidental data loss)
export SYNC_SAFETY_ENABLED=true
export SYNC_SAFETY_NODE_THRESHOLD_PCT=25.0
export SYNC_SAFETY_EDGE_THRESHOLD_PCT=30.0

# Monitoring
export SYNC_HEALTH_PORT=8080
export SYNC_METRICS_PORT=8081
export LOG_LEVEL=INFO

# Run continuous sync
./graphiti-sync-rs sync-loop falkor-to-neo4j
```

## Docker Compose Example

```yaml
version: '3.8'

services:
  sync-service:
    image: graphiti-sync-rs:latest
    environment:
      # Neo4j
      SYNC_NEO4J_URI: bolt://neo4j:7687
      SYNC_NEO4J_USER: neo4j
      SYNC_NEO4J_PASSWORD: ${NEO4J_PASSWORD}
      SYNC_NEO4J_DATABASE: neo4j
      
      # FalkorDB
      SYNC_FALKORDB_HOST: falkordb
      SYNC_FALKORDB_PORT: 6379
      SYNC_FALKORDB_DATABASE: graphiti
      
      # Performance
      SYNC_SYNC_BATCH_SIZE: 500
      SYNC_SYNC_PARALLEL_WORKERS: 8
      SYNC_SYNC_INTERVAL_SECONDS: 300
      
      # Safety validation
      SYNC_SAFETY_ENABLED: true
      SYNC_SAFETY_NODE_THRESHOLD_PCT: 30.0
      SYNC_SAFETY_EDGE_THRESHOLD_PCT: 30.0
      
      # Monitoring
      SYNC_HEALTH_PORT: 8080
      SYNC_METRICS_PORT: 8081
      LOG_LEVEL: INFO
    ports:
      - "8080:8080"  # Health check
      - "8081:8081"  # Metrics
    command: sync-loop falkor-to-neo4j
    depends_on:
      - neo4j
      - falkordb
```

## Troubleshooting

### Configuration Not Loading

If environment variables aren't being recognized:

1. **Check prefix**: All variables must start with `SYNC_`
2. **Check nested structure**: Use underscores: `SYNC_NEO4J_URI`, not `SYNC_NEO4JURI`
3. **Check case**: Variable names are case-sensitive
4. **View loaded config**: Check startup logs for actual values

### Override Priority

Configuration is loaded in this order (later overrides earlier):

1. Default values (hardcoded in `src/config/settings.rs`)
2. Environment variables with `SYNC_` prefix
3. Special overrides (`HEALTH_PORT`, `SYNC_METRICS_PORT`, `SYNC_NUM_WORKERS`)

### Debugging Configuration

Enable debug logging to see configuration loading:

```bash
export LOG_LEVEL=DEBUG
./graphiti-sync-rs health-server
```

## Security Best Practices

1. **Never commit credentials** - Use environment variables or secrets management
2. **Use strong passwords** - Especially for Neo4j authentication
3. **Restrict network access** - Firewall health/metrics ports appropriately
4. **Sanitize logs** - Passwords are automatically redacted in logs
5. **Use TLS** - Configure `neo4j://` (TLS) instead of `bolt://` for production

## See Also

- [README.md](../README.md) - General usage and architecture
- [src/config/settings.rs](../src/config/settings.rs) - Configuration implementation
- [src/main.rs](../src/main.rs) - Command-line interface
