use anyhow::{ensure, Result};
use serde::{Deserialize, Serialize};
use std::{env, str::FromStr};

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
    pub embedding_dimension: usize,
    pub max_method_results: usize,

    /// Enable cross-encoder reranking
    pub reranker_enabled: bool,
    /// URL of the cross-encoder reranker service
    pub reranker_url: String,
    /// Timeout for reranker requests (ms)
    pub reranker_timeout_ms: u64,
    /// Max reranker HTTP attempts including the first try
    pub reranker_max_retries: u32,
    /// Base reranker retry backoff in milliseconds
    pub reranker_retry_base_ms: u64,

    /// Timeout for MMR reranking computation (ms) - prevents O(n²) explosion
    pub mmr_timeout_ms: u64,
    /// Maximum total results before reranking - caps O(n²) input size
    pub max_pre_rerank_results: usize,

    /// Timeout for BFS traversal (ms) - prevents runaway graph exploration
    pub bfs_timeout_ms: u64,
    /// Maximum nodes to expand per batch in BFS - controls DB query batching
    pub bfs_batch_size: usize,

    /// Timeout for HippoRAG spreading activation (ms)
    pub hipporag_timeout_ms: u64,
    /// Maximum nodes to expand per batch in HippoRAG
    pub hipporag_batch_size: usize,
    /// Hub degree threshold for HippoRAG - limits neighbors from high-degree nodes
    pub hipporag_hub_threshold: usize,
}

impl Config {
    pub fn from_env() -> Result<Self> {
        Self::from_var_lookup(|key| env::var(key).ok())
    }

    pub fn test_defaults() -> Self {
        Self::from_var_lookup(|_| None).expect("default test config should parse")
    }

    fn from_var_lookup<F>(get_var: F) -> Result<Self>
    where
        F: Fn(&str) -> Option<String>,
    {
        let config = Config {
            port: parse_var(&get_var, "PORT", "3004")?,
            falkor_host: var_or_default(&get_var, "FALKORDB_HOST", "localhost"),
            falkor_port: parse_var(&get_var, "FALKORDB_PORT", "6379")?,
            graph_name: var_or_default(&get_var, "GRAPH_NAME", "graphiti_migration"),
            redis_url: var_or_default(&get_var, "REDIS_URL", "redis://localhost:6379"),
            max_connections: parse_var(&get_var, "MAX_CONNECTIONS", "200")?,
            cache_ttl: parse_var(&get_var, "CACHE_TTL", "300")?,
            enable_simd: parse_var(&get_var, "ENABLE_SIMD", "true")?,
            parallel_threshold: parse_var(&get_var, "PARALLEL_THRESHOLD", "100")?,
            embedding_dimension: parse_var(&get_var, "EMBEDDING_DIMENSION", "2560")?,
            max_method_results: parse_var(&get_var, "MAX_METHOD_RESULTS", "200")?,
            reranker_enabled: var_or_default(&get_var, "RERANKER_ENABLED", "true").to_lowercase()
                == "true",
            reranker_url: var_or_default(&get_var, "RERANKER_URL", "http://100.81.139.20:11435"),
            reranker_timeout_ms: parse_var(&get_var, "RERANKER_TIMEOUT_MS", "5000")?,
            reranker_max_retries: parse_var(&get_var, "RERANKER_MAX_RETRIES", "3")?,
            reranker_retry_base_ms: parse_var(&get_var, "RERANKER_RETRY_BASE_MS", "200")?,
            mmr_timeout_ms: parse_var(&get_var, "MMR_TIMEOUT_MS", "5000")?,
            max_pre_rerank_results: parse_var(&get_var, "MAX_PRE_RERANK_RESULTS", "500")?,
            bfs_timeout_ms: parse_var(&get_var, "BFS_TIMEOUT_MS", "10000")?,
            bfs_batch_size: parse_var(&get_var, "BFS_BATCH_SIZE", "50")?,
            hipporag_timeout_ms: parse_var(&get_var, "HIPPORAG_TIMEOUT_MS", "10000")?,
            hipporag_batch_size: parse_var(&get_var, "HIPPORAG_BATCH_SIZE", "50")?,
            hipporag_hub_threshold: parse_var(&get_var, "HIPPORAG_HUB_THRESHOLD", "200")?,
        };

        config.validate()?;
        Ok(config)
    }

    fn validate(&self) -> Result<()> {
        ensure!(self.port > 0, "PORT must be greater than 0");
        ensure!(self.falkor_port > 0, "FALKORDB_PORT must be greater than 0");
        ensure!(
            self.max_connections > 0,
            "MAX_CONNECTIONS must be greater than 0"
        );
        ensure!(
            self.parallel_threshold > 0,
            "PARALLEL_THRESHOLD must be greater than 0"
        );
        ensure!(
            self.embedding_dimension > 0,
            "EMBEDDING_DIMENSION must be greater than 0"
        );
        ensure!(
            self.max_method_results > 0,
            "MAX_METHOD_RESULTS must be greater than 0"
        );
        ensure!(self.cache_ttl > 0, "CACHE_TTL must be greater than 0");
        ensure!(
            self.reranker_timeout_ms > 0,
            "RERANKER_TIMEOUT_MS must be greater than 0"
        );
        ensure!(
            self.reranker_max_retries > 0,
            "RERANKER_MAX_RETRIES must be greater than 0"
        );
        ensure!(
            self.reranker_retry_base_ms > 0,
            "RERANKER_RETRY_BASE_MS must be greater than 0"
        );
        ensure!(
            self.mmr_timeout_ms > 0,
            "MMR_TIMEOUT_MS must be greater than 0"
        );
        ensure!(
            self.max_pre_rerank_results > 0,
            "MAX_PRE_RERANK_RESULTS must be greater than 0"
        );
        ensure!(
            self.bfs_timeout_ms > 0,
            "BFS_TIMEOUT_MS must be greater than 0"
        );
        ensure!(
            self.bfs_batch_size > 0,
            "BFS_BATCH_SIZE must be greater than 0"
        );
        ensure!(
            self.hipporag_timeout_ms > 0,
            "HIPPORAG_TIMEOUT_MS must be greater than 0"
        );
        ensure!(
            self.hipporag_batch_size > 0,
            "HIPPORAG_BATCH_SIZE must be greater than 0"
        );
        ensure!(
            self.hipporag_hub_threshold > 0,
            "HIPPORAG_HUB_THRESHOLD must be greater than 0"
        );
        Ok(())
    }
}

fn var_or_default<F>(get_var: &F, key: &str, default: &str) -> String
where
    F: Fn(&str) -> Option<String>,
{
    get_var(key).unwrap_or_else(|| default.to_string())
}

fn parse_var<T, F>(get_var: &F, key: &str, default: &str) -> Result<T>
where
    T: FromStr,
    T::Err: std::error::Error + Send + Sync + 'static,
    F: Fn(&str) -> Option<String>,
{
    Ok(var_or_default(get_var, key, default).parse()?)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    #[test]
    fn uses_expected_defaults_when_env_is_missing() {
        let config = Config::from_var_lookup(|_| None).expect("defaults should parse");

        assert_eq!(config.port, 3004);
        assert_eq!(config.falkor_host, "localhost");
        assert_eq!(config.falkor_port, 6379);
        assert_eq!(config.graph_name, "graphiti_migration");
        assert_eq!(config.redis_url, "redis://localhost:6379");
        assert_eq!(config.embedding_dimension, 2560);
        assert!(config.reranker_enabled);
        assert!(config.max_connections > 0);
        assert!(config.bfs_timeout_ms > 0);
    }

    #[test]
    fn parses_custom_values() {
        let vars = HashMap::from([
            ("PORT", "4010"),
            ("FALKORDB_HOST", "falkor"),
            ("FALKORDB_PORT", "6380"),
            ("GRAPH_NAME", "custom_graph"),
            ("REDIS_URL", "redis://cache:6379"),
            ("MAX_CONNECTIONS", "64"),
            ("CACHE_TTL", "120"),
            ("ENABLE_SIMD", "false"),
            ("PARALLEL_THRESHOLD", "12"),
            ("EMBEDDING_DIMENSION", "1024"),
            ("MAX_METHOD_RESULTS", "80"),
            ("RERANKER_ENABLED", "false"),
            ("RERANKER_URL", "http://reranker.internal"),
            ("RERANKER_TIMEOUT_MS", "2500"),
            ("RERANKER_MAX_RETRIES", "4"),
            ("RERANKER_RETRY_BASE_MS", "150"),
            ("MMR_TIMEOUT_MS", "3000"),
            ("MAX_PRE_RERANK_RESULTS", "90"),
            ("BFS_TIMEOUT_MS", "4000"),
            ("BFS_BATCH_SIZE", "25"),
            ("HIPPORAG_TIMEOUT_MS", "6000"),
            ("HIPPORAG_BATCH_SIZE", "30"),
            ("HIPPORAG_HUB_THRESHOLD", "75"),
        ]);

        let config =
            Config::from_var_lookup(|key| vars.get(key).map(|value| (*value).to_string())).unwrap();

        assert_eq!(config.port, 4010);
        assert_eq!(config.falkor_host, "falkor");
        assert_eq!(config.falkor_port, 6380);
        assert_eq!(config.graph_name, "custom_graph");
        assert_eq!(config.redis_url, "redis://cache:6379");
        assert_eq!(config.max_connections, 64);
        assert_eq!(config.cache_ttl, 120);
        assert!(!config.enable_simd);
        assert_eq!(config.parallel_threshold, 12);
        assert_eq!(config.embedding_dimension, 1024);
        assert_eq!(config.max_method_results, 80);
        assert!(!config.reranker_enabled);
        assert_eq!(config.reranker_url, "http://reranker.internal");
        assert_eq!(config.reranker_timeout_ms, 2500);
        assert_eq!(config.reranker_max_retries, 4);
        assert_eq!(config.reranker_retry_base_ms, 150);
        assert_eq!(config.mmr_timeout_ms, 3000);
        assert_eq!(config.max_pre_rerank_results, 90);
        assert_eq!(config.bfs_timeout_ms, 4000);
        assert_eq!(config.bfs_batch_size, 25);
        assert_eq!(config.hipporag_timeout_ms, 6000);
        assert_eq!(config.hipporag_batch_size, 30);
        assert_eq!(config.hipporag_hub_threshold, 75);
    }

    #[test]
    fn rejects_zero_and_invalid_numeric_values() {
        let zero_pool = HashMap::from([("MAX_CONNECTIONS", "0")]);
        let zero_error =
            Config::from_var_lookup(|key| zero_pool.get(key).map(|value| (*value).to_string()))
                .unwrap_err();
        assert!(zero_error.to_string().contains("MAX_CONNECTIONS"));

        let invalid_timeout = HashMap::from([("RERANKER_TIMEOUT_MS", "-1")]);
        assert!(Config::from_var_lookup(|key| {
            invalid_timeout.get(key).map(|value| (*value).to_string())
        })
        .is_err());
    }
}
