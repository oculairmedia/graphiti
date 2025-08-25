# FalkorDB Persistence Implementation Guide

## Implementation Overview

This guide provides step-by-step instructions for implementing persistence in FalkorDB deployments, from basic setups to production-ready configurations.

> Graphiti context: Integrate these steps into Graphiti’s infra (docker-compose and/or Kubernetes). For local developer setups, keep persistence enabled on FalkorDB to validate ingestion idempotency and recovery. For ephemeral CI caches, disable persistence to speed up builds.


## Phase 1: Basic AOF Implementation

### Step 1: Prepare Environment

```bash
# Create necessary directories
sudo mkdir -p /var/lib/falkordb/data
sudo mkdir -p /var/log/falkordb
sudo mkdir -p /etc/falkordb

# Set proper permissions
sudo chown -R redis:redis /var/lib/falkordb
sudo chown -R redis:redis /var/log/falkordb
sudo chown -R redis:redis /etc/falkordb
```

### Step 2: Basic Configuration File

Create `/etc/falkordb/redis.conf`:

```redis
# Basic FalkorDB configuration with AOF persistence

# Module loading
loadmodule /FalkorDB/bin/src/falkordb.so THREAD_COUNT 4 CACHE_SIZE 100

# Network
bind 127.0.0.1
port 6379
protected-mode yes

# Basic AOF persistence
appendonly yes
appendfsync everysec
appendfilename "appendonly.aof"

# Data directory
dir /var/lib/falkordb/data

# Logging
loglevel notice
logfile /var/log/falkordb/falkordb.log
```

### Step 3: Start FalkorDB with Basic Persistence

```bash
# Start Redis with FalkorDB module
redis-server /etc/falkordb/redis.conf

# Or using Docker
docker run -d \
  --name falkordb-basic \
  -v falkordb_data:/var/lib/falkordb/data \
  -p 6379:6379 \
  -e REDIS_ARGS="--appendonly yes --appendfsync everysec" \
  falkordb/falkordb:latest
```

### Step 4: Verify Basic Persistence

```bash
# Test data creation and persistence
redis-cli GRAPH.QUERY testdb "CREATE (:Person {name: 'Alice', id: 1})"

# Check AOF file creation
ls -la /var/lib/falkordb/data/appendonly.aof

# Restart service
sudo systemctl restart redis
# or
docker restart falkordb-basic

# Verify data persisted
redis-cli GRAPH.QUERY testdb "MATCH (p:Person) RETURN p.name, p.id"
```

## Phase 2: Production Configuration

### Step 1: Enhanced Configuration

Create `/etc/falkordb/redis-prod.conf`:

```redis
# Production FalkorDB configuration

# Module loading with optimized parameters
loadmodule /FalkorDB/bin/src/falkordb.so THREAD_COUNT 8 CACHE_SIZE 200 TIMEOUT_DEFAULT 30000

# Network and security
bind 0.0.0.0
port 6379
protected-mode yes
requirepass your_secure_password_here
tcp-keepalive 300

# Hybrid persistence configuration
appendonly yes
appendfsync everysec
appendfilename "appendonly.aof"
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
aof-use-rdb-preamble yes

# RDB snapshots
save 900 1
save 300 10
save 60 10000
dbfilename dump.rdb

# Graphiti note: In docker-compose.yml, FalkorDB currently sets `--maxmemory-policy allkeys-lru` for constrained dev profiles. For production Graphiti, switch to `noeviction` and increase `maxmemory` based on dataset size and headroom for fork operations.

rdbcompression yes
rdbchecksum yes

# Performance optimization
maxmemory-policy allkeys-lru
maxmemory 8gb
tcp-backlog 511

# Directory and logging
dir /var/lib/falkordb/data
logfile /var/log/falkordb/falkordb.log
loglevel notice

# Security hardening
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command CONFIG "CONFIG_a1b2c3d4e5f6"
```

### Step 2: Systemd Service Configuration

Create `/etc/systemd/system/falkordb.service`:

```ini
[Unit]
Description=FalkorDB Graph Database
After=network.target

[Service]
Type=notify
ExecStart=/usr/bin/redis-server /etc/falkordb/redis-prod.conf
ExecReload=/bin/kill -USR2 $MAINPID
TimeoutStopSec=0
Restart=always
User=redis
Group=redis

# Security settings
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/falkordb /var/log/falkordb

[Install]
WantedBy=multi-user.target
```

### Step 3: Deploy Production Configuration

```bash
# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable falkordb
sudo systemctl start falkordb

# Verify service status
sudo systemctl status falkordb

# Check logs
sudo journalctl -u falkordb -f
```

### Step 4: Production Verification

```bash
# Connect with authentication
redis-cli -a your_secure_password_here

# Verify persistence configuration
redis-cli -a your_secure_password_here CONFIG GET "*persist*"
redis-cli -a your_secure_password_here CONFIG GET "*aof*"

# Test FalkorDB functionality
redis-cli -a your_secure_password_here GRAPH.QUERY proddb "CREATE (:Product {name: 'Widget', price: 29.99})"

# Verify module configuration
redis-cli -a your_secure_password_here GRAPH.CONFIG GET *
```

## Phase 3: Docker Production Deployment

### Step 1: Docker Compose Configuration

Create `docker-compose.prod.yml`:

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
      - falkordb_logs:/var/log/falkordb
      - ./config/redis-prod.conf:/etc/redis/redis.conf:ro
    environment:
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    command: redis-server /etc/redis/redis.conf
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "3"

  falkordb-exporter:
    image: oliver006/redis_exporter:latest
    container_name: falkordb-exporter
    restart: unless-stopped
    ports:
      - "9121:9121"
    environment:
      - REDIS_ADDR=redis://falkordb:6379
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    depends_on:
      - falkordb

volumes:
  falkordb_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /opt/falkordb/data
  falkordb_logs:
    driver: local

networks:
  default:
    name: falkordb-network
```

### Step 2: Environment Configuration

Create `.env` file:

```bash
# FalkorDB Production Environment
REDIS_PASSWORD=your_very_secure_password_here
COMPOSE_PROJECT_NAME=falkordb-prod
```

### Step 3: Deploy with Docker Compose

```bash
# Create data directories
sudo mkdir -p /opt/falkordb/data
sudo chown -R 999:999 /opt/falkordb/data

# Deploy stack
docker-compose -f docker-compose.prod.yml up -d

# Verify deployment
docker-compose -f docker-compose.prod.yml ps
docker-compose -f docker-compose.prod.yml logs falkordb
```

## Phase 4: Kubernetes Production Deployment

### Step 1: Namespace and Storage

```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: falkordb-prod

---
# storage-class.yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: falkordb-ssd
  namespace: falkordb-prod
provisioner: kubernetes.io/gce-pd
parameters:
  type: pd-ssd
  replication-type: regional-pd
allowVolumeExpansion: true
```

### Step 2: ConfigMap and Secrets

```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: falkordb-config
  namespace: falkordb-prod
data:
  redis.conf: |
    loadmodule /FalkorDB/bin/src/falkordb.so THREAD_COUNT 8 CACHE_SIZE 200
    appendonly yes
    appendfsync everysec
    save 900 1
    save 300 10
    save 60 10000
    maxmemory-policy allkeys-lru
    requirepass ${REDIS_PASSWORD}

---
# secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: falkordb-secret
  namespace: falkordb-prod
type: Opaque
data:
  redis-password: <base64-encoded-password>
```

### Step 3: StatefulSet Deployment

```yaml
# statefulset.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: falkordb
  namespace: falkordb-prod
spec:
  serviceName: falkordb-headless
  replicas: 1
  selector:
    matchLabels:
      app: falkordb
  template:
    metadata:
      labels:
        app: falkordb
    spec:
      containers:
      - name: falkordb
        image: falkordb/falkordb:latest
        ports:
        - containerPort: 6379
          name: redis
        env:
        - name: REDIS_PASSWORD
          valueFrom:
            secretKeyRef:
              name: falkordb-secret
              key: redis-password
        volumeMounts:
        - name: data
          mountPath: /var/lib/falkordb/data
        - name: config
          mountPath: /etc/redis/redis.conf
          subPath: redis.conf
        livenessProbe:
          exec:
            command:
            - redis-cli
            - -a
            - $(REDIS_PASSWORD)
            - ping
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          exec:
            command:
            - redis-cli
            - -a
            - $(REDIS_PASSWORD)
            - ping
          initialDelaySeconds: 5
          periodSeconds: 5
      volumes:
      - name: config
        configMap:
          name: falkordb-config
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: falkordb-ssd
      resources:
        requests:
          storage: 100Gi
```

### Step 4: Services and Monitoring

```yaml
# service.yaml
apiVersion: v1
kind: Service
metadata:
  name: falkordb
  namespace: falkordb-prod
spec:
  selector:
    app: falkordb
  ports:
  - port: 6379
    targetPort: 6379
    name: redis
  type: ClusterIP

---
# headless-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: falkordb-headless
  namespace: falkordb-prod
spec:
  selector:
    app: falkordb
  ports:
  - port: 6379
    targetPort: 6379
  clusterIP: None
```

### Step 5: Deploy to Kubernetes

```bash
# Apply configurations
kubectl apply -f namespace.yaml
kubectl apply -f storage-class.yaml
kubectl apply -f configmap.yaml
kubectl apply -f secret.yaml
kubectl apply -f statefulset.yaml
kubectl apply -f service.yaml

# Verify deployment
kubectl get pods -n falkordb-prod
kubectl get pvc -n falkordb-prod
kubectl logs -f statefulset/falkordb -n falkordb-prod

# Test connectivity
kubectl port-forward svc/falkordb 6379:6379 -n falkordb-prod
redis-cli -a your_password ping
```

## Implementation Validation

### Comprehensive Testing Script

```bash
#!/bin/bash
# validate-implementation.sh

REDIS_PASSWORD="your_password"
REDIS_CLI="redis-cli -a $REDIS_PASSWORD"

echo "=== FalkorDB Implementation Validation ==="

# Test 1: Basic connectivity
echo "1. Testing connectivity..."
if $REDIS_CLI ping | grep -q PONG; then
  echo "✓ Connection successful"
else
  echo "✗ Connection failed"
  exit 1
fi

# Test 2: Module verification
echo "2. Verifying FalkorDB module..."
if $REDIS_CLI MODULE LIST | grep -q falkor; then
  echo "✓ FalkorDB module loaded"
else
  echo "✗ FalkorDB module not found"
  exit 1
fi

# Test 3: Persistence configuration
echo "3. Checking persistence configuration..."
AOF_STATUS=$($REDIS_CLI CONFIG GET appendonly | tail -1)
if [ "$AOF_STATUS" = "yes" ]; then
  echo "✓ AOF persistence enabled"
else
  echo "✗ AOF persistence disabled"
fi

# Test 4: Graph operations
echo "4. Testing graph operations..."
$REDIS_CLI GRAPH.QUERY validation "CREATE (:Test {id: 1, timestamp: timestamp()})" > /dev/null
if [ $? -eq 0 ]; then
  echo "✓ Graph creation successful"
  $REDIS_CLI GRAPH.QUERY validation "MATCH (n:Test) DELETE n" > /dev/null
else
  echo "✗ Graph operations failed"
  exit 1
fi

# Test 5: Persistence verification
echo "5. Testing data persistence..."
$REDIS_CLI GRAPH.QUERY persist_test "CREATE (:PersistTest {value: 'test_data'})" > /dev/null
$REDIS_CLI BGSAVE > /dev/null
echo "   Data created and saved. Restart FalkorDB and run this script again to verify persistence."

echo -e "\n✓ Implementation validation completed successfully"
```

---

**Next**: See [06-backup-recovery-procedures.md](06-backup-recovery-procedures.md) for backup and recovery procedures.

