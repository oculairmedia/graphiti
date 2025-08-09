use axum::{extract::State, Json};
use serde::{Deserialize, Serialize};
use tracing::instrument;

use crate::error::SearchResult;
use crate::models::{Node, NodeSearchConfig, SearchFilters};
use crate::search::SearchEngine;
use crate::AppState;

#[derive(Debug, Deserialize)]
pub struct NodeSearchRequest {
    pub query: String,
    pub config: NodeSearchConfig,
    pub filters: Option<SearchFilters>,
    pub query_vector: Option<Vec<f32>>,
}

#[derive(Debug, Serialize)]
pub struct NodeSearchResponse {
    pub nodes: Vec<Node>,
    pub total: usize,
    pub latency_ms: u64,
}

#[instrument(skip(state))]
pub async fn node_search_handler(
    State(state): State<AppState>,
    Json(request): Json<NodeSearchRequest>,
) -> SearchResult<Json<NodeSearchResponse>> {
    let start = std::time::Instant::now();
    
    // Get database connection
    let falkor_conn = state.falkor_pool.get().await
        .map_err(|e| crate::error::SearchError::Database(
            format!("Failed to get database connection: {}", e)
        ))?;

    // Create search engine
    let mut engine = SearchEngine::new(falkor_conn, state.redis_pool.clone());
    
    // Execute node search
    let nodes = engine.search_nodes(
        &request.query,
        &request.config,
        &request.filters.unwrap_or_default(),
        request.query_vector.as_deref(),
    ).await?;
    
    let total = nodes.len();
    let latency_ms = start.elapsed().as_millis() as u64;
    
    Ok(Json(NodeSearchResponse {
        nodes,
        total,
        latency_ms,
    }))
}