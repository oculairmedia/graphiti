use axum::{extract::State, Json};
use serde::{Deserialize, Serialize};
use tracing::instrument;

use crate::error::SearchResult;
use crate::models::{Community, CommunitySearchConfig, SearchFilters};
use crate::search::SearchEngine;
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
    Json(request): Json<CommunitySearchRequest>,
) -> SearchResult<Json<CommunitySearchResponse>> {
    let start = std::time::Instant::now();

    // Create search engine with pools
    let mut engine = SearchEngine::new(state.falkor_pool.clone(), state.redis_pool.clone());

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
