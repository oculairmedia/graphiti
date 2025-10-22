use once_cell::sync::Lazy;
use prometheus::{
    register_histogram_vec, register_int_counter_vec, register_int_gauge_vec, Encoder,
    HistogramVec, IntCounterVec, IntGaugeVec, TextEncoder,
};
use std::time::Duration;

const DIRECTION_LABEL: [&str; 1] = ["direction"];

static SYNC_ATTEMPTS: Lazy<IntCounterVec> = Lazy::new(|| {
    register_int_counter_vec!(
        "graphiti_sync_attempts_total",
        "Number of sync attempts by direction",
        &DIRECTION_LABEL
    )
    .expect("register sync attempts counter")
});

static SYNC_SUCCESSES: Lazy<IntCounterVec> = Lazy::new(|| {
    register_int_counter_vec!(
        "graphiti_sync_success_total",
        "Number of successful syncs by direction",
        &DIRECTION_LABEL
    )
    .expect("register sync success counter")
});

static SYNC_FAILURES: Lazy<IntCounterVec> = Lazy::new(|| {
    register_int_counter_vec!(
        "graphiti_sync_failure_total",
        "Number of failed syncs by direction",
        &DIRECTION_LABEL
    )
    .expect("register sync failure counter")
});

static SYNC_NODES: Lazy<IntCounterVec> = Lazy::new(|| {
    register_int_counter_vec!(
        "graphiti_sync_nodes_total",
        "Total nodes processed by direction",
        &DIRECTION_LABEL
    )
    .expect("register sync nodes counter")
});

static SYNC_EDGES: Lazy<IntCounterVec> = Lazy::new(|| {
    register_int_counter_vec!(
        "graphiti_sync_edges_total",
        "Total edges processed by direction",
        &DIRECTION_LABEL
    )
    .expect("register sync edges counter")
});

static SYNC_DURATION: Lazy<HistogramVec> = Lazy::new(|| {
    register_histogram_vec!(
        "graphiti_sync_duration_seconds",
        "Sync duration in seconds by direction",
        &DIRECTION_LABEL,
        vec![1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0]
    )
    .expect("register sync duration histogram")
});

static SYNC_ACTIVE: Lazy<IntGaugeVec> = Lazy::new(|| {
    register_int_gauge_vec!(
        "graphiti_sync_active",
        "Gauge of active sync operations by direction",
        &DIRECTION_LABEL
    )
    .expect("register sync active gauge")
});

pub fn record_start(direction: &str) {
    SYNC_ATTEMPTS.with_label_values(&[direction]).inc();
    SYNC_ACTIVE.with_label_values(&[direction]).inc();
}

pub fn record_success(direction: &str, nodes: usize, edges: usize, duration: Duration) {
    SYNC_SUCCESSES.with_label_values(&[direction]).inc();
    SYNC_NODES
        .with_label_values(&[direction])
        .inc_by(nodes as u64);
    SYNC_EDGES
        .with_label_values(&[direction])
        .inc_by(edges as u64);
    SYNC_DURATION
        .with_label_values(&[direction])
        .observe(duration.as_secs_f64());
    SYNC_ACTIVE.with_label_values(&[direction]).dec();
}

pub fn record_failure(direction: &str, duration: Duration) {
    SYNC_FAILURES.with_label_values(&[direction]).inc();
    SYNC_DURATION
        .with_label_values(&[direction])
        .observe(duration.as_secs_f64());
    SYNC_ACTIVE.with_label_values(&[direction]).dec();
}

pub fn gather() -> Result<String, String> {
    let encoder = TextEncoder::new();
    let metric_families = prometheus::gather();

    let mut buffer = Vec::new();
    encoder
        .encode(&metric_families, &mut buffer)
        .map_err(|e| e.to_string())?;

    String::from_utf8(buffer).map_err(|e| e.to_string())
}
