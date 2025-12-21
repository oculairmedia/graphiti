// Library exports for testing
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// Re-export modules
pub mod duckdb_store;
pub mod delta_tracker;
pub mod cache;
pub mod stream_consumer;  // GRAPH-107: Redis stream consumer for real-time updates
pub mod reconciliation;   // GRAPH-112: Paginated ID fetching for memory safety
// pub mod websocket; // Commented out - requires AppState from main.rs
// pub mod arrow_converter; // Commented out - not needed for tests

// Core data structures
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Node {
    pub id: String,
    pub label: String,
    pub node_type: String,
    pub summary: Option<String>,
    pub properties: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Edge {
    pub from: String,
    pub to: String,
    pub edge_type: String,
    pub weight: f64,
}

impl Node {
    pub fn new(id: String, label: String, node_type: String) -> Self {
        Self {
            id,
            label,
            node_type,
            summary: None,
            properties: HashMap::new(),
        }
    }
}

impl Edge {
    pub fn new(from: String, to: String, edge_type: String, weight: f64) -> Self {
        Self {
            from,
            to,
            edge_type,
            weight,
        }
    }
}
