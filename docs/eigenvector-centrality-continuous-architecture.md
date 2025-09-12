# Continuous Eigenvector Centrality Maintenance Architecture

**Version**: 1.0  
**Date**: 2025-01-12  
**Status**: Proposal  
**Authors**: Graphiti Team  
**Technical Review**: Completed (GPT-5 Audit)  
**Huly Milestone**: [Eigenvector Centrality Continuous Index](https://huly.app/project/GRAPH/milestone/68c4572ec41f0bb5fb8e6b7a)

## Executive Summary

This document proposes a fundamental architectural shift for eigenvector centrality computation in Graphiti, moving from batch computation to continuous maintenance. Instead of computing eigenvector centrality on-demand (2-5 minutes for 10k+ nodes), we maintain it as a first-class index that is continuously updated with graph changes.

**Key Innovation**: Eigenvector centrality becomes a persistent, incrementally-maintained index rather than a query-time computation, similar to how search engines maintain inverted indexes.

## Problem Statement

Current implementation issues:
- **Performance**: 2-5 minutes for 10k+ nodes (unacceptable for interactive use)
- **Resource Usage**: Full graph extraction and recomputation on every request
- **Scalability**: Linear degradation with graph size
- **No Native Support**: FalkorDB lacks native eigenvector algorithm (unlike PageRank/Betweenness)

## Proposed Architecture

### Core Concept: Persistent Eigenvector State Machine

```rust
pub struct EigenvectorIndex {
    // Core state
    eigenvector: Vec<f64>,              // Current eigenvector (dense)
    lambda: f64,                         // Current eigenvalue (Rayleigh quotient)
    residual: f64,                       // Current residual norm
    
    // Graph representation
    csr_matrix: CSRMatrix<f64>,         // Compressed sparse row format
    graph_version: u64,                  // Version for invalidation
    
    // Multi-resolution cache
    levels: Vec<ApproximationLevel>,    // Different accuracy levels
    
    // Acceleration state (optional)
    prev_vector: Option<Vec<f64>>,      // For Chebyshev acceleration
    anderson_history: VecDeque<Vec<f64>>, // For Anderson mixing
}

struct ApproximationLevel {
    tolerance: f64,
    vector: Vec<f64>,
    last_updated: Instant,
    access_count: u64,
}
```

### Mathematical Foundation

We compute the dominant eigenvector of A^T (transpose of adjacency matrix) for "incoming importance" centrality:

```rust
// Power iteration with A^T
loop {
    // y = A^T * x (using GraphBLAS)
    let y = spmv_transpose(&csr_matrix, &x);
    
    // Rayleigh quotient for eigenvalue
    let lambda = dot(&x, &y) / dot(&x, &x);
    
    // Normalize
    x = normalize(y);
    
    // Check convergence via residual
    let residual = norm2(y - lambda * x) / norm2(x);
    if residual < tolerance {
        break;
    }
}
```

### Key Components

#### 1. GraphBLAS Integration (Recommended Approach)

Use SuiteSparse:GraphBLAS for high-performance sparse matrix operations:

```rust
// FFI to SuiteSparse:GraphBLAS
#[link(name = "graphblas")]
extern "C" {
    fn GrB_mxv(
        w: GrB_Vector,
        mask: GrB_Vector,
        accum: GrB_BinaryOp,
        op: GrB_Semiring,
        A: GrB_Matrix,
        u: GrB_Vector,
        desc: GrB_Descriptor
    ) -> GrB_Info;
}

// Wrapper for sparse matrix-vector multiplication
pub fn spmv_transpose(matrix: &CSRMatrix<f64>, vector: &[f64]) -> Vec<f64> {
    // Use GrB_DESC_T0 descriptor for transpose
    unsafe {
        let mut result = vec![0.0; vector.len()];
        GrB_mxv(
            result.as_mut_ptr(),
            null(),
            null(),
            GrB_PLUS_TIMES_SEMIRING_FP64,
            matrix.grb_handle,
            vector.as_ptr(),
            GrB_DESC_T0  // Transpose descriptor
        );
        result
    }
}
```

#### 2. Warm-Start Incremental Updates

On graph changes, use the previous eigenvector as initial guess:

```rust
impl EigenvectorIndex {
    pub async fn handle_graph_delta(&mut self, delta: GraphDelta) {
        // Update CSR matrix structure
        match delta {
            GraphDelta::AddEdge(src, dst, weight) => {
                self.csr_matrix.add_edge(src, dst, weight);
            }
            GraphDelta::RemoveEdge(src, dst) => {
                self.csr_matrix.remove_edge(src, dst);
            }
            GraphDelta::BatchUpdate(updates) => {
                // Rebuild CSR for large batches
                self.rebuild_csr_from_updates(updates);
            }
        }
        
        // Increment version
        self.graph_version += 1;
        
        // Reconverge with warm start (typically 2-5 iterations)
        self.reconverge_from_warm_start();
    }
    
    fn reconverge_from_warm_start(&mut self) {
        let mut x = self.eigenvector.clone(); // Start from previous solution
        
        for iter in 0..MAX_WARM_START_ITERS {
            let y = spmv_transpose(&self.csr_matrix, &x);
            let lambda_new = dot(&x, &y) / dot(&x, &x);
            
            x = normalize(y);
            
            let residual = compute_residual(&self.csr_matrix, &x, lambda_new);
            if residual < self.tolerance {
                self.eigenvector = x;
                self.lambda = lambda_new;
                self.residual = residual;
                break;
            }
        }
    }
}
```

#### 3. Multi-Resolution Caching Strategy

Maintain multiple accuracy levels for different use cases:

```rust
pub enum CentralityRequest {
    Exact,              // Full convergence (ε < 1e-8)
    Production(f64),    // Specific tolerance
    Approximate,        // Fast approximation (ε < 1e-3)
    Cached,            // Return immediately with last known
}

impl EigenvectorIndex {
    pub fn get_centrality(&self, request: CentralityRequest) -> CentralityResult {
        match request {
            CentralityRequest::Exact => {
                self.compute_to_tolerance(1e-8)
            }
            CentralityRequest::Production(tol) => {
                self.get_or_compute_level(tol)
            }
            CentralityRequest::Approximate => {
                // Return best available approximation
                self.levels.iter()
                    .find(|l| l.tolerance <= 1e-3)
                    .map(|l| l.vector.clone())
                    .unwrap_or_else(|| self.compute_to_tolerance(1e-3))
            }
            CentralityRequest::Cached => {
                CentralityResult {
                    values: self.eigenvector.clone(),
                    residual: self.residual,
                    computed_at: self.last_updated,
                }
            }
        }
    }
    
    // Background task continuously refines approximations
    async fn background_refinement(&mut self) {
        loop {
            for level in &mut self.levels {
                if level.access_count > REFINEMENT_THRESHOLD {
                    self.refine_to_tolerance(level.tolerance);
                    level.last_updated = Instant::now();
                }
            }
            tokio::time::sleep(Duration::from_secs(1)).await;
        }
    }
}
```

#### 4. Acceleration Techniques (Priority Order)

##### a. Chebyshev Polynomial Acceleration (Recommended First)

```rust
fn chebyshev_acceleration(&mut self, y_current: Vec<f64>, y_prev: Vec<f64>) -> Vec<f64> {
    // Estimate spectral bounds
    let lambda_max = self.lambda * 1.1;  // Conservative upper bound
    let lambda_min = self.lambda * 0.9;  // Conservative lower bound
    
    // Chebyshev coefficient
    let rho = (lambda_max - lambda_min) / (lambda_max + lambda_min);
    let alpha = 2.0 / (1.0 + (1.0 - rho * rho).sqrt());
    
    // Accelerated vector: x_{k+1} = y_k + alpha * (y_k - y_{k-1})
    let mut x_new = y_current.clone();
    for i in 0..x_new.len() {
        x_new[i] += alpha * (y_current[i] - y_prev[i]);
    }
    normalize(x_new)
}
```

##### b. Anderson Acceleration (Optional)

```rust
fn anderson_mixing(&mut self, vectors: &[Vec<f64>], residuals: &[Vec<f64>]) -> Vec<f64> {
    // Solve least squares problem for optimal mixing coefficients
    // Returns weighted combination of previous iterates
    // Implementation details omitted for brevity
}
```

##### c. GPU Acceleration (Future, Optional)

```rust
#[cfg(feature = "gpu")]
mod gpu {
    use cugraph::centrality::eigenvector_centrality;
    
    pub fn compute_eigenvector_gpu(
        edges: &[(u32, u32, f64)]
    ) -> Result<Vec<f64>, CuGraphError> {
        // Delegate to cuGraph for massive graphs (10M+ edges)
        eigenvector_centrality(edges, tolerance=1e-6, max_iter=100)
    }
}
```

### System Architecture

```
┌─────────────────────────────────────────────┐
│              Client Request                  │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│         Eigenvector Index Service           │
│  ┌─────────────────────────────────────┐   │
│  │     Request Handler                  │   │
│  │  - Check cache levels                │   │
│  │  - Return best available             │   │
│  │  - Queue refinement if needed        │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │   Continuous Maintenance Thread      │   │
│  │  - Process graph updates             │   │
│  │  - Warm-start reconvergence         │   │
│  │  - Background refinement            │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │      GraphBLAS Backend               │   │
│  │  - SuiteSparse:GraphBLAS            │   │
│  │  - Parallel SpMV operations         │   │
│  │  - CSR/CSC matrix storage           │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│              FalkorDB                       │
│  - Graph storage and updates                │
│  - Future: algo.eigenvector procedure       │
└─────────────────────────────────────────────┘
```

## Implementation Roadmap

### Phase 1: Core Implementation (Weeks 1-2)

**7 Main Issues + 8 Sub-issues**

#### Critical Path Issues (Urgent):
- **[GRAPH-517](https://huly.app/issue/GRAPH-517): GraphBLAS Integration Layer**
  - GRAPH-541: Design GraphBLAS FFI Interface
  - GRAPH-540: Implement Core GraphBLAS Bindings
  - GRAPH-542: GraphBLAS Safety Wrappers
  - GRAPH-543: GraphBLAS Unit Tests

- **[GRAPH-518](https://huly.app/issue/GRAPH-518): Power Iteration Core Algorithm**
  - GRAPH-544: Implement Basic Power Iteration
  - GRAPH-545: Rayleigh Quotient Computation
  - GRAPH-546: Residual-Based Convergence
  - GRAPH-547: Component Connectivity Handling

#### High Priority Issues:
- [GRAPH-520](https://huly.app/issue/GRAPH-520): CSR/CSC Matrix Management
- [GRAPH-521](https://huly.app/issue/GRAPH-521): Warm-Start Incremental Updates
- [GRAPH-519](https://huly.app/issue/GRAPH-519): Multi-Resolution Cache System
- [GRAPH-522](https://huly.app/issue/GRAPH-522): Eigenvector Index Service

#### Medium Priority:
- [GRAPH-523](https://huly.app/issue/GRAPH-523): Chebyshev Polynomial Acceleration

### Phase 2: Production Hardening (Weeks 3-4)

**6 Issues - Stability & Performance**

- [GRAPH-525](https://huly.app/issue/GRAPH-525): Robust Matrix Update Operations (High)
- [GRAPH-524](https://huly.app/issue/GRAPH-524): Error Handling and Recovery System (High)
- [GRAPH-528](https://huly.app/issue/GRAPH-528): Monitoring and Metrics Dashboard (Medium)
- [GRAPH-529](https://huly.app/issue/GRAPH-529): Performance Benchmarking Suite (Medium)
- [GRAPH-526](https://huly.app/issue/GRAPH-526): Production Configuration Management (Medium)
- [GRAPH-527](https://huly.app/issue/GRAPH-527): Anderson Acceleration Implementation (Low)

### Phase 3: Advanced Features (Month 2)

**6 Issues - Optimization & Scaling**

- [GRAPH-533](https://huly.app/issue/GRAPH-533): Update Burst Backpressure (High)
- [GRAPH-530](https://huly.app/issue/GRAPH-530): Node Reordering for Cache Locality (Medium)
- [GRAPH-532](https://huly.app/issue/GRAPH-532): Snapshot Versioning System (Medium)
- [GRAPH-531](https://huly.app/issue/GRAPH-531): GPU Backend Integration (Low)
- [GRAPH-535](https://huly.app/issue/GRAPH-535): Distributed Computation Support (Low)
- [GRAPH-534](https://huly.app/issue/GRAPH-534): Adaptive Algorithm Selection (Low)

### Phase 4: FalkorDB Integration (Month 3+)

**4 Issues - Native Algorithm**

- [GRAPH-536](https://huly.app/issue/GRAPH-536): FalkorDB Algorithm Specification (Medium)
- [GRAPH-538](https://huly.app/issue/GRAPH-538): FalkorDB Native Implementation (Low)
- [GRAPH-537](https://huly.app/issue/GRAPH-537): FalkorDB Contribution Process (Low)
- [GRAPH-539](https://huly.app/issue/GRAPH-539): Migration to Native Algorithm (Low)

## Performance Characteristics

### Expected Performance

| Operation | Current | Proposed | Improvement |
|-----------|---------|----------|-------------|
| Cold Start (10k nodes) | 2-5 min | 100-500ms | 240-600x |
| Warm Query (cached) | 2-5 min | <1ms | 120,000x+ |
| Incremental Update | N/A | 10-50ms | N/A |
| Memory Usage | O(n²) extraction | O(edges + k*nodes) | 10-100x reduction |

### SLA Targets

- **P50 Query Latency**: <5ms (cached)
- **P95 Query Latency**: <50ms (warm start)
- **P99 Query Latency**: <500ms (cold start)
- **Update Processing**: <100ms for single edge update
- **Throughput**: 10,000+ queries/second (cached)

## Key Technical Decisions (Based on GPT-5 Audit)

### What to Keep and Strengthen:
1. **SpMV-centric implementation** (CSR/CSC), parallelized over rows/edges
2. **Warm starts**: Reuse last eigenvector after small graph deltas; often reconverges in 1–5 iterations
3. **Residual-based stopping** with Rayleigh quotient; f64 precision
4. **Chebyshev/Anderson acceleration** for small spectral gaps
5. **Multi-resolution cache** (tolerances like 1e-3, 1e-4, 1e-6) with background tightening
6. **Connectivity awareness** (WCC/SCC); be explicit about A vs A^T

### What to Change or Defer:
1. **Do not attempt rank-1 "Sherman-Morrison" updates** to the eigenvector. Use warm-started iterations instead.
2. **Avoid private zero-copy FFI** into FalkorDB's internal GraphBLAS matrices; prefer a stable backend you control (SuiteSparse:GraphBLAS)
3. **Be cautious with chunked adjacency loading**; prefer a single compact CSR/CSC (optionally memory-mapped) for iterative SpMV
4. **Ensure compute threads do not oversubscribe** Tokio; use a dedicated pool

## Risk Mitigation

### Technical Risks

1. **Small Spectral Gap**
   - **Risk**: Slow convergence for certain graph structures
   - **Mitigation**: Chebyshev/Anderson acceleration, adaptive tolerance

2. **Memory Pressure**
   - **Risk**: Large graphs exceeding memory
   - **Mitigation**: Memory-mapped CSR, selective subgraph computation

3. **Numerical Stability**
   - **Risk**: Precision loss in iterative computation
   - **Mitigation**: Use f64 throughout, regular renormalization

### Operational Risks

1. **Update Storms**
   - **Risk**: Burst of updates overwhelming the system
   - **Mitigation**: Update batching, backpressure, queue management

2. **Cache Invalidation**
   - **Risk**: Stale data being served
   - **Mitigation**: Version tracking, precise invalidation logic

## Monitoring and Observability

Key metrics to track:
- Convergence rate (iterations to tolerance)
- Cache hit rates by tolerance level
- Update processing latency
- Residual norms over time
- Memory usage and CSR matrix statistics

## Conclusion

This architecture transforms eigenvector centrality from an expensive batch computation into an efficient, continuously-maintained index. By leveraging GraphBLAS for sparse linear algebra, warm starts for incremental updates, and multi-resolution caching, we can achieve sub-millisecond query latencies while maintaining mathematical accuracy.

The phased implementation approach with **27 tracked issues** allows us to deliver immediate value while building toward a robust, production-ready system that can eventually be contributed back to FalkorDB as a native algorithm.

## References

1. **SuiteSparse:GraphBLAS Documentation**: https://github.com/DrTimothyAldenDavis/GraphBLAS
2. **FalkorDB Algorithm Procedures**: https://docs.falkordb.com/commands/graph.query.html
3. **Power Iteration Convergence Analysis**: Golub & Van Loan, Matrix Computations (4th ed.)
4. **Chebyshev Acceleration**: Saad, Iterative Methods for Sparse Linear Systems
5. **Anderson Acceleration**: Walker & Ni, "Anderson Acceleration for Fixed-Point Iterations"
6. **Technical Audit**: GPT-5 review findings incorporated into design decisions

---

**Total Issues Created**: 27 issues (19 main + 8 sub-issues)  
**Huly Project**: GRAPH  
**Milestone**: Eigenvector Centrality Continuous Index  
**Target Date**: April 30, 2025