# How-to: Work with Temporal Workflows

> **Keywords**: `temporal`, `workflow`, `ingestion`, `consolidation`, `activity`, `queue`

## Overview

Graphiti uses Temporal.io for:
- **Ingestion workflows** - Reliable, retryable data ingestion
- **Consolidation workflows** - Nightly graph cleanup

---

## Quick Start

### Enable Temporal Ingestion

```bash
# .env
TEMPORAL_INGESTION_ENABLED=true
TEMPORAL_VISIBILITY_ADDRESS=192.168.50.90:7233
TEMPORAL_INGESTION_NAMESPACE=graphiti
```

### Start Workers

```bash
# Staged workers (recommended)
docker compose --profile temporal-staged up -d

# Or legacy single worker
docker compose --profile temporal up -d
```

---

## Ingestion Workflows

### Architecture

```
Episode → Temporal Workflow
           ├── Activity: extract_nodes
           ├── Activity: resolve_nodes  
           ├── Activity: extract_edges
           └── Activity: resolve_edges_and_persist
                ↓
             FalkorDB
```

### Workflow ID Format

```
ingest-episode-<episode_uuid>
```

### Configuration

```bash
# Staged queue mode (recommended)
TEMPORAL_INGESTION_WORKFLOW_TASK_QUEUE=graphiti-ingestion-workflow
TEMPORAL_INGESTION_EXTRACT_TASK_QUEUE=graphiti-ingestion-extract
TEMPORAL_INGESTION_RESOLVE_TASK_QUEUE=graphiti-ingestion-resolution
TEMPORAL_INGESTION_EDGE_TASK_QUEUE=graphiti-ingestion-edge
TEMPORAL_INGESTION_PERSIST_TASK_QUEUE=graphiti-ingestion-persist

# Concurrency limits (prevent LLM API throttling)
TEMPORAL_EXTRACT_MAX_CONCURRENT_ACTIVITIES=3
TEMPORAL_RESOLVE_MAX_CONCURRENT_ACTIVITIES=3
TEMPORAL_EDGE_MAX_CONCURRENT_ACTIVITIES=2
TEMPORAL_PERSIST_MAX_CONCURRENT_ACTIVITIES=5

# Delays between LLM calls
TEMPORAL_RATE_LIMIT_POST_LLM_DELAY=2.0
TEMPORAL_RATE_LIMIT_INTER_ACTIVITY_DELAY=0.0
```

### Monitor Workflows

- **Temporal UI**: http://192.168.50.90:8080
- **Namespace**: `graphiti`
- **Search**: `ingest-episode-`

---

## Consolidation Workflows

### What It Does

**Phase 1 — PRUNE**:
- Removes orphaned entities
- Removes junk entities (generic names)
- Removes old episodic nodes
- Removes invalidated edges

**Phase 2 — MERGE**:
- Merges duplicate entities (name-based)
- Merges semantically similar entities

**Phase 3 — ENRICH**:
- Regenerates entity summaries
- Backfills missing embeddings
- Recalculates centrality

### Run Consolidation

```bash
# One-off run
python3 scripts/schedule_consolidation.py --once

# With custom settings
python3 scripts/schedule_consolidation.py --once --retention-days 60 --batch-size 200

# Schedule nightly (3 AM UTC)
python3 scripts/schedule_consolidation.py --schedule

# Custom cron
python3 scripts/schedule_consolidation.py --schedule --cron "0 5 * * *"

# Delete schedule
python3 scripts/schedule_consolidation.py --delete-schedule
```

### Configuration

```bash
TEMPORAL_CONSOLIDATION_TASK_QUEUE=graphiti-consolidation
TEMPORAL_CONSOLIDATION_MAX_ACTIVITIES=2
```

### Check Consolidation Reports

```bash
redis-cli -p 6379 GRAPH.QUERY graphiti_prompts \
  "MATCH (r:ConsolidationReport) 
   RETURN r.run_id, r.started_at, r.total_pruned, r.total_merged 
   ORDER BY r.started_at DESC" --csv
```

---

## Worker Management

### Start Workers

```bash
# Ingestion workers
docker compose --profile temporal-staged up -d \
  graphiti-temporal-ingestion-worker-extract \
  graphiti-temporal-ingestion-worker-resolve \
  graphiti-temporal-ingestion-worker-edge \
  graphiti-temporal-ingestion-worker-persist

# Consolidation worker
docker compose --profile temporal-consolidation up -d \
  graphiti-temporal-consolidation-worker
```

### Check Worker Logs

```bash
docker logs -f graphiti-graphiti-temporal-ingestion-worker-1
```

### Worker Health

Workers expose Prometheus metrics on port 9196.

---

## Migration to Staged Queues

### Strategy A (Safe)

Run both legacy and staged workers until legacy queue drains:

```bash
docker compose --profile temporal --profile temporal-staged up -d
```

### Strategy B (Fast)

Cancel old workflows and requeue:

```bash
# Dry run
python3 scripts/migrate_to_staged_queues.py --dry-run --limit 10

# Migrate
python3 scripts/migrate_to_staged_queues.py --limit 100 --force
```

---

## Troubleshooting

### Issue: Workflow stuck

**Check Temporal UI**:
1. Go to http://192.168.50.90:8080
2. Find workflow by ID
3. Check activity failures

**Common causes**:
- LLM API errors (429 rate limits)
- Worker not running
- Network issues

### Issue: Rate limiting (429 errors)

**Solution**: Reduce concurrency

```bash
TEMPORAL_EXTRACT_MAX_CONCURRENT_ACTIVITIES=1
TEMPORAL_RATE_LIMIT_POST_LLM_DELAY=5.0
```

### Issue: Worker not picking up tasks

**Check**:
```bash
# Worker running?
docker ps | grep temporal

# Correct task queue?
docker logs graphiti-graphiti-temporal-ingestion-worker-1 | grep "task queue"
```

---

## Files to Know

| File | Purpose |
|------|---------|
| `worker/temporal_ingestion_worker.py` | Ingestion worker |
| `worker/temporal_consolidation_worker.py` | Consolidation worker |
| `graphiti_core/temporal/` | Workflow definitions |
| `scripts/schedule_consolidation.py` | Consolidation scheduler |

---

## See Also

- [add-episode.md](add-episode.md) - Adding data
- [consolidation.md](consolidation.md) - Consolidation details
- [../reference/temporal-config.md](../reference/temporal-config.md) - Full config
- [../explanation/consolidation-system.md](../explanation/consolidation-system.md) - Architecture
