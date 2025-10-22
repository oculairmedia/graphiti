//! Continuous sync loop with periodic execution and graceful shutdown.

use std::sync::Arc;
use std::time::Duration;
use tokio::sync::{mpsc, Mutex};
use tokio::time;
use tracing::{error, info, warn};

use crate::config::Settings;
use crate::disaster_recovery::{DisasterRecoveryDetector, DisasterState, RecoveryStateTracker};
use crate::error::Result;
use crate::extractors::{FalkorDBExtractor, Neo4jExtractor};
use crate::loaders::{FalkorDBLoader, Neo4jLoader};
use crate::models::{GraphEdge, GraphNode};
use crate::safety::SafetyValidator;
use crate::telemetry;

/// Direction of synchronization
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SyncDirection {
    /// Neo4j → FalkorDB
    Neo4jToFalkor,
    /// FalkorDB → Neo4j
    FalkorToNeo4j,
}

impl std::fmt::Display for SyncDirection {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SyncDirection::Neo4jToFalkor => write!(f, "neo4j-to-falkor"),
            SyncDirection::FalkorToNeo4j => write!(f, "falkor-to-neo4j"),
        }
    }
}

/// Continuous sync orchestrator
pub struct ContinuousSyncOrchestrator {
    settings: Arc<Settings>,
    direction: SyncDirection,
    shutdown_tx: Option<mpsc::Sender<()>>,
    last_signature: Arc<Mutex<Option<ChangeSignature>>>,
    recovery_tracker: Arc<Mutex<RecoveryStateTracker>>,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
struct ChangeSignature {
    entity_nodes: usize,
    episodic_nodes: usize,
    community_nodes: usize,
    edges: usize,
}

impl ContinuousSyncOrchestrator {
    /// Create new continuous sync orchestrator
    pub fn new(settings: Settings, direction: SyncDirection) -> Self {
        let orchestrator = Self {
            settings: Arc::new(settings),
            direction,
            shutdown_tx: None,
            last_signature: Arc::new(Mutex::new(None)),
            recovery_tracker: Arc::new(Mutex::new(RecoveryStateTracker::from_env())),
        };
        telemetry::mark_sync_idle(&direction.to_string());
        orchestrator
    }

    /// Calculate optimal number of workers based on system resources
    ///
    /// Strategy:
    /// - Use available CPU cores as baseline (leave 1-2 cores for system)
    /// - Cap based on available memory (each worker needs ~50-100MB)
    /// - Respect environment variable override if set
    /// - Minimum 2 workers, maximum 16 workers
    fn calculate_optimal_workers() -> usize {
        // Check for manual override first
        if let Ok(manual_workers) = std::env::var("SYNC_PARALLEL_WORKERS") {
            if let Ok(workers) = manual_workers.parse::<usize>() {
                let clamped = workers.clamp(1, 32);
                info!(
                    "📊 Using manual worker count: {} (from SYNC_PARALLEL_WORKERS)",
                    clamped
                );
                return clamped;
            }
        }

        let mut sys = sysinfo::System::new_all();
        sys.refresh_all();

        // Get CPU cores (logical, includes hyperthreading)
        let cpu_count = num_cpus::get();

        // Reserve 1-2 cores for system based on total cores
        let reserved_cores = if cpu_count <= 4 { 1 } else { 2 };
        let available_cores = cpu_count.saturating_sub(reserved_cores).max(1);

        // Get available memory in MB
        let available_memory_mb = sys.available_memory() / 1_024 / 1_024;

        // Each worker needs approximately 50-100MB (connection + buffers)
        // Use conservative 100MB estimate
        const MEMORY_PER_WORKER_MB: u64 = 100;
        let memory_based_workers = (available_memory_mb / MEMORY_PER_WORKER_MB) as usize;

        // Take minimum of CPU-based and memory-based limits
        let optimal_workers = available_cores.min(memory_based_workers);

        // Clamp to reasonable range: 2-16 workers
        let final_workers = optimal_workers.clamp(2, 16);

        info!(
            "📊 Auto-scaling workers: {} cores available ({} total - {} reserved), {}MB memory available",
            available_cores, cpu_count, reserved_cores, available_memory_mb
        );
        info!(
            "📊 Calculated: {} workers (CPU-limited: {}, Memory-limited: {}, Final: {})",
            final_workers, available_cores, memory_based_workers, final_workers
        );

        final_workers
    }

    /// Start the continuous sync loop
    pub async fn start(&mut self) -> Result<()> {
        let (shutdown_tx, mut shutdown_rx) = mpsc::channel::<()>(1);
        self.shutdown_tx = Some(shutdown_tx);

        // Check for disaster state on startup
        self.check_disaster_recovery().await?;

        let interval_duration = Duration::from_secs(self.settings.sync.interval_seconds);
        let mut interval = time::interval(interval_duration);
        interval.set_missed_tick_behavior(time::MissedTickBehavior::Skip);

        info!(
            "🔄 Starting continuous sync loop (interval: {}s, direction: {:?})",
            self.settings.sync.interval_seconds, self.direction
        );

        let mut sync_count = 0u64;

        loop {
            tokio::select! {
                _ = interval.tick() => {
                    sync_count += 1;
                    info!("⏰ Sync cycle #{} starting...", sync_count);

                    // Check for changes before syncing
                    if !self.has_changes().await {
                        info!("✨ No changes detected, skipping sync");
                        telemetry::mark_sync_idle(&self.direction.to_string());
                        continue;
                    }

                    telemetry::mark_sync_start(&self.direction.to_string());

                    // Perform sync
                    match self.sync_once().await {
                        Ok((nodes_synced, edges_synced)) => {
                            info!(
                                "✅ Sync cycle #{} complete: {} nodes, {} edges",
                                sync_count, nodes_synced, edges_synced
                            );
                            telemetry::mark_sync_success(
                                &self.direction.to_string(),
                                nodes_synced,
                                edges_synced,
                            );
                        }
                        Err(e) => {
                            error!("❌ Sync cycle #{} failed: {}", sync_count, e);
                            telemetry::mark_sync_failure(&self.direction.to_string(), &e.to_string());
                        }
                    }
                }
                _ = shutdown_rx.recv() => {
                    info!("🛑 Shutdown signal received, stopping sync loop");
                    break;
                }
            }
        }

        info!(
            "✅ Continuous sync loop stopped after {} cycles",
            sync_count
        );
        Ok(())
    }

    /// Stop the continuous sync loop
    pub async fn stop(&mut self) {
        if let Some(tx) = self.shutdown_tx.take() {
            let _ = tx.send(()).await;
        }
    }

    /// Check if there are changes to sync
    async fn has_changes(&self) -> bool {
        match self.current_signature().await {
            Ok(signature) => {
                let mut guard = self.last_signature.lock().await;
                let changed = guard.as_ref().map_or(true, |prev| prev != &signature);
                if changed {
                    *guard = Some(signature);
                }
                changed
            }
            Err(err) => {
                warn!("Change detection failed, forcing sync: {}", err);
                true
            }
        }
    }

    /// Perform a single sync operation
    async fn sync_once(&self) -> Result<(usize, usize)> {
        // Run safety validation before sync
        self.validate_safety().await?;

        match self.direction {
            SyncDirection::Neo4jToFalkor => self.sync_neo4j_to_falkor().await,
            SyncDirection::FalkorToNeo4j => self.sync_falkor_to_neo4j().await,
        }
    }

    /// Validate sync operation is safe before proceeding
    async fn validate_safety(&self) -> Result<()> {
        let validator = SafetyValidator::from_env();

        match self.direction {
            SyncDirection::Neo4jToFalkor => {
                info!("🛡️  Validating safety for Neo4j → FalkorDB sync");
                
                let neo4j_extractor =
                    Neo4jExtractor::new(&self.settings.neo4j, &self.settings.sync).await?;
                let mut falkor_extractor =
                    FalkorDBExtractor::new(&self.settings.falkordb, &self.settings.sync).await?;

                let source_entities = neo4j_extractor.count_nodes("Entity").await?;
                let source_episodic = neo4j_extractor.count_nodes("Episodic").await?;
                let source_community = neo4j_extractor.count_nodes("Community").await?;
                let source_edges = neo4j_extractor.count_edges().await?;

                let target_entities = falkor_extractor.count_nodes("Entity").await?;
                let target_episodic = falkor_extractor.count_nodes("Episodic").await?;
                let target_community = falkor_extractor.count_nodes("Community").await?;
                let target_edges = falkor_extractor.count_edges().await?;

                validator.validate_sync(
                    "neo4j-to-falkor",
                    source_entities,
                    source_episodic,
                    source_community,
                    source_edges,
                    target_entities,
                    target_episodic,
                    target_community,
                    target_edges,
                )?;
            }
            SyncDirection::FalkorToNeo4j => {
                info!("🛡️  Validating safety for FalkorDB → Neo4j sync");
                
                let mut falkor_extractor =
                    FalkorDBExtractor::new(&self.settings.falkordb, &self.settings.sync).await?;
                let neo4j_extractor =
                    Neo4jExtractor::new(&self.settings.neo4j, &self.settings.sync).await?;

                let source_entities = falkor_extractor.count_nodes("Entity").await?;
                let source_episodic = falkor_extractor.count_nodes("Episodic").await?;
                let source_community = falkor_extractor.count_nodes("Community").await?;
                let source_edges = falkor_extractor.count_edges().await?;

                let target_entities = neo4j_extractor.count_nodes("Entity").await?;
                let target_episodic = neo4j_extractor.count_nodes("Episodic").await?;
                let target_community = neo4j_extractor.count_nodes("Community").await?;
                let target_edges = neo4j_extractor.count_edges().await?;

                validator.validate_sync(
                    "falkor-to-neo4j",
                    source_entities,
                    source_episodic,
                    source_community,
                    source_edges,
                    target_entities,
                    target_episodic,
                    target_community,
                    target_edges,
                )?;
            }
        }

        Ok(())
    }

    /// Check for disaster state and trigger recovery if needed
    async fn check_disaster_recovery(&self) -> Result<()> {
        let detector = DisasterRecoveryDetector::from_env();

        let report = match self.direction {
            SyncDirection::Neo4jToFalkor => detector.detect_neo4j_to_falkor(&self.settings).await?,
            SyncDirection::FalkorToNeo4j => detector.detect_falkor_to_neo4j(&self.settings).await?,
        };

        // If disaster detected and auto-recovery enabled
        if detector.should_auto_recover(&report) {
            let mut tracker = self.recovery_tracker.lock().await;
            
            if tracker.can_recover() {
                info!("🚨 Disaster detected - initiating automatic recovery");
                tracker.mark_recovery_attempt();
                drop(tracker); // Release lock before recovery

                // Perform recovery sync
                match self.perform_recovery_sync().await {
                    Ok((nodes, edges)) => {
                        info!("✅ Recovery complete: {} nodes, {} edges", nodes, edges);
                        let mut tracker = self.recovery_tracker.lock().await;
                        tracker.reset();
                    }
                    Err(e) => {
                        error!("❌ Recovery failed: {}", e);
                        return Err(e);
                    }
                }
            } else {
                error!("❌ Automatic recovery blocked by safety limits");
                error!("   Review disaster state manually and adjust recovery settings");
            }
        }

        Ok(())
    }

    /// Perform recovery sync (bypasses normal safety checks)
    async fn perform_recovery_sync(&self) -> Result<(usize, usize)> {
        info!("🔄 Starting recovery sync...");
        
        // Recovery sync bypasses change detection and uses full sync
        match self.direction {
            SyncDirection::Neo4jToFalkor => self.sync_neo4j_to_falkor().await,
            SyncDirection::FalkorToNeo4j => self.sync_falkor_to_neo4j().await,
        }
    }

    async fn current_signature(&self) -> Result<ChangeSignature> {
        match self.direction {
            SyncDirection::Neo4jToFalkor => {
                let extractor =
                    Neo4jExtractor::new(&self.settings.neo4j, &self.settings.sync).await?;
                let entity_nodes = extractor.count_nodes("Entity").await?;
                let episodic_nodes = extractor.count_nodes("Episodic").await?;
                let community_nodes = extractor.count_nodes("Community").await?;
                let edges = extractor.count_edges().await?;
                Ok(ChangeSignature {
                    entity_nodes,
                    episodic_nodes,
                    community_nodes,
                    edges,
                })
            }
            SyncDirection::FalkorToNeo4j => {
                let mut extractor =
                    FalkorDBExtractor::new(&self.settings.falkordb, &self.settings.sync).await?;
                let entity_nodes = extractor.count_nodes("Entity").await?;
                let episodic_nodes = extractor.count_nodes("Episodic").await?;
                let community_nodes = extractor.count_nodes("Community").await?;
                let edges = extractor.count_edges().await?;
                Ok(ChangeSignature {
                    entity_nodes,
                    episodic_nodes,
                    community_nodes,
                    edges,
                })
            }
        }
    }

    /// Sync from Neo4j to FalkorDB
    async fn sync_neo4j_to_falkor(&self) -> Result<(usize, usize)> {
        info!("📦 Syncing Neo4j → FalkorDB");

        let extractor = Neo4jExtractor::new(&self.settings.neo4j, &self.settings.sync).await?;
        let mut loader = FalkorDBLoader::new(&self.settings.falkordb, &self.settings.sync).await?;

        // Sync Entity nodes
        let (node_tx, node_rx) = mpsc::channel::<Vec<GraphNode>>(self.settings.sync.batch_size);

        let node_extraction_handle =
            tokio::spawn(async move { extractor.extract_nodes("Entity", node_tx).await });

        let node_loading_result = loader.load_nodes(node_rx).await?;
        let _node_extraction_result = node_extraction_handle.await.map_err(|e| {
            crate::error::SyncError::Orchestration(format!("Extraction failed: {}", e))
        })??;

        let nodes_synced = node_loading_result.nodes_loaded;

        info!("✅ Synced {} nodes", nodes_synced);

        // For Neo4j → FalkorDB, we currently only sync nodes
        Ok((nodes_synced, 0))
    }

    /// Sync from FalkorDB to Neo4j
    async fn sync_falkor_to_neo4j(&self) -> Result<(usize, usize)> {
        info!("📦 Syncing FalkorDB → Neo4j");

        // Sync Entity nodes
        let mut node_extractor =
            FalkorDBExtractor::new(&self.settings.falkordb, &self.settings.sync).await?;
        let mut node_loader = Neo4jLoader::new(&self.settings.neo4j, &self.settings.sync).await?;

        let (node_tx, node_rx) = mpsc::channel::<Vec<GraphNode>>(self.settings.sync.batch_size);

        let node_extraction_handle =
            tokio::spawn(async move { node_extractor.extract_nodes("Entity", node_tx).await });

        let node_loading_result = node_loader.load_nodes(node_rx).await?;
        let _node_extraction_result = node_extraction_handle.await.map_err(|e| {
            crate::error::SyncError::Orchestration(format!("Extraction failed: {}", e))
        })??;

        let entity_nodes_synced = node_loading_result.nodes_loaded;

        // Sync Episodic nodes
        let mut episodic_extractor =
            FalkorDBExtractor::new(&self.settings.falkordb, &self.settings.sync).await?;
        let mut episodic_loader =
            Neo4jLoader::new(&self.settings.neo4j, &self.settings.sync).await?;

        let (episodic_tx, episodic_rx) =
            mpsc::channel::<Vec<GraphNode>>(self.settings.sync.batch_size);

        let episodic_extraction_handle = tokio::spawn(async move {
            episodic_extractor
                .extract_nodes("Episodic", episodic_tx)
                .await
        });

        let episodic_loading_result = episodic_loader.load_nodes(episodic_rx).await?;
        let _episodic_extraction_result = episodic_extraction_handle.await.map_err(|e| {
            crate::error::SyncError::Orchestration(format!("Extraction failed: {}", e))
        })??;

        let episodic_nodes_synced = episodic_loading_result.nodes_loaded;
        let mut total_nodes = entity_nodes_synced + episodic_nodes_synced;

        // Sync Community nodes
        let mut community_extractor =
            FalkorDBExtractor::new(&self.settings.falkordb, &self.settings.sync).await?;
        let mut community_loader =
            Neo4jLoader::new(&self.settings.neo4j, &self.settings.sync).await?;

        let (community_tx, community_rx) =
            mpsc::channel::<Vec<GraphNode>>(self.settings.sync.batch_size);

        let community_extraction_handle = tokio::spawn(async move {
            community_extractor
                .extract_nodes("Community", community_tx)
                .await
        });

        let community_loading_result = community_loader.load_nodes(community_rx).await?;
        let _community_extraction_result = community_extraction_handle.await.map_err(|e| {
            crate::error::SyncError::Orchestration(format!("Extraction failed: {}", e))
        })??;

        let community_nodes_synced = community_loading_result.nodes_loaded;
        total_nodes += community_nodes_synced;

        // Sync edges with parallel loading, pipelined cache loading, and prefetching
        //
        // Pipeline optimization: Start extraction and cache loading in parallel,
        // allowing extraction to feed a buffer while cache loads. This overlaps
        // FalkorDB extraction with Neo4j cache loading instead of doing them serially.

        let mut edge_extractor =
            FalkorDBExtractor::new(&self.settings.falkordb, &self.settings.sync).await?;

        // Create channel with larger buffer to enable prefetching
        // Buffer size = batch_size * 4 allows ~4 batches to queue while waiting for workers
        let channel_buffer = self.settings.sync.batch_size * 4;
        let (edge_tx, edge_rx) = mpsc::channel::<Vec<GraphEdge>>(channel_buffer);

        // Start edge extraction immediately - don't wait for cache
        info!("🚀 Starting edge extraction with prefetch buffer ({})", channel_buffer);
        let edge_extraction_handle =
            tokio::spawn(async move { edge_extractor.extract_edges(edge_tx).await });

        // Start cache loading in parallel with extraction
        info!("⚡ Loading node ID cache in parallel with extraction...");
        let neo4j_config = self.settings.neo4j.clone();
        let sync_config = self.settings.sync.clone();
        let cache_loading_handle = tokio::spawn(async move {
            let mut cache_loader = Neo4jLoader::new(&neo4j_config, &sync_config).await?;
            cache_loader.load_node_id_cache().await?;
            cache_loader.take_node_id_cache()
                .ok_or_else(|| crate::error::SyncError::SyncFailed(
                    "Failed to load node ID cache".to_string()
                ))
        });

        // Wait for cache to be ready (extraction continues in background)
        let node_id_cache = cache_loading_handle.await.map_err(|e| {
            crate::error::SyncError::Orchestration(format!("Cache loading failed: {}", e))
        })??;

        // Auto-scale workers based on available system resources
        let num_workers = Self::calculate_optimal_workers();
        info!(
            "🚀 Starting parallel edge loading with {} workers (extraction ongoing, cache ready)",
            num_workers
        );

        // Start parallel loading - extraction is already filling the channel buffer
        let edge_loading_result = Neo4jLoader::load_edges_parallel(
            edge_rx,
            &self.settings.neo4j,
            &self.settings.sync,
            node_id_cache,
            num_workers,
        ).await?;

        // Wait for extraction to complete
        let _edge_extraction_result = edge_extraction_handle.await.map_err(|e| {
            crate::error::SyncError::Orchestration(format!("Extraction failed: {}", e))
        })??;

        let edges_synced = edge_loading_result.edges_loaded;

        info!(
            "✅ Synced {} nodes (Entity: {}, Episodic: {}, Community: {}) and {} edges",
            total_nodes,
            entity_nodes_synced,
            episodic_nodes_synced,
            community_nodes_synced,
            edges_synced
        );

        Ok((total_nodes, edges_synced))
    }
}
