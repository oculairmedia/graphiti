pub mod config;
pub mod embeddings;
pub mod error;
pub mod falkor;
pub mod handlers;
pub mod models;
pub mod search;

// Re-export AppState
#[derive(Clone)]
pub struct AppState {
    pub falkor_pool: falkor::FalkorPool,
    pub redis_pool: deadpool_redis::Pool,
    pub config: config::Config,
}
