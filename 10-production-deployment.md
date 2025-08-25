# FalkorDB Production Deployment Guide

## Production Architecture Overview

> Graphiti context: Use this as the baseline for Graphiti’s graph store tier. Connect Graphiti API and ingestion services to the master endpoint for writes and to replicas for read-heavy paths where eventual consistency is acceptable. Keep Graphiti Redis caches (if any) separate from FalkorDB and non-persistent.


### Recommended Production Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Load Balancer                            │
│                  (HAProxy/NGINX)                           │
└─────────────────────┬───────────────────────────────────────┘
                      │
    ┌─────────────────┼─────────────────┐
    │                 │                 │
┌───▼────┐       ┌───▼────┐       ┌───▼────┐
│FalkorDB│       │FalkorDB│       │FalkorDB│
│Master  │◄─────►│Replica │◄─────►│Replica │
│        │       │        │       │        │
└────────┘       └────────┘       └────────┘
    │                 │                 │
┌───▼────┐       ┌───▼────┐       ┌───▼────┐
│Persist │       │Persist │       │Persist │
│Storage │       │Storage │       │Storage │
└────────┘       └────────┘       └────────┘
```

## Infrastructure Requirements

### 1. Hardware Specifications

#### Production Master Node
```yaml
CPU: 16+ cores (Intel Xeon or AMD EPYC)
Memory: 64GB+ RAM
Storage:
  - OS: 100GB SSD
  - Data: 1TB+ NVMe SSD (3000+ IOPS)
  - Backup: 2TB+ for retention
Network: 10Gbps+ with redundancy
```

#### Production Replica Nodes
```yaml
CPU: 8+ cores
Memory: 32GB+ RAM
Storage:
  - OS: 100GB SSD
  - Data: 1TB+ NVMe SSD
Network: 1Gbps+ with redundancy
```

### 2. Storage Configuration

#### Filesystem Recommendations
```bash
# Use XFS for better performance with large files
mkfs.xfs -f /dev/nvme0n1p1

# Mount with optimized options
mount -o noatime,nodiratime,nobarrier /dev/nvme0n1p1 /var/lib/falkordb

# Add to /etc/fstab
echo "/dev/nvme0n1p1 /var/lib/falkordb xfs noatime,nodiratime,nobarrier 0 2" >> /etc/fstab
```

#### LVM Configuration for Flexibility
```bash
# Create LVM setup for easy expansion
pvcreate /dev/nvme0n1
vgcreate falkordb-vg /dev/nvme0n1
lvcreate -L 500G -n data-lv falkordb-vg
lvcreate -L 200G -n backup-lv falkordb-vg

# Format and mount
mkfs.xfs /dev/falkordb-vg/data-lv
mkfs.xfs /dev/falkordb-vg/backup-lv

mkdir -p /var/lib/falkordb/data /var/lib/falkordb/backup
mount /dev/falkordb-vg/data-lv /var/lib/falkordb/data
mount /dev/falkordb-vg/backup-lv /var/lib/falkordb/backup
```

## Production Configuration

### 1. Master Node Configuration

```redis
# /etc/falkordb/redis-master.conf
# FalkorDB Production Master Configuration

# Module loading
loadmodule /FalkorDB/bin/src/falkordb.so THREAD_COUNT 16 CACHE_SIZE 500 TIMEOUT_DEFAULT 30000 QUERY_MEM_CAPACITY 2147483648

# Network configuration
bind 0.0.0.0
port 6379
protected-mode yes
requirepass ${REDIS_MASTER_PASSWORD}
tcp-backlog 511
tcp-keepalive 300

# Graphiti policy: Set maxmemory to 70–80% of node memory and use `noeviction` for FalkorDB. Size replicas for read throughput of Graphiti API and search. Prefer NVMe storage with sustained IOPS.

timeout 0

# Memory management
maxmemory 48gb
maxmemory-policy allkeys-lru
maxmemory-samples 5

# Persistence configuration (Hybrid)
appendonly yes
appendfsync everysec

# Graphiti delta: Our docker-compose.prod.yml currently configures RDB-only (`--save 60 1`) without AOF. Update production to hybrid by adding `--appendonly yes --appendfsync everysec` and ensure the persistent volume includes both dump.rdb and appendonly.aof.

appendfilename "appendonly.aof"
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
aof-use-rdb-preamble yes
aof-rewrite-incremental-fsync yes

# RDB configuration
save 900 1
save 300 10
save 60 10000
dbfilename dump.rdb
rdbcompression yes
rdbchecksum yes
rdb-save-incremental-fsync yes

# Directory configuration
dir /var/lib/falkordb/data

# Logging
loglevel notice
logfile /var/log/falkordb/falkordb-master.log
syslog-enabled yes
syslog-ident falkordb-master

# Security
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command CONFIG "CONFIG_a1b2c3d4e5f6"
rename-command SHUTDOWN "SHUTDOWN_f6e5d4c3b2a1"

# Client management
maxclients 10000

# Slow log
slowlog-log-slower-than 10000
slowlog-max-len 128

# Replication (master settings)
repl-diskless-sync yes
repl-diskless-sync-delay 5
repl-ping-replica-period 10
repl-timeout 60
```

### 2. Replica Node Configuration

```redis
# /etc/falkordb/redis-replica.conf
# FalkorDB Production Replica Configuration

# Module loading
loadmodule /FalkorDB/bin/src/falkordb.so THREAD_COUNT 8 CACHE_SIZE 300

# Network configuration
bind 0.0.0.0
port 6379
protected-mode yes
requirepass ${REDIS_REPLICA_PASSWORD}

# Memory management
maxmemory 24gb
maxmemory-policy allkeys-lru

# Persistence configuration (AOF only for replicas)
appendonly yes
appendfsync everysec
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb

# Replication configuration
replicaof ${MASTER_HOST} 6379
masterauth ${REDIS_MASTER_PASSWORD}
replica-serve-stale-data yes
replica-read-only yes
replica-priority 100

# Directory and logging
dir /var/lib/falkordb/data
logfile /var/log/falkordb/falkordb-replica.log
loglevel notice

# Security (same as master)
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command CONFIG "CONFIG_a1b2c3d4e5f6"
```

## High Availability Setup

### 1. Redis Sentinel Configuration

```redis
# /etc/falkordb/sentinel.conf
# Redis Sentinel for FalkorDB HA

port 26379
bind 0.0.0.0

# Monitor master
sentinel monitor falkordb-master ${MASTER_HOST} 6379 2
sentinel auth-pass falkordb-master ${REDIS_MASTER_PASSWORD}

# Timing configuration
sentinel down-after-milliseconds falkordb-master 5000
sentinel parallel-syncs falkordb-master 1
sentinel failover-timeout falkordb-master 10000

# Notification scripts
sentinel notification-script falkordb-master /opt/scripts/sentinel-notify.sh
sentinel client-reconfig-script falkordb-master /opt/scripts/sentinel-reconfig.sh

# Logging
logfile /var/log/falkordb/sentinel.log
```

### 2. Sentinel Notification Scripts

```bash
#!/bin/bash
# /opt/scripts/sentinel-notify.sh

EVENT_TYPE=$1
INSTANCE_NAME=$2
INSTANCE_HOST=$3
INSTANCE_PORT=$4

case $EVENT_TYPE in
    "+sdown")
        echo "$(date): Master $INSTANCE_NAME is down" | mail -s "FalkorDB Alert" admin@company.com
        ;;
    "+failover-end")
        echo "$(date): Failover completed for $INSTANCE_NAME" | mail -s "FalkorDB Alert" admin@company.com
        ;;
    "+switch-master")
        echo "$(date): Master switched to $INSTANCE_HOST:$INSTANCE_PORT" | mail -s "FalkorDB Alert" admin@company.com
        ;;
esac
```

### 3. Load Balancer Configuration (HAProxy)

```haproxy
# /etc/haproxy/haproxy.cfg
global
    daemon
    maxconn 4096
    log stdout local0

defaults
    mode tcp
    timeout connect 5000ms
    timeout client 50000ms
    timeout server 50000ms
    option tcplog

# FalkorDB Master (writes)
frontend falkordb_master_frontend
    bind *:6380
    default_backend falkordb_master_backend

backend falkordb_master_backend
    balance first
    option tcp-check
    tcp-check send AUTH\ ${REDIS_PASSWORD}\r\n
    tcp-check expect string +OK
    tcp-check send PING\r\n
    tcp-check expect string +PONG
    server master1 ${MASTER_HOST}:6379 check inter 1s

# FalkorDB Replicas (reads)
frontend falkordb_replica_frontend
    bind *:6381
    default_backend falkordb_replica_backend

backend falkordb_replica_backend
    balance roundrobin
    option tcp-check
    tcp-check send AUTH\ ${REDIS_PASSWORD}\r\n
    tcp-check expect string +OK
    tcp-check send PING\r\n
    tcp-check expect string +PONG
    server replica1 ${REPLICA1_HOST}:6379 check inter 1s
    server replica2 ${REPLICA2_HOST}:6379 check inter 1s
```

## Container Orchestration

### 1. Docker Swarm Deployment

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  falkordb-master:
    image: falkordb/falkordb:latest
    hostname: falkordb-master
    environment:
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    volumes:
      - falkordb_master_data:/var/lib/falkordb/data
      - ./config/redis-master.conf:/etc/redis/redis.conf:ro
    ports:
      - "6379:6379"
    command: redis-server /etc/redis/redis.conf
    deploy:
      replicas: 1
      placement:
        constraints:
          - node.role == manager
      resources:
        limits:
          memory: 48G
          cpus: '16'
        reservations:
          memory: 32G
          cpus: '8'
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3

  falkordb-replica:
    image: falkordb/falkordb:latest
    environment:
      - REDIS_PASSWORD=${REDIS_PASSWORD}
      - MASTER_HOST=falkordb-master
    volumes:
      - falkordb_replica_data:/var/lib/falkordb/data
      - ./config/redis-replica.conf:/etc/redis/redis.conf:ro
    command: redis-server /etc/redis/redis.conf
    deploy:
      replicas: 2
      placement:
        constraints:
          - node.role == worker
      resources:
        limits:
          memory: 24G
          cpus: '8'
        reservations:
          memory: 16G
          cpus: '4'
    depends_on:
      - falkordb-master

  sentinel:
    image: redis:7-alpine
    environment:
      - MASTER_HOST=falkordb-master
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    volumes:
      - ./config/sentinel.conf:/etc/redis/sentinel.conf:ro
    command: redis-sentinel /etc/redis/sentinel.conf
    deploy:
      replicas: 3
      placement:
        max_replicas_per_node: 1

volumes:
  falkordb_master_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /opt/falkordb/master/data
  falkordb_replica_data:
    driver: local
```

### 2. Kubernetes Production Deployment

```yaml
# falkordb-production.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: falkordb-prod

---
apiVersion: v1
kind: ConfigMap
metadata:
  name: falkordb-config
  namespace: falkordb-prod
data:
  redis-master.conf: |
    loadmodule /FalkorDB/bin/src/falkordb.so THREAD_COUNT 16 CACHE_SIZE 500
    appendonly yes
    appendfsync everysec
    save 900 1 300 10 60 10000
    maxmemory 48gb
    maxmemory-policy allkeys-lru
    requirepass ${REDIS_PASSWORD}

  redis-replica.conf: |
    loadmodule /FalkorDB/bin/src/falkordb.so THREAD_COUNT 8 CACHE_SIZE 300
    appendonly yes
    appendfsync everysec
    maxmemory 24gb
    maxmemory-policy allkeys-lru
    replicaof falkordb-master 6379
    masterauth ${REDIS_PASSWORD}
    requirepass ${REDIS_PASSWORD}

---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: falkordb-master
  namespace: falkordb-prod
spec:
  serviceName: falkordb-master
  replicas: 1
  selector:
    matchLabels:
      app: falkordb-master
  template:
    metadata:
      labels:
        app: falkordb-master
    spec:
      containers:
      - name: falkordb
        image: falkordb/falkordb:latest
        ports:
        - containerPort: 6379
        env:
        - name: REDIS_PASSWORD
          valueFrom:
            secretKeyRef:
              name: falkordb-secret
              key: password
        volumeMounts:
        - name: data
          mountPath: /var/lib/falkordb/data
        - name: config
          mountPath: /etc/redis/redis.conf
          subPath: redis-master.conf
        resources:
          requests:
            memory: "32Gi"
            cpu: "8"
          limits:
            memory: "48Gi"
            cpu: "16"
        livenessProbe:
          exec:
            command:
            - redis-cli
            - -a
            - $(REDIS_PASSWORD)
            - ping
          initialDelaySeconds: 30
          periodSeconds: 10
      volumes:
      - name: config
        configMap:
          name: falkordb-config
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: fast-ssd
      resources:
        requests:
          storage: 1Ti

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: falkordb-replica
  namespace: falkordb-prod
spec:
  replicas: 2
  selector:
    matchLabels:
      app: falkordb-replica
  template:
    metadata:
      labels:
        app: falkordb-replica
    spec:
      containers:
      - name: falkordb
        image: falkordb/falkordb:latest
        ports:
        - containerPort: 6379
        env:
        - name: REDIS_PASSWORD
          valueFrom:
            secretKeyRef:
              name: falkordb-secret
              key: password
        volumeMounts:
        - name: data
          mountPath: /var/lib/falkordb/data
        - name: config
          mountPath: /etc/redis/redis.conf
          subPath: redis-replica.conf
        resources:
          requests:
            memory: "16Gi"
            cpu: "4"
          limits:
            memory: "24Gi"
            cpu: "8"
      volumes:
      - name: config
        configMap:
          name: falkordb-config
      - name: data
        emptyDir: {}
```

## Security Hardening

### 1. Network Security

```bash
# Firewall configuration (iptables)
# Allow only necessary ports
iptables -A INPUT -p tcp --dport 6379 -s ${TRUSTED_NETWORK} -j ACCEPT
iptables -A INPUT -p tcp --dport 26379 -s ${TRUSTED_NETWORK} -j ACCEPT
iptables -A INPUT -p tcp --dport 6379 -j DROP
iptables -A INPUT -p tcp --dport 26379 -j DROP

# Save rules
iptables-save > /etc/iptables/rules.v4
```

### 2. TLS Configuration

```redis
# Enable TLS in redis.conf
port 0
tls-port 6380
tls-cert-file /etc/ssl/certs/falkordb.crt
tls-key-file /etc/ssl/private/falkordb.key
tls-ca-cert-file /etc/ssl/certs/ca.crt
tls-protocols "TLSv1.2 TLSv1.3"
```

### 3. Authentication and Authorization

```redis
# Strong password policy
requirepass $(openssl rand -base64 32)

# ACL configuration (Redis 6+)
user default off
user falkordb_app on >$(openssl rand -base64 32) ~* &* +@all -flushall -flushdb
user falkordb_readonly on >$(openssl rand -base64 32) ~* +@read -@dangerous
```

## Monitoring and Observability

### 1. Production Monitoring Stack

```yaml
# monitoring-stack.yml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./grafana/datasources:/etc/grafana/provisioning/datasources

  redis-exporter:
    image: oliver006/redis_exporter:latest
    environment:
      - REDIS_ADDR=redis://falkordb-master:6379
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    ports:
      - "9121:9121"

  alertmanager:
    image: prom/alertmanager:latest
    ports:
      - "9093:9093"
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml

volumes:
  prometheus_data:
  grafana_data:
```

### 2. Production Alerting Rules

```yaml
# production-alerts.yml
groups:
  - name: falkordb_production
    rules:
      - alert: FalkorDBDown
        expr: redis_up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "FalkorDB instance is down"

      - alert: FalkorDBHighMemoryUsage
        expr: redis_memory_used_bytes / redis_memory_max_bytes > 0.9
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "FalkorDB memory usage is high"

      - alert: FalkorDBReplicationLag
        expr: redis_master_repl_offset - redis_replica_repl_offset > 1000000
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "FalkorDB replication lag is high"
```

## Operational Procedures

### 1. Deployment Checklist

```markdown
## Pre-Deployment Checklist
- [ ] Hardware specifications verified
- [ ] Storage configured and mounted
- [ ] Network security configured
- [ ] SSL certificates installed
- [ ] Configuration files reviewed
- [ ] Backup procedures tested
- [ ] Monitoring stack deployed
- [ ] Alert rules configured
- [ ] Documentation updated

## Deployment Steps
1. [ ] Deploy master node
2. [ ] Verify master functionality
3. [ ] Deploy replica nodes
4. [ ] Configure replication
5. [ ] Deploy Sentinel (if using)
6. [ ] Configure load balancer
7. [ ] Run health checks
8. [ ] Perform failover test
9. [ ] Load test with production data
10. [ ] Go-live approval

## Post-Deployment Checklist
- [ ] All services running
- [ ] Monitoring active
- [ ] Alerts configured
- [ ] Backup schedule active
- [ ] Documentation complete
- [ ] Team trained on procedures
```

### 2. Maintenance Procedures

```bash
#!/bin/bash
# maintenance-procedures.sh

# Rolling restart procedure
rolling_restart() {
    echo "Starting rolling restart..."

    # Restart replicas first
    for replica in replica1 replica2; do
        echo "Restarting $replica..."
        systemctl restart falkordb@$replica
        sleep 30

        # Verify replica is back online
        redis-cli -h $replica -a $REDIS_PASSWORD ping
    done

    # Restart master last
    echo "Restarting master..."
    systemctl restart falkordb@master
    sleep 30

    # Verify master is back online
    redis-cli -h master -a $REDIS_PASSWORD ping

    echo "Rolling restart completed"
}

# Configuration update procedure
update_config() {
    local config_file=$1

    echo "Updating configuration..."

    # Validate configuration
    redis-server $config_file --test-memory

    if [ $? -eq 0 ]; then
        # Apply to replicas first
        for replica in replica1 replica2; do
            scp $config_file $replica:/etc/falkordb/redis.conf
            systemctl restart falkordb@$replica
        done

        # Apply to master last
        scp $config_file master:/etc/falkordb/redis.conf
        systemctl restart falkordb@master

        echo "Configuration update completed"
    else
        echo "Configuration validation failed"
        exit 1
    fi
}
```

---

This completes the comprehensive FalkorDB persistence documentation set. The 10 documents provide complete coverage of Redis persistence mechanisms, FalkorDB-specific considerations, implementation guides, monitoring, troubleshooting, performance optimization, and production deployment strategies.
