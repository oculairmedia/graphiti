# Parallel Testing Strategy

**Purpose**: Design comprehensive test harness to validate Temporal migration safety and measure performance improvements.

**Philosophy**: "Trust, but verify" - run both systems in parallel during migration phases, collect metrics, make data-driven decisions.

---

## Testing Approach Overview

### Core Principle: Shadow Mode First
Before routing real traffic to Temporal, validate with:
1. **Shadow mode**: Temporal processes episodes without database writes (read-only)
2. **Parallel validation**: Compare Temporal results vs. current system
3. **Canary deployment**: Route small % of real traffic, compare metrics
4. **Full rollout**: Gradual increase based on metrics validation

### Test Pyramid

```
                    /\
                   /  \
                  / E2E\          Manual/Exploratory (5%)
                 /______\
                /        \
               / Integration\     Full workflow tests (15%)
              /____________\
             /              \
            /   Unit Tests   \   Activity isolation (80%)
           /__________________\
```

**Target Coverage**:
- **Unit tests**: 80% of test effort (fast, cheap, isolate activities)
- **Integration tests**: 15% of test effort (end-to-end with real services)
- **E2E/Manual**: 5% of test effort (production-like scenarios)

---

## 1. Unit Tests (Activity Isolation)

### Objective
Test each Temporal activity in isolation with mocked dependencies.

### Test Structure

#### 1.1 Entity Extraction Activity Tests

**File**: `tests/temporal/activities/test_extract_entities.py`

```python
import pytest
from unittest.mock import Mock, AsyncMock
from temporal.activities.extract_entities import extract_entities_activity
from graphiti_core.nodes import EpisodeType, EntityNode

@pytest.mark.asyncio
async def test_extract_entities_success():
    """Test successful entity extraction with mocked LLM"""
    # Setup
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = """
    [
        {"name": "John Doe", "type": "PERSON", "summary": "Software engineer"},
        {"name": "Acme Corp", "type": "ORGANIZATION", "summary": "Tech company"}
    ]
    """
    
    # Execute
    result = await extract_entities_activity(
        episode_uuid="test-123",
        episode_content="John Doe works at Acme Corp",
        episode_type=EpisodeType.message,
        llm_client=mock_llm
    )
    
    # Assert
    assert len(result.entities) == 2
    assert result.entities[0].name == "John Doe"
    assert result.entities[1].name == "Acme Corp"
    assert mock_llm.generate.call_count == 1

@pytest.mark.asyncio
async def test_extract_entities_llm_transient_error():
    """Test retry behavior on transient LLM error"""
    mock_llm = AsyncMock()
    mock_llm.generate.side_effect = [
        Exception("502 Bad Gateway"),  # First call fails
        """[{"name": "Test", "type": "PERSON"}]"""  # Second call succeeds
    ]
    
    # Temporal automatically retries based on RetryPolicy
    result = await extract_entities_activity(
        episode_uuid="test-123",
        episode_content="Test content",
        episode_type=EpisodeType.message,
        llm_client=mock_llm
    )
    
    assert len(result.entities) == 1
    assert mock_llm.generate.call_count == 2

@pytest.mark.asyncio
async def test_extract_entities_permanent_error():
    """Test DLQ routing on permanent error"""
    mock_llm = AsyncMock()
    mock_llm.generate.side_effect = PermanentError("Invalid episode format")
    
    # Should NOT retry, should fail immediately
    with pytest.raises(PermanentError):
        await extract_entities_activity(
            episode_uuid="test-123",
            episode_content="",  # Invalid
            episode_type=EpisodeType.message,
            llm_client=mock_llm
        )
    
    assert mock_llm.generate.call_count == 1  # No retries

@pytest.mark.asyncio
async def test_extract_entities_timeout():
    """Test activity timeout handling"""
    mock_llm = AsyncMock()
    
    async def slow_generate(*args, **kwargs):
        await asyncio.sleep(120)  # Simulate 2-minute LLM call
    
    mock_llm.generate = slow_generate
    
    # Activity should timeout and be retryable
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            extract_entities_activity(..., llm_client=mock_llm),
            timeout=90  # Activity timeout: 90 seconds
        )
```

**Coverage Goals**:
- ✅ Successful extraction
- ✅ Transient errors (retryable)
- ✅ Permanent errors (non-retryable)
- ✅ Timeouts
- ✅ Empty results
- ✅ Malformed LLM responses
- ✅ Rate limit errors (429)

#### 1.2 Node Deduplication Activity Tests

**File**: `tests/temporal/activities/test_deduplicate_nodes.py`

```python
@pytest.mark.asyncio
async def test_deduplicate_nodes_success():
    """Test node deduplication with mocked embedder and graph driver"""
    mock_embedder = AsyncMock()
    mock_embedder.embed.return_value = [0.1, 0.2, 0.3, ...]  # 1024-dim vector
    
    mock_driver = AsyncMock()
    mock_driver.search_nodes.return_value = [
        ExistingNode(uuid="old-123", name="John Doe", similarity=0.92),
        ExistingNode(uuid="old-456", name="Jon Doe", similarity=0.85)
    ]
    
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = """
    {
        "duplicate_of": "old-123",
        "reason": "Same person, minor spelling variation"
    }
    """
    
    result = await deduplicate_nodes_activity(
        entities=[EntityNode(name="John Doe", type="PERSON", ...)],
        embedder=mock_embedder,
        driver=mock_driver,
        llm_client=mock_llm
    )
    
    assert result.deduplicated[0].existing_uuid == "old-123"
    assert result.deduplicated[0].merged_with == "John Doe"
    assert mock_embedder.embed.call_count == 1
    assert mock_driver.search_nodes.call_count == 1

@pytest.mark.asyncio
async def test_deduplicate_nodes_no_matches():
    """Test new node creation when no duplicates found"""
    mock_embedder = AsyncMock()
    mock_embedder.embed.return_value = [0.1, 0.2, ...]
    
    mock_driver = AsyncMock()
    mock_driver.search_nodes.return_value = []  # No matches
    
    result = await deduplicate_nodes_activity(
        entities=[EntityNode(name="Unique Person", type="PERSON", ...)],
        embedder=mock_embedder,
        driver=mock_driver,
        llm_client=None  # No LLM needed if no matches
    )
    
    assert len(result.new_nodes) == 1
    assert result.new_nodes[0].name == "Unique Person"

@pytest.mark.asyncio
async def test_deduplicate_nodes_embedder_failure():
    """Test fallback when embedder fails"""
    mock_embedder = AsyncMock()
    mock_embedder.embed.side_effect = Exception("GPU OOM")
    
    # Should be retryable (TransientError)
    with pytest.raises(TransientError):
        await deduplicate_nodes_activity(
            entities=[EntityNode(name="Test", ...)],
            embedder=mock_embedder,
            driver=mock_driver,
            llm_client=mock_llm
        )
```

**Coverage Goals**:
- ✅ Successful deduplication (match found, LLM confirms)
- ✅ No matches found (create new node)
- ✅ Embedder failures (GPU OOM, timeout)
- ✅ Graph driver failures (FalkorDB down)
- ✅ LLM failures (disambiguation)
- ✅ Batch processing (10+ entities)

#### 1.3 Edge Extraction Activity Tests

**File**: `tests/temporal/activities/test_extract_edges.py`

```python
@pytest.mark.asyncio
async def test_extract_edges_success():
    """Test edge extraction with valid nodes"""
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = """
    [
        {
            "source_entity": "John Doe",
            "target_entity": "Acme Corp",
            "relation_type": "WORKS_AT",
            "summary": "John is employed by Acme"
        }
    ]
    """
    
    result = await extract_edges_activity(
        episode_uuid="test-123",
        episode_content="John Doe works at Acme Corp",
        entities=["John Doe", "Acme Corp"],
        llm_client=mock_llm
    )
    
    assert len(result.edges) == 1
    assert result.edges[0].source == "John Doe"
    assert result.edges[0].target == "Acme Corp"
    assert result.edges[0].relation == "WORKS_AT"

@pytest.mark.asyncio
async def test_extract_edges_no_relationships():
    """Test when no relationships exist between entities"""
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = "[]"  # Empty list
    
    result = await extract_edges_activity(
        episode_uuid="test-123",
        episode_content="John lives in NYC. Acme is in SF.",
        entities=["John", "Acme"],
        llm_client=mock_llm
    )
    
    assert len(result.edges) == 0
```

**Coverage Goals**:
- ✅ Valid edges extracted
- ✅ No relationships found
- ✅ Invalid entity references
- ✅ Self-referential edges
- ✅ LLM hallucination (creates non-existent entities)

#### 1.4 Save to Graph Activity Tests

**File**: `tests/temporal/activities/test_save_to_graph.py`

```python
@pytest.mark.asyncio
async def test_save_to_graph_success():
    """Test graph persistence with mocked FalkorDB driver"""
    mock_driver = AsyncMock()
    mock_driver.save_nodes.return_value = {"created": 2, "updated": 0}
    mock_driver.save_edges.return_value = {"created": 1, "updated": 0}
    
    result = await save_to_graph_activity(
        nodes=[...],
        edges=[...],
        driver=mock_driver
    )
    
    assert result.nodes_created == 2
    assert result.edges_created == 1
    assert mock_driver.save_nodes.call_count == 1
    assert mock_driver.save_edges.call_count == 1

@pytest.mark.asyncio
async def test_save_to_graph_falkordb_oom():
    """Test handling FalkorDB out-of-memory"""
    mock_driver = AsyncMock()
    mock_driver.save_nodes.side_effect = Exception("OOM command not allowed when used memory > 'maxmemory'")
    
    # Should be retryable (TransientError)
    with pytest.raises(TransientError):
        await save_to_graph_activity(
            nodes=[...],
            edges=[...],
            driver=mock_driver
        )

@pytest.mark.asyncio
async def test_save_to_graph_idempotency():
    """Test that saving same data twice is idempotent"""
    mock_driver = AsyncMock()
    mock_driver.save_nodes.return_value = {"created": 2, "updated": 0}
    
    # First save
    result1 = await save_to_graph_activity(nodes=[...], edges=[...], driver=mock_driver)
    
    # Second save (simulating retry after timeout)
    mock_driver.save_nodes.return_value = {"created": 0, "updated": 2}  # Now updates
    result2 = await save_to_graph_activity(nodes=[...], edges=[...], driver=mock_driver)
    
    assert result1.nodes_created == 2
    assert result2.nodes_updated == 2  # Idempotent
```

**Coverage Goals**:
- ✅ Successful batch save
- ✅ FalkorDB OOM (retryable)
- ✅ Network failures (retryable)
- ✅ Idempotency (duplicate saves)
- ✅ Partial failures (some nodes saved, some failed)

---

## 2. Integration Tests (Full Workflow)

### Objective
Test complete `IngestEpisodeWorkflow` end-to-end with real services (not mocked).

### Test Environment Setup

**Docker Compose Test Stack**:
```yaml
# tests/integration/docker-compose.test.yml
services:
  temporal-test:
    image: temporalio/auto-setup:latest
    ports:
      - "7234:7233"  # Different port to avoid conflicts
    environment:
      - SKIP_SCHEMA_SETUP=false
      - SKIP_DEFAULT_NAMESPACE_CREATION=false
  
  falkordb-test:
    image: falkordb/falkordb:latest
    ports:
      - "6380:6379"  # Different port
    volumes:
      - ./test-data:/data
  
  vllm-test:
    image: vllm/vllm-openai:latest
    # ... (smaller model for faster tests)
```

### Integration Test Structure

#### 2.1 Full Pipeline Test (Happy Path)

**File**: `tests/integration/test_full_pipeline.py`

```python
import pytest
from temporalio.client import Client
from temporalio.worker import Worker
from temporal.workflows.ingest_episode import IngestEpisodeWorkflow
from temporal.activities import *

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_pipeline_success():
    """
    Test complete episode ingestion workflow end-to-end.
    Uses real Temporal, FalkorDB, and LLM services.
    """
    # Connect to test Temporal server
    client = await Client.connect("localhost:7234")
    
    # Start worker in background
    worker = Worker(
        client,
        task_queue="test-ingestion-queue",
        workflows=[IngestEpisodeWorkflow],
        activities=[
            extract_entities_activity,
            deduplicate_nodes_activity,
            extract_edges_activity,
            resolve_edges_activity,
            save_to_graph_activity
        ]
    )
    
    async with worker:
        # Execute workflow
        result = await client.execute_workflow(
            IngestEpisodeWorkflow.run,
            args=[{
                "episode_uuid": "integration-test-001",
                "episode_content": "Alice met Bob at Google. They discussed AI research.",
                "episode_type": "message",
                "source_description": "Test conversation",
                "created_at": "2026-01-12T02:00:00Z"
            }],
            id="test-workflow-001",
            task_queue="test-ingestion-queue"
        )
        
        # Assertions
        assert result.success == True
        assert result.nodes_created >= 3  # Alice, Bob, Google
        assert result.edges_created >= 2  # Alice-met-Bob, Alice-at-Google or Bob-at-Google
        assert result.duration_seconds < 300  # Should complete in <5 minutes
        
        # Verify data in FalkorDB
        driver = FalkorDBDriver(host="localhost", port=6380, database="test_graph")
        nodes = await driver.get_nodes_by_episode("integration-test-001")
        assert len(nodes) >= 3
        
        edges = await driver.get_edges_by_episode("integration-test-001")
        assert len(edges) >= 2

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_pipeline_with_retries():
    """
    Test workflow resilience when activities fail transiently.
    Simulate LLM rate limit, verify automatic retry.
    """
    client = await Client.connect("localhost:7234")
    
    # Mock LLM to fail first 2 times, succeed on 3rd
    with patch('temporal.activities.extract_entities.llm_client') as mock_llm:
        mock_llm.generate.side_effect = [
            Exception("429 Rate Limit"),
            Exception("502 Bad Gateway"),
            """[{"name": "Test", "type": "PERSON"}]"""  # Success
        ]
        
        result = await client.execute_workflow(
            IngestEpisodeWorkflow.run,
            args=[...],
            id="test-retry-001",
            task_queue="test-ingestion-queue"
        )
        
        assert result.success == True
        assert result.retry_count == 2  # Failed twice, succeeded on 3rd

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_pipeline_permanent_failure():
    """
    Test that permanent errors skip retries and go to DLQ.
    """
    client = await Client.connect("localhost:7234")
    
    with patch('temporal.activities.extract_entities.validate_episode') as mock_validate:
        mock_validate.side_effect = PermanentError("Invalid episode format")
        
        with pytest.raises(WorkflowFailureError) as exc:
            await client.execute_workflow(
                IngestEpisodeWorkflow.run,
                args=[{"episode_uuid": "bad-episode", ...}],
                id="test-permanent-fail-001",
                task_queue="test-ingestion-queue"
            )
        
        # Should fail immediately without retries
        assert "PermanentError" in str(exc.value)
        assert exc.value.retry_count == 0

@pytest.mark.integration
@pytest.mark.asyncio
async def test_workflow_crash_recovery():
    """
    Test that workflow resumes from checkpoint after worker crash.
    """
    client = await Client.connect("localhost:7234")
    
    # Start workflow
    handle = await client.start_workflow(
        IngestEpisodeWorkflow.run,
        args=[...],
        id="test-crash-recovery-001",
        task_queue="test-ingestion-queue"
    )
    
    # Wait for entity extraction to complete
    await asyncio.sleep(10)
    
    # Simulate worker crash (stop worker, lose in-memory state)
    # ... stop worker ...
    
    # Restart worker
    new_worker = Worker(client, task_queue="test-ingestion-queue", ...)
    async with new_worker:
        # Workflow should resume from last checkpoint (after entity extraction)
        result = await handle.result()
        
        assert result.success == True
        # Verify entity extraction was NOT re-run (check LLM call count)
```

**Coverage Goals**:
- ✅ Happy path (all activities succeed first try)
- ✅ Transient failures with automatic retry
- ✅ Permanent failures (immediate DLQ)
- ✅ Worker crash recovery
- ✅ Timeout handling
- ✅ Concurrent workflow execution (10+ workflows in parallel)

#### 2.2 Shadow Mode Test (Validation Against Current System)

**File**: `tests/integration/test_shadow_mode.py`

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_shadow_mode_validation():
    """
    Process same episode through BOTH current system and Temporal.
    Compare results to ensure functional equivalence.
    """
    episode_data = {
        "uuid": "shadow-test-001",
        "content": "Test episode content",
        "type": "message"
    }
    
    # Process through CURRENT system
    current_worker = IngestionWorker(...)
    current_result = await current_worker._process_episode(episode_data)
    
    # Process through TEMPORAL (shadow mode, read-only)
    temporal_client = await Client.connect("localhost:7234")
    temporal_result = await temporal_client.execute_workflow(
        IngestEpisodeWorkflow.run,
        args=[episode_data],
        id="shadow-test-001",
        task_queue="shadow-queue"
    )
    
    # Compare results
    assert temporal_result.nodes_created == current_result.nodes_created
    assert temporal_result.edges_created == current_result.edges_created
    
    # Compare node details
    for temporal_node, current_node in zip(temporal_result.nodes, current_result.nodes):
        assert temporal_node.name == current_node.name
        assert temporal_node.type == current_node.type
        # Allow minor summary differences (LLM non-determinism)
        assert similarity(temporal_node.summary, current_node.summary) > 0.85
    
    # Compare edge details
    for temporal_edge, current_edge in zip(temporal_result.edges, current_result.edges):
        assert temporal_edge.source == current_edge.source
        assert temporal_edge.target == current_edge.target
        assert temporal_edge.relation == current_edge.relation
```

**Coverage Goals**:
- ✅ Functional equivalence (same nodes/edges)
- ✅ Latency comparison (Temporal should be ≤10% slower initially)
- ✅ Resource usage comparison (CPU, memory, GPU)
- ✅ Error rate comparison (should be ≤current system)

---

## 3. Load Tests (Performance Validation)

### Objective
Validate Temporal can handle production load (36 episodes/hour baseline, 360 episodes/hour peak).

### Load Test Scenarios

#### 3.1 Baseline Load Test

**File**: `tests/load/test_baseline_load.py`

```python
import pytest
from locust import HttpUser, task, between
from temporalio.client import Client

class TemporalWorkflowUser(HttpUser):
    wait_time = between(1, 5)  # 1-5 second pause between workflows
    
    async def on_start(self):
        self.client = await Client.connect("localhost:7233")
    
    @task
    async def ingest_episode(self):
        """Submit episode ingestion workflow"""
        episode = generate_random_episode()
        
        start_time = time.time()
        result = await self.client.execute_workflow(
            IngestEpisodeWorkflow.run,
            args=[episode],
            id=f"load-test-{uuid.uuid4()}",
            task_queue="production-queue"
        )
        duration = time.time() - start_time
        
        # Record metrics
        self.environment.events.request.fire(
            request_type="workflow",
            name="ingest_episode",
            response_time=duration * 1000,  # ms
            response_length=len(result.nodes) + len(result.edges),
            exception=None if result.success else Exception("Workflow failed")
        )

# Run with: locust -f test_baseline_load.py --users 2 --spawn-rate 1 --run-time 1h
```

**Metrics to Collect**:
- **Throughput**: Episodes processed per hour
- **Latency**: p50, p95, p99, p99.9 durations
- **Success rate**: % of workflows completed successfully
- **Resource usage**: CPU, memory, GPU utilization over time
- **External service health**: LLM quota usage, FalkorDB memory, embedding service load

**Baseline Targets** (Current System):
- Throughput: 36 episodes/hour with 2 workers
- Latency p50: 226 seconds (3.76 minutes)
- Latency p95: 300 seconds (5 minutes)
- Success rate: 98.8% (1.2% DLQ rate)

**Temporal Goals**:
- Throughput: ≥36 episodes/hour (maintain current)
- Latency p50: ≤240 seconds (within 10% of baseline)
- Success rate: ≥98.8% (match or improve)
- Resource usage: Similar CPU/memory footprint

#### 3.2 Stress Test (10× Load)

**Purpose**: Find breaking point, validate graceful degradation.

```bash
# Run 10× baseline load (360 episodes/hour = 20 workers)
locust -f test_baseline_load.py --users 20 --spawn-rate 5 --run-time 30m
```

**Expected Behavior**:
1. **LLM rate limiting kicks in** → Workflows wait/retry automatically
2. **FalkorDB memory pressure** → Graceful slowdown (not crash)
3. **Embedding service queue** → Activities timeout, retry with backoff
4. **Worker saturation** → Task queue backlog grows (Temporal handles)

**Success Criteria**:
- ✅ No crashes or data loss
- ✅ Graceful degradation (latency increases, throughput plateaus)
- ✅ Automatic recovery when load decreases
- ✅ Clear metrics showing bottleneck (LLM quota, GPU, or FalkorDB)

#### 3.3 Sustained Load Test (24 Hours)

**Purpose**: Validate stability over long duration, detect memory leaks.

```bash
# Run at 2× baseline load for 24 hours
locust -f test_baseline_load.py --users 4 --spawn-rate 1 --run-time 24h
```

**Metrics to Watch**:
- Memory usage trends (should be flat, not increasing)
- FalkorDB memory (should stabilize, not grow unbounded)
- Error rates over time (should be stable)
- Temporal server disk usage (event history storage)

---

## 4. Failure Mode Tests (Chaos Engineering)

### Objective
Validate resilience to infrastructure failures.

### Failure Scenarios

#### 4.1 Service Restart Tests

**File**: `tests/chaos/test_service_restarts.py`

```python
@pytest.mark.chaos
@pytest.mark.asyncio
async def test_falkordb_restart_mid_workflow():
    """Test workflow recovery when FalkorDB restarts during processing"""
    client = await Client.connect("localhost:7233")
    
    # Start workflow
    handle = await client.start_workflow(
        IngestEpisodeWorkflow.run,
        args=[...],
        id="test-falkordb-restart",
        task_queue="chaos-queue"
    )
    
    # Wait for entity extraction to complete
    await asyncio.sleep(10)
    
    # Restart FalkorDB (simulates crash or maintenance)
    subprocess.run(["docker", "restart", "graphiti-falkordb-1"])
    
    # Wait for FalkorDB to reload (~2 minutes with RDB)
    await asyncio.sleep(120)
    
    # Workflow should retry save_to_graph_activity and succeed
    result = await handle.result()
    assert result.success == True

@pytest.mark.chaos
@pytest.mark.asyncio
async def test_llm_service_downtime():
    """Test workflow retry when LLM service is temporarily down"""
    client = await Client.connect("localhost:7233")
    
    # Start workflow
    handle = await client.start_workflow(
        IngestEpisodeWorkflow.run,
        args=[...],
        id="test-llm-downtime",
        task_queue="chaos-queue"
    )
    
    # Wait briefly, then simulate LLM service down
    await asyncio.sleep(5)
    # Mock LLM to return 503 for 60 seconds
    with patch('llm_client.generate') as mock:
        mock.side_effect = Exception("503 Service Unavailable")
        await asyncio.sleep(60)
    
    # LLM recovers, workflow should retry and succeed
    result = await handle.result()
    assert result.success == True
    assert result.retry_count > 0

@pytest.mark.chaos
@pytest.mark.asyncio
async def test_worker_crash_mid_activity():
    """Test workflow resume after worker crashes during activity"""
    client = await Client.connect("localhost:7233")
    
    # Start workflow
    handle = await client.start_workflow(
        IngestEpisodeWorkflow.run,
        args=[...],
        id="test-worker-crash",
        task_queue="chaos-queue"
    )
    
    # Wait for activity to start
    await asyncio.sleep(5)
    
    # Kill worker process (simulates crash)
    subprocess.run(["pkill", "-9", "-f", "temporal-worker"])
    
    # Start new worker
    new_worker = Worker(client, task_queue="chaos-queue", ...)
    async with new_worker:
        # Workflow should resume from last checkpoint
        result = await handle.result()
        assert result.success == True
```

**Scenarios to Test**:
- ✅ FalkorDB restart (data persists, workflow retries)
- ✅ LLM service downtime (automatic retry with backoff)
- ✅ Embedding service crash (retry, no fallback)
- ✅ Worker crash (workflow resumes from checkpoint)
- ✅ Temporal server restart (workflows resume after recovery)
- ✅ Network partition (activities timeout, retry)

#### 4.2 Resource Exhaustion Tests

```python
@pytest.mark.chaos
@pytest.mark.asyncio
async def test_falkordb_oom_recovery():
    """Test handling FalkorDB OOM during save"""
    # Fill FalkorDB to 95% capacity
    fill_falkordb_to_threshold(threshold=0.95)
    
    # Submit workflow
    result = await client.execute_workflow(
        IngestEpisodeWorkflow.run,
        args=[...],
        id="test-oom-recovery"
    )
    
    # Should fail gracefully, go to DLQ (not crash)
    assert result.success == False
    assert "OOM" in result.error_message

@pytest.mark.chaos
@pytest.mark.asyncio
async def test_llm_quota_exhaustion():
    """Test adaptive behavior when LLM quota is exhausted"""
    # Exhaust LLM quota (100% usage)
    exhaust_llm_quota()
    
    # Submit workflow
    handle = await client.start_workflow(
        IngestEpisodeWorkflow.run,
        args=[...],
        id="test-quota-exhaustion"
    )
    
    # Should retry with exponential backoff
    # Eventually succeed when quota resets (next hour)
    result = await asyncio.wait_for(handle.result(), timeout=3600)
    assert result.success == True
    assert result.retry_count > 10  # Many retries due to quota
```

---

## 5. Replay Tests (Idempotency Validation)

### Objective
Validate that replaying episodes produces identical results (idempotent).

### Replay Test Structure

**File**: `tests/replay/test_idempotency.py`

```python
@pytest.mark.replay
@pytest.mark.asyncio
async def test_episode_replay_idempotency():
    """
    Process same episode twice, verify results are identical.
    Tests UUID-based deduplication and idempotent graph writes.
    """
    episode_data = {
        "uuid": "replay-test-001",
        "content": "Alice works at Google",
        "type": "message"
    }
    
    # First ingestion
    result1 = await client.execute_workflow(
        IngestEpisodeWorkflow.run,
        args=[episode_data],
        id="replay-001-first",
        task_queue="test-queue"
    )
    
    # Second ingestion (replay)
    result2 = await client.execute_workflow(
        IngestEpisodeWorkflow.run,
        args=[episode_data],
        id="replay-001-second",
        task_queue="test-queue"
    )
    
    # Results should be identical
    assert result1.nodes_created == result2.nodes_created
    assert result1.edges_created == result2.edges_created
    
    # Verify no duplicate data in FalkorDB
    driver = FalkorDBDriver(...)
    nodes = await driver.get_nodes_by_episode("replay-test-001")
    edges = await driver.get_edges_by_episode("replay-test-001")
    
    # Should only have ONE copy of each node/edge
    assert len(nodes) == result1.nodes_created
    assert len(edges) == result1.edges_created

@pytest.mark.replay
@pytest.mark.asyncio
async def test_production_episode_replay():
    """
    Replay random sample of 100 production episodes.
    Verify results match original ingestion.
    """
    # Fetch 100 random episodes from production
    production_episodes = fetch_random_episodes(count=100)
    
    for episode in production_episodes:
        # Get original results from FalkorDB
        original_nodes = await driver.get_nodes_by_episode(episode.uuid)
        original_edges = await driver.get_edges_by_episode(episode.uuid)
        
        # Replay through Temporal (shadow mode, no writes)
        replay_result = await client.execute_workflow(
            IngestEpisodeWorkflow.run,
            args=[episode],
            id=f"replay-{episode.uuid}",
            task_queue="replay-queue"
        )
        
        # Compare (allow minor LLM non-determinism)
        assert abs(len(replay_result.nodes) - len(original_nodes)) <= 1
        assert abs(len(replay_result.edges) - len(original_edges)) <= 2
```

---

## 6. Metrics Collection & Comparison Framework

### 6.1 Metrics to Collect

#### Current System Metrics (Baseline)
```python
# File: scripts/collect_baseline_metrics.py

import time
import psutil
import redis
from queue_client import QueueClient

class BaselineMetricsCollector:
    def collect_episode_metrics(self):
        """Collect per-episode metrics"""
        return {
            "timestamp": time.time(),
            "queue_depth": self.queue.depth(),
            "workers_active": self.count_active_workers(),
            "episodes_total": self.get_episode_count(),
            "entities_total": self.get_entity_count(),
            "edges_total": self.get_edge_count(),
            "falkordb_memory_mb": self.get_falkordb_memory(),
            "llm_quota_used_pct": self.get_llm_quota_usage(),
        }
    
    def collect_episode_trace(self, episode_uuid):
        """Collect detailed trace for single episode"""
        start_time = time.time()
        
        # Hook into worker._process_episode to collect stage timings
        trace = {
            "episode_uuid": episode_uuid,
            "start_time": start_time,
            "stages": {}
        }
        
        # Record each stage duration
        for stage in ["entity_extraction", "node_dedup", "edge_extraction", "edge_resolution", "graph_save"]:
            stage_start = time.time()
            # ... stage executes ...
            stage_end = time.time()
            trace["stages"][stage] = {
                "duration_sec": stage_end - stage_start,
                "llm_calls": count_llm_calls_in_stage(stage),
                "errors": count_errors_in_stage(stage),
                "retries": count_retries_in_stage(stage)
            }
        
        trace["total_duration_sec"] = time.time() - start_time
        trace["success"] = True  # or False if DLQ
        
        return trace

# Run: python scripts/collect_baseline_metrics.py --duration 168h > baseline_metrics.jsonl
```

#### Temporal System Metrics

```python
# File: scripts/collect_temporal_metrics.py

from temporalio.client import Client

class TemporalMetricsCollector:
    async def collect_workflow_metrics(self):
        """Collect Temporal workflow metrics"""
        client = await Client.connect("localhost:7233")
        
        # Query workflow execution history
        workflows = await client.list_workflows(
            query="WorkflowType='IngestEpisodeWorkflow' AND StartTime > '2026-01-12T00:00:00Z'"
        )
        
        metrics = {
            "timestamp": time.time(),
            "workflows_running": 0,
            "workflows_completed": 0,
            "workflows_failed": 0,
            "workflow_durations": [],
            "activity_retry_counts": {},
            "task_queue_backlog": await self.get_task_queue_backlog()
        }
        
        for workflow in workflows:
            status = await workflow.describe()
            
            if status.status == "RUNNING":
                metrics["workflows_running"] += 1
            elif status.status == "COMPLETED":
                metrics["workflows_completed"] += 1
                metrics["workflow_durations"].append(status.close_time - status.start_time)
            elif status.status == "FAILED":
                metrics["workflows_failed"] += 1
            
            # Collect activity retry counts
            for activity in status.activity_task_started_events:
                activity_name = activity.activity_type.name
                retry_count = activity.attempt
                if activity_name not in metrics["activity_retry_counts"]:
                    metrics["activity_retry_counts"][activity_name] = []
                metrics["activity_retry_counts"][activity_name].append(retry_count)
        
        # Calculate percentiles
        if metrics["workflow_durations"]:
            sorted_durations = sorted(metrics["workflow_durations"])
            metrics["workflow_duration_p50"] = percentile(sorted_durations, 50)
            metrics["workflow_duration_p95"] = percentile(sorted_durations, 95)
            metrics["workflow_duration_p99"] = percentile(sorted_durations, 99)
        
        return metrics

# Run: python scripts/collect_temporal_metrics.py --duration 168h > temporal_metrics.jsonl
```

### 6.2 Comparison Script

**File**: `scripts/compare_systems.py`

```python
import json
import pandas as pd
import matplotlib.pyplot as plt

def compare_metrics(baseline_file, temporal_file):
    """Compare baseline vs. Temporal metrics"""
    
    # Load metrics
    baseline = pd.read_json(baseline_file, lines=True)
    temporal = pd.read_json(temporal_file, lines=True)
    
    # Calculate comparison
    comparison = {
        "throughput": {
            "baseline": calculate_throughput(baseline),
            "temporal": calculate_throughput(temporal),
            "delta_pct": percent_change(baseline_throughput, temporal_throughput)
        },
        "latency_p50": {
            "baseline": baseline["workflow_duration_p50"].mean(),
            "temporal": temporal["workflow_duration_p50"].mean(),
            "delta_pct": percent_change(baseline_p50, temporal_p50)
        },
        "latency_p95": {
            "baseline": baseline["workflow_duration_p95"].mean(),
            "temporal": temporal["workflow_duration_p95"].mean(),
            "delta_pct": percent_change(baseline_p95, temporal_p95)
        },
        "success_rate": {
            "baseline": calculate_success_rate(baseline),
            "temporal": calculate_success_rate(temporal),
            "delta_pct": percent_change(baseline_success, temporal_success)
        },
        "retry_rate": {
            "baseline": calculate_retry_rate(baseline),
            "temporal": calculate_retry_rate(temporal),
            "delta_pct": percent_change(baseline_retry, temporal_retry)
        }
    }
    
    # Print comparison table
    print("\n=== SYSTEM COMPARISON ===\n")
    print(f"{'Metric':<20} {'Baseline':<15} {'Temporal':<15} {'Delta':<10}")
    print("-" * 60)
    for metric, values in comparison.items():
        print(f"{metric:<20} {values['baseline']:<15.2f} {values['temporal']:<15.2f} {values['delta_pct']:>+9.1f}%")
    
    # Generate charts
    plot_comparison(baseline, temporal, comparison)
    
    # Pass/Fail decision
    decision = make_go_nogo_decision(comparison)
    print(f"\n=== GO/NO-GO DECISION ===\n")
    print(decision)
    
    return comparison

def make_go_nogo_decision(comparison):
    """
    Data-driven go/no-go decision based on comparison.
    
    PASS criteria:
    - Throughput >= 100% of baseline (no regression)
    - Latency p50 <= 110% of baseline (within 10%)
    - Success rate >= 98.8% (matches baseline)
    - Error rate <= baseline
    
    FAIL criteria:
    - Any metric worse than threshold
    """
    failures = []
    
    if comparison["throughput"]["delta_pct"] < 0:
        failures.append(f"Throughput regression: {comparison['throughput']['delta_pct']:.1f}%")
    
    if comparison["latency_p50"]["delta_pct"] > 10:
        failures.append(f"Latency p50 regression: {comparison['latency_p50']['delta_pct']:.1f}% (threshold: 10%)")
    
    if comparison["success_rate"]["temporal"] < 98.8:
        failures.append(f"Success rate too low: {comparison['success_rate']['temporal']:.1f}% (threshold: 98.8%)")
    
    if failures:
        return "❌ NO-GO\n\nFailures:\n" + "\n".join(f"  - {f}" for f in failures)
    else:
        return "✅ GO\n\nAll metrics within acceptable thresholds. Safe to proceed to next phase."

# Run: python scripts/compare_systems.py baseline_metrics.jsonl temporal_metrics.jsonl
```

---

## 7. Shadow Mode Testing (Phase 1)

### Objective
Run Temporal in shadow mode (read-only) alongside current system, validate functional equivalence.

### Shadow Mode Architecture

```
┌─────────────────┐
│  Episode Queue  │
│   (LevelDB)     │
└────────┬────────┘
         │
    ┌────┴────┐
    │ Fanout  │ (custom script or queue duplication)
    └────┬────┘
         │
    ┌────┴──────────────┐
    │                   │
    ▼                   ▼
┌────────────┐    ┌─────────────┐
│  Current   │    │  Temporal   │
│  Workers   │    │  Workers    │
│  (write)   │    │ (read-only) │
└────────────┘    └─────────────┘
    │                   │
    ▼                   ▼
┌────────────┐    ┌─────────────┐
│ FalkorDB   │    │  Metrics    │
│ (prod)     │    │  Collector  │
└────────────┘    └─────────────┘
```

### Implementation

**File**: `scripts/shadow_mode_runner.py`

```python
import asyncio
from queue_client import QueueClient
from temporalio.client import Client
from temporal.workflows.ingest_episode import IngestEpisodeWorkflow

class ShadowModeRunner:
    def __init__(self):
        self.queue = QueueClient()
        self.temporal_client = None
        self.metrics_collector = MetricsCollector()
    
    async def run(self):
        """Run shadow mode: duplicate episodes to Temporal"""
        self.temporal_client = await Client.connect("localhost:7233")
        
        while True:
            # Peek at queue (don't consume)
            episode = await self.queue.peek()
            
            if episode:
                # Current system will process normally (via worker)
                # Shadow: Also send to Temporal (non-blocking)
                asyncio.create_task(self.shadow_process(episode))
            
            await asyncio.sleep(1)
    
    async def shadow_process(self, episode):
        """Process episode through Temporal in shadow mode"""
        try:
            start_time = time.time()
            
            # Execute workflow (read-only, no FalkorDB writes)
            result = await self.temporal_client.execute_workflow(
                IngestEpisodeWorkflow.run,
                args=[episode],
                id=f"shadow-{episode['uuid']}",
                task_queue="shadow-queue",
                execution_timeout=timedelta(minutes=10)
            )
            
            duration = time.time() - start_time
            
            # Compare with current system results (fetch from FalkorDB)
            current_result = await self.fetch_current_system_result(episode['uuid'])
            
            # Log comparison
            self.metrics_collector.log_shadow_comparison(
                episode_uuid=episode['uuid'],
                current_nodes=len(current_result.nodes),
                temporal_nodes=len(result.nodes),
                current_edges=len(current_result.edges),
                temporal_edges=len(result.edges),
                current_duration=current_result.duration,
                temporal_duration=duration,
                match_score=calculate_match_score(current_result, result)
            )
            
        except Exception as e:
            # Shadow failures don't affect production
            self.metrics_collector.log_shadow_error(episode['uuid'], str(e))

# Run: python scripts/shadow_mode_runner.py --duration 7d
```

**Success Criteria** (Shadow Mode):
- ✅ 95%+ match score (nodes/edges functionally equivalent)
- ✅ Latency within 20% of current system (initial tolerance)
- ✅ Error rate ≤ current system
- ✅ Zero impact on production (shadow failures don't affect current system)

---

## 8. Canary Deployment Testing (Phase 2)

### Objective
Route 1% of real traffic to Temporal, compare metrics, rollback if needed.

### Canary Architecture

```
┌─────────────────┐
│  Episode Queue  │
└────────┬────────┘
         │
    ┌────┴────┐
    │ Router  │  (1% → Temporal, 99% → Current)
    └────┬────┘
         │
    ┌────┴──────────────┐
    │                   │
    ▼                   ▼
┌────────────┐    ┌─────────────┐
│  Current   │    │  Temporal   │
│  Workers   │    │  Workers    │
│   (99%)    │    │    (1%)     │
└────────────┘    └─────────────┘
    │                   │
    └────────┬──────────┘
             ▼
      ┌─────────────┐
      │  FalkorDB   │
      │   (prod)    │
      └─────────────┘
```

### Implementation

**File**: `scripts/canary_router.py`

```python
import random
from queue_client import QueueClient
from temporalio.client import Client

class CanaryRouter:
    def __init__(self, canary_percentage=1.0):
        self.canary_percentage = canary_percentage
        self.queue = QueueClient()
        self.temporal_client = None
        self.metrics = CanaryMetrics()
    
    async def run(self):
        """Route episodes: X% to Temporal, (100-X)% to current workers"""
        self.temporal_client = await Client.connect("localhost:7233")
        
        while True:
            # Fetch episode from queue
            episode = await self.queue.get()
            
            if episode:
                # Decide routing
                if random.random() * 100 < self.canary_percentage:
                    # Route to Temporal
                    await self.route_to_temporal(episode)
                else:
                    # Route to current workers (put back in queue)
                    await self.queue.put(episode)
            
            await asyncio.sleep(0.1)
    
    async def route_to_temporal(self, episode):
        """Send episode to Temporal workflow"""
        try:
            result = await self.temporal_client.execute_workflow(
                IngestEpisodeWorkflow.run,
                args=[episode],
                id=f"canary-{episode['uuid']}",
                task_queue="production-queue",
                execution_timeout=timedelta(minutes=10)
            )
            
            # Log success
            self.metrics.log_success(
                system="temporal",
                episode_uuid=episode['uuid'],
                duration=result.duration,
                nodes_created=result.nodes_created,
                edges_created=result.edges_created
            )
            
        except Exception as e:
            # Log failure
            self.metrics.log_failure(
                system="temporal",
                episode_uuid=episode['uuid'],
                error=str(e)
            )
            
            # Rollback: put episode back in queue for current workers
            await self.queue.put(episode)

# Run: python scripts/canary_router.py --percentage 1.0 --duration 7d
```

### Automated Rollback

**File**: `scripts/canary_monitor.py`

```python
class CanaryMonitor:
    def __init__(self, error_rate_threshold=3.0):
        self.error_rate_threshold = error_rate_threshold
        self.metrics = CanaryMetrics()
    
    async def monitor(self):
        """Monitor canary metrics, auto-rollback if error rate exceeds threshold"""
        while True:
            await asyncio.sleep(60)  # Check every minute
            
            # Calculate error rates
            current_error_rate = self.metrics.get_error_rate(system="current")
            temporal_error_rate = self.metrics.get_error_rate(system="temporal")
            
            print(f"Current system error rate: {current_error_rate:.2f}%")
            print(f"Temporal system error rate: {temporal_error_rate:.2f}%")
            
            # Rollback condition: Temporal error rate >3% above baseline
            if temporal_error_rate > current_error_rate + self.error_rate_threshold:
                print("❌ AUTOMATIC ROLLBACK TRIGGERED")
                print(f"Temporal error rate ({temporal_error_rate:.2f}%) exceeds threshold")
                
                # Stop routing to Temporal
                self.stop_canary_routing()
                
                # Alert team
                self.send_alert(
                    title="Canary Rollback Triggered",
                    message=f"Temporal error rate {temporal_error_rate:.2f}% > {self.error_rate_threshold:.2f}% threshold"
                )
                
                break

# Run: python scripts/canary_monitor.py --threshold 3.0
```

**Canary Success Criteria**:
- ✅ Temporal error rate ≤ baseline + 3%
- ✅ Temporal latency p95 ≤ baseline + 20%
- ✅ Zero data loss (all episodes processed)
- ✅ No manual intervention required

---

## Summary: Testing Roadmap

### Phase 0: Development Testing (Weeks 1-2)
- ✅ Unit tests (80% coverage target)
- ✅ Integration tests (happy path + retries)
- ✅ Local failure injection tests

### Phase 1: Shadow Mode (Weeks 3-4)
- ✅ Run Temporal in read-only mode
- ✅ Collect 7 days of metrics
- ✅ Compare: throughput, latency, error rate
- ✅ Validate functional equivalence (95%+ match)

### Phase 2: Canary Deployment (Weeks 5-6)
- ✅ Route 1% traffic to Temporal
- ✅ Monitor for 7 days
- ✅ Auto-rollback if error rate >3%
- ✅ Manual go/no-go decision based on metrics

### Phase 3: Load Testing (Weeks 7-8)
- ✅ Baseline load (36 episodes/hour)
- ✅ Stress test (10× load)
- ✅ Sustained test (24 hours)
- ✅ Chaos tests (service failures)

### Phase 4: Gradual Rollout (Weeks 9-12)
- ✅ 10% → 25% → 50% → 100% traffic
- ✅ Continuous monitoring at each step
- ✅ Rollback plan ready at each step

---

## Test Automation & CI/CD

### GitHub Actions Workflow

**File**: `.github/workflows/temporal-tests.yml`

```yaml
name: Temporal Migration Tests

on:
  push:
    branches: [main, temporal-migration]
  pull_request:
    branches: [main]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio pytest-cov
      - name: Run unit tests
        run: |
          pytest tests/temporal/activities/ -v --cov=temporal/activities --cov-report=term-missing
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  integration-tests:
    runs-on: ubuntu-latest
    services:
      temporal:
        image: temporalio/auto-setup:latest
        ports:
          - 7233:7233
      falkordb:
        image: falkordb/falkordb:latest
        ports:
          - 6379:6379
    steps:
      - uses: actions/checkout@v3
      - name: Run integration tests
        run: |
          pytest tests/integration/ -v --temporal-host=localhost:7233

  load-tests:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      - name: Run load tests
        run: |
          locust -f tests/load/test_baseline_load.py --headless --users 2 --spawn-rate 1 --run-time 10m
      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: load-test-results
          path: locust_report.html
```

---

## Metrics Dashboards

### Grafana Dashboard (Comparison View)

**File**: `grafana/temporal-comparison-dashboard.json`

```json
{
  "dashboard": {
    "title": "Temporal Migration: System Comparison",
    "panels": [
      {
        "title": "Throughput (Episodes/Hour)",
        "targets": [
          {"expr": "rate(episodes_processed_total{system='current'}[1h])", "legendFormat": "Current System"},
          {"expr": "rate(episodes_processed_total{system='temporal'}[1h])", "legendFormat": "Temporal"}
        ]
      },
      {
        "title": "Latency (p50, p95, p99)",
        "targets": [
          {"expr": "histogram_quantile(0.50, episode_duration_seconds{system='current'})", "legendFormat": "Current p50"},
          {"expr": "histogram_quantile(0.50, episode_duration_seconds{system='temporal'})", "legendFormat": "Temporal p50"},
          {"expr": "histogram_quantile(0.95, episode_duration_seconds{system='current'})", "legendFormat": "Current p95"},
          {"expr": "histogram_quantile(0.95, episode_duration_seconds{system='temporal'})", "legendFormat": "Temporal p95"}
        ]
      },
      {
        "title": "Error Rate (%)",
        "targets": [
          {"expr": "rate(episodes_failed_total{system='current'}[1h]) / rate(episodes_processed_total{system='current'}[1h]) * 100", "legendFormat": "Current System"},
          {"expr": "rate(episodes_failed_total{system='temporal'}[1h]) / rate(episodes_processed_total{system='temporal'}[1h]) * 100", "legendFormat": "Temporal"}
        ]
      },
      {
        "title": "Activity Retry Distribution (Temporal)",
        "targets": [
          {"expr": "histogram_quantile(0.50, activity_retry_count)", "legendFormat": "p50 Retries"},
          {"expr": "histogram_quantile(0.95, activity_retry_count)", "legendFormat": "p95 Retries"},
          {"expr": "histogram_quantile(0.99, activity_retry_count)", "legendFormat": "p99 Retries"}
        ]
      }
    ]
  }
}
```

---

## Documentation Deliverables

### Test Reports

After each test phase, generate reports:

1. **Unit Test Report**: Coverage %, pass/fail by activity
2. **Integration Test Report**: End-to-end success rate, failure modes
3. **Shadow Mode Report**: 7-day comparison (match score, latency delta, error rate)
4. **Canary Report**: 7-day comparison (throughput, latency, errors, rollback events)
5. **Load Test Report**: Stress test results, breaking point, resource usage
6. **Final Comparison Report**: Side-by-side metrics, go/no-go recommendation

**Example Report Template**: `reports/shadow-mode-week-1.md`

```markdown
# Shadow Mode Test Report - Week 1

**Test Period**: 2026-01-13 to 2026-01-20
**Episodes Processed**: 6,048 (36/hour baseline × 168 hours)
**Systems Compared**: Current (LevelDB queue) vs. Temporal (shadow mode, read-only)

## Executive Summary
✅ Shadow mode validation PASSED
- Match score: 96.2% (target: 95%+)
- Latency delta: +8.3% (target: <20%)
- Error rate: 1.1% vs. 1.2% baseline (target: ≤baseline)

**Recommendation**: Proceed to Canary Deployment (Phase 2)

## Detailed Metrics

### Throughput
- Current system: 36.1 episodes/hour (average)
- Temporal system: 36.0 episodes/hour (shadow, read-only)
- Delta: -0.3% (within acceptable range)

### Latency
|Metric|Current|Temporal|Delta|
|------|-------|--------|-----|
|p50|226s|239s|+5.8%|
|p95|298s|331s|+11.1%|
|p99|412s|459s|+11.4%|

### Functional Equivalence
- Episodes with 100% match: 5,821 (96.2%)
- Episodes with minor differences (±1 node/edge): 201 (3.3%)
- Episodes with significant differences: 26 (0.4%)

### Error Analysis
- Current system DLQ: 73 episodes (1.2%)
- Temporal system failures: 68 episodes (1.1%)
- Common errors: LLM rate limits (42%), FalkorDB timeout (31%), embedding failure (27%)

## Notable Findings
1. **Temporal latency slightly higher** (+8.3% p50): Due to Temporal orchestration overhead. Expected to decrease with optimizations.
2. **Functional equivalence high** (96.2%): Minor differences due to LLM non-determinism.
3. **Error rate slightly lower** (1.1% vs. 1.2%): Temporal retry policies more robust.

## Recommendations
1. ✅ Proceed to Canary Deployment (1% traffic)
2. Optimize Temporal activity timeouts (reduce overhead)
3. Monitor LLM rate limiting closely during canary phase
```

---

## Conclusion

This comprehensive testing strategy provides:

1. **Multi-layer validation**: Unit → Integration → Shadow → Canary → Full rollout
2. **Data-driven decisions**: Each phase has explicit pass/fail criteria
3. **Risk mitigation**: Shadow mode + canary + automated rollback minimize production impact
4. **Continuous monitoring**: Real-time metrics comparison at every phase
5. **Automated testing**: CI/CD integration for regression prevention

**Next Steps**:
1. Implement unit tests for all activities (Week 1-2)
2. Set up integration test environment (Week 2)
3. Deploy shadow mode infrastructure (Week 3)
4. Collect 7 days of shadow mode data (Week 3-4)
5. Decision point: Proceed to canary if shadow mode passes

**Success Criteria Summary**:
- ✅ Unit tests: 80% coverage, all passing
- ✅ Integration tests: 100% pass rate
- ✅ Shadow mode: 95%+ match score, latency <+20%, error rate ≤baseline
- ✅ Canary: Error rate <+3%, latency <+20%, zero data loss
- ✅ Load tests: No crashes at 10× load, graceful degradation
- ✅ Final rollout: Maintain 36+ episodes/hour throughput, <1.2% error rate
