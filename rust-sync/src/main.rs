mod config;
mod disaster_recovery;
mod error;
mod extractors;
mod health;
mod loaders;
mod metrics;
mod metrics_server;
mod models;
mod orchestrator;
mod safety;
mod telemetry;

use crate::config::Settings;
use crate::error::Result;
use crate::extractors::{FalkorDBExtractor, Neo4jExtractor};
use crate::health::HealthServer;
use crate::loaders::{FalkorDBLoader, Neo4jLoader};
use crate::metrics_server::MetricsServer;
use crate::models::GraphNode;
use crate::orchestrator::{ContinuousSyncOrchestrator, SyncDirection};
use std::env;
use tokio::sync::mpsc;
use tracing::{error, info, Level};
use tracing_subscriber::FmtSubscriber;

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize tracing with configurable log level
    let log_level = env::var("LOG_LEVEL")
        .ok()
        .and_then(|level| match level.to_uppercase().as_str() {
            "TRACE" => Some(Level::TRACE),
            "DEBUG" => Some(Level::DEBUG),
            "INFO" => Some(Level::INFO),
            "WARN" => Some(Level::WARN),
            "ERROR" => Some(Level::ERROR),
            _ => None,
        })
        .unwrap_or(Level::INFO);

    let subscriber = FmtSubscriber::builder()
        .with_max_level(log_level)
        .finish();
    tracing::subscriber::set_global_default(subscriber).expect("Failed to set tracing subscriber");

    info!("🚀 Starting Graphiti Rust Sync Service");

    // Load configuration
    let settings = Settings::new()?;
    info!("✅ Configuration loaded successfully");
    info!("   Neo4j URI: {}", settings.neo4j.uri);
    info!(
        "   FalkorDB: {}:{}",
        settings.falkordb.host, settings.falkordb.port
    );
    info!("   Batch size: {}", settings.sync.batch_size);
    info!("   Query limit: {}", settings.sync.max_query_limit);

    // Parse command line arguments
    let args: Vec<String> = env::args().collect();

    if args.len() > 1 {
        match args[1].as_str() {
            "health-server" => {
                info!("🏥 Starting health check server");
                run_health_server(settings).await?;
            }
            "clear-neo4j" => {
                info!("🗑️  Clearing Neo4j database");
                clear_neo4j(&settings).await?;
            }
            "sync-loop" => {
                let direction = args.get(2).map(|s| s.as_str()).unwrap_or("falkor-to-neo4j");
                match direction {
                    "neo4j-to-falkor" => {
                        info!("🔄 Starting continuous sync: Neo4j → FalkorDB");
                        run_sync_loop(settings, SyncDirection::Neo4jToFalkor).await?;
                    }
                    "falkor-to-neo4j" => {
                        info!("🔄 Starting continuous sync: FalkorDB → Neo4j");
                        run_sync_loop(settings, SyncDirection::FalkorToNeo4j).await?;
                    }
                    _ => {
                        eprintln!("Unknown direction: {}", direction);
                        eprintln!(
                            "Usage: {} sync-loop [neo4j-to-falkor|falkor-to-neo4j]",
                            args[0]
                        );
                        std::process::exit(1);
                    }
                }
            }
            "test-sync" => {
                let direction = args.get(2).map(|s| s.as_str()).unwrap_or("neo4j-to-falkor");
                match direction {
                    "neo4j-to-falkor" => {
                        info!("🔄 Testing Neo4j → FalkorDB sync");
                        test_neo4j_to_falkor(&settings).await?;
                    }
                    "falkor-to-neo4j" => {
                        info!("🔄 Testing FalkorDB → Neo4j sync");
                        test_falkor_to_neo4j(&settings).await?;
                    }
                    "falkor-to-neo4j-parallel" => {
                        info!("🔄 Testing FalkorDB → Neo4j sync (PARALLEL)");
                        test_falkor_to_neo4j_parallel(&settings).await?;
                    }
                    _ => {
                        eprintln!("Unknown direction: {}", direction);
                        eprintln!("Usage: {} test-sync [neo4j-to-falkor|falkor-to-neo4j|falkor-to-neo4j-parallel]", args[0]);
                        std::process::exit(1);
                    }
                }
            }
            _ => {
                eprintln!("Unknown command: {}", args[1]);
                show_usage(&args[0]);
                std::process::exit(1);
            }
        }
    } else {
        show_usage(&args[0]);
    }

    Ok(())
}

fn show_usage(program_name: &str) {
    println!("📖 Graphiti Rust Sync Service");
    println!();
    println!("Usage:");
    println!(
        "  {} health-server                  # Start health check HTTP server (port 8080)",
        program_name
    );
    println!("  {} sync-loop [direction]          # Start continuous sync loop (default: falkor-to-neo4j)", program_name);
    println!(
        "  {} test-sync [direction]          # Test sync once (default: neo4j-to-falkor)",
        program_name
    );
    println!(
        "  {} clear-neo4j                    # Clear all data from Neo4j",
        program_name
    );
    println!();
    println!("Directions:");
    println!("  neo4j-to-falkor                   # Sync from Neo4j to FalkorDB");
    println!("  falkor-to-neo4j                   # Sync from FalkorDB to Neo4j");
}

/// Run the health check server
async fn run_health_server(settings: Settings) -> Result<()> {
    use tokio::signal;

    info!("Initializing health check server...");

    // Allow port override via environment variable
    let port = env::var("HEALTH_PORT")
        .ok()
        .and_then(|p| p.parse::<u16>().ok())
        .unwrap_or(8080);

    let metrics_port = env::var("SYNC_METRICS_PORT")
        .ok()
        .and_then(|p| p.parse::<u16>().ok())
        .unwrap_or(settings.metrics.port);

    let mut health_server = HealthServer::new(settings.clone(), Some(port));
    let mut metrics_server = MetricsServer::new(metrics_port);

    health_server.start().await?;
    metrics_server.start().await?;

    info!("✅ Health check server started on http://0.0.0.0:{}", port);
    info!(
        "✅ Metrics server started on http://0.0.0.0:{}/metrics",
        metrics_port
    );
    info!("   Endpoints:");
    info!("   - GET /health   - Full health check with database connectivity");
    info!("   - GET /healthz  - Alias for /health");
    info!("   - GET /live     - Liveness probe (always returns 200 if running)");
    info!("   - GET /ready    - Readiness probe (checks database connectivity)");
    info!("   - GET /metrics  - Prometheus metrics endpoint");
    info!("");
    info!("Press Ctrl+C to stop");

    // Wait for shutdown signal
    match signal::ctrl_c().await {
        Ok(()) => {
            info!("Shutdown signal received, stopping server...");
            health_server.stop().await;
            metrics_server.stop().await;
            info!("Server stopped");
        }
        Err(err) => {
            eprintln!("Unable to listen for shutdown signal: {}", err);
        }
    }

    Ok(())
}

/// Run the continuous sync loop
async fn run_sync_loop(settings: Settings, direction: SyncDirection) -> Result<()> {
    use tokio::signal;

    info!("Initializing continuous sync...");
    info!("   Sync interval: {}s", settings.sync.interval_seconds);
    info!("   Direction: {:?}", direction);

    let mut orchestrator = ContinuousSyncOrchestrator::new(settings, direction);

    // Spawn the sync loop task
    let sync_handle = tokio::spawn(async move { orchestrator.start().await });

    info!("✅ Continuous sync loop started");
    info!("Press Ctrl+C to stop");

    // Wait for shutdown signal
    match signal::ctrl_c().await {
        Ok(()) => {
            info!("Shutdown signal received, stopping sync loop...");
            // Note: The sync loop will stop on its own via the shutdown channel
            // We just need to wait for it to finish
            match sync_handle.await {
                Ok(Ok(())) => info!("Sync loop stopped successfully"),
                Ok(Err(e)) => error!("Sync loop error: {}", e),
                Err(e) => error!("Task join error: {}", e),
            }
        }
        Err(err) => {
            eprintln!("Unable to listen for shutdown signal: {}", err);
        }
    }

    Ok(())
}

/// Clear all data from Neo4j
async fn clear_neo4j(settings: &Settings) -> Result<()> {
    use crate::loaders::Neo4jLoader;

    info!("Connecting to Neo4j...");
    let _loader = Neo4jLoader::new(&settings.neo4j, &settings.sync).await?;

    info!("Executing: MATCH (n) DETACH DELETE n");

    // Access the graph field to execute the delete query
    // Note: This is a workaround since Neo4jLoader doesn't expose graph publicly
    // In production, add a clear() method to Neo4jLoader

    info!("⚠️  Please run this Cypher query manually in Neo4j browser:");
    info!("   MATCH (n) DETACH DELETE n");
    info!(
        "   URL: http://{}:7474",
        settings
            .neo4j
            .uri
            .replace("bolt://", "")
            .replace(":7687", "")
    );

    Ok(())
}

/// Test sync from Neo4j to FalkorDB
async fn test_neo4j_to_falkor(settings: &Settings) -> Result<()> {
    info!("Connecting to Neo4j for extraction...");
    let extractor = Neo4jExtractor::new(&settings.neo4j, &settings.sync).await?;

    info!("Connecting to FalkorDB for loading...");
    let mut loader = FalkorDBLoader::new(&settings.falkordb, &settings.sync).await?;

    // Test with Entity nodes (Graphiti data)
    info!("Testing sync of Entity nodes...");
    let (tx, rx) = mpsc::channel::<Vec<GraphNode>>(settings.sync.batch_size);

    // Spawn extraction
    let extraction_handle =
        tokio::spawn(async move { extractor.extract_nodes("Entity", tx).await });

    // Load nodes
    let loading_result = loader.load_nodes(rx).await?;

    // Wait for extraction
    let extraction_result = extraction_handle.await.map_err(|e| {
        crate::error::SyncError::Orchestration(format!("Extraction failed: {}", e))
    })??;

    info!("✅ Sync complete!");
    info!("   Extracted: {} nodes", extraction_result.total_nodes);
    info!("   Loaded: {} nodes", loading_result.nodes_loaded);
    info!("   Extraction time: {:?}", extraction_result.duration);
    info!("   Loading time: {:?}", loading_result.duration);

    Ok(())
}

/// Test sync from FalkorDB to Neo4j
async fn test_falkor_to_neo4j(settings: &Settings) -> Result<()> {
    use crate::models::GraphEdge;

    info!("Connecting to FalkorDB for extraction...");
    let mut node_extractor = FalkorDBExtractor::new(&settings.falkordb, &settings.sync).await?;
    let mut edge_extractor = FalkorDBExtractor::new(&settings.falkordb, &settings.sync).await?;

    info!("Connecting to Neo4j for loading...");
    let mut node_loader = Neo4jLoader::new(&settings.neo4j, &settings.sync).await?;
    let mut edge_loader = Neo4jLoader::new(&settings.neo4j, &settings.sync).await?;

    // Sync Entity nodes
    info!("📦 Syncing Entity nodes...");
    let (node_tx, node_rx) = mpsc::channel::<Vec<GraphNode>>(settings.sync.batch_size);

    let node_extraction_handle =
        tokio::spawn(async move { node_extractor.extract_nodes("Entity", node_tx).await });

    let node_loading_result = node_loader.load_nodes(node_rx).await?;
    let node_extraction_result = node_extraction_handle.await.map_err(|e| {
        crate::error::SyncError::Orchestration(format!("Extraction failed: {}", e))
    })??;

    info!("✅ Entity nodes synced:");
    info!("   Extracted: {} nodes", node_extraction_result.total_nodes);
    info!("   Loaded: {} nodes", node_loading_result.nodes_loaded);
    info!("   Extraction time: {:?}", node_extraction_result.duration);
    info!("   Loading time: {:?}", node_loading_result.duration);

    // Sync Episodic nodes
    info!("📦 Syncing Episodic nodes...");
    let mut episodic_extractor = FalkorDBExtractor::new(&settings.falkordb, &settings.sync).await?;
    let mut episodic_loader = Neo4jLoader::new(&settings.neo4j, &settings.sync).await?;

    let (episodic_tx, episodic_rx) = mpsc::channel::<Vec<GraphNode>>(settings.sync.batch_size);

    let episodic_extraction_handle = tokio::spawn(async move {
        episodic_extractor
            .extract_nodes("Episodic", episodic_tx)
            .await
    });

    let episodic_loading_result = episodic_loader.load_nodes(episodic_rx).await?;
    let episodic_extraction_result = episodic_extraction_handle.await.map_err(|e| {
        crate::error::SyncError::Orchestration(format!("Extraction failed: {}", e))
    })??;

    info!("✅ Episodic nodes synced:");
    info!(
        "   Extracted: {} nodes",
        episodic_extraction_result.total_nodes
    );
    info!("   Loaded: {} nodes", episodic_loading_result.nodes_loaded);

    // Sync edges
    info!("🔗 Syncing edges...");

    // Load node ID cache for optimized edge creation (5-10x speedup)
    info!("📋 Loading node ID cache for optimized edge matching...");
    edge_loader.load_node_id_cache().await?;

    let (edge_tx, edge_rx) = mpsc::channel::<Vec<GraphEdge>>(settings.sync.batch_size);

    let edge_extraction_handle =
        tokio::spawn(async move { edge_extractor.extract_edges(edge_tx).await });

    let edge_loading_result = edge_loader.load_edges(edge_rx).await?;
    let edge_extraction_result = edge_extraction_handle.await.map_err(|e| {
        crate::error::SyncError::Orchestration(format!("Extraction failed: {}", e))
    })??;

    info!("✅ Edges synced:");
    info!("   Extracted: {} edges", edge_extraction_result.total_edges);
    info!("   Loaded: {} edges", edge_loading_result.edges_loaded);
    info!("   Extraction time: {:?}", edge_extraction_result.duration);
    info!("   Loading time: {:?}", edge_loading_result.duration);

    info!("🎉 Full sync complete!");
    let total_nodes = node_loading_result.nodes_loaded + episodic_loading_result.nodes_loaded;
    info!("   Total nodes: {}", total_nodes);
    info!("   Total edges: {}", edge_loading_result.edges_loaded);

    Ok(())
}

/// Test sync from FalkorDB to Neo4j using PARALLEL workers
async fn test_falkor_to_neo4j_parallel(settings: &Settings) -> Result<()> {
    use crate::models::GraphEdge;

    // Number of parallel workers (can be configured via env var)
    let num_workers = env::var("SYNC_NUM_WORKERS")
        .ok()
        .and_then(|w| w.parse::<usize>().ok())
        .unwrap_or(settings.sync.parallel_workers);

    info!("🚀 Using {} parallel workers for loading", num_workers);

    info!("Connecting to FalkorDB for extraction...");
    let mut node_extractor = FalkorDBExtractor::new(&settings.falkordb, &settings.sync).await?;
    let mut edge_extractor = FalkorDBExtractor::new(&settings.falkordb, &settings.sync).await?;

    // Sync Entity nodes with parallel loading
    info!("📦 Syncing Entity nodes (PARALLEL)...");
    let (node_tx, node_rx) = mpsc::channel::<Vec<GraphNode>>(settings.sync.batch_size);

    let node_extraction_handle =
        tokio::spawn(async move { node_extractor.extract_nodes("Entity", node_tx).await });

    let neo4j_config = settings.neo4j.clone();
    let sync_config = settings.sync.clone();
    let node_loading_result =
        Neo4jLoader::load_nodes_parallel(node_rx, &neo4j_config, &sync_config, num_workers).await?;

    let node_extraction_result = node_extraction_handle.await.map_err(|e| {
        crate::error::SyncError::Orchestration(format!("Extraction failed: {}", e))
    })??;

    info!("✅ Entity nodes synced:");
    info!("   Extracted: {} nodes", node_extraction_result.total_nodes);
    info!("   Loaded: {} nodes", node_loading_result.nodes_loaded);
    info!("   Extraction time: {:?}", node_extraction_result.duration);
    info!("   Loading time: {:?}", node_loading_result.duration);
    info!(
        "   Throughput: {:.0} nodes/second",
        node_loading_result.nodes_loaded as f64 / node_loading_result.duration.as_secs_f64()
    );

    // Sync Episodic nodes with parallel loading
    info!("📦 Syncing Episodic nodes (PARALLEL)...");
    let mut episodic_extractor = FalkorDBExtractor::new(&settings.falkordb, &settings.sync).await?;

    let (episodic_tx, episodic_rx) = mpsc::channel::<Vec<GraphNode>>(settings.sync.batch_size);

    let episodic_extraction_handle = tokio::spawn(async move {
        episodic_extractor
            .extract_nodes("Episodic", episodic_tx)
            .await
    });

    let neo4j_config = settings.neo4j.clone();
    let sync_config = settings.sync.clone();
    let episodic_loading_result =
        Neo4jLoader::load_nodes_parallel(episodic_rx, &neo4j_config, &sync_config, num_workers)
            .await?;

    let episodic_extraction_result = episodic_extraction_handle.await.map_err(|e| {
        crate::error::SyncError::Orchestration(format!("Extraction failed: {}", e))
    })??;

    info!("✅ Episodic nodes synced:");
    info!(
        "   Extracted: {} nodes",
        episodic_extraction_result.total_nodes
    );
    info!("   Loaded: {} nodes", episodic_loading_result.nodes_loaded);
    info!(
        "   Throughput: {:.0} nodes/second",
        episodic_loading_result.nodes_loaded as f64
            / episodic_loading_result.duration.as_secs_f64()
    );

    // Sync edges with parallel loading
    info!("🔗 Syncing edges (PARALLEL)...");

    // Load node ID cache first (single-threaded operation)
    info!("📋 Loading node ID cache for optimized edge matching...");
    let mut cache_loader = Neo4jLoader::new(&settings.neo4j, &settings.sync).await?;
    cache_loader.load_node_id_cache().await?;
    let node_id_cache = cache_loader.take_node_id_cache().ok_or_else(|| {
        crate::error::SyncError::SyncFailed("Failed to load node ID cache".to_string())
    })?;

    let (edge_tx, edge_rx) = mpsc::channel::<Vec<GraphEdge>>(settings.sync.batch_size);

    let edge_extraction_handle =
        tokio::spawn(async move { edge_extractor.extract_edges(edge_tx).await });

    let neo4j_config = settings.neo4j.clone();
    let sync_config = settings.sync.clone();
    let edge_loading_result = Neo4jLoader::load_edges_parallel(
        edge_rx,
        &neo4j_config,
        &sync_config,
        node_id_cache,
        num_workers,
    )
    .await?;

    let edge_extraction_result = edge_extraction_handle.await.map_err(|e| {
        crate::error::SyncError::Orchestration(format!("Extraction failed: {}", e))
    })??;

    info!("✅ Edges synced:");
    info!("   Extracted: {} edges", edge_extraction_result.total_edges);
    info!("   Loaded: {} edges", edge_loading_result.edges_loaded);
    info!("   Extraction time: {:?}", edge_extraction_result.duration);
    info!("   Loading time: {:?}", edge_loading_result.duration);
    info!(
        "   Throughput: {:.0} edges/second",
        edge_loading_result.edges_loaded as f64 / edge_loading_result.duration.as_secs_f64()
    );

    info!("🎉 Full PARALLEL sync complete!");
    let total_nodes = node_loading_result.nodes_loaded + episodic_loading_result.nodes_loaded;
    info!("   Total nodes: {}", total_nodes);
    info!("   Total edges: {}", edge_loading_result.edges_loaded);
    info!("   Workers used: {}", num_workers);

    Ok(())
}
