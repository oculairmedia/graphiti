# Centrality Calculation Implementation Analysis

## Overview

This document provides a comprehensive analysis of the centrality calculation implementation in Graphiti, including its architecture, performance issues, and integration points across the codebase.

## Architecture Overview

### High-Level Architecture

```
Frontend (React/TypeScript)
    ↓ HTTP API calls
Nginx Reverse Proxy (30s timeout)
    ↓ Proxy to
Python API Server (FastAPI) - Port 8003
    ↓ HTTP calls (30s timeout)
Rust Centrality Service - Port 3003
    ↓ Direct connection
FalkorDB (Redis-based graph database)
```

### Service Components

1. **Frontend UI** (`frontend/src/components/ControlPanel/CentralityControlsTab.tsx`)
   - User interface for centrality calculations
   - Supports: PageRank, Degree, Betweenness, Eigenvector, All Metrics
   - Timeout: 600 seconds (10 minutes)

2. **Python API Server** (`server/graph_service/routers/centrality.py`)
   - FastAPI endpoints that proxy to Rust service
   - Timeout: 30 seconds (causing issues)
   - Endpoints: `/centrality/{pagerank,degree,betweenness,all}`

3. **Rust Centrality Service** (`graphiti-centrality-rs/`)
   - High-performance centrality calculations
   - Uses FalkorDB native algorithms when available
   - Falls back to custom implementations
   - Target: 100-1000x faster than Python

4. **FalkorDB Database**
   - Graph storage with native algorithm support
   - Stores centrality results as node properties

## Centrality Algorithms Implemented

### 1. PageRank Centrality ✅ OPTIMIZED
- **Pre-computed Check**: First checks for existing `n.pagerank_centrality` values
- **Native**: `CALL algo.pageRank(null, null)` (fixed syntax)
- **Fallback**: Optimized custom iterative implementation
- **Performance**: **SIGNIFICANTLY IMPROVED** with caching and fixed native calls
- **Storage**: `n.pagerank_centrality`

### 2. Degree Centrality ✅ FAST
- **Implementation**: Optimized Cypher queries
- **Directions**: in, out, both
- **Query**: `MATCH (n)-[r]-() RETURN n.uuid, count(r) as degree`
- **Performance**: Fast (instant for ~10k nodes)
- **Storage**: `n.degree_centrality`

### 3. Betweenness Centrality ✅ OPTIMIZED
- **Pre-computed Check**: First checks for existing `n.betweenness_centrality` values
- **Native**: `CALL algo.betweenness({nodeLabels: [], relationshipTypes: []})` (fixed syntax)
- **Fallback**: Sampling-based approximation (50 nodes for graphs >100 nodes)
- **Performance**: **SIGNIFICANTLY IMPROVED** with caching and fixed native calls
- **Storage**: `n.betweenness_centrality`

### 4. Eigenvector Centrality
- **Implementation**: Power iteration method
- **Connectivity Analysis**: Adapts algorithm based on graph structure
- **Damping**: Uses PageRank-style damping for disconnected graphs
- **Performance**: Slow, requires convergence iterations
- **Storage**: `n.eigenvector_centrality`

### 5. Composite Importance Score
- **Formula**: Weighted combination of all metrics
- **Normalization**: All metrics normalized to [0,1] range
- **Storage**: `n.importance_score`

## Current Performance Issues

### Timeout Cascade Problem

```
Frontend: 600s timeout
    ↓
Nginx: 30s proxy_read_timeout
    ↓ (FAILS HERE)
Python API: 30s httpx timeout
    ↓
Rust Service: No timeout
    ↓
FalkorDB: Unlimited query timeout
```

**Root Cause**: Nginx times out after 30 seconds, returning HTML error page instead of JSON.

### Performance Bottlenecks

1. **FalkorDB Native Algorithm Failures**
   - Native PageRank often fails, falls back to slow custom implementation
   - Native betweenness not consistently available
   - Custom algorithms are 10-100x slower

2. **Large Graph Complexity**
   - Current test graph: ~10,184 nodes, ~20,661 edges
   - PageRank calculation: >3 minutes
   - All centralities: >5 minutes

3. **Sequential Processing**
   - Algorithms run sequentially, not in parallel
   - No caching of intermediate results
   - Full recalculation on each request

## Integration Points

### Frontend Integration

**File**: `frontend/src/api/graphClient.ts`
```typescript
// Centrality calculation methods
calculatePageRank(options)
calculateDegreeCentrality(options) 
calculateBetweennessCentrality(options)
calculateEigenvectorCentrality(options)  // New
calculateAllCentralities(options)
```

**File**: `frontend/src/components/ControlPanel/CentralityControlsTab.tsx`
- UI controls for all centrality types
- Progress indicators and error handling
- Store results option

### API Layer Integration

**File**: `server/graph_service/routers/centrality.py`
```python
# Proxy endpoints to Rust service
@router.post('/pagerank')
@router.post('/degree') 
@router.post('/betweenness')
@router.post('/all')
```

**Timeout Configuration**:
```python
async with httpx.AsyncClient(timeout=30.0) as client:
    # This 30s timeout is too short for large graphs
```

### Rust Service Integration

**File**: `graphiti-centrality-rs/src/server.rs`
```rust
// HTTP endpoints
.route("/centrality/pagerank", post(pagerank_endpoint))
.route("/centrality/degree", post(degree_endpoint)) 
.route("/centrality/betweenness", post(betweenness_endpoint))
.route("/centrality/all", post(all_centralities_endpoint))
```

**File**: `graphiti-centrality-rs/src/algorithms.rs`
- Native FalkorDB algorithm calls
- Custom fallback implementations
- Batch storage operations

### Database Integration

**Storage Schema**:
```cypher
// Node properties for centrality scores
n.pagerank_centrality: float
n.degree_centrality: float  
n.betweenness_centrality: float
n.eigenvector_centrality: float
n.importance_score: float
```

**Batch Updates**:
```cypher
UNWIND [...] AS nodeData
MATCH (n {uuid: nodeData.uuid})
SET n.pagerank_centrality = nodeData.pagerank,
    n.degree_centrality = nodeData.degree,
    n.betweenness_centrality = nodeData.betweenness,
    n.eigenvector_centrality = nodeData.eigenvector,
    n.importance_score = nodeData.importance
```

## Error Handling and Fallbacks

### Service Fallback Chain

1. **Rust Service Failure** → Python implementation (not implemented)
2. **Native Algorithm Failure** → Custom implementation
3. **Timeout** → Proper error response (recently fixed)
4. **Database Connection** → Service health checks

### Error Types

1. **Timeout Errors**: `{"detail": "Centrality calculation timed out"}`
2. **Database Errors**: Connection failures, query errors
3. **Algorithm Errors**: Convergence failures, invalid parameters
4. **Network Errors**: Service unavailable, proxy failures

## Recent Improvements

### Frontend Enhancements
- ✅ Added eigenvector centrality option
- ✅ Increased timeout to 10 minutes
- ✅ Disabled virtualization limits
- ✅ Better error handling

### API Improvements  
- ✅ Proper timeout error responses
- ✅ JSON error format (no more HTML errors)
- ⚠️ Still has 30s timeout bottleneck

### Performance Optimizations
- ✅ Batch database updates (100 nodes per batch)
- ✅ Sampling for betweenness (50 nodes for large graphs)
- ⚠️ Native algorithm reliability issues remain

## Critical Issues Requiring Resolution

### 1. Timeout Configuration Mismatch
**Problem**: Nginx 30s timeout kills long-running calculations
**Solution**: Increase nginx `proxy_read_timeout` for centrality endpoints

### 2. Native Algorithm Reliability
**Problem**: FalkorDB native algorithms fail unpredictably
**Solution**: Investigate FalkorDB configuration and algorithm parameters

### 3. Performance Optimization
**Problem**: Custom algorithms too slow for production use
**Solutions**: 
- Parallel algorithm execution
- Result caching
- Incremental updates
- Graph partitioning

### 4. User Experience
**Problem**: No progress indication for long calculations
**Solutions**:
- WebSocket progress updates
- Estimated completion times
- Cancellation support

## Recommended Next Steps

1. **Immediate Fixes**
   - Update nginx timeout configuration
   - Investigate FalkorDB native algorithm failures
   - Add progress indicators

2. **Performance Optimization**
   - Implement result caching
   - Add parallel algorithm execution
   - Optimize for incremental updates

3. **Monitoring and Observability**
   - Add performance metrics
   - Algorithm success/failure tracking
   - User experience analytics

4. **Testing and Validation**
   - Performance benchmarks
   - Algorithm accuracy validation
   - Load testing with various graph sizes

## Configuration Reference

### Timeout Settings Across Services

| Service | Component | Current Timeout | Recommended |
|---------|-----------|----------------|-------------|
| Frontend | API Client | 600s (10 min) | ✅ Adequate |
| Nginx | proxy_read_timeout | 30s | ⚠️ 600s needed |
| Python API | httpx.AsyncClient | 30s | ⚠️ 600s needed |
| Rust Service | No timeout | ∞ | ✅ OK |
| FalkorDB | Query timeout | ∞ | ⚠️ Consider limits |

### Environment Variables

```bash
# Rust Centrality Service
FALKORDB_HOST=falkordb
FALKORDB_PORT=6379
GRAPH_NAME=graphiti_migration
BIND_ADDR=0.0.0.0:3003

# Python API Server
USE_RUST_CENTRALITY=true
RUST_CENTRALITY_URL=http://graphiti-centrality-rs:3003

# Frontend
CENTRALITY_TIMEOUT=600000  # 10 minutes in milliseconds
```

### FalkorDB Configuration

```redis
# Recommended FalkorDB settings for centrality
GRAPH.CONFIG SET THREAD_COUNT 8
GRAPH.CONFIG SET CACHE_SIZE 200
GRAPH.CONFIG SET TIMEOUT_DEFAULT 300000  # 5 minutes
```

## Performance Benchmarks

### Current Performance (10k nodes, 20k edges)

| Algorithm | Native | Custom | Status |
|-----------|--------|--------|--------|
| Degree | ~1s | ~1s | ✅ Fast |
| PageRank | Fails | ~180s | ⚠️ Slow |
| Betweenness | Fails | ~240s | ⚠️ Very Slow |
| Eigenvector | N/A | ~120s | ⚠️ Slow |
| All Combined | N/A | ~300s+ | ❌ Too Slow |

### Target Performance Goals

| Graph Size | All Centralities | Individual Metrics |
|------------|------------------|-------------------|
| 1k nodes | <10s | <5s |
| 10k nodes | <60s | <30s |
| 100k nodes | <300s | <120s |

## Troubleshooting Guide

### Common Error Messages

1. **"Centrality calculation timed out"**
   - Cause: Calculation exceeds timeout limits
   - Solution: Increase timeouts or optimize algorithms

2. **"Failed to parse JSON response: <!DOCTYPE"**
   - Cause: Nginx timeout returning HTML error page
   - Solution: Fix nginx proxy_read_timeout

3. **"Rust centrality service failed, falling back to Python"**
   - Cause: Rust service unavailable or erroring
   - Solution: Check Rust service logs and connectivity

4. **"FalkorDB connection error"**
   - Cause: Database connectivity issues
   - Solution: Verify FalkorDB service health

### Diagnostic Commands

```bash
# Check service health
curl http://localhost:3003/health
curl http://localhost:8003/docs

# Test simple calculation
curl -X POST http://localhost:3003/centrality/degree \
  -H "Content-Type: application/json" \
  -d '{"direction": "both", "store_results": false}'

# Check graph statistics
curl http://localhost:3003/stats

# Monitor calculation progress
docker logs graphiti-graphiti-centrality-rs-1 -f
```

## Code Examples

### Frontend Usage

```typescript
// Calculate specific centrality type
const result = await graphClient.calculatePageRank({
  damping_factor: 0.85,
  iterations: 20,
  store_results: true
});

// Calculate all centralities
const allResults = await graphClient.calculateAllCentralities({
  store_results: true
});

// Handle errors
try {
  const result = await graphClient.calculateEigenvectorCentrality();
} catch (error) {
  if (error.message.includes('timed out')) {
    // Handle timeout
  }
}
```

### Direct API Usage

```bash
# PageRank calculation
curl -X POST http://localhost:8003/centrality/pagerank \
  -H "Content-Type: application/json" \
  -d '{
    "damping_factor": 0.85,
    "iterations": 20,
    "store_results": false
  }'

# All centralities with storage
curl -X POST http://localhost:8003/centrality/all \
  -H "Content-Type: application/json" \
  -d '{"store_results": true}'
```

### Rust Service Direct Access

```bash
# Bypass Python API for testing
curl -X POST http://localhost:3003/centrality/degree \
  -H "Content-Type: application/json" \
  -d '{"direction": "both", "store_results": false}'
```

## Future Enhancements

### Short Term (1-2 weeks)
- Fix timeout configuration cascade
- Improve native algorithm reliability
- Add progress indicators

### Medium Term (1-2 months)
- Implement result caching
- Add parallel algorithm execution
- Optimize for incremental updates

### Long Term (3-6 months)
- Graph partitioning for massive graphs
- Machine learning-based centrality approximation
- Real-time centrality updates

## Conclusion

The centrality calculation system is architecturally sound but suffers from performance and timeout configuration issues. The primary bottlenecks are:

1. **Timeout mismatches** between services
2. **Unreliable native algorithms** forcing slow fallbacks
3. **Sequential processing** without optimization

Addressing these issues will significantly improve user experience and enable centrality calculations on larger graphs. The recent addition of eigenvector centrality and improved error handling are positive steps toward a more robust system.
