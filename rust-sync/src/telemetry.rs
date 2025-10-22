use std::sync::{Arc, Mutex};
use std::time::Duration as StdDuration;

use chrono::{DateTime, Utc};
use once_cell::sync::Lazy;

use crate::metrics;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum SyncPhase {
    Idle,
    Running,
    Success,
    Failed,
}

#[derive(Clone, Debug)]
pub struct SyncTelemetry {
    pub phase: SyncPhase,
    pub last_direction: Option<String>,
    pub last_attempt_at: Option<DateTime<Utc>>,
    pub last_success_at: Option<DateTime<Utc>>,
    pub last_error: Option<String>,
    pub last_nodes_synced: usize,
    pub last_edges_synced: usize,
    pub success_count: usize,
    pub failure_count: usize,
}

impl SyncTelemetry {
    pub fn new() -> Self {
        Self {
            phase: SyncPhase::Idle,
            last_direction: None,
            last_attempt_at: None,
            last_success_at: None,
            last_error: None,
            last_nodes_synced: 0,
            last_edges_synced: 0,
            success_count: 0,
            failure_count: 0,
        }
    }

    pub fn success_rate(&self) -> Option<f64> {
        let total = self.success_count + self.failure_count;
        if total == 0 {
            None
        } else {
            Some(self.success_count as f64 / total as f64)
        }
    }
}

static TELEMETRY: Lazy<Arc<Mutex<SyncTelemetry>>> =
    Lazy::new(|| Arc::new(Mutex::new(SyncTelemetry::new())));

pub fn mark_sync_idle(direction: &str) {
    let mut telemetry = TELEMETRY.lock().expect("Sync telemetry mutex poisoned");
    telemetry.phase = SyncPhase::Idle;
    telemetry.last_direction = Some(direction.to_string());
    telemetry.last_attempt_at = Some(Utc::now());
}

pub fn mark_sync_start(direction: &str) {
    let mut telemetry = TELEMETRY.lock().expect("Sync telemetry mutex poisoned");
    telemetry.phase = SyncPhase::Running;
    telemetry.last_direction = Some(direction.to_string());
    telemetry.last_attempt_at = Some(Utc::now());
    telemetry.last_error = None;
    metrics::record_start(direction);
}

pub fn mark_sync_success(direction: &str, nodes: usize, edges: usize) {
    let now = Utc::now();
    let duration = {
        let mut telemetry = TELEMETRY.lock().expect("Sync telemetry mutex poisoned");
        telemetry.phase = SyncPhase::Success;
        telemetry.last_direction = Some(direction.to_string());
        telemetry.last_success_at = Some(now);
        telemetry.last_nodes_synced = nodes;
        telemetry.last_edges_synced = edges;
        telemetry.success_count += 1;
        telemetry.last_error = None;
        telemetry
            .last_attempt_at
            .and_then(|ts| (now - ts).to_std().ok())
            .unwrap_or_else(|| StdDuration::from_secs(0))
    };

    metrics::record_success(direction, nodes, edges, duration);
}

pub fn mark_sync_failure(direction: &str, error: &str) {
    let now = Utc::now();
    let duration = {
        let mut telemetry = TELEMETRY.lock().expect("Sync telemetry mutex poisoned");
        telemetry.phase = SyncPhase::Failed;
        telemetry.last_direction = Some(direction.to_string());
        telemetry.last_error = Some(error.to_string());
        telemetry.failure_count += 1;
        telemetry
            .last_attempt_at
            .and_then(|ts| (now - ts).to_std().ok())
            .unwrap_or_else(|| StdDuration::from_secs(0))
    };

    metrics::record_failure(direction, duration);
}

pub fn current_status() -> SyncTelemetry {
    TELEMETRY
        .lock()
        .expect("Sync telemetry mutex poisoned")
        .clone()
}
