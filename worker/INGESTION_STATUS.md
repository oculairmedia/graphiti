# Ingestion Status Report

## Current Status: ✅ **HEALTHY**

### Recent Performance (Last 10 Minutes)
- **Successful Episodes**: 5
- **Failed Episodes**: 0
- **Success Rate**: 100%
- **Average Processing Time**: ~130 seconds per episode

### Latest Successfully Processed Episodes
1. Episode `c48ce336` - Completed in 127.85s (02:59:28)
2. Episode `3f1b9800` - Completed in 96.69s (02:57:57)
3. Episode `13aec733` - Completed in 86.11s (02:57:20)
4. Episode `0d0fa445` - Completed in 229.86s (02:56:20)
5. Episode `682a3d61` - Successfully saved (02:55:54)

### Active Processing
Currently processing episode `fb3a2bab` - extracting edges (as of 02:59:49)

## Error Analysis

### Previous Errors (Resolved)
**Time**: 02:49 - 02:52 (7-10 minutes ago)
**Type**: Unique constraint violation on Entity nodes
**Count**: 3 failed tasks
**Status**: ✅ **No longer occurring**
**Impact**: Minimal - episodes are now processing successfully

### Ongoing Minor Issues
**Type**: Mandatory constraint violation during node merge
**Error**: Edge missing uuid property during deduplication
**Impact**: Low - episodes still complete successfully
**Frequency**: Occasional

## Vector Type Mismatch Status
✅ **RESOLVED** - All embeddings properly wrapped with `vecf32()`
- No "Type mismatch" errors in logs
- Edge invalidation working correctly
- Vector similarity queries functioning properly

## Logging Status
✅ **ACTIVE** - FalkorDB query logging enabled
- Query text visible (truncated to 2000 chars)
- Parameters logged with embedding summarization
- Format: `<vector len=2560 sample=[...]>`

## Database Health
After isolated node cleanup:
- **Total Nodes**: 14,922
- **Total Edges**: 44,509
- **Isolated Nodes**: 0 ✅

## Recommendations

1. ✅ **Continue monitoring** - System is operating normally
2. 🔍 **Investigate unique constraint violations** (if they recur)
3. 🔧 **Fix edge uuid assignment** in node merge operations (low priority)
4. 📊 **Track processing metrics** over time for optimization

## Metrics to Monitor

```bash
# Check recent success rate
docker compose logs graphiti-worker --since 10m | grep -c "Successfully saved"

# Check for errors
docker compose logs graphiti-worker --since 10m | grep -E "ERROR|Failed"

# Monitor current activity
docker compose logs -f graphiti-worker | grep -E "Processing episode|Successfully saved"
```

---
**Report Generated**: October 7, 2025 - 03:01 UTC  
**Status**: All systems operational ✅
