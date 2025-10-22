# Eigenvector Centrality Fix Plan

## Problem Summary

Eigenvector centrality values are showing as 0 in the graph frontend despite being calculated by the centrality service. This is caused by a storage inconsistency between the Rust and Python centrality systems.

## Root Cause Analysis

### Issue Identified
The Rust centrality service correctly calculates eigenvector centrality, but the Python atomic storage layer does not persist it to the database.

### Evidence
1. **Rust Service (Working)**: 
   - `calculate_all_centralities()` includes eigenvector calculation (line 916 in algorithms.rs)
   - Rust client storage includes eigenvector (lines 135, 151, 176 in client.rs)
   - Stores as `n.eigenvector_centrality` property

2. **Python Storage (Broken)**:
   - `atomic_centrality_storage.py` only stores: pagerank, degree, betweenness, importance
   - Missing eigenvector in `_store_batch` method (lines 304-307)
   - When Python storage is used, eigenvector data is lost

3. **Missing API Endpoints**:
   - No dedicated `/centrality/eigenvector` endpoint in Rust service
   - No eigenvector endpoint in Python centrality router

## Implementation Plan

### Phase 1: Fix Critical Storage Bug (Priority: HIGH)

#### 1.1 Update Python Atomic Storage
**File**: `graphiti_core/utils/maintenance/atomic_centrality_storage.py`

**Changes Required**:
- Add eigenvector to batch_data dictionary in `_store_batch` method
- Update the UNWIND query to include eigenvector_centrality property
- Ensure consistency with Rust storage format

**Specific Updates**:
```python
# Line ~307: Add eigenvector to batch_data
batch_data.append({
    "uuid": node_id,
    "pagerank": node_scores.get("pagerank", 0.0),
    "degree": node_scores.get("degree", 0),
    "betweenness": node_scores.get("betweenness", 0.0),
    "eigenvector": node_scores.get("eigenvector", 0.0),  # ADD THIS LINE
    "importance": node_scores.get("importance", 0.0),
    "transaction_id": transaction_id,
    "updated_at": datetime.now(timezone.utc).isoformat(),
})
```

#### 1.2 Update Storage Query
**File**: Same file, update the UNWIND query to include eigenvector_centrality:

```cypher
UNWIND $batch_data AS item
MATCH (n {uuid: item.uuid})
SET n.pagerank_centrality = item.pagerank,
    n.degree_centrality = item.degree,
    n.betweenness_centrality = item.betweenness,
    n.eigenvector_centrality = item.eigenvector,  # ADD THIS LINE
    n.importance_score = item.importance,
    n.centrality_transaction_id = item.transaction_id,
    n.centrality_updated_at = item.updated_at
```

### Phase 2: Add Missing API Endpoints (Priority: MEDIUM)

#### 2.1 Add Eigenvector Request Model
**File**: `graphiti-centrality-rs/src/models.rs`

**Add**:
```rust
/// Request for eigenvector centrality calculation
#[derive(Debug, Deserialize)]
pub struct EigenvectorRequest {
    pub group_id: Option<String>,
    #[serde(default = "default_max_iterations")]
    pub max_iterations: u32,
    #[serde(default = "default_tolerance")]
    pub tolerance: f64,
    #[serde(default = "default_store_results")]
    pub store_results: bool,
}

fn default_max_iterations() -> u32 { 100 }
fn default_tolerance() -> f64 { 1e-6 }
```

#### 2.2 Add Eigenvector Endpoint to Rust Service
**File**: `graphiti-centrality-rs/src/server.rs`

**Add Route**:
```rust
// In create_router function, add:
.route("/centrality/eigenvector", post(eigenvector_endpoint))
```

**Add Handler**:
```rust
/// Eigenvector centrality endpoint
async fn eigenvector_endpoint(
    State(state): State<AppState>,
    Json(request): Json<EigenvectorRequest>,
) -> impl IntoResponse {
    let start = Instant::now();

    match calculate_eigenvector_centrality(
        &state.client,
        request.group_id.as_deref(),
        request.max_iterations,
        request.tolerance,
    )
    .await
    {
        Ok(result) => {
            let execution_time_ms = start.elapsed().as_millis();

            // Store results if requested
            if request.store_results {
                let formatted_scores: HashMap<String, HashMap<String, f64>> = result
                    .scores
                    .iter()
                    .map(|(uuid, score)| {
                        let mut scores = HashMap::new();
                        scores.insert("eigenvector".to_string(), *score);
                        (uuid.clone(), scores)
                    })
                    .collect();

                if let Err(e) = state
                    .client
                    .store_centrality_scores(&formatted_scores)
                    .await
                {
                    error!("Failed to store eigenvector centrality scores: {}", e);
                }
            }

            Json(CentralityResponse {
                scores: result.scores,
                metric: "eigenvector".to_string(),
                nodes_processed: result.nodes_processed,
                execution_time_ms,
            })
            .into_response()
        }
        Err(e) => {
            error!("Eigenvector centrality calculation failed: {}", e);
            handle_error(e).into_response()
        }
    }
}
```

#### 2.3 Add Eigenvector Endpoint to Python Router
**File**: `server/graph_service/routers/centrality.py`

**Add Request Model**:
```python
class EigenvectorRequest(BaseModel):
    group_id: Optional[str] = Field(None, description='Optional group ID to filter nodes')
    max_iterations: int = Field(100, description='Maximum iterations for convergence')
    tolerance: float = Field(1e-6, description='Convergence tolerance')
    store_results: bool = Field(True, description='Whether to store results in database')
```

**Add Endpoint**:
```python
@router.post('/eigenvector', status_code=status.HTTP_200_OK)
async def calculate_eigenvector_endpoint(
    request: EigenvectorRequest,
    graphiti: ZepGraphitiDep,
) -> CentralityResponse:
    """
    Calculate eigenvector centrality for all nodes in the graph.
    Eigenvector centrality measures the importance of nodes based on the importance of their connections.
    This endpoint proxies to the high-performance Rust centrality service.
    """
    result = await call_rust_centrality_service(
        "/centrality/eigenvector",
        request.model_dump()
    )
    
    return CentralityResponse(
        scores=result.get("scores", {}),
        metric='eigenvector',
        nodes_processed=result.get("nodes_processed", len(result.get("scores", {})))
    )
```

### Phase 3: Verification and Testing

#### 3.1 Test Storage Fix
1. Run centrality calculation using Python storage path
2. Verify eigenvector_centrality property is set in database
3. Confirm frontend displays non-zero eigenvector values

#### 3.2 Test New Endpoints
1. Test `/centrality/eigenvector` endpoint directly
2. Verify response format matches other centrality endpoints
3. Test with and without `store_results` parameter

#### 3.3 Integration Testing
1. Test `/centrality/all` endpoint includes eigenvector
2. Verify fallback scenarios work properly
3. Test frontend integration with eigenvector data

## Files to Modify

### Critical (Phase 1)
1. `graphiti_core/utils/maintenance/atomic_centrality_storage.py` - Fix storage bug

### API Completeness (Phase 2)  
2. `graphiti-centrality-rs/src/models.rs` - Add EigenvectorRequest
3. `graphiti-centrality-rs/src/server.rs` - Add eigenvector endpoint
4. `server/graph_service/routers/centrality.py` - Add Python eigenvector endpoint

### Documentation (Phase 3)
5. `docs/api/centrality.md` - Update API documentation
6. `graph-visualizer-rust/API_ENDPOINTS.md` - Add eigenvector endpoint

## Success Criteria

1. ✅ Eigenvector centrality values are non-zero in frontend
2. ✅ Python storage path preserves eigenvector data
3. ✅ Dedicated eigenvector endpoint works independently
4. ✅ All centrality endpoints have consistent behavior
5. ✅ Fallback scenarios maintain eigenvector data

## Risk Assessment

**Low Risk**: The storage fix is isolated and follows existing patterns. The new endpoints follow established conventions.

**Mitigation**: Test thoroughly with both Rust and Python storage paths before deployment.
