use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};
use serde_json::json;
use tracing::{error, info, instrument};

use crate::embeddings::{l2_normalize_embedding, EMBEDDER};
use crate::error::SearchResult;
use crate::models::{SearchMethod, SearchRequest, SearchResults};
use crate::AppState;

pub mod community_search;
pub mod edge_search;
pub mod episode_search;
pub mod node_search;

pub use community_search::community_search_handler;
pub use edge_search::edge_search_handler;
pub use episode_search::episode_search_handler;
pub use node_search::node_search_handler;

pub(crate) fn search_methods_need_embedding(methods: &[SearchMethod]) -> bool {
    methods
        .iter()
        .any(|method| matches!(method, SearchMethod::Similarity | SearchMethod::Hipporag))
}

pub(crate) fn search_request_needs_embedding(request: &SearchRequest) -> bool {
    request
        .config
        .edge_config
        .as_ref()
        .is_some_and(|config| search_methods_need_embedding(&config.search_methods))
        || request
            .config
            .node_config
            .as_ref()
            .is_some_and(|config| search_methods_need_embedding(&config.search_methods))
        || request.config.community_config.is_some()
}

pub(crate) async fn ensure_query_embedding(
    query: &str,
    query_vector: &mut Option<Vec<f32>>,
    needs_embedding: bool,
) -> Vec<String> {
    let mut warnings = Vec::new();

    if !needs_embedding {
        return warnings;
    }

    if query_vector.is_none() && !query.is_empty() {
        info!("Generating embedding for query: {}", query);
        match EMBEDDER.generate_embedding(query).await {
            Ok(Some(embedding)) => {
                info!("Generated embedding with {} dimensions", embedding.len());
                *query_vector = Some(embedding);
            }
            Ok(None) => {
                let warning = "Embedding service returned no vector; embedding-backed search methods were skipped".to_string();
                info!("{}", warning);
                warnings.push(warning);
            }
            Err(e) => {
                let warning = format!(
                    "Embedding generation failed; embedding-backed search methods were skipped: {}",
                    e
                );
                error!("{}", warning);
                warnings.push(warning);
            }
        }
    }

    if let Some(embedding) = query_vector.as_mut() {
        match l2_normalize_embedding(embedding) {
            Some(norm) => info!("Normalized query embedding (l2_norm={:.6})", norm),
            None => info!("Skipping query embedding normalization (zero or non-finite norm)"),
        }
    }

    warnings
}

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
    Json(mut request): Json<SearchRequest>,
) -> SearchResult<Json<SearchResults>> {
    info!("Processing search request for query: {}", request.query);

    let needs_embedding = search_request_needs_embedding(&request);
    let embedding_warnings =
        ensure_query_embedding(&request.query, &mut request.query_vector, needs_embedding).await;

    let mut engine = state.create_search_engine();

    // Execute search
    let mut results = engine.search(request).await?;
    if !embedding_warnings.is_empty() {
        results.degraded = true;
        results.warnings.extend(embedding_warnings);
    }

    info!(
        "Search completed - edges: {}, nodes: {}, episodes: {}, communities: {}, latency: {}ms, degraded: {}, warnings: {}",
        results.edges.len(),
        results.nodes.len(),
        results.episodes.len(),
        results.communities.len(),
        results.latency_ms,
        results.degraded,
        results.warnings.len()
    );

    Ok(Json(results))
}
