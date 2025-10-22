//! Data models for health check responses.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Overall health status of the service
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum HealthStatus {
    /// Service is healthy and operational
    Healthy,
    /// Service is degraded but operational
    Degraded,
    /// Service is unhealthy
    Unhealthy,
}

/// Database connectivity status
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DatabaseStatus {
    /// Database name (neo4j or falkordb)
    pub name: String,
    /// Connection status
    pub connected: bool,
    /// Optional error message
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    /// Response time in milliseconds
    #[serde(skip_serializing_if = "Option::is_none")]
    pub response_time_ms: Option<u64>,
}

/// Sync operation status
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncStatus {
    /// Current sync state (idle, running, failed)
    pub state: String,
    /// Last sync timestamp
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_sync: Option<String>,
    /// Number of items synced in last operation
    #[serde(skip_serializing_if = "Option::is_none")]
    pub items_synced: Option<usize>,
    /// Success rate (0.0 to 1.0)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub success_rate: Option<f64>,
    /// Last processed direction
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_direction: Option<String>,
    /// Nodes synced in last operation
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nodes_synced: Option<usize>,
    /// Edges synced in last operation
    #[serde(skip_serializing_if = "Option::is_none")]
    pub edges_synced: Option<usize>,
    /// Last error message
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_error: Option<String>,
}

/// Complete health check response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HealthResponse {
    /// Overall status
    pub status: HealthStatus,
    /// Service version
    pub version: String,
    /// Uptime in seconds
    pub uptime_seconds: u64,
    /// Database connectivity status
    pub databases: HashMap<String, DatabaseStatus>,
    /// Current sync status
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sync: Option<SyncStatus>,
    /// Additional metadata
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata: Option<HashMap<String, String>>,
}

impl HealthResponse {
    /// Create a new healthy response
    pub fn healthy(version: String, uptime_seconds: u64) -> Self {
        Self {
            status: HealthStatus::Healthy,
            version,
            uptime_seconds,
            databases: HashMap::new(),
            sync: None,
            metadata: None,
        }
    }

    /// Create a new unhealthy response
    pub fn unhealthy(version: String, uptime_seconds: u64, reason: String) -> Self {
        let mut metadata = HashMap::new();
        metadata.insert("reason".to_string(), reason);

        Self {
            status: HealthStatus::Unhealthy,
            version,
            uptime_seconds,
            databases: HashMap::new(),
            sync: None,
            metadata: Some(metadata),
        }
    }

    /// Add database status
    pub fn with_database(mut self, name: String, status: DatabaseStatus) -> Self {
        self.databases.insert(name, status);
        self
    }

    /// Add sync status
    pub fn with_sync(mut self, sync: SyncStatus) -> Self {
        self.sync = Some(sync);
        self
    }

    /// Update overall status based on database health
    pub fn compute_status(&mut self) {
        let all_connected = self.databases.values().all(|db| db.connected);

        if !all_connected {
            let any_connected = self.databases.values().any(|db| db.connected);
            self.status = if any_connected {
                HealthStatus::Degraded
            } else {
                HealthStatus::Unhealthy
            };
        }
    }
}
