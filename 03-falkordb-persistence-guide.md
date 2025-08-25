# FalkorDB Persistence Implementation Guide

## Overview

FalkorDB is a Redis module that inherits Redis's persistence mechanisms while adding graph-specific considerations. This guide covers FalkorDB-specific persistence implementation, configuration, and best practices.

> Graphiti context: FalkorDB in Graphiti stores long-lived episode, entity, and relationship data. Persistence must survive orchestrated restarts during ingestion runs and scheduled maintenance. The configurations below should be embedded in the Graphiti infra manifests (docker-compose, Kubernetes) under the falkordb service/statefulset. For Graphiti caches, use separate Redis with persistence disabled.


## FalkorDB Persistence Architecture

### Module Integration with Redis Persistence

FalkorDB leverages Redis's native persistence mechanisms:
- **Graph data structures** are serialized through Redis RDB format
- **Graph operations** are logged through Redis AOF
- **Module state** is preserved across restarts
- **No additional persistence layer** required

### Graph Data Persistence

```cypher
-- Example: Creating persistent graph data
CREATE (:Person {name: 'Alice', age: 30})-[:KNOWS]->(:Person {name: 'Bob', age: 25})
```

The above graph structure is automatically persisted through Redis mechanisms without additional configuration.

## Docker Deployment with Persistence

### Basic Docker Setup

```bash
# Create persistent volume
docker volume create falkordb_data

# Run FalkorDB with persistence
docker run -d \
  --name falkordb \
  -v falkordb_data:/var/lib/falkordb/data \
  -p 6379:6379 \
  -e REDIS_ARGS="--appendonly yes --appendfsync everysec --save 900 1 --save 300 10 --save 60 10000" \
  falkordb/falkordb:latest
```

### Production Docker Configuration

```bash
# Production-ready FalkorDB with comprehensive persistence
docker run -d \
  --name falkordb-prod \
  --restart unless-stopped \
  -v falkordb_data:/var/lib/falkordb/data \
  -v falkordb_config:/etc/falkordb \
  -p 6379:6379 \
  -e REDIS_ARGS="--requirepass ${REDIS_PASSWORD} --appendonly yes --appendfsync everysec --save 900 1 --save 300 10 --save 60 10000 --rdbcompression yes --rdbchecksum yes" \
  -e FALKORDB_ARGS="THREAD_COUNT 4 CACHE_SIZE 100" \
  falkordb/falkordb:latest
```

### Docker Compose Configuration

```yaml
version: '3.8'
services:
  falkordb:
    image: falkordb/falkordb:latest
    container_name: falkordb-prod
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - falkordb_data:/var/lib/falkordb/data
      - falkordb_config:/etc/falkordb
      - ./redis.conf:/etc/redis/redis.conf
    environment:
      - REDIS_ARGS=--requirepass ${REDIS_PASSWORD} --appendonly yes --appendfsync everysec
      - FALKORDB_ARGS=THREAD_COUNT 4 CACHE_SIZE 100
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  falkordb_data:
    driver: local
  falkordb_config:
    driver: local
```

## Kubernetes Deployment

### Helm Configuration (values.yaml)

```yaml
global:
  security:
    allowInsecureImages: true

image:
  registry: docker.io
  repository: falkordb/falkordb
  tag: "latest"

master:
  persistence:
    enabled: true
    size: 100Gi
    storageClass: "fast-ssd"
  extraFlags:
    - "--loadmodule /FalkorDB/bin/src/falkordb.so"
    - "--appendonly yes"
    - "--appendfsync everysec"
    - "--save 900 1"
    - "--save 300 10"
    - "--save 60 10000"

replica:
  persistence:
    enabled: true
    size: 100Gi
    storageClass: "fast-ssd"
  extraFlags:
    - "--loadmodule /FalkorDB/bin/src/falkordb.so"
    - "--appendonly yes"
    - "--appendfsync everysec"

auth:
  enabled: true
  password: "${REDIS_PASSWORD}"
```

### Kubernetes Deployment

```bash
# Install FalkorDB with persistence
helm install falkordb-prod oci://registry-1.docker.io/bitnamicharts/redis -f values.yaml

# Verify persistence
kubectl get pvc
kubectl describe pvc data-falkordb-prod-master-0
```

## Configuration Files

### redis.conf for FalkorDB

```redis
# FalkorDB Redis Configuration with Persistence

# Load FalkorDB module
loadmodule /FalkorDB/bin/src/falkordb.so THREAD_COUNT 4 CACHE_SIZE 100

# Network configuration
bind 0.0.0.0
port 6379
protected-mode yes
requirepass your_secure_password

# Persistence configuration
appendonly yes
appendfsync everysec
appendfilename "appendonly.aof"
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb

save 900 1
save 300 10
save 60 10000
dbfilename dump.rdb

# Graphiti paths: In docker-compose.yml we mount `/var/lib/falkordb/data` for persistence. Ensure this maps to durable storage in production. For mcp_server/docker-compose.yml and frontend compose files using `/data`, align to a single data path convention.


# Directory configuration
dir /var/lib/falkordb/data

# Performance tuning
rdbcompression yes
rdbchecksum yes
maxmemory-policy allkeys-lru

# Logging
loglevel notice
logfile /var/log/falkordb/falkordb.log

# Security
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command CONFIG "CONFIG_b835c3f8a5d2e7f1"
```

## Data Persistence Verification

### Testing Persistence

```bash
# 1. Create test data
redis-cli GRAPH.QUERY testgraph "CREATE (:Database {name:'falkordb', type:'graph'})"

# 2. Verify data exists
redis-cli GRAPH.QUERY testgraph "MATCH (n) RETURN n"

# 3. Restart container/service
docker restart falkordb

# 4. Verify data persisted
redis-cli GRAPH.QUERY testgraph "MATCH (n) RETURN n"
# Should return the same data
```

### Automated Verification Script

```bash
#!/bin/bash
# verify-persistence.sh

REDIS_HOST="localhost"
REDIS_PORT="6379"
REDIS_PASSWORD="your_password"
GRAPH_NAME="persistence_test"

echo "Testing FalkorDB persistence..."

# Create test data
redis-cli -h $REDIS_HOST -p $REDIS_PORT -a $REDIS_PASSWORD \
  GRAPH.QUERY $GRAPH_NAME "CREATE (:Test {id: 1, timestamp: timestamp()})"

# Get initial count
INITIAL_COUNT=$(redis-cli -h $REDIS_HOST -p $REDIS_PORT -a $REDIS_PASSWORD \
  GRAPH.QUERY $GRAPH_NAME "MATCH (n:Test) RETURN count(n)" | head -n 1)

echo "Initial node count: $INITIAL_COUNT"

# Trigger persistence
redis-cli -h $REDIS_HOST -p $REDIS_PORT -a $REDIS_PASSWORD BGSAVE
redis-cli -h $REDIS_HOST -p $REDIS_PORT -a $REDIS_PASSWORD BGREWRITEAOF

echo "Persistence operations completed"
echo "Restart your FalkorDB instance and run this script again to verify"
```

## FalkorDB-Specific Configuration Parameters

### Module Configuration

```redis
# FalkorDB module parameters affecting persistence
THREAD_COUNT 4              # Number of query execution threads
CACHE_SIZE 100             # Query cache size
TIMEOUT_DEFAULT 0          # Default query timeout (0 = unlimited)
TIMEOUT_MAX 0              # Maximum query timeout
RESULTSET_SIZE -1          # Maximum result set size (-1 = unlimited)
QUERY_MEM_CAPACITY 0       # Maximum memory per query (0 = unlimited)
```

### Runtime Configuration

```redis
# Set FalkorDB configuration at runtime
GRAPH.CONFIG SET CACHE_SIZE 200
GRAPH.CONFIG SET TIMEOUT_DEFAULT 30000

# Get current configuration
GRAPH.CONFIG GET *
```

## Backup Procedures for FalkorDB

### Manual Backup

```bash
#!/bin/bash
# backup-falkordb.sh

BACKUP_DIR="/backup/falkordb/$(date +%Y%m%d_%H%M%S)"
REDIS_DATA_DIR="/var/lib/falkordb/data"

mkdir -p $BACKUP_DIR

# Stop AOF rewrites during backup
redis-cli CONFIG SET auto-aof-rewrite-percentage 0

# Wait for any ongoing rewrite to complete
while [ "$(redis-cli INFO persistence | grep aof_rewrite_in_progress:1)" ]; do
  echo "Waiting for AOF rewrite to complete..."
  sleep 5
done

# Backup files
cp $REDIS_DATA_DIR/dump.rdb $BACKUP_DIR/
cp $REDIS_DATA_DIR/appendonly.aof $BACKUP_DIR/

# Re-enable AOF rewrites
redis-cli CONFIG SET auto-aof-rewrite-percentage 100

echo "Backup completed: $BACKUP_DIR"
```

### Automated Backup with Cron

```bash
# Add to crontab for daily backups at 2 AM
0 2 * * * /opt/scripts/backup-falkordb.sh >> /var/log/falkordb-backup.log 2>&1
```

## Recovery Procedures

### Recovery from RDB

```bash
# 1. Stop FalkorDB
docker stop falkordb

# 2. Replace RDB file
cp /backup/dump.rdb /var/lib/falkordb/data/

# 3. Start FalkorDB
docker start falkordb

# 4. Verify data
redis-cli GRAPH.QUERY testgraph "MATCH (n) RETURN count(n)"
```

### Recovery from AOF

```bash
# 1. Stop FalkorDB
docker stop falkordb

# 2. Replace AOF file
cp /backup/appendonly.aof /var/lib/falkordb/data/

# 3. Start FalkorDB (will replay AOF)
docker start falkordb

# 4. Monitor recovery progress
docker logs -f falkordb
```

## Monitoring FalkorDB Persistence

### Key Metrics

```redis
# Check persistence status
INFO persistence

# Key metrics to monitor:
# rdb_last_save_time - Last RDB save timestamp
# rdb_changes_since_last_save - Changes since last save
# aof_enabled - AOF status
# aof_rewrite_in_progress - AOF rewrite status
# aof_last_rewrite_time_sec - Last rewrite duration
```

### Health Check Script

```bash
#!/bin/bash
# health-check.sh

REDIS_CLI="redis-cli -a $REDIS_PASSWORD"

# Check if FalkorDB module is loaded
MODULE_STATUS=$($REDIS_CLI MODULE LIST | grep -i falkor)
if [ -z "$MODULE_STATUS" ]; then
  echo "ERROR: FalkorDB module not loaded"
  exit 1
fi

# Check persistence status
PERSISTENCE_INFO=$($REDIS_CLI INFO persistence)
echo "Persistence Status:"
echo "$PERSISTENCE_INFO" | grep -E "(rdb_last_save_time|aof_enabled|aof_last_rewrite_time)"

# Test graph operations
$REDIS_CLI GRAPH.QUERY healthcheck "CREATE (:HealthCheck {timestamp: timestamp()})" > /dev/null
$REDIS_CLI GRAPH.QUERY healthcheck "MATCH (n:HealthCheck) DELETE n" > /dev/null

echo "Health check completed successfully"
```

---

**Next**: See [04-configuration-reference.md](04-configuration-reference.md) for detailed configuration parameters.
