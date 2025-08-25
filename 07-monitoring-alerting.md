# FalkorDB Persistence Monitoring and Alerting

## Overview

Comprehensive monitoring of FalkorDB persistence mechanisms is crucial for maintaining data integrity and system reliability. This guide covers monitoring strategies, key metrics, alerting configurations, and operational dashboards.

> Graphiti context: Wire these alerts into Graphiti’s existing observability stack (Prometheus + Grafana + Alertmanager). Key SLOs: API P99 latency, ingestion throughput, and FalkorDB persistence health. Alert on AOF rewrite stalls during ingestion windows and on RDB saves overlapping with batch jobs.


## Key Persistence Metrics

### Redis Persistence Metrics

#### RDB Metrics
```redis
# Get RDB persistence information
INFO persistence

# Key RDB metrics:
rdb_changes_since_last_save    # Changes since last RDB save
rdb_bgsave_in_progress        # Background save in progress (0/1)
rdb_last_save_time            # Unix timestamp of last save
rdb_last_bgsave_status        # Status of last background save
rdb_last_bgsave_time_sec      # Duration of last background save
rdb_current_bgsave_time_sec   # Duration of current background save
rdb_last_cow_size             # Copy-on-write memory during last save
```

#### AOF Metrics
```redis
# AOF-specific metrics:
aof_enabled                   # AOF enabled status (0/1)
aof_rewrite_in_progress      # AOF rewrite in progress (0/1)
aof_rewrite_scheduled        # AOF rewrite scheduled (0/1)
aof_last_rewrite_time_sec    # Duration of last AOF rewrite
aof_current_rewrite_time_sec # Duration of current AOF rewrite
aof_last_bgrewrite_status    # Status of last background rewrite
aof_last_write_status        # Status of last write operation
aof_last_cow_size            # Copy-on-write memory during last rewrite
aof_current_size             # Current AOF file size
aof_base_size                # AOF file size at last rewrite
aof_pending_rewrite          # AOF rewrite pending (0/1)
aof_buffer_length            # AOF buffer length
aof_rewrite_buffer_length    # AOF rewrite buffer length
aof_pending_bio_fsync        # Pending background I/O fsync operations
aof_delayed_fsync            # Delayed fsync operations
```

### FalkorDB-Specific Metrics

```redis
# FalkorDB module information
MODULE LIST

# FalkorDB configuration metrics
GRAPH.CONFIG GET *

# Key FalkorDB metrics:
THREAD_COUNT                 # Number of execution threads
CACHE_SIZE                   # Query cache size
TIMEOUT_DEFAULT              # Default query timeout
QUERY_MEM_CAPACITY          # Memory capacity per query
MAX_QUEUED_QUERIES          # Maximum queued queries
```

## Monitoring Implementation

### 1. Prometheus Monitoring Setup

#### Redis Exporter Configuration

```yaml
# docker-compose.monitoring.yml
version: '3.8'

services:
  redis-exporter:
    image: oliver006/redis_exporter:latest
    container_name: falkordb-exporter
    restart: unless-stopped
    ports:
      - "9121:9121"
    environment:
      - REDIS_ADDR=redis://falkordb:6379
      - REDIS_PASSWORD=${REDIS_PASSWORD}
      - REDIS_EXPORTER_INCL_SYSTEM_METRICS=true
    command:
      - '--redis.addr=redis://falkordb:6379'
      - '--redis.password=${REDIS_PASSWORD}'
      - '--include-system-metrics'
      - '--redis-only-metrics'
    depends_on:
      - falkordb

  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    restart: unless-stopped
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'

volumes:
  prometheus_data:
```

#### Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "falkordb_rules.yml"

scrape_configs:
  - job_name: 'falkordb'
    static_configs:
      - targets: ['redis-exporter:9121']
    scrape_interval: 10s
    metrics_path: /metrics

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093
```

### 2. Custom Monitoring Script

```bash
#!/bin/bash
# monitor-falkordb.sh

REDIS_PASSWORD="your_password"
REDIS_CLI="redis-cli -a $REDIS_PASSWORD"
METRICS_FILE="/var/log/falkordb-metrics.log"
ALERT_THRESHOLD_RDB_CHANGES=10000
ALERT_THRESHOLD_AOF_SIZE_MB=1000

# Function to get metric value
get_metric() {
    local metric=$1
    $REDIS_CLI INFO persistence | grep "^$metric:" | cut -d: -f2 | tr -d '\r'
}

# Function to send alert
send_alert() {
    local message=$1
    echo "$(date): ALERT - $message" >> "$METRICS_FILE"
    # Send to monitoring system (e.g., PagerDuty, Slack)
    curl -X POST -H 'Content-type: application/json' \
        --data "{\"text\":\"FalkorDB Alert: $message\"}" \
        "$SLACK_WEBHOOK_URL"
}

# Collect metrics
RDB_CHANGES=$(get_metric "rdb_changes_since_last_save")
RDB_LAST_SAVE=$(get_metric "rdb_last_save_time")
AOF_SIZE=$(get_metric "aof_current_size")
AOF_REWRITE_IN_PROGRESS=$(get_metric "aof_rewrite_in_progress")
RDB_BGSAVE_IN_PROGRESS=$(get_metric "rdb_bgsave_in_progress")

# Convert AOF size to MB
AOF_SIZE_MB=$((AOF_SIZE / 1024 / 1024))

# Log metrics
echo "$(date): RDB_CHANGES=$RDB_CHANGES, AOF_SIZE_MB=$AOF_SIZE_MB, AOF_REWRITE=$AOF_REWRITE_IN_PROGRESS" >> "$METRICS_FILE"

# Check thresholds and alert
if [ "$RDB_CHANGES" -gt "$ALERT_THRESHOLD_RDB_CHANGES" ]; then
    send_alert "High number of RDB changes: $RDB_CHANGES (threshold: $ALERT_THRESHOLD_RDB_CHANGES)"
fi

# Graphiti thresholds: Start with rdb_changes_since_last_save > 50k for 10m (heavy ingestion) and aof_current_size_bytes > 5GiB sustained for 30m. Tune based on Graphiti’s observed ingestion cadence.


if [ "$AOF_SIZE_MB" -gt "$ALERT_THRESHOLD_AOF_SIZE_MB" ]; then
    send_alert "Large AOF file size: ${AOF_SIZE_MB}MB (threshold: ${ALERT_THRESHOLD_AOF_SIZE_MB}MB)"
fi

# Check for persistence failures
RDB_STATUS=$(get_metric "rdb_last_bgsave_status")
AOF_STATUS=$(get_metric "aof_last_write_status")

if [ "$RDB_STATUS" != "ok" ]; then
    send_alert "RDB save failed: $RDB_STATUS"
fi

if [ "$AOF_STATUS" != "ok" ]; then
    send_alert "AOF write failed: $AOF_STATUS"
fi

# Check FalkorDB module status
MODULE_STATUS=$($REDIS_CLI MODULE LIST | grep -i falkor)
if [ -z "$MODULE_STATUS" ]; then
    send_alert "FalkorDB module not loaded"
fi
```

### 3. Grafana Dashboard Configuration

#### Dashboard JSON Configuration

```json
{
  "dashboard": {
    "title": "FalkorDB Persistence Monitoring",
    "panels": [
      {
        "title": "RDB Changes Since Last Save",
        "type": "stat",
        "targets": [
          {
            "expr": "redis_rdb_changes_since_last_save",
            "legendFormat": "Changes"
          }
        ],
        "thresholds": [
          {"color": "green", "value": 0},
          {"color": "yellow", "value": 5000},
          {"color": "red", "value": 10000}
        ]
      },
      {
        "title": "AOF File Size",
        "type": "graph",
        "targets": [
          {
            "expr": "redis_aof_current_size_bytes / 1024 / 1024",
            "legendFormat": "AOF Size (MB)"
          }
        ]
      },
      {
        "title": "Persistence Operations",
        "type": "graph",
        "targets": [
          {
            "expr": "redis_rdb_bgsave_in_progress",
            "legendFormat": "RDB Save In Progress"
          },
          {
            "expr": "redis_aof_rewrite_in_progress",
            "legendFormat": "AOF Rewrite In Progress"
          }
        ]
      },
      {
        "title": "Last Save Times",
        "type": "table",
        "targets": [
          {
            "expr": "redis_rdb_last_save_timestamp_seconds",
            "legendFormat": "Last RDB Save"
          },
          {
            "expr": "redis_aof_last_rewrite_timestamp_seconds",
            "legendFormat": "Last AOF Rewrite"
          }
        ]
      }
    ]
  }
}
```

## Alerting Rules

### 1. Prometheus Alerting Rules

```yaml
# falkordb_rules.yml
groups:
  - name: falkordb_persistence
    rules:
      - alert: FalkorDBHighRDBChanges
        expr: redis_rdb_changes_since_last_save > 10000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High number of RDB changes"
          description: "FalkorDB has {{ $value }} changes since last RDB save"

      - alert: FalkorDBLargeAOFFile
        expr: redis_aof_current_size_bytes / 1024 / 1024 > 1000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Large AOF file size"
          description: "AOF file size is {{ $value }}MB"

      - alert: FalkorDBPersistenceFailure
        expr: redis_rdb_last_bgsave_status != 1 or redis_aof_last_write_status != 1
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Persistence operation failed"
          description: "RDB or AOF operation has failed"

      - alert: FalkorDBModuleDown
        expr: redis_up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "FalkorDB instance down"
          description: "FalkorDB instance is not responding"

      - alert: FalkorDBLongRunningOperation
        expr: redis_rdb_bgsave_in_progress == 1 and redis_rdb_current_bgsave_time_sec > 300
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Long-running RDB save"
          description: "RDB save has been running for {{ $value }} seconds"

      - alert: FalkorDBAOFRewriteStuck
        expr: redis_aof_rewrite_in_progress == 1 and redis_aof_current_rewrite_time_sec > 600
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "AOF rewrite taking too long"
          description: "AOF rewrite has been running for {{ $value }} seconds"
```

### 2. Health Check Script

```bash
#!/bin/bash
# health-check.sh

REDIS_PASSWORD="your_password"
REDIS_CLI="redis-cli -a $REDIS_PASSWORD"
HEALTH_STATUS=0

echo "=== FalkorDB Health Check ==="

# Check Redis connectivity
if ! $REDIS_CLI ping > /dev/null 2>&1; then
    echo "✗ Redis connection failed"
    HEALTH_STATUS=1
else
    echo "✓ Redis connection OK"
fi

# Check FalkorDB module
if ! $REDIS_CLI MODULE LIST | grep -q falkor; then
    echo "✗ FalkorDB module not loaded"
    HEALTH_STATUS=1
else
    echo "✓ FalkorDB module loaded"
fi

# Check persistence configuration
AOF_ENABLED=$($REDIS_CLI CONFIG GET appendonly | tail -1)
if [ "$AOF_ENABLED" != "yes" ]; then
    echo "⚠ AOF persistence disabled"
fi

# Check for persistence errors
RDB_STATUS=$($REDIS_CLI INFO persistence | grep rdb_last_bgsave_status | cut -d: -f2 | tr -d '\r')
AOF_STATUS=$($REDIS_CLI INFO persistence | grep aof_last_write_status | cut -d: -f2 | tr -d '\r')

if [ "$RDB_STATUS" != "ok" ]; then
    echo "✗ RDB save status: $RDB_STATUS"
    HEALTH_STATUS=1
fi

if [ "$AOF_STATUS" != "ok" ]; then
    echo "✗ AOF write status: $AOF_STATUS"
    HEALTH_STATUS=1
fi

# Test graph operations
if $REDIS_CLI GRAPH.QUERY healthcheck "CREATE (:HealthCheck {timestamp: timestamp()})" > /dev/null 2>&1; then
    $REDIS_CLI GRAPH.QUERY healthcheck "MATCH (n:HealthCheck) DELETE n" > /dev/null 2>&1
    echo "✓ Graph operations working"
else
    echo "✗ Graph operations failed"
    HEALTH_STATUS=1
fi

# Check disk space
DISK_USAGE=$(df /var/lib/falkordb/data | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 85 ]; then
    echo "⚠ High disk usage: ${DISK_USAGE}%"
    HEALTH_STATUS=1
fi

if [ $HEALTH_STATUS -eq 0 ]; then
    echo "✓ All health checks passed"
else
    echo "✗ Health check failed"
fi

exit $HEALTH_STATUS
```

## Log Monitoring

### 1. Log Analysis Script

```bash
#!/bin/bash
# analyze-logs.sh

LOG_FILE="/var/log/falkordb/falkordb.log"
ALERT_PATTERNS=(
    "BGSAVE failed"
    "AOF rewrite failed"
    "Disk full"
    "Out of memory"
    "Connection refused"
    "Module loading failed"
)

echo "=== FalkorDB Log Analysis ==="

for pattern in "${ALERT_PATTERNS[@]}"; do
    COUNT=$(grep -c "$pattern" "$LOG_FILE")
    if [ $COUNT -gt 0 ]; then
        echo "⚠ Found $COUNT occurrences of: $pattern"
        grep "$pattern" "$LOG_FILE" | tail -5
    fi
done

# Check for recent errors
echo -e "\nRecent errors (last 24 hours):"
grep -E "(ERROR|WARN)" "$LOG_FILE" | grep "$(date -d '24 hours ago' '+%d %b %Y')" | tail -10
```

### 2. Logrotate Configuration

```bash
# /etc/logrotate.d/falkordb
/var/log/falkordb/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 redis redis
    postrotate
        systemctl reload falkordb > /dev/null 2>&1 || true
    endscript
}
```

## Performance Monitoring

### Key Performance Indicators

```bash
#!/bin/bash
# performance-monitor.sh

REDIS_PASSWORD="your_password"
REDIS_CLI="redis-cli -a $REDIS_PASSWORD"

# Collect performance metrics
MEMORY_USAGE=$($REDIS_CLI INFO memory | grep used_memory_human | cut -d: -f2 | tr -d '\r')
CONNECTED_CLIENTS=$($REDIS_CLI INFO clients | grep connected_clients | cut -d: -f2 | tr -d '\r')
OPS_PER_SEC=$($REDIS_CLI INFO stats | grep instantaneous_ops_per_sec | cut -d: -f2 | tr -d '\r')
KEYSPACE_HITS=$($REDIS_CLI INFO stats | grep keyspace_hits | cut -d: -f2 | tr -d '\r')
KEYSPACE_MISSES=$($REDIS_CLI INFO stats | grep keyspace_misses | cut -d: -f2 | tr -d '\r')

# Calculate hit ratio
if [ "$KEYSPACE_MISSES" -gt 0 ]; then
    HIT_RATIO=$(echo "scale=2; $KEYSPACE_HITS / ($KEYSPACE_HITS + $KEYSPACE_MISSES) * 100" | bc)
else
    HIT_RATIO="100.00"
fi

echo "Performance Metrics:"
echo "Memory Usage: $MEMORY_USAGE"
echo "Connected Clients: $CONNECTED_CLIENTS"
echo "Operations/sec: $OPS_PER_SEC"
echo "Hit Ratio: ${HIT_RATIO}%"

# FalkorDB-specific metrics
CACHE_SIZE=$($REDIS_CLI GRAPH.CONFIG GET CACHE_SIZE | tail -1)
THREAD_COUNT=$($REDIS_CLI GRAPH.CONFIG GET THREAD_COUNT | tail -1)

echo "FalkorDB Cache Size: $CACHE_SIZE"
echo "FalkorDB Thread Count: $THREAD_COUNT"
```

## Automated Monitoring Deployment

### Monitoring Stack Deployment

```bash
#!/bin/bash
# deploy-monitoring.sh

MONITORING_DIR="/opt/falkordb-monitoring"

# Create monitoring directory structure
mkdir -p "$MONITORING_DIR"/{prometheus,grafana,alertmanager}

# Deploy Prometheus configuration
cat > "$MONITORING_DIR/prometheus/prometheus.yml" << 'EOF'
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'falkordb'
    static_configs:
      - targets: ['localhost:9121']
EOF

# Deploy monitoring stack
docker-compose -f docker-compose.monitoring.yml up -d

# Wait for services to start
sleep 30

# Import Grafana dashboard
curl -X POST \
  http://admin:admin@localhost:3000/api/dashboards/db \
  -H 'Content-Type: application/json' \
  -d @falkordb-dashboard.json

echo "✓ Monitoring stack deployed successfully"
echo "Grafana: http://localhost:3000 (admin/admin)"
echo "Prometheus: http://localhost:9090"
```

---

**Next**: See [08-troubleshooting-guide.md](08-troubleshooting-guide.md) for troubleshooting common persistence issues.
