use axum::{extract::State, Json};
use serde::{Deserialize, Serialize};
use tracing::instrument;

use crate::error::SearchResult;
use crate::models::{Episode, SearchFilters};
use crate::search::SearchEngine;
use crate::AppState;

#[derive(Debug, Deserialize)]
pub struct EpisodeSearchRequest {
    pub query: String,
    pub filters: Option<SearchFilters>,
    pub limit: Option<usize>,
}

#[derive(Debug, Serialize)]
pub struct EpisodeSearchResponse {
    pub episodes: Vec<Episode>,
    pub total: usize,
    pub latency_ms: u64,
}

#[instrument(skip(state))]
pub async fn episode_search_handler(
    State(state): State<AppState>,
    Json(request): Json<EpisodeSearchRequest>,
) -> SearchResult<Json<EpisodeSearchResponse>> {
    let start = std::time::Instant::now();

    // Get database connection
    let falkor_conn = state.falkor_pool.get().await.map_err(|e| {
        crate::error::SearchError::Database(format!("Failed to get database connection: {}", e))
    })?;

    // Create search engine
    let mut engine = SearchEngine::new(falkor_conn, state.redis_pool.clone());

    // Execute episode search
    let episodes = engine
        .search_episodes(
            &request.query,
            &request.filters.unwrap_or_default(),
            request.limit.unwrap_or(100),
        )
        .await?;

    let total = episodes.len();
    let latency_ms = start.elapsed().as_millis() as u64;

    Ok(Json(EpisodeSearchResponse {
        episodes,
        total,
        latency_ms,
    }))
}
