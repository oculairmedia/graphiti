use graphiti_centrality::server;
use graphiti_centrality::models::DatabaseConfig;
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

    tracing::subscriber::set_global_default(subscriber)
        .map_err(|e| anyhow::anyhow!("Failed to set tracing subscriber: {}", e))?;

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
    info!("Creating application state with database connection...");
    let state = match server::AppState::new(config).await {
        Ok(state) => {
            info!("✅ Database connection successful");
            state
        },
        Err(e) => {
            info!("❌ Database connection failed: {}", e);
            return Err(anyhow::anyhow!("Database connection failed: {}", e));
        }
    };

    // Create router
    info!("Creating HTTP router...");
    let app = server::create_router(state);

    // Start server
    let bind_addr = env::var("BIND_ADDR").unwrap_or_else(|_| "0.0.0.0:3003".to_string());
    info!("🚀 Server starting on {}", bind_addr);

    let listener = match tokio::net::TcpListener::bind(&bind_addr).await {
        Ok(listener) => {
            info!("✅ TCP listener bound successfully");
            listener
        },
        Err(e) => {
            info!("❌ Failed to bind TCP listener: {}", e);
            return Err(anyhow::anyhow!("Failed to bind TCP listener: {}", e));
        }
    };
    
    info!("🌐 Starting HTTP server...");
    axum::serve(listener, app).await
        .map_err(|e| anyhow::anyhow!("HTTP server error: {}", e))?;
    info!("Server stopped");

    Ok(())
}