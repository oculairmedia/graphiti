# Gotchas & Pitfalls

> **READ THIS FIRST** - Common mistakes that waste hours of debugging.
> These are the top pitfalls an AI agent should know before working on this codebase.

---

## 1. FalkorDB Vector Type MUST Use `vecf32([...])` Syntax

**Problem**: Storing embeddings as Python lists breaks ALL vector queries.

```python
# ❌ WRONG - stores as List, breaks HNSW index
query = f"SET n.embedding = {embedding}"

# ✅ CORRECT - stores as Vectorf32
query = f"SET n.embedding = vecf32([{','.join(str(v) for v in embedding)}])"
```

**Symptoms**: "expected Vectorf32 but was List" error, 0 results from vector search
**Fix**: `python3 scripts/validate_embeddings.py --fix`
**Files to check**: `graphiti_core/driver/*.py`, any code that sets embeddings

---

## 2. Docker Dependency Chains - Use `docker restart` NOT `docker-compose`

**Problem**: `docker-compose restart graph-visualizer-rust` cascades through dependencies and may restart FalkorDB.

**Solution**: Always use container names for restarts:

```bash
# ✅ SAFE - restarts only the specified container
docker restart graphiti-graph-visualizer-rust-1
docker restart graphiti-nginx-1
docker restart graphiti-frontend-1

# ❌ DANGEROUS - cascades through depends_on
docker-compose restart graph-visualizer-rust
```

**Why**: FalkorDB takes ~2 minutes to reload from RDB after restart.

---

## 3. NEVER Use `docker system prune --volumes` or `docker volume prune`

**Problem**: These commands delete the `graphiti_falkordb_data` volume, destroying all graph data.

**Solution**: Use the safe cleanup script:

```bash
# ✅ SAFE - protects all data volumes
/opt/stacks/graphiti/scripts/safe_cleanup.sh

# Preview what would be cleaned
/opt/stacks/graphiti/scripts/safe_cleanup.sh --dry-run
```

**Protected volumes**: `graphiti_falkordb_data`, `graphiti_visualizer_duckdb`, `dspy_training_data`

---

## 4. FalkorDB Restart is Safe (Data Persists)

**Good news**: FalkorDB uses RDB snapshots. Restarts are safe.

**Timing**: Data reloads from RDB in ~2 minutes. Wait before querying.

**Verify**:
```bash
redis-cli -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)" --csv
```

---

## 5. Healthcheck Timing - Services Have Start Periods

**Problem**: Services may show "Created" but not "Running" immediately after `docker-compose up`.

**Cause**: Healthchecks have `start_period` (up to 4.5 minutes for visualizer).

**Fix**: Wait or manually start dependent containers:
```bash
docker start graphiti-nginx-1 graphiti-frontend-1
```

---

## 6. Temporal Rate Limits - Configure Per-Activity Concurrency

**Problem**: LLM APIs (OpenAI, etc.) have rate limits. Default concurrency may cause 429 errors.

**Solution**: Tune these environment variables:

```bash
# Legacy single-queue mode
TEMPORAL_MAX_CONCURRENT_ACTIVITIES=5

# Staged mode (per-activity limits)
TEMPORAL_EXTRACT_MAX_CONCURRENT_ACTIVITIES=3
TEMPORAL_RESOLVE_MAX_CONCURRENT_ACTIVITIES=3
TEMPORAL_EDGE_MAX_CONCURRENT_ACTIVITIES=2
TEMPORAL_PERSIST_MAX_CONCURRENT_ACTIVITIES=5

# Add delays between LLM calls
TEMPORAL_RATE_LIMIT_POST_LLM_DELAY=2.0
```

---

## 7. Embedding Dimensions Must Match Provider

**Problem**: Using wrong embedding dimensions causes storage/query failures.

| Provider | Default Model | Dimensions |
|----------|---------------|------------|
| OpenAI | text-embedding-3-small | 1536 |
| Voyage | voyage-3-large | 1024 |
| Gemini | embedding-001 | 768 |
| Ollama (nomic) | nomic-embed-text | 768 |

**Always** specify `embedding_dim` when configuring embedder for non-OpenAI providers.

---

## 8. Bi-Temporal Fields Are Separate Concepts

| Field | Meaning |
|-------|---------|
| `created_at` | When the record was inserted into DB |
| `t_valid_at` | When the fact became true in reality |
| `t_invalid_at` | When the fact was contradicted (NULL = still valid) |

**Gotcha**: Don't confuse `created_at` with `t_valid_at`. Historical queries use `t_valid_at`.

---

## 9. Entity Resolution is Name-Based (Not Semantic)

**Default behavior**: Entities with same name (case-insensitive) are merged.

**Semantic dedup**: Run consolidation workflow for embedding-based dedup.

```bash
python3 scripts/schedule_consolidation.py --once
```

---

## 10. DSPy Signatures Define Extraction Behavior

**Location**: `graphiti_core/prompts/` - these DSPy signatures control extraction.

**Key files**:
- `extract_nodes.py` - Entity extraction
- `extract_edges.py` - Relationship extraction
- `dedupe_nodes.py` - Node resolution

**Modification**: Changes to docstrings affect what gets extracted.

---

## 11. Type Errors - Never Suppress with `as any` or `@ts-ignore`

**Problem**: Suppressed type errors hide real bugs.

**Solution**: Fix the underlying type mismatch. If external library has wrong types, create proper wrapper.

```python
# ❌ NEVER
result = some_func()  # type: ignore

# ✅ Fix the type or create wrapper
def typed_wrapper() -> ExpectedType:
    result = some_func()
    assert isinstance(result, ExpectedType)
    return result
```

---

## 12. Test Fixtures May Affect Production State

**Problem**: Tests that connect to real FalkorDB can pollute production data.

**Solution**: Tests should use separate database or mock the driver.

```python
# Use test database
driver = FalkorDriver(database="graphiti_test")
```

---

## 13. MCP Server Tools Are Stateful

**Problem**: MCP server maintains state across tool calls.

**Gotcha**: Tool calls that modify state (add_episode, delete_node) affect subsequent calls.

**Solution**: Check state with `get_graph_state` or `search_nodes` before assuming.

---

## 14. Centrality Calculation is Resource-Intensive

**Problem**: Full centrality recalculation on large graphs takes significant time.

**Solution**: Only run on demand or during consolidation (nightly).

```python
# Manual trigger
from graphiti_core.utils import calculate_all_centralities
await calculate_all_centralities(driver, store_results=True)
```

---

## 15. Frontend Expects Specific API Response Formats

**Problem**: Frontend will break if API changes response structure.

**Files**: `frontend/src/` - check expected types before modifying API.

**Test**: After API changes, verify frontend still loads and displays data.

---

## Summary Checklist

Before making changes:

- [ ] Check if FalkorDB vector operations use `vecf32()`
- [ ] Use `docker restart <container>` not `docker-compose`
- [ ] Never run `docker system prune --volumes`
- [ ] Check Temporal concurrency limits for LLM operations
- [ ] Verify embedding dimensions match provider
- [ ] Understand bi-temporal field semantics
- [ ] Check if DSPy signature changes affect extraction
- [ ] Never suppress type errors
- [ ] Consider test database isolation

---

*Last updated: March 2026*
