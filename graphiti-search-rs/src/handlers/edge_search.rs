use axum::{extract::State, Json};
use serde::{Deserialize, Serialize};
use tracing::instrument;

use super::{ensure_query_embedding, search_methods_need_embedding};
use crate::error::SearchResult;
use crate::models::{Edge, EdgeSearchConfig, SearchFilters};
use crate::AppState;

#[derive(Debug, Deserialize)]
pub struct EdgeSearchRequest {
    pub query: String,
    pub config: EdgeSearchConfig,
    pub filters: Option<SearchFilters>,
    pub query_vector: Option<Vec<f32>>,
    /// Maximum number of results to return (defaults to 100)
    #[serde(default = "default_limit")]
    pub limit: usize,
}

fn default_limit() -> usize {
    100
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
    Json(mut request): Json<EdgeSearchRequest>,
) -> SearchResult<Json<EdgeSearchResponse>> {
    let start = std::time::Instant::now();

    let needs_embedding = search_methods_need_embedding(&request.config.search_methods);
    let _ =
        ensure_query_embedding(&request.query, &mut request.query_vector, needs_embedding).await;

    let mut engine = state.create_search_engine();

    // Execute edge search
    let edges = engine
        .search_edges(
            &request.query,
            &request.config,
            &request.filters.unwrap_or_default(),
            request.query_vector.as_deref(),
            request.limit,
        )
        .await?;

    let total = edges.len();
    let latency_ms = start.elapsed().as_millis() as u64;

    Ok(Json(EdgeSearchResponse {
        edges,
        total,
        latency_ms,
    }))
}
