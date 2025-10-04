# Memory Replay System - Remaining Work & Testing Guide

## Current Status

The memory replay system has been implemented with the following components:

✅ **Completed:**
- Core replay components (ReplayScheduler, ReplayExecutor, ReplayCandidateDetector)
- Configuration system with environment variables
- API endpoints (`/metrics/replay`, `/replay/trigger`)
- Metadata migration script (successfully populated 6,075 metadata nodes)
- Episode hydration (5,898 episodes hydrated with metadata)
- Docker integration and deployment
- Comprehensive test suite (13 tests passing)

⚠️ **Issue Identified:**
- Candidate detection returns 0 results through API despite 3,456 qualifying episodes in database
- Root cause: FalkorDB parameterized datetime comparison incompatibility
- Fix applied: Changed to inline timestamp values in query

## Critical Issue: Candidate Detection Not Working

### Problem Description

When calling `/replay/trigger?dry_run=true`, the API returns:
```json
{
  "dry_run": true,
  "enabled": true,
  "requested": 0,
  "selected_count": 0,
  "selected": []
}
```

However, manual database query confirms 3,456 episodes should qualify:
```cypher
MATCH (ep:Episodic)
WHERE ep.created_at IS NOT NULL 
  AND ep.created_at < '2025-01-30T12:00:00+00:00'
RETURN count(ep)
// Returns: 3456
```

### Root Cause

**File:** `graphiti_core/utils/replay/candidate_detector.py`
**Line:** 181 (before fix)

The query was using parameterized datetime comparison:
```python
AND ep.created_at < $cutoff_time
```

**FalkorDB Issue:** FalkorDB doesn't handle parameterized datetime comparisons reliably - it performs lexicographic string comparison instead of datetime comparison.

### Fix Applied

Changed from parameterized query to inline values:

```python
# BEFORE (broken)
query = """
WHERE ep.created_at < $cutoff_time
"""
params = {'cutoff_time': cutoff_iso}
result = await self.driver.execute_query(query, **params)

# AFTER (fixed)
query = f"""
WHERE ep.created_at < '{cutoff_iso}'
"""
result = await self.driver.execute_query(query)
```

## Remaining Tasks

### 1. Verify the Fix Works

**Priority:** CRITICAL
**Estimated Time:** 15 minutes

#### Steps:

1. **Rebuild Docker image:**
   ```bash
   cd u:\graphiti
   docker-compose build graph
   ```

2. **Restart the service:**
   ```bash
   docker-compose up -d graph
   ```

3. **Wait for service to be ready:**
   ```bash
   # Check logs
   docker-compose logs -f graph
   
   # Wait for "Application startup complete"
   ```

4. **Test candidate detection:**
   ```bash
   curl -X POST "http://localhost:8003/replay/trigger?dry_run=true" | jq
   ```

5. **Expected result:**
   ```json
   {
     "dry_run": true,
     "enabled": true,
     "requested": 3456,  // Or similar large number
     "selected_count": 10,  // Based on batch_size
     "selected": [
       {
         "episode_uuid": "...",
         "group_id": "GRAPH",
         "priority": 0.85,
         "reason": "sparse_entities,no_cross_group_links",
         "attempts": 0
       },
       // ... more candidates
     ]
   }
   ```

6. **If still returns 0 candidates:**
   - Check logs: `docker-compose logs graph | grep "ReplayCandidateDetector"`
   - Look for query execution logs
   - Verify environment variables are set correctly
   - Check database connectivity

### 2. Run Integration Tests

**Priority:** HIGH
**Estimated Time:** 30 minutes

The test suite has been created but needs to be run against the live system:

```bash
# Run all replay tests
pytest tests/test_memory_replay_executor.py \
       tests/test_memory_replay_scheduler.py \
       tests/test_replay_candidate_detector.py -v

# Expected: All 13 tests should pass
```

**Current test status:** ✅ 13 passed, 25 warnings

### 3. Manual End-to-End Testing

**Priority:** HIGH
**Estimated Time:** 45 minutes

#### Test Scenario 1: Dry Run Preview

```bash
# Preview candidates without scheduling
curl -X POST "http://localhost:8003/replay/trigger?dry_run=true" | jq

# Verify:
# - Returns candidates
# - No tasks added to queue
# - Metrics unchanged
```

#### Test Scenario 2: Manual Trigger

```bash
# Trigger actual replay scheduling
curl -X POST "http://localhost:8003/replay/trigger" | jq

# Expected response:
{
  "dry_run": false,
  "scheduled": 10,  // Number of tasks scheduled
  "status": {
    "enabled": true,
    "last_run_at": "2025-01-30T...",
    "last_scheduled": 10,
    "total_scheduled": 10
  }
}
```

#### Test Scenario 3: Verify Queue

```bash
# Check queue has tasks
curl http://localhost:8093/queue/memory_replay | jq

# Expected: Should show 10 pending tasks
```

#### Test Scenario 4: Monitor Metrics

```bash
# Check metrics endpoint
curl http://localhost:8003/metrics/replay | jq

# Verify:
# - last_run_at updated
# - last_scheduled shows correct count
# - total_scheduled incremented
```

#### Test Scenario 5: Worker Processing

```bash
# Watch worker logs
docker-compose logs -f graphiti-queued

# Look for:
# - "Processing REPLAY task"
# - "Replay completed for episode..."
# - Success/failure messages
```

### 4. Database Verification

**Priority:** MEDIUM
**Estimated Time:** 20 minutes

After replay tasks complete, verify database updates:

```bash
# Connect to FalkorDB
docker exec -it <falkordb-container> redis-cli -p 6379

# Check ReplayMetadata updates
GRAPH.QUERY default_db "
MATCH (rm:ReplayMetadata)
WHERE rm.last_replayed_at IS NOT NULL
RETURN count(rm) as replayed_count
"

# Check episode metadata updates
GRAPH.QUERY default_db "
MATCH (ep:Episodic)
WHERE ep.entity_count IS NOT NULL
RETURN count(ep) as episodes_with_counts
"
```

### 5. Performance Testing

**Priority:** LOW
**Estimated Time:** 30 minutes

Test system under load:

```bash
# Trigger multiple replay cycles
for i in {1..5}; do
  curl -X POST "http://localhost:8003/replay/trigger"
  sleep 10
done

# Monitor:
# - Queue depth
# - Worker processing rate
# - Database performance
# - Memory usage
```

## Known Issues & Workarounds

### Issue 1: FalkorDB Parameterized Queries

**Status:** FIXED (pending verification)

**Description:** FalkorDB doesn't handle parameterized datetime comparisons correctly.

**Workaround:** Use inline values in queries instead of parameters.

**Files affected:**
- `graphiti_core/utils/replay/candidate_detector.py`

### Issue 2: Environment Variable Defaults

**Status:** RESOLVED

**Description:** `ReplayConfig.from_env()` was using class attributes before they were defined.

**Solution:** Use hardcoded defaults in `from_env()` method.

**Files affected:**
- `graphiti_core/utils/replay/scheduler.py`

### Issue 3: Docker Build Context

**Status:** ONGOING

**Description:** Docker Desktop connectivity issues on Windows.

**Workaround:** Ensure Docker Desktop is running before building/deploying.

## Testing Checklist

Use this checklist to verify the system is working:

- [ ] Docker image builds successfully
- [ ] Service starts without errors
- [ ] `/metrics/replay` endpoint returns valid data
- [ ] `/replay/trigger?dry_run=true` returns candidates (not 0)
- [ ] `/replay/trigger` schedules tasks to queue
- [ ] Queue shows pending REPLAY tasks
- [ ] Workers process REPLAY tasks successfully
- [ ] ReplayMetadata nodes are updated in database
- [ ] Episode metadata (entity_count, etc.) is updated
- [ ] Metrics endpoint shows updated statistics
- [ ] All 13 unit tests pass
- [ ] No errors in service logs
- [ ] No errors in worker logs

## Configuration Reference

### Environment Variables

```bash
# Replay System
REPLAY_ENABLED=true
REPLAY_BATCH_SIZE=10
REPLAY_STALE_DAYS=2  # Episodes older than 2 days
REPLAY_MIN_PRIORITY=0.3
REPLAY_COOLDOWN_HOURS=1
REPLAY_MAX_PER_GROUP_PER_HOUR=50
REPLAY_CANDIDATE_SCAN_MULTIPLIER=4
REPLAY_TARGET_GROUP_ID=  # Empty = all groups

# Queue Configuration
QUEUE_URL=http://graphiti-queued:8080
QUEUE_NAME=memory_replay

# Database
FALKORDB_HOST=falkordb
FALKORDB_PORT=6379
FALKORDB_DATABASE=default_db
```

### Key Files

```
graphiti_core/utils/replay/
├── __init__.py
├── candidate_detector.py  # ⚠️ Recently modified
├── executor.py
└── scheduler.py

server/graph_service/
├── main.py  # API endpoints
└── routers/

tests/
├── test_memory_replay_executor.py
├── test_memory_replay_scheduler.py
└── test_replay_candidate_detector.py

docs/
├── 11-memory-replay-operations.md
└── memory_replay_specification.md
```

## Next Steps After Verification

Once the candidate detection is working:

1. **Monitor Production Behavior:**
   - Watch for 24 hours
   - Check replay success rate
   - Monitor database growth
   - Verify no performance degradation

2. **Tune Parameters:**
   - Adjust `REPLAY_STALE_DAYS` based on data patterns
   - Optimize `REPLAY_BATCH_SIZE` for throughput
   - Fine-tune priority thresholds

3. **Add Monitoring:**
   - Set up alerts for failed replays
   - Track replay success rate over time
   - Monitor queue depth trends

4. **Documentation:**
   - Update operational runbook
   - Document common issues and solutions
   - Create troubleshooting guide

## Troubleshooting Guide

### Problem: Still Getting 0 Candidates

**Check:**
1. Environment variables are set correctly
2. Database has episodes with `created_at` older than threshold
3. Query is being executed (check logs)
4. FalkorDB connection is working

**Debug:**
```bash
# Check environment
docker exec <graph-container> env | grep REPLAY

# Check database
docker exec <falkordb-container> redis-cli -p 6379 \
  GRAPH.QUERY default_db "MATCH (ep:Episodic) RETURN count(ep)"

# Check logs
docker-compose logs graph | grep -i "replay"
```

### Problem: Tasks Not Processing

**Check:**
1. Worker service is running
2. Queue service is accessible
3. Worker has correct queue configuration

**Debug:**
```bash
# Check worker status
docker-compose ps graphiti-queued

# Check worker logs
docker-compose logs -f graphiti-queued

# Check queue
curl http://localhost:8093/queue/memory_replay
```

### Problem: Database Not Updating

**Check:**
1. Replay tasks are completing successfully
2. Database connection is working
3. Permissions are correct

**Debug:**
```bash
# Check ReplayMetadata
docker exec <falkordb-container> redis-cli -p 6379 \
  GRAPH.QUERY default_db "MATCH (rm:ReplayMetadata) RETURN count(rm)"

# Check recent updates
docker exec <falkordb-container> redis-cli -p 6379 \
  GRAPH.QUERY default_db "
  MATCH (rm:ReplayMetadata)
  WHERE rm.last_replayed_at IS NOT NULL
  RETURN rm.episode_uuid, rm.last_replayed_at
  ORDER BY rm.last_replayed_at DESC
  LIMIT 10
  "
```

## Success Criteria

The memory replay system is considered fully operational when:

1. ✅ All unit tests pass
2. ⚠️ Candidate detection returns expected results (PENDING VERIFICATION)
3. ⚠️ Manual trigger schedules tasks successfully (PENDING VERIFICATION)
4. ⚠️ Workers process replay tasks without errors (PENDING VERIFICATION)
5. ⚠️ Database metadata is updated correctly (PENDING VERIFICATION)
6. ⚠️ Metrics endpoint shows accurate statistics (PENDING VERIFICATION)
7. ⚠️ System runs for 24 hours without issues (PENDING VERIFICATION)

## Contact & Support

For issues or questions:
- Check logs first: `docker-compose logs graph`
- Review this document
- Check `docs/11-memory-replay-operations.md` for operational details
- Review `docs/memory_replay_specification.md` for design details

