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

    // Generate embedding if not provided and similarity search is requested
    if request.query_vector.is_none()
        && !request.query.is_empty()
        && request
            .config
            .search_methods
            .iter()
            .any(|m| matches!(m, crate::models::SearchMethod::Similarity))
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

    // Normalize query embedding for cosine similarity search.
    // Stored embeddings are typically unit-normalized; normalizing the query improves ANN search behavior.
    if request
        .config
        .search_methods
        .iter()
        .any(|m| matches!(m, crate::models::SearchMethod::Similarity))
    {
        if let Some(embedding) = request.query_vector.as_mut() {
            match crate::embeddings::l2_normalize_embedding(embedding) {
                Some(norm) => info!("Normalized query embedding (l2_norm={:.6})", norm),
                None => info!("Skipping query embedding normalization (zero or non-finite norm)"),
            }
        }
    }

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
        state.config.hipporag_timeout_ms,
        state.config.hipporag_batch_size,
        state.config.hipporag_hub_threshold,
        reranker_client,
    );

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
