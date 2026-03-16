# How-to: Debug Ingestion

> **Keywords**: `debug`, `ingestion`, `episode`, `temporal`, `queue`, `worker`, `errors`

## Quick Triage

1. Confirm which ingestion path is active (Temporal vs legacy queue).
2. Check API and worker logs for the failing episode UUID.
3. Verify graph writes landed in FalkorDB.
4. Check common gotchas (vector type, rate limits, stale workers).

---

## 1) Identify Active Ingestion Mode

Ingestion can run through two paths:

- Temporal-native routing (`/api/temporal/messages` and Temporal workflows)
- Legacy queue routing (`/api/queue/*` endpoints)

Primary switch:

```bash
echo "$TEMPORAL_INGESTION_ENABLED"
```

When `TEMPORAL_INGESTION_ENABLED=true`, the service attempts Temporal workflow startup first.

---

## 2) Check Service Health and Logs

```bash
docker-compose ps
docker-compose logs --tail=100 graph
docker-compose logs --tail=100 graphiti-worker
docker-compose logs --tail=100 graphiti-temporal-ingestion-worker
```

If using Temporal, also check the Temporal UI:

- `http://192.168.50.90:8080` (namespace: `graphiti`)

---

## 3) Verify Data Was Persisted

Check node and edge counts:

```bash
redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)" --csv
redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" --csv
```

If counts do not move after successful ingestion responses, inspect worker errors and endpoint configuration.

---

## 4) Common Failure Patterns

### Temporal Workflows Not Starting

- Verify Temporal env vars are set in runtime, not just `.env`.
- Ensure temporal ingestion worker is actually running.
- Check for connectivity issues to Temporal server.

### Queue Backlog Not Draining

- Check queue endpoints under `server/graph_service/routers/ingest_queue.py`.
- Inspect worker logs for repeated retries or serialization failures.

### Vector Search or Embedding Errors

If logs show `expected Vectorf32 but was List`, fix corrupted embeddings:

```bash
python3 scripts/validate_embeddings.py
python3 scripts/validate_embeddings.py --fix
```

### LLM Rate Limits

Reduce Temporal concurrency (especially extract/resolve/edge activities) and add post-LLM delay where needed.

---

## 5) High-Signal Files

| File | Why it matters |
|------|----------------|
| `server/graph_service/routers/ingest.py` | Main message ingestion path + fallback behavior |
| `server/graph_service/routers/ingest_temporal.py` | Temporal-native endpoint behavior |
| `server/graph_service/routers/ingest_queue.py` | Legacy queue endpoints and status |
| `worker/temporal_ingestion_worker.py` | Temporal activity execution |
| `graphiti_core/graphiti.py` | Core ingestion and persistence calls |

---

## 6) Minimal Repro Workflow

1. Send a single small message payload.
2. Capture response (episode/workflow IDs).
3. Trace that ID through graph API logs and worker logs.
4. Confirm resulting nodes/edges in FalkorDB queries.

This isolates routing and persistence issues from high-throughput noise.

---

## See Also

- [add-episode.md](add-episode.md) - Ingestion usage patterns
- [temporal-workflows.md](temporal-workflows.md) - Temporal operations
- [../gotchas.md](../gotchas.md) - Critical ingestion pitfalls
