# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --status in_progress  # Claim work
bd close <id>         # Complete work
bd sync               # Sync with git
```

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds



<!-- HULY-PROJECT-INFO -->
# Project Context

## Huly Integration
- **Project Code**: `GRAPH`
- **Project Name**: Graphiti Knowledge Graph Platform
- **Letta Agent ID**: `agent-80ac3bb8-1087-412d-a19c-7c8c6aeb5916`

## Project Agent Role
This project has an assigned **Letta PM Agent** (`agent-80ac3bb8-1087-412d-a19c-7c8c6aeb5916`) that acts as the senior developer and project manager. This agent:
- **Understands the full architecture** and codebase context for this project
- **Tracks all ongoing work** via memory blocks synced from Huly issues
- **Maintains project history** including past decisions, patterns, and lessons learned
- **Can provide guidance** on implementation approaches, code patterns, and potential pitfalls

When working on this project, you should:
- **Report completed work** to the PM agent so it stays informed of changes
- **Ask for architectural guidance** if you're unsure about implementation approach
- **Share important discoveries** that future work might benefit from

## Workflow Instructions
1. **Before starting work**: Search Huly for related issues using `huly-mcp` with project code `GRAPH`
2. **Issue references**: All issues for this project use the format `GRAPH-XXX` (e.g., `GRAPH-123`)
3. **On task completion**: Report to this project's Letta agent via `matrix-identity-bridge` using `talk_to_agent` or `letta_chat`
4. **Memory**: Store important discoveries in Graphiti with `graphiti-mcp_add_memory`

### Reporting Example
```json
{
  "operation": "talk_to_agent",
  "agent": "agent-80ac3bb8-1087-412d-a19c-7c8c6aeb5916",
  "message": "Completed task GRAPH-XXX: [summary of work done]"
}
```

<!-- END-HULY-PROJECT-INFO -->

# Graphiti Stack Agent Instructions

## CRITICAL: Safe Disk Cleanup

### ⚠️ NEVER USE THESE COMMANDS:
```bash
# ❌ DANGEROUS - will delete FalkorDB data volume
docker system prune --volumes
docker volume prune

# ❌ DANGEROUS - may delete data volumes
docker system prune -a --volumes
```

### ✅ USE THIS INSTEAD:
```bash
# Safe cleanup script - protects all data volumes
/opt/stacks/graphiti/scripts/safe_cleanup.sh

# Preview what would be cleaned
/opt/stacks/graphiti/scripts/safe_cleanup.sh --dry-run

# Aggressive cleanup (includes build cache) but still protects data
/opt/stacks/graphiti/scripts/safe_cleanup.sh --all
```

### 🛡️ FalkorDB Protection Commands:
```bash
# Create protection copy OUTSIDE Docker (survives volume prune)
/opt/stacks/graphiti/scripts/protect_falkordb.sh

# Check protection status
/opt/stacks/graphiti/scripts/protect_falkordb.sh --status

# Restore from protection copy (if volume was deleted)
/opt/stacks/graphiti/scripts/protect_falkordb.sh --restore
```

### Protected Volumes (NEVER manually delete):
- `graphiti_falkordb_data` - FalkorDB graph data (PRIMARY DATA STORE)
- `graphiti_visualizer_duckdb` - Visualizer cache
- `graphiti_queued_data` - Queue service data

---

## CRITICAL: Data Persistence Rules

### ✅ FalkorDB is the Primary Data Store (Updated Jan 2026)

**FalkorDB** (`falkordb` service):
- **PRIMARY AND ONLY DATA STORE** - all data persists via RDB snapshots
- Restarts reload from RDB in **~2 minutes**
- RDB snapshots occur every 5 minutes (if changes) or every 1 minute (if 100+ changes)
- Memory limit: 16GB to handle RDB reload overhead
- Runtime `maxmemory` is 8GB (reload can temporarily use more)
- Check data status: `redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" --csv`
- **Current size (Jan 2026)**: ~66K nodes, ~224K edges
- Historical note: Started with 48K nodes, 121K edges (Dec 2025 from original Neo4j migration)

### Deprecated Services (No Longer Used)
- **Neo4j** - Was previously source of truth, now deprecated
- **graphiti-sync-rs** - Was Neo4j → FalkorDB sync service, no longer needed

## Service Architecture (Simplified Jan 2026)

### Current Stack
```
falkordb (persisted) → graph-visualizer-rust → frontend/nginx
                    → graph (API) → graphiti-worker
```

**FalkorDB is now standalone** - no sync dependencies, no init containers needed for data.

### Safe Commands

**ALWAYS check status before taking action:**
```bash
docker-compose ps
```

**To view logs without affecting services:**
```bash
docker-compose logs <service-name>
docker-compose logs --tail=20 <service-name>
docker-compose logs -f <service-name>  # Follow logs
```

**SAFE operations (no dependencies, no data loss):**
```bash
# Frontend - safe to restart anytime
docker-compose restart frontend
docker restart graphiti-frontend-1

# API server - persists to FalkorDB
docker-compose restart graph
docker restart graphiti-graph-1
```

**NOW SAFER with persistence (but still use caution):**
```bash
# ⚠️ FalkorDB restart is now SAFE - data persists and reloads in ~2 minutes
docker-compose restart falkordb
docker restart graphiti-falkordb-1

# ❌ Still avoid - will recreate entire dependency chain unnecessarily
docker-compose up -d graph-visualizer-rust

# ❌ Still avoid - will recreate init container and may trigger unnecessary sync
docker-compose up -d graphiti-init
```

**If visualizer needs restart (use container name, NOT service name):**
```bash
# ✅ SAFE - restarts only the visualizer container
docker restart graphiti-graph-visualizer-rust-1

# ❌ DANGEROUS - restarts entire dependency chain
docker-compose restart graph-visualizer-rust
```

## Graph Data Monitoring

### Check FalkorDB Counts
```bash
# Edge count
redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r) as edge_count" --csv
# Node count
redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n) as node_count" --csv
```
Current (Jan 2026): ~66K nodes, ~224K edges
Historical baseline (Dec 2025): 48K nodes, 121K edges

## Service-Specific Notes

### graph-visualizer-rust (Port 3000)
- **Image**: `graphiti-rust-visualizer:incremental-updates` (local, not pulled from registry)
- **State**: Depends on FalkorDB data
- **Batch size**: 5000 edges (set in src/main.rs line 399)
- **DuckDB cache**: 17GB stored in `visualizer_duckdb` volume
- **To rebuild**: Must use `docker build` in `graph-visualizer-rust/` directory
- **Restart safely**: `docker restart graphiti-graph-visualizer-rust-1`
- **Healthcheck**: 1 hour start_period + 100 retries (15s interval) = up to 85 minutes to become healthy
- **Initial load time**: Loads ALL edges from FalkorDB into memory on startup - scales with graph size
- **Why healthcheck is long**: After sync completes, visualizer must load ALL edges (currently 224K+) and build DuckDB cache before becoming healthy

### FalkorDB (Port 6379)
- **Database name**: `graphiti_migration`
- **Protocol**: Redis-compatible
- **Indexes**: UUID indexes exist on all node/edge types (RANGE indexes)
- **Persistence**: RDB snapshots to `falkordb_data` volume
- **Memory**: 16GB limit, 8GB runtime maxmemory
- **Performance**: Queries scale with graph size (currently 224K+ edges)

### Frontend (Port 8085)
- React + TypeScript + Vite
- Connects directly to Rust visualizer (port 3000)
- Safe to restart anytime
- **Depends on**: graph-visualizer-rust being healthy
- **Note**: If created but not started after stack restart, manually start with `docker start graphiti-frontend-1`

### Nginx (Ports 8088, 8443)
- Reverse proxy for graph API and visualizer
- Safe to restart anytime
- **Depends on**: graph-visualizer-rust being healthy
- **Note**: If created but not started after stack restart, manually start with `docker start graphiti-nginx-1`

### Python API (Port 8003)
- Used for data ingestion only
- Does NOT serve visualization data
- Safe to restart (persists to FalkorDB)

## Common Workflows

### 1. After FalkorDB Restart
```bash
# Check data loaded correctly (should match expected counts)
redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" --csv

# Data reloads from RDB in ~2 minutes
# If count is 0, check FalkorDB logs for RDB load errors
docker-compose logs --tail=50 falkordb
```

### 2. Checking Visualizer Status
```bash
# Is it running and healthy?
docker-compose ps graph-visualizer-rust

# Check logs for errors
docker-compose logs --tail=50 graph-visualizer-rust

# Access visualization
open http://localhost:3000
```

### 3. Safe Visualizer Restart
```bash
# Method 1: Docker restart (preserves other services)
docker restart graphiti-graph-visualizer-rust-1

# Method 2: Stop and start individually
docker stop graphiti-graph-visualizer-rust-1
docker start graphiti-graph-visualizer-rust-1
```

## Environment Variables

Key variables from docker-compose.yml:
- `FALKORDB_HOST=falkordb` (internal Docker network)
- `FALKORDB_PORT=6379`
- `FALKORDB_DATABASE=graphiti_migration`
- `NODE_LIMIT=100000`
- `EDGE_LIMIT=100000`
- `CACHE_ENABLED=false` (for visualizer)
- `NEO4J_USER=neo4j`
- `NEO4J_PASSWORD=graphiti123`

## Troubleshooting

### Nginx/Frontend Not Starting After Stack Restart
**Symptom**: After `docker-compose up`, nginx and frontend show "Created" status but never start

**Cause**: They depend on visualizer being healthy, but visualizer's healthcheck had insufficient time (was 105s, now 85 minutes). If visualizer takes too long to load graph data, it never becomes healthy, so nginx/frontend never start.

**Fix Applied**: 
- Increased visualizer healthcheck `start_period` from 30s to 3600s (1 hour)
- Increased healthcheck `retries` from 5 to 100 (25 more minutes)
- Total: Up to 85 minutes for visualizer to become healthy after loading large graphs

**Immediate Workaround**: If they're stuck in "Created" state:
```bash
docker start graphiti-nginx-1 graphiti-frontend-1
```

### Visualizer Shows Incomplete Data
**Symptom**: Frontend shows far fewer edges than expected

**Causes**:
1. FalkorDB RDB not fully loaded yet (wait ~2 minutes after restart)
2. DuckDB cache stale (delete and let it rebuild)
3. Visualizer started before FalkorDB finished loading

**Fix**:
1. Verify data loaded: `redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" --csv`
2. If count is correct, restart visualizer: `docker restart graphiti-graph-visualizer-rust-1`

### FalkorDB OOM (Out of Memory)
**Symptom**: FalkorDB container restarts, queries fail

**Fix**: FalkorDB memory limit is 16GB in docker-compose. With 224K+ edges and 66K+ nodes, this should be sufficient. If OOM occurs, increase memory limit in docker-compose.yml.

## Temporal Integration

Graphiti supports two modes of Temporal integration:

### 1. Temporal Visibility (Observability Only)

**Status**: Production-ready. Signal-based visibility for the existing ingestion pipeline.

When enabled, the existing `add_episode_resilient()` pipeline emits signals to a Temporal workflow for observability. The existing pipeline remains authoritative—Temporal just watches.

**Environment Variables:**
```bash
TEMPORAL_VISIBILITY_ENABLED=true
TEMPORAL_VISIBILITY_ADDRESS=192.168.50.90:7233
TEMPORAL_VISIBILITY_NAMESPACE=graphiti
TEMPORAL_VISIBILITY_TASK_QUEUE=graphiti-visibility
TEMPORAL_VISIBILITY_RPC_TIMEOUT_SECONDS=0.5
```

**Enable:**
```bash
docker compose --profile temporal up -d graphiti-temporal-visibility-worker
docker restart graphiti-graphiti-worker-1
```

### 2. Temporal Ingestion (Full Workflow)

**Status**: Production-ready (Jan 2026). Each ingestion stage runs as a Temporal Activity with full retry/visibility.

When enabled, the queue worker routes ALL episode ingestion through Temporal instead of calling `add_episode_resilient()` directly. Each stage (extract_nodes, resolve_nodes, extract_edges, resolve_edges_and_persist) is a separate Temporal Activity.

**Environment Variables:**
```bash
TEMPORAL_INGESTION_ENABLED=true
TEMPORAL_VISIBILITY_ADDRESS=192.168.50.90:7233
TEMPORAL_VISIBILITY_NAMESPACE=graphiti
TEMPORAL_INGESTION_WORKFLOW_PREFIX=ingest-episode-

# Legacy single-queue mode (default if staged queues are NOT enabled)
TEMPORAL_INGESTION_TASK_QUEUE=graphiti-ingestion

# Staged queue mode (enable by setting ANY of these vars)
TEMPORAL_INGESTION_WORKFLOW_TASK_QUEUE=graphiti-ingestion-workflow
TEMPORAL_INGESTION_EXTRACT_TASK_QUEUE=graphiti-ingestion-extract
TEMPORAL_INGESTION_RESOLVE_TASK_QUEUE=graphiti-ingestion-resolve
TEMPORAL_INGESTION_EDGE_TASK_QUEUE=graphiti-ingestion-edge
TEMPORAL_INGESTION_PERSIST_TASK_QUEUE=graphiti-ingestion-persist

# Rate Limiting (prevents LLM API flooding under load)
TEMPORAL_MAX_CONCURRENT_WORKFLOW_TASKS=10   # Max workflows polling concurrently
TEMPORAL_MAX_CONCURRENT_LOCAL_ACTIVITIES=5  # Max local activities
TEMPORAL_RATE_LIMIT_POST_LLM_DELAY=0.0      # Seconds to wait after LLM-heavy activities
TEMPORAL_RATE_LIMIT_INTER_ACTIVITY_DELAY=0.0 # Seconds between any activities

# Legacy (single queue) activity limit
TEMPORAL_MAX_CONCURRENT_ACTIVITIES=5        # Max activities running concurrently (legacy)

# Staged per-activity concurrency limits
TEMPORAL_EXTRACT_MAX_CONCURRENT_ACTIVITIES=3
TEMPORAL_RESOLVE_MAX_CONCURRENT_ACTIVITIES=3
TEMPORAL_EDGE_MAX_CONCURRENT_ACTIVITIES=2
TEMPORAL_PERSIST_MAX_CONCURRENT_ACTIVITIES=5

# Workflow Timeout (increase if large backlogs cause timeouts)
TEMPORAL_INGESTION_WORKFLOW_TIMEOUT_HOURS=8  # Default 8 hours per workflow
```

**Rate Limiting Strategy:**
- `TEMPORAL_MAX_CONCURRENT_ACTIVITIES=5` is the primary knob in legacy mode
- In staged mode, tune `TEMPORAL_EXTRACT/RESOLVE/EDGE/PERSIST_MAX_CONCURRENT_ACTIVITIES`
- For rate-limited APIs (429 errors), drop extract/resolve/edge to 1-2
- `TEMPORAL_RATE_LIMIT_POST_LLM_DELAY=2.0` adds 2-second delay after each LLM activity

**Enable (Legacy Single Queue):**
```bash
docker compose --profile temporal up -d graphiti-temporal-ingestion-worker
# Ensure TEMPORAL_INGESTION_ENABLED=true in .env, then:
docker compose up -d graphiti-worker
```

**Enable (Staged Queues + One Worker Per Stage):**
```bash
# During migration (keep legacy worker to drain old workflows)
docker compose --profile temporal --profile temporal-staged up -d

# After migration completes (legacy drained)
docker compose --profile temporal-staged up -d

# Ensure TEMPORAL_INGESTION_ENABLED=true in .env, then:
docker compose up -d graphiti-worker
```

**Migration (Staged Queues):**
- Strategy A (safe): run both `temporal` and `temporal-staged` profiles until legacy queue drains, then stop legacy worker.
- Strategy B (fast): cancel + requeue old workflows using `scripts/migrate_to_staged_queues.py`.

```bash
# Dry run migration (no changes)
python3 scripts/migrate_to_staged_queues.py --dry-run --limit 10

# Migrate first 100 workflows
python3 scripts/migrate_to_staged_queues.py --limit 100 --force
```

**Workflow ID Format:** `ingest-episode-<episode_uuid>`

**Activities:**
- `extract_nodes` - Entity extraction via DSPy/LLM
- `resolve_nodes` - Node deduplication and resolution
- `extract_edges` - Relationship extraction
- `resolve_edges_and_persist` - Edge resolution and FalkorDB persistence

### Architecture

```
Mode 1: Visibility Only (TEMPORAL_VISIBILITY_ENABLED=true)
─────────────────────────────────────────────────────────
Queue → graphiti-worker → add_episode_resilient() → FalkorDB
                              │
                              └─ signals ──▶ Temporal (visibility only)

Mode 2: Full Temporal (TEMPORAL_INGESTION_ENABLED=true)  
──────────────────────────────────────────────────────
Queue → graphiti-worker → Temporal Workflow → Activities → FalkorDB
                              │
                              └─ Full observability, retries, history
```

### Verify Temporal Workflows

- **Web UI**: http://192.168.50.90:8080 (namespace: `graphiti`)
- **Worker logs**: `docker logs -f graphiti-graphiti-temporal-ingestion-worker-1`

### Troubleshooting

- **DSPy async error**: Fixed in Jan 2026. The `configure_lm()` function is now idempotent and handles async context safely.
- **Rate limits**: LLM rate limits may cause activity retries—this is expected. Temporal will retry with backoff.
- **Worker not routing to Temporal**: Ensure `TEMPORAL_INGESTION_ENABLED=true` is set AND the worker container was recreated (not just restarted).
- Set appropriate timeouts (startToCloseTimeout, scheduleToCloseTimeout)

Full implementation guide will be added to this file once infrastructure is complete (graphiti-37d).

---

## File Locations

### Key Configuration Files
- `/opt/stacks/graphiti/docker-compose.yml` - Main orchestration
- `/opt/stacks/graphiti/.env` - Environment variables
- `/opt/stacks/graphiti/graph-visualizer-rust/src/main.rs` - Visualizer code (batch size line 399)
- `/opt/stacks/graphiti/temporal/` - Temporal workflows (when implemented)

### Data Volumes
- `falkordb_data` - FalkorDB RDB snapshots (PRIMARY DATA - NEVER DELETE)
- `visualizer_duckdb` - DuckDB cache (safe to delete, will rebuild)

## Before Any Docker Command

**MANDATORY CHECKS - DO THIS EVERY TIME:**

1. **Check if service is already running:**
   ```bash
   docker-compose ps | grep <service-name>
   ```
   - If already running and healthy → DON'T restart it!

2. **Check dependency chains in docker-compose.yml:**
   - Does the service have `depends_on`?
   - Will this cascade to falkordb or graphiti-init?
   - If yes → **STOP and ask user permission**

3. **Understand the impact:**
   - Restarting FalkorDB = ~2 minutes reload from RDB (data is safe)
   - Use `docker restart` for individual containers to avoid dependency chain issues

**SAFE PATTERN:**
```bash
# 1. Check first
docker-compose ps graph-visualizer-rust

# 2. If already running, use container name to restart
docker restart graphiti-graph-visualizer-rust-1

# 3. NEVER use docker-compose for services with dependencies
# ❌ docker-compose up -d graph-visualizer-rust
# ❌ docker-compose restart graph-visualizer-rust
```

**WHEN IN DOUBT:**
- Use `docker restart <container-name>` instead of `docker-compose`
- Use `docker-compose ps` to check status before acting
- **ASK THE USER** before any operation that might restart databases or init containers
