use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Request for PageRank calculation
#[derive(Debug, Deserialize)]
pub struct PageRankRequest {
    pub group_id: Option<String>,
    #[serde(default = "default_damping_factor")]
    pub damping_factor: f64,
    #[serde(default = "default_iterations")]
    pub iterations: u32,
    #[serde(default = "default_store_results")]
    pub store_results: bool,
}

/// Request for degree centrality calculation
#[derive(Debug, Deserialize)]
pub struct DegreeRequest {
    pub group_id: Option<String>,
    #[serde(default = "default_direction")]
    pub direction: String,
    #[serde(default = "default_store_results")]
    pub store_results: bool,
}

/// Request for betweenness centrality calculation
#[derive(Debug, Deserialize)]
pub struct BetweennessRequest {
    pub group_id: Option<String>,
    pub sample_size: Option<u32>,
    #[serde(default = "default_store_results")]
    pub store_results: bool,
}

/// Request for all centralities calculation
#[derive(Debug, Deserialize)]
pub struct AllCentralitiesRequest {
    pub group_id: Option<String>,
    #[serde(default = "default_store_results")]
    pub store_results: bool,
}

/// Response for single centrality metric
#[derive(Debug, Serialize)]
pub struct CentralityResponse {
    pub scores: HashMap<String, f64>,
    pub metric: String,
    pub nodes_processed: usize,
    pub execution_time_ms: u128,
}

/// Response for all centralities
#[derive(Debug, Serialize)]
pub struct AllCentralitiesResponse {
    pub scores: HashMap<String, HashMap<String, f64>>,
    pub nodes_processed: usize,
    pub execution_time_ms: u128,
}

/// Internal representation of centrality scores
#[derive(Debug, Clone)]
pub struct CentralityScores {
    pub scores: HashMap<String, f64>,
    pub nodes_processed: usize,
}

/// Configuration for FalkorDB connection
#[derive(Debug, Clone)]
pub struct DatabaseConfig {
    pub host: String,
    pub port: u16,
    pub graph_name: String,
    pub username: Option<String>,
    pub password: Option<String>,
}

impl Default for DatabaseConfig {
    fn default() -> Self {
        Self {
            host: "falkordb".to_string(),
            port: 6379,
            graph_name: "graphiti_migration".to_string(),
            username: None,
            password: None,
        }
    }
}

// Default values for serde
fn default_damping_factor() -> f64 {
    0.85
}

fn default_iterations() -> u32 {
    20
}

fn default_direction() -> String {
    "both".to_string()
}

fn default_store_results() -> bool {
    true
}