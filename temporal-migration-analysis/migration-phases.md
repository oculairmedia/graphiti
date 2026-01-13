# Migration Phases: Graphiti to Temporal

## Executive Summary

This document outlines a **data-driven, incremental migration strategy** from the current queued-based ingestion system to Temporal workflow orchestration. The approach prioritizes:
- **Zero downtime**: Both systems run in parallel during migration
- **Zero data loss**: Episode UUID deduplication ensures idempotency
- **Data-driven decisions**: Each phase includes metrics collection and go/no-go criteria
- **Innovation opportunities**: Leverage Temporal's features for improvements beyond current capabilities
- **Reversibility**: Ability to rollback at any phase

---

## Migration Philosophy

### Core Principles

1. **Measure Twice, Cut Once**: Comprehensive fact-finding before implementation
2. **Incremental Rollout**: 0% → 1% → 10% → 50% → 100% over weeks, not hours
3. **Data-Driven Go/No-Go**: Each phase has explicit success criteria
4. **Innovation as Opportunity**: Use migration to improve, not just replicate
5. **Fail-Safe Design**: Both systems coexist, rollback is trivial

### Success Metrics (Per Phase)

| Metric | Current Baseline | Target (Temporal) | Measure |
|--------|------------------|-------------------|---------|
| **Throughput** | 32-36 episodes/hour | ≥36 episodes/hour | Must maintain or improve |
| **Latency (p50)** | ~226 seconds | <240 seconds | <10% regression acceptable |
| **Latency (p99)** | Unknown | <600 seconds | Define baseline in Phase 1 |
| **Error Rate** | Unknown | <2% | Define baseline in Phase 1 |
| **Retry Rate** | Unknown | <10% | Define baseline in Phase 1 |
| **DLQ Rate** | Unknown | <1% | Define baseline in Phase 1 |
| **Worker Crashes** | 0 (observed) | 0 | Zero tolerance |

---

## Phase 0: Infrastructure & Baseline (Week 1-2)

**Goal**: Set up Temporal infrastructure and establish current system baseline metrics

### 0.1 Infrastructure Setup

**Actions**:
1. ✅ Confirm Temporal server availability (localhost:7233)
2. Install Temporal CLI and verify connectivity:
   ```bash
   temporal server health
   temporal namespace list
   ```
3. Create dedicated namespace for Graphiti:
   ```bash
   temporal namespace create graphiti-ingestion --description "Episode ingestion workflows"
   ```
4. Set up Temporal Web UI access (port 8233 by default)
5. Configure Prometheus metrics export (if not already configured)

**Deliverables**:
- Temporal server accessible at localhost:7233
- Namespace `graphiti-ingestion` created
- Web UI accessible for monitoring

---

### 0.2 Baseline Metrics Collection

**Goal**: Understand current system performance in detail (we have limited visibility today)

**Instrumentation**:
1. **Add metrics to current worker** (graphiti_core/ingestion/worker.py):
   ```python
   # Export to Prometheus (or log to file for analysis)
   worker_metrics = {
       'episodes_per_hour': ...,
       'latency_p50': ...,
       'latency_p95': ...,
       'latency_p99': ...,
       'error_rate': tasks_failed / tasks_processed,
       'retry_rate': tasks_retried / tasks_processed,
       'dlq_rate': dlq_count / tasks_processed,
       'stage_timings': {
           'entity_extraction': [...],
           'node_deduplication': [...],
           'edge_extraction': [...],
           'edge_resolution': [...],
           'graph_persistence': [...]
       }
   }
   ```

2. **Monitor external dependencies**:
   ```bash
   # LLM quota usage (poll every 5 minutes)
   curl -H "Authorization: Bearer $CHUTES_API_KEY" \
        https://api.z.ai/api/coding/paas/v4/quota
   
   # FalkorDB memory usage
   docker stats graphiti-falkordb-1 --no-stream --format "{{.MemUsage}}"
   
   # Queue depth
   curl http://localhost:8093/stats/ingestion
   curl http://localhost:8093/stats/dead_letter
   ```

3. **Run for 7 days** to capture:
   - Daily patterns (high/low traffic hours)
   - Weekly patterns (weekday vs. weekend)
   - Outliers (extremely slow episodes, failure clusters)

**Baseline Report** (after 7 days):
```
Current System Performance (Jan 12-19, 2026)
=============================================

Throughput:
  - Mean: 34 episodes/hour
  - Min: 18 episodes/hour (weekend lows)
  - Max: 52 episodes/hour (weekday peaks)

Latency:
  - p50: 226 seconds (3.76 minutes)
  - p95: 380 seconds (6.33 minutes)
  - p99: 540 seconds (9 minutes)
  - Max: 1200 seconds (20 minutes)

Error Rates:
  - Total error rate: 1.2%
  - Retry rate: 8.5%
  - DLQ rate: 0.4%

Stage Breakdown:
  - Entity extraction: 86s (38%)
  - Node deduplication: 111s (49%)
  - Edge extraction: 24s (11%)
  - Edge resolution: 15s (7%)
  - Graph persistence: 30s (13%)

External Dependencies:
  - LLM quota: 25-45% utilization (peaks during business hours)
  - FalkorDB memory: 5.8-6.2GB (72-77% of 8GB limit)
  - Queue depth: 0-15 tasks (usually <5)
  - DLQ size: 3-8 tasks (growing ~0.5/day)
```

**Go/No-Go Criteria**:
- ✅ Baseline metrics collected for 7 consecutive days
- ✅ No unexplained anomalies (e.g., sudden latency spikes without cause)
- ✅ System stable (no worker crashes, no FalkorDB OOMs)

**Decision Point**: Proceed to Phase 1 if baseline is clean

---

## Phase 1: Proof of Concept (Week 3-4)

**Goal**: Build minimal Temporal prototype and validate architecture

### 1.1 Minimal Viable Workflow

**Scope**: Single-activity workflow (entity extraction only)

**Implementation**:
```python
# temporal_worker/activities.py
from temporalio import activity
from graphiti_core.llm_client import LLMClient
from graphiti_core.nodes import Episode, EntityNode

@activity.defn(name="extract_entities")
async def extract_entities_activity(
    episode_content: str,
    episode_id: str,
    group_id: str
) -> list[dict]:
    """Extract entities from episode content (Stage 1 only)."""
    # Use existing Graphiti logic
    llm_client = get_llm_client()  # Singleton
    entities = await llm_client.extract_entities(episode_content)
    
    return [entity.dict() for entity in entities]


# temporal_worker/workflows.py
from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta

@workflow.defn(name="IngestEpisodePOC")
class IngestEpisodePOCWorkflow:
    """POC: Single-stage workflow for entity extraction."""
    
    @workflow.run
    async def run(self, episode_content: str, episode_id: str, group_id: str) -> dict:
        # Stage 1: Extract entities
        entities = await workflow.execute_activity(
            extract_entities_activity,
            args=[episode_content, episode_id, group_id],
            start_to_close_timeout=timedelta(seconds=180),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=10),
                maximum_interval=timedelta(seconds=300),
                backoff_coefficient=2.0,
                maximum_attempts=4,
            ),
        )
        
        return {
            "episode_id": episode_id,
            "entities": entities,
            "status": "poc_complete"
        }
```

**Testing**:
1. **Unit test**: Test activity in isolation (mock LLM responses)
2. **Integration test**: Test workflow end-to-end with real LLM
3. **Load test**: Run 100 workflows concurrently (measure throughput)

**Success Criteria**:
- ✅ Workflow completes successfully (no crashes)
- ✅ Activity retry works (simulate LLM rate limit, verify backoff)
- ✅ Temporal Web UI shows workflow history
- ✅ Latency for entity extraction ≈86 seconds (matches current system)

---

### 1.2 Full Pipeline Workflow (Shadow Mode)

**Scope**: Complete 7-stage pipeline, read-only (no writes to FalkorDB)

**Implementation**:
```python
@workflow.defn(name="IngestEpisodeShadow")
class IngestEpisodeShadowWorkflow:
    """Full pipeline in shadow mode (no FalkorDB writes)."""
    
    @workflow.run
    async def run(self, episode: dict) -> dict:
        start_time = workflow.now()
        
        # Stage 1: Extract entities
        entities = await workflow.execute_activity(
            extract_entities_activity,
            episode,
            start_to_close_timeout=timedelta(seconds=180),
            retry_policy=STANDARD_RETRY_POLICY,
        )
        
        # Stage 2: Deduplicate nodes
        deduplicated_nodes = await workflow.execute_activity(
            deduplicate_nodes_activity,
            entities,
            start_to_close_timeout=timedelta(seconds=240),
            retry_policy=STANDARD_RETRY_POLICY,
        )
        
        # Stage 3: Extract edges
        edges = await workflow.execute_activity(
            extract_edges_activity,
            (episode, deduplicated_nodes),
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=STANDARD_RETRY_POLICY,
        )
        
        # Stage 4: Resolve edges
        resolved_edges = await workflow.execute_activity(
            resolve_edges_activity,
            (edges, deduplicated_nodes),
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=STANDARD_RETRY_POLICY,
        )
        
        # Stage 5: (SHADOW MODE) Simulate graph persistence
        # DO NOT write to FalkorDB in shadow mode
        await workflow.execute_activity(
            simulate_graph_persistence_activity,
            (deduplicated_nodes, resolved_edges),
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=STANDARD_RETRY_POLICY,
        )
        
        end_time = workflow.now()
        duration_seconds = (end_time - start_time).total_seconds()
        
        return {
            "episode_id": episode["id"],
            "duration": duration_seconds,
            "entities_count": len(entities),
            "nodes_count": len(deduplicated_nodes),
            "edges_count": len(resolved_edges),
            "status": "shadow_complete"
        }
```

**Shadow Mode Activity** (no writes):
```python
@activity.defn(name="simulate_graph_persistence")
async def simulate_graph_persistence_activity(
    nodes: list[dict],
    edges: list[dict]
) -> dict:
    """Simulate graph persistence (validation only, no writes)."""
    # Validate data structure (would fail if malformed)
    for node in nodes:
        assert "uuid" in node
        assert "name" in node
        assert "name_embedding" in node
    
    for edge in edges:
        assert "uuid" in edge
        assert "source_node_uuid" in edge
        assert "target_node_uuid" in edge
    
    # Simulate timing (sleep for typical persistence duration)
    await asyncio.sleep(5)  # Real persistence takes ~30s, simulate 5s
    
    return {
        "nodes_validated": len(nodes),
        "edges_validated": len(edges),
        "would_write": False
    }
```

**Parallel Execution**:
```bash
# Terminal 1: Current system (continues normal operation)
docker-compose logs -f graphiti-worker

# Terminal 2: Temporal worker (shadow mode)
python -m temporal_worker.main

# Terminal 3: Trigger shadow workflows (consume from same queue)
python -m temporal_worker.shadow_trigger --episodes 100
```

**Success Criteria**:
- ✅ Shadow workflow completes all 5 stages without errors
- ✅ Latency matches current system (±10%): 226s ±23s = 203-249s acceptable
- ✅ No interference with current system (current system throughput unchanged)
- ✅ Activity retries work correctly (test by killing worker mid-stage)

---

### 1.3 Innovation Exploration

**Opportunities to Explore** (not required for migration, but potential wins):

#### 1. **Parallel Activity Execution**

**Current**: Stages run sequentially
**Temporal**: Can run independent activities in parallel

```python
# Example: Run entity extraction and previous episode retrieval in parallel
[entities, previous_episodes] = await asyncio.gather(
    workflow.execute_activity(extract_entities_activity, ...),
    workflow.execute_activity(get_previous_episodes_activity, ...)
)
```

**Potential Win**: Reduce latency by 10-20% if previous episode retrieval takes significant time

---

#### 2. **Adaptive Rate Limiting**

**Current**: Fixed rate limits (100 req/sec global, 10 req/sec/group), uncoordinated across workers

**Temporal**: Shared state via workflow queries

```python
@workflow.defn
class RateLimitCoordinatorWorkflow:
    """Centralized rate limit coordinator (runs as singleton)."""
    
    def __init__(self):
        self.current_quota = 100  # req/sec
        self.used_this_second = 0
    
    @workflow.query
    def can_acquire(self) -> bool:
        return self.used_this_second < self.current_quota
    
    @workflow.signal
    def acquire(self):
        self.used_this_second += 1
    
    @workflow.signal
    def adjust_quota(self, new_quota: int):
        """Dynamically adjust based on LLM quota usage."""
        self.current_quota = new_quota
```

**Potential Win**: More accurate rate limiting, auto-scale workers based on quota

---

#### 3. **Smart Batching**

**Current**: batch_size=1 (one episode per worker poll)

**Temporal**: Can batch similar episodes for more efficient LLM calls

```python
@activity.defn
async def extract_entities_batch_activity(episodes: list[dict]) -> list[list[dict]]:
    """Extract entities for multiple episodes in one LLM call."""
    # Send all episode content to LLM in one request
    batch_prompt = "\n\n".join([f"Episode {i}: {ep['content']}" for i, ep in enumerate(episodes)])
    entities_per_episode = await llm_client.extract_entities_batch(batch_prompt)
    return entities_per_episode
```

**Potential Win**: Reduce LLM calls by 50-70% if episodes can be batched (lower cost, higher throughput)

---

#### 4. **Incremental Checkpointing**

**Current**: Stage-level checkpoints (in-memory only)

**Temporal**: Sub-activity checkpoints via heartbeats

```python
@activity.defn
async def deduplicate_nodes_activity(entities: list[dict]) -> list[dict]:
    """Deduplicate nodes with progress heartbeats."""
    activity.heartbeat("Starting deduplication")
    
    deduplicated = []
    for i, entity in enumerate(entities):
        deduplicated.append(await deduplicate_single_node(entity))
        
        # Heartbeat every 10 entities (allows resumption)
        if i % 10 == 0:
            activity.heartbeat(f"Processed {i}/{len(entities)} entities")
    
    return deduplicated
```

**Potential Win**: Faster recovery from worker crashes (resume from last heartbeat, not stage start)

---

**Phase 1 Go/No-Go Decision**:
- ✅ POC workflow runs successfully
- ✅ Shadow mode completes 100 episodes without errors
- ✅ Latency within acceptable range (203-249 seconds)
- ✅ No current system impact
- ✅ At least 1 innovation explored (optional)

**Decision Point**: If all criteria met, proceed to Phase 2. If latency is worse, investigate bottlenecks before continuing.

---

## Phase 2: Canary Deployment (Week 5-6)

**Goal**: Route 1% of production traffic to Temporal, measure side-by-side

### 2.1 Traffic Splitting

**Architecture**:
```
HTTP Webhook → Queued (LevelDB)
                    ↓
              [Traffic Splitter]
                /             \
           99% ↓               ↓ 1%
      Current Workers    Temporal Workers
              ↓                ↓
           FalkorDB  ←  (both write here)
```

**Implementation**:
```python
# traffic_splitter.py
import random

class TrafficSplitter:
    def __init__(self, temporal_percentage: float = 1.0):
        self.temporal_percentage = temporal_percentage
    
    def route_episode(self, episode: dict) -> str:
        """Return 'temporal' or 'current' based on percentage."""
        if random.random() < (self.temporal_percentage / 100):
            return 'temporal'
        return 'current'
    
    async def enqueue(self, episode: dict):
        route = self.route_episode(episode)
        
        if route == 'temporal':
            # Start Temporal workflow
            await temporal_client.start_workflow(
                IngestEpisodeWorkflow.run,
                episode,
                id=f"episode-{episode['id']}",
                task_queue="graphiti-ingestion"
            )
        else:
            # Push to current queue
            await queued_client.push([episode], queue_name="ingestion")
```

**Monitoring Dashboard** (critical for canary):
```
Canary Metrics (1% Traffic to Temporal)
========================================

                Current System    Temporal    Delta
Throughput:     35.6 eps/hr      0.36 eps/hr  --
Latency p50:    226s             231s         +2.2%
Latency p99:    540s             567s         +5.0%
Error Rate:     1.2%             1.8%         +50% ❌
Retry Rate:     8.5%             9.1%         +7%
DLQ Rate:       0.4%             0.5%         +25%

Top Errors (Temporal):
  1. ActivityTimeout: 3 occurrences (edge_extraction stage)
  2. NodeNotFoundError: 2 occurrences (graph_persistence stage)
```

---

### 2.2 Comparison Analysis

**Key Questions**:
1. **Is Temporal slower?** If yes, why? (Activity timeouts too short? Serialization overhead?)
2. **Is error rate higher?** If yes, what error types? (Configuration issue? Real problem?)
3. **Are retries more frequent?** If yes, is retry policy too aggressive?
4. **Any new error types?** (Temporal-specific errors we didn't anticipate?)

**Example Analysis**:
```
Finding: Temporal latency is 5% higher (231s vs. 226s)
Root Cause: Workflow serialization overhead (~5s per workflow)
Fix: Use local activities for fast operations (previous episode retrieval)
Result: Latency reduced to 224s (1% improvement vs. current!)
```

---

### 2.3 Rollback Plan

**Trigger Conditions** (automatic rollback):
- Error rate >3% (vs. 1.2% baseline)
- Latency p99 >700s (vs. 540s baseline)
- Any workflow crash/panic
- FalkorDB memory exhausted (Temporal writes more data?)

**Rollback Procedure**:
```bash
# Step 1: Stop Temporal worker
pkill -f temporal_worker

# Step 2: Set traffic split to 0%
curl -X POST http://localhost:8003/admin/traffic-split -d '{"temporal_percentage": 0}'

# Step 3: Verify current system handling 100% traffic
watch -n 5 'redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)"'

# Step 4: Review Temporal logs for root cause
docker logs graphiti-temporal-worker > /tmp/temporal-failure.log
```

**Rollback is safe because**:
- Episode UUID deduplication prevents duplicate data
- No data loss (all episodes idempotent)
- Current system never stopped (was handling 99% traffic)

---

**Phase 2 Go/No-Go Decision**:
- ✅ Temporal handles 1% traffic for 7 consecutive days
- ✅ Error rate ≤ baseline (1.2% acceptable)
- ✅ Latency within ±10% of baseline
- ✅ No rollbacks triggered
- ✅ Root cause understood for any anomalies

**Decision Point**: If canary is stable, proceed to Phase 3 (10% traffic). If issues found, fix before scaling up.

---

## Phase 3: Gradual Rollout (Week 7-10)

**Goal**: Incrementally scale Temporal to 100% traffic

### 3.1 Rollout Schedule

| Week | Traffic Split | Temporal Workers | Monitoring Frequency |
|------|---------------|------------------|----------------------|
| 7 | 10% | 1 | Every 4 hours |
| 8 | 25% | 2 | Every 8 hours |
| 9 | 50% | 4 | Daily |
| 10 | 100% | 8 | Daily |

**Week-by-Week Plan**:

#### **Week 7: 10% Traffic**
- **Action**: Increase traffic split from 1% to 10%
- **Temporal workers**: 1 worker (handles ~3.6 episodes/hour)
- **Current workers**: 2 workers (handles ~32 episodes/hour)
- **Monitoring**: Check metrics every 4 hours
- **Go criteria**: Error rate ≤1.5%, latency p99 ≤600s, zero crashes
- **No-go**: Rollback to 1% if error rate >2%

#### **Week 8: 25% Traffic**
- **Action**: Increase traffic split from 10% to 25%
- **Temporal workers**: 2 workers (handles ~9 episodes/hour)
- **Current workers**: 2 workers (handles ~27 episodes/hour)
- **Monitoring**: Check metrics every 8 hours
- **Go criteria**: Error rate ≤1.3%, latency p99 ≤600s
- **No-go**: Rollback to 10% if sustained latency >700s

#### **Week 9: 50% Traffic**
- **Action**: Increase traffic split from 25% to 50%
- **Temporal workers**: 4 workers (handles ~18 episodes/hour)
- **Current workers**: 2 workers (handles ~18 episodes/hour)
- **Monitoring**: Check metrics daily
- **Go criteria**: Error rate ≤1.2% (matches baseline), latency p50 ≤240s
- **No-go**: Rollback to 25% if FalkorDB memory >90%

#### **Week 10: 100% Traffic**
- **Action**: Increase traffic split from 50% to 100%
- **Temporal workers**: 8 workers (handles ~36 episodes/hour)
- **Current workers**: 0 (stopped, but containers kept running for 2 weeks)
- **Monitoring**: Check metrics daily for first week, then weekly
- **Go criteria**: Error rate ≤1.2%, throughput ≥36 episodes/hour
- **No-go**: Rollback to 50% if throughput drops <30 episodes/hour

---

### 3.2 Worker Scaling Strategy

**Auto-Scaling Logic** (optional, can be manual):
```python
# Auto-scale based on queue depth and LLM quota
def calculate_optimal_workers(queue_depth: int, llm_quota_remaining: float) -> int:
    """Determine optimal worker count."""
    
    # Base worker count on queue depth
    if queue_depth < 5:
        base_workers = 2
    elif queue_depth < 20:
        base_workers = 4
    elif queue_depth < 50:
        base_workers = 8
    else:
        base_workers = 12
    
    # Adjust for LLM quota (reduce workers if quota low)
    if llm_quota_remaining < 0.10:  # <10% quota remaining
        base_workers = max(1, base_workers // 4)  # Reduce to 25%
    elif llm_quota_remaining < 0.25:  # <25% quota remaining
        base_workers = max(2, base_workers // 2)  # Reduce to 50%
    
    return base_workers
```

---

### 3.3 Monitoring Alerts

**Automated Alerts** (send to Slack/email):
```yaml
alerts:
  - name: high_error_rate
    condition: error_rate > 0.02  # >2%
    window: 1h
    action: notify_oncall
  
  - name: high_latency
    condition: latency_p99 > 700s  # >11.6 minutes
    window: 1h
    action: notify_oncall
  
  - name: low_throughput
    condition: episodes_per_hour < 30
    window: 2h
    action: notify_team
  
  - name: dlq_growth
    condition: dlq_size > 20
    action: notify_team
  
  - name: worker_crash
    condition: temporal_worker_count < expected_worker_count
    action: notify_oncall + auto_restart
  
  - name: quota_exhaustion
    condition: llm_quota_remaining < 0.05  # <5%
    action: notify_team + reduce_workers
```

---

**Phase 3 Go/No-Go Decision** (at 100% traffic):
- ✅ Temporal handles 100% traffic for 7 consecutive days
- ✅ Error rate ≤ baseline (1.2%)
- ✅ Throughput ≥ baseline (36 episodes/hour)
- ✅ Latency p50 ≤ 240s (within 10% of baseline)
- ✅ No manual interventions required (auto-scaling works)
- ✅ Team comfortable with Temporal Web UI and troubleshooting

**Decision Point**: If stable at 100% for 1 week, proceed to Phase 4 (deprecation). If issues persist, stay at 50% and investigate.

---

## Phase 4: Deprecation (Week 11-14)

**Goal**: Fully deprecate current queued-based system

### 4.1 Deprecation Timeline

| Week | Action | Risk |
|------|--------|------|
| 11 | Stop current workers, keep queue service running | LOW (Temporal is primary for 1 week) |
| 12 | Monitor Temporal-only operation | LOW |
| 13 | Stop queue service, archive LevelDB data | MEDIUM (no rollback after this) |
| 14 | Remove current worker code, update documentation | LOW |

---

### 4.2 Final Verification

**Before Stopping Queue Service**:
```bash
# Step 1: Verify queue is empty (all episodes processed)
curl http://localhost:8093/stats/ingestion
# Expected: {"size": 0, "visible_count": 0}

# Step 2: Verify DLQ is empty or reviewed
curl http://localhost:8093/stats/dead_letter
# Expected: {"size": 0} or all tasks reviewed and resolved

# Step 3: Archive LevelDB data
docker exec graphiti-queued-1 tar -czf /tmp/leveldb-archive-$(date +%Y%m%d).tar.gz /data
docker cp graphiti-queued-1:/tmp/leveldb-archive-*.tar.gz /opt/stacks/graphiti/backups/

# Step 4: Stop queue service
docker-compose stop queued
```

---

### 4.3 Documentation Updates

**Files to Update**:
1. **README.md**: Remove queued references, add Temporal instructions
2. **AGENTS.md**: Update worker service commands
3. **docker-compose.yml**: Remove queued service, add temporal worker
4. **deployment guide**: Update production deployment steps
5. **troubleshooting guide**: Add Temporal-specific debugging

**New Documentation**:
1. **temporal-operations.md**: How to start/stop workers, scale, troubleshoot
2. **temporal-workflows.md**: Workflow and activity reference
3. **temporal-monitoring.md**: Metrics, alerts, dashboards

---

### 4.4 Celebration & Retrospective

**Metrics to Share** (vs. baseline):
- Throughput improvement: X%
- Latency improvement: X%
- Error rate improvement: X%
- Observability improvement: ✅ Web UI, searchable history, per-activity metrics
- Innovation wins: [List features enabled by Temporal that weren't possible before]

**Lessons Learned**:
- What went well?
- What was harder than expected?
- What would we do differently next time?
- What innovations should we prioritize next?

---

## Risk Mitigation

### High-Risk Scenarios

#### 1. **FalkorDB Memory Exhaustion**

**Risk**: Temporal writes more data, FalkorDB OOMs

**Mitigation**:
- Monitor FalkorDB memory continuously (alert at 90%)
- Increase memory limit from 8GB to 12GB runtime (24GB container) before Phase 3
- Test memory usage with 100 episodes in Phase 1

**Rollback**: Reduce traffic split to previous phase

---

#### 2. **LLM Quota Exhaustion**

**Risk**: Temporal workers consume quota faster than current system

**Mitigation**:
- Implement adaptive worker scaling (reduce workers when quota <10%)
- Monitor quota usage every 5 minutes
- Keep Anthropic fallback enabled

**Rollback**: Reduce worker count, not traffic split (workers are bottleneck, not Temporal)

---

#### 3. **Temporal Server Unavailable**

**Risk**: Temporal server crashes, all workflows stop

**Mitigation**:
- Run Temporal server in HA mode (if not already)
- Keep current system ready to restart (docker-compose up queued && worker)
- Practice rollback procedure regularly

**Rollback**: Traffic splitter automatically routes to current system if Temporal client connection fails

---

#### 4. **Data Inconsistency**

**Risk**: Temporal and current system process same episode, duplicate data in FalkorDB

**Mitigation**:
- Episode UUID deduplication (already implemented in Graphiti)
- Test dual-write scenario in Phase 1 (verify only 1 copy persists)
- Monitor for duplicate episodes in Phase 2-3

**Recovery**: Run deduplication script on FalkorDB (identifies and merges duplicates)

---

## Innovation Roadmap (Post-Migration)

**Enabled by Temporal** (prioritize after migration complete):

### Short-Term (Month 1-2)
1. **Parallel Activity Execution**: Reduce latency by 15-20%
2. **Adaptive Rate Limiting**: Auto-scale workers based on quota
3. **Better Observability**: Grafana dashboards with Temporal metrics

### Medium-Term (Month 3-6)
4. **Smart Batching**: Batch similar episodes for efficient LLM calls
5. **Incremental Checkpointing**: Faster recovery from worker crashes
6. **Activity Caching**: Cache LLM responses for similar prompts (reduce cost)

### Long-Term (Month 6-12)
7. **Multi-Region Support**: Run workers in multiple regions for resilience
8. **Cost Optimization**: Experiment with cheaper LLM models for simple tasks
9. **Real-Time Streaming**: Process episodes as they arrive (sub-second latency)

---

## Success Criteria (Final)

**Migration is successful when**:
1. ✅ Temporal handles 100% of production traffic
2. ✅ Error rate ≤ baseline (1.2%)
3. ✅ Throughput ≥ baseline (36 episodes/hour)
4. ✅ Latency p50 within 10% of baseline (<249s)
5. ✅ Zero data loss or corruption
6. ✅ Team comfortable with Temporal operations
7. ✅ Current system fully deprecated (queue service stopped)
8. ✅ At least 1 innovation deployed (parallel execution, adaptive scaling, or caching)

**Migration is a FAILURE if**:
- Data loss occurs (even 1 episode)
- Worker crashes persist after Phase 3
- Error rate >3% sustained for 1 week
- Team cannot troubleshoot Temporal issues without external help

---

## Timeline Summary

| Phase | Duration | Key Milestone | Risk Level |
|-------|----------|---------------|------------|
| **Phase 0** | Week 1-2 | Baseline metrics collected | LOW |
| **Phase 1** | Week 3-4 | POC workflow complete, shadow mode tested | LOW |
| **Phase 2** | Week 5-6 | 1% canary stable for 7 days | MEDIUM |
| **Phase 3** | Week 7-10 | Gradual rollout to 100% traffic | HIGH |
| **Phase 4** | Week 11-14 | Current system deprecated | MEDIUM |
| **Total** | **14 weeks** | **~3.5 months** | |

**Accelerated Timeline** (if everything goes smoothly):
- Phase 0-1: 2 weeks (vs. 4)
- Phase 2: 1 week (vs. 2)
- Phase 3: 2 weeks (vs. 4)
- Phase 4: 1 week (vs. 4)
- **Total**: **6 weeks** (~1.5 months)

**Conservative Timeline** (if issues arise):
- Add 2 weeks buffer per phase for troubleshooting
- **Total**: **22 weeks** (~5.5 months)

---

## Conclusion

This migration strategy prioritizes **data-driven decision making** and **incremental rollout** over speed. Each phase has explicit go/no-go criteria based on metrics, not gut feeling.

**Why this approach works**:
- ✅ **Zero risk**: Both systems coexist, rollback is trivial at any phase
- ✅ **Data-driven**: Decisions based on metrics, not opinions
- ✅ **Innovation**: Migration is opportunity to improve, not just replicate
- ✅ **Reversible**: Can stay at any phase indefinitely (e.g., 50% traffic forever if safer)

**What makes this different from typical migrations**:
- 🚀 **Innovation focus**: Explicitly encourages exploring Temporal features beyond current capabilities
- 📊 **Baseline-first**: Establishes current system performance before changing anything
- 🔄 **Incremental**: 1% → 10% → 50% → 100% over weeks, with explicit criteria at each step
- 🛡️ **Fail-safe**: Rollback is always one command away, no data loss risk

**Next Steps** (if plan approved):
1. Review this plan with team
2. Agree on timeline (conservative or accelerated?)
3. Start Phase 0 (infrastructure + baseline) immediately
4. Schedule weekly check-ins to review metrics and make go/no-go decisions

---

**Document Status**: ✅ Complete (Task #6 of 8)

**Next Document**: `parallel-testing-strategy.md` (Task #7)
