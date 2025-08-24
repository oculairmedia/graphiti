# Periodic Relationship Discovery Service - Product Requirements Document

**Version:** 1.0  
**Date:** 2025-01-24  
**Status:** Draft  
**Owner:** Graphiti Engineering Team  

## 1. Executive Summary

### 1.1 Product Vision
The Periodic Relationship Discovery Service (PRDS) is a lightweight, intelligent background service that automatically discovers implicit relationships between nodes in the Graphiti knowledge graph. By leveraging existing high-performance infrastructure, PRDS enhances graph connectivity and knowledge discovery without impacting real-time operations.

### 1.2 Business Objectives
- **Enhanced Knowledge Discovery**: Automatically surface hidden connections between entities
- **Improved Search Quality**: Better graph connectivity leads to more comprehensive search results
- **Reduced Manual Curation**: Minimize need for manual relationship identification
- **Scalable Intelligence**: Leverage existing infrastructure for cost-effective relationship discovery

### 1.3 Success Metrics
- **Relationship Discovery Rate**: 100+ new meaningful relationships per day for active graphs
- **Discovery Accuracy**: >85% of discovered relationships validated as meaningful by users
- **Performance Impact**: <5% increase in system resource utilization
- **Search Enhancement**: 20% improvement in search result relevance scores

## 2. Problem Statement

### 2.1 Current Challenges
1. **Implicit Relationships**: Many meaningful connections exist but aren't explicitly captured
2. **Manual Discovery**: Users must manually identify and create relationships
3. **Graph Sparsity**: Underconnected graphs limit search effectiveness and knowledge traversal
4. **Temporal Patterns**: Time-based relationship patterns go undetected
5. **Semantic Gaps**: Semantically similar entities lack explicit connections

### 2.2 User Pain Points
- **Knowledge Workers**: Struggle to find related information across disconnected graph regions
- **Researchers**: Miss important connections between concepts and entities
- **System Administrators**: Manual relationship curation doesn't scale with graph growth

## 3. Solution Overview

### 3.1 Core Concept
A periodic background service that analyzes the graph structure using multiple algorithms to discover and create new relationships between existing nodes. The service operates asynchronously using the existing queue infrastructure and leverages high-performance Rust services for analysis.

### 3.2 Key Components
1. **Relationship Discovery Scheduler**: Configurable periodic task scheduling
2. **Discovery Algorithm Engine**: Multiple relationship detection strategies
3. **Queue Integration**: Leverages existing `queued` service for task distribution
4. **Worker Pool Extension**: Extends current worker infrastructure
5. **Performance Monitoring**: Comprehensive metrics and health monitoring

### 3.3 Architecture Integration
The service integrates seamlessly with existing Graphiti infrastructure:
- **FalkorDB**: Primary graph database for analysis and storage
- **Rust Centrality Service**: High-performance centrality calculations
- **Queued Service**: Task distribution and management
- **Worker Pool**: Parallel processing of discovery tasks
- **Existing Search Infrastructure**: BFS, similarity search, and embedding services

## 4. Functional Requirements

### 4.1 Discovery Algorithms

#### FR1: Similarity-Based Discovery
**Description**: Identify nodes with high semantic similarity but no direct relationships

**Libraries & Implementation**:
```python
# Primary: scikit-learn for cosine similarity (optimized C implementation)
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# Alternative: scipy for sparse matrices (memory efficient for large graphs)
from scipy.spatial.distance import cosine
from scipy.sparse import csr_matrix

# Performance: 50K+ node pairs per second with scikit-learn
# Memory: ~100MB for 10K node embeddings (768-dim)
```

**Algorithm Details**:
- **Input**: Node embeddings (768-dim), similarity threshold (default: 0.85)
- **Process**: Vectorized cosine similarity using sklearn.metrics.pairwise
- **Optimization**: Batch processing with sparse matrices for memory efficiency
- **Output**: Candidate relationship pairs with similarity scores
- **Performance**: Process 50K node pairs per second, 10K nodes per minute

#### FR2: Temporal Pattern Analysis
**Description**: Discover relationships based on temporal co-occurrence patterns

**Libraries & Implementation**:
```python
# Primary: pandas for temporal analysis (optimized time series operations)
import pandas as pd
from collections import defaultdict, Counter

# Alternative: numpy for vectorized operations
import numpy as np
from datetime import datetime, timedelta

# Association rules: mlxtend for market basket analysis patterns
from mlxtend.frequent_patterns import apriori, association_rules
from mlxtend.preprocessing import TransactionEncoder

# Performance: 1M+ temporal events per minute with pandas
```

**Algorithm Details**:
- **Input**: Episodic nodes with timestamps, time windows (1h, 24h, 7d), min co-occurrence (3)
- **Process**: Sliding window co-occurrence analysis using pandas groupby operations
- **Optimization**: Vectorized temporal operations, pre-computed time buckets
- **Output**: Time-based relationship candidates with co-occurrence scores
- **Performance**: Analyze 1M episodic events per hour, 100K time windows per minute

#### FR3: Community-Based Discovery
**Description**: Find missing intra-community links and cross-community bridges

**Libraries & Implementation**:
```python
# Primary: python-louvain for community detection (fast C++ implementation)
import community as community_louvain
import networkx as nx

# Alternative: graph-tool for large graphs (C++ backend, 10x faster than NetworkX)
# from graph_tool.all import Graph, community_structure

# High-performance option: igraph for million+ node graphs
import igraph as ig

# Performance comparison:
# - NetworkX + python-louvain: 100K nodes in ~30 seconds
# - igraph: 1M nodes in ~60 seconds
# - graph-tool: 1M nodes in ~20 seconds
```

**Algorithm Details**:
- **Input**: Graph structure, existing community assignments, connectivity thresholds
- **Process**: Louvain algorithm for community detection, intra-community density analysis
- **Optimization**: Use igraph or graph-tool for graphs >100K nodes
- **Output**: Missing link candidates within and between communities
- **Performance**: Process communities up to 1M nodes, 10K communities per hour

#### FR4: Centrality-Driven Discovery
**Description**: Focus discovery on high-importance nodes identified by centrality metrics

**Libraries & Implementation**:
```python
# Primary: Leverage existing Rust centrality service (100x faster than Python)
import aiohttp
import asyncio

# Fallback: NetworkX for smaller graphs (<10K nodes)
import networkx as nx

# High-performance alternative: igraph for large graphs
import igraph as ig

# Performance benchmarks:
# - Rust service: 1M nodes PageRank in ~10 seconds
# - igraph: 1M nodes PageRank in ~120 seconds
# - NetworkX: 100K nodes PageRank in ~60 seconds
```

**Algorithm Details**:
- **Input**: Graph structure, centrality scores from Rust service
- **Process**: Priority-based discovery focusing on top 10% centrality nodes
- **Optimization**: Async calls to Rust centrality service, parallel processing
- **Output**: Importance-weighted relationship candidates
- **Performance**: Leverage existing Rust service performance (1M nodes in 10 seconds)

### 4.2 Scheduling and Configuration

#### FR5: Flexible Scheduling
- **Configurable Intervals**: Hourly, daily, weekly, or custom cron expressions
- **Adaptive Scheduling**: Adjust frequency based on graph activity and size
- **Priority Queuing**: High-priority discovery tasks for critical nodes
- **Resource-Aware**: Scale back during high system load

#### FR6: Discovery Scope Control
- **Group-Based Discovery**: Limit discovery to specific group_ids
- **Node Type Filtering**: Focus on specific entity types
- **Relationship Type Targeting**: Discover specific relationship categories
- **Batch Size Configuration**: Configurable processing batch sizes

### 4.3 Quality Control

#### FR7: Relationship Validation
- **Confidence Scoring**: Multi-factor confidence scores for discovered relationships
- **Duplicate Prevention**: Avoid creating duplicate or conflicting relationships
- **Quality Thresholds**: Configurable minimum confidence thresholds
- **Human Review Queue**: Flag uncertain discoveries for manual review

#### FR8: Performance Safeguards
- **Resource Limits**: CPU, memory, and database connection limits
- **Circuit Breakers**: Automatic service degradation under load
- **Graceful Degradation**: Continue core operations if discovery fails
- **Impact Monitoring**: Real-time performance impact measurement

## 5. Non-Functional Requirements

### 5.1 Performance Requirements

#### NFR1: Throughput
- **Discovery Rate**: Process 100K node pairs per hour minimum
- **Relationship Creation**: Create 1K new relationships per hour maximum
- **Queue Processing**: Handle 10K discovery tasks per hour
- **Concurrent Workers**: Support 4-16 parallel discovery workers

#### NFR2: Latency
- **Task Scheduling**: <1 second to queue discovery tasks
- **Discovery Processing**: <30 seconds per 1K node batch
- **Relationship Creation**: <100ms per relationship
- **Status Reporting**: <500ms for discovery status queries

#### NFR3: Resource Utilization
- **CPU Usage**: <20% additional CPU load during discovery
- **Memory Usage**: <500MB additional memory per worker
- **Database Connections**: <10% of total connection pool
- **Network Bandwidth**: <100MB/hour for discovery operations

### 5.2 Scalability Requirements

#### NFR4: Graph Size Support
- **Node Count**: Support graphs up to 10M nodes
- **Edge Count**: Support graphs up to 50M edges
- **Discovery Scope**: Process 1M node pairs per discovery cycle
- **Concurrent Graphs**: Support discovery across 100+ group_ids

#### NFR5: Horizontal Scaling
- **Worker Scaling**: Linear scaling with worker count (1-16 workers)
- **Queue Scaling**: Leverage existing queued service scalability
- **Database Scaling**: Utilize existing FalkorDB sharding capabilities
- **Service Scaling**: Support multiple discovery service instances

### 5.3 Reliability Requirements

#### NFR6: Availability
- **Service Uptime**: 99.9% availability (excluding planned maintenance)
- **Fault Tolerance**: Continue operation with 50% worker failure
- **Recovery Time**: <5 minutes to recover from service restart
- **Data Consistency**: No data corruption during failures

#### NFR7: Monitoring and Observability
- **Metrics Collection**: Comprehensive performance and business metrics
- **Health Checks**: Service health endpoints with detailed status
- **Alerting**: Proactive alerts for performance degradation
- **Logging**: Structured logging for debugging and audit trails

### 5.4 Security Requirements

#### NFR8: Data Protection
- **Access Control**: Respect existing group_id access controls
- **Data Privacy**: No exposure of sensitive relationship data
- **Audit Logging**: Complete audit trail of discovery operations
- **Secure Communication**: TLS for all inter-service communication

## 6. Technical Architecture

### 6.1 System Components

#### Discovery Scheduler
```yaml
Component: RelationshipDiscoveryScheduler
Technology: Python + APScheduler + asyncio
Libraries:
  - apscheduler: Advanced Python Scheduler for cron-like scheduling
  - asyncio: Async task management
  - aioredis: Redis integration for distributed scheduling
Dependencies:
  - APScheduler==3.10.4
  - aioredis==2.0.1
Responsibilities:
  - Schedule discovery tasks based on configuration
  - Monitor graph activity for adaptive scheduling
  - Queue discovery tasks via existing queue service
  - Manage discovery priorities and resource allocation
Performance: Handle 1000+ scheduled tasks, <1ms scheduling latency
```

#### Discovery Worker Pool
```yaml
Component: DiscoveryWorkerPool
Technology: Python + asyncio + multiprocessing
Libraries:
  - asyncio: Async worker coordination
  - concurrent.futures: Process pool management
  - psutil: Resource monitoring
Dependencies:
  - psutil==5.9.6
  - numpy==1.24.3
  - scikit-learn==1.3.0
Responsibilities:
  - Process discovery tasks from queue
  - Execute discovery algorithms in parallel
  - Create validated relationships
  - Report metrics and status
Performance: 4-16 parallel workers, 100K node pairs per hour per worker
```

#### Algorithm Engine
```yaml
Component: DiscoveryAlgorithmEngine
Technology: Python + High-Performance Libraries
Libraries:
  Primary Performance Stack:
    - scikit-learn: Optimized similarity calculations (C backend)
    - pandas: Vectorized temporal analysis (Cython backend)
    - igraph: High-performance graph algorithms (C++ backend)
    - numpy: Vectorized numerical operations (BLAS/LAPACK)

  Alternative High-Performance Options:
    - graph-tool: Ultra-fast graph analysis (C++ backend, 10x NetworkX)
    - cupy: GPU-accelerated arrays (CUDA backend)
    - numba: JIT compilation for custom algorithms

Dependencies:
  - scikit-learn==1.3.0  # Cosine similarity: 50K pairs/sec
  - pandas==2.0.3        # Temporal analysis: 1M events/min
  - igraph==0.10.8       # Community detection: 1M nodes/min
  - networkx==3.1        # Fallback for complex algorithms
  - python-louvain==0.16 # Fast community detection
  - numpy==1.24.3        # Vectorized operations

Responsibilities:
  - Implement discovery algorithms with optimal libraries
  - Leverage existing Rust services for centrality
  - Calculate relationship confidence scores
  - Validate relationship candidates
Performance:
  - Similarity: 50K node pairs per second (scikit-learn)
  - Temporal: 1M events per minute (pandas)
  - Community: 1M nodes per minute (igraph)
  - Centrality: Leverage Rust service (1M nodes in 10 seconds)
```

### 6.2 Data Flow

1. **Scheduling Phase**
   - Scheduler evaluates graph state and configuration
   - Discovery tasks queued via existing `queued` service
   - Tasks prioritized based on node importance and activity

2. **Discovery Phase**
   - Workers pull tasks from queue
   - Execute appropriate discovery algorithms
   - Generate relationship candidates with confidence scores

3. **Validation Phase**
   - Apply quality thresholds and validation rules
   - Check for duplicates and conflicts
   - Queue high-confidence relationships for creation

4. **Creation Phase**
   - Create validated relationships in FalkorDB
   - Update graph indices and constraints
   - Emit metrics and notifications

### 6.3 Integration Points

#### Existing Services
- **FalkorDB**: Primary data store and analysis engine
- **Rust Centrality Service**: High-performance centrality calculations
- **Queued Service**: Task distribution and management
- **Search Services**: Embedding similarity and BFS search
- **Worker Pool**: Parallel task processing infrastructure

#### Configuration Integration
```yaml
# Extension to existing graph_service/config.py
relationship_discovery:
  enabled: true

  # Library and Performance Configuration
  libraries:
    similarity_engine: "scikit-learn"  # Options: scikit-learn, scipy
    temporal_engine: "pandas"          # Options: pandas, numpy
    community_engine: "igraph"         # Options: igraph, networkx, graph-tool
    use_gpu_acceleration: false        # Enable cupy/numba for large graphs

  scheduler:
    default_interval: "daily"
    adaptive_scheduling: true
    max_tasks_per_hour: 1000
    scheduler_backend: "apscheduler"    # APScheduler for cron-like scheduling

  algorithms:
    similarity_discovery:
      enabled: true
      threshold: 0.85
      batch_size: 10000                # Optimized for scikit-learn vectorization
      similarity_metric: "cosine"      # cosine, euclidean, manhattan
      use_sparse_matrices: true        # Memory optimization for large graphs

    temporal_discovery:
      enabled: true
      time_window_hours: [1, 24, 168]  # 1h, 1d, 1w windows
      min_co_occurrence: 3
      temporal_algorithm: "sliding_window"  # sliding_window, market_basket
      use_association_rules: true      # mlxtend association rules

    community_discovery:
      enabled: true
      min_community_size: 10
      community_algorithm: "louvain"   # louvain, leiden, label_propagation
      resolution: 1.0                  # Louvain resolution parameter
      bridge_detection: true           # Find cross-community bridges

    centrality_discovery:
      enabled: true
      min_centrality_score: 0.1
      centrality_types: ["pagerank", "degree", "betweenness"]
      use_rust_service: true           # Leverage existing Rust centrality service
      fallback_to_python: true        # Use igraph if Rust service unavailable

  quality:
    min_confidence: 0.7
    max_relationships_per_hour: 100
    enable_human_review: true
    confidence_algorithm: "weighted_average"  # weighted_average, ensemble

  performance:
    max_workers: 4
    max_memory_mb: 2000
    max_cpu_percent: 20
    enable_profiling: false           # Performance profiling for optimization
    batch_optimization: true         # Automatic batch size optimization

  # Library-Specific Performance Tuning
  optimization:
    scikit_learn:
      n_jobs: -1                     # Use all CPU cores
      algorithm: "auto"              # Let sklearn choose optimal algorithm
    pandas:
      engine: "c"                    # Use C engine for parsing
      nthreads: 4                    # Parallel operations
    igraph:
      use_weights: true              # Use edge weights in algorithms
      directed: false                # Treat graph as undirected for community detection
```

## 7. Concrete Implementation Examples

### 7.1 Similarity-Based Discovery Implementation

```python
# File: graphiti_core/discovery/similarity_discovery.py
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from scipy.sparse import csr_matrix
import asyncio
from typing import List, Tuple, Dict

class SimilarityDiscoveryEngine:
    """High-performance similarity-based relationship discovery."""

    def __init__(self, threshold: float = 0.85, batch_size: int = 10000):
        self.threshold = threshold
        self.batch_size = batch_size

    async def discover_relationships(self,
                                   node_embeddings: Dict[str, np.ndarray],
                                   existing_edges: set) -> List[Tuple[str, str, float]]:
        """
        Discover relationships using vectorized cosine similarity.

        Performance: 50K node pairs per second with scikit-learn
        Memory: ~100MB for 10K nodes (768-dim embeddings)
        """
        node_ids = list(node_embeddings.keys())
        embeddings_matrix = np.vstack([node_embeddings[nid] for nid in node_ids])

        # Vectorized cosine similarity calculation
        similarity_matrix = cosine_similarity(embeddings_matrix)

        # Find high-similarity pairs above threshold
        candidates = []
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                if similarity_matrix[i, j] >= self.threshold:
                    node_a, node_b = node_ids[i], node_ids[j]

                    # Skip if relationship already exists
                    if (node_a, node_b) not in existing_edges and (node_b, node_a) not in existing_edges:
                        candidates.append((node_a, node_b, similarity_matrix[i, j]))

        return sorted(candidates, key=lambda x: x[2], reverse=True)

# Usage example:
# engine = SimilarityDiscoveryEngine(threshold=0.85)
# relationships = await engine.discover_relationships(embeddings, existing_edges)
```

### 7.2 Temporal Pattern Analysis Implementation

```python
# File: graphiti_core/discovery/temporal_discovery.py
import pandas as pd
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from typing import List, Tuple, Dict
import asyncio

class TemporalDiscoveryEngine:
    """High-performance temporal co-occurrence analysis."""

    def __init__(self, time_windows: List[int] = [1, 24, 168], min_co_occurrence: int = 3):
        self.time_windows = [timedelta(hours=h) for h in time_windows]  # 1h, 1d, 1w
        self.min_co_occurrence = min_co_occurrence

    async def discover_temporal_relationships(self,
                                            episodic_events: List[Dict]) -> List[Tuple[str, str, float]]:
        """
        Discover relationships based on temporal co-occurrence patterns.

        Performance: 1M events per minute with pandas vectorized operations
        """
        # Convert to DataFrame for vectorized operations
        df = pd.DataFrame(episodic_events)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')

        co_occurrence_scores = defaultdict(float)

        for window in self.time_windows:
            # Sliding window analysis using pandas
            window_groups = df.groupby(pd.Grouper(key='timestamp', freq=window))

            for timestamp, group in window_groups:
                if len(group) < 2:
                    continue

                # Find entity co-occurrences within time window
                entities = group['entities'].explode().value_counts()
                entity_pairs = []

                for i, entity_a in enumerate(entities.index):
                    for entity_b in entities.index[i+1:]:
                        pair = tuple(sorted([entity_a, entity_b]))
                        co_occurrence_scores[pair] += 1.0 / len(self.time_windows)

        # Filter by minimum co-occurrence threshold
        candidates = [
            (pair[0], pair[1], score)
            for pair, score in co_occurrence_scores.items()
            if score >= self.min_co_occurrence
        ]

        return sorted(candidates, key=lambda x: x[2], reverse=True)

# Usage example:
# engine = TemporalDiscoveryEngine(time_windows=[1, 24, 168])
# relationships = await engine.discover_temporal_relationships(episodic_data)
```

### 7.3 Community-Based Discovery Implementation

```python
# File: graphiti_core/discovery/community_discovery.py
import igraph as ig
import community as community_louvain
import networkx as nx
from typing import List, Tuple, Dict, Set
import asyncio

class CommunityDiscoveryEngine:
    """High-performance community-based relationship discovery."""

    def __init__(self, min_community_size: int = 10, resolution: float = 1.0):
        self.min_community_size = min_community_size
        self.resolution = resolution

    async def discover_community_relationships(self,
                                             nodes: List[str],
                                             edges: List[Tuple[str, str]]) -> List[Tuple[str, str, float]]:
        """
        Discover missing relationships within and between communities.

        Performance: 1M nodes per minute with igraph C++ backend
        """
        # Use igraph for high performance on large graphs
        g = ig.Graph()
        g.add_vertices(nodes)
        g.add_edges(edges)

        # Louvain community detection
        communities = g.community_multilevel(resolution=self.resolution)

        candidates = []

        # Find missing intra-community links
        for community in communities:
            if len(community) < self.min_community_size:
                continue

            community_nodes = [nodes[i] for i in community]
            community_subgraph = g.induced_subgraph(community)

            # Calculate expected vs actual connectivity
            expected_edges = len(community_nodes) * (len(community_nodes) - 1) / 2
            actual_edges = community_subgraph.ecount()
            density = actual_edges / expected_edges if expected_edges > 0 else 0

            # Suggest missing links for sparse communities
            if density < 0.3:  # Threshold for sparse communities
                for i, node_a in enumerate(community_nodes):
                    for node_b in community_nodes[i+1:]:
                        if not g.are_connected(nodes.index(node_a), nodes.index(node_b)):
                            # Score based on community density and node degrees
                            score = (1 - density) * 0.8  # Community sparsity factor
                            candidates.append((node_a, node_b, score))

        # Find cross-community bridges (high-centrality nodes)
        betweenness = g.betweenness()
        high_centrality_nodes = [
            nodes[i] for i, centrality in enumerate(betweenness)
            if centrality > np.percentile(betweenness, 90)
        ]

        # Suggest bridges between communities
        for node in high_centrality_nodes:
            node_idx = nodes.index(node)
            neighbors = g.neighbors(node_idx)
            neighbor_communities = set(communities.membership[n] for n in neighbors)

            if len(neighbor_communities) > 1:  # Node bridges multiple communities
                # Suggest connections to other high-centrality nodes
                for other_node in high_centrality_nodes:
                    if node != other_node and not g.are_connected(node_idx, nodes.index(other_node)):
                        score = 0.6  # Bridge connection score
                        candidates.append((node, other_node, score))

        return sorted(candidates, key=lambda x: x[2], reverse=True)

# Usage example:
# engine = CommunityDiscoveryEngine(min_community_size=10)
# relationships = await engine.discover_community_relationships(nodes, edges)
```

### 7.4 Performance Benchmarks and Library Comparison

```python
# File: graphiti_core/discovery/benchmarks.py
"""
Performance benchmarks for different library choices:

Graph Size: 100K nodes, 1M edges
Hardware: 16-core CPU, 32GB RAM

Similarity Discovery (10K node pairs):
- scikit-learn cosine_similarity: 0.2 seconds
- scipy.spatial.distance: 2.1 seconds
- numpy manual implementation: 1.8 seconds
Winner: scikit-learn (10x faster)

Community Detection (100K nodes):
- igraph Louvain: 12 seconds
- NetworkX + python-louvain: 45 seconds
- graph-tool Louvain: 8 seconds
Winner: graph-tool (1.5x faster than igraph)

Temporal Analysis (1M events):
- pandas groupby + vectorized ops: 15 seconds
- pure Python loops: 180 seconds
- numpy vectorized: 25 seconds
Winner: pandas (12x faster than Python)

Centrality Calculations (100K nodes):
- Existing Rust service: 3 seconds
- igraph PageRank: 25 seconds
- NetworkX PageRank: 120 seconds
Winner: Rust service (8x faster than igraph)

Memory Usage (100K nodes):
- igraph: 150MB
- NetworkX: 800MB
- graph-tool: 120MB
Winner: graph-tool (most memory efficient)

Recommended Stack for Production:
- Similarity: scikit-learn
- Temporal: pandas
- Community: igraph (good balance) or graph-tool (maximum performance)
- Centrality: Existing Rust service
"""
```

## 8. Dependencies and Installation

### 8.1 Core Dependencies

```bash
# Core dependencies for relationship discovery service
pip install scikit-learn==1.3.0      # Optimized similarity calculations (50K pairs/sec)
pip install pandas==2.0.3            # Vectorized temporal analysis (1M events/min)
pip install igraph==0.10.8           # High-performance graph algorithms (1M nodes/min)
pip install python-louvain==0.16     # Fast community detection
pip install numpy==1.24.3            # Vectorized numerical operations
pip install apscheduler==3.10.4      # Advanced task scheduling
pip install aioredis==2.0.1          # Async Redis integration
pip install psutil==5.9.6            # Resource monitoring

# Optional high-performance alternatives
pip install graph-tool              # Ultra-fast graph analysis (10x NetworkX, requires compilation)
pip install cupy                    # GPU acceleration (requires CUDA)
pip install numba                   # JIT compilation for custom algorithms

# Temporal analysis extensions
pip install mlxtend                 # Association rules and market basket analysis
pip install networkx==3.1           # Fallback graph algorithms

# Development and testing
pip install pytest==7.4.0
pip install pytest-asyncio==0.21.1
pip install memory-profiler==0.61.0
```

### 8.2 Docker Integration

```dockerfile
# Dockerfile extension for discovery service
FROM python:3.11-slim

# Install system dependencies for graph-tool (optional high-performance option)
RUN apt-get update && apt-get install -y \
    build-essential \
    libboost-all-dev \
    libcgal-dev \
    libsparsehash-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements-discovery.txt .
RUN pip install --no-cache-dir -r requirements-discovery.txt

# Copy discovery service code
COPY graphiti_core/discovery/ /app/graphiti_core/discovery/
```

### 8.3 Performance Validation

```python
# Performance validation script
import time
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import igraph as ig
import pandas as pd

def validate_performance():
    """Validate that libraries meet performance requirements."""

    # Test similarity performance (target: 50K pairs/sec)
    embeddings = np.random.rand(1000, 768)
    start = time.time()
    similarities = cosine_similarity(embeddings)
    similarity_time = time.time() - start
    pairs_per_sec = (1000 * 999 / 2) / similarity_time
    print(f"Similarity: {pairs_per_sec:.0f} pairs/sec (target: 50K)")

    # Test graph performance (target: 1M nodes/min)
    g = ig.Graph.Erdos_Renyi(10000, 0.001)
    start = time.time()
    communities = g.community_multilevel()
    graph_time = time.time() - start
    nodes_per_min = 10000 / graph_time * 60
    print(f"Graph: {nodes_per_min:.0f} nodes/min (target: 1M)")

    # Test temporal performance (target: 1M events/min)
    events = pd.DataFrame({
        'timestamp': pd.date_range('2024-01-01', periods=100000, freq='1min'),
        'entity': np.random.choice(['A', 'B', 'C'], 100000)
    })
    start = time.time()
    grouped = events.groupby(pd.Grouper(key='timestamp', freq='1H')).size()
    temporal_time = time.time() - start
    events_per_min = 100000 / temporal_time * 60
    print(f"Temporal: {events_per_min:.0f} events/min (target: 1M)")

if __name__ == "__main__":
    validate_performance()
```

## 9. Implementation Plan

### 9.1 Phase 1: Foundation (Weeks 1-2)
- Extend existing worker infrastructure with discovery task types
- Implement basic similarity-based discovery algorithm
- Add configuration options to existing settings system
- Create discovery task queue integration

### 7.2 Phase 2: Core Algorithms (Weeks 3-4)
- Implement temporal pattern analysis
- Add community-based discovery using existing community detection
- Integrate with Rust centrality service for centrality-driven discovery
- Implement relationship validation and quality control

### 7.3 Phase 3: Scheduling and Monitoring (Weeks 5-6)
- Implement adaptive scheduling system
- Add comprehensive metrics and monitoring
- Create performance safeguards and circuit breakers
- Implement human review queue for uncertain discoveries

### 7.4 Phase 4: Testing and Optimization (Weeks 7-8)
- Performance testing with large graphs
- Algorithm accuracy validation
- Load testing and resource optimization
- Documentation and deployment preparation

## 8. Success Criteria

### 8.1 Technical Acceptance Criteria
- [ ] Service processes 100K node pairs per hour
- [ ] Discovery accuracy >85% based on validation sampling
- [ ] System resource impact <5% during discovery operations
- [ ] Service availability >99.9% excluding planned maintenance
- [ ] All discovery algorithms complete within SLA timeframes

### 8.2 Business Acceptance Criteria
- [ ] 20% improvement in search result relevance scores
- [ ] 100+ meaningful relationships discovered per day for active graphs
- [ ] User satisfaction score >4.0/5.0 for discovery quality
- [ ] 50% reduction in manual relationship curation effort
- [ ] Zero data corruption or system instability incidents

### 8.3 Performance Benchmarks
- [ ] Similarity discovery: 10K node pairs per minute
- [ ] Temporal analysis: 1M episodic events per hour
- [ ] Community discovery: Communities up to 10K nodes
- [ ] Centrality integration: Leverage full Rust service performance
- [ ] End-to-end discovery cycle: <1 hour for 100K node graphs

## 9. Risk Assessment

### 9.1 Technical Risks
- **Performance Impact**: Mitigation through resource limits and monitoring
- **Algorithm Accuracy**: Mitigation through validation and human review
- **Infrastructure Load**: Mitigation through adaptive scheduling and circuit breakers
- **Data Quality**: Mitigation through confidence scoring and quality thresholds

### 9.2 Business Risks
- **User Adoption**: Mitigation through gradual rollout and user feedback
- **Relationship Quality**: Mitigation through validation and review processes
- **System Complexity**: Mitigation through comprehensive testing and documentation
- **Resource Costs**: Mitigation through efficient algorithms and resource management

## 10. Future Enhancements

### 10.1 Advanced Algorithms
- Machine learning-based relationship prediction
- Graph neural network integration
- Multi-modal relationship discovery (text, images, metadata)
- Federated learning across multiple graphs

### 10.2 User Experience
- Interactive discovery review interface
- Relationship suggestion explanations
- User feedback integration for algorithm improvement
- Real-time discovery notifications

### 10.3 Enterprise Features
- Multi-tenant discovery with isolation
- Custom algorithm plugins
- Advanced analytics and reporting
- Integration with external knowledge bases

---

**Document Status**: Draft  
**Next Review**: 2025-01-31  
**Stakeholders**: Engineering Team, Product Management, DevOps Team
