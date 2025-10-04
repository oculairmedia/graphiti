# Worker Silent - Solution Found

## Problem Identified ✓

**Root Cause:** Episodes in database are missing `valid_at` field, causing replay tasks to fail with:
```
ValueError: valid_at cannot be None for episode {uuid}
```

**Location:** `graphiti_core/nodes.py:784` in `get_episodic_node_from_record()`

**Impact:**
- Replay tasks fail immediately when trying to load episodes
- Tasks retry every 20 seconds indefinitely
- Worker appears "silent" because it's stuck retrying failed tasks
- No progress on actual replay processing

## Quick Fix (5 minutes)

### Step 1: Run Dry-Run to Check Impact

```bash
# See how many episodes are affected
python3 backfill_valid_at.py --dry-run
```

### Step 2: Backfill Missing Data

```bash
# Fix the data
python3 backfill_valid_at.py
```

This will:
- Find all episodes without `valid_at`
- Set `valid_at = created_at` for those episodes
- Verify all episodes now have `valid_at`

### Step 3: Restart Worker

```bash
# Restart to clear failed tasks
docker-compose restart graphiti-worker

# Monitor logs
docker-compose logs -f graphiti-worker
```

### Step 4: Verify Fix

```bash
# Check replay tasks are processing
curl -H "Accept: application/json" \
  http://localhost:8093/queue/memory_replay/metrics | jq

# Should see tasks completing, not retrying
docker-compose logs -f graphiti-worker | grep -E "Replay|Completed"
```

## What the Script Does

```python
# Finds episodes without valid_at
MATCH (ep:Episodic)
WHERE ep.valid_at IS NULL
RETURN count(ep)

# Sets valid_at = created_at
MATCH (ep:Episodic)
WHERE ep.valid_at IS NULL
SET ep.valid_at = ep.created_at
```

## Expected Output

```
============================================================
Backfill valid_at for Episodes
============================================================

✓ Connected to FalkorDB at falkordb:6379

============================================================
1. Checking for Episodes Without valid_at
============================================================

⚠ Found 3456 episodes without valid_at

============================================================
2. Backfilling valid_at
============================================================

✓ Updated 3456 episodes

============================================================
3. Verifying Fix
============================================================

✓ All episodes now have valid_at set!

============================================================
Summary
============================================================

✓ Successfully backfilled valid_at for 3456 episodes

ℹ Next steps:
  1. Restart worker: docker-compose restart graphiti-worker
  2. Monitor logs: docker-compose logs -f graphiti-worker
  3. Check replay tasks are processing
```

## Why This Happened

**Historical Context:**
- Older episodes were created before `valid_at` was a required field
- Database migration didn't backfill existing episodes
- New episodes have `valid_at` set correctly
- Only affects old episodes being replayed

**Code Guard:**
```python
# graphiti_core/nodes.py:784
if valid_at is None:
    raise ValueError(f'valid_at cannot be None for episode {uuid}')
```

This guard is correct - `valid_at` should never be None. The issue is the data, not the code.

## Alternative Solutions (If Backfill Fails)

### Option 1: Modify Code to Use Fallback

```python
# In graphiti_core/nodes.py:784
if valid_at is None:
    logger.warning(f'valid_at is None for episode {uuid}, using created_at')
    valid_at = created_at
```

### Option 2: Skip Episodes Without valid_at

```python
# In replay executor
try:
    episode = await EpisodicNode.get_by_uuid(driver, uuid)
except ValueError as e:
    if 'valid_at cannot be None' in str(e):
        logger.warning(f'Skipping episode {uuid}: missing valid_at')
        raise ReplayEpisodeNotFound(uuid) from e
    raise
```

## Prevention

### Add Validation on Episode Creation

```python
# In graphiti.py
async def add_episode(..., reference_time: datetime):
    if reference_time is None:
        reference_time = utc_now()  # Never allow None
```

### Add Database Constraint

```cypher
# If FalkorDB supports constraints
CREATE CONSTRAINT ON (ep:Episodic) ASSERT ep.valid_at IS NOT NULL
```

## Monitoring

After fix, monitor for:

```bash
# No more "valid_at cannot be None" errors
docker-compose logs graphiti-worker | grep "valid_at cannot be None"

# Replay tasks completing successfully
docker-compose logs graphiti-worker | grep "Replay.*completed"

# Queue depth decreasing
watch -n 5 'curl -s -H "Accept: application/json" \
  http://localhost:8093/queue/memory_replay/metrics | jq ".visible, .invisible"'
```

## Related Documentation

- **Detailed Analysis:** `docs/REPLAY_VALID_AT_ISSUE.md`
- **Worker Troubleshooting:** `docs/WORKER_TROUBLESHOOTING.md`
- **Backfill Script:** `backfill_valid_at.py`

## Status Checklist

- [x] Issue identified (missing valid_at in database)
- [ ] Dry-run completed
- [ ] Backfill executed
- [ ] Worker restarted
- [ ] Replay tasks processing successfully
- [ ] No more retry loops in logs

