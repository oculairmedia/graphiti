# Product Requirements Document: FalkorDB Edge Sync Optimization

## Executive Summary

### Problem Statement
The FalkorDB→Neo4j sync service currently fails to process large edge datasets due to memory-intensive graph traversal queries that hit FalkorDB's RESULTSET_SIZE limits. The service stops at 5,000 relationships out of 43,495 total edges, representing an 88% data loss.

### Solution Overview
Implement an elegant "Direct Edge Access Pattern" that reduces query complexity by 60-70%, eliminates complex graph traversals, and enables reliable processing of large edge datasets within FalkorDB's constraints.

## 1. Background & Context

### Current Architecture
- **Service**: `graphiti-sync-service-1` handles FalkorDB→Neo4j synchronization
- **Dataset Scale**: 17,214 nodes, 43,495 edges in production
- **Current Limitation**: Stops at 5,000 edges due to RESULTSET_SIZE constraints
- **Impact**: Critical data loss affecting graph completeness

### Technical Context
- **FalkorDB RESULTSET_SIZE**: 20,000 (recently increased from default)
- **Query Memory Limit**: 128MB per query (QUERY_MEM_CAPACITY)
- **Current Query Pattern**: Complex `MATCH (source)-[r:RELATES_TO]->(target)` traversal
- **Memory Usage**: ~45-75MB for 15K edge queries (3-5KB per edge)

## 2. Requirements

### 2.1 Functional Requirements

#### FR1: Complete Edge Extraction
- **Requirement**: Process all 43,495+ edges without data loss
- **Acceptance Criteria**:
  - Zero failed extractions due to RESULTSET_SIZE limits
  - Complete data integrity between FalkorDB and Neo4j
  - Support for datasets up to 100K+ edges

#### FR2: Query Optimization
- **Requirement**: Reduce memory footprint per edge query by 60-70%
- **Acceptance Criteria**:
  - Memory usage ≤25MB for 15K edge batches
  - Query execution time reduced by 50%+
  - No complex graph traversal patterns

#### FR3: Adaptive Batch Sizing
- **Requirement**: Implement intelligent batch sizing based on data type
- **Acceptance Criteria**:
  - Edge batches: 8,000 records max
  - Node batches: 15,000 records max
  - Dynamic adjustment based on memory usage

#### FR4: Backwards Compatibility
- **Requirement**: Maintain compatibility with existing sync architecture
- **Acceptance Criteria**:
  - No breaking changes to API contracts
  - Existing configuration parameters respected
  - Fallback to legacy extraction if needed

### 2.2 Non-Functional Requirements

#### NFR1: Performance
- **Target**: 2-3x faster edge extraction
- **Metric**: Query execution time ≤5 seconds per batch
- **Constraint**: Stay within 128MB query memory limit

#### NFR2: Reliability
- **Target**: 99.9% successful edge extraction rate
- **Metric**: Zero timeouts or memory-related failures
- **Constraint**: Graceful degradation under load

#### NFR3: Scalability
- **Target**: Support 500K+ edges without architectural changes
- **Metric**: Linear performance scaling with dataset size
- **Constraint**: Memory usage growth ≤O(log n)

#### NFR4: Maintainability
- **Target**: Clear, documented optimization patterns
- **Metric**: Code complexity reduction by 30%
- **Constraint**: Single responsibility principle adherence

## 3. Solution Architecture

### 3.1 Core Innovation: Direct Edge Access Pattern

#### Current Query (Problematic)
```cypher
MATCH (source)-[r:RELATES_TO]->(target)
RETURN r.uuid, source.uuid, target.uuid, properties(r)
ORDER BY r.uuid SKIP 0 LIMIT 15000
```
**Issues**: Complex traversal, excessive data retrieval, memory overhead

#### Optimized Query (Solution)
```cypher
MATCH ()-[r:RELATES_TO]->()
RETURN r.uuid, r.source_uuid, r.target_uuid,
       r.created_at, r.updated_at, r.weight, r.valid_at, r.invalid_at
ORDER BY r.uuid SKIP 0 LIMIT 8000
```
**Benefits**: Direct access, selective properties, reduced memory

### 3.2 Technical Architecture

#### Component Overview
```
┌─────────────────────────────────────────────────────────┐
│                 FalkorDB Extractor                      │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────────────────────┐│
│  │ Query Optimizer │  │     Adaptive Batch Manager     ││
│  │                 │  │                                 ││
│  │ • Direct Access │  │ • Edge Batches: 8K max         ││
│  │ • Selective     │  │ • Node Batches: 15K max        ││
│  │   Properties    │  │ • Memory Monitoring             ││
│  │ • Memory        │  │ • Dynamic Adjustment            ││
│  │   Efficient     │  │                                 ││
│  └─────────────────┘  └─────────────────────────────────┘│
├─────────────────────────────────────────────────────────┤
│                 Result Processor                        │
│                                                         │
│ • Minimal Memory Allocation                             │
│ • Streamlined Data Conversion                           │
│ • Efficient Batching                                    │
└─────────────────────────────────────────────────────────┘
```

#### Data Flow
```
FalkorDB → Direct Edge Query → Selective Properties → Batch Processing → Neo4j
   ↓              ↓                    ↓                  ↓            ↓
43K edges → 8K batches → Essential fields → Memory efficient → Complete sync
```

## 4. Implementation Plan

### 4.1 Phase 1: Query Pattern Optimization (Week 1)

#### Tasks
1. **Implement Direct Edge Access**
   - Replace complex `MATCH (source)-[r]->(target)` with `MATCH ()-[r]->()`
   - Estimate: 2 days
   - Owner: Backend Team

2. **Selective Property Extraction**
   - Replace `properties(r)` with explicit field selection
   - Define essential edge properties list
   - Estimate: 1 day
   - Owner: Backend Team

3. **Memory Profiling**
   - Benchmark current vs optimized query memory usage
   - Validate 60-70% reduction target
   - Estimate: 1 day
   - Owner: Backend Team

#### Deliverables
- Optimized query implementation
- Memory usage comparison report
- Performance benchmarks

### 4.2 Phase 2: Adaptive Batch Management (Week 2)

#### Tasks
1. **Batch Size Calculator**
   - Implement dynamic batch sizing logic
   - Edge vs node optimization
   - Estimate: 2 days
   - Owner: Backend Team

2. **Memory Monitoring**
   - Add real-time memory usage tracking
   - Implement adaptive limits
   - Estimate: 2 days
   - Owner: Backend Team

3. **Configuration Updates**
   - Add new batch size parameters
   - Maintain backwards compatibility
   - Estimate: 1 day
   - Owner: Backend Team

#### Deliverables
- Adaptive batch manager
- Configuration schema updates
- Memory monitoring dashboard

### 4.3 Phase 3: Integration & Testing (Week 3)

#### Tasks
1. **Integration Testing**
   - Test with full 43K edge dataset
   - Validate complete extraction
   - Estimate: 2 days
   - Owner: QA Team

2. **Performance Testing**
   - Load testing with larger datasets
   - Memory leak detection
   - Estimate: 2 days
   - Owner: QA Team

3. **Regression Testing**
   - Ensure no breaking changes
   - Test with various data configurations
   - Estimate: 1 day
   - Owner: QA Team

#### Deliverables
- Test execution report
- Performance benchmarks
- Regression test suite

### 4.4 Phase 4: Deployment & Monitoring (Week 4)

#### Tasks
1. **Production Deployment**
   - Staged rollout with monitoring
   - Rollback plan preparation
   - Estimate: 1 day
   - Owner: DevOps Team

2. **Monitoring Setup**
   - Metrics collection for new patterns
   - Alert configuration
   - Estimate: 1 day
   - Owner: DevOps Team

3. **Documentation**
   - Technical documentation
   - Operational runbooks
   - Estimate: 1 day
   - Owner: Technical Writing Team

#### Deliverables
- Production deployment
- Monitoring dashboards
- Complete documentation

## 5. Technical Specifications

### 5.1 API Contracts

#### Edge Extraction Method Signature
```python
async def extract_entity_edges_optimized(
    self,
    since_timestamp: Optional[datetime] = None,
    batch_size: Optional[int] = None
) -> AsyncIterator[List[Dict[str, Any]]]
```

#### Essential Edge Properties
```python
ESSENTIAL_EDGE_PROPERTIES = [
    'uuid',           # Primary identifier
    'source_uuid',    # Source node reference
    'target_uuid',    # Target node reference
    'created_at',     # Creation timestamp
    'updated_at',     # Modification timestamp
    'weight',         # Relationship weight
    'valid_at',       # Validity start time
    'invalid_at'      # Validity end time
]
```

### 5.2 Configuration Schema

#### New Configuration Parameters
```yaml
sync:
  # Existing parameters maintained
  max_query_limit: 15000
  enable_query_pagination: true

  # New optimization parameters
  optimization:
    enabled: true
    edge_batch_size: 8000      # Conservative edge batch limit
    node_batch_size: 15000     # Standard node batch limit
    memory_threshold_mb: 100   # Memory usage alert threshold
    adaptive_sizing: true      # Enable dynamic batch adjustment
```

### 5.3 Performance Targets

#### Memory Usage
- **Current**: 45-75MB per 15K edge batch
- **Target**: 15-25MB per 8K edge batch
- **Improvement**: 60-70% reduction

#### Query Performance
- **Current**: 8-12 seconds per batch
- **Target**: 3-5 seconds per batch
- **Improvement**: 50%+ faster execution

#### Throughput
- **Current**: ~1,250 edges/second
- **Target**: ~2,500 edges/second
- **Improvement**: 2x throughput increase

## 6. Risk Analysis & Mitigation

### 6.1 Technical Risks

#### Risk: Query Optimization Introduces Bugs
- **Probability**: Medium
- **Impact**: High
- **Mitigation**: Comprehensive regression testing, staged rollout

#### Risk: Edge Properties Schema Changes
- **Probability**: Low
- **Impact**: Medium
- **Mitigation**: Explicit property mapping, backwards compatibility testing

#### Risk: Performance Regression in Other Areas
- **Probability**: Low
- **Impact**: Medium
- **Mitigation**: Full performance benchmark suite, rollback capability

### 6.2 Operational Risks

#### Risk: Production Deployment Issues
- **Probability**: Medium
- **Impact**: High
- **Mitigation**: Blue-green deployment, automated rollback triggers

#### Risk: Monitoring Blind Spots
- **Probability**: Medium
- **Impact**: Medium
- **Mitigation**: Comprehensive metrics collection, alerting setup

## 7. Success Metrics

### 7.1 Primary KPIs

#### Data Completeness
- **Metric**: Percentage of edges successfully extracted
- **Current**: 11.5% (5K/43.5K)
- **Target**: 100%

#### Performance Improvement
- **Metric**: Query execution time reduction
- **Current**: 8-12 seconds per batch
- **Target**: 3-5 seconds per batch

#### Memory Efficiency
- **Metric**: Memory usage per edge
- **Current**: 3-5KB per edge
- **Target**: 1-1.5KB per edge

### 7.2 Secondary KPIs

#### System Reliability
- **Metric**: Successful extraction rate
- **Target**: 99.9%

#### Scalability
- **Metric**: Maximum supported edge count
- **Current**: 5K (hard limit)
- **Target**: 100K+ (linear scaling)

## 8. Conclusion

This optimization project represents a critical improvement to the Graphiti sync service architecture. By implementing the Direct Edge Access Pattern, we can:

1. **Eliminate data loss** currently affecting 88% of edge relationships
2. **Improve performance** by 2-3x through query optimization
3. **Enable scalability** for datasets 10-20x larger than current limits
4. **Maintain reliability** with robust error handling and monitoring

The proposed solution addresses the root cause through elegant query optimization rather than configuration workarounds, creating a foundation for future growth and ensuring data integrity across the entire graph ecosystem.

---

**Document Version**: 1.0
**Last Updated**: Current
**Author**: Technical Team
**Approvers**: Product Team, Engineering Team
**Next Review**: Post-implementation (4 weeks)