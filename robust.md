# Robust Eigenvector Centrality Implementation Proposal

## Executive Summary

This document outlines a comprehensive proposal for implementing robust eigenvector centrality in the Graphiti knowledge graph system. The current implementation suffers from critical issues including incorrect edge direction handling and poor convergence behavior, resulting in degenerate solutions where most nodes receive zero centrality scores.

## Root Cause Analysis

### Current Implementation Issues

1. **Undirected Edge Treatment**: Line 520 in `graphiti-centrality-rs/src/algorithms.rs` uses `(n)-[r]-(m)` treating edges as undirected
2. **No Connectivity Analysis**: Algorithm doesn't check for strongly connected components
3. **Degenerate Convergence**: Power iteration converges to solutions where only nodes in the largest strongly connected component get non-zero scores
4. **Poor Initialization**: Uniform initialization (1/√n) is suboptimal
5. **Inadequate Convergence Criteria**: Single tolerance check insufficient for robust convergence

### Impact on Knowledge Graphs

- Information flow direction is lost
- Influence propagation is incorrectly modeled
- Results are meaningless for most nodes
- Algorithm fails on realistic graph topologies

## Research-Based Solution Architecture

### Multi-Strategy Approach

Based on NetworkX best practices and graph theory research, we propose a multi-strategy architecture:

```rust
pub enum EigenvectorStrategy {
    Pure,           // Traditional eigenvector centrality
    Damped,         // PageRank-style damping for robustness  
    ComponentWise,  // Per-component calculation
    Adaptive,       // Automatically choose best strategy
}

pub enum GraphConnectivity {
    StronglyConnected,
    WeaklyConnected, 
    Disconnected,
}
```

### Algorithm Selection Logic

1. **Strongly Connected Graphs**: Use pure eigenvector centrality
2. **Weakly Connected Graphs**: Use damped eigenvector centrality (PageRank-style)
3. **Disconnected Graphs**: Use component-wise calculation
4. **Pathological Cases**: Fall back to Katz centrality or degree centrality

## Technical Implementation

### 1. Fix Directed Edge Handling

**Current (Incorrect):**
```cypher
OPTIONAL MATCH (n)-[r]-(m)  // Treats edges as undirected
```

**Proposed (Correct):**
```cypher
MATCH (n) WHERE n.group_id = '{}'
OPTIONAL MATCH (n)<-[r]-(m) WHERE m.group_id = '{}'
WITH n, collect(DISTINCT m.uuid) as in_neighbors
OPTIONAL MATCH (n)-[r]->(m) WHERE m.group_id = '{}'
RETURN n.uuid as node, in_neighbors, count(m) as out_degree
```

### 2. Connectivity Analysis

```rust
async fn analyze_graph_connectivity(
    client: &FalkorClient, 
    group_id: Option<&str>
) -> Result<GraphConnectivity> {
    
    // Use FalkorDB's strongly connected components algorithm
    let scc_query = format!(
        "CALL algo.scc('{}') YIELD nodeId, componentId
         RETURN componentId, count(*) as size
         ORDER BY size DESC",
        client.graph_name()
    );
    
    let results = client.execute_query(&scc_query, None).await?;
    
    // Analyze component structure
    if results.len() == 1 {
        GraphConnectivity::StronglyConnected
    } else if has_giant_component(&results) {
        GraphConnectivity::WeaklyConnected  
    } else {
        GraphConnectivity::Disconnected
    }
}
```

### 3. Damped Eigenvector Centrality

For non-strongly connected graphs, implement PageRank-style damping:

```rust
// Power iteration with damping
for iteration in 0..max_iterations {
    for node in &all_nodes {
        let mut score = uniform_value; // Damping term: (1-d)/N
        
        // Add contributions from in-neighbors
        if let Some(in_neighbors) = adjacency.get(node) {
            for neighbor in in_neighbors {
                if let Some(neighbor_score) = scores.get(neighbor) {
                    let neighbor_out_degree = out_degrees.get(neighbor).unwrap_or(&1.0);
                    score += damping_factor * (neighbor_score / neighbor_out_degree);
                }
            }
        }
        
        new_scores.insert(node.clone(), score);
    }
    
    // Normalize and check convergence
    normalize_l2(&mut new_scores);
    if check_convergence(&scores, &new_scores, tolerance) {
        break;
    }
    scores = new_scores;
}
```

### 4. Component-Wise Calculation

For disconnected graphs:

1. Identify strongly connected components
2. Calculate eigenvector centrality within each component
3. Weight by component size/importance
4. Normalize globally

### 5. Enhanced Convergence Criteria

```rust
// Multiple convergence checks
let l1_diff: f64 = all_nodes.iter()
    .map(|node| {
        let old = scores.get(node).unwrap_or(&0.0);
        let new = new_scores.get(node).unwrap_or(&0.0);
        (old - new).abs()
    })
    .sum();
    
let max_diff: f64 = all_nodes.iter()
    .map(|node| {
        let old = scores.get(node).unwrap_or(&0.0);
        let new = new_scores.get(node).unwrap_or(&0.0);
        (old - new).abs()
    })
    .fold(0.0, f64::max);

// Converged if both L1 and max difference are small
if l1_diff / node_count < tolerance && max_diff < tolerance * 10.0 {
    break;
}
```

## Implementation Phases

### Phase 1: Critical Fix (Immediate)
- [ ] Fix directed edge query in line 520
- [ ] Update adjacency matrix construction
- [ ] Test with current graph data

### Phase 2: Connectivity Analysis (Week 1)
- [ ] Implement strongly connected components detection
- [ ] Add graph connectivity classification
- [ ] Create strategy selection logic

### Phase 3: Damped Algorithm (Week 2)
- [ ] Implement damped eigenvector centrality
- [ ] Add improved initialization strategies
- [ ] Enhance convergence criteria

### Phase 4: Component-Wise Calculation (Week 3)
- [ ] Implement per-component calculation
- [ ] Add component weighting strategies
- [ ] Global normalization across components

### Phase 5: Testing & Validation (Week 4)
- [ ] Comprehensive unit tests
- [ ] Integration tests with real data
- [ ] Performance benchmarking
- [ ] Comparison with NetworkX results

## Error Handling & Fallbacks

```rust
impl CentralityError {
    pub fn EigenvectorConvergenceFailure(iterations: u32, final_diff: f64) -> Self {
        CentralityError::Custom(format!(
            "Eigenvector centrality failed to converge after {} iterations (final_diff: {:.8})", 
            iterations, final_diff
        ))
    }
    
    pub fn GraphStructureIncompatible(reason: String) -> Self {
        CentralityError::Custom(format!(
            "Graph structure incompatible with eigenvector centrality: {}", 
            reason
        ))
    }
}
```

### Fallback Hierarchy
1. Pure eigenvector centrality
2. Damped eigenvector centrality  
3. Katz centrality
4. Degree centrality (always succeeds)

## Testing Strategy

### Unit Tests
- Strongly connected graphs
- Weakly connected graphs
- Disconnected graphs
- Edge cases (single nodes, self-loops)

### Integration Tests
- Real knowledge graph data
- Performance with large graphs
- Comparison with NetworkX implementations

### Validation Metrics
- Convergence rate
- Result stability
- Computational performance
- Memory usage

## Expected Outcomes

### Immediate Benefits
- Fix "most nodes have 0.0% centrality" issue
- Correct handling of directed information flow
- Meaningful results for all graph topologies

### Long-term Benefits
- Production-ready eigenvector centrality
- Robust handling of edge cases
- Foundation for advanced centrality measures
- Improved search and ranking quality

## API Changes

### New Function Signature
```rust
pub async fn calculate_eigenvector_centrality_robust(
    client: &FalkorClient,
    group_id: Option<&str>,
    max_iterations: u32,
    tolerance: f64,
    strategy: Option<EigenvectorStrategy>,
) -> Result<CentralityScores>
```

### Backward Compatibility
- Keep existing function as deprecated
- Provide migration guide
- Default to adaptive strategy

## Performance Considerations

- Connectivity analysis: O(V + E) using FalkorDB's native algorithms
- Damped iteration: Same complexity as current implementation
- Component-wise: Linear in number of components
- Memory usage: Minimal increase for adjacency storage

## Conclusion

This proposal provides a comprehensive solution to the eigenvector centrality issues in Graphiti. By implementing proper directed edge handling, connectivity analysis, and robust algorithms, we can ensure meaningful and reliable centrality scores for all knowledge graph topologies.

The phased implementation approach allows for incremental improvements while maintaining system stability. The research-based design draws from proven NetworkX implementations and graph theory best practices.

## Observability and Debugging

### Per-Iteration Metrics
- **L1/Average Difference**: Track average absolute change in scores per iteration
- **Max Difference**: Monitor maximum absolute change for any single node
- **L2 Norm**: Ensure proper normalization at each step
- **Top-K Preview**: Log top 5-10 nodes by score at key iterations (1, 10, 50, final)

### Early Warning Detection
- **Oscillation Detection**: Flag if differences increase for 3+ consecutive iterations
- **Non-Decreasing Differences**: Warn if convergence stalls
- **Numerical Instability**: Check for NaN/Inf values in scores

### Strongly Connected Components Summary
- **SCC Count**: Number of strongly connected components
- **Giant Component Size**: Size of largest SCC as percentage of total nodes
- **Non-Zero Score Coverage**: Percentage of nodes with meaningful centrality scores

### Initialization Logging
- **Strategy Used**: Record which algorithm strategy was selected
- **Random Seed**: Log seed for reproducible degree-based initialization
- **Initial Distribution**: Summary statistics of initial score distribution

## Edge Case Handling Details

### Dangling Nodes (No Outgoing Edges)
- **Treatment**: Set out_degree floor to 1.0 to avoid division by zero
- **Rationale**: Prevents NaN propagation while maintaining mathematical validity
- **Implementation**: `out_degrees.insert(node.clone(), out_degree.max(1.0))`

### Self-Loops
- **Policy**: Include self-loops in centrality calculation
- **Rationale**: Self-loops represent self-reinforcing importance in knowledge graphs
- **Query**: Ensure `(n)-[r]->(n)` patterns are captured in adjacency queries

### Isolated Nodes
- **Behavior**: Receive only damping mass contribution: `(1-d)/N`
- **Post-Normalization**: Included in global L2 normalization
- **Expected Result**: Very low but non-zero centrality scores

### Zero-Degree Nodes
- **In-Degree Zero**: Initialize with small positive value: `1.0 / sqrt(N)`
- **Out-Degree Zero**: Treated as dangling nodes (floor to 1.0)
- **Both Zero**: Isolated node treatment applies

## Parameter Defaults and Guidance

### Recommended Defaults
```rust
pub const DEFAULT_MAX_ITERATIONS: u32 = 100;
pub const DEFAULT_TOLERANCE: f64 = 1e-6;
pub const DEFAULT_DAMPING_FACTOR: f64 = 0.15;
pub const DEFAULT_STRATEGY: EigenvectorStrategy = EigenvectorStrategy::Adaptive;
```

### Strategy Selection Heuristics
- **Adaptive Logic**:
  - Single SCC with >95% of nodes → Pure eigenvector centrality
  - Giant component with >80% of nodes → Damped eigenvector centrality
  - Multiple significant components → ComponentWise calculation
  - Pathological cases → Fallback to Katz centrality

### Tolerance Guidelines
- **Large Graphs (>1000 nodes)**: Use 1e-5 for faster convergence
- **Small Graphs (<100 nodes)**: Use 1e-7 for higher precision
- **Production Systems**: Use 1e-6 as balanced default

### Damping Factor Guidelines
- **Knowledge Graphs**: 0.15 (similar to PageRank)
- **Social Networks**: 0.10 (lower damping for stronger locality)
- **Citation Networks**: 0.20 (higher damping for broader influence)

## Frontend and Serialization Considerations

### Score Serialization
- **Format**: Ensure all scores serialized as 64-bit floats
- **Normalization**: Apply global L2 normalization across all nodes post-aggregation
- **Precision**: Maintain at least 6 decimal places for meaningful differentiation

### UI Integration
- **Property Mapping**: Confirm backend "eigenvector" key maps to frontend "eigenvector_centrality"
- **Percentage Scaling**: Convert [0,1] normalized scores to percentages for display
- **Zero Handling**: Display very small values (< 1e-6) as "< 0.01%" rather than "0.0%"

### Database Storage
- **Field Type**: Store as DOUBLE/FLOAT64 in graph database
- **Indexing**: Consider indexing on eigenvector_centrality for ranking queries
- **Null Handling**: Never store NULL; use 0.0 for failed calculations

### API Response Format
```json
{
  "node_id": "uuid-string",
  "eigenvector_centrality": 0.123456,
  "eigenvector_centrality_percentile": 85.2,
  "calculation_metadata": {
    "strategy_used": "Damped",
    "iterations_to_convergence": 23,
    "final_tolerance": 8.7e-7
  }
}
```
