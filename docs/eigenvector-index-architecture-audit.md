# Eigenvector Index Architecture — Technical Audit and Recommendations

Author: Augment Agent (GPT‑5) • Date: 2025‑09‑12

## Executive summary
- Treating eigenvector centrality as a continuously maintained index is the right product direction.
- Anchor the computation on high‑throughput sparse linear algebra (SpMV via GraphBLAS), warm starts, and residual‑based convergence; add polynomial acceleration (Chebyshev/Anderson) before heavier Krylov methods.
- Avoid two hazards:
  1) Private FFI into FalkorDB internals (undocumented, unstable ABI/lifecycle).
  2) Incorrect “rank‑1 Sherman–Morrison” style eigenvector updates (not valid for eigenvectors).
- A pragmatic roadmap: robust power iteration (Aᵀx) + GraphBLAS backend + caching/invalidation now; optional GPU later; propose an official `algo.eigenvector` to FalkorDB when ready.

## Key recommendations (what to keep / change)

Keep and strengthen:
- SpMV-centric implementation (CSR/CSC), parallelized over rows/edges.
- Warm starts: reuse last eigenvector after small graph deltas; often reconverges in 1–5 iters.
- Residual-based stopping with Rayleigh quotient; f64 precision.
- Chebyshev/Anderson acceleration for small spectral gaps.
- Multi‑resolution cache (tolerances like 1e‑3, 1e‑4, 1e‑6) with background tightening.
- Connectivity awareness (WCC/SCC); be explicit about A vs Aᵀ.

Change or defer:
- Do not attempt rank‑1 “Sherman–Morrison” updates to the eigenvector. Use warm‑started iterations instead.
- Avoid private zero‑copy FFI into FalkorDB’s internal GraphBLAS matrices; prefer a stable backend you control (SuiteSparse:GraphBLAS) or upstream an official procedure.
- Be cautious with chunked adjacency loading; prefer a single compact CSR/CSC (optionally memory‑mapped) for iterative SpMV.
- Ensure compute threads do not oversubscribe Tokio; use a dedicated pool.

## Mathematical/convergence core
- Compute the dominant eigenvector of Aᵀ for “incoming importance” (document the choice clearly).
- Use Rayleigh quotient and residual for principled stopping.

Example residual‑based stopping:
<augment_code_snippet mode="EXCERPT">
````rust
// After y = A^T * x:
let lambda = dot(&x, &y) / dot(&x, &x);
let resid = norm2_axpy(&y, -lambda, &x) / norm2(&x);
if resid < tol { break; }
````
</augment_code_snippet>

GraphBLAS transpose via descriptor (conceptual):
<augment_code_snippet mode="EXCERPT">
````matlab
% C = A' * B using descriptor
C = GrB.mxm('+.*', A, B, struct('in0','transpose'));
````
</augment_code_snippet>

## Systems design: persistent index service (now) vs. in‑DB kernel (later)

Short‑ to mid‑term (recommended):
- Build/retain CSR/CSC once per (graph_id, scope) in the Rust service.
- Bind to SuiteSparse:GraphBLAS (FFI) for fast SpMV; parallelize over row blocks.
- Maintain an EigenvectorIndex with:
  - current vector x (dense f64), λ (Rayleigh), residual
  - cache levels by tolerance, last_updated/access_count
  - version/snapshot metadata for precise invalidation
- On batched graph deltas: rebuild affected CSR segments (or rebuild CSR if simpler initially); warm‑start 1–5 iterations to reconverge.

Long‑term (optional):
- Collaborate with FalkorDB to add an official `algo.eigenvector` procedure, mirroring `algo.pageRank`/`algo.betweenness`, implemented natively on its GraphBLAS core. Avoid private, unsupported FFI.

Existing FalkorDB procedures (no eigenvector today):
<augment_code_snippet mode="EXCERPT">
````cypher
CALL algo.pageRank({...});
CALL algo.betweenness({ nodeLabels:[], relationshipTypes:[] });
CALL algo.wcc({...});
````
</augment_code_snippet>

## Parallelism and data layout
- Use CSR (row‑major) for Aᵀx or CSC for Ax depending on your chosen direction; keep it consistent.
- Partition rows into coarse blocks for Rayon; avoid fine‑grained locks.
- Normalize with parallel reductions; expect tiny non‑determinism in floating sums.
- Consider node reordering (RCM/degree) to improve locality if memory bandwidth saturates.

## Caching, invalidation, and SLAs
- Key cache by (graph_id, group_id/filter, direction, tol).
- Multi‑level strategy:
  - Serve best available level within SLA.
  - Background task tightens to stricter levels.
- Invalidate precisely on topology changes; for small deltas warm‑start re‑convergence.

## Acceleration options (in order of practicality)
1) Chebyshev or polynomial acceleration for power iteration (low cost, good gains).
2) Anderson acceleration (vector mixing).
3) Arnoldi/Lanczos (only if needed; adds complexity, orthogonalization, memory).
4) Optional GPU backend (cuGraph) for 10^7+ edges; feature‑gated.

## Pitfalls and mitigations
- Small spectral gap → slow iterations: add acceleration and warm starts.
- Async oversubscription: dedicate a CPU pool for SpMV.
- Data movement: avoid re‑extracting adjacency each request; snapshot and reuse.
- Precision: keep f64; normalize each iteration.
- Determinism: document minor variability from parallel reductions.

## Implementation roadmap

Phase 1 (now)
- Adopt SuiteSparse:GraphBLAS in Rust; implement Aᵀx power iteration with residual‑based stopping (f64), warm starts, Chebyshev/Anderson.
- Build CSR/CSC once per scope; add multi‑resolution cache and invalidation.

Phase 2
- Improve locality (node reordering), blocking/tiling if needed; robust snapshot/versioning; backpressure for update bursts.
- Optional: GPU backend (cuGraph) behind a feature flag.

Phase 3
- Collaborate with FalkorDB to upstream `algo.eigenvector` as a first‑class procedure; avoid private FFI.

## Minimal corrective code sketches

Warm‑started reconvergence after updates:
<augment_code_snippet mode="EXCERPT">
````rust
for _ in 0..max_iters {
    y = spmv_at(&csr, &x);        // A^T x via GraphBLAS
    let lambda = dot(&x,&y)/dot(&x,&x);
    x = normalize(y);
    if residual(&csr, &x, lambda) < tol { break; }
}
````
</augment_code_snippet>

Chebyshev mixing (conceptual, scalar form):
<augment_code_snippet mode="EXCERPT">
````rust
// x_{k+1} = y_k + alpha_k (y_k - y_{k-1})
let y_new = y_k + alpha * (y_k - y_prev);
````
</augment_code_snippet>

## References (Context7)
- FalkorDB procedures/algorithms: PageRank/Betweenness/WCC, no public eigenvector today.
  - https://github.com/falkordb/docs (procedures, algorithms)
- SuiteSparse:GraphBLAS API and descriptors (transpose for mxm/vxm), OpenMP linking:
  - https://github.com/drtimothyaldendavis/suitesparse (GraphBLAS demos/docs)
- cuGraph eigenvector centrality (GPU path, tol/max_iter API):
  - https://github.com/rapidsai/cugraph (centrality notebooks/APIs)

---

Bottom line: Make eigenvector a maintained index by combining robust power iteration (GraphBLAS SpMV) with warm starts, residual‑based control, and multi‑level caching. Defer private in‑DB FFI; if native integration is desired, upstream an official algorithm procedure instead.
