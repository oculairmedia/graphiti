# Performance Tuning Guide

## Current Bottlenecks (400 RPS is too low!)

### 1. Connection Pool Size (CRITICAL)
**Problem**: Only 32 connections configured
**Fix**: Increase to 200-500

```bash
# Change in Docker/environment:
MAX_CONNECTIONS=200  # Was 32
```

### 2. Add Caching Layer (90% speedup)
**Problem**: Every request hits FalkorDB
**Fix**: Add Redis caching

```rust
// In search handlers, add:
let cache_key = format!("search:{}:{}", query, limit);
if let Some(cached) = redis.get(&cache_key).await? {
    return Ok(serde_json::from_str(&cached)?);
}
// ... do search ...
redis.setex(&cache_key, 300, &json_result).await?;
```

### 3. FalkorDB Connection Multiplexing
**Problem**: FalkorDB is single-threaded
**Fix**: Use pipelining and multiple FalkorDB instances

```rust
// Use pipeline for batch operations
let pipe = redis::pipe()
    .cmd("GRAPH.QUERY").arg(&graph).arg(&query1)
    .cmd("GRAPH.QUERY").arg(&graph).arg(&query2)
    .query_async(&mut conn).await?;
```

### 4. Increase Worker Threads
**Problem**: Default workers = CPU cores (probably 4)
**Fix**: Configure more workers

```rust
// In main.rs, if using actix-web:
HttpServer::new(app)
    .workers(32)  // Increase from default
    .bind(addr)?
    .run()

// For tokio runtime:
tokio::runtime::Builder::new_multi_thread()
    .worker_threads(32)
    .enable_all()
    .build()?
```

## Expected Performance After Fixes

| Component | Before | After | Impact |
|-----------|--------|-------|--------|
| Connection Pool | 32 | 200 | 6x capacity |
| Cache Hit Rate | 0% | 90% | 10x for cached |
| Worker Threads | 4 | 32 | 8x concurrency |
| FalkorDB Queries | Serial | Pipelined | 2-3x throughput |

**Expected RPS: 4,000-6,000** (10-15x improvement)

## Quick Test Commands

```bash
# Test with wrk
wrk -t12 -c400 -d30s --latency \
  -s search_test.lua \
  http://localhost:3004/search

# Test with ab
ab -n 10000 -c 100 -T application/json \
  -p search_payload.json \
  http://localhost:3004/search

# Monitor connection pool usage
redis-cli -p 6379 CLIENT LIST | wc -l

# Monitor FalkorDB slow queries
redis-cli -p 6379 GRAPH.SLOWLOG GET
```

## Architecture for 10,000+ RPS

### Option 1: Horizontal Scaling
```
Load Balancer (nginx/HAProxy)
    ├── Rust Service 1 (200 connections)
    ├── Rust Service 2 (200 connections)
    └── Rust Service 3 (200 connections)
         └── Shared Redis Cache
              └── FalkorDB Cluster
```

### Option 2: Add Read Replicas
```
Writes → FalkorDB Primary
Reads  → FalkorDB Replica 1
      → FalkorDB Replica 2
      → FalkorDB Replica 3
```

### Option 3: Switch to DragonflyDB
- Drop-in Redis replacement
- Multi-threaded (uses all CPU cores)
- 25x faster than Redis
- Same protocol, just change connection string

## Monitoring Metrics to Track

1. **Connection pool saturation**
   ```rust
   let stats = pool.status();
   metrics.gauge("pool.available", stats.available);
   metrics.gauge("pool.waiting", stats.waiting);
   ```

2. **Cache hit rate**
   ```rust
   metrics.increment("cache.hit") or metrics.increment("cache.miss")
   ```

3. **Query latency percentiles**
   ```rust
   metrics.histogram("query.latency", elapsed_ms);
   // Track p50, p95, p99
   ```

4. **FalkorDB slow queries**
   ```bash
   redis-cli GRAPH.SLOWLOG GET
   ```