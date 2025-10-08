# Redis and FalkorDB Persistence Configuration Reference
> Graphiti context: Use these parameters for the FalkorDB datastore. For Graphiti’s auxiliary Redis caches, default to persistence disabled (save "" and appendonly no). Align THREAD_COUNT and CACHE_SIZE with Graphiti’s query concurrency (API + batch jobs) and memory budget. See recommendations inline below.


## Redis Persistence Configuration Parameters

### RDB (Snapshot) Configuration

#### Core RDB Parameters

```redis
# Save points: save <seconds> <changes>
save 900 1          # Save if ≥1 key changed in 900 seconds
save 300 10         # Save if ≥10 keys changed in 300 seconds
save 60 10000       # Save if ≥10000 keys changed in 60 seconds
save ""             # Disable RDB snapshots

# RDB file settings
dbfilename dump.rdb                    # RDB filename
dir /var/lib/redis/                   # Data directory
rdbcompression yes                    # Enable RDB compression
rdbchecksum yes                       # Enable RDB checksums
```

#### Advanced RDB Parameters

```redis
# RDB save behavior
stop-writes-on-bgsave-error yes       # Stop writes if RDB save fails
rdb-del-sync-files no                 # Keep RDB files after replication

# Memory optimization
rdb-save-incremental-fsync yes        # Incremental fsync during RDB save
```

### AOF (Append-Only File) Configuration

#### Core AOF Parameters

```redis
# Enable AOF
appendonly yes                        # Enable AOF persistence
appendfilename "appendonly.aof"       # AOF filename

# Fsync policy
appendfsync everysec                  # Recommended: fsync every second
# appendfsync always                  # Fsync after every write (safest)
# appendfsync no                      # OS-controlled fsync (fastest)

# Directory settings (Redis 7.0+)
appenddirname "appendonlydir"         # AOF directory name
```

#### AOF Rewrite Configuration

```redis
# Auto-rewrite settings
auto-aof-rewrite-percentage 100       # Trigger rewrite when AOF grows 100%
auto-aof-rewrite-min-size 64mb        # Minimum size before rewrite
aof-rewrite-incremental-fsync yes     # Incremental fsync during rewrite

# AOF loading behavior
aof-load-truncated yes                # Load truncated AOF files
aof-use-rdb-preamble yes             # Use RDB format in AOF rewrites
```

#### AOF Error Handling

```redis
# Error handling
no-appendfsync-on-rewrite no          # Continue fsync during rewrite
aof-timestamp-enabled no              # Disable AOF timestamps
```

### Hybrid Configuration Examples

#### Production Recommended

```redis
# Hybrid persistence for production
appendonly yes
appendfsync everysec
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb

save 900 1
save 300 10
save 60 10000

dbfilename dump.rdb
dir /var/lib/redis/
rdbcompression yes
rdbchecksum yes
```

#### High-Availability Configuration

```redis
# High-availability setup
appendonly yes
appendfsync everysec
auto-aof-rewrite-percentage 50        # More frequent rewrites
auto-aof-rewrite-min-size 32mb        # Smaller rewrite threshold

save 300 1                           # More frequent snapshots
save 60 10
save 10 1000

rdbcompression yes
rdbchecksum yes
aof-use-rdb-preamble yes
```

#### Performance-Optimized Configuration

```redis
# Performance-optimized (some durability trade-off)
appendonly yes
appendfsync everysec

# Graphiti recommendation: For FalkorDB, prefer `maxmemory-policy noeviction` to avoid data loss under memory pressure. Use `allkeys-lru` only for Redis caches. Set `maxmemory` to ~70-80% of container/host RAM to leave headroom for forked BGSAVE/BGREWRITEAOF.

auto-aof-rewrite-percentage 200       # Less frequent rewrites
auto-aof-rewrite-min-size 128mb       # Larger rewrite threshold

save 900 1                           # Less frequent snapshots
save 300 100

rdbcompression no                     # Disable compression for speed
no-appendfsync-on-rewrite yes        # Skip fsync during rewrite
```

## FalkorDB Module Configuration

### Module Loading

```redis
# Load FalkorDB module with parameters
loadmodule /FalkorDB/bin/src/falkordb.so THREAD_COUNT 4 CACHE_SIZE 100

# Alternative: Load via command line
redis-server --loadmodule ./falkordb.so THREAD_COUNT 4 CACHE_SIZE 100
```

### FalkorDB Configuration Parameters

#### Core Parameters

| Parameter | Description | Default | Range | Runtime Configurable |
|-----------|-------------|---------|-------|---------------------|
| `THREAD_COUNT` | Number of query execution threads | 8 | 1-64 | No |
| `OMP_THREAD_COUNT` | OpenMP threads per query | 8 | 1-64 | No |
| `CACHE_SIZE` | Query cache size | 25 | 0-∞ | Yes |
| `TIMEOUT_DEFAULT` | Default query timeout (ms) | 0 | 0-∞ | Yes |
| `TIMEOUT_MAX` | Maximum query timeout (ms) | 0 | 0-∞ | Yes |

#### Memory and Performance Parameters

| Parameter | Description | Default | Runtime Configurable |
|-----------|-------------|---------|---------------------|
| `QUERY_MEM_CAPACITY` | Max memory per query (bytes) | 0 (unlimited) | Yes |
| `RESULTSET_SIZE` | Max result set size | -1 (unlimited) | Yes |
| `NODE_CREATION_BUFFER` | Node creation buffer size | 16384 | Yes |
| `MAX_QUEUED_QUERIES` | Max queued queries | UINT64_MAX | Yes |

#### Persistence-Related Parameters

| Parameter | Description | Default | Runtime Configurable |
|-----------|-------------|---------|---------------------|
| `VKEY_MAX_ENTITY_COUNT` | Entities per virtual key | 100000 | Yes |
| `EFFECTS_THRESHOLD` | Replication effects threshold (μs) | 300 | Yes |

### Runtime Configuration Commands

```redis
# Set configuration at runtime
GRAPH.CONFIG SET CACHE_SIZE 200
GRAPH.CONFIG SET TIMEOUT_DEFAULT 30000
GRAPH.CONFIG SET QUERY_MEM_CAPACITY 1073741824  # 1GB

# Get configuration values
GRAPH.CONFIG GET CACHE_SIZE
GRAPH.CONFIG GET *                              # Get all parameters

# Example output:
# 1) "CACHE_SIZE"
# 2) (integer) 200
```

## Environment-Specific Configurations

### Docker Environment Variables

```bash
# Redis configuration via environment
REDIS_ARGS="--appendonly yes --appendfsync everysec --save 900 1"

# FalkorDB configuration via environment
FALKORDB_ARGS="THREAD_COUNT 4 CACHE_SIZE 100 TIMEOUT_DEFAULT 30000"

# Complete Docker run command
docker run -d \
  -e REDIS_ARGS="--appendonly yes --appendfsync everysec --save 900 1 --save 300 10" \
  -e FALKORDB_ARGS="THREAD_COUNT 4 CACHE_SIZE 100" \
  falkordb/falkordb:latest
```

### Kubernetes ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: falkordb-config
data:
  redis.conf: |
    # FalkorDB Redis Configuration
    loadmodule /FalkorDB/bin/src/falkordb.so THREAD_COUNT 4 CACHE_SIZE 100
    
    # Persistence
    appendonly yes
    appendfsync everysec
    save 900 1
    save 300 10
    save 60 10000
    
    # Performance
    maxmemory-policy allkeys-lru
    tcp-keepalive 300
    
    # Security
    requirepass ${REDIS_PASSWORD}
    protected-mode yes
```

## Configuration Validation

### Validation Commands

```redis
# Check current configuration
CONFIG GET "*persist*"
CONFIG GET "*aof*"
CONFIG GET "*rdb*"
CONFIG GET "*save*"

# Validate FalkorDB module
MODULE LIST
GRAPH.CONFIG GET *

# Test persistence functionality
BGSAVE
BGREWRITEAOF
INFO persistence
```

### Configuration Testing Script

```bash
#!/bin/bash
# validate-config.sh

REDIS_CLI="redis-cli"

echo "=== Redis Configuration Validation ==="

# Check persistence settings
echo "Persistence Configuration:"
$REDIS_CLI CONFIG GET appendonly
$REDIS_CLI CONFIG GET appendfsync
$REDIS_CLI CONFIG GET save

# Check FalkorDB module
echo -e "\nFalkorDB Module Status:"
MODULE_STATUS=$($REDIS_CLI MODULE LIST | grep -i falkor)
if [ -n "$MODULE_STATUS" ]; then
  echo "✓ FalkorDB module loaded"
  $REDIS_CLI GRAPH.CONFIG GET THREAD_COUNT
  $REDIS_CLI GRAPH.CONFIG GET CACHE_SIZE
else
  echo "✗ FalkorDB module not loaded"
  exit 1
fi

# Test basic functionality
echo -e "\nFunctionality Test:"
$REDIS_CLI GRAPH.QUERY test "CREATE (:ConfigTest {timestamp: timestamp()})" > /dev/null
if [ $? -eq 0 ]; then
  echo "✓ Graph operations working"
  $REDIS_CLI GRAPH.QUERY test "MATCH (n:ConfigTest) DELETE n" > /dev/null
else
  echo "✗ Graph operations failed"
  exit 1
fi

echo -e "\n✓ Configuration validation completed successfully"
```

## Performance Tuning Guidelines

### Memory-Optimized Configuration

```redis
# For memory-constrained environments
appendonly yes
appendfsync everysec
auto-aof-rewrite-percentage 50        # More aggressive rewriting
auto-aof-rewrite-min-size 32mb

save 900 1                           # Minimal RDB snapshots
rdbcompression yes                   # Enable compression

# FalkorDB settings
CACHE_SIZE 50                        # Smaller cache
QUERY_MEM_CAPACITY 536870912         # 512MB limit per query
```

### High-Throughput Configuration

```redis
# For high-throughput workloads
appendonly yes
appendfsync everysec
auto-aof-rewrite-percentage 200       # Less frequent rewrites
no-appendfsync-on-rewrite yes         # Skip fsync during rewrite

save 1800 1                          # Less frequent snapshots
save 600 100

# FalkorDB settings
THREAD_COUNT 8                       # More threads
CACHE_SIZE 200                       # Larger cache
MAX_QUEUED_QUERIES 10000            # Higher queue limit
```

### Low-Latency Configuration

```redis
# For latency-sensitive applications
appendonly yes
appendfsync everysec
aof-rewrite-incremental-fsync yes

save 300 1                           # Frequent small snapshots
rdb-save-incremental-fsync yes

# FalkorDB settings
TIMEOUT_DEFAULT 5000                 # 5-second timeout
RESULTSET_SIZE 1000                  # Limit result sizes
```

## Configuration Migration

### Upgrading from RDB-only to Hybrid

```redis
# Current RDB-only configuration
save 900 1
save 300 10
save 60 10000

# Add AOF configuration
CONFIG SET appendonly yes
CONFIG SET appendfsync everysec
CONFIG REWRITE

# Verify configuration
CONFIG GET appendonly
CONFIG GET appendfsync
```

### Migrating Between AOF Policies

```redis
# Change from 'always' to 'everysec'
CONFIG SET appendfsync everysec
CONFIG REWRITE

# Monitor performance impact
INFO persistence
INFO stats
```

---

**Next**: See [05-implementation-guide.md](05-implementation-guide.md) for step-by-step implementation instructions.

