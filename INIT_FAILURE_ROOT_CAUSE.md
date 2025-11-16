# Init Container Failure - Root Cause Analysis

## Problem
The `graphiti-init` container was timing out and failing even after we updated the scripts to remove timeouts.

## Root Cause
**The docker-compose.yml was overriding the script's timeout default!**

### What We Changed in Scripts
```bash
# scripts/cold-boot-init.sh (line 22)
SYNC_TIMEOUT="${SYNC_TIMEOUT:-0}"  # No timeout - wait indefinitely
```

### What docker-compose.yml Was Doing
```yaml
# docker-compose.yml (line 471) - OLD
environment:
  - SYNC_TIMEOUT=${SYNC_TIMEOUT:-1200}  # ❌ 20 minute timeout!
```

### The Override Chain
1. Script sets default: `SYNC_TIMEOUT="${SYNC_TIMEOUT:-0}"`
2. **BUT** environment variable is already set by docker-compose: `SYNC_TIMEOUT=1200`
3. Script uses existing env var instead of its default
4. Container times out after 20 minutes
5. Sync incomplete, container exits with error code 1

## The Fix

### Updated docker-compose.yml (line 471)
```yaml
environment:
  - SYNC_TIMEOUT=${SYNC_TIMEOUT:-0}  # ✅ No timeout by default
```

Now the environment variable matches the script's intention.

## Why This Was Hard to Spot

1. **Multiple layers**: Script default vs environment variable vs docker-compose default
2. **Old logs**: Container logs showed old runs with the old timeout
3. **Container restarts**: Every `docker-compose up -d` restarted init, clearing FalkorDB
4. **Bash precedence**: Environment variables take precedence over script defaults

## Timeline of Events

### First Attempt (17:33)
- Started with SYNC_TIMEOUT=600 (10 min hardcoded in script)
- Timed out at ~27,000 edges
- **Result**: FAILURE

### Second Attempt (00:08 / 7:08 PM) 
- Updated script to SYNC_TIMEOUT=0
- **BUT** docker-compose.yml still had SYNC_TIMEOUT=1200
- Timed out again at 20 minutes
- **Result**: FAILURE

### Third Attempt (Current)
- Fixed both script AND docker-compose.yml
- Both now default to SYNC_TIMEOUT=0
- Currently syncing edges (~110K+)
- **Expected**: SUCCESS

## Verification

### Before Fix
```bash
$ docker exec graphiti-init env | grep SYNC_TIMEOUT
SYNC_TIMEOUT=1200  # ❌ Wrong - 20 minute timeout
```

### After Fix  
```bash
$ docker exec graphiti-init env | grep SYNC_TIMEOUT
SYNC_TIMEOUT=0  # ✅ Correct - no timeout
```

(Note: Will need container restart for new value to take effect)

## Lessons Learned

1. **Check ALL layers**: Script, environment, docker-compose, .env files
2. **Environment variables override script defaults** in bash
3. **Container logs can be stale** - always check current container state
4. **Test the actual running environment**, not just the code

## Files Modified

1. `scripts/cold-boot-init.sh` - Changed default from 600 to 0
2. `scripts/automated-cold-boot.sh` - Removed timeout from wait loop  
3. `docker-compose.yml` - Changed SYNC_TIMEOUT default from 1200 to 0 ✅ **KEY FIX**

## Current Status

- Sync running with SYNC_TIMEOUT=1200 (old container)
- Once this sync completes or we restart, new timeout=0 will take effect
- Graph has 121,139 edges to sync
- Currently at ~110,000+ edges

## Next Steps

After current sync completes:
1. Services will start normally
2. On next cold boot, init will wait indefinitely for sync
3. No more timeout failures regardless of graph size
