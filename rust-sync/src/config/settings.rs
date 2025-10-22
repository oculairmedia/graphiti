use config::{Config, ConfigError, Environment};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Settings {
    pub neo4j: Neo4jConfig,
    pub falkordb: FalkorDBConfig,
    pub sync: SyncConfig,
    pub health: HealthConfig,
    pub metrics: MetricsConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Neo4jConfig {
    pub uri: String,
    pub user: String,
    pub password: String,
    pub database: String,
    pub pool_size: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FalkorDBConfig {
    pub host: String,
    pub port: u16,
    pub database: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncConfig {
    pub batch_size: usize,
    pub max_query_limit: usize,
    pub interval_seconds: u64,
    pub query_timeout_ms: u64,
    pub operation_timeout_seconds: u64,
    pub retry_attempts: usize,
    pub retry_backoff_ms: u64,
    pub parallel_workers: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HealthConfig {
    pub port: u16,
    pub path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MetricsConfig {
    pub port: u16,
}

impl Settings {
    pub fn new() -> Result<Self, ConfigError> {
        let config = Config::builder()
            // Default values
            .set_default("neo4j.uri", "bolt://localhost:7687")?
            .set_default("neo4j.user", "neo4j")?
            .set_default("neo4j.password", "password")?
            .set_default("neo4j.database", "neo4j")?
            .set_default("neo4j.pool_size", 10)?
            .set_default("falkordb.host", "localhost")?
            .set_default("falkordb.port", 6379)?
            .set_default("falkordb.database", "graphiti")?
            .set_default("sync.batch_size", 400)?
            .set_default("sync.max_query_limit", 1000000)?
            .set_default("sync.interval_seconds", 180)?
            .set_default("sync.query_timeout_ms", 300000)? // 5 minutes
            .set_default("sync.operation_timeout_seconds", 3600)? // 1 hour
            .set_default("sync.retry_attempts", 3)?
            .set_default("sync.retry_backoff_ms", 500)?
            .set_default("sync.parallel_workers", 4)?
            .set_default("health.port", 8080)?
            .set_default("health.path", "/health")?
            .set_default("metrics.port", 8081)?
            // Override with environment variables (with prefix SYNC_)
            .add_source(Environment::with_prefix("SYNC").separator("_"))
            .build()?;

        config.try_deserialize()
    }
}

impl Default for Settings {
    fn default() -> Self {
        Self::new().expect("Failed to load default settings")
    }
}
