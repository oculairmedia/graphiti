# Product Requirements Document: Graphiti Memory System Enhancement

**Version:** 1.0  
**Date:** January 2025  
**Status:** Draft  
**Authors:** Graphiti Core Team  

## 1. Executive Summary

### 1.1 Product Vision
Transform Graphiti from a static knowledge graph into a dynamic, adaptive memory system that mimics human cognitive processes through implementation of state-of-the-art memory decay algorithms, importance scoring, and progressive consolidation mechanisms.

### 1.2 Business Objectives
- **Improve Retrieval Relevance**: Achieve 75% improvement in retrieval quality metrics
- **Scale Efficiently**: Support 10M+ node graphs with sub-second query response
- **Reduce Noise**: Automatically filter irrelevant/outdated information through decay
- **Enable Adaptive Learning**: System learns from usage patterns to optimize retrieval

### 1.3 Success Metrics
- Precision@10: ≥ 0.74 (from baseline 0.42)
- Query latency P99: < 100ms for 1M node graphs
- Memory efficiency: 85% reduction in RAM usage through sparse matrices
- User satisfaction: 80% improvement in relevance ratings

## 2. Product Overview

### 2.1 Problem Statement

Current Limitations:
- **Information Overload**: All memories persist indefinitely with equal weight
- **No Prioritization**: Critical knowledge is indistinguishable from trivial facts
- **Static Retrieval**: Search doesn't adapt to user patterns or context
- **Memory Bloat**: Graph grows unbounded without natural forgetting
- **Limited Abstraction**: No progressive consolidation of knowledge

### 2.2 Solution Overview

The Graphiti Memory System introduces:
1. **FSRS-6 Memory Decay**: Scientific forgetting curves based on 1.7B real-world reviews
2. **PageRank Importance Scoring**: Identify and preserve critical knowledge nodes
3. **Progressive Consolidation**: Form abstract concepts from concrete memories
4. **Adaptive Retrieval**: Dynamic search strategies based on query patterns
5. **Dormant Memory Reactivation**: Surface forgotten but relevant knowledge

### 2.3 Target Users

**Primary Users:**
- AI/ML Engineers building conversational agents
- Knowledge management systems developers
- Research teams needing persistent context
- Enterprise search and discovery platforms

**Secondary Users:**
- Educational technology platforms
- Personal knowledge management tools
- Healthcare systems for patient history
- Legal research and case law systems

## 3. User Stories and Use Cases

### 3.1 User Stories

**As an AI Engineer:**
- I want my agent to forget irrelevant details while preserving important facts
- I want retrieval to prioritize frequently accessed and central knowledge
- I want the system to form abstract concepts from repeated patterns

**As a Knowledge Worker:**
- I want search results ranked by importance and recency
- I want dormant but relevant memories to surface when needed
- I want the system to learn from my access patterns

**As a System Administrator:**
- I want efficient memory usage that scales with graph size
- I want configurable decay and consolidation parameters
- I want monitoring of memory health and performance

### 3.2 Use Cases

#### UC1: Conversational Agent Memory
**Actor**: AI Developer  
**Precondition**: Agent has accumulated 100K+ conversation memories  
**Flow**:
1. User queries agent about past conversation
2. System applies memory decay to filter old/irrelevant memories
3. PageRank identifies important conversation threads
4. Adaptive search selects optimal retrieval strategy
5. Agent responds with relevant, prioritized information

**Success Criteria**: 
- Response includes most relevant memories
- Irrelevant details are filtered out
- Response time < 100ms

#### UC2: Research Knowledge Consolidation
**Actor**: Research Scientist  
**Precondition**: System contains 10K+ research paper summaries  
**Flow**:
1. System identifies stable memory clusters (papers on similar topics)
2. Progressive consolidation creates abstract concept nodes
3. Hierarchical structure preserves details while providing overview
4. Scientist queries high-level concept
5. System returns consolidated knowledge with drill-down capability

**Success Criteria**:
- Abstract summaries accurately represent paper clusters
- Original details remain accessible
- Consolidation reduces search space by 70%

#### UC3: Adaptive Learning from Usage
**Actor**: Knowledge Worker  
**Precondition**: System has 30 days of query history  
**Flow**:
1. User issues query similar to past searches
2. System recognizes query pattern
3. Adaptive strategy selector chooses optimal search method
4. Results are reranked based on user's access patterns
5. System updates strategy performance metrics

**Success Criteria**:
- Repeated queries show improved relevance
- Search adapts to user's domain focus
- Query performance improves over time

## 4. Functional Requirements

### 4.1 Memory Decay System

**FR1.1**: System SHALL implement FSRS-6 algorithm with 17 configurable parameters  
**FR1.2**: System SHALL calculate retrievability for each node/edge based on:
- Time since last access
- Stability (resistance to forgetting)
- Difficulty (inherent complexity)
- Review history

**FR1.3**: System SHALL update decay values:
- Automatically via background tasks (configurable frequency)
- On-demand during search operations
- Batch updates for efficiency

**FR1.4**: System SHALL support custom decay functions allowing:
- Domain-specific decay curves
- Integration with external factors
- A/B testing of decay strategies

### 4.2 Importance Scoring

**FR2.1**: System SHALL calculate PageRank scores for all nodes with:
- Configurable damping factor (default 0.85)
- Convergence threshold (default 1e-6)
- Maximum iterations (default 100)

**FR2.2**: System SHALL support additional centrality metrics:
- Betweenness centrality
- Closeness centrality
- Eigenvector centrality
- Clustering coefficient

**FR2.3**: System SHALL weight search results by importance:
- Combine relevance and importance scores
- Configurable importance weight (0-1)
- Override capability for specific queries

### 4.3 Progressive Consolidation

**FR3.1**: System SHALL identify consolidation candidates based on:
- Minimum stability threshold (configurable, default 7 days)
- Semantic coherence threshold (default 0.7)
- Minimum cluster size (default 5 nodes)

**FR3.2**: System SHALL create hierarchical community structures:
- Multiple consolidation levels (default max 3)
- Preserve original memories as children
- Generate abstract summaries via LLM

**FR3.3**: System SHALL maintain bidirectional links:
- Parent communities link to members
- Members reference parent community
- Navigation between abstraction levels

### 4.4 Adaptive Search

**FR4.1**: System SHALL classify queries into types:
- Temporal (time-based queries)
- Conceptual (abstract concepts)
- Factual (specific facts)
- Exploratory (broad discovery)

**FR4.2**: System SHALL select search strategies based on:
- Query classification
- Historical performance data
- Current graph statistics
- User preferences

**FR4.3**: System SHALL track strategy performance:
- Response time per strategy
- Relevance metrics (precision, recall)
- User feedback signals
- Continuous optimization

### 4.5 Dormant Memory Reactivation

**FR5.1**: System SHALL identify dormant memories:
- Retrievability below threshold (default 0.3)
- No recent access (configurable period)
- Potential relevance to current context

**FR5.2**: System SHALL reactivate relevant memories:
- Boost retrievability scores
- Update last_accessed timestamp
- Track reactivation success

**FR5.3**: System SHALL prevent thrashing:
- Limit reactivations per time period
- Minimum dormancy period before reactivation
- Reactivation cooldown period

## 5. Non-Functional Requirements

### 5.1 Performance Requirements

**NFR1.1**: Query latency SHALL NOT exceed:
- P50: 20ms for 100K nodes
- P95: 50ms for 100K nodes
- P99: 100ms for 1M nodes

**NFR1.2**: Background task performance:
- Decay update: < 1 second per 10K nodes
- PageRank calculation: < 10 seconds for 1M nodes
- Consolidation: < 30 seconds for 10K candidates

**NFR1.3**: Memory usage SHALL NOT exceed:
- 100MB per 10K nodes (with sparse matrices)
- 1GB per 100K nodes
- 15GB per 1M nodes

### 5.2 Scalability Requirements

**NFR2.1**: System SHALL support graphs up to:
- 10M nodes in production
- 50M edges
- 1M communities

**NFR2.2**: System SHALL scale horizontally:
- Sharding by group_id
- Distributed PageRank computation
- Parallel decay calculations

### 5.3 Reliability Requirements

**NFR3.1**: System availability: 99.9% uptime  
**NFR3.2**: Data durability: No data loss on system failure  
**NFR3.3**: Graceful degradation: Core search works if memory features fail

### 5.4 Security Requirements

**NFR4.1**: Memory metrics SHALL be encrypted at rest  
**NFR4.2**: Access patterns SHALL NOT leak private information  
**NFR4.3**: Consolidation SHALL preserve access controls

### 5.5 Maintainability Requirements

**NFR5.1**: Configuration changes without restart  
**NFR5.2**: Comprehensive metrics and monitoring  
**NFR5.3**: Backward compatibility with existing graphs

## 6. Technical Architecture

### 6.1 System Architecture

```
┌────────────────────────────────────────────────────────┐
│                    Client Applications                   │
│         (Agents, Search Systems, Knowledge Tools)        │
└────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                      API Gateway                         │
│              (REST / GraphQL / WebSocket)                │
└────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                  Memory Management Layer                 │
├──────────────┬──────────────┬──────────────────────────┤
│   FSRS-6     │   PageRank   │    Consolidation         │
│   Engine     │   Scorer     │      Manager             │
├──────────────┼──────────────┼──────────────────────────┤
│  Adaptive    │   Dormant    │     Sparse Matrix        │
│  Search      │   Memory     │       Cache              │
└──────────────┴──────────────┴──────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                   Graph Operations Layer                 │
├──────────────┬──────────────┬──────────────────────────┤
│   Search     │  Community   │      Embeddings          │
│   Engine     │  Detection   │       Service            │
└──────────────┴──────────────┴──────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                    Storage Layer                         │
├──────────────┬──────────────┬──────────────────────────┤
│   Neo4j      │   FalkorDB   │      Redis               │
│   (Primary)  │  (Secondary) │     (Cache)              │
└──────────────┴──────────────┴──────────────────────────┘
```

### 6.2 Data Flow Architecture

```
Query Flow:
User Query → Query Classifier → Strategy Selector → 
Search Executor → Memory Reranker → Result Aggregator → Response

Update Flow:
New Episode → Node Extraction → Edge Extraction → 
Memory Initialization → Importance Calculation → Storage

Maintenance Flow:
Timer Trigger → Decay Calculator → PageRank Updater → 
Consolidation Manager → Cache Refresher → Metrics Logger
```

### 6.3 Component Specifications

#### Memory Metrics Service
- **Responsibility**: Calculate and update memory decay values
- **Interface**: Async Python API
- **Dependencies**: FSRS-6 library, Graph DB
- **Performance**: 10K nodes/second update rate

#### PageRank Service
- **Responsibility**: Calculate node importance scores
- **Interface**: GraphDB stored procedures
- **Dependencies**: Sparse matrix library
- **Performance**: O(n*k) where k = iterations

#### Consolidation Service
- **Responsibility**: Progressive memory abstraction
- **Interface**: Background task queue
- **Dependencies**: LLM client, Embedder
- **Performance**: 100 consolidations/minute

## 7. API Specifications

### 7.1 Memory Management APIs

```python
# Initialize memory-aware system
POST /api/v1/memory/initialize
{
    "group_id": "string",
    "fsrs_params": {...},
    "enable_pagerank": boolean,
    "enable_consolidation": boolean
}

# Update memory metrics
POST /api/v1/memory/review
{
    "node_uuid": "string",
    "rating": "AGAIN|HARD|GOOD|EASY",
    "timestamp": "ISO8601"
}

# Get memory statistics
GET /api/v1/memory/stats/{group_id}
Response:
{
    "total_nodes": integer,
    "average_retrievability": float,
    "dormant_ratio": float,
    "consolidation_levels": {...}
}
```

### 7.2 Search APIs

```python
# Memory-aware search
POST /api/v1/search/memory-aware
{
    "query": "string",
    "group_ids": ["string"],
    "use_decay": boolean,
    "boost_important": boolean,
    "include_dormant": boolean,
    "strategy": "auto|semantic|structural|temporal"
}

# Reactivate dormant memories
POST /api/v1/memory/reactivate
{
    "context": "string",
    "threshold": float,
    "max_nodes": integer
}
```

### 7.3 Maintenance APIs

```python
# Trigger decay update
POST /api/v1/maintenance/decay
{
    "group_ids": ["string"],
    "batch_size": integer
}

# Trigger consolidation
POST /api/v1/maintenance/consolidate
{
    "group_ids": ["string"],
    "threshold_days": integer,
    "min_cluster_size": integer
}

# Update PageRank scores
POST /api/v1/maintenance/pagerank
{
    "group_ids": ["string"],
    "damping_factor": float,
    "max_iterations": integer
}
```

## 8. Success Metrics and KPIs

### 8.1 Quality Metrics

| Metric | Baseline | Target | Measurement Method |
|--------|----------|--------|-------------------|
| Precision@10 | 0.42 | 0.74 | A/B testing on query set |
| Recall@10 | 0.38 | 0.69 | Test dataset evaluation |
| F1 Score | 0.40 | 0.71 | Harmonic mean of P&R |
| MRR | 0.45 | 0.78 | Reciprocal rank analysis |
| NDCG@10 | 0.48 | 0.81 | Graded relevance scores |

### 8.2 Performance Metrics

| Metric | Target | Critical Threshold | Measurement |
|--------|--------|-------------------|-------------|
| Query Latency P50 | 20ms | 50ms | APM monitoring |
| Query Latency P99 | 100ms | 200ms | APM monitoring |
| Decay Update Time | 1s/10K nodes | 5s/10K nodes | Background job metrics |
| Memory Usage | 100MB/10K nodes | 200MB/10K nodes | System monitoring |

### 8.3 Business Metrics

| Metric | Target | Measurement Period | Method |
|--------|--------|-------------------|--------|
| User Satisfaction | +80% | Quarterly | User surveys |
| Query Volume | +50% | Monthly | Usage analytics |
| System Adoption | 100 deployments | 6 months | Customer tracking |
| Support Tickets | -40% | Monthly | Ticket system |

## 9. Risk Assessment

### 9.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Performance degradation at scale | Medium | High | Implement caching, use sparse matrices |
| Memory calculation overhead | Medium | Medium | Background processing, batch updates |
| Consolidation quality issues | Low | Medium | Human-in-the-loop validation |
| Backward compatibility breaks | Low | High | Migration tools, versioning |

### 9.2 Business Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| User resistance to forgetting | Medium | Medium | Education, configurable parameters |
| Integration complexity | High | Medium | Comprehensive documentation, support |
| Competitive alternatives | Medium | High | Continuous innovation, benchmarking |

### 9.3 Operational Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Increased operational complexity | High | Medium | Automation, monitoring tools |
| Data loss during consolidation | Low | High | Versioning, rollback capability |
| Resource consumption spikes | Medium | Medium | Rate limiting, resource quotas |

## 10. Implementation Timeline

### Phase 1: Foundation (Weeks 1-2)
- [ ] Week 1: Core FSRS-6 implementation
  - Memory metrics data model
  - Basic decay calculations
  - Storage schema updates
  
- [ ] Week 2: PageRank integration
  - Graph analysis implementation
  - Importance score storage
  - Initial scoring run

**Deliverables**: Working memory decay system with importance scoring

### Phase 2: Core Features (Weeks 3-4)
- [ ] Week 3: Search integration
  - Memory-aware reranking
  - Decay factor in scoring
  - Importance boosting
  
- [ ] Week 4: Adaptive search
  - Query classification
  - Strategy selection
  - Performance tracking

**Deliverables**: Memory-aware search with adaptive strategies

### Phase 3: Advanced Features (Weeks 5-6)
- [ ] Week 5: Progressive consolidation
  - Cluster identification
  - LLM summarization
  - Hierarchy creation
  
- [ ] Week 6: Dormant memory
  - Identification algorithm
  - Reactivation logic
  - Thrashing prevention

**Deliverables**: Full consolidation and reactivation system

### Phase 4: Optimization (Weeks 7-8)
- [ ] Week 7: Performance optimization
  - Sparse matrix implementation
  - Caching layer
  - Batch processing
  
- [ ] Week 8: Production readiness
  - Monitoring setup
  - Documentation
  - Migration tools

**Deliverables**: Production-ready system with full documentation

### Phase 5: Deployment (Weeks 9-10)
- [ ] Week 9: Beta deployment
  - Selected customer rollout
  - Performance monitoring
  - Feedback collection
  
- [ ] Week 10: General availability
  - Full rollout
  - Support documentation
  - Training materials

**Deliverables**: GA release with support infrastructure

## 11. Acceptance Criteria

### 11.1 Feature Acceptance

**Memory Decay**
- [ ] FSRS-6 calculations match reference implementation ±0.1%
- [ ] Decay updates complete within SLA for 1M nodes
- [ ] Retrievability values properly bounded [0, 1]

**PageRank Scoring**
- [ ] Convergence within 100 iterations for 99% of graphs
- [ ] Scores sum to 1.0 (normalized)
- [ ] Updates complete within 10 seconds for 1M nodes

**Progressive Consolidation**
- [ ] Semantic coherence > 0.7 for all communities
- [ ] Information preservation > 80%
- [ ] Hierarchy navigable bidirectionally

**Adaptive Search**
- [ ] Strategy selection improves relevance by >20%
- [ ] Query classification accuracy > 85%
- [ ] Performance tracking operational

### 11.2 Performance Acceptance

- [ ] Query latency P99 < 100ms (1M nodes)
- [ ] Memory usage < 15GB (1M nodes)
- [ ] Background tasks non-blocking
- [ ] No degradation of existing features

### 11.3 Quality Acceptance

- [ ] Test coverage > 90%
- [ ] Documentation complete
- [ ] All APIs backward compatible
- [ ] Migration tools tested

## 12. Dependencies

### 12.1 Technical Dependencies
- Neo4j 5.26+ or FalkorDB 1.1.2+
- Python 3.11+
- NumPy, SciPy for matrix operations
- LLM API (OpenAI, Anthropic, etc.)
- Redis for caching (optional)

### 12.2 Team Dependencies
- ML Engineering: FSRS-6 implementation
- Backend Engineering: API development
- DevOps: Infrastructure scaling
- Product: Feature prioritization
- QA: Test planning and execution

### 12.3 External Dependencies
- Customer feedback for beta testing
- Academic review of algorithms
- Performance benchmarking datasets

## 13. Open Questions

1. **Decay Parameters**: Should decay rates be user-configurable or system-optimized?
2. **Consolidation Triggers**: Manual vs automatic consolidation?
3. **Privacy**: How to handle memory decay for compliance (GDPR right to be forgotten)?
4. **Pricing**: How to price memory features (storage vs compute)?
5. **Migration**: Forced migration vs opt-in for existing customers?

## 14. Appendices

### Appendix A: Glossary

- **FSRS-6**: Free Spaced Repetition Scheduler, version 6
- **Retrievability**: Probability of successful memory recall
- **Stability**: Resistance to forgetting over time
- **Consolidation**: Process of forming abstract memories from concrete ones
- **Dormant Memory**: Low-retrievability memory that may still be relevant
- **PageRank**: Algorithm for measuring node importance in a graph

### Appendix B: References

1. Ye et al. (2024). "A Stochastic Shortest Path Algorithm for Optimizing Spaced Repetition Scheduling"
2. Page et al. (1999). "The PageRank Citation Ranking: Bringing Order to the Web"
3. McClelland et al. (1995). "Why there are complementary learning systems"
4. Lewis et al. (2020). "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"

### Appendix C: Competitive Analysis

| Feature | Graphiti + Memory | Pinecone | Weaviate | Qdrant |
|---------|------------------|----------|----------|--------|
| Memory Decay | ✓ (FSRS-6) | ✗ | ✗ | ✗ |
| Importance Scoring | ✓ (PageRank) | ✗ | ✗ | ✗ |
| Progressive Consolidation | ✓ | ✗ | ✗ | ✗ |
| Adaptive Search | ✓ | Partial | ✗ | ✗ |
| Graph Structure | ✓ | ✗ | Partial | ✗ |
| Temporal Awareness | ✓ | ✗ | ✓ | ✗ |

### Appendix D: Configuration Schema

```yaml
memory_config:
  fsrs:
    enabled: boolean
    parameters: array[17] | "optimal"
    initial_stability: float
    initial_difficulty: float
    
  importance:
    algorithm: "pagerank" | "hits" | "betweenness"
    update_frequency: "hourly" | "daily" | "weekly"
    damping_factor: float
    
  consolidation:
    enabled: boolean
    auto_trigger: boolean
    threshold_days: integer
    min_cluster_size: integer
    max_levels: integer
    
  search:
    adaptive: boolean
    use_decay: boolean
    boost_important: boolean
    include_dormant: boolean
    dormant_threshold: float
```

## Document Approval

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Product Manager | | | |
| Engineering Lead | | | |
| ML Lead | | | |
| QA Lead | | | |
| Customer Success | | | |

---

*This PRD is a living document and will be updated as requirements evolve and new insights are gained during implementation.*