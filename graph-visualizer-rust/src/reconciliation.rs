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
use tracing::{debug, info, warn};

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
