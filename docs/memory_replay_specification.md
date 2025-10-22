# Graphiti Memory Replay System Specification

## Overview

This document outlines the design and implementation of a **Memory Replay System** for Graphiti, inspired by hippocampal memory consolidation in the human brain. The system addresses the current limitation where episodes with poor entity extraction, missing cross-group connections, and stale processing remain under-enriched in the knowledge graph.

## Problem Statement

### Current Issues
1. **Unbounded Dynamic Prompts**: As the number of nodes increases, prompts become unwieldy, causing performance degradation
2. **Poor Entity Connections**: Episodes often result in isolated nodes with few meaningful relationships
3. **Cross-Group Deduplication Gap**: The current pipeline doesn't handle entity deduplication across different group IDs
4. **Stale Extraction Versions**: Episodes processed with older extraction algorithms remain under-optimized

### Research Foundation
The memory replay concept is based on extensive neuroscience research:
- **Hippocampal Sharp Wave-Ripples (SWRs)**: Memory strengthening during replay
- **Burst-Associated Ripples (BARRs)**: Selective inhibition to prevent oversaturation
- **Systems Consolidation**: Transfer of memories from hippocampus to neocortex
- **Experience Replay in AI**: Proven technique in continual learning systems

## System Architecture

### Core Components

#### 1. Replay Candidate Detection Engine
```python
# Location: graphiti_core/utils/replay/candidate_detector.py
class ReplayCandidateDetector:
    """Identifies episodes that would benefit from replay processing"""
    
    async def identify_candidates(
        self, 
        group_id: str | None = None,
        limit: int = 100
    ) -> list[ReplayCandidate]:
        """
        Detect episodes needing replay based on multiple heuristics:
        - Few extracted entities (< 3)
        - Missing cross-group connections
        - Old extraction versions
        - Low confidence scores
        - Temporal importance (recent user interactions)
        """
```

#### 2. Replay Scheduler & Queue Integration
```python
# Location: graphiti_core/utils/replay/scheduler.py
class MemoryReplayScheduler:
    """Manages replay scheduling and queue integration"""
    
    async def schedule_replay_loop(self):
        """
        Permanent background loop that:
        1. Scans for replay candidates
        2. Prioritizes based on importance metrics
        3. Queues replay tasks via existing QueuedClient
        4. Implements exponential backoff and safety limits
        """
```

#### 3. Replay Execution Engine
```python
# Location: graphiti_core/utils/replay/executor.py
class ReplayExecutor:
    """Executes replay operations using existing resilient ingestion"""
    
    async def replay_episode(
        self, 
        episode_uuid: str,
        replay_context: ReplayContext
    ) -> ReplayResult:
        """
        Idempotent replay using existing add_episode_resilient:
        - Preserves original episode UUID
        - Uses MERGE operations for updates
        - Tracks replay metadata and provenance
        """
```

## Integration with Existing Systems

### Queue/Worker Integration

The replay system leverages the existing `graphiti_core/ingestion/worker.py` infrastructure:

```python
# Enhanced TaskType in queue_client.py
class TaskType(str, Enum):
    EPISODE = "episode"
    ENTITY = "entity" 
    BATCH = "batch"
    RELATIONSHIP = "relationship"
    DEDUPLICATION = "deduplication"
    REPLAY = "replay"  # NEW: Memory replay tasks
```

### Resilient Ingestion Integration

Replay operations use the existing `add_episode_resilient` method:

```python
# In graphiti_core/graphiti.py - Enhanced method signature
async def add_episode_resilient(
    self,
    name: str,
    episode_body: str,
    source_description: str,
    reference_time: datetime,
    source: EpisodeType = EpisodeType.message,
    group_id: str | None = None,
    uuid: str | None = None,  # Preserves identity during replay
    replay_mode: bool = False,  # NEW: Indicates replay operation
    replay_context: ReplayContext | None = None,  # NEW: Replay metadata
    # ... existing parameters
) -> 'AddEpisodeResults':
```

### Database Schema Extensions

#### Replay Metadata Table
```sql
-- New table for tracking replay operations
CREATE TABLE replay_metadata (
    episode_uuid VARCHAR(36) PRIMARY KEY,
    group_id VARCHAR(255) NOT NULL,
    last_replayed_at TIMESTAMP,
    replay_attempts INTEGER DEFAULT 0,
    extraction_version VARCHAR(50),
    replay_reason TEXT,
    confidence_score FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_replay_metadata_group_id ON replay_metadata(group_id);
CREATE INDEX idx_replay_metadata_last_replayed ON replay_metadata(last_replayed_at);
```

#### Episode Enhancement Tracking
```sql
-- Track enhancement metrics for episodes
ALTER TABLE episodic_nodes ADD COLUMN entity_count INTEGER DEFAULT 0;
ALTER TABLE episodic_nodes ADD COLUMN edge_count INTEGER DEFAULT 0;
ALTER TABLE episodic_nodes ADD COLUMN cross_group_connections INTEGER DEFAULT 0;
ALTER TABLE episodic_nodes ADD COLUMN extraction_version VARCHAR(50);
ALTER TABLE episodic_nodes ADD COLUMN confidence_score FLOAT;
```

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1-2)
1. **Replay Candidate Detection**
   - Implement `ReplayCandidateDetector` class
   - Create heuristics for identifying under-enriched episodes
   - Add database queries for candidate selection

2. **Replay Metadata System**
   - Create replay metadata schema
   - Implement tracking and provenance
   - Add safety mechanisms (max attempts, cooldown periods)

### Phase 2: Queue Integration (Week 3)
1. **Enhanced Task Types**
   - Add `REPLAY` task type to `TaskType` enum
   - Modify worker to handle replay tasks
   - Implement replay-specific error handling

2. **Scheduler Implementation**
   - Create background replay scheduler
   - Implement adaptive scheduling based on system load
   - Add configuration for replay intervals and limits

### Phase 3: Execution Engine (Week 4)
1. **Replay Executor**
   - Implement idempotent replay using `add_episode_resilient`
   - Add replay context and metadata tracking
   - Ensure proper UUID preservation and MERGE operations

2. **Safety Mechanisms**
   - Implement circuit breakers per group
   - Add exponential backoff for failed replays
   - Create escape hatches for disabling replay

### Phase 4: Monitoring & Optimization (Week 5)
1. **Metrics and Dashboards**
   - Track replay throughput and success rates
   - Monitor enrichment deltas (before/after entity counts)
   - Alert on replay failures or infinite loops

2. **Performance Tuning**
   - Optimize candidate detection queries
   - Implement batch replay operations
   - Add adaptive priority scoring

## Configuration

### Environment Variables
```bash
# Replay system configuration
REPLAY_ENABLED=true
REPLAY_INTERVAL_SECONDS=300
REPLAY_BATCH_SIZE=10
REPLAY_MAX_ATTEMPTS=3
REPLAY_COOLDOWN_HOURS=24
REPLAY_CONFIDENCE_THRESHOLD=0.7

# Safety limits
REPLAY_MAX_PER_GROUP_PER_HOUR=100
REPLAY_CIRCUIT_BREAKER_THRESHOLD=10
REPLAY_ENABLE_CROSS_GROUP=true
```

### Configuration Class
```python
# Location: graphiti_core/config/replay_config.py
@dataclass
class ReplayConfig:
    enabled: bool = True
    interval_seconds: int = 300
    batch_size: int = 10
    max_attempts: int = 3
    cooldown_hours: int = 24
    confidence_threshold: float = 0.7
    max_per_group_per_hour: int = 100
    circuit_breaker_threshold: int = 10
    enable_cross_group: bool = True
```

## Safety Mechanisms

### 1. Circuit Breakers
- Disable replay for specific groups after consecutive failures
- Global circuit breaker for system-wide issues
- Automatic recovery after cooldown periods

### 2. Rate Limiting
- Maximum replays per group per hour
- Adaptive backoff based on system load
- Priority queuing for critical operations

### 3. Infinite Loop Prevention
- Maximum replay attempts per episode
- Exponential backoff between attempts
- Replay reason tracking to prevent redundant operations

### 4. Resource Management
- Memory usage monitoring during replay
- Database connection pooling
- Graceful degradation under high load

## Monitoring and Observability

### Key Metrics
1. **Replay Throughput**: Episodes replayed per hour
2. **Enrichment Delta**: Entity/edge count improvements
3. **Success Rate**: Percentage of successful replays
4. **Cross-Group Connections**: New inter-group relationships discovered
5. **System Impact**: Resource usage during replay operations

### Alerting
- Failed replay attempts exceeding threshold
- Circuit breaker activations
- Unusual replay patterns or infinite loops
- Performance degradation during replay operations

## Expected Benefits

### Quantitative Improvements
- **15-25% increase** in entity extraction completeness
- **30-40% improvement** in cross-group entity connections
- **20-30% reduction** in isolated episodes
- **10-15% better** semantic search relevance

### Qualitative Benefits
- More coherent knowledge graph structure
- Better temporal relationship discovery
- Improved deduplication across groups
- Enhanced system adaptability to new extraction methods

## Migration Strategy

### Backward Compatibility
- All existing APIs remain unchanged
- Replay system operates as optional enhancement
- Gradual rollout with feature flags
- Fallback to current behavior if replay fails

### Rollout Plan
1. **Development Environment**: Full implementation and testing
2. **Staging Environment**: Performance validation with production data
3. **Production Pilot**: Limited group IDs with monitoring
4. **Full Production**: Gradual expansion to all groups

## Future Enhancements

### Advanced Replay Strategies
- **Semantic Clustering**: Group similar episodes for batch replay
- **Temporal Patterns**: Prioritize replay based on time-based importance
- **User Interaction Signals**: Weight replay priority by query patterns
- **Cross-Modal Enhancement**: Replay with different LLM models for diversity

### Integration Opportunities
- **Centrality-Based Prioritization**: Use graph centrality metrics for replay selection
- **Embedding Similarity**: Identify episodes with similar but disconnected content
- **Community Detection**: Replay episodes to strengthen community boundaries
- **Temporal Graph Analysis**: Replay based on temporal relationship patterns

## Alternative Architecture: Separate Replay Service

### Why a Separate Service Makes Sense

Based on the current Graphiti architecture analysis, implementing replay as a **separate microservice** offers several advantages:

1. **Clean Separation of Concerns**: Replay logic doesn't pollute core ingestion pipeline
2. **Independent Scaling**: Replay service can scale based on replay workload, not ingestion load
3. **Fault Isolation**: Replay failures don't impact real-time ingestion
4. **Technology Flexibility**: Can use different tech stack optimized for batch processing
5. **Easier Testing**: Isolated service is easier to test and validate
6. **Deployment Independence**: Can deploy replay updates without touching core Graphiti

### Current Data Available for Replay Analysis

From the codebase analysis, we have rich data available:

#### EpisodicNode Properties
```python
class EpisodicNode(Node):
    uuid: str                    # Unique identifier
    name: str                    # Episode title/name
    group_id: str               # Partition identifier
    content: str                # Raw episode content (if store_raw_episode_content=True)
    source: EpisodeType         # message, document, etc.
    source_description: str     # Description of data source
    created_at: datetime        # When episode was created
    valid_at: datetime          # When original event occurred
    entity_edges: list[str]     # Referenced entity edge UUIDs
```

#### EntityNode Properties
```python
class EntityNode(Node):
    uuid: str                   # Unique identifier
    name: str                   # Entity name
    group_id: str              # Partition identifier
    labels: list[str]          # Entity type labels
    summary: str               # Regional summary of surrounding edges
    name_embedding: list[float] # Semantic embedding of name
    attributes: dict[str, Any]  # Additional entity attributes
    created_at: datetime       # Creation timestamp
```

#### EntityEdge Properties
```python
class EntityEdge(Edge):
    uuid: str                   # Unique identifier
    name: str                   # Relation name
    fact: str                   # Fact representing the relationship
    fact_embedding: list[float] # Semantic embedding of fact
    episodes: list[str]         # Episode UUIDs that reference this edge
    source_node_uuid: str       # Source entity UUID
    target_node_uuid: str       # Target entity UUID
    group_id: str              # Partition identifier
    created_at: datetime       # Creation timestamp
    valid_at: datetime         # When fact became true
    invalid_at: datetime       # When fact stopped being true
    expired_at: datetime       # When edge was invalidated
```

### Replay Service Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Graphiti Replay Service                  │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │   Candidate     │  │    Scheduler    │  │   Executor   │ │
│  │   Detector      │  │                 │  │              │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
│           │                     │                   │       │
│           └─────────────────────┼───────────────────┘       │
│                                 │                           │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Replay Metadata Store                      │ │
│  │         (SQLite/PostgreSQL/Redis)                       │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                 │
                                 │ HTTP API Calls
                                 ▼
┌─────────────────────────────────────────────────────────────┐
│                    Core Graphiti System                     │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │   Graph API     │  │   Queue System  │  │  Database    │ │
│  │   (FastAPI)     │  │   (Queued)      │  │ (Neo4j/Falkor)│ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Detailed Implementation Examples

### Separate Service Implementation

#### 1. Replay Service API Design

```python
# replay_service/main.py
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

app = FastAPI(title="Graphiti Memory Replay Service")

class ReplayCandidate(BaseModel):
    episode_uuid: str
    group_id: str
    entity_count: int
    edge_count: int
    cross_group_connections: int
    confidence_score: float
    replay_priority: float
    replay_reason: str
    last_replayed_at: Optional[datetime]

class ReplayRequest(BaseModel):
    episode_uuid: str
    priority: float = 0.5
    reason: str = "manual_replay"
    force: bool = False

class ReplayStatus(BaseModel):
    episode_uuid: str
    status: str  # pending, running, completed, failed
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    entities_before: int
    entities_after: int
    edges_before: int
    edges_after: int
    error_message: Optional[str]

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "graphiti-replay"}

@app.get("/candidates", response_model=List[ReplayCandidate])
async def get_replay_candidates(
    group_id: Optional[str] = None,
    limit: int = 100,
    min_priority: float = 0.3
):
    """Get episodes that would benefit from replay"""
    detector = ReplayCandidateDetector()
    return await detector.identify_candidates(group_id, limit, min_priority)

@app.post("/replay", response_model=ReplayStatus)
async def trigger_replay(
    request: ReplayRequest,
    background_tasks: BackgroundTasks
):
    """Trigger replay for a specific episode"""
    executor = ReplayExecutor()

    # Start replay in background
    background_tasks.add_task(executor.execute_replay, request)

    return ReplayStatus(
        episode_uuid=request.episode_uuid,
        status="pending",
        entities_before=0,
        entities_after=0,
        edges_before=0,
        edges_after=0
    )

@app.get("/replay/{episode_uuid}/status", response_model=ReplayStatus)
async def get_replay_status(episode_uuid: str):
    """Get status of replay operation"""
    metadata_store = ReplayMetadataStore()
    return await metadata_store.get_replay_status(episode_uuid)

@app.post("/scheduler/start")
async def start_scheduler():
    """Start the background replay scheduler"""
    scheduler = ReplayScheduler()
    await scheduler.start()
    return {"message": "Scheduler started"}

@app.post("/scheduler/stop")
async def stop_scheduler():
    """Stop the background replay scheduler"""
    scheduler = ReplayScheduler()
    await scheduler.stop()
    return {"message": "Scheduler stopped"}
```

#### 2. Candidate Detection Using Current Data

```python
# replay_service/candidate_detector.py
import httpx
from typing import List, Optional
from datetime import datetime, timedelta

class ReplayCandidateDetector:
    def __init__(self, graphiti_api_url: str = "http://localhost:8003"):
        self.graphiti_api_url = graphiti_api_url
        self.client = httpx.AsyncClient()

    async def identify_candidates(
        self,
        group_id: Optional[str] = None,
        limit: int = 100,
        min_priority: float = 0.3
    ) -> List[ReplayCandidate]:
        """Identify episodes needing replay using current Graphiti data"""

        candidates = []

        # Get sparse episodes (few entity connections)
        sparse_episodes = await self._get_sparse_episodes(group_id, limit)
        candidates.extend(sparse_episodes)

        # Get isolated episodes (no cross-group connections)
        isolated_episodes = await self._get_isolated_episodes(group_id, limit)
        candidates.extend(isolated_episodes)

        # Get old episodes that might benefit from re-processing
        stale_episodes = await self._get_stale_episodes(group_id, limit)
        candidates.extend(stale_episodes)

        # Deduplicate and filter by priority
        unique_candidates = self._deduplicate_candidates(candidates)
        filtered_candidates = [c for c in unique_candidates if c.replay_priority >= min_priority]

        # Sort by priority and limit results
        sorted_candidates = sorted(filtered_candidates, key=lambda x: x.replay_priority, reverse=True)
        return sorted_candidates[:limit]

    async def _get_sparse_episodes(self, group_id: Optional[str], limit: int) -> List[ReplayCandidate]:
        """Find episodes with few entity connections using current API"""

        # Use existing search API to find episodes
        search_params = {
            "query": "",  # Empty query to get all
            "limit": limit * 2,  # Get extra for filtering
        }
        if group_id:
            search_params["group_id"] = group_id

        response = await self.client.get(
            f"{self.graphiti_api_url}/search",
            params=search_params
        )

        if response.status_code != 200:
            return []

        search_results = response.json()
        candidates = []

        for result in search_results.get("results", []):
            if result.get("type") == "episode":
                # Get detailed episode info
                episode_detail = await self._get_episode_details(result["uuid"])
                if episode_detail:
                    entity_count = len(episode_detail.get("entity_edges", []))

                    # Consider sparse if < 3 entities
                    if entity_count < 3:
                        priority = self._calculate_priority(
                            entity_count=entity_count,
                            cross_group_count=0,  # Will calculate separately
                            days_since_creation=self._days_since_creation(episode_detail["created_at"])
                        )

                        candidates.append(ReplayCandidate(
                            episode_uuid=result["uuid"],
                            group_id=episode_detail["group_id"],
                            entity_count=entity_count,
                            edge_count=0,  # Will calculate separately
                            cross_group_connections=0,
                            confidence_score=0.5,  # Default
                            replay_priority=priority,
                            replay_reason="sparse_entities",
                            last_replayed_at=None
                        ))

        return candidates

    async def _get_episode_details(self, episode_uuid: str) -> Optional[dict]:
        """Get detailed episode information"""
        try:
            # Use existing node API to get episode details
            response = await self.client.get(f"{self.graphiti_api_url}/nodes/{episode_uuid}")
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return None

    def _calculate_priority(
        self,
        entity_count: int,
        cross_group_count: int,
        days_since_creation: int
    ) -> float:
        """Calculate replay priority score (0-1)"""

        # Base priority from entity sparsity (fewer entities = higher priority)
        entity_priority = max(0, (5 - entity_count) / 5)

        # Cross-group isolation penalty
        isolation_priority = 0.3 if cross_group_count == 0 else 0

        # Recency bonus (newer episodes get slight priority)
        recency_priority = max(0, (30 - days_since_creation) / 30) * 0.1

        # Weighted combination
        priority = entity_priority * 0.6 + isolation_priority * 0.3 + recency_priority * 0.1

        return min(1.0, priority)

    def _days_since_creation(self, created_at_str: str) -> int:
        """Calculate days since episode creation"""
        try:
            created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            return (datetime.now(created_at.tzinfo) - created_at).days
        except:
            return 0
```

#### 3. Replay Executor Using Existing APIs

```python
# replay_service/executor.py
import httpx
from typing import Optional
from datetime import datetime

class ReplayExecutor:
    def __init__(self, graphiti_api_url: str = "http://localhost:8003"):
        self.graphiti_api_url = graphiti_api_url
        self.client = httpx.AsyncClient(timeout=60.0)
        self.metadata_store = ReplayMetadataStore()

    async def execute_replay(self, request: ReplayRequest) -> ReplayStatus:
        """Execute replay for an episode using existing Graphiti APIs"""

        episode_uuid = request.episode_uuid

        try:
            # Update status to running
            await self.metadata_store.update_replay_status(
                episode_uuid, "running", started_at=datetime.utcnow()
            )

            # Get current episode data
            episode_data = await self._get_episode_data(episode_uuid)
            if not episode_data:
                raise Exception(f"Episode {episode_uuid} not found")

            # Count current entities/edges before replay
            entities_before = await self._count_episode_entities(episode_uuid)
            edges_before = await self._count_episode_edges(episode_uuid)

            # Execute replay by re-ingesting the episode
            replay_result = await self._reingest_episode(episode_data, request.force)

            # Count entities/edges after replay
            entities_after = await self._count_episode_entities(episode_uuid)
            edges_after = await self._count_episode_edges(episode_uuid)

            # Update status to completed
            status = ReplayStatus(
                episode_uuid=episode_uuid,
                status="completed",
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                entities_before=entities_before,
                entities_after=entities_after,
                edges_before=edges_before,
                edges_after=edges_after,
                error_message=None
            )

            await self.metadata_store.update_replay_status(
                episode_uuid, "completed",
                completed_at=datetime.utcnow(),
                entities_after=entities_after,
                edges_after=edges_after
            )

            return status

        except Exception as e:
            # Update status to failed
            await self.metadata_store.update_replay_status(
                episode_uuid, "failed",
                completed_at=datetime.utcnow(),
                error_message=str(e)
            )

            return ReplayStatus(
                episode_uuid=episode_uuid,
                status="failed",
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                entities_before=0,
                entities_after=0,
                edges_before=0,
                edges_after=0,
                error_message=str(e)
            )

    async def _reingest_episode(self, episode_data: dict, force: bool = False) -> dict:
        """Re-ingest episode using existing add_messages API"""

        # Prepare message for re-ingestion
        message_data = {
            "uuid": episode_data["uuid"],  # Preserve UUID for idempotent update
            "group_id": episode_data["group_id"],
            "name": episode_data["name"],
            "content": episode_data["content"],
            "timestamp": episode_data["valid_at"],
            "source_description": episode_data["source_description"],
            "role": "system",
            "role_type": "replay"
        }

        # Use existing messages endpoint for re-ingestion
        response = await self.client.post(
            f"{self.graphiti_api_url}/messages",
            json={
                "group_id": episode_data["group_id"],
                "messages": [message_data]
            }
        )

        if response.status_code not in [200, 201]:
            raise Exception(f"Re-ingestion failed: {response.status_code} - {response.text}")

        return response.json()
```

### 1. Original Replay Candidate Detection Implementation

```python
# graphiti_core/utils/replay/candidate_detector.py
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
from graphiti_core.driver.driver import GraphDriver
from graphiti_core.utils.datetime_utils import utc_now

@dataclass
class ReplayCandidate:
    episode_uuid: str
    group_id: str
    entity_count: int
    edge_count: int
    extraction_version: str
    confidence_score: float
    last_replayed_at: Optional[datetime]
    replay_priority: float
    replay_reason: str

class ReplayCandidateDetector:
    def __init__(self, driver: GraphDriver):
        self.driver = driver

    async def identify_candidates(
        self,
        group_id: Optional[str] = None,
        limit: int = 100
    ) -> List[ReplayCandidate]:
        """Identify episodes that would benefit from replay"""

        # Query for episodes with few entities
        sparse_episodes_query = """
        MATCH (ep:Episodic)
        WHERE ($group_id IS NULL OR ep.group_id = $group_id)
        OPTIONAL MATCH (ep)-[:MENTIONS]->(e:Entity)
        WITH ep, count(e) as entity_count
        WHERE entity_count < 3
        RETURN ep.uuid as episode_uuid,
               ep.group_id as group_id,
               entity_count,
               ep.extraction_version as extraction_version,
               ep.confidence_score as confidence_score
        LIMIT $limit
        """

        # Query for episodes missing cross-group connections
        isolated_episodes_query = """
        MATCH (ep:Episodic)-[:MENTIONS]->(e:Entity)
        WHERE ($group_id IS NULL OR ep.group_id = $group_id)
        WITH ep, collect(DISTINCT e.group_id) as connected_groups
        WHERE size(connected_groups) = 1 AND connected_groups[0] = ep.group_id
        RETURN ep.uuid as episode_uuid,
               ep.group_id as group_id,
               size(connected_groups) as cross_group_count
        LIMIT $limit
        """

        # Query for episodes with old extraction versions
        stale_episodes_query = """
        MATCH (ep:Episodic)
        WHERE ($group_id IS NULL OR ep.group_id = $group_id)
        AND (ep.extraction_version IS NULL OR ep.extraction_version < $current_version)
        RETURN ep.uuid as episode_uuid,
               ep.group_id as group_id,
               ep.extraction_version as extraction_version
        LIMIT $limit
        """

        session = self.driver.session()
        candidates = []

        try:
            # Execute queries and combine results
            sparse_results = await session.run(sparse_episodes_query, {
                'group_id': group_id,
                'limit': limit
            })

            isolated_results = await session.run(isolated_episodes_query, {
                'group_id': group_id,
                'limit': limit
            })

            stale_results = await session.run(stale_episodes_query, {
                'group_id': group_id,
                'current_version': self._get_current_extraction_version(),
                'limit': limit
            })

            # Process and prioritize candidates
            candidates.extend(self._process_sparse_episodes(sparse_results))
            candidates.extend(self._process_isolated_episodes(isolated_results))
            candidates.extend(self._process_stale_episodes(stale_results))

            # Remove duplicates and sort by priority
            unique_candidates = self._deduplicate_candidates(candidates)
            return sorted(unique_candidates, key=lambda x: x.replay_priority, reverse=True)

        finally:
            await session.close()

    def _calculate_replay_priority(
        self,
        entity_count: int,
        cross_group_count: int,
        days_since_last_replay: int,
        confidence_score: float
    ) -> float:
        """Calculate replay priority score (0-1, higher = more important)"""

        # Base priority from entity sparsity
        entity_priority = max(0, (5 - entity_count) / 5)

        # Cross-group connection bonus
        cross_group_priority = 0.3 if cross_group_count == 0 else 0

        # Time-based priority (replay less frequently over time)
        time_priority = min(1.0, days_since_last_replay / 30)

        # Confidence penalty (lower confidence = higher priority)
        confidence_priority = max(0, (0.8 - confidence_score) / 0.8)

        # Weighted combination
        priority = (
            entity_priority * 0.4 +
            cross_group_priority * 0.3 +
            time_priority * 0.2 +
            confidence_priority * 0.1
        )

        return min(1.0, priority)
```

### 2. Enhanced Worker Integration

```python
# Enhanced graphiti_core/ingestion/worker.py
class IngestionWorker:
    async def process_task(self, task: IngestionTask) -> bool:
        """Enhanced task processing with replay support"""

        if task.type == TaskType.REPLAY:
            return await self._process_replay_task(task)
        elif task.type == TaskType.EPISODE:
            return await self._process_episode_task(task)
        # ... existing task types

    async def _process_replay_task(self, task: IngestionTask) -> bool:
        """Process memory replay task"""
        try:
            payload = task.payload
            episode_uuid = payload.get('episode_uuid')
            replay_context = ReplayContext.from_dict(payload.get('replay_context', {}))

            logger.info(f"Processing replay task for episode {episode_uuid}")

            # Get original episode data
            episode = await EpisodicNode.get_by_uuid(self.graphiti.driver, episode_uuid)
            if not episode:
                logger.error(f"Episode {episode_uuid} not found for replay")
                return False

            # Execute replay using existing resilient ingestion
            result = await self.graphiti.add_episode_resilient(
                name=episode.name,
                episode_body=episode.content,
                source_description=episode.source_description,
                reference_time=episode.valid_at,
                source=episode.source,
                group_id=episode.group_id,
                uuid=episode.uuid,  # Preserve original UUID
                replay_mode=True,
                replay_context=replay_context
            )

            # Update replay metadata
            await self._update_replay_metadata(episode_uuid, replay_context, result)

            logger.info(f"Replay completed for episode {episode_uuid}: "
                       f"{result.entities_created} entities, {result.edges_created} edges")

            return True

        except Exception as e:
            logger.error(f"Replay task failed: {e}")
            await self._handle_replay_failure(task, e)
            return False
```

### 3. Replay Scheduler Implementation

```python
# graphiti_core/utils/replay/scheduler.py
import asyncio
from typing import Optional
from datetime import datetime, timedelta
from graphiti_core.config.replay_config import ReplayConfig
from graphiti_core.ingestion.queue_client import QueuedClient, IngestionTask, TaskType, TaskPriority

class MemoryReplayScheduler:
    def __init__(
        self,
        graphiti: 'Graphiti',
        queue_client: QueuedClient,
        config: ReplayConfig
    ):
        self.graphiti = graphiti
        self.queue_client = queue_client
        self.config = config
        self.candidate_detector = ReplayCandidateDetector(graphiti.driver)
        self._running = False
        self._circuit_breakers = {}  # group_id -> failure_count

    async def start_replay_loop(self):
        """Start the continuous replay scheduling loop"""
        if not self.config.enabled:
            logger.info("Memory replay is disabled")
            return

        self._running = True
        logger.info("Starting memory replay scheduler")

        while self._running:
            try:
                await self._replay_cycle()
                await asyncio.sleep(self.config.interval_seconds)
            except Exception as e:
                logger.error(f"Replay cycle failed: {e}")
                await asyncio.sleep(self.config.interval_seconds * 2)  # Backoff on error

    async def stop_replay_loop(self):
        """Stop the replay scheduling loop"""
        self._running = False
        logger.info("Stopping memory replay scheduler")

    async def _replay_cycle(self):
        """Execute one replay cycle"""
        logger.debug("Starting replay cycle")

        # Get candidates for replay
        candidates = await self.candidate_detector.identify_candidates(
            limit=self.config.batch_size * 2  # Get extra candidates for filtering
        )

        if not candidates:
            logger.debug("No replay candidates found")
            return

        # Filter candidates based on safety mechanisms
        filtered_candidates = self._apply_safety_filters(candidates)

        # Limit to batch size
        batch_candidates = filtered_candidates[:self.config.batch_size]

        logger.info(f"Scheduling {len(batch_candidates)} episodes for replay")

        # Queue replay tasks
        for candidate in batch_candidates:
            await self._queue_replay_task(candidate)

    def _apply_safety_filters(self, candidates: List[ReplayCandidate]) -> List[ReplayCandidate]:
        """Apply safety filters to candidate list"""
        filtered = []

        for candidate in candidates:
            # Check circuit breaker
            if self._is_circuit_breaker_active(candidate.group_id):
                logger.debug(f"Circuit breaker active for group {candidate.group_id}")
                continue

            # Check cooldown period
            if self._is_in_cooldown(candidate):
                logger.debug(f"Episode {candidate.episode_uuid} in cooldown period")
                continue

            # Check rate limits
            if not await self._check_rate_limit(candidate.group_id):
                logger.debug(f"Rate limit exceeded for group {candidate.group_id}")
                continue

            filtered.append(candidate)

        return filtered

    async def _queue_replay_task(self, candidate: ReplayCandidate):
        """Queue a replay task for execution"""
        replay_context = ReplayContext(
            reason=candidate.replay_reason,
            priority_score=candidate.replay_priority,
            scheduled_at=utc_now(),
            attempt_number=1
        )

        task = IngestionTask(
            id=f"replay_{candidate.episode_uuid}_{int(time.time())}",
            type=TaskType.REPLAY,
            payload={
                'episode_uuid': candidate.episode_uuid,
                'replay_context': replay_context.to_dict()
            },
            group_id=candidate.group_id,
            priority=TaskPriority.NORMAL,
            metadata={
                'replay_reason': candidate.replay_reason,
                'priority_score': candidate.replay_priority
            }
        )

        await self.queue_client.enqueue(task)
        logger.debug(f"Queued replay task for episode {candidate.episode_uuid}")
```

### 4. Database Integration Examples

```python
# graphiti_core/utils/replay/metadata_manager.py
class ReplayMetadataManager:
    def __init__(self, driver: GraphDriver):
        self.driver = driver

    async def update_replay_metadata(
        self,
        episode_uuid: str,
        replay_context: ReplayContext,
        result: 'AddEpisodeResults'
    ):
        """Update replay metadata after successful replay"""

        query = """
        MERGE (rm:ReplayMetadata {episode_uuid: $episode_uuid})
        SET rm.group_id = $group_id,
            rm.last_replayed_at = $timestamp,
            rm.replay_attempts = COALESCE(rm.replay_attempts, 0) + 1,
            rm.extraction_version = $extraction_version,
            rm.replay_reason = $replay_reason,
            rm.confidence_score = $confidence_score,
            rm.updated_at = $timestamp

        // Update episode metrics
        MATCH (ep:Episodic {uuid: $episode_uuid})
        SET ep.entity_count = $entity_count,
            ep.edge_count = $edge_count,
            ep.extraction_version = $extraction_version,
            ep.confidence_score = $confidence_score
        """

        session = self.driver.session()
        try:
            await session.run(query, {
                'episode_uuid': episode_uuid,
                'group_id': replay_context.group_id,
                'timestamp': utc_now(),
                'extraction_version': self._get_current_extraction_version(),
                'replay_reason': replay_context.reason,
                'confidence_score': result.confidence_score,
                'entity_count': len(result.entities_created),
                'edge_count': len(result.edges_created)
            })
        finally:
            await session.close()
```

### 5. Enhanced Resilient Ingestion Integration

```python
# Enhanced graphiti_core/graphiti.py
@dataclass
class ReplayContext:
    reason: str
    priority_score: float
    scheduled_at: datetime
    attempt_number: int
    group_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'reason': self.reason,
            'priority_score': self.priority_score,
            'scheduled_at': self.scheduled_at.isoformat(),
            'attempt_number': self.attempt_number,
            'group_id': self.group_id
        }

# Enhanced add_episode_resilient method signature
async def add_episode_resilient(
    self,
    # ... existing parameters ...
    replay_mode: bool = False,  # NEW
    replay_context: ReplayContext | None = None,  # NEW
) -> 'AddEpisodeResults':
    """Enhanced resilient ingestion with replay support"""

    if replay_mode and replay_context:
        logger.info(f"Replay operation: {replay_context.reason}")

    # ... existing implementation with replay enhancements ...
```

## Testing Strategy

### Unit Tests
```python
# tests/test_replay_system.py
class TestReplaySystem:
    async def test_candidate_detection(self):
        """Test replay candidate detection logic"""
        detector = ReplayCandidateDetector(mock_driver)
        candidates = await detector.identify_candidates(limit=10)

        assert len(candidates) <= 10
        assert all(c.replay_priority >= 0 for c in candidates)

    async def test_replay_execution(self):
        """Test replay execution preserves UUID"""
        original_episode = await create_test_episode()

        result = await graphiti.add_episode_resilient(
            name=original_episode.name,
            episode_body=original_episode.content,
            uuid=original_episode.uuid,
            replay_mode=True,
            replay_context=ReplayContext(
                reason="test_replay",
                priority_score=0.8,
                scheduled_at=utc_now(),
                attempt_number=1
            )
        )

        # Verify UUID preservation and enhancement
        assert result.episode.uuid == original_episode.uuid
        assert len(result.entities_created) >= len(original_entities)
```

#### 4. Replay Metadata Store

```python
# replay_service/metadata_store.py
import sqlite3
import json
from typing import Optional, List
from datetime import datetime
from dataclasses import dataclass, asdict

@dataclass
class ReplayRecord:
    episode_uuid: str
    group_id: str
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    entities_before: int
    entities_after: int
    edges_before: int
    edges_after: int
    replay_reason: str
    error_message: Optional[str]
    created_at: datetime

class ReplayMetadataStore:
    def __init__(self, db_path: str = "replay_metadata.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database for replay metadata"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS replay_records (
                episode_uuid TEXT PRIMARY KEY,
                group_id TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                entities_before INTEGER DEFAULT 0,
                entities_after INTEGER DEFAULT 0,
                edges_before INTEGER DEFAULT 0,
                edges_after INTEGER DEFAULT 0,
                replay_reason TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_replay_group_id ON replay_records(group_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_replay_status ON replay_records(status)
        """)

        conn.commit()
        conn.close()

    async def update_replay_status(
        self,
        episode_uuid: str,
        status: str,
        **kwargs
    ):
        """Update replay status and metadata"""
        conn = sqlite3.connect(self.db_path)

        # Build update fields
        update_fields = ["status = ?", "updated_at = ?"]
        values = [status, datetime.utcnow().isoformat()]

        for field, value in kwargs.items():
            if value is not None:
                update_fields.append(f"{field} = ?")
                if isinstance(value, datetime):
                    values.append(value.isoformat())
                else:
                    values.append(value)

        values.append(episode_uuid)

        conn.execute(f"""
            INSERT OR REPLACE INTO replay_records
            (episode_uuid, group_id, status, created_at, updated_at)
            VALUES (?, 'unknown', ?, ?, ?)
            ON CONFLICT(episode_uuid) DO UPDATE SET
            {', '.join(update_fields)}
        """, [episode_uuid, status, datetime.utcnow().isoformat(), datetime.utcnow().isoformat()] + values[:-1])

        conn.commit()
        conn.close()
```

#### 5. Deployment Configuration

```yaml
# docker-compose.replay.yml
version: '3.8'

services:
  graphiti-replay:
    build:
      context: ./replay_service
      dockerfile: Dockerfile
    ports:
      - "8004:8000"
    environment:
      - GRAPHITI_API_URL=http://graphiti-api:8000
      - REPLAY_DB_PATH=/data/replay_metadata.db
      - REPLAY_ENABLED=true
      - REPLAY_INTERVAL_SECONDS=300
      - REPLAY_BATCH_SIZE=10
      - REPLAY_MAX_ATTEMPTS=3
      - LOG_LEVEL=INFO
    volumes:
      - replay_data:/data
    depends_on:
      - graphiti-api
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  replay_data:
```

```dockerfile
# replay_service/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p /data

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```txt
# replay_service/requirements.txt
fastapi==0.104.1
uvicorn==0.24.0
httpx==0.25.2
pydantic==2.5.0
sqlite3
python-multipart==0.0.6
```

### Separate Service Benefits

#### 1. **Data Access Patterns**
- **Read-Only Access**: Replay service only reads from Graphiti via APIs
- **No Direct DB Access**: Uses existing HTTP endpoints, maintaining encapsulation
- **API-First Integration**: Leverages existing `/search`, `/nodes`, `/messages` endpoints
- **Idempotent Operations**: Re-ingestion with same UUID updates existing data

#### 2. **Operational Advantages**
- **Independent Scaling**: Scale replay service based on replay workload
- **Fault Isolation**: Replay failures don't impact core ingestion
- **Easy Monitoring**: Separate service metrics and logs
- **Technology Choice**: Can use different stack (e.g., Go, Rust) if needed

#### 3. **Development Benefits**
- **Clean APIs**: Well-defined interface between services
- **Easier Testing**: Mock Graphiti API for replay service tests
- **Independent Deployment**: Deploy replay updates without touching core
- **Team Ownership**: Different teams can own different services

#### 4. **Current Data Utilization**
- **Rich Episode Data**: Uses existing `content`, `entity_edges`, `created_at` fields
- **Entity Relationships**: Leverages existing entity and edge APIs
- **Search Integration**: Uses existing search endpoints for candidate detection
- **Metadata Tracking**: Separate SQLite store for replay-specific metadata

### Implementation Phases for Separate Service

#### Phase 1: Basic Service (Week 1)
1. **Core Service Setup**
   - FastAPI application with health checks
   - SQLite metadata store
   - Basic candidate detection using search API
   - Manual replay trigger endpoint

#### Phase 2: Automated Detection (Week 2)
1. **Enhanced Candidate Detection**
   - Sparse episode detection via search API
   - Cross-group connection analysis
   - Priority scoring algorithm
   - Candidate filtering and ranking

#### Phase 3: Execution Engine (Week 3)
1. **Replay Execution**
   - Episode re-ingestion via messages API
   - Before/after metrics collection
   - Error handling and retry logic
   - Status tracking and reporting

#### Phase 4: Scheduler & Monitoring (Week 4)
1. **Background Scheduler**
   - Automated replay scheduling
   - Rate limiting and safety mechanisms
   - Circuit breakers per group
   - Comprehensive monitoring and alerting

#### Phase 5: Production Readiness (Week 5)
1. **Production Features**
   - Docker deployment configuration
   - Performance optimization
   - Comprehensive testing
   - Documentation and runbooks

---

*This comprehensive specification provides a complete blueprint for implementing a neuroscience-inspired memory replay system as a separate microservice that will transform Graphiti's knowledge graph quality through intelligent, automated episode re-processing and cross-group entity enrichment.*
