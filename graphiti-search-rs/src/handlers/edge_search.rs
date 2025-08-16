use axum::{extract::State, Json};
use serde::{Deserialize, Serialize};
use tracing::{error, info, instrument};

use crate::embeddings::EMBEDDER;
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
    Json(mut request): Json<EdgeSearchRequest>,
) -> SearchResult<Json<EdgeSearchResponse>> {
    let start = std::time::Instant::now();

    // Generate embedding if not provided and similarity search is requested
    if request.query_vector.is_none() 
        && !request.query.is_empty() 
        && request.config.search_methods.iter().any(|m| matches!(m, crate::models::SearchMethod::Similarity)) 
    {
        info!("Generating embedding for query: {}", request.query);
        match EMBEDDER.generate_embedding(&request.query).await {
            Ok(Some(embedding)) => {
                info!("Generated embedding with {} dimensions", embedding.len());
                request.query_vector = Some(embedding);
            }
            Ok(None) => {
                info!("No embedding generated, continuing without similarity search");
            }
            Err(e) => {
                error!("Failed to generate embedding: {}, continuing without it", e);
            }
        }
    }

    // Create search engine with pools
    let mut engine = SearchEngine::new(state.falkor_pool.clone(), state.redis_pool.clone());

    // Execute edge search
    let edges = engine
        .search_edges(
            &request.query,
            &request.config,
            &request.filters.unwrap_or_default(),
            request.query_vector.as_deref(),
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
