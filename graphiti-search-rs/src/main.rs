use anyhow::Result;
use axum::{
    routing::{get, post},
    Router,
};
use std::net::SocketAddr;
use tower_http::{compression::CompressionLayer, cors::CorsLayer, trace::TraceLayer};
use tracing::{info, Level};
use tracing_subscriber::{filter::EnvFilter, FmtSubscriber};

mod config;
mod error;
mod falkor;
mod handlers;
mod models;
mod search;

use crate::config::Config;
use crate::falkor::FalkorPool;
use crate::handlers::{health_check, search_handler};

#[derive(Clone)]
pub struct AppState {
    pub falkor_pool: FalkorPool,
    pub redis_pool: deadpool_redis::Pool,
    pub config: Config,
}

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize tracing
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("graphiti_search=debug,info"));

    let subscriber = FmtSubscriber::builder()
        .with_env_filter(filter)
        .with_target(false)
        .with_thread_ids(true)
        .with_line_number(true)
        .finish();

    tracing::subscriber::set_global_default(subscriber)?;

    info!("Starting Graphiti Search Service");

    // Load configuration
    let config = Config::from_env()?;
    info!("Configuration loaded");

    // Initialize FalkorDB connection pool
    let falkor_pool = FalkorPool::new(&config).await?;
    info!("FalkorDB connection pool initialized");

    // Initialize Redis connection pool
    let redis_config = deadpool_redis::Config {
        url: Some(config.redis_url.clone()),
        pool: Some(deadpool_redis::PoolConfig {
            max_size: 32,
            ..Default::default()
        }),
        ..Default::default()
    };
    let redis_pool = redis_config.create_pool(Some(deadpool_redis::Runtime::Tokio1))?;
    info!("Redis connection pool initialized");

    // Create application state
    let state = AppState {
        falkor_pool,
        redis_pool,
        config: config.clone(),
    };

    // Build router
    let app = Router::new()
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
        .with_state(state);

    // Start server
    let addr = SocketAddr::from(([0, 0, 0, 0], config.port));
    info!("🚀 Server starting on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}
