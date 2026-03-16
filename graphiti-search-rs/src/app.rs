use axum::{
    routing::{get, post},
    Router,
};
use std::time::Duration;
use tower_http::{compression::CompressionLayer, cors::CorsLayer, trace::TraceLayer};
use tracing::{info, warn};

use crate::config::Config;
use crate::falkor::FalkorPool;
use crate::handlers::{self, health_check, search_handler};
use crate::reranker::RerankerClient;
use crate::retry::RetryConfig;
use crate::search::SearchEngine;

#[derive(Clone)]
pub struct AppState {
    pub falkor_pool: FalkorPool,
    pub redis_pool: deadpool_redis::Pool,
    pub config: Config,
    pub reranker_client: Option<RerankerClient>,
}

impl AppState {
    pub fn create_search_engine(&self) -> SearchEngine {
        SearchEngine::new(
            self.falkor_pool.clone(),
            self.redis_pool.clone(),
            self.config.max_method_results,
            self.config.mmr_timeout_ms,
            self.config.max_pre_rerank_results,
            self.config.bfs_timeout_ms,
            self.config.bfs_batch_size,
            self.config.hipporag_timeout_ms,
            self.config.hipporag_batch_size,
            self.config.hipporag_hub_threshold,
            self.reranker_client.clone(),
        )
    }
}

pub fn build_reranker_client(config: &Config) -> Option<RerankerClient> {
    if !config.reranker_enabled {
        return None;
    }

    match RerankerClient::new(
        &config.reranker_url,
        config.reranker_timeout_ms,
        RetryConfig::new(
            config.reranker_max_retries,
            Duration::from_millis(config.reranker_retry_base_ms),
        ),
    ) {
        Ok(client) => {
            info!("RerankerClient initialized for {}", config.reranker_url);
            Some(client)
        }
        Err(error) => {
            warn!("Failed to create reranker client: {}", error);
            None
        }
    }
}

pub fn create_router(state: AppState) -> Router {
    Router::new()
        .route("/health", get(health_check))
        .route("/search", post(search_handler))
        .route("/search/edges", post(handlers::edge_search_handler))
        .route("/search/nodes", post(handlers::node_search_handler))
        .route("/search/episodes", post(handlers::episode_search_handler))
        .route(
            "/search/communities",
            post(handlers::community_search_handler),
        )
        .layer(CompressionLayer::new())
        .layer(CorsLayer::permissive())
        .layer(TraceLayer::new_for_http())
        .with_state(state)
}
