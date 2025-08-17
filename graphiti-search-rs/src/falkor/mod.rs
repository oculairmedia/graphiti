use anyhow::Result;
use async_trait::async_trait;
use deadpool::managed::{Manager, Object, Pool, RecycleResult};
use std::sync::Arc;
use tracing::{debug, info};

use crate::config::Config;
use crate::error::{SearchError, SearchResult};

pub mod client;
pub mod client_v2;
pub mod parser;
pub mod parser_v2;
pub mod queries;

// Keep old client for backward compatibility but allow it to be unused
#[allow(unused_imports)]
pub use self::client::FalkorClient;
pub use self::client_v2::FalkorClientV2;

pub type FalkorPool = Pool<FalkorManager>;
pub type FalkorConnection = Object<FalkorManager>;

pub struct FalkorManager {
    config: Arc<Config>,
}

impl FalkorManager {
    pub fn new(config: &Config) -> Self {
        Self {
            config: Arc::new(config.clone()),
        }
    }
}

#[async_trait]
impl Manager for FalkorManager {
    type Type = FalkorClientV2;
    type Error = SearchError;

    async fn create(&self) -> Result<FalkorClientV2, Self::Error> {
        debug!("Creating new FalkorDB connection with SDK");
        FalkorClientV2::new(&self.config)
            .await
            .map_err(|e| SearchError::Database(format!("Failed to create connection: {e}")))
    }

    async fn recycle(
        &self,
        conn: &mut FalkorClientV2,
        _metrics: &deadpool::managed::Metrics,
    ) -> RecycleResult<Self::Error> {
        conn.ping()
            .await
            .map_err(|e| SearchError::Database(format!("Connection ping failed: {e}")))?;
        Ok(())
    }
}

pub async fn create_falkor_pool(config: &Config) -> SearchResult<FalkorPool> {
    let manager = FalkorManager::new(config);

    let pool = Pool::builder(manager)
        .max_size(config.max_connections)
        .build()
        .map_err(|e| SearchError::Database(format!("Failed to create pool: {e}")))?;

    // Test connection
    let conn = pool
        .get()
        .await
        .map_err(|e| SearchError::Database(format!("Failed to get connection: {e}")))?;
    drop(conn);

    info!(
        "FalkorDB connection pool created with {} connections",
        config.max_connections
    );
    Ok(pool)
}
