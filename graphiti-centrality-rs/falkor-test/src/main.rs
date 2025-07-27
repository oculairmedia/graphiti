use falkordb::{FalkorClientBuilder, FalkorConnectionInfo, FalkorValue};
use std::collections::HashMap;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("Testing FalkorDB query syntax...");
    
    // Connect to FalkorDB
    let connection_string = "falkor://localhost:6389";
    let connection_info: FalkorConnectionInfo = connection_string.try_into()?;
    
    let client = FalkorClientBuilder::new_async()
        .with_connection_info(connection_info)
        .build()
        .await?;
    
    let mut graph = client.select_graph("graphiti_migration");
    
    // Test 1: Direct query without parameters (simplest approach)
    println!("\n1. Testing direct query without parameters:");
    let uuid = "test-uuid-123";
    let query = format!("MATCH (n {{uuid: '{}'}}) SET n.direct_test = 0.99", uuid);
    
    match graph.query(&query).execute().await {
        Ok(_) => println!("✓ Direct query worked"),
        Err(e) => println!("✗ Direct query failed: {}", e),
    }
    
    // Test 2: Get a real node and update it
    println!("\n2. Testing with real node:");
    let query = "MATCH (n) RETURN n.uuid as uuid LIMIT 1";
    
    if let Ok(mut result) = graph.query(query).execute().await {
        // Process the lazy result set
        let mut found_uuid = None;
        for row in result.data {
            if let Some(FalkorValue::String(real_uuid)) = row.first() {
                found_uuid = Some(real_uuid.clone());
                break;
            }
        }
        
        if let Some(real_uuid) = found_uuid {
            println!("Found real node: {}", real_uuid);
            
            // Try direct update with multiple properties
            let query = format!(
                "MATCH (n {{uuid: '{}'}}) SET n.pagerank_centrality = {}, n.degree_centrality = {}, n.betweenness_centrality = {}, n.eigenvector_centrality = {}",
                real_uuid, 0.123, 0.456, 0.789, 0.999
            );
            
            match graph.query(&query).execute().await {
                Ok(_) => println!("✓ Real node multiple property update worked"),
                Err(e) => println!("✗ Real node multiple property update failed: {}", e),
            }
            
            // Verify the update
            let query = format!(
                "MATCH (n {{uuid: '{}'}}) RETURN n.pagerank_centrality, n.degree_centrality, n.betweenness_centrality, n.eigenvector_centrality",
                real_uuid
            );
            
            if let Ok(mut result) = graph.query(&query).execute().await {
                for row in result.data {
                    println!("Updated values: {:?}", row);
                }
            }
        }
    }
    
    // Test 3: Try parameterized query with String parameters
    println!("\n3. Testing parameterized query with String params:");
    let uuid_value = "test-uuid-456";
    let query = "MATCH (n {uuid: $uuid}) RETURN n.uuid LIMIT 1";
    let mut params = HashMap::new();
    params.insert("uuid".to_string(), uuid_value.to_string());
    
    match graph.query(query).with_params(&params).execute().await {
        Ok(mut result) => {
            println!("✓ Parameterized query worked");
            for row in result.data {
                println!("  Result: {:?}", row);
            }
        },
        Err(e) => println!("✗ Parameterized query failed: {}", e),
    }
    
    // Test 4: Try parameterized SET with numeric values as strings
    println!("\n4. Testing parameterized SET with numeric strings:");
    let query = "MATCH (n {uuid: $uuid}) SET n.test_value = toFloat($value)";
    let mut params = HashMap::new();
    params.insert("uuid".to_string(), uuid_value.to_string());
    params.insert("value".to_string(), "0.12345".to_string());
    
    match graph.query(query).with_params(&params).execute().await {
        Ok(_) => println!("✓ Parameterized SET with toFloat worked"),
        Err(e) => println!("✗ Parameterized SET with toFloat failed: {}", e),
    }
    
    println!("\nDone testing!");
    Ok(())
}