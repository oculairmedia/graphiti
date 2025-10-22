# Centrality 502 Error Fix

## Problem Description

The frontend was experiencing 502 Bad Gateway errors when trying to calculate centrality metrics, with error messages like:

```
Failed to load resource: the server responded with a status of 502 (Bad Gateway)
Centrality calculation failed: Error: API request failed after 1 attempts to /api/centrality/all: Failed to parse JSON response: Unexpected token '<', "<!DOCTYPE "... is not valid JSON
```

## Root Cause Analysis

The error flow was:
1. Frontend calls `/api/centrality/*` endpoints
2. Nginx routes to `graph-visualizer-rust:3000` 
3. Graph-visualizer-rust tries to proxy to `graphiti-centrality-rs:3003`
4. **Connection fails** → 502 error → HTML error page returned
5. Frontend tries to parse HTML as JSON → "Unexpected token '<', "<!DOCTYPE"" error

## Issues Identified

1. **Missing Environment Variable**: The `graph-visualizer-rust` service was missing the `CENTRALITY_SERVICE_URL` environment variable
2. **Service Dependency**: The graph-visualizer-rust service wasn't configured to wait for the centrality service to be healthy
3. **Service Communication**: The centrality service may not have been running or accessible

## Solution Applied

### 1. Added Missing Environment Variable

Added `CENTRALITY_SERVICE_URL` to the `graph-visualizer-rust` service in `docker-compose.yml`:

```yaml
environment:
  - FALKORDB_HOST=${FALKORDB_HOST:-falkordb}
  - FALKORDB_PORT=${FALKORDB_PORT:-6379}
  - GRAPH_NAME=${FALKORDB_DATABASE:-graphiti_migration}
  - NODE_LIMIT=${NODE_LIMIT:-100000}
  - EDGE_LIMIT=${EDGE_LIMIT:-100000}
  - MIN_DEGREE_CENTRALITY=${MIN_DEGREE_CENTRALITY:-0}
  - CACHE_ENABLED=${CACHE_ENABLED:-true}
  - RUST_LOG=${RUST_LOG:-info}
  - CENTRALITY_SERVICE_URL=${RUST_CENTRALITY_URL:-http://graphiti-centrality-rs:3003}  # ← ADDED
```

### 2. Added Service Dependency

Updated the `depends_on` section to ensure the centrality service is healthy before starting:

```yaml
depends_on:
  falkordb:
    condition: service_healthy
  graphiti-centrality-rs:  # ← ADDED
    condition: service_healthy
```

## Technical Details

- The `graph-visualizer-rust` service acts as a proxy for centrality calculations
- It expects the `CENTRALITY_SERVICE_URL` environment variable to know where to forward requests
- Without this variable, it falls back to a default URL, but service dependencies weren't properly configured
- The centrality service runs on `graphiti-centrality-rs:3003` within the Docker network

## Next Steps

After applying these changes:

1. Restart the Docker services: `docker-compose down && docker-compose up -d`
2. Verify the centrality service is healthy: `docker-compose ps graphiti-centrality-rs`
3. Test centrality calculations in the frontend
4. Monitor logs for any remaining connectivity issues

## Files Modified

- `docker-compose.yml` - Added environment variable and service dependency

## Verification

To verify the fix is working:

1. Check service health: `curl http://localhost:3000/api/centrality/health`
2. Test a centrality calculation from the frontend
3. Monitor Docker logs: `docker-compose logs -f graph-visualizer-rust graphiti-centrality-rs`

---

## Centrality Data Flow & Neo4j Synchronization

### How Centrality Updates Work

**Yes, centrality scores DO get synchronized to Neo4j!** Here's the complete data flow:

#### 1. Centrality Calculation Flow
```
Frontend → Nginx → graph-visualizer-rust → graphiti-centrality-rs → FalkorDB
```

#### 2. Storage Process
When centrality is calculated:
1. **Rust Centrality Service** calculates metrics using FalkorDB native algorithms
2. **Stores results in FalkorDB** as node properties:
   - `n.pagerank_centrality: float`
   - `n.degree_centrality: float`
   - `n.betweenness_centrality: float`
   - `n.eigenvector_centrality: float`
   - `n.importance_score: float`

#### 3. Automatic Sync to Neo4j
The **sync-service** automatically synchronizes data from FalkorDB to Neo4j:

**Current Configuration** (from `sync_service/config.yaml`):
- **Sync Direction**: `"reverse"` (FalkorDB → Neo4j)
- **Sync Interval**: Every 180 seconds (3 minutes)
- **Reverse Incremental**: `true` (only syncs changes)
- **Continuous Sync**: `true` (always running)

#### 4. Data Persistence
- **Primary Storage**: FalkorDB (fast calculations)
- **Persistent Storage**: Neo4j (permanent record)
- **Sync Method**: Automatic reverse incremental sync every 3 minutes

### Key Points

✅ **Centrality scores ARE persisted to Neo4j**
✅ **Sync happens automatically every 3 minutes**
✅ **Only changed data is synchronized (incremental)**
✅ **Both databases maintain the same centrality properties**

### Monitoring Sync Status

Check sync service health:
```bash
curl http://localhost:8082/health
curl http://localhost:8083/metrics
```

View sync logs:
```bash
docker-compose logs -f sync-service
```
