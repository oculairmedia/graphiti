# Redis Persistence Mechanisms - Comprehensive Overview

## Introduction

Redis provides multiple persistence mechanisms to ensure data durability across server restarts and system failures. Understanding these mechanisms is crucial for implementing robust FalkorDB deployments.

> Graphiti context: Graphiti uses FalkorDB as the primary graph store and may also run a separate Redis instance for caching (e.g., in graphiti-search-rs). Apply the persistence recommendations in this document to the FalkorDB instance only. For cache Redis, prefer persistence disabled (no RDB/AOF) to maximize throughput and reduce I/O.


## Persistence Options

### 1. RDB (Redis Database) Snapshots

RDB creates point-in-time snapshots of your dataset at specified intervals.

#### How RDB Works
- Creates a binary dump of the entire dataset
- Triggered by configurable save points or manual commands
- Uses copy-on-write for minimal performance impact
- Compact binary format for efficient storage

#### RDB Configuration
```redis
# Save points: save <seconds> <changes>
save 900 1      # Save if ≥1 key changed in 900 seconds (15 minutes)
save 300 10     # Save if ≥10 keys changed in 300 seconds (5 minutes)
save 60 10000   # Save if ≥10000 keys changed in 60 seconds (1 minute)

# RDB file configuration
dbfilename dump.rdb
dir /var/lib/redis/

# Compression and checksums
rdbcompression yes
rdbchecksum yes
```

#### RDB Commands
```redis
SAVE          # Synchronous save (blocks server)
BGSAVE        # Asynchronous background save
LASTSAVE      # Unix timestamp of last successful save
```

#### RDB Advantages
- **Fast Recovery**: Quick startup from compact binary format
- **Compact Storage**: Efficient disk space usage
- **Low Resource Impact**: Minimal ongoing performance overhead
- **Backup Friendly**: Single file easy to backup and transfer

#### RDB Disadvantages
- **Data Loss Risk**: Potential loss of data between snapshots
- **Memory Spikes**: Fork process can temporarily double memory usage
- **Write Performance**: Periodic performance impact during saves

### 2. AOF (Append-Only File)

AOF logs every write operation received by the server, which can be replayed at startup.

#### How AOF Works
- Appends every write command to a log file
- Replays commands during startup to reconstruct dataset
- Supports automatic log rewriting for size optimization
- Configurable fsync policies for durability vs performance

#### AOF Configuration
```redis
# Enable AOF
appendonly yes
appendfilename "appendonly.aof"

# Fsync policy
appendfsync everysec    # Recommended: fsync every second
# appendfsync always    # Fsync after every write (safest, slowest)
# appendfsync no        # Let OS decide when to fsync (fastest, least safe)

# Auto-rewrite configuration
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb

# AOF directory (Redis 7.0+)
apappenddirname "appendonlydir"
```

#### AOF Commands
```redis
BGREWRITEAOF  # Trigger background AOF rewrite
```

#### AOF Fsync Policies

| Policy | Description | Data Loss Risk | Performance Impact |
|--------|-------------|----------------|-------------------|
| `always` | Fsync after every write | None | High |
| `everysec` | Fsync every second | ≤1 second | Low |
| `no` | OS-controlled fsync | Variable | Minimal |

#### AOF Advantages
- **Better Durability**: Minimal data loss (≤1 second with everysec)
- **Human Readable**: Text format, can be manually inspected/edited
- **Incremental**: Only new operations are appended
- **Corruption Resilient**: Partial corruption doesn't affect entire dataset

#### AOF Disadvantages
- **Larger Files**: Typically larger than equivalent RDB files
- **Slower Recovery**: Must replay all operations during startup
- **Higher Resource Usage**: Ongoing disk I/O and CPU overhead
- **Rewrite Complexity**: Requires periodic rewriting to manage size

### 3. Hybrid Persistence (RDB + AOF)

Combines both RDB and AOF for optimal durability and recovery characteristics.

#### Hybrid Configuration
```redis
# Enable both persistence mechanisms
appendonly yes
appendfsync everysec

save 900 1
save 300 10
save 60 10000

# Hybrid loading preference
aof-use-rdb-preamble yes  # Use RDB format in AOF rewrites
```

#### Hybrid Benefits
- **Fast Recovery**: RDB provides quick baseline restoration
- **Minimal Data Loss**: AOF ensures recent changes are preserved
- **Operational Flexibility**: Multiple recovery options available
- **Backup Redundancy**: Multiple backup formats available

## Persistence Comparison Matrix

| Feature | RDB Only | AOF Only | Hybrid |
|---------|----------|----------|--------|
| **Data Loss Risk** | High | Low | Low |
| **Recovery Speed** | Fast | Slow | Fast |
| **File Size** | Small | Large | Medium |
| **CPU Overhead** | Low | Medium | Medium |
| **Memory Usage** | Low | Medium | Medium |
| **Backup Complexity** | Simple | Medium | Complex |
| **Production Suitability** | Cache only | Good | Excellent |

## Performance Considerations

### Write Performance Impact
```redis
# Benchmark results (approximate)
# Baseline (no persistence): 100,000 ops/sec
# RDB only: 95,000 ops/sec (-5%)
# AOF (everysec): 85,000 ops/sec (-15%)
# AOF (always): 25,000 ops/sec (-75%)
# Hybrid: 80,000 ops/sec (-20%)
```

### Memory Usage Patterns
- **RDB**: Temporary 2x memory during background saves
- **AOF**: Additional buffers for write operations
- **Hybrid**: Combined overhead of both mechanisms

### Disk I/O Patterns
- **RDB**: Periodic large writes during snapshots
- **AOF**: Continuous small writes + periodic rewrites
- **Hybrid**: Combined I/O patterns

## Best Practices

### 1. Configuration Recommendations
```redis
# Production-recommended hybrid setup
appendonly yes

# Graphiti default: Start with `auto-aof-rewrite-percentage 100` and `min-size 64mb`; increase thresholds if ingestion causes frequent rewrites impacting API latency. Schedule heavy rewrites outside peak Graphiti API hours.

appendfsync everysec
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb

save 900 1
save 300 10
save 60 10000

rdbcompression yes
rdbchecksum yes
```

### 2. Monitoring Key Metrics
```redis
INFO persistence
# Key metrics to monitor:
# - rdb_last_save_time
# - rdb_changes_since_last_save
# - aof_enabled
# - aof_rewrite_in_progress
# - aof_last_rewrite_time_sec
```

### 3. Backup Procedures
```bash
# Safe AOF backup procedure
redis-cli CONFIG SET auto-aof-rewrite-percentage 0
redis-cli INFO persistence | grep aof_rewrite_in_progress
# Ensure aof_rewrite_in_progress:0 before copying files
cp /var/lib/redis/appendonly.aof /backup/location/
redis-cli CONFIG SET auto-aof-rewrite-percentage 100
```

## Troubleshooting Common Issues

### AOF Corruption
```bash
# Check and fix AOF corruption
redis-check-aof --fix /var/lib/redis/appendonly.aof
```

### RDB Corruption
```bash
# Check RDB file integrity
redis-check-rdb /var/lib/redis/dump.rdb
```

### Performance Issues
- Monitor `INFO persistence` for rewrite frequency
- Adjust `auto-aof-rewrite-percentage` if rewrites are too frequent
- Consider disk I/O capacity for AOF workloads

## Migration Strategies

### From No Persistence to AOF
```redis
CONFIG SET appendonly yes
CONFIG REWRITE
```

### From RDB to Hybrid
```redis
CONFIG SET appendonly yes
# Keep existing RDB configuration
CONFIG REWRITE
```

### From AOF to Hybrid
```redis
CONFIG SET save "900 1 300 10 60 10000"
CONFIG REWRITE
```

---

**Next**: See [03-falkordb-persistence-guide.md](03-falkordb-persistence-guide.md) for FalkorDB-specific implementation details.

