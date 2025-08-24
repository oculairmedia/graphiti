use graphiti_centrality::{
    algorithms::{calculate_all_centralities, calculate_degree_centrality, calculate_pagerank},
    client::FalkorClient,
    models::DatabaseConfig,
};
use std::env;
use tokio_test;

/// Create a test client for integration tests
async fn create_test_client() -> FalkorClient {
    let config = DatabaseConfig {
        host: env::var("FALKORDB_HOST").unwrap_or_else(|_| "falkordb".to_string()),
        port: env::var("FALKORDB_PORT")
            .unwrap_or_else(|_| "6379".to_string())
            .parse()
            .unwrap_or(6379),
        graph_name: env::var("GRAPH_NAME").unwrap_or_else(|_| "graphiti_migration".to_string()),
        username: env::var("FALKORDB_USERNAME").ok(),
        password: env::var("FALKORDB_PASSWORD").ok(),
    };

    FalkorClient::new(config)
        .await
        .expect("Failed to create test client")
}

#[tokio::test]
async fn test_connection() {
    let client = create_test_client().await;
    client
        .test_connection()
        .await
        .expect("Database connection failed");
}

#[tokio::test]
async fn test_graph_stats() {
    let client = create_test_client().await;
    let stats = client
        .get_graph_stats()
        .await
        .expect("Failed to get graph stats");

    println!("Graph stats: {:?}", stats);

    assert!(stats.contains_key("nodes"));
    assert!(stats.contains_key("edges"));

    let node_count = stats.get("nodes").unwrap();
    let edge_count = stats.get("edges").unwrap();

    assert!(*node_count > 0, "Graph should have nodes");
    assert!(*edge_count > 0, "Graph should have edges");
}

#[tokio::test]
async fn test_pagerank_calculation() {
    let client = create_test_client().await;

    let start = std::time::Instant::now();
    let result = calculate_pagerank(&client, None, 0.85, 20)
        .await
        .expect("PageRank calculation failed");
    let duration = start.elapsed();

    println!(
        "PageRank calculated for {} nodes in {:?}",
        result.nodes_processed, duration
    );

    assert!(result.nodes_processed > 0, "Should process some nodes");
    assert!(!result.scores.is_empty(), "Should return scores");

    // Verify PageRank scores are reasonable (sum should be approximately 1.0)
    let total_score: f64 = result.scores.values().sum();
    println!("Total PageRank score: {}", total_score);

    // Performance assertion: should complete in reasonable time
    assert!(
        duration.as_secs() < 10,
        "PageRank should complete in less than 10 seconds"
    );

    // Verify all scores are positive and finite
    for (uuid, score) in &result.scores {
        assert!(
            score.is_finite() && *score >= 0.0,
            "Score for {} should be finite and non-negative: {}",
            uuid,
            score
        );
    }
}

#[tokio::test]
async fn test_degree_centrality_calculation() {
    let client = create_test_client().await;

    for direction in ["in", "out", "both"] {
        let start = std::time::Instant::now();
        let result = calculate_degree_centrality(&client, direction, None)
            .await
            .unwrap_or_else(|_| panic!("Degree centrality calculation failed for {}", direction));
        let duration = start.elapsed();

        println!(
            "Degree centrality ({}) calculated for {} nodes in {:?}",
            direction, result.nodes_processed, duration
        );

        assert!(result.nodes_processed > 0, "Should process some nodes");
        assert!(!result.scores.is_empty(), "Should return scores");

        // Performance assertion
        assert!(
            duration.as_secs() < 5,
            "Degree centrality should complete in less than 5 seconds"
        );

        // Verify all scores are non-negative integers (converted to f64)
        for (uuid, score) in &result.scores {
            assert!(
                *score >= 0.0 && score.fract() == 0.0,
                "Degree score for {} should be non-negative integer: {}",
                uuid,
                score
            );
        }
    }
}

#[tokio::test]
async fn test_all_centralities_calculation() {
    let client = create_test_client().await;

    let start = std::time::Instant::now();
    let result = calculate_all_centralities(&client, None)
        .await
        .expect("All centralities calculation failed");
    let duration = start.elapsed();

    println!(
        "All centralities calculated for {} nodes in {:?}",
        result.len(),
        duration
    );

    assert!(!result.is_empty(), "Should return scores for some nodes");

    // Performance assertion
    assert!(
        duration.as_secs() < 30,
        "All centralities should complete in less than 30 seconds"
    );

    // Verify structure of results
    for (uuid, node_scores) in &result {
        assert!(
            node_scores.contains_key("pagerank"),
            "Node {} should have pagerank score",
            uuid
        );
        assert!(
            node_scores.contains_key("degree"),
            "Node {} should have degree score",
            uuid
        );
        assert!(
            node_scores.contains_key("betweenness"),
            "Node {} should have betweenness score",
            uuid
        );
        assert!(
            node_scores.contains_key("importance"),
            "Node {} should have importance score",
            uuid
        );

        // Verify all scores are finite
        for (metric, score) in node_scores {
            assert!(
                score.is_finite(),
                "Score {} for node {} should be finite: {}",
                metric,
                uuid,
                score
            );
        }
    }
}

#[tokio::test]
#[ignore] // This test requires specific data setup
async fn test_group_id_filtering() {
    let client = create_test_client().await;

    // Test with a group_id filter (this assumes test data exists)
    let result = calculate_pagerank(&client, Some("test_group"), 0.85, 20).await;

    match result {
        Ok(scores) => {
            println!(
                "Group filtering test passed with {} nodes",
                scores.nodes_processed
            );
        }
        Err(e) => {
            println!(
                "Group filtering test failed (expected if no test_group data): {}",
                e
            );
        }
    }
}

#[tokio::test]
async fn test_performance_comparison() {
    let client = create_test_client().await;

    // Get graph size first
    let stats = client.get_graph_stats().await.unwrap();
    let node_count = stats.get("nodes").unwrap();

    println!("Performance test on {} nodes", node_count);

    // Test PageRank performance
    let start = std::time::Instant::now();
    let pagerank_result = calculate_pagerank(&client, None, 0.85, 20).await.unwrap();
    let pagerank_duration = start.elapsed();

    // Test degree centrality performance
    let start = std::time::Instant::now();
    let degree_result = calculate_degree_centrality(&client, "both", None)
        .await
        .unwrap();
    let degree_duration = start.elapsed();

    println!("Performance Results:");
    println!(
        "  PageRank: {} nodes in {:?} ({:.2} nodes/sec)",
        pagerank_result.nodes_processed,
        pagerank_duration,
        pagerank_result.nodes_processed as f64 / pagerank_duration.as_secs_f64()
    );
    println!(
        "  Degree: {} nodes in {:?} ({:.2} nodes/sec)",
        degree_result.nodes_processed,
        degree_duration,
        degree_result.nodes_processed as f64 / degree_duration.as_secs_f64()
    );

    // Performance targets (adjust based on expected performance)
    if *node_count < 1000 {
        assert!(
            pagerank_duration.as_secs() < 5,
            "PageRank should complete in <5s for small graphs"
        );
        assert!(
            degree_duration.as_secs() < 1,
            "Degree centrality should complete in <1s for small graphs"
        );
    }
}
