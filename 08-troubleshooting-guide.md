# FalkorDB Persistence Troubleshooting Guide

## Common Persistence Issues
> Graphiti context: When investigating issues, correlate persistence events with Graphiti ingestion schedules and API traffic patterns. Prioritize keeping production read paths (Graphiti API) available while recovering write paths (ingestion/ETL) if contention arises.



### 1. AOF File Corruption

#### Symptoms
- Redis fails to start with AOF loading errors
- Error messages like "Bad file format reading the append only file"
- Incomplete data after restart

#### Diagnosis
```bash
# Check AOF file integrity
redis-check-aof /var/lib/falkordb/data/appendonly.aof

# Example output for corrupted file:
# AOF analyzed, error found at position 12345
# This will fix the AOF file. Continue? (y/N)
```

#### Resolution
```bash
# Method 1: Automatic repair (may lose some data)
redis-check-aof --fix /var/lib/falkordb/data/appendonly.aof

# Method 2: Manual truncation
# 1. Stop FalkorDB
sudo systemctl stop falkordb

# 2. Backup corrupted AOF
cp /var/lib/falkordb/data/appendonly.aof /backup/corrupted_aof_$(date +%Y%m%d_%H%M%S).aof

# 3. Truncate at corruption point
head -c 12345 /var/lib/falkordb/data/appendonly.aof > /tmp/truncated.aof
mv /tmp/truncated.aof /var/lib/falkordb/data/appendonly.aof

# 4. Start FalkorDB
sudo systemctl start falkordb

# 5. Verify data integrity
redis-cli -a your_password GRAPH.QUERY testdb "MATCH (n) RETURN count(n)"
```

#### Prevention
```bash
# Enable AOF file checksums (Redis 7.0+)
CONFIG SET aof-timestamp-enabled yes

# Regular AOF integrity checks
#!/bin/bash
# aof-check.sh
if ! redis-check-aof /var/lib/falkordb/data/appendonly.aof; then
    echo "AOF corruption detected" | mail -s "FalkorDB Alert" admin@company.com
fi
```

### 2. RDB Save Failures

#### Symptoms
- Background save failures in logs
- `rdb_last_bgsave_status` shows "err"
- No recent RDB files created

#### Diagnosis
```bash
# Check RDB save status
redis-cli -a your_password INFO persistence | grep rdb_last_bgsave_status

# Check disk space
df -h /var/lib/falkordb/data

# Check permissions
ls -la /var/lib/falkordb/data/

# Check system logs
journalctl -u falkordb | grep -i "save\|rdb"
```

#### Common Causes and Solutions

##### Insufficient Disk Space
```bash
# Check available space
df -h /var/lib/falkordb/data

# Solution: Clean up old files or expand storage
# Remove old backup files
find /backup -name "*.rdb" -mtime +30 -delete

# Or expand volume (example for LVM)
lvextend -L +10G /dev/vg0/falkordb-data
resize2fs /dev/vg0/falkordb-data
```

##### Permission Issues
```bash
# Fix ownership
sudo chown -R redis:redis /var/lib/falkordb/data

# Fix permissions
sudo chmod 755 /var/lib/falkordb/data
sudo chmod 644 /var/lib/falkordb/data/*.rdb
```

##### Memory Issues (Fork Failure)
```bash
# Check memory usage
redis-cli -a your_password INFO memory

# Check system memory
free -h

# Solutions:
# 1. Increase system memory
# 2. Reduce Redis memory usage
redis-cli -a your_password CONFIG SET maxmemory 4gb

# Graphiti ops tip: If AOF rewrites hurt API latency, temporarily set `no-appendfsync-on-rewrite yes` and schedule a manual BGREWRITEAOF during a maintenance window.

redis-cli -a your_password CONFIG SET maxmemory-policy allkeys-lru

# 3. Disable transparent huge pages
echo never > /sys/kernel/mm/transparent_hugepage/enabled
```

### 3. AOF Rewrite Issues

#### Symptoms
- AOF file growing too large
- AOF rewrite operations failing
- High disk I/O during rewrite

#### Diagnosis
```bash
# Check AOF rewrite status
redis-cli -a your_password INFO persistence | grep -E "aof_rewrite|aof_current_size"

# Monitor rewrite process
watch "redis-cli -a your_password INFO persistence | grep aof_rewrite"
```

#### Solutions

##### Manual AOF Rewrite
```bash
# Trigger manual rewrite
redis-cli -a your_password BGREWRITEAOF

# Monitor progress
redis-cli -a your_password INFO persistence | grep aof_rewrite_in_progress
```

##### Adjust Rewrite Thresholds
```bash
# More aggressive rewriting
redis-cli -a your_password CONFIG SET auto-aof-rewrite-percentage 50
redis-cli -a your_password CONFIG SET auto-aof-rewrite-min-size 32mb

# Less aggressive rewriting (for high-write workloads)
redis-cli -a your_password CONFIG SET auto-aof-rewrite-percentage 200
redis-cli -a your_password CONFIG SET auto-aof-rewrite-min-size 128mb
```

##### Disable Fsync During Rewrite
```bash
# Reduce I/O contention during rewrite
redis-cli -a your_password CONFIG SET no-appendfsync-on-rewrite yes
```

### 4. FalkorDB Module Loading Issues

#### Symptoms
- FalkorDB commands not available
- Module not listed in `MODULE LIST`
- Graph operations fail

#### Diagnosis
```bash
# Check if module is loaded
redis-cli -a your_password MODULE LIST | grep -i falkor

# Check Redis logs for module loading errors
journalctl -u falkordb | grep -i "module\|falkor"

# Verify module file exists
ls -la /FalkorDB/bin/src/falkordb.so
```

#### Solutions

##### Module Path Issues
```bash
# Verify correct module path in configuration
grep -i "loadmodule" /etc/falkordb/redis.conf

# Update configuration with correct path
loadmodule /usr/lib/redis/modules/falkordb.so

# Or use absolute path
loadmodule /FalkorDB/bin/src/falkordb.so THREAD_COUNT 4
```

##### Module Dependencies
```bash
# Check for missing dependencies
ldd /FalkorDB/bin/src/falkordb.so

# Install missing dependencies (Ubuntu/Debian)
sudo apt-get install libgomp1 libblas3 liblapack3

# Install missing dependencies (CentOS/RHEL)
sudo yum install libgomp openblas-devel lapack-devel
```

##### Module Version Compatibility
```bash
# Check Redis version
redis-cli -a your_password INFO server | grep redis_version

# Ensure FalkorDB module is compatible
# Download compatible version from FalkorDB releases
wget https://github.com/FalkorDB/FalkorDB/releases/download/v2.12.0/falkordb.so
```

### 5. Performance Issues

#### Symptoms
- Slow graph operations
- High memory usage
- Frequent AOF rewrites

#### Diagnosis
```bash
# Check performance metrics
redis-cli -a your_password INFO stats | grep -E "ops_per_sec|keyspace"
redis-cli -a your_password INFO memory | grep used_memory_human

# Check FalkorDB configuration
redis-cli -a your_password GRAPH.CONFIG GET *

# Monitor slow queries
redis-cli -a your_password CONFIG SET slowlog-log-slower-than 10000
redis-cli -a your_password SLOWLOG GET 10
```

#### Solutions

##### Optimize FalkorDB Configuration
```bash
# Increase thread count for better parallelism
redis-cli -a your_password GRAPH.CONFIG SET THREAD_COUNT 8

# Increase cache size
redis-cli -a your_password GRAPH.CONFIG SET CACHE_SIZE 200

# Set query timeouts
redis-cli -a your_password GRAPH.CONFIG SET TIMEOUT_DEFAULT 30000
```

##### Memory Optimization
```bash
# Set memory limits
redis-cli -a your_password CONFIG SET maxmemory 8gb
redis-cli -a your_password CONFIG SET maxmemory-policy allkeys-lru

# Optimize RDB compression
redis-cli -a your_password CONFIG SET rdbcompression yes
```

##### I/O Optimization
```bash
# Adjust AOF fsync policy for better performance
redis-cli -a your_password CONFIG SET appendfsync everysec

# Disable fsync during rewrites
redis-cli -a your_password CONFIG SET no-appendfsync-on-rewrite yes
```

### 6. Data Consistency Issues

#### Symptoms
- Missing data after restart
- Inconsistent query results
- Graph structure corruption

#### Diagnosis
```bash
# Check persistence configuration
redis-cli -a your_password CONFIG GET "*persist*"

# Verify data integrity
redis-cli -a your_password GRAPH.QUERY testdb "MATCH (n) RETURN count(n)"

# Check for persistence errors
redis-cli -a your_password INFO persistence | grep -E "status|error"
```

#### Solutions

##### Enable Hybrid Persistence
```bash
# Ensure both AOF and RDB are enabled
redis-cli -a your_password CONFIG SET appendonly yes
redis-cli -a your_password CONFIG SET save "900 1 300 10 60 10000"
redis-cli -a your_password CONFIG REWRITE
```

##### Verify Backup Integrity
```bash
# Test backup restoration
#!/bin/bash
# test-backup-integrity.sh

BACKUP_FILE="/backup/falkordb/latest.tar.gz"
TEST_DIR="/tmp/falkordb_test"

# Extract backup
mkdir -p "$TEST_DIR"
tar -xzf "$BACKUP_FILE" -C "$TEST_DIR"

# Start test instance
redis-server --port 6380 --dir "$TEST_DIR" --dbfilename dump.rdb --daemonize yes

# Verify data
RECORD_COUNT=$(redis-cli -p 6380 DBSIZE)
echo "Backup contains $RECORD_COUNT records"

# Cleanup
redis-cli -p 6380 SHUTDOWN
rm -rf "$TEST_DIR"
```

## Diagnostic Tools and Scripts

### 1. Comprehensive Health Check

```bash
#!/bin/bash
# comprehensive-health-check.sh

REDIS_PASSWORD="your_password"
REDIS_CLI="redis-cli -a $REDIS_PASSWORD"
ISSUES_FOUND=0

echo "=== FalkorDB Comprehensive Health Check ==="

# Function to report issues
report_issue() {
    echo "❌ ISSUE: $1"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
}

report_ok() {
    echo "✅ OK: $1"
}

# Check 1: Basic connectivity
if $REDIS_CLI ping > /dev/null 2>&1; then
    report_ok "Redis connectivity"
else
    report_issue "Cannot connect to Redis"
fi

# Check 2: FalkorDB module
if $REDIS_CLI MODULE LIST | grep -q falkor; then
    report_ok "FalkorDB module loaded"
else
    report_issue "FalkorDB module not loaded"
fi

# Check 3: Persistence configuration
AOF_ENABLED=$($REDIS_CLI CONFIG GET appendonly | tail -1)
if [ "$AOF_ENABLED" = "yes" ]; then
    report_ok "AOF persistence enabled"
else
    report_issue "AOF persistence disabled"
fi

# Check 4: Persistence status
RDB_STATUS=$($REDIS_CLI INFO persistence | grep rdb_last_bgsave_status | cut -d: -f2 | tr -d '\r')
if [ "$RDB_STATUS" = "ok" ]; then
    report_ok "RDB save status"
else
    report_issue "RDB save failed: $RDB_STATUS"
fi

AOF_STATUS=$($REDIS_CLI INFO persistence | grep aof_last_write_status | cut -d: -f2 | tr -d '\r')
if [ "$AOF_STATUS" = "ok" ]; then
    report_ok "AOF write status"
else
    report_issue "AOF write failed: $AOF_STATUS"
fi

# Check 5: Disk space
DISK_USAGE=$(df /var/lib/falkordb/data | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -lt 85 ]; then
    report_ok "Disk space usage: ${DISK_USAGE}%"
else
    report_issue "High disk usage: ${DISK_USAGE}%"
fi

# Check 6: Memory usage
MEMORY_USAGE=$($REDIS_CLI INFO memory | grep used_memory_human | cut -d: -f2 | tr -d '\r')
MAX_MEMORY=$($REDIS_CLI CONFIG GET maxmemory | tail -1)
if [ "$MAX_MEMORY" != "0" ]; then
    report_ok "Memory limit configured: $MAX_MEMORY"
else
    report_issue "No memory limit set"
fi

# Check 7: File permissions
if [ -r "/var/lib/falkordb/data" ] && [ -w "/var/lib/falkordb/data" ]; then
    report_ok "Data directory permissions"
else
    report_issue "Data directory permission problems"
fi

# Summary
echo -e "\n=== Health Check Summary ==="
if [ $ISSUES_FOUND -eq 0 ]; then
    echo "✅ All checks passed - FalkorDB is healthy"
    exit 0
else
    echo "❌ Found $ISSUES_FOUND issues - requires attention"
    exit 1
fi
```

### 2. Performance Diagnostic Script

```bash
#!/bin/bash
# performance-diagnostic.sh

REDIS_PASSWORD="your_password"
REDIS_CLI="redis-cli -a $REDIS_PASSWORD"

echo "=== FalkorDB Performance Diagnostics ==="

# System metrics
echo "System Information:"
echo "CPU cores: $(nproc)"
echo "Total memory: $(free -h | awk '/^Mem:/ {print $2}')"
echo "Available memory: $(free -h | awk '/^Mem:/ {print $7}')"

# Redis metrics
echo -e "\nRedis Metrics:"
$REDIS_CLI INFO stats | grep -E "instantaneous_ops_per_sec|total_commands_processed"
$REDIS_CLI INFO memory | grep -E "used_memory_human|maxmemory_human"
$REDIS_CLI INFO clients | grep connected_clients

# FalkorDB metrics
echo -e "\nFalkorDB Configuration:"
$REDIS_CLI GRAPH.CONFIG GET THREAD_COUNT
$REDIS_CLI GRAPH.CONFIG GET CACHE_SIZE
$REDIS_CLI GRAPH.CONFIG GET TIMEOUT_DEFAULT

# Persistence metrics
echo -e "\nPersistence Metrics:"
$REDIS_CLI INFO persistence | grep -E "aof_current_size|rdb_changes_since_last_save"

# Slow queries
echo -e "\nSlow Queries (last 10):"
$REDIS_CLI SLOWLOG GET 10
```

### 3. Emergency Recovery Script

```bash
#!/bin/bash
# emergency-recovery.sh

REDIS_PASSWORD="your_password"
BACKUP_DIR="/backup/falkordb"
DATA_DIR="/var/lib/falkordb/data"

echo "=== FalkorDB Emergency Recovery ==="

# Stop FalkorDB
echo "Stopping FalkorDB..."
sudo systemctl stop falkordb

# Backup current state
echo "Backing up current state..."
sudo mv "$DATA_DIR" "${DATA_DIR}.emergency.$(date +%Y%m%d_%H%M%S)"

# Find latest backup
LATEST_BACKUP=$(find "$BACKUP_DIR" -name "*.tar.gz" -type f -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2-)

if [ -z "$LATEST_BACKUP" ]; then
    echo "❌ No backup found in $BACKUP_DIR"
    exit 1
fi

echo "Using backup: $LATEST_BACKUP"

# Restore from backup
sudo mkdir -p "$DATA_DIR"
sudo tar -xzf "$LATEST_BACKUP" -C "$DATA_DIR" --strip-components=1

# Fix permissions
sudo chown -R redis:redis "$DATA_DIR"

# Start FalkorDB
echo "Starting FalkorDB..."
sudo systemctl start falkordb

# Wait and verify
sleep 10
if redis-cli -a "$REDIS_PASSWORD" ping > /dev/null 2>&1; then
    echo "✅ Emergency recovery completed successfully"
    redis-cli -a "$REDIS_PASSWORD" INFO keyspace
else
    echo "❌ Recovery failed - check logs"
    exit 1
fi
```

---

**Next**: See [09-performance-benchmarking.md](09-performance-benchmarking.md) for performance benchmarking considerations.
