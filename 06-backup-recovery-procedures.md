# FalkorDB Backup and Recovery Procedures

## Overview

This document provides comprehensive backup and recovery procedures for FalkorDB deployments, covering both automated and manual processes for different deployment scenarios.

> Graphiti context: Schedule daily/weekly FalkorDB backups aligned with Graphiti content ingestion windows to minimize snapshot contention. Store backups in our Graphiti S3 bucket with lifecycle rules. Do not back up transient Redis caches used by Graphiti services.


## Backup Strategies

### 1. Automated Daily Backups

#### Production Backup Script

```bash
#!/bin/bash
# /opt/scripts/falkordb-backup.sh

# Configuration
BACKUP_BASE_DIR="/backup/falkordb"
REDIS_DATA_DIR="/var/lib/falkordb/data"
REDIS_PASSWORD="your_secure_password"
REDIS_CLI="redis-cli -a $REDIS_PASSWORD"
RETENTION_DAYS=7
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_BASE_DIR/$DATE"

# Logging
LOG_FILE="/var/log/falkordb-backup.log"
exec 1> >(tee -a "$LOG_FILE")
exec 2>&1

echo "=== FalkorDB Backup Started: $(date) ==="

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Function to log and exit on error
error_exit() {
    echo "ERROR: $1" >&2
    exit 1
}

# Check Redis connectivity
$REDIS_CLI ping > /dev/null || error_exit "Cannot connect to Redis"

# Disable AOF auto-rewrite during backup
echo "Disabling AOF auto-rewrite..."
ORIGINAL_REWRITE_PERCENTAGE=$($REDIS_CLI CONFIG GET auto-aof-rewrite-percentage | tail -1)
$REDIS_CLI CONFIG SET auto-aof-rewrite-percentage 0

# Wait for any ongoing AOF rewrite to complete
echo "Waiting for AOF rewrite to complete..."
while [ "$($REDIS_CLI INFO persistence | grep aof_rewrite_in_progress:1)" ]; do
    echo "  AOF rewrite in progress, waiting..."
    sleep 5
done

# Trigger RDB snapshot
echo "Creating RDB snapshot..."
$REDIS_CLI BGSAVE

# Wait for RDB save to complete
while [ "$($REDIS_CLI LASTSAVE)" = "$($REDIS_CLI LASTSAVE)" ]; do
    sleep 1
done

# Copy persistence files
echo "Copying persistence files..."
if [ -f "$REDIS_DATA_DIR/dump.rdb" ]; then
    cp "$REDIS_DATA_DIR/dump.rdb" "$BACKUP_DIR/" || error_exit "Failed to copy RDB file"
    echo "✓ RDB file backed up"
fi

if [ -f "$REDIS_DATA_DIR/appendonly.aof" ]; then
    cp "$REDIS_DATA_DIR/appendonly.aof" "$BACKUP_DIR/" || error_exit "Failed to copy AOF file"

# Graphiti storage: Push `${DATE}.tar.gz` to the Graphiti S3 bucket (s3://graphiti-backups/falkordb/) using server-side encryption and a 30–90 day lifecycle. Tag backups with commit SHA/build ID from the Graphiti deployment pipeline.

    echo "✓ AOF file backed up"
fi

# Copy configuration files
if [ -f "/etc/falkordb/redis.conf" ]; then
    cp "/etc/falkordb/redis.conf" "$BACKUP_DIR/" || error_exit "Failed to copy config file"
    echo "✓ Configuration file backed up"
fi

# Re-enable AOF auto-rewrite
echo "Re-enabling AOF auto-rewrite..."
$REDIS_CLI CONFIG SET auto-aof-rewrite-percentage "$ORIGINAL_REWRITE_PERCENTAGE"

# Create backup metadata
cat > "$BACKUP_DIR/backup_info.txt" << EOF
Backup Date: $(date)
Redis Version: $($REDIS_CLI INFO server | grep redis_version | cut -d: -f2 | tr -d '\r')
FalkorDB Module: $($REDIS_CLI MODULE LIST | grep falkor)
Database Size: $($REDIS_CLI DBSIZE)
Memory Usage: $($REDIS_CLI INFO memory | grep used_memory_human | cut -d: -f2 | tr -d '\r')
Persistence Info:
$($REDIS_CLI INFO persistence)
EOF

# Compress backup
echo "Compressing backup..."
cd "$BACKUP_BASE_DIR"
tar -czf "${DATE}.tar.gz" "$DATE/"
rm -rf "$DATE/"

# Cleanup old backups
echo "Cleaning up old backups..."
find "$BACKUP_BASE_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete

# Verify backup
if [ -f "$BACKUP_BASE_DIR/${DATE}.tar.gz" ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_BASE_DIR/${DATE}.tar.gz" | cut -f1)
    echo "✓ Backup completed successfully: ${DATE}.tar.gz ($BACKUP_SIZE)"
else
    error_exit "Backup file not found"
fi

echo "=== FalkorDB Backup Completed: $(date) ==="
```

#### Cron Configuration

```bash
# Add to crontab for automated backups
# Daily backup at 2:00 AM
0 2 * * * /opt/scripts/falkordb-backup.sh

# Weekly full backup at 1:00 AM on Sundays
0 1 * * 0 /opt/scripts/falkordb-backup.sh

# Verify cron job
crontab -l | grep falkordb
```

### 2. Docker Backup Procedures

#### Docker Volume Backup

```bash
#!/bin/bash
# docker-backup.sh

CONTAINER_NAME="falkordb-prod"
BACKUP_DIR="/backup/falkordb-docker/$(date +%Y%m%d_%H%M%S)"
REDIS_PASSWORD="your_password"

mkdir -p "$BACKUP_DIR"

# Stop writes and create consistent backup
docker exec $CONTAINER_NAME redis-cli -a $REDIS_PASSWORD CONFIG SET auto-aof-rewrite-percentage 0
docker exec $CONTAINER_NAME redis-cli -a $REDIS_PASSWORD BGSAVE

# Wait for save to complete
while [ "$(docker exec $CONTAINER_NAME redis-cli -a $REDIS_PASSWORD LASTSAVE)" = "$(docker exec $CONTAINER_NAME redis-cli -a $REDIS_PASSWORD LASTSAVE)" ]; do
    sleep 1
done

# Create volume backup
docker run --rm \
    -v falkordb_data:/source:ro \
    -v "$BACKUP_DIR":/backup \
    alpine tar -czf /backup/falkordb_data.tar.gz -C /source .

# Re-enable AOF rewrite
docker exec $CONTAINER_NAME redis-cli -a $REDIS_PASSWORD CONFIG SET auto-aof-rewrite-percentage 100

echo "Docker backup completed: $BACKUP_DIR/falkordb_data.tar.gz"
```

### 3. Kubernetes Backup Procedures

#### Volume Snapshot Backup

```yaml
# volume-snapshot.yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: falkordb-snapshot-$(date +%Y%m%d-%H%M%S)
  namespace: falkordb-prod
spec:
  volumeSnapshotClassName: csi-gce-pd-snapshot-class
  source:
    persistentVolumeClaimName: data-falkordb-0
```

```bash
# Create snapshot
kubectl apply -f volume-snapshot.yaml

# Verify snapshot
kubectl get volumesnapshot -n falkordb-prod
```

#### Kubernetes Backup Job

```yaml
# backup-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: falkordb-backup-$(date +%Y%m%d-%H%M%S)
  namespace: falkordb-prod
spec:
  template:
    spec:
      containers:
      - name: backup
        image: alpine:latest
        command:
        - /bin/sh
        - -c
        - |
          apk add --no-cache redis
          redis-cli -h falkordb -a $REDIS_PASSWORD BGSAVE
          sleep 10
          tar -czf /backup/falkordb-$(date +%Y%m%d-%H%M%S).tar.gz -C /data .
        env:
        - name: REDIS_PASSWORD
          valueFrom:
            secretKeyRef:
              name: falkordb-secret
              key: redis-password
        volumeMounts:
        - name: data
          mountPath: /data
        - name: backup-storage
          mountPath: /backup
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: data-falkordb-0
      - name: backup-storage
        persistentVolumeClaim:
          claimName: backup-storage
      restartPolicy: OnFailure
```

## Recovery Procedures

### 1. Complete System Recovery

#### Recovery from RDB Backup

```bash
#!/bin/bash
# recover-from-rdb.sh

BACKUP_FILE="/backup/falkordb/20240824_020000.tar.gz"
REDIS_DATA_DIR="/var/lib/falkordb/data"
REDIS_SERVICE="falkordb"

echo "=== FalkorDB Recovery from RDB ==="

# Stop FalkorDB service
echo "Stopping FalkorDB service..."
sudo systemctl stop $REDIS_SERVICE

# Backup current data (if any)
if [ -d "$REDIS_DATA_DIR" ]; then
    echo "Backing up current data..."
    sudo mv "$REDIS_DATA_DIR" "${REDIS_DATA_DIR}.backup.$(date +%Y%m%d_%H%M%S)"
fi

# Create data directory
sudo mkdir -p "$REDIS_DATA_DIR"

# Extract backup
echo "Extracting backup..."
cd /tmp
tar -xzf "$BACKUP_FILE"
BACKUP_DIR=$(tar -tzf "$BACKUP_FILE" | head -1 | cut -f1 -d"/")

# Copy RDB file
if [ -f "/tmp/$BACKUP_DIR/dump.rdb" ]; then
    sudo cp "/tmp/$BACKUP_DIR/dump.rdb" "$REDIS_DATA_DIR/"
    echo "✓ RDB file restored"
else
    echo "✗ RDB file not found in backup"
    exit 1
fi

# Copy configuration if available
if [ -f "/tmp/$BACKUP_DIR/redis.conf" ]; then
    sudo cp "/tmp/$BACKUP_DIR/redis.conf" "/etc/falkordb/"
    echo "✓ Configuration restored"
fi

# Set proper permissions
sudo chown -R redis:redis "$REDIS_DATA_DIR"
sudo chown -R redis:redis "/etc/falkordb"

# Start FalkorDB service
echo "Starting FalkorDB service..."
sudo systemctl start $REDIS_SERVICE

# Wait for service to start
sleep 10

# Verify recovery
echo "Verifying recovery..."
redis-cli -a your_password ping
if [ $? -eq 0 ]; then
    echo "✓ FalkorDB service started successfully"
    redis-cli -a your_password INFO keyspace
else
    echo "✗ FalkorDB service failed to start"
    exit 1
fi

# Cleanup
rm -rf "/tmp/$BACKUP_DIR"

echo "=== Recovery completed successfully ==="
```

#### Recovery from AOF Backup

```bash
#!/bin/bash
# recover-from-aof.sh

BACKUP_FILE="/backup/falkordb/20240824_020000.tar.gz"
REDIS_DATA_DIR="/var/lib/falkordb/data"
REDIS_SERVICE="falkordb"

echo "=== FalkorDB Recovery from AOF ==="

# Stop service
sudo systemctl stop $REDIS_SERVICE

# Backup current data
if [ -d "$REDIS_DATA_DIR" ]; then
    sudo mv "$REDIS_DATA_DIR" "${REDIS_DATA_DIR}.backup.$(date +%Y%m%d_%H%M%S)"
fi

# Create data directory
sudo mkdir -p "$REDIS_DATA_DIR"

# Extract and restore AOF
cd /tmp
tar -xzf "$BACKUP_FILE"
BACKUP_DIR=$(tar -tzf "$BACKUP_FILE" | head -1 | cut -f1 -d"/")

if [ -f "/tmp/$BACKUP_DIR/appendonly.aof" ]; then
    sudo cp "/tmp/$BACKUP_DIR/appendonly.aof" "$REDIS_DATA_DIR/"
    echo "✓ AOF file restored"
else
    echo "✗ AOF file not found in backup"
    exit 1
fi

# Set permissions and start service
sudo chown -R redis:redis "$REDIS_DATA_DIR"
sudo systemctl start $REDIS_SERVICE

# Monitor AOF loading
echo "Monitoring AOF replay..."
tail -f /var/log/falkordb/falkordb.log | grep -E "(Loading|loaded|AOF)" &
TAIL_PID=$!

# Wait for service to be ready
while ! redis-cli -a your_password ping > /dev/null 2>&1; do
    echo "Waiting for AOF replay to complete..."
    sleep 5
done

kill $TAIL_PID
echo "✓ AOF replay completed successfully"

# Cleanup
rm -rf "/tmp/$BACKUP_DIR"

echo "=== Recovery completed successfully ==="
```

### 2. Docker Recovery Procedures

#### Docker Volume Recovery

```bash
#!/bin/bash
# docker-recovery.sh

BACKUP_FILE="/backup/falkordb-docker/20240824_020000/falkordb_data.tar.gz"
CONTAINER_NAME="falkordb-prod"

echo "=== Docker FalkorDB Recovery ==="

# Stop container
docker stop $CONTAINER_NAME

# Remove existing volume (backup first if needed)
docker volume create falkordb_data_backup
docker run --rm -v falkordb_data:/source -v falkordb_data_backup:/backup alpine cp -a /source/. /backup/

# Remove and recreate volume
docker volume rm falkordb_data
docker volume create falkordb_data

# Restore from backup
docker run --rm \
    -v falkordb_data:/target \
    -v "$(dirname $BACKUP_FILE)":/backup \
    alpine tar -xzf "/backup/$(basename $BACKUP_FILE)" -C /target

# Start container
docker start $CONTAINER_NAME

# Verify recovery
sleep 10
docker exec $CONTAINER_NAME redis-cli -a your_password ping

echo "✓ Docker recovery completed successfully"
```

### 3. Point-in-Time Recovery

#### AOF Point-in-Time Recovery

```bash
#!/bin/bash
# point-in-time-recovery.sh

TARGET_TIMESTAMP="2024-08-24 14:30:00"
AOF_FILE="/var/lib/falkordb/data/appendonly.aof"
RECOVERY_AOF="/tmp/recovery_appendonly.aof"

echo "=== Point-in-Time Recovery to $TARGET_TIMESTAMP ==="

# Convert timestamp to Unix time
TARGET_UNIX=$(date -d "$TARGET_TIMESTAMP" +%s)

# Parse AOF file and extract commands up to target time
python3 << EOF
import re
import time

target_time = $TARGET_UNIX
output_file = "$RECOVERY_AOF"

with open("$AOF_FILE", 'r') as infile, open(output_file, 'w') as outfile:
    current_time = 0
    buffer = []

    for line in infile:
        buffer.append(line)

        # Look for timestamp commands
        if 'timestamp()' in line.lower():
            # Extract timestamp and compare
            # This is a simplified example - actual implementation
            # would need more sophisticated AOF parsing
            pass

        # Write commands that occurred before target time
        if current_time <= target_time:
            outfile.writelines(buffer)
            buffer = []

print(f"Point-in-time AOF created: {output_file}")
EOF

# Stop Redis and replace AOF file
sudo systemctl stop falkordb
sudo cp "$RECOVERY_AOF" "$AOF_FILE"
sudo chown redis:redis "$AOF_FILE"
sudo systemctl start falkordb

echo "✓ Point-in-time recovery completed"
```

## Disaster Recovery Testing

### Recovery Testing Script

```bash
#!/bin/bash
# test-recovery.sh

TEST_BACKUP="/backup/falkordb/test_backup.tar.gz"
TEST_DATA_DIR="/tmp/falkordb_test"
REDIS_PASSWORD="your_password"

echo "=== Disaster Recovery Test ==="

# Create test environment
mkdir -p "$TEST_DATA_DIR"

# Extract test backup
cd /tmp
tar -xzf "$TEST_BACKUP"
BACKUP_DIR=$(tar -tzf "$TEST_BACKUP" | head -1 | cut -f1 -d"/")

# Start test Redis instance
redis-server --port 6380 --dir "$TEST_DATA_DIR" --dbfilename dump.rdb --daemonize yes

# Copy backup data
cp "/tmp/$BACKUP_DIR/dump.rdb" "$TEST_DATA_DIR/"

# Restart test instance to load data
redis-cli -p 6380 SHUTDOWN
redis-server --port 6380 --dir "$TEST_DATA_DIR" --dbfilename dump.rdb --daemonize yes

# Verify data integrity
sleep 5
RECORD_COUNT=$(redis-cli -p 6380 DBSIZE)
echo "Recovered records: $RECORD_COUNT"

# Cleanup
redis-cli -p 6380 SHUTDOWN
rm -rf "$TEST_DATA_DIR" "/tmp/$BACKUP_DIR"

echo "✓ Recovery test completed successfully"
```

## Backup Monitoring and Alerting

### Backup Verification Script

```bash
#!/bin/bash
# verify-backup.sh

BACKUP_DIR="/backup/falkordb"
ALERT_EMAIL="admin@company.com"
MAX_BACKUP_AGE_HOURS=25

# Check for recent backups
LATEST_BACKUP=$(find "$BACKUP_DIR" -name "*.tar.gz" -mtime -1 | head -1)

if [ -z "$LATEST_BACKUP" ]; then
    echo "ERROR: No recent backup found" | mail -s "FalkorDB Backup Alert" $ALERT_EMAIL
    exit 1
fi

# Verify backup integrity
if tar -tzf "$LATEST_BACKUP" > /dev/null 2>&1; then
    echo "✓ Backup integrity verified: $(basename $LATEST_BACKUP)"
else
    echo "ERROR: Backup corruption detected" | mail -s "FalkorDB Backup Alert" $ALERT_EMAIL
    exit 1
fi

# Check backup age
BACKUP_AGE_HOURS=$(( ($(date +%s) - $(stat -c %Y "$LATEST_BACKUP")) / 3600 ))
if [ $BACKUP_AGE_HOURS -gt $MAX_BACKUP_AGE_HOURS ]; then
    echo "WARNING: Backup is $BACKUP_AGE_HOURS hours old" | mail -s "FalkorDB Backup Alert" $ALERT_EMAIL
fi

echo "✓ Backup verification completed successfully"
```

---

**Next**: See [07-monitoring-alerting.md](07-monitoring-alerting.md) for monitoring and alerting setup.
