# Fixing Memory Replay Candidate Detection

## Problem Statement

The memory replay candidate detection is returning **0 candidates** through the API endpoint despite the database containing **3,456 qualifying episodes**.

### Symptoms

```bash
# API returns empty results
curl -X POST "http://localhost:8003/replay/trigger?dry_run=true" | jq
{
  "dry_run": true,
  "enabled": true,
  "requested": 0,
  "selected_count": 0,
  "selected": []
}

# But manual database query shows 3,456 episodes
GRAPH.QUERY default_db "
MATCH (ep:Episodic)
WHERE ep.created_at IS NOT NULL 
  AND ep.created_at < '2025-01-30T12:00:00+00:00'
RETURN count(ep)
"
# Result: 3456
```

## Root Cause Analysis

### The Issue

**File:** `graphiti_core/utils/replay/candidate_detector.py`
**Method:** `_fetch_candidate_rows()`
**Line:** ~181

The query uses **parameterized datetime comparison** which FalkorDB doesn't handle correctly:

```python
# BROKEN CODE (current state before fix)
query = """
MATCH (ep:Episodic)
WHERE ep.created_at < $cutoff_time
"""

params = {
    'cutoff_time': cutoff_iso  # ISO string like "2025-01-30T12:00:00+00:00"
}

result = await self.driver.execute_query(query, **params)
```

### Why It Fails

1. **FalkorDB Parameter Handling:** When you pass a datetime as a parameter (`$cutoff_time`), FalkorDB treats it as a **string** and performs **lexicographic comparison** instead of datetime comparison.

2. **String vs DateTime Comparison:**
   ```
   # What we want (datetime comparison):
   datetime("2025-01-15") < datetime("2025-01-30")  → true
   
   # What FalkorDB does (string comparison):
   "2025-01-15T..." < "2025-01-30T..."  → depends on string format
   ```

3. **Parameter Type Confusion:** The parameter system doesn't preserve the datetime type, so FalkorDB can't distinguish between a datetime string and a regular string.

### Why Manual Query Works

Your manual query works because the timestamp is **inline** (not parameterized):

```cypher
WHERE ep.created_at < '2025-01-30T12:00:00+00:00'
```

When the value is inline, FalkorDB's parser correctly interprets it as a datetime literal and performs proper datetime comparison.

## The Fix

### Solution: Use Inline Values Instead of Parameters

Change from parameterized query to inline values using f-strings:

```python
# FIXED CODE
def _fetch_candidate_rows(self, ...):
    # Calculate cutoff time
    stale_days = float(os.getenv('REPLAY_STALE_DAYS', '90'))
    now = self._now()
    cutoff_time = now - timedelta(days=stale_days)
    cutoff_iso = cutoff_time.isoformat()
    
    # Build query with inline values
    group_filter = f"ep.group_id = '{group_id}'" if group_id else "true"
    
    query = f"""
    MATCH (ep:Episodic)
    OPTIONAL MATCH (rm:ReplayMetadata {{episode_uuid: ep.uuid}})
    WITH ep, rm,
         coalesce(ep.entity_count, size(coalesce(ep.entity_edges, []))) AS entity_count,
         coalesce(ep.edge_count, size(coalesce(ep.entity_edges, []))) AS edge_count,
         coalesce(ep.cross_group_connections, 0) AS cross_group_connections,
         coalesce(ep.confidence_score, 0.0) AS confidence_score
    WHERE {group_filter}
      AND ep.created_at IS NOT NULL
      AND ep.created_at < '{cutoff_iso}'
      AND (
            entity_count < {entity_threshold}
         OR cross_group_connections = 0
         OR confidence_score < {confidence_threshold}
         OR ep.extraction_version IS NULL
         OR ('{current_extraction_version}' IS NOT NULL AND ep.extraction_version <> '{current_extraction_version}')
      )
    RETURN ep.uuid AS episode_uuid,
           ep.group_id AS group_id,
           entity_count,
           edge_count,
           cross_group_connections,
           ep.extraction_version AS extraction_version,
           confidence_score,
           ep.valid_at AS valid_at,
           ep.created_at AS created_at,
           rm.last_replayed_at AS last_replayed_at,
           coalesce(rm.replay_attempts, 0) AS replay_attempts
    ORDER BY ep.valid_at DESC
    LIMIT {max_candidates}
    """
    
    # Execute without parameters
    result = await self.driver.execute_query(query)
    return _normalise_records(result)
```

### Key Changes

1. **Inline timestamp:** `AND ep.created_at < '{cutoff_iso}'`
2. **Inline thresholds:** `entity_count < {entity_threshold}`
3. **Inline limits:** `LIMIT {max_candidates}`
4. **No parameters:** `execute_query(query)` instead of `execute_query(query, **params)`

## Implementation Steps

### Step 0: Verify Docker Compose Configuration

**IMPORTANT:** The `docker-compose.yml` has been updated to build locally instead of pulling from GitHub:

```yaml
graph:
  build:
    context: .
    dockerfile: Dockerfile
  image: graphiti-api-local:latest
```

If you see `image: ghcr.io/oculairmedia/graphiti-api:...` instead, the compose file is still using remote images and `docker-compose build` won't work. See `docs/LOCAL_BUILD_GUIDE.md` for details.

### Step 1: Apply the Code Fix

The fix has already been applied to `graphiti_core/utils/replay/candidate_detector.py`. Verify it's correct:

```bash
# Check the file
cat graphiti_core/utils/replay/candidate_detector.py | grep -A 5 "ep.created_at <"

# Should show:
# AND ep.created_at < '{cutoff_iso}'
# NOT:
# AND ep.created_at < $cutoff_time
```

### Step 2: Rebuild Docker Image

The code change needs to be built into the Docker image:

```bash
cd u:\graphiti

# Option A: Build with docker-compose (recommended)
docker-compose build --no-cache graph

# Option B: Build directly with docker (if compose doesn't work)
docker build --no-cache -t graphiti-api-local:latest -f Dockerfile .

# Expected output:
# [+] Building ...
# => [graph] exporting to image
# => => writing image sha256:...
```

**Note:** The `--no-cache` flag ensures a clean build with all your latest changes.

### Step 3: Restart the Service

Deploy the updated image:

```bash
# Stop the current service
docker-compose stop graph

# Start with new image
docker-compose up -d graph

# Verify it's running
docker-compose ps graph
```

### Step 4: Wait for Service Ready

```bash
# Watch logs until startup complete
docker-compose logs -f graph

# Look for:
# "Application startup complete"
# "Uvicorn running on http://0.0.0.0:8000"
```

### Step 5: Test Candidate Detection

```bash
# Test dry-run endpoint
curl -X POST "http://localhost:8003/replay/trigger?dry_run=true" | jq
```

**Expected Success Output:**
```json
{
  "dry_run": true,
  "enabled": true,
  "requested": 3456,  // Large number of candidates found
  "selected_count": 10,  // Batch size limit
  "selected": [
    {
      "episode_uuid": "abc-123-...",
      "group_id": "GRAPH",
      "priority": 0.85,
      "reason": "sparse_entities,no_cross_group_links",
      "attempts": 0
    },
    // ... 9 more candidates
  ]
}
```

**If Still Failing (0 candidates):**
```json
{
  "dry_run": true,
  "enabled": true,
  "requested": 0,  // ❌ Still broken
  "selected_count": 0,
  "selected": []
}
```

## Debugging If Still Broken

### Debug Step 1: Check Logs

```bash
# Look for query execution logs
docker-compose logs graph | grep "ReplayCandidateDetector"

# Should see:
# INFO: ReplayCandidateDetector query params: stale_days=2.000000, cutoff=2025-01-30T...
# INFO: ReplayCandidateDetector query: MATCH (ep:Episodic)...
# INFO: ReplayCandidateDetector fetched X raw rows
```

### Debug Step 2: Verify Environment Variables

```bash
# Check environment inside container
docker exec <graph-container-name> env | grep REPLAY

# Should show:
# REPLAY_ENABLED=true
# REPLAY_STALE_DAYS=2
# REPLAY_BATCH_SIZE=10
# REPLAY_MIN_PRIORITY=0.3
```

### Debug Step 3: Test Query Directly

```bash
# Get the exact query from logs
docker-compose logs graph | grep "ReplayCandidateDetector query:"

# Copy the query and test in FalkorDB directly
docker exec -it <falkordb-container> redis-cli -p 6379

# Run the query
GRAPH.QUERY default_db "MATCH (ep:Episodic) WHERE ep.created_at < '2025-01-30T12:00:00+00:00' RETURN count(ep)"
```

### Debug Step 4: Check Database Connection

```bash
# Verify FalkorDB is accessible
docker exec <graph-container> python3 -c "
from graphiti_core.driver.falkordb_driver import FalkorDriver
driver = FalkorDriver(host='falkordb', port=6379, database='default_db')
print('Connection successful')
"
```

### Debug Step 5: Manual Python Test

Create a test script to isolate the issue:

```python
# test_candidate_detection.py
import asyncio
from datetime import datetime, timezone, timedelta
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.utils.replay.candidate_detector import ReplayCandidateDetector

async def test():
    driver = FalkorDriver(host='falkordb', port=6379, database='default_db')
    detector = ReplayCandidateDetector(driver)
    
    candidates = await detector.identify_candidates(
        group_id=None,
        limit=100,
        min_priority=0.1
    )
    
    print(f"Found {len(candidates)} candidates")
    for c in candidates[:5]:
        print(f"  - {c.episode_uuid}: priority={c.replay_priority:.2f}, reason={c.replay_reason}")

asyncio.run(test())
```

Run it:
```bash
docker exec <graph-container> python3 /path/to/test_candidate_detection.py
```

## Alternative Solutions (If Fix Doesn't Work)

### Alternative 1: Use Timestamp Integers

Convert to Unix timestamps:

```python
cutoff_timestamp = int(cutoff_time.timestamp())

query = f"""
WHERE toInteger(ep.created_at_timestamp) < {cutoff_timestamp}
"""
```

**Requires:** Episodes must have `created_at_timestamp` field populated.

### Alternative 2: Use datetime() Function

If FalkorDB supports it:

```python
query = f"""
WHERE datetime(ep.created_at) < datetime('{cutoff_iso}')
"""
```

### Alternative 3: Client-Side Filtering

Fetch all episodes and filter in Python (not recommended for large datasets):

```python
# Fetch all episodes
query = "MATCH (ep:Episodic) RETURN ep"
all_episodes = await driver.execute_query(query)

# Filter in Python
cutoff = datetime.now() - timedelta(days=stale_days)
candidates = [ep for ep in all_episodes if ep.created_at < cutoff]
```

## Verification Checklist

After applying the fix, verify:

- [ ] Code change is in `candidate_detector.py`
- [ ] Query uses inline values (f-string), not parameters
- [ ] Docker image rebuilt successfully
- [ ] Service restarted with new image
- [ ] Service logs show "Application startup complete"
- [ ] `/replay/trigger?dry_run=true` returns candidates > 0
- [ ] Logs show "ReplayCandidateDetector fetched X raw rows" where X > 0
- [ ] Selected candidates have valid UUIDs and priorities
- [ ] No errors in service logs

## Expected Timeline

- **Code fix:** ✅ Already applied
- **Docker rebuild:** ~2-5 minutes
- **Service restart:** ~30 seconds
- **Testing:** ~5 minutes
- **Total:** ~10 minutes

## Success Criteria

The fix is successful when:

1. **API returns candidates:**
   ```json
   {
     "requested": 3456,  // Or similar large number
     "selected_count": 10
   }
   ```

2. **Logs show query execution:**
   ```
   INFO: ReplayCandidateDetector fetched 3456 raw rows
   ```

3. **Manual trigger works:**
   ```bash
   curl -X POST "http://localhost:8003/replay/trigger"
   # Returns: {"scheduled": 10}
   ```

## Related Files

- **Main fix:** `graphiti_core/utils/replay/candidate_detector.py` (lines 155-215)
- **API endpoint:** `server/graph_service/main.py` (lines 190-204)
- **Scheduler:** `graphiti_core/utils/replay/scheduler.py` (lines 272-309)
- **Tests:** `tests/test_replay_candidate_detector.py`

## References

- **Similar pattern in codebase:** `graphiti-search-rs/src/falkor/client.rs` (uses inline values for vectors)
- **FalkorDB docs:** https://docs.falkordb.com/
- **Issue discussion:** See conversation history for detailed analysis

## Next Steps After Fix

Once candidate detection works:

1. Run full test suite: `pytest tests/test_memory_replay_*.py`
2. Test manual trigger: `curl -X POST http://localhost:8003/replay/trigger`
3. Verify queue: `curl http://localhost:8093/queue/memory_replay`
4. Monitor worker processing: `docker-compose logs -f graphiti-queued`
5. Check database updates: Query ReplayMetadata nodes

See `docs/MEMORY_REPLAY_REMAINING_WORK.md` for complete testing guide.

