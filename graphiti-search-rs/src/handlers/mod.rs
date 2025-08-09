use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};
use serde_json::json;
use tracing::{error, info, instrument};

use crate::error::SearchResult;
use crate::models::{SearchRequest, SearchResults};
use crate::search::SearchEngine;
use crate::AppState;

pub mod community_search;
pub mod edge_search;
pub mod episode_search;
pub mod node_search;

pub use community_search::community_search_handler;
pub use edge_search::edge_search_handler;
pub use episode_search::episode_search_handler;
pub use node_search::node_search_handler;

/// Health check endpoint
pub async fn health_check(State(state): State<AppState>) -> impl IntoResponse {
    // Try to get a connection from the pool
    match state.falkor_pool.get().await {
        Ok(mut conn) => {
            // Try to ping the database
            match conn.ping().await {
                Ok(_) => {
                    info!("Health check passed");
                    (
                        StatusCode::OK,
                        Json(json!({
                            "status": "healthy",
                            "service": "graphiti-search-rs",
                            "database": "connected",
                        })),
                    )
                }
                Err(e) => {
                    error!("Database ping failed: {}", e);
                    (
                        StatusCode::SERVICE_UNAVAILABLE,
                        Json(json!({
                            "status": "unhealthy",
                            "service": "graphiti-search-rs",
                            "database": "ping failed",
                            "error": e.to_string(),
                        })),
                    )
                }
            }
        }
        Err(e) => {
            error!("Failed to get database connection: {}", e);
            (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(json!({
                    "status": "unhealthy",
                    "service": "graphiti-search-rs",
                    "database": "connection failed",
                    "error": e.to_string(),
                })),
            )
        }
    }
}

/// Main search endpoint
#[instrument(skip(state))]
pub async fn search_handler(
    State(state): State<AppState>,
    Json(request): Json<SearchRequest>,
) -> SearchResult<Json<SearchResults>> {
    info!("Processing search request for query: {}", request.query);

    // Create search engine with pools
    let mut engine = SearchEngine::new(state.falkor_pool.clone(), state.redis_pool.clone());

    // Execute search
    let results = engine.search(request).await?;

    info!(
        "Search completed - edges: {}, nodes: {}, episodes: {}, communities: {}, latency: {}ms",
        results.edges.len(),
        results.nodes.len(),
        results.episodes.len(),
        results.communities.len(),
        results.latency_ms
    );

    Ok(Json(results))
}
