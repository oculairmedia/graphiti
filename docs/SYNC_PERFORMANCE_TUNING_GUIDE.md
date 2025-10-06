# Neo4j → FalkorDB Sync Performance Tuning Guide

## Overview

This guide provides comprehensive tuning parameters to optimize the performance of data synchronization between Neo4j and FalkorDB. The default configuration is conservative for reliability, but can be significantly optimized for speed.

## Current Performance Baseline

**Default Configuration:**
- Migration batch size: 100 nodes/batch
- Sync batch size: 500 items/batch
- Optimization mode: DISABLED
- Neo4j pool size: 10 connections
- FalkorDB pool size: 5 connections

**Estimated Performance:**
- 4000 nodes = 40 batches
- ~2-5 seconds per batch
- **Total time: 80-200 seconds**

## Optimized Performance Target

**Optimized Configuration:**
- Migration batch size: 2000 nodes/batch
- Sync batch size: 2000 items/batch
- Optimization mode: ENABLED
- Neo4j pool size: 20 connections
- FalkorDB pool size: 15 connections

**Expected Performance:**
- 4000 nodes = 2 batches
- ~3-8 seconds per batch
- **Total time: 6-16 seconds**

**Expected Speedup: 5-12x faster** 🚀

---

## Tuning Parameters

### 1. Batch Sizes (BIGGEST IMPACT 💥)

Batch sizes control how many items are processed in a single database transaction.

#### Migration Batch Size
**Environment Variable:** `MIGRATION_BATCH_SIZE`
**Default:** `100`
**Recommended:** `2000` (for speed) or `1000` (balanced)
**Maximum Safe:** `5000`

**Impact:**
- Fewer database round trips
- Reduced query parsing overhead
- Better network utilization
- **Speedup: 5-20x**

**Trade-offs:**
- Larger batches use more memory
- Longer transactions (higher lock contention risk)
- All-or-nothing on failure (entire batch fails)

#### Sync Batch Size
**Environment Variable:** `SYNC_BATCH_SIZE`
**Default:** `500`
**Recommended:** `2000` (for speed) or `1000` (balanced)
**Maximum Safe:** `5000`

**Impact:**
- Similar to migration batch size
- **Speedup: 2-4x**

---

### 2. Optimization Mode (HUGE WIN 🎯)

The sync service has an advanced optimization mode that's currently disabled.

#### Enable Optimization
**Environment Variable:** `SYNC_OPTIMIZATION_ENABLED`
**Default:** `false` (disabled due to FalkorDB Cypher compatibility issues)
**Recommended:** `true` (test first!)

**Why Currently Disabled:**
- Comment in config.yaml: "TEMP: Disable optimization - FalkorDB Cypher incompatible"
- May require testing to verify compatibility with current FalkorDB version

#### Node Batch Size (When Optimization Enabled)
**Environment Variable:** `SYNC_OPTIMIZATION_NODE_BATCH_SIZE`
**Default:** `15000`
**Recommended:** `20000` (for speed) or `15000` (safe)
**Maximum Safe:** `30000`

**Impact:**
- Optimized extraction patterns for nodes
- **Speedup: 2-3x for node processing**

#### Edge Batch Size (When Optimization Enabled)
**Environment Variable:** `SYNC_OPTIMIZATION_EDGE_BATCH_SIZE`
**Default:** `1000` (reduced from 8000 in code comments)
**Recommended:** `5000` (for speed) or `3000` (balanced)
**Maximum Safe:** `20000`

**Impact:**
- Optimized extraction patterns for edges
- **Speedup: 2-5x for edge processing**

#### Memory Threshold
**Environment Variable:** `SYNC_OPTIMIZATION_MEMORY_THRESHOLD_MB`
**Default:** `100`
**Recommended:** `200` (if you have RAM) or `150` (balanced)

**Impact:**
- Adaptive batch sizing based on memory usage
- Prevents OOM errors
- Automatically reduces batch size if memory pressure detected

#### Adaptive Sizing
**Environment Variable:** `SYNC_OPTIMIZATION_ADAPTIVE_SIZING`
**Default:** `true`
**Recommended:** `true` (keep enabled)

**Impact:**
- Dynamically adjusts batch sizes based on performance telemetry
- Learns optimal batch size over time

---

### 3. Connection Pool Sizes (PARALLELISM 🔄)

Connection pools control how many concurrent database operations can run.

#### Neo4j Pool Size
**Environment Variable:** `NEO4J_POOL_SIZE`
**Default:** `10`
**Recommended:** `20` (for speed) or `15` (balanced)
**Maximum Safe:** `50`

**Impact:**
- More concurrent read queries from Neo4j
- Better CPU utilization
- **Speedup: 1.5-2x**

**Trade-offs:**
- More memory per connection
- More load on Neo4j server
- Diminishing returns beyond 20-30

#### FalkorDB Pool Size
**Environment Variable:** `FALKORDB_POOL_SIZE`
**Default:** `5`
**Recommended:** `15` (for speed) or `10` (balanced)
**Maximum Safe:** `30`

**Impact:**
- More concurrent write operations to FalkorDB
- Better throughput
- **Speedup: 1.5-3x**

**Trade-offs:**
- FalkorDB is single-threaded per graph
- Too many connections can cause contention
- Sweet spot is usually 10-20

---

### 4. Sync Behavior (FOR ONE-TIME MIGRATION)

Control how the sync service operates.

#### Continuous Sync
**Environment Variable:** `SYNC_ENABLE_CONTINUOUS`
**Default:** `true`
**Recommended for Migration:** `false` (disable during one-time migration)
**Recommended for Production:** `true` (enable for ongoing sync)

**Impact:**
- Disabling prevents interruptions during migration
- All resources focused on one-time sync

#### Full Sync on Startup
**Environment Variable:** `SYNC_FULL_ON_STARTUP`
**Default:** `false`
**Recommended for Migration:** `true` (do full sync once)
**Recommended for Production:** `false` (use incremental)

#### Incremental Sync
**Environment Variable:** `SYNC_ENABLE_INCREMENTAL`
**Default:** `false`
**Recommended for Migration:** `false` (not needed for one-time)
**Recommended for Production:** `true` (efficient ongoing sync)

#### Sync Direction
**Environment Variable:** `SYNC_DIRECTION`
**Default:** `reverse` (FalkorDB → Neo4j)
**Options:** `forward` (Neo4j → FalkorDB) or `reverse`

**Note:** For Neo4j → FalkorDB migration, use `forward` direction.

---

### 5. Query Limits

Control maximum query sizes and pagination.

#### Max Query Limit
**Environment Variable:** `SYNC_MAX_QUERY_LIMIT`
**Default:** `15000`
**Recommended:** `20000` (for speed) or `15000` (safe)

**Impact:**
- Larger queries fetch more data per request
- Fewer round trips

#### Enable Query Pagination
**Environment Variable:** `SYNC_ENABLE_QUERY_PAGINATION`
**Default:** `true`
**Recommended:** `true` (keep enabled)

**Impact:**
- Prevents memory exhaustion on large datasets
- Allows resumption on failure

---

### 6. Retry Configuration

Control error handling and recovery.

#### Max Retries
**Environment Variable:** `SYNC_MAX_RETRIES`
**Default:** `5`
**Recommended for Speed:** `3` (fail faster)
**Recommended for Reliability:** `5` (more resilient)

#### Retry Delay
**Environment Variable:** `SYNC_RETRY_DELAY_SECONDS`
**Default:** `15`
**Recommended for Speed:** `5` (faster recovery)
**Recommended for Reliability:** `15` (avoid overwhelming services)

---

## Recommended Configurations

### Configuration 1: Maximum Speed (Risky)

**Use Case:** Fast one-time migration, plenty of RAM, low data criticality

```bash
# Batch Sizes
MIGRATION_BATCH_SIZE=5000
SYNC_BATCH_SIZE=5000

# Optimization
SYNC_OPTIMIZATION_ENABLED=true
SYNC_OPTIMIZATION_NODE_BATCH_SIZE=30000
SYNC_OPTIMIZATION_EDGE_BATCH_SIZE=10000
SYNC_OPTIMIZATION_MEMORY_THRESHOLD_MB=500
SYNC_OPTIMIZATION_ADAPTIVE_SIZING=true

# Connection Pools
NEO4J_POOL_SIZE=30
FALKORDB_POOL_SIZE=20

# Sync Behavior
SYNC_ENABLE_CONTINUOUS=false
SYNC_FULL_ON_STARTUP=true
SYNC_ENABLE_INCREMENTAL=false
SYNC_DIRECTION=forward

# Query Limits
SYNC_MAX_QUERY_LIMIT=30000
SYNC_ENABLE_QUERY_PAGINATION=true

# Retries
SYNC_MAX_RETRIES=2
SYNC_RETRY_DELAY_SECONDS=3
```

**Expected Performance:** 10-15x faster than default

---

### Configuration 2: Balanced (Recommended)

**Use Case:** Good speed with safety, production-ready

```bash
# Batch Sizes
MIGRATION_BATCH_SIZE=2000
SYNC_BATCH_SIZE=2000

# Optimization
SYNC_OPTIMIZATION_ENABLED=true
SYNC_OPTIMIZATION_NODE_BATCH_SIZE=20000
SYNC_OPTIMIZATION_EDGE_BATCH_SIZE=5000
SYNC_OPTIMIZATION_MEMORY_THRESHOLD_MB=200
SYNC_OPTIMIZATION_ADAPTIVE_SIZING=true

# Connection Pools
NEO4J_POOL_SIZE=20
FALKORDB_POOL_SIZE=15

# Sync Behavior
SYNC_ENABLE_CONTINUOUS=false
SYNC_FULL_ON_STARTUP=true
SYNC_ENABLE_INCREMENTAL=false
SYNC_DIRECTION=forward

# Query Limits
SYNC_MAX_QUERY_LIMIT=20000
SYNC_ENABLE_QUERY_PAGINATION=true

# Retries
SYNC_MAX_RETRIES=3
SYNC_RETRY_DELAY_SECONDS=5
```

**Expected Performance:** 5-10x faster than default

---

### Configuration 3: Conservative (Safe)

**Use Case:** Limited RAM, critical data, prefer reliability over speed

```bash
# Batch Sizes
MIGRATION_BATCH_SIZE=500
SYNC_BATCH_SIZE=1000

# Optimization
SYNC_OPTIMIZATION_ENABLED=false  # Keep disabled if compatibility issues
SYNC_OPTIMIZATION_NODE_BATCH_SIZE=10000
SYNC_OPTIMIZATION_EDGE_BATCH_SIZE=2000
SYNC_OPTIMIZATION_MEMORY_THRESHOLD_MB=100
SYNC_OPTIMIZATION_ADAPTIVE_SIZING=true

# Connection Pools
NEO4J_POOL_SIZE=10
FALKORDB_POOL_SIZE=8

# Sync Behavior
SYNC_ENABLE_CONTINUOUS=false
SYNC_FULL_ON_STARTUP=true
SYNC_ENABLE_INCREMENTAL=false
SYNC_DIRECTION=forward

# Query Limits
SYNC_MAX_QUERY_LIMIT=10000
SYNC_ENABLE_QUERY_PAGINATION=true

# Retries
SYNC_MAX_RETRIES=5
SYNC_RETRY_DELAY_SECONDS=10
```

**Expected Performance:** 2-3x faster than default

---

## Implementation Steps

### Step 1: Add Environment Variables

Edit your `.env` file and add the desired configuration:

```bash
nano .env
# Add variables from one of the configurations above
```

### Step 2: Rebuild Sync Service

```bash
docker-compose build sync-service
```

### Step 3: Restart Sync Service

```bash
docker-compose up -d sync-service
```

### Step 4: Monitor Progress

```bash
# Watch logs
docker-compose logs -f sync-service

# Check health
curl http://localhost:8082/health

# Check metrics
curl http://localhost:8083/metrics
```

---

## Monitoring and Troubleshooting

### Key Metrics to Watch

1. **Batch Processing Time**
   - Look for: "Processing batch X-Y (Z nodes)"
   - Target: <5 seconds per batch

2. **Memory Usage**
   - Monitor container memory with: `docker stats sync-service`
   - Should stay below memory threshold

3. **Error Rate**
   - Look for: "ERROR" or "Failed" in logs
   - Should be <1% of operations

4. **Total Sync Time**
   - Look for: "Full sync completed in X seconds"
   - Compare to baseline

### Common Issues

#### Issue 1: Out of Memory (OOM)
**Symptoms:** Container crashes, "killed" messages
**Solution:** Reduce batch sizes by 50%, increase memory threshold

#### Issue 2: Connection Timeouts
**Symptoms:** "Connection timeout" errors
**Solution:** Reduce pool sizes, increase retry delay

#### Issue 3: FalkorDB Lock Contention
**Symptoms:** Slow writes, "lock" errors
**Solution:** Reduce FalkorDB pool size to 5-10

#### Issue 4: Optimization Mode Incompatibility
**Symptoms:** Cypher syntax errors when optimization enabled
**Solution:** Set `SYNC_OPTIMIZATION_ENABLED=false`

---

## Advanced Optimization (Future Work)

### 1. Redis Pipelining for FalkorDB Writes

Instead of individual Cypher queries, use Redis pipelining to batch all writes into a single network round trip.

**Expected Speedup:** 3-5x for write operations

**Implementation:** Requires code changes in `sync_service/loaders/falkordb_loader.py`

### 2. Parallel Batch Processing

Process multiple batches concurrently instead of sequentially.

**Expected Speedup:** 2-4x (depending on CPU cores)

**Implementation:** Requires code changes in `sync_service/orchestrator/sync_orchestrator.py`

### 3. Disable Centrality Calculation During Migration

Centrality metrics are expensive to calculate. Skip during migration and calculate once at the end.

**Expected Speedup:** 2-3x

**Implementation:** Add `CALCULATE_CENTRALITY_ON_SYNC=false` flag

### 4. Direct Graph Copy (Bypass Cypher)

Use Neo4j's export and FalkorDB's import commands for bulk data transfer.

**Expected Speedup:** 10-20x

**Implementation:** New migration script using `neo4j-admin export` and FalkorDB bulk loader

---

## Testing Recommendations

### Test Plan

1. **Baseline Test**
   - Run with default configuration
   - Record total time and memory usage

2. **Conservative Test**
   - Apply Configuration 3 (Conservative)
   - Verify 2-3x speedup
   - Check for errors

3. **Balanced Test**
   - Apply Configuration 2 (Balanced)
   - Verify 5-10x speedup
   - Monitor memory usage

4. **Maximum Speed Test**
   - Apply Configuration 1 (Maximum Speed)
   - Verify 10-15x speedup
   - Watch for OOM or errors

5. **Validation**
   - Compare node/edge counts between Neo4j and FalkorDB
   - Spot-check data integrity
   - Verify all properties migrated correctly

### Validation Queries

```cypher
// Neo4j - Count nodes
MATCH (n) RETURN count(n) as total_nodes

// FalkorDB - Count nodes
GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n) as total_nodes"

// Neo4j - Count edges
MATCH ()-[r]->() RETURN count(r) as total_edges

// FalkorDB - Count edges
GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r) as total_edges"
```

---

## References

- **Sync Service Config:** `sync_service/config.yaml`
- **Migration Script:** `sync_service/simple_migration.py`
- **Orchestrator:** `sync_service/orchestrator/sync_orchestrator.py`
- **Settings Schema:** `sync_service/config/settings.py`
- **Best Practices:** `DATABASE_SYNC_OPTIMIZATION_BEST_PRACTICES.md`

---

## Changelog

- **2025-10-04:** Initial documentation created based on codebase analysis

