#![allow(clippy::uninlined_format_args)]

use anyhow::Result;
use graphiti_search_rs::{
    app::{build_reranker_client, AppState},
    config::Config,
    create_router,
    falkor::create_falkor_pool,
};
use std::net::SocketAddr;
use tracing::info;
use tracing_subscriber::{filter::EnvFilter, FmtSubscriber};

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
    let falkor_pool = create_falkor_pool(&config).await?;
    info!("FalkorDB connection pool initialized");

    // Initialize Redis connection pool
    let redis_config = deadpool_redis::Config::from_url(config.redis_url.clone());
    let redis_pool = redis_config.create_pool(Some(deadpool_redis::Runtime::Tokio1))?;
    info!("Redis connection pool initialized");

    // Create reranker client once (connection pooling)
    let reranker_client = build_reranker_client(&config);

    // Create application state
    let state = AppState {
        falkor_pool,
        redis_pool,
        config: config.clone(),
        reranker_client,
    };

    // Build router
    let app = create_router(state);

    // Start server
    let addr = SocketAddr::from(([0, 0, 0, 0], config.port));
    info!("🚀 Server starting on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}
