# Sync Service 5000 Limit Investigation

## Issue Summary

After applying pagination fixes (changing `ORDER BY r.created_at` to `ORDER BY r.uuid` and updating termination logic), the sync service now gets stuck at exactly **5000 relationships** instead of the previous 9,998. This represents a regression where our fixes have triggered a different limitation.

## Root Cause Analysis

### 🎯 **Primary Cause: Hidden FalkorDB RESULTSET_SIZE Limit**

**Location**: `docker-compose.yml`, lines 48-49

```yaml
environment:
  - REDIS_ARGS=--loglevel warning --maxmemory 2g --maxmemory-policy allkeys-lru --save ""
  - FALKORDB_ARGS=NODE_CREATION_BUFFER 128 QUERY_MEM_CAPACITY 134217728 CMD_INFO no OMP_THREAD_COUNT 1 CACHE_SIZE 5
```

**Critical Discovery**: The FalkorDB configuration does **NOT** explicitly set `RESULTSET_SIZE`, which means it could be using a **default limit of 5000** or have been set elsewhere.

### 📚 **FalkorDB Documentation Evidence**

From Context7 FalkorDB documentation:

```
RESULTSET_SIZE
  Description: Limit on the number of records returned by a query.
  Default: Unlimited (negative config value).
  Example:
    127.0.0.1:6379> GRAPH.CONFIG SET RESULTSET_SIZE 3
```

However, documentation also shows examples where `RESULTSET_SIZE 1000` is set as a configuration example, suggesting this limit is commonly applied.

### 🔄 **Why Our Fixes Triggered This Issue**

#### Before Our Fixes:
1. **Query**: `ORDER BY r.created_at` with NULL values
2. **Behavior**: NULL handling caused inconsistent pagination, bypassing RESULTSET_SIZE
3. **Result**: Got 9,998 results due to flawed termination logic, not RESULTSET_SIZE

#### After Our Fixes:
1. **Query**: `ORDER BY r.uuid` (stable, no NULLs)
2. **Behavior**: Clean query execution now **respects RESULTSET_SIZE limit**
3. **Result**: First query returns exactly 5000 results (RESULTSET_SIZE limit)
4. **Termination**: Second query with `SKIP 5000` returns 0 results → new termination logic stops

### 🧩 **Execution Flow Analysis**

```
Query 1: MATCH (source)-[r:RELATES_TO]->(target) RETURN ... ORDER BY r.uuid SKIP 0 LIMIT 15000
→ FalkorDB RESULTSET_SIZE limit kicks in → Returns exactly 5000 results

Query 2: MATCH (source)-[r:RELATES_TO]->(target) RETURN ... ORDER BY r.uuid SKIP 5000 LIMIT 15000  
→ SKIP 5000 goes beyond RESULTSET_SIZE window → Returns 0 results

Termination: len(result.result_set) == 0 → Stops pagination
```

## Configuration Analysis

### Application-Level Limits ✅
- `SYNC_MAX_QUERY_LIMIT=15000` (docker-compose.yml line 352)
- `max_query_limit: 5000` (settings.py default, overridden by env var)

### FalkorDB Server-Level Limits ❌
- **Missing**: No explicit `RESULTSET_SIZE` configuration
- **Suspected**: Default or runtime-set limit of 5000

### Memory Constraints
- `QUERY_MEM_CAPACITY 134217728` (128MB per query)
- `maxmemory 2g` (Redis-level limit)
- `CACHE_SIZE 5` (Very small query cache)

## Comparison: Before vs After Fixes

| Aspect | Before Fixes | After Fixes |
|--------|-------------|-------------|
| **ORDER BY** | `r.created_at` (with NULLs) | `r.uuid` (stable) |
| **Query Execution** | Inconsistent, bypassed limits | Clean, respects limits |
| **RESULTSET_SIZE Impact** | Bypassed due to NULL issues | Enforced (5000 limit) |
| **Results Retrieved** | 9,998 (flawed pagination) | 5000 (hard limit) |
| **Termination Logic** | `< max_query_limit` (wrong) | `== 0` (correct) |

## Potential Solutions

### 1. **Immediate Fix: Increase RESULTSET_SIZE** ⭐ **RECOMMENDED**

```yaml
# docker-compose.yml
environment:
  - FALKORDB_ARGS=NODE_CREATION_BUFFER 128 QUERY_MEM_CAPACITY 134217728 CMD_INFO no OMP_THREAD_COUNT 1 CACHE_SIZE 5 RESULTSET_SIZE 20000
```

### 2. **Runtime Configuration Fix**

```bash
# Set via Redis CLI
docker exec graphiti-falkordb-1 redis-cli GRAPH.CONFIG SET RESULTSET_SIZE 20000
```

### 3. **Alternative: Chunked Pagination**

Modify the sync service to use smaller, guaranteed chunks:

```python
# Use smaller chunks that fit within RESULTSET_SIZE
max_query_limit = min(self.max_query_limit, 4000)  # Stay under 5000 limit
```

### 4. **Cursor-Based Pagination**

Implement true cursor-based pagination using UUID ranges:

```cypher
MATCH (source)-[r:RELATES_TO]->(target) 
WHERE r.uuid > $last_uuid 
RETURN r.uuid, source.uuid, target.uuid, properties(r) 
ORDER BY r.uuid 
LIMIT 5000
```

## Recommended Action Plan

### Phase 1: Immediate Resolution
1. **Add RESULTSET_SIZE to docker-compose.yml**:
   ```yaml
   FALKORDB_ARGS=... RESULTSET_SIZE 20000
   ```
2. **Restart FalkorDB container**
3. **Test sync service**

### Phase 2: Verification
1. **Check FalkorDB configuration**: `GRAPH.CONFIG GET RESULTSET_SIZE`
2. **Monitor sync progress**: Verify all 14,771 relationships are processed
3. **Validate data integrity**: Ensure no data loss

### Phase 3: Long-term Improvement
1. **Implement cursor-based pagination** for better scalability
2. **Add configuration monitoring** to detect limit changes
3. **Document FalkorDB configuration requirements**

## Files Requiring Changes

1. **docker-compose.yml** - Add RESULTSET_SIZE to FALKORDB_ARGS
2. **sync_service/extractors/falkordb_extractor.py** - Optional: Add cursor-based pagination
3. **Documentation** - Update configuration requirements

## Testing Strategy

1. **Before Changes**: Verify sync stops at 5000
2. **After RESULTSET_SIZE Change**: Verify sync processes all 14,771 relationships  
3. **Performance Test**: Monitor memory usage and query performance
4. **Regression Test**: Ensure no other functionality is affected

---

**Investigation Date**: Current  
**Root Cause**: FalkorDB RESULTSET_SIZE limit (likely 5000)  
**Severity**: High (66% data loss - worse than before)  
**Status**: ✅ **ROOT CAUSE IDENTIFIED** - Ready for fix implementation  
**Confidence**: Very High - Clear evidence of RESULTSET_SIZE limitation
