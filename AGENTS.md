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
- `graphiti_falkordb_data` - FalkorDB graph data
- `graphiti_neo4j_data` - Neo4j source of truth
- `graphiti_visualizer_duckdb` - Visualizer cache
- `graphiti_queued_data` - Queue service data

---

## CRITICAL: Data Persistence Rules

### ✅ FalkorDB NOW HAS PERSISTENCE (Updated Dec 2025)

**FalkorDB** (`falkordb` service):
- **DATA IS NOW PERSISTED** via RDB snapshots to `falkordb_data` volume
- Restarts will reload from RDB in **~2 minutes** (vs 2-3 hour sync)
- RDB snapshots occur every 5 minutes (if changes) or every 1 minute (if 100+ changes)
- Memory limit increased to 16GB to handle RDB reload overhead
- Runtime `maxmemory` is 8GB (reload can temporarily use more)
- Check data status: `redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" --csv`
- Target: 121,139 edges (from Neo4j)

**Neo4j** (`neo4j` service):
- Data IS persisted via Docker volumes
- Safe to restart, but avoid during active operations
- Source of truth for disaster recovery

**Sync Service** (`graphiti-sync-rs`):
- Runs Neo4j → FalkorDB sync on cold boot or disaster recovery
- Only needed if FalkorDB data is lost/corrupted
- Full sync takes 2-3 hours for 121K edges
- With persistence enabled, full sync should rarely be needed

## Service Dependencies and Startup Order

### Critical Dependency Chain
```
neo4j (persisted) → falkordb (in-memory) → graphiti-sync-rs → graphiti-init → graph-visualizer-rust
```

**How It Works:**
1. **graphiti-init** (alpine container) runs `cold-boot-init.sh` script
2. Script waits for Neo4j → FalkorDB sync to **complete 100%** (both nodes AND edges)
3. Script verifies sync is stable (3 consecutive checks with no changes)
4. Only then does graphiti-init exit successfully
5. **graph-visualizer-rust** depends on `graphiti-init` completing successfully
6. This ensures visualizer NEVER starts with incomplete data

**NEVER run `docker-compose up -d <service>` if that service has depends_on chains!**
- This will recreate ALL dependent services
- For FalkorDB, this means **LOSING ALL SYNCED DATA**
- Example: `docker-compose up -d graph-visualizer-rust` will restart falkordb, neo4j, sync-rs, and graphiti-init

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

# API server - persists to Neo4j
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

## Sync Progress Monitoring

### Check FalkorDB Edge Count
```bash
redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r) as edge_count" --csv
```
Target: 121,139 edges

### Check Neo4j Edge Count (source)
```bash
docker exec graphiti-neo4j-1 cypher-shell -u neo4j -p graphiti123 "MATCH ()-[r]->() RETURN count(r) as edge_count"
```

### Check Sync Service Logs
```bash
docker-compose logs --tail=30 graphiti-sync-rs
```

### Check If Sync Is Complete
Sync is complete when FalkorDB edge count == Neo4j edge count (121,139)

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
- **Why healthcheck is long**: After sync completes, visualizer must load 121K+ edges and build DuckDB cache before becoming healthy

### FalkorDB (Port 6379)
- **Database name**: `graphiti_migration`
- **Protocol**: Redis-compatible
- **Indexes**: UUID indexes exist on all node/edge types (RANGE indexes)
- **Memory**: In-memory only, no RDB persistence enabled
- **Performance**: Queries slow down as graph grows (115K+ edges)

### Neo4j (Ports 7474, 7687)
- **Auth**: `neo4j / graphiti123`
- **Database**: `neo4j` (default)
- **Persistence**: Enabled via Docker volume `neo4j_data`
- **Browser**: http://localhost:7474

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
- Safe to restart (persists to Neo4j)

## Common Workflows

### 1. After FalkorDB Restart (DATA LOSS SCENARIO)
```bash
# Check if data was lost
redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" --csv

# If count is 0 or very low, sync was lost
# Must wait 2-3 hours for re-sync
# Monitor with:
watch -n 30 'redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r) as edge_count" --csv'
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

## Performance Characteristics

### Sync Performance Degrades Over Time
- **First 50K edges**: ~500 edges/minute
- **50K-100K edges**: ~300 edges/minute  
- **100K-120K edges**: ~100 edges/minute (slow due to index updates)
- **Final 1K edges**: ~50 edges/minute

This is **NORMAL** - index update overhead increases as graph grows.

### Why Sync Slows Down (Even With Indexes)
1. Index update overhead (RELATES_TO index has 30K+ documents)
2. Memory fragmentation after hours of writes
3. Lock contention between 8 parallel workers
4. Complex relationship properties (RELATES_TO has 8 indexed fields)

**DO NOT INTERRUPT - Let it finish naturally**

## Docker Compose Gotchas

### Dependency Chain Issue
The visualizer has this in docker-compose.yml (lines 108-110):
```yaml
depends_on:
  graphiti-init:
    condition: service_completed_successfully
```

This means running `docker-compose up -d graph-visualizer-rust` will:
1. Recreate `graphiti-init`
2. Recreate all `graphiti-init` dependencies (falkordb, neo4j, sync service)
3. **LOSE ALL FALKORDB DATA**

### Safe Alternative
```bash
# Instead of docker-compose up -d, use:
docker start graphiti-graph-visualizer-rust-1

# Or restart:
docker restart graphiti-graph-visualizer-rust-1
```

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
**Symptom**: Frontend shows 690 edges instead of 121K

**Causes**:
1. FalkorDB sync incomplete (check edge count)
2. DuckDB cache stale (delete and let it rebuild)
3. Visualizer started before sync completed

**Fix**:
1. Verify sync complete: `redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" --csv`
2. If sync incomplete, wait for completion
3. If sync complete, restart visualizer: `docker restart graphiti-graph-visualizer-rust-1`

### Sync Service Stuck
**Symptom**: Edge count not increasing

**Check**:
```bash
docker-compose logs --tail=50 graphiti-sync-rs
```

If no new log entries for 5+ minutes, sync may be hung. Check FalkorDB:
```bash
docker-compose logs falkordb | tail -50
```

### FalkorDB OOM (Out of Memory)
**Symptom**: Sync crashes, FalkorDB container restarts

**Fix**: FalkorDB memory limit is 4GB in docker-compose. With 121K edges and 48K nodes, this should be sufficient. If OOM occurs, increase memory limit or reduce batch size in sync service.

## File Locations

### Key Configuration Files
- `/opt/stacks/graphiti/docker-compose.yml` - Main orchestration
- `/opt/stacks/graphiti/.env` - Environment variables
- `/opt/stacks/graphiti/graph-visualizer-rust/src/main.rs` - Visualizer code (batch size line 399)

### Data Volumes
- `neo4j_data` - Neo4j persisted data (SAFE)
- `visualizer_duckdb` - DuckDB cache (safe to delete, will rebuild)
- FalkorDB has NO volume - data is in-memory only

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
   - Restarting FalkorDB = **2-3 hours lost**
   - Restarting graphiti-init = **restarts FalkorDB too**
   - Restarting graph-visualizer-rust with compose = **restarts entire chain**

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
