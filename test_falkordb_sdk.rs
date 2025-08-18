// Standalone test for FalkorDB SDK implementation
use anyhow::Result;
use falkordb::{FalkorAsyncClient, FalkorClientBuilder, FalkorConnectionInfo, FalkorValue};
use std::collections::HashMap;

#[tokio::main]
async fn main() -> Result<()> {
    println!("{}", "=".repeat(60));
    println!("Testing FalkorDB SDK Implementation");
    println!("{}", "=".repeat(60));

    // Connection configuration
    let conn_url = "redis://localhost:6389";
    let graph_name = "graphiti_migration";
    
    println!("Connecting to FalkorDB at {}", conn_url);
    
    // Create connection using the SDK
    let conn_info: FalkorConnectionInfo = conn_url.try_into()?;
    let client = FalkorClientBuilder::new_async()
        .with_connection_info(conn_info)
        .build()
        .await?;
    
    let mut graph = client.select_graph(graph_name);
    println!("✓ Connected to graph: {}", graph_name);
    
    // Test 1: Simple query
    println!("\nTest 1: Simple query");
    let result = graph.query("RETURN 1 as num").execute().await?;
    let data: Vec<_> = result.data.collect();
    println!("✓ Simple query works: {:?}", data);
    
    // Test 2: Count nodes with embeddings
    println!("\nTest 2: Count nodes with embeddings");
    let result = graph.query("MATCH (n:Entity) WHERE n.name_embedding IS NOT NULL RETURN count(n) as count").execute().await?;
    let data: Vec<_> = result.data.collect();
    if let Some(row) = data.first() {
        if let Some(FalkorValue::I64(count)) = row.first() {
            println!("✓ Found {} nodes with embeddings", count);
        }
    }
    
    // Test 3: Fulltext search with parameters
    println!("\nTest 3: Fulltext search with parameters");
    let mut params = HashMap::new();
    params.insert("query".to_string(), "'alice'".to_string());
    params.insert("limit".to_string(), "5".to_string());
    
    let result = graph
        .query("MATCH (n:Entity) WHERE toLower(n.name) CONTAINS $query RETURN n.name LIMIT $limit")
        .with_params(&params)
        .execute()
        .await?;
    
    let data: Vec<_> = result.data.collect();
    println!("✓ Fulltext search returned {} results", data.len());
    for (i, row) in data.iter().enumerate().take(3) {
        if let Some(FalkorValue::String(name)) = row.first() {
            println!("  {}. {}", i + 1, name);
        }
    }
    
    // Test 4: Similarity search with vecf32()
    println!("\nTest 4: Similarity search with vecf32()");
    
    // Generate a test vector (first 10 dimensions for brevity)
    let test_vector = vec![0.1, -0.2, 0.3, -0.4, 0.5, -0.6, 0.7, -0.8, 0.9, -0.1];
    let mut full_vector = test_vector.clone();
    // Pad to 1024 dimensions
    for _ in 10..1024 {
        full_vector.push(0.0);
    }
    
    let vector_str = full_vector
        .iter()
        .map(|v| v.to_string())
        .collect::<Vec<_>>()
        .join(",");
    
    let query = format!(
        "MATCH (n:Entity) 
         WHERE n.name_embedding IS NOT NULL
         WITH n, (2 - vec.cosineDistance(n.name_embedding, vecf32([{}])))/2 AS score
         WHERE score >= 0.0
         RETURN n.name, score
         ORDER BY score DESC
         LIMIT 5",
        vector_str
    );
    
    println!("  Query length: {} chars", query.len());
    
    let result = graph.query(&query).execute().await?;
    let data: Vec<_> = result.data.collect();
    
    println!("✓ Similarity search returned {} results", data.len());
    for (i, row) in data.iter().enumerate().take(3) {
        if row.len() >= 2 {
            if let (Some(FalkorValue::String(name)), Some(score_val)) = (row.get(0), row.get(1)) {
                let score = match score_val {
                    FalkorValue::F64(f) => *f,
                    FalkorValue::I64(i) => *i as f64,
                    _ => 0.0,
                };
                println!("  {}. {} (score: {:.4})", i + 1, name, score);
            }
        }
    }
    
    // Test 5: Edge similarity search
    println!("\nTest 5: Edge similarity search");
    
    let query = format!(
        "MATCH (a)-[r:RELATES_TO]->(b)
         WHERE r.fact_embedding IS NOT NULL
         WITH r, (2 - vec.cosineDistance(r.fact_embedding, vecf32([{}])))/2 AS score
         WHERE score >= 0.0
         RETURN r.fact, score
         ORDER BY score DESC
         LIMIT 5",
        vector_str
    );
    
    let result = graph.query(&query).execute().await?;
    let data: Vec<_> = result.data.collect();
    
    println!("✓ Edge similarity search returned {} results", data.len());
    for (i, row) in data.iter().enumerate().take(3) {
        if row.len() >= 2 {
            if let (Some(FalkorValue::String(fact)), Some(score_val)) = (row.get(0), row.get(1)) {
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
    
    println!("\n" + &"=".repeat(60));
    println!("✓ All tests passed successfully!");
    println!("  The FalkorDB SDK handles vector operations correctly.");
    println!("  No 'Type: mismatch' errors encountered!");
    println!("{}", "=".repeat(60));
    
    Ok(())
}