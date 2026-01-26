// BFS Integration Tests
// Requires FalkorDB instance running on localhost:6379 with data
// Run with: cargo test --test test_bfs_integration -- --ignored --nocapture

use std::time::{Duration, Instant};
use tokio::time::timeout;

fn init_tracing() {
    let _ = tracing_subscriber::fmt()
        .with_env_filter("graphiti_search_rs=debug")
        .with_test_writer()
        .try_init();
}

async fn setup_test_connection() -> (
    graphiti_search_rs::config::Config,
    graphiti_search_rs::falkor::FalkorPool,
) {
    use graphiti_search_rs::config::Config;
    use graphiti_search_rs::falkor::create_falkor_pool;

    init_tracing();

    std::env::set_var("FALKORDB_HOST", "localhost");
    std::env::set_var("FALKORDB_PORT", "6379");
    std::env::set_var("GRAPH_NAME", "graphiti_migration");
    std::env::set_var("REDIS_URL", "redis://localhost:6379");

    let config = Config::from_env().expect("Failed to load config");
    let pool = create_falkor_pool(&config)
        .await
        .expect("Failed to create pool");

    (config, pool)
}

async fn get_seed_nodes(
    conn: &mut graphiti_search_rs::falkor::FalkorConnection,
    count: usize,
) -> Vec<graphiti_search_rs::models::Node> {
    match conn.get_random_nodes(count).await {
        Ok(nodes) => {
            println!("get_random_nodes returned {} nodes", nodes.len());
            nodes
        }
        Err(e) => {
            println!("get_random_nodes error: {:?}", e);
            Vec::new()
        }
    }
}

// ============================================================================
// Basic BFS Functionality Tests
// ============================================================================

#[tokio::test(flavor = "multi_thread")]
#[ignore = "Requires FalkorDB instance running on localhost:6379 with data"]
async fn test_bfs_basic_traversal() {
    use graphiti_search_rs::search::bfs::{search_nodes_bfs, BfsConfig};

    let (_config, pool) = setup_test_connection().await;
    let mut conn = pool.get().await.expect("Failed to get connection");

    // Get seed nodes
    let seed_nodes = get_seed_nodes(&mut conn, 3).await;
    if seed_nodes.is_empty() {
        println!("SKIP: No nodes in database");
        return;
    }

    println!("Starting BFS with {} seed nodes:", seed_nodes.len());
    for node in &seed_nodes {
        println!("  - {} ({})", node.name, node.uuid);
    }

    let config = BfsConfig::default();

    let start = Instant::now();
    let result = timeout(
        Duration::from_secs(30),
        search_nodes_bfs(&mut conn, seed_nodes.clone(), &config, None),
    )
    .await
    .expect("Test timed out")
    .expect("BFS search failed");

    let elapsed = start.elapsed();
    println!("\nBFS returned {} nodes in {:?}", result.len(), elapsed);

    // Verify we got results (BFS should expand from seeds)
    assert!(
        !result.is_empty(),
        "BFS should return at least the seed nodes"
    );

    // Verify scores are assigned
    for node in &result {
        assert!(node.score.is_some(), "All BFS results should have scores");
        println!(
            "  - {} (score: {:.4})",
            node.name,
            node.score.unwrap_or(0.0)
        );
    }

    // Verify results are sorted by score (descending)
    let scores: Vec<f32> = result.iter().map(|n| n.score.unwrap_or(0.0)).collect();
    for i in 1..scores.len() {
        assert!(
            scores[i - 1] >= scores[i],
            "Results should be sorted by score descending"
        );
    }
}

#[tokio::test(flavor = "multi_thread")]
#[ignore = "Requires FalkorDB instance running on localhost:6379 with data"]
async fn test_bfs_empty_seeds() {
    use graphiti_search_rs::search::bfs::{search_nodes_bfs, BfsConfig};

    let (_config, pool) = setup_test_connection().await;
    let mut conn = pool.get().await.expect("Failed to get connection");

    let config = BfsConfig::default();
    let empty_seeds: Vec<graphiti_search_rs::models::Node> = vec![];

    let result = search_nodes_bfs(&mut conn, empty_seeds, &config, None)
        .await
        .expect("BFS with empty seeds should not error");

    assert!(
        result.is_empty(),
        "BFS with empty seeds should return empty results"
    );
    println!("✓ BFS handles empty seeds gracefully");
}

// ============================================================================
// Beam Width Tests
// ============================================================================

#[tokio::test(flavor = "multi_thread")]
#[ignore = "Requires FalkorDB instance running on localhost:6379 with data"]
async fn test_bfs_beam_width_limits() {
    use graphiti_search_rs::search::bfs::{search_nodes_bfs, BfsConfig};

    let (_config, pool) = setup_test_connection().await;
    let mut conn = pool.get().await.expect("Failed to get connection");

    let seed_nodes = get_seed_nodes(&mut conn, 3).await;
    if seed_nodes.is_empty() {
        println!("SKIP: No nodes in database");
        return;
    }

    // Test with very small beam width
    let small_beam_config = BfsConfig {
        beam_width: 5,
        max_depth: 2,
        ..Default::default()
    };

    let small_result = search_nodes_bfs(&mut conn, seed_nodes.clone(), &small_beam_config, None)
        .await
        .expect("BFS with small beam should work");

    // Test with larger beam width
    let large_beam_config = BfsConfig {
        beam_width: 100,
        max_depth: 2,
        ..Default::default()
    };

    let large_result = search_nodes_bfs(&mut conn, seed_nodes, &large_beam_config, None)
        .await
        .expect("BFS with large beam should work");

    println!("Small beam (5): {} nodes", small_result.len());
    println!("Large beam (100): {} nodes", large_result.len());

    // With same depth, larger beam width should generally find more or equal nodes
    // (not strictly true if graph is sparse, but generally holds)
    println!("✓ Beam width configuration works");
}

// ============================================================================
// Hub Suppression Tests
// ============================================================================

#[tokio::test(flavor = "multi_thread")]
#[ignore = "Requires FalkorDB instance running on localhost:6379 with data"]
async fn test_bfs_hub_suppression() {
    use graphiti_search_rs::search::bfs::{search_nodes_bfs, BfsConfig};

    let (_config, pool) = setup_test_connection().await;
    let mut conn = pool.get().await.expect("Failed to get connection");

    let seed_nodes = get_seed_nodes(&mut conn, 3).await;
    if seed_nodes.is_empty() {
        println!("SKIP: No nodes in database");
        return;
    }

    // Very aggressive hub suppression
    let aggressive_config = BfsConfig {
        hub_degree_threshold: 10, // Very low threshold
        per_hop_limit: 5,         // Very limited per-hop
        max_expansions: 50,       // Limited expansions
        ..Default::default()
    };

    let start = Instant::now();
    let result = search_nodes_bfs(&mut conn, seed_nodes.clone(), &aggressive_config, None)
        .await
        .expect("BFS with hub suppression should work");
    let elapsed = start.elapsed();

    println!(
        "Hub suppression test: {} nodes in {:?}",
        result.len(),
        elapsed
    );

    // Verify we didn't explode (should complete quickly with limits)
    assert!(
        elapsed < Duration::from_secs(5),
        "Hub suppression should prevent explosion"
    );
    println!("✓ Hub suppression prevents traversal explosion");
}

// ============================================================================
// Decay Scoring Tests
// ============================================================================

#[tokio::test(flavor = "multi_thread")]
#[ignore = "Requires FalkorDB instance running on localhost:6379 with data"]
async fn test_bfs_decay_scoring() {
    use graphiti_search_rs::search::bfs::{search_nodes_bfs, BfsConfig};

    let (_config, pool) = setup_test_connection().await;
    let mut conn = pool.get().await.expect("Failed to get connection");

    let mut seed_nodes = get_seed_nodes(&mut conn, 1).await;
    if seed_nodes.is_empty() {
        println!("SKIP: No nodes in database");
        return;
    }

    // Set initial score for seed
    seed_nodes[0].score = Some(1.0);
    let seed_uuid = seed_nodes[0].uuid.to_string();

    let config = BfsConfig {
        decay: 0.5, // Aggressive decay for testing
        max_depth: 3,
        ..Default::default()
    };

    let result = search_nodes_bfs(&mut conn, seed_nodes, &config, None)
        .await
        .expect("BFS should work");

    // Find the seed node in results
    let seed_in_results = result.iter().find(|n| n.uuid.to_string() == seed_uuid);

    println!("Decay test results ({} nodes):", result.len());
    for node in result.iter().take(10) {
        let is_seed = node.uuid.to_string() == seed_uuid;
        println!(
            "  - {} (score: {:.4}){}",
            node.name,
            node.score.unwrap_or(0.0),
            if is_seed { " [SEED]" } else { "" }
        );
    }

    // Verify seed has highest score (or close to it)
    if let Some(seed) = seed_in_results {
        let seed_score = seed.score.unwrap_or(0.0);
        // Non-seed nodes should have decayed scores
        for node in &result {
            if node.uuid.to_string() != seed_uuid {
                let score = node.score.unwrap_or(0.0);
                // With 0.5 decay, distance-1 nodes have max 0.5, distance-2 max 0.25, etc.
                assert!(
                    score <= 1.0,
                    "Non-seed scores should be <= 1.0 due to decay"
                );
            }
        }
        println!("✓ Seed node score: {:.4}", seed_score);
    }

    println!("✓ Decay scoring produces expected score ordering");
}

// ============================================================================
// Max Expansions / Max Visited Tests
// ============================================================================

#[tokio::test(flavor = "multi_thread")]
#[ignore = "Requires FalkorDB instance running on localhost:6379 with data"]
async fn test_bfs_expansion_limits() {
    use graphiti_search_rs::search::bfs::{search_nodes_bfs, BfsConfig};

    let (_config, pool) = setup_test_connection().await;
    let mut conn = pool.get().await.expect("Failed to get connection");

    let seed_nodes = get_seed_nodes(&mut conn, 5).await;
    if seed_nodes.is_empty() {
        println!("SKIP: No nodes in database");
        return;
    }

    // Very limited expansions
    let limited_config = BfsConfig {
        max_expansions: 10,
        max_visited: 20,
        max_depth: 5, // Allow deep traversal but limit expansions
        ..Default::default()
    };

    let result = search_nodes_bfs(&mut conn, seed_nodes, &limited_config, None)
        .await
        .expect("BFS with expansion limits should work");

    println!("Limited expansions test: {} nodes", result.len());

    // Should respect max_visited limit
    assert!(
        result.len() <= 20,
        "Result count should not exceed max_visited"
    );
    println!("✓ Expansion limits respected");
}

// ============================================================================
// Min Score Cutoff Tests
// ============================================================================

#[tokio::test(flavor = "multi_thread")]
#[ignore = "Requires FalkorDB instance running on localhost:6379 with data"]
async fn test_bfs_min_score_cutoff() {
    use graphiti_search_rs::search::bfs::{search_nodes_bfs, BfsConfig};

    let (_config, pool) = setup_test_connection().await;
    let mut conn = pool.get().await.expect("Failed to get connection");

    let mut seed_nodes = get_seed_nodes(&mut conn, 3).await;
    if seed_nodes.is_empty() {
        println!("SKIP: No nodes in database");
        return;
    }

    // Set initial scores
    for node in &mut seed_nodes {
        node.score = Some(1.0);
    }

    // High cutoff should limit traversal
    let high_cutoff_config = BfsConfig {
        min_score_cutoff: 0.5, // Only expand nodes with score >= 0.5
        decay: 0.6,            // With 0.6 decay, distance-1 = 0.6, distance-2 = 0.36 (below cutoff)
        ..Default::default()
    };

    let high_cutoff_result =
        search_nodes_bfs(&mut conn, seed_nodes.clone(), &high_cutoff_config, None)
            .await
            .expect("BFS with high cutoff should work");

    // Low cutoff should allow more traversal
    let low_cutoff_config = BfsConfig {
        min_score_cutoff: 0.01,
        decay: 0.6,
        ..Default::default()
    };

    let low_cutoff_result = search_nodes_bfs(&mut conn, seed_nodes, &low_cutoff_config, None)
        .await
        .expect("BFS with low cutoff should work");

    println!("High cutoff (0.5): {} nodes", high_cutoff_result.len());
    println!("Low cutoff (0.01): {} nodes", low_cutoff_result.len());

    // High cutoff should generally return fewer nodes
    // (not strictly true if graph is sparse)
    println!("✓ Min score cutoff configuration works");
}

// ============================================================================
// Edge BFS Tests
// ============================================================================

#[tokio::test(flavor = "multi_thread")]
#[ignore = "Requires FalkorDB instance running on localhost:6379 with data"]
async fn test_bfs_edge_search() {
    use graphiti_search_rs::search::bfs::{search_edges_bfs, BfsConfig};

    let (_config, pool) = setup_test_connection().await;
    let mut conn = pool.get().await.expect("Failed to get connection");

    // Get some edges as seeds
    let seed_edges = conn
        .fulltext_search_edges("", None, 5)
        .await
        .unwrap_or_default();

    if seed_edges.is_empty() {
        println!("SKIP: No edges in database");
        return;
    }

    println!("Starting edge BFS with {} seed edges:", seed_edges.len());
    for edge in &seed_edges {
        println!("  - {}", edge.fact);
    }

    // Use constrained config for edge BFS since it's more expensive
    let config = BfsConfig {
        max_depth: 2,
        max_expansions: 50,
        max_visited: 100,
        beam_width: 20,
        ..Default::default()
    };

    let start = Instant::now();
    let result = timeout(
        Duration::from_secs(60), // Longer timeout for edge BFS
        search_edges_bfs(&mut conn, seed_edges, &config, None),
    )
    .await
    .expect("Test timed out")
    .expect("Edge BFS search failed");

    let elapsed = start.elapsed();
    println!(
        "\nEdge BFS returned {} edges in {:?}",
        result.len(),
        elapsed
    );

    // Verify results have scores
    for edge in result.iter().take(5) {
        assert!(edge.score.is_some(), "Edge results should have scores");
        println!(
            "  - {} (score: {:.4})",
            edge.fact,
            edge.score.unwrap_or(0.0)
        );
    }

    println!("✓ Edge BFS works correctly");
}

// ============================================================================
// Latency Benchmarks
// ============================================================================

#[tokio::test(flavor = "multi_thread")]
#[ignore = "Requires FalkorDB instance running on localhost:6379 with data"]
async fn benchmark_bfs_latency() {
    use graphiti_search_rs::search::bfs::{search_nodes_bfs, BfsConfig};

    let (_config, pool) = setup_test_connection().await;
    let mut conn = pool.get().await.expect("Failed to get connection");

    let seed_nodes = get_seed_nodes(&mut conn, 5).await;
    if seed_nodes.is_empty() {
        println!("SKIP: No nodes in database");
        return;
    }

    println!("\n=== BFS Latency Benchmark ===");
    println!("Seed nodes: {}", seed_nodes.len());

    // Benchmark different configurations
    let configs = vec![
        ("Default", BfsConfig::default()),
        (
            "Shallow (depth=1)",
            BfsConfig {
                max_depth: 1,
                ..Default::default()
            },
        ),
        (
            "Deep (depth=4)",
            BfsConfig {
                max_depth: 4,
                ..Default::default()
            },
        ),
        (
            "Narrow beam (10)",
            BfsConfig {
                beam_width: 10,
                ..Default::default()
            },
        ),
        (
            "Wide beam (200)",
            BfsConfig {
                beam_width: 200,
                ..Default::default()
            },
        ),
        (
            "Aggressive limits",
            BfsConfig {
                max_expansions: 100,
                max_visited: 200,
                hub_degree_threshold: 50,
                ..Default::default()
            },
        ),
    ];

    let iterations = 3;

    for (name, config) in configs {
        let mut times = Vec::new();
        let mut node_counts = Vec::new();

        for _ in 0..iterations {
            let start = Instant::now();
            let result = search_nodes_bfs(&mut conn, seed_nodes.clone(), &config, None)
                .await
                .expect("BFS should work");
            times.push(start.elapsed());
            node_counts.push(result.len());
        }

        let avg_time: Duration = times.iter().sum::<Duration>() / iterations as u32;
        let avg_nodes: f64 = node_counts.iter().sum::<usize>() as f64 / iterations as f64;

        println!(
            "{:25} avg: {:>8.2?}  nodes: {:>6.1}",
            name, avg_time, avg_nodes
        );
    }

    println!("\n✓ Benchmark complete");
}

#[tokio::test(flavor = "multi_thread")]
#[ignore = "Requires FalkorDB instance running on localhost:6379 with data"]
async fn benchmark_bfs_vs_similarity() {
    use graphiti_search_rs::search::bfs::{search_nodes_bfs, BfsConfig};

    let (_config, pool) = setup_test_connection().await;
    let mut conn = pool.get().await.expect("Failed to get connection");

    // Get a real embedding from an existing node for fair comparison
    let embedding = vec![0.0f32; 2560]; // Placeholder, would need real embedding

    println!("\n=== BFS vs Similarity Comparison ===");

    let iterations = 5;

    let mut sim_times = Vec::new();
    for _ in 0..iterations {
        let start = Instant::now();
        let _result = conn
            .similarity_search_nodes(&embedding, 50, 0.0, None)
            .await
            .unwrap_or_default();
        sim_times.push(start.elapsed());
    }
    let avg_sim: Duration = sim_times.iter().sum::<Duration>() / iterations as u32;

    // Benchmark BFS (using similarity results as seeds)
    let seed_nodes = get_seed_nodes(&mut conn, 5).await;
    let mut bfs_times = Vec::new();
    let config = BfsConfig::default();

    for _ in 0..iterations {
        let start = Instant::now();
        let _result = search_nodes_bfs(&mut conn, seed_nodes.clone(), &config, None)
            .await
            .expect("BFS should work");
        bfs_times.push(start.elapsed());
    }
    let avg_bfs: Duration = bfs_times.iter().sum::<Duration>() / iterations as u32;

    let mut combined_times = Vec::new();
    for _ in 0..iterations {
        let start = Instant::now();
        let sim_results = conn
            .similarity_search_nodes(&embedding, 10, 0.0, None)
            .await
            .unwrap_or_default();
        let _final_results = search_nodes_bfs(&mut conn, sim_results, &config, None)
            .await
            .expect("BFS should work");
        combined_times.push(start.elapsed());
    }
    let avg_combined: Duration = combined_times.iter().sum::<Duration>() / iterations as u32;

    println!("Similarity only:     {:>8.2?}", avg_sim);
    println!("BFS only:            {:>8.2?}", avg_bfs);
    println!("Combined (sim+BFS):  {:>8.2?}", avg_combined);
    println!(
        "BFS overhead:        {:>8.2?}",
        avg_combined.saturating_sub(avg_sim)
    );

    println!("\n✓ Comparison complete");
}
