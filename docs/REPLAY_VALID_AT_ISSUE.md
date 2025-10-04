# Memory Replay - valid_at Issue

## Problem

Replay tasks are failing with error:
```
ValueError: valid_at cannot be None for episode {uuid}
```

## Root Cause

**File:** `graphiti_core/nodes.py`, line 784

```python
def get_episodic_node_from_record(record: Any) -> EpisodicNode:
    created_at = parse_db_date(record['created_at'])
    valid_at = parse_db_date(record['valid_at'])

    if created_at is None:
        raise ValueError(f'created_at cannot be None for episode {record.get("uuid", "unknown")}')
    if valid_at is None:
        raise ValueError(f'valid_at cannot be None for episode {record.get("uuid", "unknown")}')  # ← THIS FAILS
```

**Why it happens:**
- Some episodes in the database don't have `valid_at` field set
- When `EpisodicNode.get_by_uuid()` retrieves these episodes, `valid_at` is `None`
- The guard clause raises `ValueError`, causing replay task to fail
- Task gets retried every 20 seconds indefinitely

## Evidence from Logs

```
graphiti-worker-1  | 2025-09-30 23:12:13,149 - graphiti_core.ingestion.worker - INFO - Task replay-51831671-0fa5-4360-995e-26b9f8b1db75-1759264254630-87 will retry in 20 seconds
```

## Solutions

### Solution 1: Fix Database Data (Recommended)

Backfill `valid_at` for all episodes that are missing it:

```python
#!/usr/bin/env python3
"""Backfill valid_at for episodes missing it"""

import asyncio
from graphiti_core.driver.falkordb_driver import FalkorDriver

async def backfill_valid_at():
    driver = FalkorDriver(host='falkordb', port=6379, database='default_db')
    
    # Find episodes without valid_at
    query = """
    MATCH (ep:Episodic)
    WHERE ep.valid_at IS NULL
    SET ep.valid_at = ep.created_at
    RETURN count(ep) as updated_count
    """
    
    result = await driver.execute_query(query)
    print(f"Updated {result} episodes")

asyncio.run(backfill_valid_at())
```

**Run this:**
```bash
python3 backfill_valid_at.py
```

### Solution 2: Handle None in Code (Fallback)

Modify `get_episodic_node_from_record` to use `created_at` as fallback:

```python
# In graphiti_core/nodes.py, line 778-784

def get_episodic_node_from_record(record: Any) -> EpisodicNode:
    created_at = parse_db_date(record['created_at'])
    valid_at = parse_db_date(record['valid_at'])

    if created_at is None:
        raise ValueError(f'created_at cannot be None for episode {record.get("uuid", "unknown")}')
    
    # Use created_at as fallback if valid_at is missing
    if valid_at is None:
        logger.warning(f'valid_at is None for episode {record.get("uuid", "unknown")}, using created_at as fallback')
        valid_at = created_at
```

### Solution 3: Skip Episodes Without valid_at

Modify replay executor to skip episodes that can't be loaded:

```python
# In graphiti_core/utils/replay/executor.py

async def execute(self, episode_uuid: str, context: ReplayContext) -> AddEpisodeResults:
    try:
        episode = await EpisodicNode.get_by_uuid(self.driver, episode_uuid)
    except ValueError as e:
        if 'valid_at cannot be None' in str(e):
            logger.warning(f'Skipping episode {episode_uuid}: {e}')
            raise ReplayEpisodeNotFound(episode_uuid) from e
        raise
```

## Recommended Action Plan

### Step 1: Check How Many Episodes Are Affected

```bash
# Connect to FalkorDB
docker exec -it <falkordb-container> redis-cli -p 6379

# Count episodes without valid_at
GRAPH.QUERY default_db "MATCH (ep:Episodic) WHERE ep.valid_at IS NULL RETURN count(ep)"
```

### Step 2: Backfill the Data

Create and run the backfill script:

```bash
# Create backfill script
cat > backfill_valid_at.py << 'EOF'
#!/usr/bin/env python3
"""Backfill valid_at for episodes missing it"""

import asyncio
import sys
sys.path.insert(0, '/opt/stacks/graphiti')

from graphiti_core.driver.falkordb_driver import FalkorDriver

async def backfill_valid_at():
    driver = FalkorDriver(host='falkordb', port=6379, database='default_db')
    
    # Find and update episodes without valid_at
    query = """
    MATCH (ep:Episodic)
    WHERE ep.valid_at IS NULL
    SET ep.valid_at = ep.created_at
    RETURN count(ep) as updated_count
    """
    
    try:
        result = await driver.execute_query(query)
        print(f"✓ Updated episodes with missing valid_at")
        print(f"  Result: {result}")
    except Exception as e:
        print(f"✗ Error: {e}")

asyncio.run(backfill_valid_at())
EOF

# Run it
python3 backfill_valid_at.py
```

### Step 3: Verify Fix

```bash
# Check no episodes are missing valid_at
docker exec -it <falkordb-container> redis-cli -p 6379
GRAPH.QUERY default_db "MATCH (ep:Episodic) WHERE ep.valid_at IS NULL RETURN count(ep)"

# Should return 0
```

### Step 4: Restart Worker

```bash
# Restart worker to clear failed tasks
docker-compose restart graphiti-worker

# Monitor logs
docker-compose logs -f graphiti-worker
```

## Prevention

### Add Validation on Episode Creation

Ensure `valid_at` is always set when creating episodes:

```python
# In graphiti.py, add_episode method

async def add_episode(
    self,
    name: str,
    episode_body: str,
    source_description: str,
    reference_time: datetime,  # ← Ensure this is always provided
    ...
):
    # Validate reference_time is not None
    if reference_time is None:
        reference_time = utc_now()
    
    # Create episode with valid_at = reference_time
    episode = EpisodicNode(
        ...
        valid_at=reference_time,
        ...
    )
```

### Add Database Constraint

Add a constraint to ensure `valid_at` is always set:

```cypher
// In FalkorDB (if supported)
CREATE CONSTRAINT ON (ep:Episodic) ASSERT ep.valid_at IS NOT NULL
```

## Testing

After applying the fix:

```bash
# 1. Check queue metrics
curl -H "Accept: application/json" \
  http://localhost:8093/queue/memory_replay/metrics | jq

# 2. Trigger a test replay
curl -X POST "http://localhost:8003/replay/trigger?dry_run=true" | jq

# 3. Monitor worker logs
docker-compose logs -f graphiti-worker | grep -E "Replay|valid_at"

# 4. Verify no more "valid_at cannot be None" errors
```

## Related Files

- **Error location:** `graphiti_core/nodes.py:784`
- **Replay executor:** `graphiti_core/utils/replay/executor.py`
- **Episode creation:** `graphiti_core/graphiti.py`
- **Worker logs:** `docker-compose logs graphiti-worker`

## Status

- [x] Issue identified
- [ ] Database backfill completed
- [ ] Worker restarted
- [ ] Replay tasks processing successfully
- [ ] Prevention measures added

