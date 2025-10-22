//! Sync orchestrator with channel-based coordination
//!
//! This module implements the core sync orchestration logic that coordinates
//! extraction from Neo4j and loading into FalkorDB using tokio channels for
//! concurrent pipeline execution.

use crate::error::Result;
use crate::extractors::Neo4jExtractor;
use crate::loaders::FalkorDBLoader;
use crate::models::{ExtractionStats, GraphEdge, GraphNode, LoadingStats, SyncStats};
use tokio::sync::mpsc;
use tracing::info;

/// Sync orchestrator that coordinates extraction and loading operations
///
/// The orchestrator uses tokio channels to create a concurrent pipeline where
/// extraction and loading happen in parallel. This maximizes throughput by
/// ensuring that the loader can process data while the extractor continues
/// fetching more data from Neo4j.
pub struct SyncOrchestrator {
    extractor: Neo4jExtractor,
    loader: FalkorDBLoader,
    channel_buffer: usize,
}

impl SyncOrchestrator {
    /// Create a new sync orchestrator
    ///
    /// # Arguments
    /// * `extractor` - Neo4j extractor instance
    /// * `loader` - FalkorDB loader instance
    /// * `channel_buffer` - Buffer size for channels (default: 100)
    ///
    /// # Example
    /// ```no_run
    /// use graphiti_sync_rs::orchestrator::SyncOrchestrator;
    /// use graphiti_sync_rs::extractors::Neo4jExtractor;
    /// use graphiti_sync_rs::loaders::FalkorDBLoader;
    ///
    /// # async fn example() -> Result<(), Box<dyn std::error::Error>> {
    /// # let extractor = todo!();
    /// # let loader = todo!();
    /// let orchestrator = SyncOrchestrator::new(extractor, loader, 100);
    /// # Ok(())
    /// # }
    /// ```
    pub fn new(extractor: Neo4jExtractor, loader: FalkorDBLoader, channel_buffer: usize) -> Self {
        Self {
            extractor,
            loader,
            channel_buffer,
        }
    }

    /// Sync all node types and edges from Neo4j to FalkorDB
    ///
    /// This method orchestrates the complete sync process:
    /// 1. Syncs Entity nodes
    /// 2. Syncs Episode nodes
    /// 3. Syncs all edges/relationships
    ///
    /// # Returns
    /// Combined statistics for all sync operations
    ///
    /// # Example
    /// ```no_run
    /// # use graphiti_sync_rs::orchestrator::SyncOrchestrator;
    /// # async fn example(mut orchestrator: SyncOrchestrator) -> Result<(), Box<dyn std::error::Error>> {
    /// let stats = orchestrator.sync_all().await?;
    /// println!("Synced {} nodes and {} edges", stats.nodes_synced, stats.edges_synced);
    /// # Ok(())
    /// # }
    /// ```
    pub async fn sync_all(&mut self) -> Result<SyncStats> {
        info!("🔄 Starting full sync");

        // Define node types to sync (common Graphiti types)
        let node_types = vec!["Entity", "Episode"];

        let mut total_extraction_stats = ExtractionStats::default();
        let mut total_loading_stats = LoadingStats::default();

        // Sync each node type
        for node_type in &node_types {
            info!("Syncing nodes of type: {}", node_type);
            let (extraction, loading) = self.sync_nodes(node_type).await?;

            // Aggregate extraction stats
            total_extraction_stats.total_nodes += extraction.total_nodes;
            total_extraction_stats.total_edges += extraction.total_edges;
            total_extraction_stats.duration += extraction.duration;

            // Aggregate loading stats
            total_loading_stats.nodes_loaded += loading.nodes_loaded;
            total_loading_stats.edges_loaded += loading.edges_loaded;
            total_loading_stats.duration += loading.duration;
        }

        // Sync edges
        info!("Syncing edges");
        let (extraction, loading) = self.sync_edges().await?;

        // Aggregate final extraction stats
        total_extraction_stats.total_nodes += extraction.total_nodes;
        total_extraction_stats.total_edges += extraction.total_edges;
        total_extraction_stats.duration += extraction.duration;

        // Aggregate final loading stats
        total_loading_stats.nodes_loaded += loading.nodes_loaded;
        total_loading_stats.edges_loaded += loading.edges_loaded;
        total_loading_stats.duration += loading.duration;

        // Create combined sync stats
        let sync_stats =
            SyncStats::from_extraction_and_loading(total_extraction_stats, total_loading_stats);

        info!("✅ Full sync complete: {:?}", sync_stats);
        Ok(sync_stats)
    }

    /// Sync nodes of a specific type
    ///
    /// Creates a channel pipeline where extraction and loading run concurrently.
    /// The extractor sends batches of nodes through the channel, and the loader
    /// consumes and writes them to FalkorDB.
    ///
    /// # Arguments
    /// * `node_type` - The node label to sync (e.g., "Entity", "Episode")
    ///
    /// # Returns
    /// Tuple of (extraction stats, loading stats)
    ///
    /// # Errors
    /// Returns error if extraction or loading fails, or if tasks panic
    pub async fn sync_nodes(&mut self, node_type: &str) -> Result<(ExtractionStats, LoadingStats)> {
        info!("Starting sync of {} nodes", node_type);

        // Create channel for streaming node batches
        let (tx, rx) = mpsc::channel::<Vec<GraphNode>>(self.channel_buffer);

        // Spawn extraction task
        // Clone the extractor so it can be moved into the spawned task
        let extractor = self.extractor.clone();
        let node_type_owned = node_type.to_string();
        let extraction_handle =
            tokio::spawn(async move { extractor.extract_nodes(&node_type_owned, tx).await });

        // Load nodes directly (no need to spawn since we need exclusive access)
        let loading_result = self.loader.load_nodes(rx).await?;

        // Wait for extraction task
        let extraction_result = extraction_handle.await.map_err(|e| {
            crate::error::SyncError::Orchestration(format!("Extraction task panicked: {}", e))
        })??;

        info!(
            "Completed sync of {} nodes: extracted {}, loaded {}",
            node_type, extraction_result.total_nodes, loading_result.nodes_loaded
        );

        Ok((extraction_result, loading_result))
    }

    /// Sync all edges
    ///
    /// Creates a channel pipeline where extraction and loading run concurrently.
    /// The extractor sends batches of edges through the channel, and the loader
    /// consumes and writes them to FalkorDB.
    ///
    /// # Returns
    /// Tuple of (extraction stats, loading stats)
    ///
    /// # Errors
    /// Returns error if extraction or loading fails, or if tasks panic
    pub async fn sync_edges(&mut self) -> Result<(ExtractionStats, LoadingStats)> {
        info!("Starting sync of edges");

        // Create channel for streaming edge batches
        let (tx, rx) = mpsc::channel::<Vec<GraphEdge>>(self.channel_buffer);

        // Spawn extraction task
        let extractor = self.extractor.clone();
        let extraction_handle = tokio::spawn(async move { extractor.extract_edges(tx).await });

        // Load edges directly (no need to spawn since we need exclusive access)
        let loading_result = self.loader.load_edges(rx).await?;

        // Wait for extraction task
        let extraction_result = extraction_handle.await.map_err(|e| {
            crate::error::SyncError::Orchestration(format!("Extraction task panicked: {}", e))
        })??;

        info!(
            "Completed sync of edges: extracted {}, loaded {}",
            extraction_result.total_edges, loading_result.edges_loaded
        );

        Ok((extraction_result, loading_result))
    }

    /// Graceful shutdown - ensure all channels are closed and tasks complete
    ///
    /// Currently a no-op as channels are automatically closed when dropped.
    /// Future versions may add connection cleanup logic.
    pub async fn shutdown(&mut self) -> Result<()> {
        info!("🛑 Shutting down sync orchestrator");
        // Channels are automatically closed when dropped
        // Future: Add connection cleanup if needed
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sync_stats_default() {
        let stats = SyncStats::from_extraction_and_loading(
            ExtractionStats::default(),
            LoadingStats::default(),
        );
        assert_eq!(stats.nodes_synced, 0);
        assert_eq!(stats.edges_synced, 0);
    }

    #[test]
    fn test_extraction_stats_default() {
        let stats = ExtractionStats::default();
        assert_eq!(stats.total_nodes, 0);
        assert_eq!(stats.total_edges, 0);
    }

    #[test]
    fn test_loading_stats_default() {
        let stats = LoadingStats::default();
        assert_eq!(stats.nodes_loaded, 0);
        assert_eq!(stats.edges_loaded, 0);
    }

    #[test]
    fn test_stats_aggregation() {
        use std::time::Duration;

        let extraction = ExtractionStats {
            total_nodes: 100,
            total_edges: 50,
            duration: Duration::from_secs(5),
        };

        let loading = LoadingStats {
            nodes_loaded: 100,
            edges_loaded: 50,
            duration: Duration::from_secs(3),
        };

        let sync_stats = SyncStats::from_extraction_and_loading(extraction, loading);

        assert_eq!(sync_stats.nodes_synced, 100);
        assert_eq!(sync_stats.edges_synced, 50);
        assert_eq!(sync_stats.total_duration, Duration::from_secs(8));
    }
}
