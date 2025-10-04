# Candidate Detection Fix - Quick Checklist

Use this checklist to systematically fix and verify the candidate detection issue.

## Pre-Flight Checks

- [ ] Docker Desktop is running
- [ ] You're in the repository root: `u:\graphiti`
- [ ] You have the latest code changes

## Step 1: Verify Code Fix

```bash
# Check the query uses inline values (not parameters)
grep "ep.created_at <" graphiti_core/utils/replay/candidate_detector.py
```

**Expected:** `AND ep.created_at < '{cutoff_iso}'`
**Not:** `AND ep.created_at < $cutoff_time`

- [ ] Code shows inline values (f-string with `{cutoff_iso}`)
- [ ] No `$cutoff_time` parameter in query

## Step 2: Verify Docker Compose Config

```bash
# Check graph service configuration
grep -A 5 "^  graph:" docker-compose.yml
```

**Expected:**
```yaml
graph:
  build:
    context: .
    dockerfile: Dockerfile
  image: graphiti-api-local:latest
```

**Not:**
```yaml
graph:
  image: ghcr.io/oculairmedia/graphiti-api:...
```

- [ ] Shows `build:` section
- [ ] Shows `image: graphiti-api-local:latest`
- [ ] No `ghcr.io` remote image reference

## Step 3: Rebuild Image

```bash
# Clean build
docker-compose build --no-cache graph
```

**Watch for:**
- Build steps executing (not just "pulling image")
- No errors during build
- "Successfully tagged graphiti-api-local:latest"

- [ ] Build completed without errors
- [ ] Took 2-5 minutes (not instant)
- [ ] Shows "Successfully tagged" message

## Step 4: Verify Image Created

```bash
# Check image exists and is recent
docker images | grep graphiti-api-local
```

**Expected:**
```
graphiti-api-local   latest   abc123def456   2 minutes ago   1.2GB
```

- [ ] Image exists
- [ ] Timestamp is recent (within last 10 minutes)
- [ ] Size is reasonable (~1-2GB)

## Step 5: Restart Service

```bash
# Stop old container
docker-compose stop graph

# Start with new image
docker-compose up -d graph
```

**Alternative (force recreate):**
```bash
docker-compose up -d --force-recreate graph
```

- [ ] Stop command completed
- [ ] Start command completed
- [ ] No errors shown

## Step 6: Verify Service Running

```bash
# Check service status
docker-compose ps graph
```

**Expected:**
```
NAME              STATUS         PORTS
graphiti-graph-1  Up 30 seconds  0.0.0.0:8003->8000/tcp
```

- [ ] Status shows "Up"
- [ ] Port 8003 is mapped
- [ ] No "Restarting" or "Exited" status

## Step 7: Check Startup Logs

```bash
# Watch logs for startup
docker-compose logs -f graph
```

**Look for:**
- "Application startup complete"
- "Uvicorn running on http://0.0.0.0:8000"
- No errors or exceptions

- [ ] Shows "Application startup complete"
- [ ] Shows Uvicorn running message
- [ ] No errors in logs

## Step 8: Test Health Endpoint

```bash
# Basic health check
curl http://localhost:8003/health
```

**Expected:** `{"status":"healthy"}` or similar

- [ ] Returns 200 OK
- [ ] Returns valid JSON
- [ ] No connection errors

## Step 9: Test Candidate Detection

```bash
# Dry run test
curl -X POST "http://localhost:8003/replay/trigger?dry_run=true" | jq
```

**Expected (SUCCESS):**
```json
{
  "dry_run": true,
  "enabled": true,
  "requested": 3456,  // Large number
  "selected_count": 10,
  "selected": [...]
}
```

**Failure (STILL BROKEN):**
```json
{
  "dry_run": true,
  "enabled": true,
  "requested": 0,  // ❌
  "selected_count": 0,
  "selected": []
}
```

- [ ] Returns 200 OK
- [ ] `requested` is > 0 (not 0)
- [ ] `selected_count` is > 0
- [ ] `selected` array has items

## Step 10: Verify Query Execution

```bash
# Check query logs
docker-compose logs graph | grep "ReplayCandidateDetector"
```

**Expected:**
```
INFO: ReplayCandidateDetector query params: stale_days=2.000000, cutoff=2025-01-30T...
INFO: ReplayCandidateDetector query: MATCH (ep:Episodic)...
INFO: ReplayCandidateDetector fetched 3456 raw rows
```

- [ ] Shows query params log
- [ ] Shows query execution log
- [ ] Shows "fetched X raw rows" where X > 0

## Troubleshooting Section

### If Step 1 Fails (Code not fixed)

```bash
# Re-apply the fix manually
# Edit graphiti_core/utils/replay/candidate_detector.py
# Change line ~181 from:
#   AND ep.created_at < $cutoff_time
# To:
#   AND ep.created_at < '{cutoff_iso}'
```

### If Step 2 Fails (Docker compose not configured)

```bash
# Edit docker-compose.yml
# Change graph service from:
#   image: ghcr.io/oculairmedia/graphiti-api:...
# To:
#   build:
#     context: .
#     dockerfile: Dockerfile
#   image: graphiti-api-local:latest
```

### If Step 3 Fails (Build errors)

```bash
# Check Dockerfile exists
ls -la Dockerfile

# Check build context
ls -la graphiti_core/
ls -la server/

# Try verbose build
docker build --no-cache --progress=plain -t graphiti-api-local:latest -f Dockerfile .
```

### If Step 5 Fails (Can't restart)

```bash
# Force stop
docker-compose kill graph

# Remove container
docker-compose rm -f graph

# Start fresh
docker-compose up -d graph
```

### If Step 9 Fails (Still returns 0)

```bash
# Check environment variables
docker exec $(docker-compose ps -q graph) env | grep REPLAY

# Should show:
# REPLAY_ENABLED=true
# REPLAY_STALE_DAYS=2

# Check database directly
docker exec -it $(docker ps | grep falkor | awk '{print $1}') redis-cli -p 6379
GRAPH.QUERY default_db "MATCH (ep:Episodic) WHERE ep.created_at IS NOT NULL RETURN count(ep)"

# Check query in logs
docker-compose logs graph | grep "ReplayCandidateDetector query:"
```

## Success Criteria

All of these must be true:

- [x] Code fix applied (inline values, not parameters)
- [x] Docker compose configured for local build
- [x] Image built successfully
- [x] Service running without errors
- [x] Health endpoint responds
- [x] Candidate detection returns `requested > 0`
- [x] Logs show query execution
- [x] Logs show "fetched X raw rows" where X > 0

## Next Steps After Success

Once all checks pass:

1. **Test manual trigger:**
   ```bash
   curl -X POST "http://localhost:8003/replay/trigger" | jq
   ```

2. **Check queue:**
   ```bash
   curl http://localhost:8093/queue/memory_replay | jq
   ```

3. **Monitor workers:**
   ```bash
   docker-compose logs -f graphiti-queued
   ```

4. **Run tests:**
   ```bash
   pytest tests/test_memory_replay_*.py -v
   ```

See `docs/MEMORY_REPLAY_REMAINING_WORK.md` for complete testing guide.

## Time Estimates

- Steps 1-2: 2 minutes (verification)
- Step 3: 2-5 minutes (build)
- Steps 4-8: 2 minutes (restart and verify)
- Steps 9-10: 1 minute (test)
- **Total: ~10 minutes**

## Quick Commands Summary

```bash
# Verify code
grep "ep.created_at <" graphiti_core/utils/replay/candidate_detector.py

# Verify config
grep -A 5 "^  graph:" docker-compose.yml

# Rebuild
docker-compose build --no-cache graph

# Restart
docker-compose up -d --force-recreate graph

# Test
curl -X POST "http://localhost:8003/replay/trigger?dry_run=true" | jq

# Check logs
docker-compose logs graph | grep "ReplayCandidateDetector"
```

## Documentation References

- **Summary:** `docs/CANDIDATE_DETECTION_SUMMARY.md`
- **Detailed Guide:** `docs/FIXING_CANDIDATE_DETECTION.md`
- **Build Guide:** `docs/LOCAL_BUILD_GUIDE.md`
- **Testing Guide:** `docs/MEMORY_REPLAY_REMAINING_WORK.md`

