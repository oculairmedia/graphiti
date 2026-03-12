# How-to: Run Docker Services

> **Keywords**: `docker`, `start`, `stop`, `restart`, `compose`, `deploy`, `service`

## Critical Rules

1. **Use `docker restart <container>` NOT `docker-compose restart <service>`**
2. **NEVER run `docker system prune --volumes`** - deletes data
3. **Check service status before acting**

---

## Quick Reference

### Check Status

```bash
docker-compose ps
```

### Safe Restarts

```bash
# Individual containers (SAFE)
docker restart graphiti-graph-visualizer-rust-1
docker restart graphiti-nginx-1
docker restart graphiti-frontend-1
docker restart graphiti-graph-1
docker restart graphiti-falkordb-1

# ❌ DANGEROUS - cascades through dependencies
docker-compose restart graph-visualizer-rust
```

### Full Stack

```bash
# Start all
docker-compose up -d

# Stop all (preserves data)
docker-compose down

# Stop and remove volumes (⚠️ DELETES DATA)
docker-compose down -v
```

---

## Service Overview

| Service | Container Name | Port | Depends On |
|---------|---------------|------|------------|
| falkordb | graphiti-falkordb-1 | 6379 | - |
| graph-visualizer-rust | graphiti-graph-visualizer-rust-1 | 3000 | falkordb |
| graph (API) | graphiti-graph-1 | 8003 | falkordb |
| frontend | graphiti-frontend-1 | 8085 | visualizer |
| nginx | graphiti-nginx-1 | 8088, 8443 | visualizer |
| graphiti-mcp | graphiti-graphiti-mcp-1 | 8001 | falkordb |

---

## Service-Specific Notes

### FalkorDB (Port 6379)

**Restart is SAFE** - data persists via RDB snapshots.

```bash
docker restart graphiti-falkordb-1

# Wait ~2 minutes for RDB load
# Verify data:
redis-cli -p 6379 GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)" --csv
```

**Memory**: 16GB limit, 8GB runtime maxmemory

### graph-visualizer-rust (Port 3000)

**Restart**: Use container name only

```bash
# ✅ SAFE
docker restart graphiti-graph-visualizer-rust-1

# ❌ DANGEROUS
docker-compose restart graph-visualizer-rust
```

**Healthcheck**: Up to 4.5 minutes on startup (loads all edges)

**DuckDB Cache**: 17GB in `visualizer_duckdb` volume

### Frontend & Nginx

After full stack restart, may need manual start:

```bash
# If stuck in "Created" state
docker start graphiti-nginx-1 graphiti-frontend-1
```

---

## Common Operations

### View Logs

```bash
# All services
docker-compose logs --tail=50

# Specific service
docker-compose logs --tail=50 falkordb
docker-compose logs -f graph  # Follow
```

### Check Health

```bash
docker-compose ps
# Look for "healthy" status
```

### Resource Usage

```bash
docker stats
```

---

## Safe Disk Cleanup

**NEVER** use `docker system prune --volumes` or `docker volume prune`.

Use the safe cleanup script:

```bash
# Preview
/opt/stacks/graphiti/scripts/safe_cleanup.sh --dry-run

# Run cleanup
/opt/stacks/graphiti/scripts/safe_cleanup.sh

# Aggressive (includes build cache)
/opt/stacks/graphiti/scripts/safe_cleanup.sh --all
```

**Protected volumes**:
- `graphiti_falkordb_data` - PRIMARY DATA
- `graphiti_visualizer_duckdb` - Visualizer cache
- `dspy_training_data` - DSPy training data

---

## FalkorDB Data Protection

### Create Protection Copy

```bash
/opt/stacks/graphiti/scripts/protect_falkordb.sh
```

### Check Protection Status

```bash
/opt/stacks/graphiti/scripts/protect_falkordb.sh --status
```

### Restore from Protection

```bash
/opt/stacks/graphiti/scripts/protect_falkordb.sh --restore
```

---

## Troubleshooting

### Issue: Services stuck in "Created" state

**Cause**: Dependencies not yet healthy

**Fix**:
```bash
# Check what's unhealthy
docker-compose ps

# Manually start dependent services
docker start graphiti-nginx-1 graphiti-frontend-1
```

### Issue: Visualizer shows incomplete data

**Causes**:
1. FalkorDB RDB not loaded yet
2. DuckDB cache stale
3. Visualizer started before FalkorDB ready

**Fix**:
```bash
# Check FalkorDB data
redis-cli -p 6379 GRAPH.QUERY graphiti_migration \
  "MATCH ()-[r]->() RETURN count(r)" --csv

# If correct, restart visualizer
docker restart graphiti-graph-visualizer-rust-1
```

### Issue: FalkorDB OOM

**Symptoms**: Container restarts, queries fail

**Fix**: Increase memory in `docker-compose.yml`:
```yaml
services:
  falkordb:
    deploy:
      resources:
        limits:
          memory: 20G
```

---

## Files to Know

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Service definitions |
| `.env` | Environment variables |
| `scripts/safe_cleanup.sh` | Safe disk cleanup |
| `scripts/protect_falkordb.sh` | Data protection |

---

## See Also

- [../gotchas.md](../gotchas.md) - Critical Docker gotchas
- [query-falkordb.md](query-falkordb.md) - FalkorDB operations
- [temporal-workflows.md](temporal-workflows.md) - Temporal services
