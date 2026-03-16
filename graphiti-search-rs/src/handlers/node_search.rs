use axum::{extract::State, Json};
use serde::{Deserialize, Serialize};
use tracing::instrument;

use super::{ensure_query_embedding, search_methods_need_embedding};
use crate::error::SearchResult;
use crate::models::{Node, NodeSearchConfig, SearchFilters};
use crate::AppState;

#[derive(Debug, Deserialize)]
pub struct NodeSearchRequest {
    pub query: String,
    pub config: NodeSearchConfig,
    pub filters: Option<SearchFilters>,
    pub query_vector: Option<Vec<f32>>,
    #[serde(default = "default_limit")]
    pub limit: usize,
}

fn default_limit() -> usize {
    100
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
    Json(mut request): Json<NodeSearchRequest>,
) -> SearchResult<Json<NodeSearchResponse>> {
    let start = std::time::Instant::now();

    let needs_embedding = search_methods_need_embedding(&request.config.search_methods);
    let _ =
        ensure_query_embedding(&request.query, &mut request.query_vector, needs_embedding).await;

    let mut engine = state.create_search_engine();

    // Execute node search
    let nodes = engine
        .search_nodes(
            &request.query,
            &request.config,
            &request.filters.unwrap_or_default(),
            request.query_vector.as_deref(),
            request.limit,
        )
        .await?;

    let total = nodes.len();
    let latency_ms = start.elapsed().as_millis() as u64;

    Ok(Json(NodeSearchResponse {
        nodes,
        total,
        latency_ms,
    }))
}
