# Temporal Migration Analysis - Progress Summary

## Completed Analysis (Jan 12, 2026)

### ✅ 1. Current Queue System Documentation
**File**: `current-queue-system.md`

**Key Findings**:
- **Queue**: Wilson Lin's `queued` service (LevelDB-backed, 300K ops/sec capability)
- **Protocol**: HTTP + MessagePack
- **Port**: 8093
- **Guarantees**: At-least-once delivery via visibility timeout (300s default)
- **Pain Points**:
  - No automatic retries with exponential backoff
  - No DLQ (exists but no alerting)
  - Poor observability (no traces, no correlation IDs)
  - Manual worker scaling

**Architecture**:
```
HTTP Webhook → Queued (LevelDB) → WorkerPool (2 workers) → Graphiti
```

---

### ✅ 2. Episode Processing Pipeline Documentation
**File**: `episode-processing-pipeline.md`

**Key Findings**:
- **Total Duration**: ~226 seconds per episode (3.76 minutes)
- **Throughput**: ~32 episodes/hour (2 workers)
- **LLM Calls**: 15-25 per episode (avg: 20)
- **Cost**: ~$0.033/episode ($33/1000 episodes)

**Pipeline Stages**:
1. **Pre-Processing** (50ms): Validation, context retrieval
2. **Entity Extraction** (86s, 38%): LLM extracts entities from text
3. **Node Deduplication** (111s, 49%): Vector search + LLM deduplication
4. **Edge Extraction** (24s, 11%): LLM extracts relationships
5. **Edge Resolution** (15s, 7%): Deduplicate edges, invalidate contradictions
6. **Graph Persistence** (30s, 13%): Batch save to FalkorDB
7. **Community Updates** (5s, 2%): Optional, disabled by default

**Bottlenecks**:
1. Node deduplication (49%) - multiple LLM calls per entity
2. Entity extraction (38%) - complex prompts
3. Graph persistence (13%) - batch size, embedding generation

**External Dependencies**:
- LLM API (OpenAI/Ollama/Cerebras)
- Embedding API (OpenAI/Voyage)
- FalkorDB (graph database)
- Centrality service (optional Rust service)

---

### ✅ 3. Worker Pool & Concurrency Model
**File**: `worker-pool-concurrency.md`

**Key Findings**:
- **Architecture**: Independent workers polling shared queue (no inter-worker communication)
- **Current Config**: 2 workers, batch_size=1, sequential processing within worker
- **Coordination**: Queue visibility timeout (20 minutes) prevents duplicate processing
- **Rate Limiting**: Per-worker (uncoordinated) - actual limits are 100×worker_count req/sec
- **Idempotency**: Episode UUID check prevents reprocessing completed episodes
- **Scaling Potential**: Can scale to 10-20 workers before hitting external rate limits

---

### ✅ 4. External Dependencies Catalog
**File**: `external-dependencies.md`

**Key Findings**:
- **Critical Dependencies**: LLM (GLM-4.5), Embeddings (Qwen3 vLLM), FalkorDB, Queued
- **Rate Limits**:
  - LLM: Quota-based (34% hourly usage), has Anthropic fallback
  - Embeddings: GPU-limited (~20 emb/sec), NO fallback
  - FalkorDB: Memory-limited (8GB runtime), NO fallback
  - Queued: 300K ops/sec (effectively unlimited)
- **Retry Strategies**:
  - LLM: 2 client retries + 3 task retries (exponential backoff 10s → 300s)
  - Task-level: 3 max attempts, exponential backoff (10s → 20s → 40s → 80s, capped at 300s)
  - Transient errors: Unlimited retries (via queue redelivery)
- **High-Risk Items**:
  - LLM quota exhaustion (medium probability, high impact)
  - FalkorDB OOM (low probability, high impact)
  - Embedding service GPU OOM (low probability, critical path failure)

---

## Pending Analysis

---

### 5. Error Handling & Retry Mechanisms
**Goal**: Document all error types, retry logic, and failure recovery

**Current State** (from code review):
- **Transient Errors**: Exponential backoff (10s, 20s, 40s, 80s, max 300s)
- **Permanent Errors**: Immediate DLQ
- **Rate Limit Errors**: Group suspension (60s)
- **Max Retries**: 3 attempts
- **Resilient Wrapper**: `add_episode_resilient()` with checkpointing

**Questions to Answer**:
- How often do retries succeed?
- What percentage go to DLQ?
- What's the average retry count?
- Are there poison messages?

---

### 6. Migration Phases Document
**Goal**: Design incremental rollout strategy for Temporal migration

**Approach**:
1. **Phase 0**: Infrastructure setup (Temporal server, workers)
2. **Phase 1**: Shadow mode (Temporal alongside current system, no writes)
3. **Phase 2**: Canary (1% traffic to Temporal)
4. **Phase 3**: Gradual rollout (10%, 50%, 100%)
5. **Phase 4**: Deprecate old system

**Success Criteria**:
- Equal or better throughput
- Lower error rate
- Better observability (Web UI, traces)
- No data loss during migration

---

### 7. Parallel Testing Strategy
**Goal**: Design test harness to compare current vs. Temporal system

**Test Types**:
1. **Unit Tests**: Test activities in isolation
2. **Integration Tests**: Test full workflow
3. **Load Tests**: Compare throughput under load
4. **Failure Tests**: Simulate crashes, network issues
5. **Replay Tests**: Replay production episodes

**Metrics to Compare**:
- Throughput (episodes/hour)
- Latency (p50, p95, p99)
- Error rate
- Retry rate
- DLQ rate

---

### 8. Temporal Component Mapping
**Goal**: Map current components to Temporal equivalents

**Initial Mapping** (from pipeline doc):

| Current Component | Temporal Equivalent |
|-------------------|---------------------|
| `queued` service | Temporal task queue |
| `IngestionWorker._process_episode()` | Temporal workflow: `IngestEpisodeWorkflow` |
| Stage 1: Entity Extraction | Activity: `extract_entities_activity` |
| Stage 2A: Node Deduplication | Activity: `deduplicate_nodes_activity` |
| Stage 2B: Edge Extraction | Activity: `extract_edges_activity` |
| Stage 3: Edge Resolution | Activity: `resolve_edges_activity` |
| Stage 5: Graph Persistence | Activity: `save_to_graph_activity` |
| Episode UUID | Workflow ID |
| Retry logic | Temporal retry policy (per-activity) |
| DLQ | Failed workflow search (`WorkflowStatus.Failed`) |

**Open Questions**:
- Should stages run sequentially or in parallel?
- How to handle long-running LLM calls (heartbeats)?
- How to implement checkpointing?
- How to handle worker crashes mid-stage?

---

## Next Steps

### Immediate (Complete Documentation)
1. ✅ Document queue system → **DONE**
2. ✅ Document pipeline stages → **DONE**
3. ✅ Document worker pool logic → **DONE**
4. ✅ Catalog external dependencies → **DONE**
5. ⏳ Document error handling

### Short-Term (Design Migration)
6. ⏳ Create migration phases doc
7. ⏳ Design parallel testing approach
8. ⏳ Map to Temporal components

### Medium-Term (Prototype)
9. Set up Temporal server (local Docker)
10. Implement single activity (entity extraction)
11. Implement simple workflow (episode ingestion)
12. Run side-by-side comparison (shadow mode)

### Long-Term (Production Migration)
13. Deploy Temporal to production
14. Canary rollout (1% traffic)
15. Gradual migration (10%, 50%, 100%)
16. Deprecate old system

---

## Key Insights So Far

### 1. Temporal is a Natural Fit
- Pipeline has clear stages → Temporal activities
- Need for retries → Temporal retry policies
- Need for observability → Temporal Web UI
- Need for checkpointing → Temporal workflow state

### 2. Migration Can Be Incremental
- Current system can run in parallel with Temporal
- Episode UUID deduplication prevents duplicate work
- Can test with 1% traffic before full rollout

### 3. Performance Should Improve
- Temporal's task queue is faster than LevelDB queue
- Activity-level parallelism (vs. worker-level)
- Better retry strategies (exponential backoff, circuit breakers)

### 4. Observability Will Be Major Win
- Temporal Web UI shows all in-flight workflows
- Per-activity timing and errors
- Full workflow history (can replay failures)
- Correlation IDs for distributed tracing

---

## Files Created

1. `/opt/stacks/graphiti/temporal-migration-analysis/current-queue-system.md` (8.5K)
   - Queue architecture, API, message format, error handling

2. `/opt/stacks/graphiti/temporal-migration-analysis/episode-processing-pipeline.md` (21K)
   - Pipeline stages, timing, LLM calls, bottlenecks, dependencies

3. `/opt/stacks/graphiti/temporal-migration-analysis/worker-pool-concurrency.md` (23K)
   - Worker coordination, rate limiting, scaling, idempotency

4. `/opt/stacks/graphiti/temporal-migration-analysis/external-dependencies.md` (36K)
   - All external services, rate limits, retry strategies, failure modes, Temporal mapping

5. `/opt/stacks/graphiti/temporal-migration-analysis/README.md` (this file)
   - Summary, progress, next steps

**Total Documentation**: 88.5K (5 files)

---

## Questions for User

1. **Temporal Server**: Is there an existing Temporal server running? (localhost:7233 mentioned in guide)
2. **Migration Timeline**: What's the target timeline for migration? (Weeks? Months?)
3. **Backwards Compatibility**: Do we need to support both systems indefinitely?
4. **Testing**: Can we test with production data, or need synthetic episodes?
5. **Monitoring**: What monitoring tools are in place? (Prometheus, Grafana, Datadog?)

---

## References

- User-provided Temporal guide (based on `huly-vibe-sync` experience)
- `/opt/stacks/graphiti/AGENTS.md` (stack-specific instructions)
- Current monitoring: `/opt/stacks/graphiti/scripts/monitor_ingestion.sh`

---

## Status: ⏳ Phase 1 In Progress (Fact-Finding)

**Completed**: 4 of 8 tasks (50%)

**Next**: Document error handling & retry mechanisms (Task #5), then move to Phase 2 (Design Migration).
