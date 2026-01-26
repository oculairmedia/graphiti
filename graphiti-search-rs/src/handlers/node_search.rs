use axum::{extract::State, Json};
use serde::{Deserialize, Serialize};
use tracing::{error, info, instrument};

use crate::embeddings::EMBEDDER;
use crate::error::SearchResult;
use crate::models::{Node, NodeSearchConfig, SearchFilters};
use crate::search::SearchEngine;
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
        reranker_client,
    );

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
