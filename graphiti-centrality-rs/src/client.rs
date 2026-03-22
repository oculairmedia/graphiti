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
        let result = graph.query(query).execute().await?;

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

    /// Store centrality scores using UNWIND batches with adaptive sizing
    /// and retry-on-backpressure (replaces per-node fallback).
    pub async fn store_centrality_scores(
        &self,
        scores: &HashMap<String, HashMap<String, f64>>,
    ) -> Result<()> {
        info!(
            "Storing centrality scores for {} nodes using batch updates",
            scores.len()
        );

        const INITIAL_BATCH_SIZE: usize = 500;
        const MIN_BATCH_SIZE: usize = 50;
        const INTER_BATCH_DELAY_MS: u64 = 20;
        const MAX_RETRIES: u32 = 3;

        let mut batch_size = INITIAL_BATCH_SIZE;
        let mut processed = 0;

        let score_entries: Vec<(&String, &HashMap<String, f64>)> = scores.iter().collect();
        let mut offset = 0;

        while offset < score_entries.len() {
            let end = (offset + batch_size).min(score_entries.len());
            let chunk = &score_entries[offset..end];

            let mut batch_data = Vec::with_capacity(chunk.len());
            for (node_uuid, node_scores) in chunk {
                let pagerank = node_scores.get("pagerank").copied().unwrap_or(0.0);
                let degree = node_scores.get("degree").copied().unwrap_or(0.0);
                let betweenness = node_scores.get("betweenness").copied().unwrap_or(0.0);
                let eigenvector = node_scores.get("eigenvector").copied().unwrap_or(0.0);
                let importance = node_scores.get("importance").copied().unwrap_or(0.0);

                batch_data.push(format!(
                    "{{uuid: '{}', pr: {}, dg: {}, bt: {}, ev: {}, im: {}}}",
                    node_uuid, pagerank, degree, betweenness, eigenvector, importance
                ));
            }

            let joined_data = batch_data.join(", ");
            let labels = ["Entity", "Episodic"];

            let mut succeeded = false;
            'retry: for attempt in 0..MAX_RETRIES {
                let mut all_ok = true;
                for label in &labels {
                    let batch_query = format!(
                        "UNWIND [{}] AS d
                         MATCH (n:{} {{uuid: d.uuid}})
                         SET n.pagerank_centrality = d.pr,
                             n.degree_centrality = d.dg,
                             n.betweenness_centrality = d.bt,
                             n.eigenvector_centrality = d.ev,
                             n.importance_score = d.im",
                        joined_data, label
                    );
                    if let Err(e) = self.execute_query(&batch_query, None).await {
                        let delay = INTER_BATCH_DELAY_MS * (2_u64.pow(attempt));
                        warn!(
                            "Batch {}-{} ({}) failed (attempt {}/{}), backoff {}ms: {}",
                            offset, end, label, attempt + 1, MAX_RETRIES, delay, e
                        );
                        tokio::time::sleep(std::time::Duration::from_millis(delay)).await;
                        if attempt == MAX_RETRIES - 1 && batch_size > MIN_BATCH_SIZE {
                            batch_size = (batch_size / 2).max(MIN_BATCH_SIZE);
                            warn!("Reducing batch size to {}", batch_size);
                        }
                        all_ok = false;
                        break;
                    }
                }
                if all_ok {
                    processed += chunk.len();
                    succeeded = true;
                    if batch_size < INITIAL_BATCH_SIZE {
                        batch_size = (batch_size * 2).min(INITIAL_BATCH_SIZE);
                    }
                    break 'retry;
                }
            }

            if !succeeded {
                warn!(
                    "Skipping batch {}-{} after {} retries",
                    offset, end, MAX_RETRIES
                );
            }

            offset = end;

            if scores.len() > 1000 && processed % 5000 == 0 && processed > 0 {
                info!(
                    "Stored centrality scores for {}/{} nodes (batch_size={})",
                    processed,
                    scores.len(),
                    batch_size
                );
            }

            tokio::time::sleep(std::time::Duration::from_millis(INTER_BATCH_DELAY_MS)).await;
        }

        info!(
            "Centrality scores stored for {}/{} nodes",
            processed,
            scores.len()
        );
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
