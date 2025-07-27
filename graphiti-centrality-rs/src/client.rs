use crate::error::{CentralityError, Result};
use crate::models::DatabaseConfig;
use falkordb::{FalkorAsyncClient, FalkorClientBuilder, FalkorConnectionInfo, FalkorValue};
use std::collections::HashMap;
use std::sync::Arc;
use tracing::{debug, info, warn};

/// High-performance FalkorDB client optimized for centrality calculations
#[derive(Clone)]
pub struct FalkorClient {
    client: Arc<FalkorAsyncClient>,
    graph_name: String,
}

impl FalkorClient {
    /// Create a new FalkorDB client with optimized settings
    pub async fn new(config: DatabaseConfig) -> Result<Self> {
        info!(
            "Connecting to FalkorDB at {}:{}, graph: {}",
            config.host, config.port, config.graph_name
        );

        let connection_string = format!("falkor://{}:{}", config.host, config.port);
        let connection_info: FalkorConnectionInfo = connection_string
            .as_str()
            .try_into()
            .map_err(|e| CentralityError::internal(format!("Invalid connection info: {}", e)))?;

        let client = FalkorClientBuilder::new_async()
            .with_connection_info(connection_info)
            .build()
            .await?;

        Ok(Self {
            client: Arc::new(client),
            graph_name: config.graph_name,
        })
    }

    /// Execute a query and return results as a vector of hash maps
    pub async fn execute_query(
        &self,
        query: &str,
        _params: Option<HashMap<String, FalkorValue>>,
    ) -> Result<Vec<HashMap<String, FalkorValue>>> {
        debug!("Executing query: {}", query);

        let mut graph = self.client.select_graph(&self.graph_name);
        let result = graph
            .query(query)
            .execute()
            .await?;

        let mut records = Vec::new();

        // Convert FalkorDB result format to our internal format
        for row in result.data {
            let mut record = HashMap::new();

            // Get column names from the header and map to values
            for (i, header) in result.header.iter().enumerate() {
                if let Some(value) = row.get(i) {
                    record.insert(header.clone(), value.clone() as FalkorValue);
                }
            }

            records.push(record);
        }

        debug!("Query returned {} records", records.len());
        Ok(records)
    }

    /// Test database connectivity
    pub async fn test_connection(&self) -> Result<()> {
        let query = "RETURN 1 as test";
        let results = self.execute_query(query, None).await?;

        if results.is_empty() {
            return Err(CentralityError::internal("Connection test failed"));
        }

        info!("FalkorDB connection test successful");
        Ok(())
    }

    /// Get basic graph statistics
    pub async fn get_graph_stats(&self) -> Result<HashMap<String, u64>> {
        let node_count_query = "MATCH (n) RETURN count(n) as count";
        let edge_count_query = "MATCH ()-[r]->() RETURN count(r) as count";

        let node_results = self.execute_query(node_count_query, None).await?;
        let edge_results = self.execute_query(edge_count_query, None).await?;

        let mut stats = HashMap::new();

        if let Some(node_record) = node_results.first() {
            if let Some(FalkorValue::I64(count)) = node_record.get("count") {
                stats.insert("nodes".to_string(), *count as u64);
            }
        }

        if let Some(edge_record) = edge_results.first() {
            if let Some(FalkorValue::I64(count)) = edge_record.get("count") {
                stats.insert("edges".to_string(), *count as u64);
            }
        }

        Ok(stats)
    }

    /// Store centrality scores back to the database
    pub async fn store_centrality_scores(
        &self,
        scores: &HashMap<String, HashMap<String, f64>>,
    ) -> Result<()> {
        info!("Storing centrality scores for {} nodes", scores.len());

        for (node_uuid, node_scores) in scores {
            let mut set_clauses = Vec::new();

            for (score_name, score_value) in node_scores {
                // Convert score names to match frontend expectations
                let property_name = match score_name.as_str() {
                    "pagerank" => "pagerank_centrality",
                    "degree" => "degree_centrality", 
                    "betweenness" => "betweenness_centrality",
                    "importance" => "eigenvector_centrality", // Map importance to eigenvector
                    _ => &format!("{}_centrality", score_name),
                };
                set_clauses.push(format!("n.{} = {}", property_name, score_value));
            }

            if !set_clauses.is_empty() {
                // Use direct query without parameters
                let query = format!(
                    "MATCH (n {{uuid: '{}'}}) SET {}",
                    node_uuid,
                    set_clauses.join(", ")
                );

                if let Err(e) = self.execute_query(&query, None).await {
                    warn!("Failed to store scores for node {}: {}", node_uuid, e);
                    // Continue with other nodes rather than failing completely
                }
            }
        }

        info!("Centrality scores stored successfully");
        Ok(())
    }

    /// Get the graph name this client is connected to
    pub fn graph_name(&self) -> &str {
        &self.graph_name
    }
}

/// Utility functions for converting FalkorValue types
pub fn falkor_value_to_string(value: &FalkorValue) -> String {
    match value {
        FalkorValue::String(s) => s.clone(),
        FalkorValue::I64(i) => i.to_string(),
        FalkorValue::F64(f) => f.to_string(),
        FalkorValue::Bool(b) => b.to_string(),
        FalkorValue::None => String::new(),
        _ => format!("{:?}", value),
    }
}

pub fn falkor_value_to_f64(value: &FalkorValue) -> Option<f64> {
    match value {
        FalkorValue::F64(f) => Some(*f),
        FalkorValue::I64(i) => Some(*i as f64),
        FalkorValue::String(s) => s.parse().ok(),
        _ => None,
    }
}

pub fn falkor_value_to_i64(value: &FalkorValue) -> Option<i64> {
    match value {
        FalkorValue::I64(i) => Some(*i),
        FalkorValue::F64(f) => Some(*f as i64),
        FalkorValue::String(s) => s.parse().ok(),
        _ => None,
    }
}