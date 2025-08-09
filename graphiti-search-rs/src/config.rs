use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::env;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    pub port: u16,
    pub falkor_host: String,
    pub falkor_port: u16,
    pub graph_name: String,
    pub redis_url: String,
    pub max_connections: usize,
    pub cache_ttl: u64,
    pub enable_simd: bool,
    pub parallel_threshold: usize,
}

impl Config {
    pub fn from_env() -> Result<Self> {
        Ok(Config {
            port: env::var("PORT")
                .unwrap_or_else(|_| "3004".to_string())
                .parse()?,
            falkor_host: env::var("FALKORDB_HOST").unwrap_or_else(|_| "localhost".to_string()),
            falkor_port: env::var("FALKORDB_PORT")
                .unwrap_or_else(|_| "6379".to_string())
                .parse()?,
            graph_name: env::var("GRAPH_NAME").unwrap_or_else(|_| "graphiti_migration".to_string()),
            redis_url: env::var("REDIS_URL")
                .unwrap_or_else(|_| "redis://localhost:6379".to_string()),
            max_connections: env::var("MAX_CONNECTIONS")
                .unwrap_or_else(|_| "200".to_string()) // Increased from 32 for better throughput
                .parse()?,
            cache_ttl: env::var("CACHE_TTL")
                .unwrap_or_else(|_| "300".to_string())
                .parse()?,
            enable_simd: env::var("ENABLE_SIMD")
                .unwrap_or_else(|_| "true".to_string())
                .parse()?,
            parallel_threshold: env::var("PARALLEL_THRESHOLD")
                .unwrap_or_else(|_| "100".to_string())
                .parse()?,
        })
    }
}
