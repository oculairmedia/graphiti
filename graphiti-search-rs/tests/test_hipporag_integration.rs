#![recursion_limit = "256"]

use std::time::Duration;
use tokio::time::timeout;

#[tokio::test]
#[ignore = "Requires FalkorDB instance running on localhost:6379 with data"]
async fn test_hipporag_search_integration() {
    use graphiti_search_rs::config::Config;
    use graphiti_search_rs::falkor::create_falkor_pool;
    use graphiti_search_rs::models::SearchFilters;
    use graphiti_search_rs::search::hipporag::{search_nodes_hipporag, HippoRAGConfig};

    // Set required env vars for Config::from_env()
    std::env::set_var("FALKORDB_HOST", "localhost");
    std::env::set_var("FALKORDB_PORT", "6379");
    std::env::set_var("GRAPH_NAME", "graphiti_migration");
    std::env::set_var("REDIS_URL", "redis://localhost:6379");

    let config = Config::from_env().expect("Failed to load config");

    let pool = create_falkor_pool(&config)
        .await
        .expect("Failed to create pool");
    let mut conn = pool.get().await.expect("Failed to get connection");

    // Create a dummy embedding (zeros will get low scores but should still work)
    let embedding = vec![0.0f32; 2560];

    let hipporag_config = HippoRAGConfig {
        max_hops: 2,
        decay: 0.85,
        seed_count: 5,
        min_score: 0.0,
        hub_degree_threshold: 200,
        per_hop_limit: 100,
    };

    let filters = SearchFilters::default();

    let result = timeout(
        Duration::from_secs(30),
        search_nodes_hipporag(
            &mut conn,
            &embedding,
            &hipporag_config,
            &filters,
            10,
            10000,
            50,
        ),
    )
    .await
    .expect("Test timed out")
    .expect("HippoRAG search failed");

    println!("HippoRAG search returned {} nodes", result.len());
    for node in &result {
        println!("  - {} (score: {:?})", node.name, node.score);
    }
}
