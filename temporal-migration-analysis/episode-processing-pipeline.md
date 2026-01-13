# Episode Processing Pipeline

## Overview
The episode ingestion pipeline processes conversational messages and structured data into a knowledge graph. It's a multi-stage pipeline with entity extraction, deduplication, edge creation, and graph persistence.

## Pipeline Entry Points

### 1. Queue-Based Ingestion (Production)
```
HTTP/Webhook → Queued Service (LevelDB) → Worker Pool → Graphiti.add_episode()
```

### 2. Direct API Ingestion (Development/Testing)
```
FastAPI Endpoint → Graphiti.add_episode_resilient() → Graphiti.add_episode()
```

## Core Method: `Graphiti.add_episode()`

**Location**: `/opt/stacks/graphiti/graphiti_core/graphiti.py:424-640`

**Signature**:
```python
async def add_episode(
    name: str,
    episode_body: str,
    source_description: str,
    reference_time: datetime,
    source: EpisodeType = EpisodeType.message,
    group_id: str | None = None,
    uuid: str | None = None,
    update_communities: bool = False,
    entity_types: dict[str, BaseModel] | None = None,
    excluded_entity_types: list[str] | None = None,
    previous_episode_uuids: list[str] | None = None,
    edge_types: dict[str, BaseModel] | None = None,
    edge_type_map: dict[tuple[str, str], list[str]] | None = None,
) -> AddEpisodeResults
```

**Returns**:
```python
class AddEpisodeResults:
    episode: EpisodicNode        # The created episode node
    nodes: list[EntityNode]      # Extracted and deduplicated entities
    edges: list[EntityEdge]      # Created relationships
```

## Pipeline Stages

### Stage 0: Pre-Processing (Lines 495-535)
**Purpose**: Setup and validation
**Duration**: ~50ms

```python
# 1. Validation
validate_entity_types(entity_types)
validate_excluded_entity_types(excluded_entity_types, entity_types)
validate_group_id(group_id)

# 2. Retrieve context (previous episodes for context)
previous_episodes = await retrieve_episodes(
    reference_time,
    last_n=RELEVANT_SCHEMA_LIMIT,  # Default: 10 episodes
    group_ids=[group_id],
    source=source
)

# 3. Create or retrieve episode node
episode = EpisodicNode(
    name=name,
    group_id=group_id,
    content=episode_body,
    source_description=source_description,
    created_at=now,
    valid_at=ensure_utc(reference_time)
)
```

**Key Operations**:
- Fetch last 10 episodes for context (graph query)
- Create episode node in memory (not yet persisted)
- Set up group_id namespace

**Dependencies**: FalkorDB (for previous episodes)

---

### Stage 1: Entity Extraction (Line 546)
**Purpose**: Extract entities (nodes) from episode text
**Duration**: ~86 seconds (measured in production)

```python
extracted_nodes = await extract_nodes(
    self.clients,          # LLM client + embedder
    episode,               # Current episode
    previous_episodes,     # Context (last 10)
    entity_types,          # Optional custom entity schemas
    excluded_entity_types  # Types to skip
)
```

**Implementation**: 
- **File**: `/opt/stacks/graphiti/graphiti_core/utils/maintenance/node_operations.py`
- **Method**: `extract_nodes()` → calls LLM to identify entities

**LLM Call**: 
- **Model**: `gpt-4o-mini` (or configured model)
- **Prompt**: "Extract entities from this episode. Previous episodes: [context]. Identify: people, places, concepts, etc."
- **Output**: Structured JSON with entity names, summaries, types

**DSPy Alternative** (if `use_dspy=True`):
- Uses DSPy signatures for structured extraction
- More reliable schema adherence
- Same basic operation

**Returns**: `List[dict]` of raw entity data (not yet EntityNode objects)

---

### Stage 2: Parallel Operations (Lines 551-571)
**Purpose**: Node resolution + Edge extraction in parallel
**Duration**: ~111s (deduplication) + ~24s (edges) = ~111s total (parallel)

#### Stage 2A: Node Resolution & Deduplication (Lines 552-560)
```python
nodes, uuid_map, node_duplicates = await resolve_extracted_nodes(
    self.clients,
    extracted_nodes,        # Raw entities from Stage 1
    episode,
    previous_episodes,
    entity_types,
    existing_nodes_override=None,
    enable_cross_graph_deduplication=self.enable_cross_graph_deduplication
)
```

**Sub-Steps**:
1. **Vector Search**: Find similar entities in existing graph
   - Embedding similarity threshold: 0.85
   - Search scope: Current `group_id` (or cross-graph if enabled)
2. **LLM Deduplication**: Ask LLM "Are these the same entity?"
   - Compare each extracted entity with similar existing ones
   - Multiple LLM calls if many candidates
3. **UUID Mapping**: Build map of `extracted_uuid → canonical_uuid`
4. **Node Creation**: Create `EntityNode` objects for new entities

**Returns**:
- `nodes`: List of `EntityNode` objects (new + existing)
- `uuid_map`: Dict mapping extracted UUIDs to canonical UUIDs
- `node_duplicates`: List of duplicate nodes to merge

**LLM Calls**: N calls where N = number of entities × number of similar candidates
**Example**: 5 entities, 3 candidates each = 15 LLM calls

---

#### Stage 2B: Edge Extraction (Lines 561-569)
```python
extracted_edges = await extract_edges(
    self.clients,
    episode,
    extracted_nodes,      # Raw entities from Stage 1
    previous_episodes,
    edge_type_map,        # Which edge types allowed between entity types
    group_id,
    edge_types            # Optional custom edge schemas
)
```

**Purpose**: Extract relationships between entities

**LLM Call**:
- **Prompt**: "Given these entities, what relationships exist? Previous episodes: [context]"
- **Output**: List of triplets: (source_entity, relationship, target_entity, fact)

**Example**:
```json
{
  "source_uuid": "entity-123",
  "target_uuid": "entity-456",
  "name": "works_at",
  "fact": "Alice works at Acme Corp as a software engineer"
}
```

**Returns**: `List[dict]` of raw edge data

---

### Stage 3: Edge Resolution (Lines 573-588)
**Purpose**: Map edge pointers to canonical UUIDs + resolve edge validity
**Duration**: ~10-20s

#### Step 3A: Pointer Resolution (Line 573)
```python
edges = resolve_edge_pointers(extracted_edges, uuid_map)
```
- Replace extracted UUIDs with canonical UUIDs from deduplication
- Ensures edges point to correct nodes after merging

#### Step 3B: Edge Resolution & Attribute Extraction (Lines 575-588)
```python
(resolved_edges, invalidated_edges), hydrated_nodes = await semaphore_gather(
    resolve_extracted_edges(
        self.clients,
        edges,
        episode,
        nodes,
        edge_types,
        edge_type_map
    ),
    extract_attributes_from_nodes(
        self.clients,
        nodes,
        episode,
        previous_episodes,
        entity_types
    )
)
```

**Parallel Operations**:

**3B.1: Edge Resolution**
- **Purpose**: Deduplicate edges + invalidate contradicting edges
- **Vector Search**: Find similar existing edges
- **LLM Call**: "Are these edges describing the same fact?"
- **Invalidation Logic**: If new edge contradicts old edge, mark old as `invalid_at = now`

**3B.2: Attribute Extraction**
- **Purpose**: Extract structured attributes from entity descriptions
- **LLM Call**: "Given this entity and episode, what are its key attributes?"
- **Example**: `{"age": 25, "occupation": "engineer", "city": "SF"}`

---

### Stage 4: Edge Construction (Lines 590-600)
**Purpose**: Build all edge types for persistence
**Duration**: ~5ms (in-memory)

```python
# 4A: Build duplicate edges (for merged entities)
duplicate_of_edges, merge_operations, duplicate_nodes_to_save = (
    build_duplicate_of_edges(episode, now, node_duplicates)
)

# 4B: Combine all entity edges
entity_edges = resolved_edges + invalidated_edges + duplicate_of_edges

# 4C: Build episodic edges (MENTIONS relationships)
episodic_edges = build_episodic_edges(
    nodes,
    episode.uuid,
    now,
    episode_group_id=episode.group_id
)

# 4D: Store edge UUIDs on episode
episode.entity_edges = [edge.uuid for edge in entity_edges]
```

**Edge Types Created**:
1. **Entity Edges**: Relationships between entities (e.g., "Alice works at Acme")
2. **Invalidated Edges**: Old edges marked as `invalid_at = now`
3. **Duplicate Edges**: `DUPLICATE_OF` edges connecting merged entities
4. **Episodic Edges**: `MENTIONS` edges (episode → entities mentioned)

---

### Stage 5: Graph Persistence (Lines 602-615)
**Purpose**: Write everything to FalkorDB
**Duration**: ~20-50s (depends on batch size)

```python
# 5A: Save episode node
await episode.save(self.driver)

# 5B: Batch save nodes and edges
await add_nodes_and_edges_bulk(
    self.driver,
    nodes=nodes + duplicate_nodes_to_save,
    edges=entity_edges + episodic_edges,
    embedder=self.embedder
)
```

**Operations**:
1. **Save Episode**: Single Cypher query (FalkorDB)
2. **Save Nodes**: Batch MERGE queries (creates or updates)
3. **Generate Embeddings**: For new nodes (OpenAI API calls)
4. **Save Edges**: Batch CREATE queries
5. **Merge Duplicates**: Execute merge operations (transfer edges, delete old nodes)

**Parallelization**: Batch size = 50 (configurable)

---

### Stage 6: Community Updates (Lines 644-650) [Optional]
**Purpose**: Update community summaries if enabled
**Duration**: ~5-10s
**Default**: Disabled (`update_communities=False`)

```python
if update_communities:
    for node in nodes:
        await update_community(
            self.driver,
            node,
            self.llm_client,
            self.embedder
        )
```

**Operations**:
- Regenerate community summaries for affected nodes
- Update community embeddings
- LLM call per community

---

## Worker Integration

### Worker Class: `IngestionWorker`
**Location**: `/opt/stacks/graphiti/graphiti_core/ingestion/worker.py:215-912`

**Workflow**:
```python
# 1. Poll queue
tasks = await queue.poll(count=batch_size, visibility_timeout=1200)  # 20 min

# 2. Process each task
for message_id, task, poll_tag in tasks:
    try:
        # 2A: Rate limiting
        await rate_limiter.acquire(task.group_id)
        
        # 2B: Idempotency check (skip if already processed)
        if await _episode_already_ingested(episode_uuid, group_id):
            continue
        
        # 2C: Call Graphiti
        result = await graphiti.add_episode_resilient(
            group_id=group_id,
            name=payload['name'],
            episode_body=payload['content'],
            reference_time=timestamp,
            uuid=episode_uuid  # Ensures deduplication
        )
        
        # 2D: Post-processing (centrality updates)
        await centrality_client.update_nodes_centrality(
            [node.uuid for node in result.nodes]
        )
        
        # 2E: Background deduplication (every 10 episodes)
        if episode_count % 10 == 0:
            await run_background_deduplication(group_id)
        
        # 3. Acknowledge success
        await queue.delete(message_id, poll_tag)
        
    except Exception as e:
        # 4. Handle failure (retry or DLQ)
        await handle_failure(message_id, poll_tag, task, e)
```

### Worker Pool: `WorkerPool`
**Location**: `/opt/stacks/graphiti/graphiti_core/ingestion/worker.py:914-962`

**Architecture**:
- Creates N workers (default: 2, configurable via `WORKER_COUNT`)
- Each worker polls independently
- Shared queue (LevelDB) prevents duplicate processing
- No coordination needed (queue handles visibility)

**Scaling**:
```python
# Environment variable
WORKER_COUNT=4  # 4 parallel workers

# Each worker processes batch_size=1 (sequential within worker)
# Total parallelism: 4 concurrent episodes
```

---

## Error Handling & Retries

### Worker-Level Errors

#### 1. Transient Errors (Retryable)
```python
class TransientError(Exception):
    """Network issues, temporary failures"""
    pass

# Retry with exponential backoff
delay = min(300, 10 * (2 ** retry_count))
await queue.update(message_id, poll_tag, delay)
```

**Examples**: 
- FalkorDB connection timeout
- LLM API rate limit (429)
- Network errors

**Retry Logic**:
- Max retries: 3 (hardcoded in `IngestionTask.max_retries`)
- Backoff: 10s, 20s, 40s, 80s (capped at 300s)
- After 3 failures → Dead Letter Queue

---

#### 2. Permanent Errors (No Retry)
```python
class PermanentError(Exception):
    """Invalid data, logic errors"""
    pass

# Move to DLQ immediately
await _move_to_dlq(task, error)
await queue.delete(message_id, poll_tag)
```

**Examples**:
- Invalid UUID format
- Missing required fields
- Node/Edge not found (data consistency issue)

---

#### 3. Rate Limit Errors
```python
class RateLimitError(Exception):
    def __init__(self, group_id: str, retry_after: int = 60):
        self.group_id = group_id
        self.retry_after = retry_after

# Suspend group for retry_after seconds
rate_limiter.suspend_group(group_id, 60)
```

**Limits**:
- **Global**: 100 requests/second
- **Per-Group**: 60 requests/minute
- **Burst Multiplier**: 1.5x

**Behavior**:
- Tasks from rate-limited group are delayed
- Other groups continue processing
- Group unsuspended after timeout

---

### Resilient Ingestion Wrapper

**Method**: `Graphiti.add_episode_resilient()`
**Location**: `/opt/stacks/graphiti/graphiti_core/graphiti.py` (wrapper around `add_episode`)

**Features**:
1. **Checkpoint Recovery**: Resume from last successful stage
2. **State Caching**: Save intermediate results (extracted nodes, edges)
3. **Retry on Failure**: Retry from checkpoint, not from scratch

**Example Flow**:
```python
# 1st attempt: Fails at Stage 3 (edge resolution)
# Cache: extracted_nodes, deduplicated_nodes saved to disk

# 2nd attempt: Resume from Stage 3
# Load: extracted_nodes, deduplicated_nodes from cache
# Skip: Stages 1-2 (already done)
```

**Cache Location**: In-memory dict (cleared on success)

---

## Performance Characteristics

### Timing Breakdown (Measured in Production)
Based on recent monitoring (Jan 2026, 2 workers, ~78 episodes/hour):

| Stage | Duration | % of Total |
|-------|----------|------------|
| 0. Pre-Processing | ~50ms | <1% |
| 1. Entity Extraction | ~86s | 38% |
| 2A. Node Deduplication | ~111s | 49% |
| 2B. Edge Extraction | ~24s | 11% |
| 3. Edge Resolution | ~15s | 7% |
| 4. Edge Construction | ~5ms | <1% |
| 5. Graph Persistence | ~30s | 13% |
| 6. Community Updates | ~5s | 2% (if enabled) |
| **Total** | **~226s** | **100%** |

**Per Episode**: 3.76 minutes (226 seconds)
**Throughput**: ~16 episodes/hour/worker (2 workers = ~32 episodes/hour)

### Bottlenecks

1. **Node Deduplication (49% of time)**
   - Multiple LLM calls per entity
   - Vector search across large graph
   - **Mitigation**: Batch embeddings, cache results

2. **Entity Extraction (38% of time)**
   - Single LLM call, but complex prompt
   - **Mitigation**: Use faster model (e.g., `gpt-4o-mini` → `gpt-4o-turbo`)

3. **Graph Persistence (13% of time)**
   - Multiple Cypher queries
   - Embedding generation
   - **Mitigation**: Larger batch sizes, async writes

### LLM API Calls per Episode

| Operation | Count | Model |
|-----------|-------|-------|
| Entity Extraction | 1 | `gpt-4o-mini` |
| Node Deduplication | N × M | `gpt-4o-mini` |
| Edge Extraction | 1 | `gpt-4o-mini` |
| Edge Deduplication | K | `gpt-4o-mini` |
| Attribute Extraction | N | `gpt-4o-mini` |
| Community Updates | C | `gpt-4o-mini` |

Where:
- N = number of entities (avg: 3-5)
- M = candidates per entity (avg: 2-3)
- K = number of edges (avg: 2-4)
- C = number of communities (0 if disabled)

**Total**: 15-25 LLM calls per episode (average: ~20)

**Token Usage** (estimated):
- Input: 5K-10K tokens per episode (context + prompts)
- Output: 1K-2K tokens per episode
- **Total**: ~7K tokens × 20 calls = ~140K tokens/episode

**Cost** (OpenAI `gpt-4o-mini` @ $0.15/1M input, $0.60/1M output):
- Input: 7K × 20 × $0.15/1M = $0.021/episode
- Output: 1K × 20 × $0.60/1M = $0.012/episode
- **Total**: ~$0.033/episode = $33/1000 episodes

---

## External Dependencies

### 1. LLM Service (OpenAI, Ollama, Cerebras)
**Usage**:
- Entity extraction
- Node deduplication
- Edge extraction
- Attribute extraction

**Failure Mode**: Transient error → Retry
**Rate Limits**: 10K RPM (OpenAI Tier 2)

### 2. Embedding Service (OpenAI, Voyage)
**Usage**:
- Node embeddings (for vector search)
- Community embeddings

**Failure Mode**: Transient error → Retry
**Rate Limits**: 10K RPM (OpenAI)

### 3. FalkorDB (Graph Database)
**Usage**:
- Retrieve previous episodes
- Vector search for deduplication
- Save nodes/edges
- Query existing graph

**Failure Mode**: Transient error → Retry
**Connection Pool**: Managed by FalkorDriver

### 4. Centrality Service (Rust)
**Optional Dependency**: Updates node centrality scores post-ingestion
**URL**: `http://graphiti-centrality-rs:3003`
**Failure Mode**: Log warning, continue (non-blocking)

---

## Idempotency & Deduplication

### Episode-Level Idempotency
**Mechanism**: Episode UUID
```python
episode = EpisodicNode(uuid=uuid, ...)
```

**Behavior**:
- Same UUID → Retrieve existing episode (don't create new)
- Check for progress: If episode has `MENTIONS` edges or `entity_edges`, skip reprocessing
- Prevents duplicate work on queue retries

**Implementation**: `/opt/stacks/graphiti/graphiti_core/ingestion/worker.py:388-428`

### Entity Deduplication
**Mechanism**: Vector search + LLM
```python
# 1. Find similar entities by embedding
candidates = vector_search(entity.name, similarity_threshold=0.85)

# 2. Ask LLM: "Are these the same entity?"
is_duplicate = await llm_client.check_duplicate(entity, candidate)

# 3. Merge if duplicate
if is_duplicate:
    uuid_map[entity.uuid] = candidate.uuid
```

**Scope**: 
- **Default**: Within same `group_id`
- **Cross-Graph**: Across all `group_id` if `enable_cross_graph_deduplication=True`

### Edge Deduplication
**Mechanism**: Vector search + LLM
```python
# 1. Find similar edges by fact embedding
candidates = vector_search(edge.fact, similarity_threshold=0.85)

# 2. Ask LLM: "Are these edges describing the same fact?"
is_duplicate = await llm_client.check_duplicate_edge(edge, candidate)

# 3. Mark old as invalid if contradicting
if is_duplicate and contradicts:
    old_edge.invalid_at = now
```

---

## Observability Gaps (Current System)

### 1. No Distributed Tracing
- Can't trace episode from queue → worker → graph
- No correlation IDs across pipeline stages
- Hard to debug slow episodes

### 2. Limited Metrics
- Only basic counters (pushed, polled, completed, failed)
- No per-stage timing
- No LLM call metrics (retries, token usage)

### 3. No Workflow State
- Can't inspect in-flight episodes
- Can't pause/resume processing
- Can't replay failed episodes from checkpoints

### 4. Poor Error Visibility
- Errors logged, but not structured
- DLQ exists but no alerting
- No automatic retry dashboards

---

## Next Steps for Temporal Migration

### Map to Temporal Concepts

| Current Component | Temporal Equivalent |
|-------------------|---------------------|
| `queued` service | Temporal task queue |
| `IngestionWorker._process_episode()` | Temporal workflow |
| Stage 1: Entity Extraction | Activity: `extract_entities` |
| Stage 2A: Node Deduplication | Activity: `deduplicate_nodes` |
| Stage 2B: Edge Extraction | Activity: `extract_edges` |
| Stage 3: Edge Resolution | Activity: `resolve_edges` |
| Stage 5: Graph Persistence | Activity: `save_to_graph` |
| Episode UUID | Workflow ID |
| Retry logic | Temporal retry policy |
| DLQ | Failed workflow search |

### Benefits of Temporal

1. **Built-in Observability**
   - Workflow history (all stages visible)
   - Per-activity timing and errors
   - Web UI for inspection

2. **Automatic Retries**
   - Per-activity retry policies
   - Exponential backoff
   - Circuit breakers

3. **Workflow State**
   - Can pause/resume workflows
   - Can inspect in-flight state
   - Can replay from checkpoints

4. **Scalability**
   - Dynamic worker scaling
   - Activity-level parallelism
   - Better resource utilization

5. **Testability**
   - Unit test workflows and activities separately
   - Mock activities for integration tests
   - Replay production workflows in dev

---

## Files to Review Next

1. `/opt/stacks/graphiti/graphiti_core/utils/maintenance/node_operations.py` - Entity extraction/deduplication implementation
2. `/opt/stacks/graphiti/graphiti_core/utils/maintenance/edge_operations.py` - Edge extraction/resolution implementation
3. `/opt/stacks/graphiti/graphiti_core/utils/bulk_utils.py` - Batch save operations
4. `/opt/stacks/graphiti/graphiti_core/llm_client/` - LLM client implementations
5. `/opt/stacks/graphiti/graphiti_core/embedder/` - Embedding client implementations
