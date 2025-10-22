# Post-Mortem: FalkorDB Data Loss - October 22, 2025

## Summary

**Incident**: Complete FalkorDB data loss (24,321 nodes → 0 nodes)
**Time**: ~18:06 - 22:07 (multiple OOM events throughout the day)
**Impact**: All graph data lost from in-memory cache, requiring full re-sync from Neo4j
**Root Cause**: Out-of-Memory (OOM) kills and segmentation faults in FalkorDB container

## Timeline

### Throughout the Day (Multiple Events)
- **01:21:04** - First OOM kill: redis-server process killed (2031MB used, 2GB limit)
- **02:52:43** - Segmentation fault in falkordb.so (segfault at 0x7d8)
- **11:14:17** - Another segfault in falkordb.so (segfault at 0x12378)
- **11:25:55** - graph-visualizer-rust OOM killed (2GB RSS)
- **16:09:18** - Second FalkorDB OOM kill (2031MB used, 2GB limit)
- **18:05:55** - graph-visualizer-rust OOM killed again
- **18:06:43** - Third FalkorDB OOM kill (2032MB used, 2GB limit)
- **22:07:53** - FalkorDB container restarted (4th restart, clean state)
- **22:14+** - Rust-sync service began re-populating from Neo4j

## Root Causes

### 1. **Memory Limit Too Low (Primary Cause)**

**Evidence**:
```
Memory cgroup out of memory: Killed process 3313652 (redis-server)
total-vm:4310228kB, anon-rss:2022688kB (2GB)
UID:0 pgtables:6740kB oom_score_adj:0
```

**Configuration**:
```yaml
falkordb:
  mem_limit: 2g
  environment:
    - REDIS_ARGS=--maxmemory 2g --maxmemory-policy allkeys-lru
```

**Problem**: With 24,321 nodes and 71,362 edges (including large embeddings), FalkorDB exceeded the 2GB memory limit and was killed by the kernel OOM killer.

### 2. **Segmentation Faults in FalkorDB**

**Evidence**:
```
thread-pool-rea[899795]: segfault at 12378 ip 00007f04699d239d
sp 00007f045f95ccf8 error 4 in falkordb.so
```

**Potential Causes**:
- Corrupt graph data structure
- Race condition in multi-threaded query execution
- Bug in FalkorDB graph module
- Invalid memory access during vector operations

### 3. **Worker Ingestion Errors (Exacerbating Factor)**

The worker was experiencing multiple critical errors that may have contributed to graph corruption:

```
name 'os' is not defined - 100% failure rate on all episodes
dictionary update sequence errors - data corruption
context overflow errors - malformed prompts
message role alternation errors - invalid LLM calls
```

**Impact**: These errors may have caused invalid graph mutations that corrupted FalkorDB's internal state, leading to segfaults.

### 4. **Design Choice: No Persistent Storage**

FalkorDB is intentionally configured **without persistent volumes**:
```yaml
# No volumes - FalkorDB runs in-memory only, restored from Neo4j on startup
```

**Rationale**: FalkorDB persistence/recovery can crash the entire system, so it's treated as ephemeral cache.

**Consequence**: Every container restart = complete data loss.

## Why the Worker Didn't Cause the Wipe Directly

**Investigation Results**:
- ✅ No `GRAPH.DELETE` commands found in worker logs
- ✅ No `FLUSHDB`/`FLUSHALL` commands issued
- ✅ No explicit graph deletion operations
- ❌ Worker errors DID exist but didn't directly delete data

**Conclusion**: The worker's errors may have corrupted graph state leading to segfaults, but the OOM killer performed the actual wipe.

## Contributing Factors

### Worker Error Cascade
1. Missing `import os` caused 100% episode failure rate
2. Malformed LLM responses caused entity extraction crashes
3. Context overflow from uncapped edge prompts
4. These errors may have created invalid graph states

### Memory Pressure
1. 24K+ nodes with 2560-dimension embeddings = ~250MB just for node embeddings
2. 71K+ edges with large fact embeddings = ~500MB+
3. Graph indexes and metadata = ~200MB
4. Total: **~1GB of graph data + Redis overhead exceeded 2GB limit**

### Concurrent Pressure
- graph-visualizer-rust also OOM killed twice (2GB RSS each time)
- Multiple services competing for memory on the same host

## Prevention Measures

### Immediate Actions (Required)

1. **Increase FalkorDB Memory Limit**
```yaml
falkordb:
  mem_limit: 8g  # Increased from 2g
  environment:
    - REDIS_ARGS=--maxmemory 6g --maxmemory-policy allkeys-lru
```

2. **Fix Worker Errors** (Already in progress)
- [x] Add missing `import os` (commit 4133251)
- [x] Fix entity extraction robustness
- [x] Add prompt clipping to edge extraction
- [x] Fix embedding type conversion
- [ ] Monitor for stability

3. **Add Memory Monitoring**
```yaml
falkordb:
  deploy:
    resources:
      reservations:
        memory: 4g
      limits:
        memory: 8g
```

### Medium-Term Actions (Recommended)

4. **Implement FalkorDB Health Monitoring**
- Add memory usage alerts at 75% threshold
- Monitor for segfaults in container logs
- Auto-restart with backoff on repeated OOM kills

5. **Reduce Graph Memory Footprint**
- Consider using smaller embedding dimensions (1024 instead of 2560)
- Implement embedding quantization for FalkorDB storage
- Use sparse embeddings where possible

6. **Graceful Degradation**
- Implement read-only fallback mode when memory is high
- Automatic eviction of least-recently-used subgraphs
- Warn users when approaching memory limits

### Long-Term Actions (Future)

7. **Investigate FalkorDB Segfaults**
- Report segfault stack traces to FalkorDB maintainers
- Consider upgrading to newer FalkorDB version
- Evaluate alternative in-memory graph databases

8. **Hybrid Storage Strategy**
- Keep hot data in FalkorDB (in-memory)
- Automatically page cold data to Neo4j
- Implement smart prefetching for common queries

9. **Distributed Architecture**
- Shard graph across multiple FalkorDB instances
- Implement graph partitioning by group_id
- Add load balancing for query distribution

## Lessons Learned

1. **2GB is insufficient** for a graph with 24K nodes + large embeddings
2. **Worker errors can indirectly corrupt graph state** leading to segfaults
3. **OOM kills are silent and catastrophic** for ephemeral in-memory databases
4. **Monitoring is critical** - we had no early warning of memory pressure
5. **Graceful degradation** would have prevented total data loss

## Action Items

| Action | Owner | Priority | Status |
|--------|-------|----------|--------|
| Increase FalkorDB memory limit to 8GB | DevOps | CRITICAL | Pending |
| Fix worker import error | Dev | CRITICAL | Complete (4133251) |
| Add memory usage monitoring | DevOps | HIGH | Pending |
| Investigate FalkorDB segfaults | Dev | HIGH | Pending |
| Implement read-only fallback mode | Dev | MEDIUM | Pending |
| Report segfaults to FalkorDB team | Dev | MEDIUM | Pending |
| Evaluate embedding dimension reduction | Data | LOW | Pending |

## Related Issues

- Worker ingestion errors: Phase 1 fixes (ac21af0), Phase 2 fixes (7a5845d)
- Missing os import: Critical fix (4133251)
- graph-visualizer-rust also experiencing OOM kills (separate investigation needed)

---

**Date**: October 22, 2025
**Incident ID**: GRAPH-FALKORDB-OOM-001
**Severity**: High (Data loss, requires full re-sync)
**Status**: Root cause identified, fixes in progress
