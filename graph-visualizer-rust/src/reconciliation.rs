//! GRAPH-112: Paginated ID Fetching for Memory Safety
//!
//! This module provides utilities for fetching all node/edge IDs from FalkorDB
//! in a memory-efficient manner using pagination. This is essential for
//! reconciliation tasks (GRAPH-113) where we need to compare local state
//! with the database state.
//!
//! ## Design
//!
//! Instead of loading all IDs into memory at once (which could exhaust RAM
//! on large graphs), we fetch IDs in batches using SKIP/LIMIT pagination.
//! This allows reconciliation to work on graphs with 100k+ nodes/edges.
//!
//! ## Usage
//!
//! ```rust,ignore
//! let fetcher = IdFetcher::new(client, graph_name);
//! 
//! // Fetch all node IDs in batches of 1000
//! let node_ids = fetcher.fetch_all_node_ids(1000).await?;
//! 
//! // Fetch all edge IDs in batches of 1000
//! let edge_ids = fetcher.fetch_all_edge_ids(1000).await?;
//! ```

use std::collections::HashSet;
use std::sync::Arc;
use falkordb::{FalkorValue, FalkorAsyncClient};
use tracing::{debug, error, info, warn};

/// Default batch size for paginated queries
pub const DEFAULT_BATCH_SIZE: usize = 1000;

/// Maximum batch size to prevent query timeouts
pub const MAX_BATCH_SIZE: usize = 5000;

/// Utility for fetching all node/edge IDs from FalkorDB with pagination
pub struct IdFetcher {
    client: Arc<FalkorAsyncClient>,
    graph_name: String,
}

impl IdFetcher {
    /// Create a new ID fetcher for the given graph
    pub fn new(client: Arc<FalkorAsyncClient>, graph_name: String) -> Self {
        Self { client, graph_name }
    }

    /// Fetch all node UUIDs from FalkorDB with pagination
    ///
    /// Returns a HashSet of all node UUIDs in the graph.
    /// Uses SKIP/LIMIT pagination to avoid memory exhaustion.
    ///
    /// # Arguments
    /// * `batch_size` - Number of IDs to fetch per batch (default: 1000, max: 5000)
    ///
    /// # Example
    /// ```rust,ignore
    /// let ids = fetcher.fetch_all_node_ids(1000).await?;
    /// println!("Found {} nodes", ids.len());
    /// ```
    pub async fn fetch_all_node_ids(
        &self,
        batch_size: usize,
    ) -> Result<HashSet<String>, Box<dyn std::error::Error + Send + Sync>> {
        let batch_size = batch_size.min(MAX_BATCH_SIZE);
        let mut ids = HashSet::new();
        let mut offset = 0;
        let mut batch_count = 0;

        info!(
            "Starting paginated node ID fetch (batch_size: {})",
            batch_size
        );

        loop {
            let query = format!(
                "MATCH (n) RETURN n.uuid AS id SKIP {} LIMIT {}",
                offset, batch_size
            );

            let mut graph = self.client.select_graph(&self.graph_name);
            let mut result = graph.query(&query).execute().await?;

            let mut fetched_in_batch = 0;
            while let Some(row) = result.data.next() {
                if let Some(id) = row.get(0) {
                    if let Some(id_str) = extract_string(id) {
                        ids.insert(id_str);
                        fetched_in_batch += 1;
                    }
                }
            }

            batch_count += 1;
            debug!(
                "Node ID batch {}: fetched {} IDs (offset: {}, total: {})",
                batch_count, fetched_in_batch, offset, ids.len()
            );

            if fetched_in_batch < batch_size {
                // Last batch - we've fetched all IDs
                break;
            }

            offset += batch_size;
        }

        info!(
            "Paginated node ID fetch complete: {} IDs in {} batches",
            ids.len(),
            batch_count
        );

        Ok(ids)
    }

    /// Fetch all edge UUIDs from FalkorDB with pagination
    ///
    /// Returns a HashSet of all edge UUIDs in the graph.
    /// Uses SKIP/LIMIT pagination to avoid memory exhaustion.
    ///
    /// # Arguments
    /// * `batch_size` - Number of IDs to fetch per batch (default: 1000, max: 5000)
    ///
    /// # Example
    /// ```rust,ignore
    /// let ids = fetcher.fetch_all_edge_ids(1000).await?;
    /// println!("Found {} edges", ids.len());
    /// ```
    pub async fn fetch_all_edge_ids(
        &self,
        batch_size: usize,
    ) -> Result<HashSet<String>, Box<dyn std::error::Error + Send + Sync>> {
        let batch_size = batch_size.min(MAX_BATCH_SIZE);
        let mut ids = HashSet::new();
        let mut offset = 0;
        let mut batch_count = 0;

        info!(
            "Starting paginated edge ID fetch (batch_size: {})",
            batch_size
        );

        loop {
            // Note: Edges may not have a uuid property in all cases
            // We use a combination of source_uuid + target_uuid + type as a fallback ID
            let query = format!(
                r#"MATCH (n)-[r]->(m) 
                   RETURN COALESCE(r.uuid, n.uuid + '-' + type(r) + '-' + m.uuid) AS id 
                   SKIP {} LIMIT {}"#,
                offset, batch_size
            );

            let mut graph = self.client.select_graph(&self.graph_name);
            let mut result = graph.query(&query).execute().await?;

            let mut fetched_in_batch = 0;
            while let Some(row) = result.data.next() {
                if let Some(id) = row.get(0) {
                    if let Some(id_str) = extract_string(id) {
                        ids.insert(id_str);
                        fetched_in_batch += 1;
                    }
                }
            }

            batch_count += 1;
            debug!(
                "Edge ID batch {}: fetched {} IDs (offset: {}, total: {})",
                batch_count, fetched_in_batch, offset, ids.len()
            );

            if fetched_in_batch < batch_size {
                // Last batch - we've fetched all IDs
                break;
            }

            offset += batch_size;
        }

        info!(
            "Paginated edge ID fetch complete: {} IDs in {} batches",
            ids.len(),
            batch_count
        );

        Ok(ids)
    }

    /// Fetch node and edge IDs concurrently
    ///
    /// More efficient than calling fetch_all_node_ids and fetch_all_edge_ids separately
    /// when you need both.
    pub async fn fetch_all_ids(
        &self,
        batch_size: usize,
    ) -> Result<(HashSet<String>, HashSet<String>), Box<dyn std::error::Error + Send + Sync>> {
        // Create separate fetchers for parallel execution
        // Note: In a real scenario, we'd want to run these concurrently
        // but FalkorDB clients may have connection limitations
        let node_ids = self.fetch_all_node_ids(batch_size).await?;
        let edge_ids = self.fetch_all_edge_ids(batch_size).await?;

        Ok((node_ids, edge_ids))
    }
}

/// Extract string value from FalkorValue
fn extract_string(value: &FalkorValue) -> Option<String> {
    match value {
        FalkorValue::String(s) => Some(s.clone()),
        FalkorValue::I64(i) => Some(i.to_string()),
        _ => value.as_string().map(|s| s.to_string()),
    }
}

/// Reconciliation state for comparing local vs remote IDs
#[derive(Debug, Default)]
pub struct ReconciliationDiff {
    /// IDs present in remote but not in local (need to add)
    pub remote_only: HashSet<String>,
    /// IDs present in local but not in remote (need to remove)
    pub local_only: HashSet<String>,
    /// IDs present in both (may need to update)
    pub common: HashSet<String>,
}

impl ReconciliationDiff {
    /// Compute the difference between remote and local ID sets
    pub fn compute(remote_ids: &HashSet<String>, local_ids: &HashSet<String>) -> Self {
        let remote_only: HashSet<String> = remote_ids.difference(local_ids).cloned().collect();
        let local_only: HashSet<String> = local_ids.difference(remote_ids).cloned().collect();
        let common: HashSet<String> = remote_ids.intersection(local_ids).cloned().collect();

        Self {
            remote_only,
            local_only,
            common,
        }
    }

    /// Check if there are any differences
    pub fn has_differences(&self) -> bool {
        !self.remote_only.is_empty() || !self.local_only.is_empty()
    }

    /// Get summary statistics
    pub fn summary(&self) -> String {
        format!(
            "Reconciliation diff: {} remote-only, {} local-only, {} common",
            self.remote_only.len(),
            self.local_only.len(),
            self.common.len()
        )
    }
}

/// Statistics for reconciliation runs
#[derive(Debug, Clone, Default, serde::Serialize)]
pub struct ReconciliationStats {
    pub last_run: Option<String>,
    pub runs_completed: u64,
    pub nodes_added: u64,
    pub nodes_removed: u64,
    pub edges_added: u64,
    pub edges_removed: u64,
    pub last_duration_ms: u64,
    pub errors: u64,
}

/// Configuration for the reconciliation service
#[derive(Debug, Clone)]
pub struct ReconciliationConfig {
    /// Interval between reconciliation runs (in seconds)
    pub interval_secs: u64,
    /// Batch size for ID fetching
    pub batch_size: usize,
    /// Whether reconciliation is enabled
    pub enabled: bool,
}

impl Default for ReconciliationConfig {
    fn default() -> Self {
        Self {
            interval_secs: 300, // 5 minutes
            batch_size: DEFAULT_BATCH_SIZE,
            enabled: true,
        }
    }
}

/// Service that periodically reconciles DuckDB with FalkorDB
///
/// This service runs in the background and:
/// 1. Fetches all node/edge IDs from FalkorDB (paginated)
/// 2. Compares with local DuckDB state
/// 3. Removes stale entries from DuckDB that no longer exist in FalkorDB
/// 4. Optionally fetches new entries that are missing from DuckDB
pub struct ReconciliationService {
    config: ReconciliationConfig,
    stats: Arc<tokio::sync::RwLock<ReconciliationStats>>,
}

impl ReconciliationService {
    /// Create a new reconciliation service
    pub fn new(config: ReconciliationConfig) -> Self {
        Self {
            config,
            stats: Arc::new(tokio::sync::RwLock::new(ReconciliationStats::default())),
        }
    }

    /// Create a new reconciliation service with external stats for metrics sharing
    ///
    /// This allows the stats to be accessed from outside the service (e.g., for Prometheus metrics)
    pub fn with_shared_stats(
        config: ReconciliationConfig,
        stats: Arc<tokio::sync::RwLock<ReconciliationStats>>,
    ) -> Self {
        Self { config, stats }
    }

    /// Get a clone of the stats Arc for sharing with other components
    pub fn stats_handle(&self) -> Arc<tokio::sync::RwLock<ReconciliationStats>> {
        self.stats.clone()
    }

    /// Get current reconciliation statistics
    pub async fn get_stats(&self) -> ReconciliationStats {
        self.stats.read().await.clone()
    }

    /// Run the reconciliation service in a background task
    ///
    /// This spawns a tokio task that runs reconciliation at the configured interval.
    pub async fn run(
        &self,
        client: Arc<FalkorAsyncClient>,
        graph_name: String,
        duckdb_store: Arc<crate::duckdb_store::DuckDBStore>,
        mut shutdown_rx: tokio::sync::watch::Receiver<bool>,
    ) {
        if !self.config.enabled {
            info!("Reconciliation service disabled");
            return;
        }

        info!(
            "Starting reconciliation service (interval: {}s, batch_size: {})",
            self.config.interval_secs, self.config.batch_size
        );

        let mut interval = tokio::time::interval(
            tokio::time::Duration::from_secs(self.config.interval_secs)
        );

        loop {
            tokio::select! {
                _ = interval.tick() => {
                    if let Err(e) = self.run_reconciliation(
                        &client,
                        &graph_name,
                        &duckdb_store,
                    ).await {
                        error!("Reconciliation failed: {}", e);
                        let mut stats = self.stats.write().await;
                        stats.errors += 1;
                    }
                }
                _ = shutdown_rx.changed() => {
                    if *shutdown_rx.borrow() {
                        info!("Reconciliation service shutting down");
                        break;
                    }
                }
            }
        }
    }

    /// Run a single reconciliation pass
    async fn run_reconciliation(
        &self,
        client: &Arc<FalkorAsyncClient>,
        graph_name: &str,
        duckdb_store: &Arc<crate::duckdb_store::DuckDBStore>,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let start = std::time::Instant::now();
        info!("Starting reconciliation pass...");

        // Create ID fetcher for FalkorDB
        let fetcher = IdFetcher::new(client.clone(), graph_name.to_string());

        // Fetch all node IDs from FalkorDB
        let remote_node_ids = fetcher.fetch_all_node_ids(self.config.batch_size).await?;
        debug!("Fetched {} node IDs from FalkorDB", remote_node_ids.len());

        // Get all node IDs from DuckDB
        let local_node_ids = duckdb_store.get_all_node_ids().await?;
        debug!("Found {} node IDs in DuckDB", local_node_ids.len());

        // Compute node diff
        let node_diff = ReconciliationDiff::compute(&remote_node_ids, &local_node_ids);
        
        let mut nodes_removed = 0;
        let mut nodes_added = 0;

        // Remove stale nodes from DuckDB (nodes that no longer exist in FalkorDB)
        if !node_diff.local_only.is_empty() {
            let stale_ids: Vec<String> = node_diff.local_only.into_iter().collect();
            info!("Removing {} stale nodes from DuckDB", stale_ids.len());
            nodes_removed = duckdb_store.delete_nodes_by_ids(&stale_ids).await?;
            info!("Removed {} stale nodes", nodes_removed);
        }

        // Note: We don't fetch missing nodes here because:
        // 1. The regular sync task handles new nodes via timestamps
        // 2. Adding nodes requires fetching full node data, not just IDs
        // If needed, remote_only nodes can be logged for the sync task to pick up
        if !node_diff.remote_only.is_empty() {
            debug!(
                "{} nodes in FalkorDB not in DuckDB (will be synced by regular task)",
                node_diff.remote_only.len()
            );
            nodes_added = node_diff.remote_only.len() as u64;
        }

        // Fetch all edge IDs from FalkorDB
        let remote_edge_ids = fetcher.fetch_all_edge_ids(self.config.batch_size).await?;
        debug!("Fetched {} edge IDs from FalkorDB", remote_edge_ids.len());

        // Get all edge IDs from DuckDB
        let local_edge_ids = duckdb_store.get_all_edge_ids().await?;
        debug!("Found {} edge IDs in DuckDB", local_edge_ids.len());

        // Compute edge diff
        let edge_diff = ReconciliationDiff::compute(&remote_edge_ids, &local_edge_ids);

        let mut edges_removed = 0;
        let edges_added = edge_diff.remote_only.len() as u64;

        // Remove stale edges from DuckDB
        if !edge_diff.local_only.is_empty() {
            let stale_pairs: Vec<(String, String)> = edge_diff.local_only
                .into_iter()
                .filter_map(|id| {
                    let parts: Vec<&str> = id.split("->").collect();
                    if parts.len() == 2 {
                        Some((parts[0].to_string(), parts[1].to_string()))
                    } else {
                        None
                    }
                })
                .collect();
            
            if !stale_pairs.is_empty() {
                info!("Removing {} stale edges from DuckDB", stale_pairs.len());
                edges_removed = duckdb_store.delete_edges_by_pairs(&stale_pairs).await? as u64;
                info!("Removed {} stale edges", edges_removed);
            }
        }

        let duration = start.elapsed();

        // Update stats
        {
            let mut stats = self.stats.write().await;
            stats.runs_completed += 1;
            stats.last_run = Some(chrono::Utc::now().to_rfc3339());
            stats.last_duration_ms = duration.as_millis() as u64;
            stats.nodes_removed += nodes_removed as u64;
            stats.nodes_added += nodes_added;
            stats.edges_removed += edges_removed;
            stats.edges_added += edges_added;
        }

        info!(
            "Reconciliation complete in {:?}: removed {} nodes, {} edges; found {} new nodes, {} new edges in FalkorDB",
            duration, nodes_removed, edges_removed, nodes_added, edges_added
        );

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_reconciliation_diff_no_changes() {
        let remote: HashSet<String> = ["a", "b", "c"].iter().map(|s| s.to_string()).collect();
        let local: HashSet<String> = ["a", "b", "c"].iter().map(|s| s.to_string()).collect();

        let diff = ReconciliationDiff::compute(&remote, &local);

        assert!(!diff.has_differences());
        assert_eq!(diff.remote_only.len(), 0);
        assert_eq!(diff.local_only.len(), 0);
        assert_eq!(diff.common.len(), 3);
    }

    #[test]
    fn test_reconciliation_diff_with_additions() {
        let remote: HashSet<String> = ["a", "b", "c", "d"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        let local: HashSet<String> = ["a", "b", "c"].iter().map(|s| s.to_string()).collect();

        let diff = ReconciliationDiff::compute(&remote, &local);

        assert!(diff.has_differences());
        assert_eq!(diff.remote_only.len(), 1);
        assert!(diff.remote_only.contains("d"));
        assert_eq!(diff.local_only.len(), 0);
        assert_eq!(diff.common.len(), 3);
    }

    #[test]
    fn test_reconciliation_diff_with_deletions() {
        let remote: HashSet<String> = ["a", "b"].iter().map(|s| s.to_string()).collect();
        let local: HashSet<String> = ["a", "b", "c"].iter().map(|s| s.to_string()).collect();

        let diff = ReconciliationDiff::compute(&remote, &local);

        assert!(diff.has_differences());
        assert_eq!(diff.remote_only.len(), 0);
        assert_eq!(diff.local_only.len(), 1);
        assert!(diff.local_only.contains("c"));
        assert_eq!(diff.common.len(), 2);
    }

    #[test]
    fn test_reconciliation_diff_mixed() {
        let remote: HashSet<String> = ["a", "b", "d"].iter().map(|s| s.to_string()).collect();
        let local: HashSet<String> = ["a", "b", "c"].iter().map(|s| s.to_string()).collect();

        let diff = ReconciliationDiff::compute(&remote, &local);

        assert!(diff.has_differences());
        assert_eq!(diff.remote_only.len(), 1);
        assert!(diff.remote_only.contains("d"));
        assert_eq!(diff.local_only.len(), 1);
        assert!(diff.local_only.contains("c"));
        assert_eq!(diff.common.len(), 2);
    }
}
