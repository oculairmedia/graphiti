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
    let reranker_client = if state.config.reranker_enabled {
        match crate::reranker::RerankerClient::new(
            &state.config.reranker_url,
            state.config.reranker_timeout_ms,
        ) {
            Ok(client) => Some(client),
            Err(e) => {
                tracing::warn!("Failed to init reranker client (disabled): {}", e);
                None
            }
        }
    } else {
        None
    };

    let mut engine = SearchEngine::new(
        state.falkor_pool.clone(),
        state.redis_pool.clone(),
        state.config.max_method_results,
        state.config.mmr_timeout_ms,
        state.config.max_pre_rerank_results,
        state.config.bfs_timeout_ms,
        state.config.bfs_batch_size,
        reranker_client,
    );

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
