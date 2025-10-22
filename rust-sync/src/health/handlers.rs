//! HTTP request handlers for health endpoints.

use axum::{
    extract::Extension,
    http::StatusCode,
    response::{IntoResponse, Json, Response},
};
use serde_json::json;
use std::sync::Arc;
use std::time::Instant;
use tracing::{debug, error};

use super::models::{DatabaseStatus, HealthResponse, HealthStatus, SyncStatus};
use crate::config::Settings;
use crate::telemetry::{self, SyncPhase};

/// Shared application state for health handlers
#[derive(Clone)]
pub struct HealthState {
    /// Service start time
    pub start_time: Instant,
    /// Configuration settings
    pub config: Arc<Settings>,
    /// Service version
    pub version: String,
}

impl HealthState {
    /// Create new health state
    pub fn new(config: Settings) -> Self {
        Self {
            start_time: Instant::now(),
            config: Arc::new(config),
            version: env!("CARGO_PKG_VERSION").to_string(),
        }
    }

    /// Get uptime in seconds
    pub fn uptime_seconds(&self) -> u64 {
        self.start_time.elapsed().as_secs()
    }
}

/// Health check endpoint handler
///
/// Returns 200 OK if service is healthy, 503 Service Unavailable otherwise
pub async fn health_check(Extension(state): Extension<HealthState>) -> Response {
    debug!("Health check requested");

    let mut response = HealthResponse::healthy(state.version.clone(), state.uptime_seconds());

    // Check Neo4j connectivity
    let neo4j_status = check_neo4j_connectivity(&state.config).await;
    response = response.with_database("neo4j".to_string(), neo4j_status);

    // Check FalkorDB connectivity
    let falkor_status = check_falkordb_connectivity(&state.config).await;
    response = response.with_database("falkordb".to_string(), falkor_status);

    // Update overall status based on database health
    response.compute_status();

    // Add sync status from telemetry
    let telemetry = telemetry::current_status();
    let state_str = match telemetry.phase {
        SyncPhase::Idle => "idle",
        SyncPhase::Running => "running",
        SyncPhase::Success => "success",
        SyncPhase::Failed => "failed",
    }
    .to_string();

    let last_sync = telemetry.last_success_at.map(|ts| ts.to_rfc3339());
    let items_synced = if telemetry.last_nodes_synced + telemetry.last_edges_synced > 0 {
        Some(telemetry.last_nodes_synced + telemetry.last_edges_synced)
    } else {
        None
    };

    let nodes_synced = if telemetry.last_nodes_synced > 0 {
        Some(telemetry.last_nodes_synced)
    } else {
        None
    };
    let edges_synced = if telemetry.last_edges_synced > 0 {
        Some(telemetry.last_edges_synced)
    } else {
        None
    };

    response = response.with_sync(SyncStatus {
        state: state_str,
        last_sync,
        items_synced,
        success_rate: telemetry.success_rate(),
        last_direction: telemetry.last_direction.clone(),
        nodes_synced,
        edges_synced,
        last_error: telemetry.last_error.clone(),
    });

    if matches!(telemetry.phase, SyncPhase::Failed) {
        response.status = HealthStatus::Degraded;
    }

    // Return appropriate HTTP status
    let http_status = match response.status {
        HealthStatus::Healthy => StatusCode::OK,
        HealthStatus::Degraded => StatusCode::OK,
        HealthStatus::Unhealthy => StatusCode::SERVICE_UNAVAILABLE,
    };

    (http_status, Json(response)).into_response()
}

/// Liveness probe endpoint
///
/// Simple endpoint that returns 200 OK if the service is running
pub async fn liveness(Extension(state): Extension<HealthState>) -> Response {
    debug!("Liveness probe requested");

    let response = HealthResponse::healthy(state.version.clone(), state.uptime_seconds());

    (StatusCode::OK, Json(response)).into_response()
}

/// Readiness probe endpoint
///
/// Returns 200 OK if service is ready to accept requests
pub async fn readiness(Extension(state): Extension<HealthState>) -> Response {
    debug!("Readiness probe requested");

    // Check database connectivity
    let neo4j_status = check_neo4j_connectivity(&state.config).await;
    let falkor_status = check_falkordb_connectivity(&state.config).await;

    let ready = neo4j_status.connected && falkor_status.connected;

    if ready {
        let response = HealthResponse::healthy(state.version.clone(), state.uptime_seconds());
        (StatusCode::OK, Json(response)).into_response()
    } else {
        let response = HealthResponse::unhealthy(
            state.version.clone(),
            state.uptime_seconds(),
            "Databases not ready".to_string(),
        );
        (StatusCode::SERVICE_UNAVAILABLE, Json(response)).into_response()
    }
}

/// Check Neo4j database connectivity
async fn check_neo4j_connectivity(config: &Settings) -> DatabaseStatus {
    let start = Instant::now();

    match tokio::time::timeout(
        std::time::Duration::from_secs(5),
        check_neo4j_internal(config),
    )
    .await
    {
        Ok(Ok(_)) => DatabaseStatus {
            name: "neo4j".to_string(),
            connected: true,
            error: None,
            response_time_ms: Some(start.elapsed().as_millis() as u64),
        },
        Ok(Err(e)) => {
            error!("Neo4j health check failed: {}", e);
            DatabaseStatus {
                name: "neo4j".to_string(),
                connected: false,
                error: Some(e.to_string()),
                response_time_ms: Some(start.elapsed().as_millis() as u64),
            }
        }
        Err(_) => {
            error!("Neo4j health check timed out");
            DatabaseStatus {
                name: "neo4j".to_string(),
                connected: false,
                error: Some("Connection timeout".to_string()),
                response_time_ms: Some(start.elapsed().as_millis() as u64),
            }
        }
    }
}

/// Internal Neo4j connectivity check
async fn check_neo4j_internal(config: &Settings) -> Result<(), Box<dyn std::error::Error>> {
    use neo4rs::{ConfigBuilder, Graph};

    let graph = Graph::connect(
        ConfigBuilder::default()
            .uri(&config.neo4j.uri)
            .user(&config.neo4j.user)
            .password(&config.neo4j.password)
            .db(config.neo4j.database.clone())
            .max_connections(config.neo4j.pool_size.max(1))
            .fetch_size(1)
            .build()?,
    )?;

    let mut result = graph.execute(neo4rs::query("RETURN 1 as test")).await?;

    if result.next().await?.is_some() {
        Ok(())
    } else {
        Err("No response from Neo4j".into())
    }
}

/// Check FalkorDB database connectivity
async fn check_falkordb_connectivity(config: &Settings) -> DatabaseStatus {
    let start = Instant::now();

    match tokio::time::timeout(
        std::time::Duration::from_secs(5),
        check_falkordb_internal(config),
    )
    .await
    {
        Ok(Ok(_)) => DatabaseStatus {
            name: "falkordb".to_string(),
            connected: true,
            error: None,
            response_time_ms: Some(start.elapsed().as_millis() as u64),
        },
        Ok(Err(e)) => {
            error!("FalkorDB health check failed: {}", e);
            DatabaseStatus {
                name: "falkordb".to_string(),
                connected: false,
                error: Some(e.to_string()),
                response_time_ms: Some(start.elapsed().as_millis() as u64),
            }
        }
        Err(_) => {
            error!("FalkorDB health check timed out");
            DatabaseStatus {
                name: "falkordb".to_string(),
                connected: false,
                error: Some("Connection timeout".to_string()),
                response_time_ms: Some(start.elapsed().as_millis() as u64),
            }
        }
    }
}

/// Internal FalkorDB connectivity check
async fn check_falkordb_internal(config: &Settings) -> Result<(), Box<dyn std::error::Error>> {
    use falkordb::{FalkorClientBuilder, FalkorConnectionInfo};

    // Build connection string in falkor:// format
    let connection_str = format!("falkor://{}:{}", config.falkordb.host, config.falkordb.port);

    let connection_info: FalkorConnectionInfo = connection_str.as_str().try_into()?;

    // Build async client
    let client = FalkorClientBuilder::new_async()
        .with_connection_info(connection_info)
        .build()
        .await?;

    // Select graph database
    let mut graph = client.select_graph(&config.falkordb.database);

    // Simple query to verify connectivity
    let _result = graph
        .query("RETURN 1 as test")
        .with_timeout(5000)
        .execute()
        .await?;

    Ok(())
}

/// Prometheus metrics endpoint handler
pub async fn metrics_endpoint() -> Response {
    match crate::metrics::gather() {
        Ok(body) => {
            let mut response = Response::new(body.into());
            *response.status_mut() = StatusCode::OK;
            response.headers_mut().insert(
                axum::http::header::CONTENT_TYPE,
                axum::http::HeaderValue::from_static("text/plain; version=0.0.4; charset=utf-8"),
            );
            response
        }
        Err(err) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({ "error": err })),
        )
            .into_response(),
    }
}
