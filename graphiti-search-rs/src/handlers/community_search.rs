use axum::{extract::State, Json};
use serde::{Deserialize, Serialize};
use tracing::instrument;

use super::ensure_query_embedding;
use crate::error::SearchResult;
use crate::models::{Community, CommunitySearchConfig, SearchFilters};
use crate::AppState;

#[derive(Debug, Deserialize)]
pub struct CommunitySearchRequest {
    pub query: String,
    pub config: CommunitySearchConfig,
    pub filters: Option<SearchFilters>,
    pub query_vector: Option<Vec<f32>>,
}

#[derive(Debug, Serialize)]
pub struct CommunitySearchResponse {
    pub communities: Vec<Community>,
    pub total: usize,
    pub latency_ms: u64,
}

#[instrument(skip(state))]
pub async fn community_search_handler(
    State(state): State<AppState>,
    Json(mut request): Json<CommunitySearchRequest>,
) -> SearchResult<Json<CommunitySearchResponse>> {
    let start = std::time::Instant::now();

    ensure_query_embedding(
        &request.query,
        &mut request.query_vector,
        !request.query.is_empty(),
    )
    .await;

    let mut engine = state.create_search_engine();

    // Execute community search
    let communities = engine
        .search_communities(
            &request.query,
            &request.config,
            &request.filters.unwrap_or_default(),
            request.query_vector.as_deref(),
        )
        .await?;

    let total = communities.len();
    let latency_ms = start.elapsed().as_millis() as u64;

    Ok(Json(CommunitySearchResponse {
        communities,
        total,
        latency_ms,
    }))
}
