# Memory Replay Candidate Detection - Complete Summary

## TL;DR - What You Need to Do

```bash
# 1. Rebuild with no cache
docker-compose build --no-cache graph

# 2. Restart the service
docker-compose up -d --force-recreate graph

# 3. Wait for ready (30 seconds)
docker-compose logs -f graph  # Wait for "startup complete"

# 4. Test it
curl -X POST "http://localhost:8003/replay/trigger?dry_run=true" | jq
```

**Expected Result:** Should return `"requested": 3456` (or similar large number), not `0`.

---

## The Problem

The memory replay candidate detection returns **0 candidates** despite having **3,456 qualifying episodes** in the database.

### Why It's Broken

**File:** `graphiti_core/utils/replay/candidate_detector.py`

The query uses **parameterized datetime comparison** which FalkorDB doesn't handle correctly:

```python
# BROKEN
query = "WHERE ep.created_at < $cutoff_time"
params = {'cutoff_time': '2025-01-30T12:00:00+00:00'}
result = await driver.execute_query(query, **params)
```

FalkorDB treats `$cutoff_time` as a **string** and does **lexicographic comparison** instead of **datetime comparison**.

### The Fix

Use **inline values** instead of parameters:

```python
# FIXED
cutoff_iso = cutoff_time.isoformat()
query = f"WHERE ep.created_at < '{cutoff_iso}'"
result = await driver.execute_query(query)
```

---

## What's Been Done

✅ **Code Fix Applied**
- Changed `candidate_detector.py` to use inline values
- All query parameters now inline (timestamp, thresholds, limits)
- Added logging to track query execution

✅ **Docker Compose Updated**
- Changed from remote image to local build
- Both `graph` and `graphiti-worker` services now build locally
- Image name: `graphiti-api-local:latest`

✅ **Documentation Created**
- `FIXING_CANDIDATE_DETECTION.md` - Step-by-step fix guide
- `LOCAL_BUILD_GUIDE.md` - Docker build reference
- `MEMORY_REPLAY_REMAINING_WORK.md` - Complete testing guide
- `CANDIDATE_DETECTION_SUMMARY.md` - This file

---

## What You Need to Do

### 1. Verify Docker Compose Configuration

Check that `docker-compose.yml` has local build config:

```bash
grep -A 5 "^  graph:" docker-compose.yml
```

Should show:
```yaml
graph:
  build:
    context: .
    dockerfile: Dockerfile
  image: graphiti-api-local:latest
```

If it shows `image: ghcr.io/oculairmedia/...`, the config wasn't updated.

### 2. Rebuild the Image

```bash
cd u:\graphiti

# Clean build (recommended)
docker-compose build --no-cache graph

# This will take 2-5 minutes
```

### 3. Restart the Service

```bash
# Stop old container
docker-compose stop graph

# Start with new image
docker-compose up -d graph

# Or force recreate
docker-compose up -d --force-recreate graph
```

### 4. Verify Service Started

```bash
# Watch logs
docker-compose logs -f graph

# Look for:
# "Application startup complete"
# "Uvicorn running on http://0.0.0.0:8000"
```

### 5. Test Candidate Detection

```bash
# Dry run test
curl -X POST "http://localhost:8003/replay/trigger?dry_run=true" | jq
```

**Success looks like:**
```json
{
  "dry_run": true,
  "enabled": true,
  "requested": 3456,
  "selected_count": 10,
  "selected": [
    {
      "episode_uuid": "abc-123...",
      "group_id": "GRAPH",
      "priority": 0.85,
      "reason": "sparse_entities,no_cross_group_links",
      "attempts": 0
    }
  ]
}
```

**Failure looks like:**
```json
{
  "dry_run": true,
  "enabled": true,
  "requested": 0,  // ❌ Still broken
  "selected_count": 0,
  "selected": []
}
```

---

## If It Still Doesn't Work

### Check 1: Verify Code Fix

```bash
# Check the query uses inline values
grep "ep.created_at <" graphiti_core/utils/replay/candidate_detector.py

# Should show:
# AND ep.created_at < '{cutoff_iso}'
```

### Check 2: Verify Image Was Rebuilt

```bash
# Check image timestamp
docker images | grep graphiti-api-local

# Should show recent timestamp (within last 10 minutes)
```

### Check 3: Check Logs

```bash
# Look for query execution
docker-compose logs graph | grep "ReplayCandidateDetector"

# Should show:
# INFO: ReplayCandidateDetector query params: stale_days=2.000000, cutoff=2025-01-30T...
# INFO: ReplayCandidateDetector query: MATCH (ep:Episodic)...
# INFO: ReplayCandidateDetector fetched X raw rows
```

### Check 4: Test Database Directly

```bash
# Get container name
docker ps | grep falkor

# Connect to FalkorDB
docker exec -it <falkordb-container> redis-cli -p 6379

# Run manual query
GRAPH.QUERY default_db "MATCH (ep:Episodic) WHERE ep.created_at IS NOT NULL AND ep.created_at < '2025-01-30T12:00:00+00:00' RETURN count(ep)"

# Should return 3456 or similar
```

### Check 5: Verify Environment Variables

```bash
# Check environment inside container
docker exec <graph-container> env | grep REPLAY

# Should show:
# REPLAY_ENABLED=true
# REPLAY_STALE_DAYS=2
# REPLAY_BATCH_SIZE=10
```

---

## Next Steps After Fix Works

Once candidate detection returns results:

1. **Test Manual Trigger**
   ```bash
   curl -X POST "http://localhost:8003/replay/trigger" | jq
   ```

2. **Verify Queue**
   ```bash
   curl http://localhost:8093/queue/memory_replay | jq
   ```

3. **Monitor Worker Processing**
   ```bash
   docker-compose logs -f graphiti-queued
   ```

4. **Check Metrics**
   ```bash
   curl http://localhost:8003/metrics/replay | jq
   ```

5. **Run Full Test Suite**
   ```bash
   pytest tests/test_memory_replay_*.py -v
   ```

See `docs/MEMORY_REPLAY_REMAINING_WORK.md` for complete testing guide.

---

## Key Files Changed

### Code Changes
- ✅ `graphiti_core/utils/replay/candidate_detector.py` (lines 155-215)
  - Changed from parameterized to inline query values
  - Added query logging

### Configuration Changes
- ✅ `docker-compose.yml` (lines 176-182, 451-457)
  - Changed `graph` service to local build
  - Changed `graphiti-worker` service to local build

### Documentation Added
- ✅ `docs/FIXING_CANDIDATE_DETECTION.md`
- ✅ `docs/LOCAL_BUILD_GUIDE.md`
- ✅ `docs/MEMORY_REPLAY_REMAINING_WORK.md`
- ✅ `docs/CANDIDATE_DETECTION_SUMMARY.md`

---

## Timeline

- **Code fix:** ✅ Already applied
- **Docker config:** ✅ Already updated
- **Rebuild:** ⏳ ~2-5 minutes
- **Restart:** ⏳ ~30 seconds
- **Testing:** ⏳ ~5 minutes
- **Total:** ~10 minutes

---

## Success Criteria

The fix is successful when:

1. ✅ `docker-compose build` completes without errors
2. ✅ Service starts and shows "Application startup complete"
3. ✅ `/replay/trigger?dry_run=true` returns `requested > 0`
4. ✅ Logs show "ReplayCandidateDetector fetched X raw rows" where X > 0
5. ✅ Selected candidates have valid UUIDs and priorities

---

## Common Issues

### "docker-compose build does nothing"
- **Cause:** Still using remote image
- **Fix:** Check docker-compose.yml has `build:` section

### "Changes not reflected after rebuild"
- **Cause:** Docker using cached layers
- **Fix:** Use `--no-cache` flag

### "Port 8003 already in use"
- **Cause:** Old container still running
- **Fix:** `docker-compose stop graph` first

### "Service won't start"
- **Cause:** Build failed or missing dependencies
- **Fix:** Check `docker-compose logs graph` for errors

---

## Quick Reference Commands

```bash
# Build
docker-compose build --no-cache graph

# Restart
docker-compose up -d --force-recreate graph

# Logs
docker-compose logs -f graph

# Test
curl -X POST "http://localhost:8003/replay/trigger?dry_run=true" | jq

# Debug
docker-compose logs graph | grep -i "replay"
docker exec <graph-container> env | grep REPLAY
```

---

## Documentation Index

### Quick Start (Pick One)

1. **CANDIDATE_DETECTION_CHECKLIST.md** ⭐ - Step-by-step checklist (fastest)
2. **This File (CANDIDATE_DETECTION_SUMMARY.md)** - Quick summary and commands

### Detailed Guides

3. **FIXING_CANDIDATE_DETECTION.md** - Complete step-by-step guide with debugging
4. **LOCAL_BUILD_GUIDE.md** - Docker build reference and troubleshooting
5. **MEMORY_REPLAY_REMAINING_WORK.md** - Full testing guide after fix works

### Reference Documentation

6. **11-memory-replay-operations.md** - Operational guide and monitoring
7. **memory_replay_specification.md** - Design specification and architecture

---

## Support

If you're still stuck after following this guide:

1. Check all logs: `docker-compose logs graph`
2. Verify database: Manual query in FalkorDB
3. Check environment: `docker exec <container> env | grep REPLAY`
4. Review detailed guide: `docs/FIXING_CANDIDATE_DETECTION.md`
5. Check build guide: `docs/LOCAL_BUILD_GUIDE.md`

