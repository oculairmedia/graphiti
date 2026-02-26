<!-- VIBESYNC:project-info:START -->

# Agent Instructions

## Huly Integration

- **Project Code**: `GRAPH`
- **Project Name**: Graphiti Knowledge Graph Platform
- **Letta Agent ID**: `agent-80ac3bb8-1087-412d-a19c-7c8c6aeb5916`

## Workflow Instructions

1. **Before starting work**: Search Huly for related issues using `huly-mcp` with project code `GRAPH`
2. **Issue references**: All issues for this project use the format `GRAPH-XXX` (e.g., `GRAPH-123`)
3. **On task completion**: Report to this project's Letta agent via `matrix-identity-bridge` using `talk_to_agent`
4. **Memory**: Store important discoveries in Graphiti with `graphiti-mcp_add_memory`
<!-- VIBESYNC:project-info:END -->

<!-- VIBESYNC:reporting-hierarchy:CUSTOM -->

## Project Agent Role

This project has an assigned **Letta PM Agent** (`agent-80ac3bb8-1087-412d-a19c-7c8c6aeb5916`) that acts as the technical product manager. This agent:

- **Understands the full architecture** and codebase context for this project
- **Tracks all ongoing work** via memory blocks synced from Huly issues
- **Maintains project history** including past decisions, patterns, and lessons learned
- **Makes technical decisions** on implementation approaches, priorities, and tradeoffs

## Developer-PM Workflow (MANDATORY)

**You are the developer. The PM agent is your technical product manager.**

### When to Consult the PM (NOT the user):

| Situation                       | Action                              |
| ------------------------------- | ----------------------------------- |
| Implementation approach unclear | Ask PM for direction                |
| Multiple valid solutions exist  | Ask PM which to choose              |
| Scope/priority questions        | Ask PM to clarify                   |
| Design tradeoffs                | Present options to PM, get decision |
| Quality vs speed tradeoffs      | PM decides                          |
| Whether to create issues        | Ask PM for structure preference     |
| Technical blockers              | Report to PM first                  |

### When to Escalate to User (via PM):

- PM explicitly says "check with Emmanuel" or "need user input"
- Budget/cost decisions (API costs, infrastructure)
- Breaking changes to user-facing behavior
- PM is unavailable after reasonable wait

### Communication Pattern:

```
Developer (you) ←→ PM Agent ←→ User (Emmanuel)
```

**NEVER ask the user for technical decisions directly.** Present analysis and options to the PM. If the PM needs user input, they will reach out.

### Example Workflow:

1. You discover multiple implementation approaches
2. You message PM: "Found 3 options for X. Option A is fastest but less flexible. Option B is more work but extensible. Option C is middle ground. Which direction?"
3. PM responds with decision (or escalates to user if needed)
4. You implement based on PM's direction

### Reporting Requirements:

- **Before starting significant work**: Brief PM on approach
- **After completing work**: Report what was done
- **On blockers**: Notify PM immediately
- **Discoveries**: Share learnings that affect future work

<!-- VIBESYNC:beads-instructions:START -->

## Beads Issue Tracking

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --status in_progress  # Claim work
bd close <id>         # Complete work
bd sync               # Sync with git
```

### Beads Sync Flow (Hybrid System)

Beads uses a **hybrid sync** approach for reliability:

#### Automatic Sync (Real-time)

- `bd create`, `bd update`, `bd close` write to SQLite DB
- File watcher detects DB changes automatically
- Syncs to Huly within ~30-60 seconds

#### Git Persistence (`bd sync`)

- `bd sync` exports to JSONL and commits to git
- Required for cross-machine persistence
- Run before ending session to ensure changes are saved

### Best Practice

```bash
bd create "New task"   # Auto-syncs to Huly
bd close some-issue    # Auto-syncs to Huly
bd sync                # Git backup (recommended before session end)
```

<!-- VIBESYNC:beads-instructions:END -->

<!-- VIBESYNC:bookstack-docs:START -->
## BookStack Documentation

- **Source of truth**: [BookStack](https://knowledge.oculair.ca)
- **Local sync**: `docs/bookstack/` (read-only mirror, syncs hourly)
- **To read docs**: Check `docs/bookstack/{book-slug}/` in your project directory
- **To create/edit docs**: Use `bookstack-mcp` tools to write directly to BookStack
- **Never edit** files in `docs/bookstack/` locally — they will be overwritten on next sync
- **PRDs and design docs** must be stored in BookStack, not local markdown files
<!-- VIBESYNC:bookstack-docs:END -->

<!-- VIBESYNC:session-completion:START -->

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
<!-- VIBESYNC:session-completion:END -->

<!-- VIBESYNC:codebase-context:START -->

## Codebase Context

**Project**: Graphiti Knowledge Graph Platform (`GRAPH`)
**Path**: `/opt/stacks/graphiti`

This project's PM agent has a `codebase_ast` memory block with live structural data including:

- File counts and function counts per directory
- Key modules and their roles
- Quality signals (doc gaps, untested modules, complexity hotspots)
- Recent file changes

Ask the PM agent for architectural guidance before making significant changes.

<!-- VIBESYNC:codebase-context:END -->

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
- `dspy_training_data` - DSPy MIPROv2 training data

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
- **Current size (Feb 2026)**: ~13K nodes, ~36K edges (reduced from ~66K after duplicate UUID cleanup)
- Historical note: Started with 48K nodes, 121K edges (Dec 2025), grew to ~66K/224K, reduced to ~13K/36K after consolidation + duplicate cleanup (Feb 2026)

## Service Architecture (Simplified Jan 2026)

### Current Stack (Jan 2026 - Temporal-native)

```
falkordb (persisted) → graph-visualizer-rust → frontend/nginx
                    → graph (API) → Temporal Ingestion Workflows
                                  → Staged Workers (extract/resolve/edge/persist)
```

**Note**: Legacy queue system (graphiti-queued, graphiti-worker) deprecated in favor of Temporal.
To enable legacy queue: `docker compose --profile legacy-queue up -d`

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

Current (Feb 2026): ~13K nodes, ~36K edges
Historical: ~66K/224K (Jan 2026, pre-consolidation), 48K/121K (Dec 2025)

## Service-Specific Notes

### graph-visualizer-rust (Port 3000)

- **Image**: `ghcr.io/oculairmedia/graphiti-rust-visualizer:main` (pulled from GHCR)
- **State**: Depends on FalkorDB data
- **Batch size**: 5000 edges (set in src/main.rs line 399)
- **DuckDB cache**: 17GB stored in `visualizer_duckdb` volume
- **To rebuild**: Must use `docker build` in `graph-visualizer-rust/` directory
- **Restart safely**: `docker restart graphiti-graph-visualizer-rust-1`
- **Healthcheck**: 120s start_period + 10 retries (15s interval) = up to 4.5 minutes to become healthy
- **Initial load time**: Loads ALL edges from FalkorDB into memory on startup - scales with graph size
- **Why healthcheck is short**: Graph loads in ~2 seconds (13K nodes, 36K edges). DuckDB cache builds in <5s. Previous 85-minute healthcheck was needed for 224K+ edges.

### FalkorDB (Port 6379)

- **Database name**: `graphiti_migration`
- **Protocol**: Redis-compatible
- **Indexes**: UUID indexes exist on all node/edge types (RANGE indexes)
- **Persistence**: RDB snapshots to `falkordb_data` volume
- **Memory**: 16GB limit, 8GB runtime maxmemory
- **Performance**: Queries scale with graph size (currently ~36K edges)

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

**Cause**: They depend on visualizer being healthy, but visualizer's healthcheck had insufficient time (was 105s, increased to 85 minutes in Jan 2026, then reduced to ~4.5 minutes in Feb 2026 after graph shrunk). If visualizer takes too long to load graph data, it never becomes healthy, so nginx/frontend never start.

**Fix Applied**:

- Healthcheck `start_period` set to 120s (sufficient for current ~13K nodes / ~36K edges)
- Healthcheck `retries` set to 10 (2.5 more minutes)
- Total: Up to ~4.5 minutes for visualizer to become healthy

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

**Fix**: FalkorDB memory limit is 16GB in docker-compose. With ~36K edges and ~13K nodes, this is more than sufficient. If OOM occurs after significant graph growth, increase memory limit in docker-compose.yml.

### Vector Search Returns 0 Results / "expected Vectorf32 but was List" Error

**Symptom**: Node or edge similarity search returns 0 results, logs show:

```
Type mismatch: expected Null or Vectorf32 but was List
```

**Cause**: Some embeddings were stored as Python Lists instead of FalkorDB's native Vectorf32 type. This happens when embeddings are ingested through code paths that don't properly convert to Vectorf32. Even one corrupted embedding breaks ALL vector queries because FalkorDB fails when it encounters the List-type embedding.

**Diagnosis**:

```bash
# Run the validation script
python3 /opt/stacks/graphiti/scripts/validate_embeddings.py
```

**Fix**:

```bash
# Remove corrupted embeddings (they can be re-embedded later)
python3 /opt/stacks/graphiti/scripts/validate_embeddings.py --fix
```

**Prevention**: All embedding storage code MUST use `vecf32([...])` Cypher syntax, not raw Python lists. Example:

```python
# CORRECT - stores as Vectorf32
query = f"SET n.embedding = vecf32([{','.join(str(v) for v in embedding)}])"

# WRONG - stores as List (causes this bug)
query = f"SET n.embedding = {embedding}"
```

**History**: Fixed Jan 2026. Found 28 corrupted node embeddings and 41 corrupted edge embeddings that had been ingested as Lists.

## DSPy Training Data Collection

**Status**: Production-ready (Jan 2026). Training data stored in FalkorDB `graphiti_prompts` graph.

### Storage

Training data is stored as `TrainingExample` nodes in FalkorDB, enabling atomic concurrent writes from all Temporal workers without race conditions.

### Monitoring Collection Progress

```bash
# Check training data counts
redis-cli -p 6379 GRAPH.QUERY graphiti_prompts "MATCH (t:TrainingExample) RETURN t.task, count(t) ORDER BY t.task" --csv

# Python API
python3 -c "
import asyncio
from graphiti_core.dspy.training_storage import get_training_stats
print(asyncio.run(get_training_stats()))
"
```

### Python API

```python
from graphiti_core.dspy import (
    record_training_example,
    get_training_examples,
    sample_training_examples,
    split_train_val,
    get_training_stats,
)

# Record a training example (atomic)
await record_training_example(
    task='entity_extraction',
    inputs={'current_message': '...', 'entity_types': '...'},
    output={'extracted_entities': {...}},
)

# Retrieve examples for optimization
examples = await get_training_examples(task='entity_extraction', limit=100)

# Random sample for train/val split
train, val = await split_train_val(task='entity_extraction', val_ratio=0.2)
```

## Prompt Storage (graphiti_prompts)

**Status**: Production-ready (Jan 2026). Versioned prompt storage for DSPy optimization with hot-swapping support.

### Architecture

Prompts are stored in a separate FalkorDB graph (`graphiti_prompts`) to isolate optimization data from the main knowledge graph (`graphiti_migration`). This enables:

- Hot-swapping prompts without restart
- A/B testing of candidate prompts
- Full version history with metrics

### Schema (PromptVersion nodes)

```
(:PromptVersion {
  id: string,           // UUID
  task: string,         // 'entity_extraction', 'edge_extraction', 'node_resolution', 'summary_generation'
  version: int,         // Incrementing version number
  status: string,       // 'live', 'candidate', 'archived', 'failed'
  docstring: string,    // The signature docstring/instructions
  demos: string,        // JSON array of few-shot examples
  accuracy: float,      // Evaluation accuracy (post-optimization)
  latency_ms: float,    // Average latency
  token_count: int,     // Average token usage
  created_at: datetime,
  promoted_at: datetime,
  archived_at: datetime,
  parent_version: int,  // Version this was optimized from
  training_examples: int
})
```

### Initialize Schema

```bash
# Create schema with indexes (safe to run multiple times)
python3 scripts/init_prompt_storage.py

# Create schema AND seed initial prompts from current signatures
python3 scripts/init_prompt_storage.py --seed
```

### Query Prompts

```bash
# List all prompts
redis-cli -p 6379 GRAPH.QUERY graphiti_prompts "MATCH (p:PromptVersion) RETURN p.task, p.version, p.status ORDER BY p.task" --csv

# Get live prompt for a task
redis-cli -p 6379 GRAPH.QUERY graphiti_prompts "MATCH (p:PromptVersion {task: 'entity_extraction', status: 'live'}) RETURN p.docstring" --csv
```

### Python API (PromptRegistry)

```python
from graphiti_core.prompts.registry import PromptRegistry, PromptTask, get_prompt_registry

# Get singleton registry
registry = get_prompt_registry()

# Get live prompt (cached, 60s TTL)
prompt = await registry.get_live_prompt(PromptTask.ENTITY_EXTRACTION)
print(prompt.docstring)
print(prompt.demos)  # Few-shot examples

# Force refresh from database
prompt = await registry.get_live_prompt(PromptTask.ENTITY_EXTRACTION, force_refresh=True)

# Create optimized candidate
candidate = await registry.create_candidate(
    task=PromptTask.ENTITY_EXTRACTION,
    docstring="New optimized instructions...",
    demos=[{"input": "...", "output": "..."}],
    parent_version=1,
    training_examples=150
)

# Update metrics after evaluation
await registry.update_metrics(candidate.id, accuracy=0.92, latency_ms=450)

# Promote to live (archives previous live version)
await registry.promote_candidate(candidate.id)
```

### Status Transitions

```
candidate → live (via promote_candidate)
live → archived (automatic when new prompt promoted)
candidate → failed (if evaluation fails)
```

## MIPROv2 Optimization Pipeline (REMOVED - Feb 2026)

**Status**: Removed. The optimization trigger, workflow, and Temporal worker have been deleted.

**Why**: MIPROv2 validation showed default prompts are already near-optimal for GLM-4.5. Results: entity extraction 0% improvement, edge extraction +6.84%, node resolution +2.06%. Did not meet the pre-committed >=10% threshold on >=2 tasks. PM decided to rip out the pipeline.

**What was kept**:
- Training data collection (modules.py still records to FalkorDB)
- 21K+ training examples in `graphiti_prompts` graph
- PromptRegistry for prompt versioning
- `IngestionCounter` node still exists in FalkorDB (harmless, not incremented)

**Removed files**: `optimization_workflow.py`, `trigger.py`, `run_optimization_direct.py`, `trigger_optimization.py`, `temporal_optimization_worker.py`, `temporal-optimization` docker-compose profile.

## Temporal Integration

Graphiti supports three modes of Temporal integration:

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

### Architecture (Jan 2026 - Queue Deprecated)

```
Current: Direct Temporal (TEMPORAL_INGESTION_ENABLED=true)
──────────────────────────────────────────────────────────
API (/api/temporal/messages) → Temporal Workflow → Staged Workers → FalkorDB
                                    │
                                    └─ Full observability, retries, history

Legacy (deprecated, use --profile legacy-queue):
──────────────────────────────────────────────────────
Queue → graphiti-worker → Temporal Workflow → Activities → FalkorDB
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


### 3. Graph Consolidation ("Graph Sleep")

**Status**: Production-ready (Feb 2026). Scheduled background pipeline that prunes noise, merges duplicate entities, and tracks quality metrics.

The consolidation system runs nightly as a Temporal workflow, gradually improving graph quality — like biological memory consolidation during sleep.

**Environment Variables:**

```bash
TEMPORAL_CONSOLIDATION_TASK_QUEUE=graphiti-consolidation
TEMPORAL_CONSOLIDATION_MAX_ACTIVITIES=2
```

**Enable:**

```bash
docker compose --profile temporal-consolidation up -d graphiti-temporal-consolidation-worker
```

**Manual Trigger:**

```bash
# One-off consolidation run
python3 scripts/schedule_consolidation.py --once

# Custom retention (default 90 days) and batch size
python3 scripts/schedule_consolidation.py --once --retention-days 60 --batch-size 200

# Create nightly schedule (3 AM UTC)
python3 scripts/schedule_consolidation.py --schedule

# Custom cron schedule
python3 scripts/schedule_consolidation.py --schedule --cron "0 5 * * *"

# Delete schedule
python3 scripts/schedule_consolidation.py --delete-schedule
```

**What It Does:**

**Phase 1 — PRUNE:**

1. **Collects pre-metrics** — snapshot of graph quality (node/edge counts, orphans, duplicates)
2. **Prunes orphaned entities** — Entity nodes with zero edges
3. **Prunes junk entities** — Generic names ("medium", "high", "priority", etc.) with ≤2 edges
4. **Prunes old episodic nodes** — Episodic nodes older than retention period (default 90 days), detaches MENTIONS edges
5. **Prunes invalidated edges** — RELATES_TO edges with `invalid_at` set (contradicted facts)

**Phase 2 — MERGE (Feb 2026):**

6. **Merges IS_DUPLICATE_OF edges** — Resolves pre-existing duplicate relationships by merging duplicate into canonical node
7. **Merges same-name entities** — Case-insensitive name grouping, selects canonical (most edges → longest summary → earliest created_at), merges duplicates via `merge_node_into()`
8. **Post-merge orphan prune** — Cleans up entities orphaned by edge reassignment during merge

**Phase 3 — REPORT:**

9. **Collects post-metrics** — snapshot for comparison
10. **Stores consolidation report** — `ConsolidationReport` node in `graphiti_prompts` graph

**Merge Mechanics:**
- Uses existing `merge_node_into()` from `node_operations.py` — transfers all edges (incoming + outgoing), merges edge properties, deletes duplicate
- Canonical selection: most connected node wins (tie-break: longest summary, then earliest creation date)
- Self-healing: failures ("canonical not found") are logged and retried on next nightly run
- Centrality recalculation deferred (planned for Phase 3 ENRICH)
- First run (Feb 2026): merged 721 entities, transferred 2,669 edges, reduced graph from 12,715 → 11,924 nodes

**Consolidation Reports:**

```bash
# View all consolidation reports
redis-cli -p 6379 GRAPH.QUERY graphiti_prompts "MATCH (r:ConsolidationReport) RETURN r.run_id, r.started_at, r.total_pruned, r.total_merged, r.pre_entity_nodes, r.post_entity_nodes ORDER BY r.started_at DESC" --csv
```

**Architecture:**

```
Temporal Schedule (3 AM UTC daily)
  └─ GraphConsolidationWorkflow
       ├─ collect_metrics (pre-snapshot)
       ├─ prune_orphaned_nodes
       ├─ prune_junk_entities
       ├─ prune_old_episodic_nodes
       ├─ prune_invalidated_edges
       ├─ merge_duplicate_of_edges      ← Phase 2
       ├─ merge_same_name_entities      ← Phase 2
       ├─ prune_orphaned_nodes (post-merge)
       ├─ regenerate_entity_summaries   ← Phase 3
       ├─ backfill_entity_embeddings    ← Phase 3
       ├─ semantic_entity_dedup         ← Phase 3
       ├─ prune_orphaned_nodes (post-dedup)
       ├─ recalculate_centrality        ← Phase 3
       ├─ collect_metrics (post-snapshot)
       └─ store_consolidation_report
```

**Worker**: `graphiti-temporal-consolidation-worker` (Prometheus metrics on port 9196)
**Temporal UI**: http://192.168.50.90:8080 (namespace: `graphiti`, search for `consolidation-`)

**Phase 3 — ENRICH (Feb 2026):**

7. **Regenerates entity summaries** — Finds entities with NULL/empty summaries, gathers connected RELATES_TO edge facts, uses LLM to generate summaries
8. **Backfills entity embeddings** — Safety net for entities with NULL `name_embedding`, stores as vecf32
9. **Semantic entity dedup** — Batch iterates entities, uses HNSW vector index on `name_embedding` for cosine similarity (threshold 0.92), selects canonical (most edges → longest summary → earliest created_at), merges via `merge_node_into()`
10. **Post-dedup orphan prune** — Cleans up entities orphaned by edge reassignment during semantic merge
11. **Recalculates centrality** — Calls `calculate_all_centralities(driver, store_results=True)` for full PageRank, degree, and betweenness recalc across entire graph

**Semantic Dedup Details:**
- Default similarity threshold: 0.92 (conservative, tune based on observed results)
- Uses `processed_uuids` set to avoid double-processing
- Canonical selection: most edges → longest summary → earliest `created_at` (same as Phase 2 name merge)
- `merge_node_into()` with `allow_cross_graph_merge=True`
- `SemanticDedupActivities` registered as separate activity class in consolidation worker
- First run data (Feb 2026): 160 entities needed summaries, 12,137 needed centrality, semantic dedup results TBD

**Future Phases (planned):**
- Phase 4: Community refresh, edge quality scoring, knowledge graph enrichment from external sources

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
