# Edge Validation and Ordering PRD

## Problem Statement

The Graphiti visualization system experiences "Edge references unknown nodes" warnings when processing real-time delta updates via WebSocket. This occurs when edges arrive before their corresponding nodes in the delta stream, causing data consistency issues in the frontend graph visualization.

### Root Cause Analysis

1. **Asynchronous Processing**: The Rust backend processes nodes and edges concurrently in the same transaction but doesn't guarantee ordering in delta broadcasts
2. **Queue Processing Order**: The `DuckDBStore::process_updates()` method processes nodes first, then edges, but the delta generation doesn't reflect this ordering
3. **Frontend Validation**: The frontend `GraphCanvas` component validates edge references during delta processing and warns about missing nodes
4. **Race Conditions**: WebSocket delta messages can arrive out of order due to network conditions

### Current Data Flow

```
Webhook → DuckDB Queue → process_updates() → Delta Generation → WebSocket → Frontend
```

**Issues:**
- Delta generation doesn't guarantee node-before-edge ordering
- Frontend receives mixed node/edge deltas in single messages
- No buffering mechanism for orphaned edges
- No validation at the backend level

## Solution Overview

Implement a comprehensive edge validation and ordering system that ensures data consistency across the entire pipeline, from backend processing to frontend visualization.

## Requirements

### Functional Requirements

1. **Backend Validation**: Validate edge references before including them in deltas
2. **Ordered Delta Generation**: Ensure nodes are always sent before their edges
3. **Edge Buffering**: Buffer orphaned edges until their nodes are available
4. **Frontend Resilience**: Handle out-of-order deltas gracefully
5. **Data Integrity**: Maintain referential integrity throughout the pipeline

### Non-Functional Requirements

1. **Performance**: Minimal impact on real-time update latency
2. **Memory**: Efficient buffering with configurable limits
3. **Reliability**: Graceful degradation when validation fails
4. **Observability**: Comprehensive logging and metrics

## Technical Design

### Phase 1: Backend Edge Validation

**File: `graph-visualizer-rust/src/duckdb_store.rs`**

1. **Add validation to edge processing:**
```rust
// In process_updates() method, before adding edges to delta
for edge in &new_edges {
    // Validate that both source and target nodes exist
    let source_exists: bool = tx.query_row(
        "SELECT COUNT(*) > 0 FROM nodes WHERE id = ?",
        params![&edge.from],
        |row| row.get(0)
    ).unwrap_or(false);
    
    let target_exists: bool = tx.query_row(
        "SELECT COUNT(*) > 0 FROM nodes WHERE id = ?", 
        params![&edge.to],
        |row| row.get(0)
    ).unwrap_or(false);
    
    if !source_exists || !target_exists {
        warn!("Edge validation failed: {} -> {} (source_exists: {}, target_exists: {})",
              edge.from, edge.to, source_exists, target_exists);
        continue; // Skip invalid edges
    }
    
    // Only add validated edges
    validated_edges.push(edge.clone());
}
```

2. **Add edge buffer for orphaned edges:**
```rust
#[derive(Default)]
struct UpdateQueue {
    nodes_to_add: Vec<Node>,
    edges_to_add: Vec<Edge>,
    nodes_to_update: HashMap<String, Node>,
    orphaned_edges: Vec<Edge>, // New: buffer for edges without nodes
}
```

### Phase 2: Ordered Delta Generation

**File: `graph-visualizer-rust/src/delta_tracker.rs`**

1. **Modify delta computation to ensure ordering:**
```rust
pub async fn compute_ordered_delta(&self, new_nodes: Vec<Node>, new_edges: Vec<Edge>) -> Vec<GraphDelta> {
    let mut deltas = Vec::new();
    
    // First delta: only nodes
    if !nodes_added.is_empty() || !nodes_updated.is_empty() {
        deltas.push(GraphDelta {
            operation: DeltaOperation::Update,
            nodes_added: nodes_added.clone(),
            nodes_updated: nodes_updated.clone(),
            nodes_removed: vec![],
            edges_added: vec![], // No edges in node delta
            edges_updated: vec![],
            edges_removed: vec![],
            timestamp: timestamp,
            sequence: sequence,
        });
    }
    
    // Second delta: only edges (after nodes are processed)
    if !edges_added.is_empty() || !edges_updated.is_empty() {
        deltas.push(GraphDelta {
            operation: DeltaOperation::Update,
            nodes_added: vec![], // No nodes in edge delta
            nodes_updated: vec![],
            nodes_removed: vec![],
            edges_added: edges_added.clone(),
            edges_updated: edges_updated.clone(),
            edges_removed: edges_removed.clone(),
            timestamp: timestamp + 1, // Slightly later timestamp
            sequence: sequence + 1,
        });
    }
    
    deltas
}
```

### Phase 3: Enhanced Frontend Validation

**File: `frontend/src/components/GraphCanvas.tsx`**

1. **Add edge buffer for missing nodes:**
```typescript
const [orphanedEdges, setOrphanedEdges] = useState<Array<{
  edge: any;
  timestamp: number;
}>>([]);

const ORPHAN_TIMEOUT = 5000; // 5 seconds
```

2. **Modify delta processing to buffer orphaned edges:**
```typescript
const processEdgeDelta = useCallback((edges: any[]) => {
  const validEdges = [];
  const newOrphans = [];
  
  for (const edge of edges) {
    const sourceExists = cosmographRef.current?.getNodes()?.some(n => n.id === edge.source);
    const targetExists = cosmographRef.current?.getNodes()?.some(n => n.id === edge.target);
    
    if (sourceExists && targetExists) {
      validEdges.push(edge);
    } else {
      console.warn(`[GraphCanvas] Buffering orphaned edge: ${edge.source} -> ${edge.target}`);
      newOrphans.push({
        edge,
        timestamp: Date.now()
      });
    }
  }
  
  // Add valid edges to graph
  if (validEdges.length > 0) {
    cosmographRef.current?.setLinks(prevLinks => [...prevLinks, ...validEdges]);
  }
  
  // Update orphaned edges buffer
  if (newOrphans.length > 0) {
    setOrphanedEdges(prev => [...prev, ...newOrphans]);
  }
}, []);
```

3. **Add periodic orphan resolution:**
```typescript
useEffect(() => {
  const interval = setInterval(() => {
    if (orphanedEdges.length === 0) return;
    
    const now = Date.now();
    const resolvedEdges = [];
    const stillOrphaned = [];
    
    for (const orphan of orphanedEdges) {
      // Timeout old orphans
      if (now - orphan.timestamp > ORPHAN_TIMEOUT) {
        console.warn(`[GraphCanvas] Orphaned edge timed out: ${orphan.edge.source} -> ${orphan.edge.target}`);
        continue;
      }
      
      // Check if nodes now exist
      const sourceExists = cosmographRef.current?.getNodes()?.some(n => n.id === orphan.edge.source);
      const targetExists = cosmographRef.current?.getNodes()?.some(n => n.id === orphan.edge.target);
      
      if (sourceExists && targetExists) {
        resolvedEdges.push(orphan.edge);
      } else {
        stillOrphaned.push(orphan);
      }
    }
    
    // Add resolved edges to graph
    if (resolvedEdges.length > 0) {
      console.log(`[GraphCanvas] Resolved ${resolvedEdges.length} orphaned edges`);
      cosmographRef.current?.setLinks(prevLinks => [...prevLinks, ...resolvedEdges]);
    }
    
    setOrphanedEdges(stillOrphaned);
  }, 1000); // Check every second
  
  return () => clearInterval(interval);
}, [orphanedEdges]);
```

## Implementation Plan

### Phase 1: Backend Validation (Week 1)
- [ ] Add edge validation to `DuckDBStore::process_updates()`
- [ ] Implement orphaned edge buffering
- [ ] Add validation metrics and logging
- [ ] Unit tests for validation logic

### Phase 2: Ordered Delta Generation (Week 2)  
- [ ] Modify `DeltaTracker` to generate ordered deltas
- [ ] Update WebSocket broadcasting to handle multiple deltas
- [ ] Integration tests for delta ordering
- [ ] Performance testing

### Phase 3: Frontend Resilience (Week 3)
- [ ] Implement edge buffering in `GraphCanvas`
- [ ] Add orphan resolution mechanism
- [ ] Enhanced error handling and logging
- [ ] End-to-end testing

### Phase 4: Monitoring & Optimization (Week 4)
- [ ] Add comprehensive metrics
- [ ] Performance optimization
- [ ] Documentation updates
- [ ] Production deployment

## Success Metrics

1. **Zero "Edge references unknown nodes" warnings** in normal operation
2. **< 100ms additional latency** for real-time updates
3. **99.9% edge resolution rate** within 5 seconds
4. **Memory usage < 10MB** for orphaned edge buffer

## Risk Mitigation

1. **Performance Impact**: Implement efficient validation queries with proper indexing
2. **Memory Leaks**: Add configurable limits and timeouts for orphaned edges
3. **Backward Compatibility**: Maintain existing API contracts
4. **Data Loss**: Comprehensive logging and fallback mechanisms

## Testing Strategy

1. **Unit Tests**: Validation logic, buffering mechanisms
2. **Integration Tests**: End-to-end delta processing
3. **Load Tests**: High-frequency update scenarios
4. **Chaos Tests**: Network delays, out-of-order delivery

## Monitoring

1. **Metrics**: Edge validation success rate, orphan buffer size, resolution time
2. **Alerts**: High orphan count, validation failures, timeout rates
3. **Dashboards**: Real-time data flow visualization
4. **Logs**: Structured logging for debugging

## Alternative Approaches

1. **Event Sourcing**: Store all events and replay in order (higher complexity)
2. **Dependency Graphs**: Build dependency trees for updates (performance overhead)
3. **Eventual Consistency**: Accept temporary inconsistency (user experience impact)

The proposed solution balances data integrity, performance, and implementation complexity while providing a robust foundation for real-time graph updates.

## Configuration

### Backend Configuration

**File: `graph-visualizer-rust/src/config.rs`**

```rust
#[derive(Debug, Clone)]
pub struct EdgeValidationConfig {
    pub enable_validation: bool,
    pub max_orphaned_edges: usize,
    pub orphan_timeout_ms: u64,
    pub enable_ordered_deltas: bool,
    pub validation_timeout_ms: u64,
}

impl Default for EdgeValidationConfig {
    fn default() -> Self {
        Self {
            enable_validation: true,
            max_orphaned_edges: 1000,
            orphan_timeout_ms: 30000, // 30 seconds
            enable_ordered_deltas: true,
            validation_timeout_ms: 1000, // 1 second
        }
    }
}
```

### Environment Variables

```bash
# Edge validation settings
EDGE_VALIDATION_ENABLED=true
MAX_ORPHANED_EDGES=1000
ORPHAN_TIMEOUT_MS=30000
ORDERED_DELTAS_ENABLED=true
VALIDATION_TIMEOUT_MS=1000

# Monitoring settings
EDGE_METRICS_ENABLED=true
VALIDATION_LOG_LEVEL=warn
```

## Database Schema Changes

### Add Validation Tracking Table

```sql
CREATE TABLE edge_validation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    edge_source VARCHAR NOT NULL,
    edge_target VARCHAR NOT NULL,
    edge_type VARCHAR NOT NULL,
    validation_status VARCHAR NOT NULL, -- 'valid', 'orphaned', 'timeout', 'resolved'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    error_message TEXT
);

CREATE INDEX idx_edge_validation_status ON edge_validation_log(validation_status);
CREATE INDEX idx_edge_validation_created ON edge_validation_log(created_at);
```

### Add Metrics Table

```sql
CREATE TABLE edge_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name VARCHAR NOT NULL,
    metric_value DOUBLE NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT -- JSON metadata
);

CREATE INDEX idx_edge_metrics_name_time ON edge_metrics(metric_name, timestamp);
```

## API Enhancements

### New Endpoints

**File: `graph-visualizer-rust/src/main.rs`**

```rust
// Get edge validation statistics
async fn get_edge_validation_stats(
    State(state): State<AppState>,
) -> Result<Json<EdgeValidationStats>, (StatusCode, Json<ErrorResponse>)> {
    let stats = state.duckdb_store.get_validation_stats().await?;
    Ok(Json(stats))
}

// Get orphaned edges
async fn get_orphaned_edges(
    State(state): State<AppState>,
) -> Result<Json<Vec<OrphanedEdge>>, (StatusCode, Json<ErrorResponse>)> {
    let orphans = state.duckdb_store.get_orphaned_edges().await?;
    Ok(Json(orphans))
}

// Force resolve orphaned edges
async fn resolve_orphaned_edges(
    State(state): State<AppState>,
) -> Result<Json<ResolutionResult>, (StatusCode, Json<ErrorResponse>)> {
    let result = state.duckdb_store.resolve_orphaned_edges().await?;
    Ok(Json(result))
}
```

### Response Types

```rust
#[derive(Serialize)]
pub struct EdgeValidationStats {
    pub total_edges_processed: u64,
    pub valid_edges: u64,
    pub orphaned_edges: u64,
    pub resolved_edges: u64,
    pub timed_out_edges: u64,
    pub current_orphan_count: usize,
    pub average_resolution_time_ms: f64,
}

#[derive(Serialize)]
pub struct OrphanedEdge {
    pub source: String,
    pub target: String,
    pub edge_type: String,
    pub created_at: u64,
    pub age_ms: u64,
}

#[derive(Serialize)]
pub struct ResolutionResult {
    pub resolved_count: usize,
    pub still_orphaned: usize,
    pub errors: Vec<String>,
}
```

## Deployment Strategy

### Rolling Deployment

1. **Phase 1**: Deploy backend changes with validation disabled
2. **Phase 2**: Enable validation in monitoring mode (log only)
3. **Phase 3**: Enable validation with buffering
4. **Phase 4**: Deploy frontend changes
5. **Phase 5**: Enable ordered deltas

### Rollback Plan

1. **Immediate**: Disable validation via environment variable
2. **Backend**: Revert to previous image version
3. **Frontend**: Disable orphan buffering via feature flag
4. **Database**: No schema changes required for rollback

## Documentation Updates

### API Documentation

- Add new endpoints to OpenAPI spec
- Update WebSocket message format documentation
- Add configuration reference

### Operational Runbooks

- Edge validation troubleshooting guide
- Performance tuning recommendations
- Monitoring and alerting setup

### Developer Guide

- Edge validation architecture overview
- Testing strategies for edge cases
- Contributing guidelines for validation logic

## Future Enhancements

### Phase 2 Features

1. **Smart Buffering**: Prioritize edges by importance/frequency
2. **Batch Resolution**: Resolve orphans in batches for efficiency
3. **Predictive Loading**: Pre-load likely nodes based on patterns
4. **Cross-Session Persistence**: Persist orphaned edges across restarts

### Advanced Validation

1. **Schema Validation**: Validate edge types and properties
2. **Business Rules**: Custom validation rules per edge type
3. **Temporal Validation**: Validate edge timestamps and ordering
4. **Semantic Validation**: Check for logical consistency

### Performance Optimizations

1. **Bloom Filters**: Fast node existence checks
2. **Caching**: Cache validation results
3. **Parallel Processing**: Validate edges in parallel
4. **Streaming**: Stream large delta updates

## Conclusion

This comprehensive PRD addresses the "edges referencing unknown nodes" issue through a multi-layered approach that ensures data integrity while maintaining performance. The solution provides immediate fixes for the current problem while establishing a foundation for future enhancements and scalability.
