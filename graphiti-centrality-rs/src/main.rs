use graphiti_centrality::{server, DatabaseConfig};
use std::env;
use tracing::info;
use tracing_subscriber::{filter::EnvFilter, FmtSubscriber};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Initialize tracing
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("graphiti_centrality=debug,info"));

    let subscriber = FmtSubscriber::builder()
        .with_env_filter(filter)
        .with_target(false)
        .with_thread_ids(true)
        .with_line_number(true)
        .finish();

    tracing::subscriber::set_global_default(subscriber)?;

    info!("Starting Graphiti Centrality Service");

    // Load configuration from environment variables
    let config = DatabaseConfig {
        host: env::var("FALKORDB_HOST").unwrap_or_else(|_| "falkordb".to_string()),
        port: env::var("FALKORDB_PORT")
            .unwrap_or_else(|_| "6379".to_string())
            .parse()
            .unwrap_or(6379),
        graph_name: env::var("GRAPH_NAME")
            .unwrap_or_else(|_| "graphiti_migration".to_string()),
        username: env::var("FALKORDB_USERNAME").ok(),
        password: env::var("FALKORDB_PASSWORD").ok(),
    };

    info!(
        "Connecting to FalkorDB at {}:{}, graph: {}",
        config.host, config.port, config.graph_name
    );

    // Create application state
    let state = server::AppState::new(config).await?;

    // Create router
    let app = server::create_router(state);

    // Start server
    let bind_addr = env::var("BIND_ADDR").unwrap_or_else(|_| "0.0.0.0:3001".to_string());
    info!("Server starting on {}", bind_addr);

    let listener = tokio::net::TcpListener::bind(&bind_addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}