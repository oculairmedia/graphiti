use axum::{extract::State, Json};
use serde::{Deserialize, Serialize};
use tracing::instrument;

use crate::error::SearchResult;
use crate::models::{Edge, EdgeSearchConfig, SearchFilters};
use crate::search::SearchEngine;
use crate::AppState;

#[derive(Debug, Deserialize)]
pub struct EdgeSearchRequest {
    pub query: String,
    pub config: EdgeSearchConfig,
    pub filters: Option<SearchFilters>,
    pub query_vector: Option<Vec<f32>>,
}

#[derive(Debug, Serialize)]
pub struct EdgeSearchResponse {
    pub edges: Vec<Edge>,
    pub total: usize,
    pub latency_ms: u64,
}

#[instrument(skip(state))]
pub async fn edge_search_handler(
    State(state): State<AppState>,
    Json(request): Json<EdgeSearchRequest>,
) -> SearchResult<Json<EdgeSearchResponse>> {
    let start = std::time::Instant::now();
    
    // Get database connection
    let falkor_conn = state.falkor_pool.get().await
        .map_err(|e| crate::error::SearchError::Database(
            format!("Failed to get database connection: {}", e)
        ))?;

    // Create search engine
    let mut engine = SearchEngine::new(falkor_conn, state.redis_pool.clone());
    
    // Execute edge search
    let edges = engine.search_edges(
        &request.query,
        &request.config,
        &request.filters.unwrap_or_default(),
        request.query_vector.as_deref(),
    ).await?;
    
    let total = edges.len();
    let latency_ms = start.elapsed().as_millis() as u64;
    
    Ok(Json(EdgeSearchResponse {
        edges,
        total,
        latency_ms,
    }))
}