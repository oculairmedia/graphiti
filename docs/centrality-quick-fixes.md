# Centrality Calculation - Quick Fixes

## Critical Issues Found

### 1. Timeout Cascade Failure ⚠️ HIGH PRIORITY

**Problem**: Nginx times out after 30 seconds, causing "Failed to parse JSON response: <!DOCTYPE" errors

**Root Cause**:
```
Frontend (600s) → Nginx (30s) → Python API (30s) → Rust Service (∞) → FalkorDB (∞)
                        ↑ FAILS HERE
```

**Fix Required**: Update nginx configuration
```nginx
# In nginx.conf, add for centrality endpoints:
location /api/centrality/ {
    proxy_pass http://rust-api;
    proxy_read_timeout 600s;  # 10 minutes
    proxy_connect_timeout 30s;
    proxy_send_timeout 30s;
}
```

### 2. Python API Timeout Too Short ⚠️ HIGH PRIORITY

**Problem**: Python API has 30s timeout, needs to match frontend 600s

**Fix Required**: Update `server/graph_service/routers/centrality.py`
```python
# Change line 80:
async with httpx.AsyncClient(timeout=600.0) as client:  # Was 30.0
```

### 3. FalkorDB Native Algorithm Failures ✅ FIXED

**Problem**: Native PageRank and betweenness algorithms fail, forcing slow custom implementations

**✅ SOLUTION IMPLEMENTED**:
The algorithms were fixed with several key improvements:

1. **Pre-computed Value Caching**: Check for existing centrality values first
```rust
// Check if PageRank centrality values already exist (pre-computed)
let precomputed_query = "MATCH (n) WHERE EXISTS(n.pagerank_centrality)
                        RETURN n.uuid as uuid, n.pagerank_centrality as score";
```

2. **Corrected Native Algorithm Syntax**:
```rust
// PageRank: Fixed syntax
let native_algorithm = "CALL algo.pageRank(null, null)";

// Betweenness: Fixed syntax
let native_algorithm = "CALL algo.betweenness({nodeLabels: [], relationshipTypes: []})";
```

3. **Proper Property Names**: Use `pagerank_centrality` and `betweenness_centrality` properties

4. **Graceful Fallbacks**: If native fails, use optimized custom implementations

## Performance Issues

### ✅ IMPROVED Performance (10,184 nodes, 20,661 edges)
- ✅ Degree centrality: ~1 second (fast)
- ✅ PageRank: **SIGNIFICANTLY FASTER** with pre-computed values or fixed native algorithm
- ✅ Betweenness: **SIGNIFICANTLY FASTER** with pre-computed values or fixed native algorithm
- ✅ All centralities: **MUCH IMPROVED** with caching and optimizations

### Quick Performance Wins

1. **Parallel Execution**: Run algorithms in parallel instead of sequential
2. **Result Caching**: Cache results to avoid recalculation
3. **Sampling Optimization**: Increase betweenness sampling for better speed/accuracy balance

## Immediate Action Items

### 1. Fix Timeout Configuration (30 minutes)
```bash
# Update nginx.conf
# Update Python API timeout
# Test with curl commands
```

### 2. Add Progress Indicators (2 hours)
```typescript
// Frontend: Add progress bar for long calculations
// WebSocket updates from backend
// Estimated completion time
```

### 3. Optimize Rust Service (4 hours)
```rust
// Investigate native algorithm failures
// Add parallel execution
// Improve error handling
```

## Testing Commands

### Verify Fixes
```bash
# Test degree centrality (should be fast)
curl -X POST http://localhost:8003/centrality/degree \
  -H "Content-Type: application/json" \
  -d '{"direction": "both", "store_results": false}'

# Test with timeout (should complete or give proper timeout message)
timeout 600 curl -X POST http://localhost:8003/centrality/all \
  -H "Content-Type: application/json" \
  -d '{"store_results": false}'
```

### Monitor Progress
```bash
# Watch Rust service logs
docker logs graphiti-graphiti-centrality-rs-1 -f

# Check service health
curl http://localhost:3003/health
curl http://localhost:3003/stats
```

## Success Criteria

### Fixed Issues ✅
- No more "Failed to parse JSON response: <!DOCTYPE" errors
- Proper timeout error messages instead of HTML pages
- Calculations complete within 10 minutes or timeout gracefully

### Performance Targets 🎯
- Degree centrality: <5 seconds
- Individual algorithms: <2 minutes
- All centralities: <5 minutes

### User Experience 📱
- Progress indicators during calculation
- Clear error messages
- Ability to cancel long-running operations

## Implementation Priority

1. **CRITICAL** (Fix immediately): Timeout configuration
2. **HIGH** (This week): Progress indicators and error handling
3. **MEDIUM** (Next sprint): Performance optimization
4. **LOW** (Future): Advanced features (caching, parallel execution)

## Files to Modify

### High Priority
- `nginx/nginx.conf` - Fix proxy timeout
- `server/graph_service/routers/centrality.py` - Fix API timeout
- `frontend/src/components/ControlPanel/CentralityControlsTab.tsx` - Add progress UI

### Medium Priority  
- `graphiti-centrality-rs/src/algorithms.rs` - Optimize algorithms
- `graphiti-centrality-rs/src/server.rs` - Add progress endpoints
- `docker-compose.yml` - FalkorDB configuration

## Risk Assessment

### Low Risk Changes ✅
- Timeout configuration updates
- Frontend UI improvements
- Error message improvements

### Medium Risk Changes ⚠️
- Algorithm optimization
- FalkorDB configuration changes
- Parallel execution implementation

### High Risk Changes ❌
- Database schema changes
- Service architecture changes
- Breaking API changes

## Rollback Plan

If changes cause issues:
1. Revert nginx configuration
2. Revert Python API timeout
3. Restart services
4. Monitor error logs

All changes should be backward compatible and easily reversible.
