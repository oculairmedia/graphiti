# Ingestion Worker Repair Plan

## Context
Recent ingestion runs against FalkorDB show repeated task retries, `ValueError: dictionary update sequence...`, context-length failures, and Falkor vector type mismatches. A focused repair is required before re-enabling full concurrency.

## Critical Findings
1. **Entity extraction hydration blow-up**  
   - Code: `graphiti_core/utils/maintenance/node_operations.py:304-307`  
   - Problem: blindly splats `ExtractedEntity(**entity_data)` even when `entity_data` is already an `ExtractedEntity` instance, string, or other scalar. Pydantic raises and the whole episode is retried forever.
2. **Aggressive duplicate merges damage graph**  
   - Code: `graphiti_core/graphiti.py:528-552` (calls) → `graphiti_core/utils/maintenance/node_operations.py:1388-1540` (implementation)  
   - Problem: any low-confidence fuzzy match or LLM guess feeds `merge_node_into`, which rewires edges and deletes the “duplicate”. False positives corrupt Falkor.
3. **Edge prompt overflows**  
   - Code: `graphiti_core/prompts/extract_edges.py` (all prompt entry points)  
   - Problem: missing `enforce_max_prompt_tokens` call; edge/reflexion prompts ship full conversation history, triggering context overflow failures and retries.
4. **Vector casting gaps during merge**  
   - Code: `graphiti_core/utils/maintenance/node_operations.py:1500+`  
   - Problem: when cloning edge properties via `SET r += $additional_props`, we can pass Python lists (`fact_embedding`) or `None` through to Falkor; wrappers never re-cast these, so Falkor raises `expected Null or Vectorf32 but was List`.
5. **Unbounded async side-effects**  
   - Code: `graphiti_core/ingestion/worker.py:395,401,420,500,516,625`  
   - Problem: we fire `asyncio.create_task` for centrality updates and dedup while transaction is still in-flight. If ingest later fails, the background job still hits Falkor, causing race conditions.

## Remediation Plan
### Phase 1 – Stop the bleeding
1. Harden entity extraction:
   - Accept both `dict` and `ExtractedEntity`; log + skip anything else.
   - Add metric for dropped payloads.
2. Disable destructive merges:
   - Feature-flag `execute_merge_operations` behind `GRAPHITI_ENABLE_AUTO_MERGE`.
   - Default off in prod until we have precision metrics.
3. Clip edge prompts:
   - Wrap `edge`, `reflexion`, and `extract_attributes` contexts with `enforce_max_prompt_tokens`.
   - Apply the same trimming to `previous_episodes`.
4. Normalize merge edge embeddings:
   - Before `SET r += $additional_props`, drop null embeddings and wrap lists with `VectorF32`.
   - Add unit test covering merge path with plain lists.
5. Gate background jobs:
   - Queue centrality/dedup updates to run only after successful commit (e.g., schedule via worker-level queue or await ingestion completion before dispatch).

### Phase 2 – Increase confidence
1. Instrumentation:
   - Emit structured metrics for each retry classification (`TransientError`, `PermanentError`, fallback to DLQ).
   - Record merge candidate similarity scores and actual merges (when flag enabled).
2. Dedup pipeline quality:
   - Require deterministic checks (exact name + high embedding cosine) before a merge candidate is considered.
   - Persist merge candidates to review queue instead of immediate execution.
3. Vector hygiene:
   - Extend `_preprocess_vectors_in_params` coverage tests to include merge and bulk paths.
   - Add Falkor integration test ingesting an episode with multiple edges to verify embeddings land as `Vectorf32`.

### Phase 3 – Concurrency & resilience
1. Reintroduce higher worker counts once retries/merges stabilize; track queue latency vs. error rate.
2. Improve error classification:
   - Expand permanent error list (schema validation, invalid payload).
   - Fast-path DLQ after N repeated prompt-format failures.
3. Provide admin tooling:
   - Endpoint to requeue DLQ entries after manual fix.
   - Dashboard widgets for ingestion success rate, retries, merges.

## Validation Checklist
- [ ] Unit: entity extraction handles dict/object/garbage payloads.
- [ ] Unit: merge path converts embeddings to `VectorF32`.
- [ ] Integration: ingest sample episode with fallback flag off → Falkor graph unchanged.
- [ ] Integration: ingest same episode with flag on and high-confidence duplicate → verify merge occurs and embeddings valid.
- [ ] Load (optional): run with `WORKER_COUNT=2`, ensure error rate < 1% and no DLQ growth.

## Open Questions
1. Should we maintain an allow-list of entity types eligible for automatic merges?
2. Do we have capacity in centrality service to buffer updates until ingestion commits?
3. Are there external consumers depending on dedup running inline (e.g., API latency expectations)?

## Owners / Next Actions
| Task | Owner | Target |
| --- | --- | --- |
| Phase 1 patch set | Core ingestion | ASAP |
| Metrics instrumentation | Observability | +3 days |
| Merge review tooling | Product eng | Q next sprint |

