//! HTTP server for health checks and monitoring.

use axum::{routing::get, Extension, Router};
use std::net::SocketAddr;
use tokio::task::JoinHandle;
use tower::make::Shared;
use tower_http::trace::TraceLayer;
use tracing::{error, info};

use super::handlers::{health_check, liveness, metrics_endpoint, readiness, HealthState};
use crate::config::Settings;
use crate::error::Result;

/// Health check HTTP server
pub struct HealthServer {
    /// Server address
    addr: SocketAddr,
    /// Server handle
    handle: Option<JoinHandle<()>>,
    /// Health state
    state: HealthState,
    /// Primary health endpoint path
    primary_path: String,
}

impl HealthServer {
    /// Create a new health server
    ///
    /// # Arguments
    ///
    /// * `config` - Service configuration
    /// * `port` - Port to listen on (default: 8080)
    pub fn new(config: Settings, port: Option<u16>) -> Self {
        let bind_port = port.unwrap_or(config.health.port);
        let addr = SocketAddr::from(([0, 0, 0, 0], bind_port));
        let primary_path = config.health.path.clone();
        let state = HealthState::new(config);

        Self {
            addr,
            handle: None,
            state,
            primary_path,
        }
    }

    /// Start the health check server
    pub async fn start(&mut self) -> Result<()> {
        info!("Starting health check server on {}", self.addr);

        // Build router with health endpoints
        let primary_route = self.primary_path.clone();

        let mut app = Router::new()
            .route("/healthz", get(health_check))
            .route("/live", get(liveness))
            .route("/ready", get(readiness))
            .route("/metrics", get(metrics_endpoint))
            .layer(TraceLayer::new_for_http())
            .layer(Extension(self.state.clone()));

        app = app.route(primary_route.as_str(), get(health_check));

        if primary_route != "/health" {
            app = app.route("/health", get(health_check));
        }

        // Spawn server task
        let addr = self.addr;
        let listener = tokio::net::TcpListener::bind(addr).await.map_err(|e| {
            crate::error::SyncError::Orchestration(format!("Failed to bind health server: {}", e))
        })?;

        info!("Health check server listening on {}", addr);

        let service = app.into_service();
        let make_service = Shared::new(service);

        let handle = tokio::spawn(async move {
            if let Err(e) = axum::serve(listener, make_service).await {
                error!("Health server error: {}", e);
            }
        });

        self.handle = Some(handle);

        Ok(())
    }

    /// Stop the health check server
    pub async fn stop(&mut self) {
        if let Some(handle) = self.handle.take() {
            info!("Stopping health check server");
            handle.abort();
        }
    }

    /// Check if server is running
    pub fn is_running(&self) -> bool {
        self.handle.is_some()
    }
}

impl Drop for HealthServer {
    fn drop(&mut self) {
        if let Some(handle) = self.handle.take() {
            handle.abort();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::settings::{
        FalkorDBConfig, HealthConfig, MetricsConfig, Neo4jConfig, SyncConfig,
    };

    #[tokio::test]
    async fn test_health_server_creation() {
        let config = Settings {
            neo4j: Neo4jConfig {
                uri: "bolt://localhost:7687".to_string(),
                user: "neo4j".to_string(),
                password: "password".to_string(),
                database: "neo4j".to_string(),
                pool_size: 10,
            },
            falkordb: FalkorDBConfig {
                host: "localhost".to_string(),
                port: 6379,
                database: "test".to_string(),
            },
            sync: SyncConfig {
                batch_size: 1000,
                max_query_limit: 10000,
                interval_seconds: 60,
                query_timeout_ms: 30_000,
                operation_timeout_seconds: 120,
                retry_attempts: 3,
                retry_backoff_ms: 500,
                parallel_workers: 4,
            },
            health: HealthConfig {
                port: 0,
                path: "/health".to_string(),
            },
            metrics: MetricsConfig { port: 0 },
        };

        let server = HealthServer::new(config, Some(0)); // Use port 0 for random port
        assert!(!server.is_running());
    }
}
