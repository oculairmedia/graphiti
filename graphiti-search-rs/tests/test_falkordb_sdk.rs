use anyhow::Result;
use falkordb::{FalkorClientBuilder, FalkorConnectionInfo, FalkorValue};

#[tokio::test]
#[ignore = "Requires FalkorDB instance running on localhost:6389"]
async fn test_falkordb_sdk_similarity_search() -> Result<()> {
    println!("\n{}", "=".repeat(60));
    println!("Testing FalkorDB SDK Similarity Search");
    println!("{}", "=".repeat(60));

    // Connection configuration
    let conn_url = "redis://localhost:6389";
    let graph_name = "graphiti_migration";

    // Create connection using the SDK
    let conn_info: FalkorConnectionInfo = conn_url.try_into()?;
    let client = FalkorClientBuilder::new_async()
        .with_connection_info(conn_info)
        .build()
        .await?;

    let mut graph = client.select_graph(graph_name);
    println!("✓ Connected to graph: {graph_name}");

    // Test similarity search with vecf32()
    println!("\nTesting similarity search with vecf32()...");

    // Create a small test vector for demonstration
    let test_vector: Vec<f32> = (0..1024).map(|i| ((i as f32) * 0.001).sin()).collect();
    let vector_str = test_vector
        .iter()
        .map(|v| v.to_string())
        .collect::<Vec<_>>()
        .join(",");

    let query = format!(
        "MATCH (n:Entity) 
         WHERE n.name_embedding IS NOT NULL
         WITH n, (2 - vec.cosineDistance(n.name_embedding, vecf32([{vector_str}])))/2 AS score
         WHERE score >= 0.0
         RETURN n.name, n.uuid, score
         ORDER BY score DESC
         LIMIT 5"
    );

    let result = graph.query(&query).execute().await?;
    let data: Vec<_> = result.data.collect();

    assert!(!data.is_empty(), "Should return some results");
    println!("✓ Node similarity search returned {} results", data.len());

    // Display results
    for (i, row) in data.iter().enumerate().take(3) {
        if row.len() >= 3 {
            if let (
                Some(FalkorValue::String(name)),
                Some(FalkorValue::String(_uuid)),
                Some(score_val),
            ) = (row.first(), row.get(1), row.get(2))
            {
                let score = match score_val {
                    FalkorValue::F64(f) => *f,
                    FalkorValue::I64(i) => *i as f64,
                    _ => 0.0,
                };
                println!("  {}. {} (score: {:.4})", i + 1, name, score);
            }
        }
    }

    // Test edge similarity search
    println!("\nTesting edge similarity search...");

    let edge_query = format!(
        "MATCH (a)-[r:RELATES_TO]->(b)
         WHERE r.fact_embedding IS NOT NULL
         WITH r, (2 - vec.cosineDistance(r.fact_embedding, vecf32([{vector_str}])))/2 AS score
         WHERE score >= 0.0
         RETURN r.fact, r.uuid, score
         ORDER BY score DESC
         LIMIT 5"
    );

    let result = graph.query(&edge_query).execute().await?;
    let data: Vec<_> = result.data.collect();

    assert!(!data.is_empty(), "Should return edge results");
    println!("✓ Edge similarity search returned {} results", data.len());

    for (i, row) in data.iter().enumerate().take(3) {
        if row.len() >= 3 {
            if let (
                Some(FalkorValue::String(fact)),
                Some(FalkorValue::String(_uuid)),
                Some(score_val),
            ) = (row.first(), row.get(1), row.get(2))
            {
                let score = match score_val {
                    FalkorValue::F64(f) => *f,
                    FalkorValue::I64(i) => *i as f64,
                    _ => 0.0,
                };
                let preview = if fact.len() > 50 {
                    format!("{}...", &fact[..50])
                } else {
                    fact.clone()
                };
                println!("  {}. {} (score: {:.4})", i + 1, preview, score);
            }
        }
    }

    println!("\n{}", "=".repeat(60));
    println!("✓ SUCCESS! FalkorDB SDK handles similarity search correctly!");
    println!("  No type mismatch errors with vecf32() function");
    println!("{}", "=".repeat(60));

    Ok(())
}

#[tokio::test]
#[ignore = "Requires FalkorDB instance running on localhost:6389"]
async fn test_falkordb_client_v2() -> Result<()> {
    use graphiti_search_rs::config::Config;
    use graphiti_search_rs::falkor::FalkorClientV2;

    println!("\n{}", "=".repeat(60));
    println!("Testing FalkorClientV2 Implementation");
    println!("{}", "=".repeat(60));

    // Load config
    let config = Config::from_env()?;

    // Create client
    let mut client = FalkorClientV2::new(&config).await?;
    println!("✓ FalkorClientV2 created successfully");

    // Test ping
    client.ping().await?;
    println!("✓ Ping successful");

    // Test fulltext search
    let results = client.fulltext_search_nodes("alice", None, 5).await?;
    println!("✓ Fulltext search returned {} results", results.len());

    // Test similarity search with a dummy embedding
    let test_embedding: Vec<f32> = (0..1024).map(|i| ((i as f32) * 0.001).sin()).collect();
    let results = client
        .similarity_search_nodes(&test_embedding, 5, 0.0, None)
        .await?;
    println!(
        "✓ Node similarity search returned {} results",
        results.len()
    );

    let edge_results = client
        .similarity_search_edges(&test_embedding, 5, 0.0, None)
        .await?;
    println!(
        "✓ Edge similarity search returned {} results",
        edge_results.len()
    );

    println!("\n✓ FalkorClientV2 works correctly with the FalkorDB SDK!");

    Ok(())
}
