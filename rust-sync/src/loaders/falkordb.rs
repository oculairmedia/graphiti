use crate::config::{FalkorDBConfig, SyncConfig};
use crate::error::{Result, SyncError};
use crate::models::{GraphEdge, GraphNode, LoadingStats, PropertyValue};
use falkordb::{AsyncGraph, FalkorClientBuilder, FalkorConnectionInfo};
use futures::future::BoxFuture;
use std::time::Instant;
use tokio::sync::mpsc;
use tokio::time::{sleep, Duration};
use tracing::{debug, error, info, warn};

/// FalkorDB loader that handles batch MERGE operations for nodes and edges
///
/// This loader receives data via tokio channels and performs batch writes
/// to FalkorDB using Cypher UNWIND patterns for efficient bulk loading.
pub struct FalkorDBLoader {
    graph: AsyncGraph,
    batch_size: usize,
    retry_attempts: usize,
    retry_backoff_ms: u64,
    chunk_size: usize,
}

impl FalkorDBLoader {
    /// Create a new FalkorDB loader with async connection
    ///
    /// # Arguments
    /// * `falkordb_config` - FalkorDB connection configuration
    /// * `sync_config` - Sync configuration including batch size
    ///
    /// # Errors
    /// Returns error if connection fails or graph selection fails
    pub async fn new(falkordb_config: &FalkorDBConfig, sync_config: &SyncConfig) -> Result<Self> {
        // Build connection string in falkor:// format
        let connection_str = format!("falkor://{}:{}", falkordb_config.host, falkordb_config.port);

        let connection_info: FalkorConnectionInfo =
            connection_str.as_str().try_into().map_err(|e| {
                SyncError::FalkorDB(format!("Invalid FalkorDB connection string: {}", e))
            })?;

        info!(
            "Connecting to FalkorDB at {}:{}",
            falkordb_config.host, falkordb_config.port
        );

        // Build async client
        let client = FalkorClientBuilder::new_async()
            .with_connection_info(connection_info)
            .build()
            .await
            .map_err(|e| SyncError::FalkorDB(format!("Failed to connect to FalkorDB: {}", e)))?;

        // Select graph database
        let graph = client.select_graph(&falkordb_config.database);

        info!(
            "Connected to FalkorDB graph '{}' (batch_size: {}, retry_attempts: {}, retry_backoff: {}ms, chunk_size: {})",
            falkordb_config.database,
            sync_config.batch_size,
            sync_config.retry_attempts,
            sync_config.retry_backoff_ms,
            sync_config.batch_size.max(1).min(100)
        );

        Ok(Self {
            graph,
            batch_size: sync_config.batch_size,
            retry_attempts: sync_config.retry_attempts.max(1),
            retry_backoff_ms: sync_config.retry_backoff_ms.max(50),
            chunk_size: sync_config.batch_size.max(1).min(100),
        })
    }

    /// Load nodes via channel using batch MERGE operations
    ///
    /// Receives batches of nodes from the channel and performs batch MERGE
    /// operations using UNWIND pattern. Tracks statistics and returns them.
    ///
    /// # Arguments
    /// * `rx` - Receiver channel for node batches
    ///
    /// # Returns
    /// LoadingStats with node count and duration
    pub async fn load_nodes(
        &mut self,
        mut rx: mpsc::Receiver<Vec<GraphNode>>,
    ) -> Result<LoadingStats> {
        let start_time = Instant::now();
        let mut total_loaded = 0;
        let mut batch_count = 0;

        info!("Starting node loading with batch_size={}", self.batch_size);

        while let Some(batch) = rx.recv().await {
            let batch_size = batch.len();
            batch_count += 1;

            debug!("Received batch {} with {} nodes", batch_count, batch_size);

            // Execute batch MERGE operation with timing
            let batch_start = Instant::now();
            match self.merge_nodes_batch(&batch).await {
                Ok(_) => {
                    total_loaded += batch_size;
                    let batch_duration = batch_start.elapsed();
                    info!(
                        "Loaded batch {} with {} nodes (total: {}) in {:?} ({:.0} nodes/sec)",
                        batch_count,
                        batch_size,
                        total_loaded,
                        batch_duration,
                        batch_size as f64 / batch_duration.as_secs_f64()
                    );
                }
                Err(e) => {
                    error!(
                        "Failed to load node batch {} (size: {}, total so far: {}) after {:?}: {}",
                        batch_count,
                        batch_size,
                        total_loaded,
                        batch_start.elapsed(),
                        e
                    );
                    return Err(SyncError::FalkorDB(format!(
                        "Node batch {} failed after loading {}/{} nodes: {}",
                        batch_count,
                        total_loaded,
                        total_loaded + batch_size,
                        e
                    )));
                }
            }
        }

        let duration = start_time.elapsed();
        let throughput = if duration.as_secs_f64() > 0.0 {
            total_loaded as f64 / duration.as_secs_f64()
        } else {
            0.0
        };

        info!(
            "✅ Completed loading {} nodes in {} batches ({:?}, {:.0} nodes/sec)",
            total_loaded, batch_count, duration, throughput
        );

        Ok(LoadingStats {
            nodes_loaded: total_loaded,
            edges_loaded: 0,
            duration,
        })
    }

    async fn run_with_retry<T, F>(&mut self, op_name: &str, mut operation: F) -> Result<T>
    where
        F: FnMut(&mut Self) -> BoxFuture<'_, Result<T>>,
    {
        let mut attempt = 0usize;
        let start_time = Instant::now();

        loop {
            let attempt_start = Instant::now();
            match operation(self).await {
                Ok(value) => {
                    if attempt > 0 {
                        info!(
                            "{} succeeded after {} retries (total time: {:?})",
                            op_name,
                            attempt,
                            start_time.elapsed()
                        );
                    }
                    return Ok(value);
                }
                Err(err) => {
                    attempt += 1;
                    let attempt_duration = attempt_start.elapsed();

                    if attempt >= self.retry_attempts {
                        error!(
                            "{} failed permanently after {} attempts (total time: {:?}, last attempt: {:?}): {}",
                            op_name, attempt, start_time.elapsed(), attempt_duration, err
                        );
                        return Err(SyncError::FalkorDB(format!(
                            "{} failed after {} retries over {:?}: {}",
                            op_name,
                            attempt,
                            start_time.elapsed(),
                            err
                        )));
                    }

                    let backoff = self.retry_backoff_ms * attempt as u64;
                    warn!(
                        "{} failed (attempt {}/{}, took {:?}) – retrying in {}ms: {}",
                        op_name, attempt, self.retry_attempts, attempt_duration, backoff, err
                    );
                    sleep(Duration::from_millis(backoff)).await;
                }
            }
        }
    }

    async fn execute_query(&mut self, query: String) -> Result<()> {
        self.graph
            .query(&query)
            .with_timeout(30_000)
            .execute()
            .await
            .map(|_| ())
            .map_err(|e| SyncError::FalkorDB(format!("Failed to execute query: {}", e)))
    }

    /// Load edges via channel using batch MERGE operations
    ///
    /// Receives batches of edges from the channel and performs batch MERGE
    /// operations using UNWIND pattern. Tracks statistics and returns them.
    ///
    /// # Arguments
    /// * `rx` - Receiver channel for edge batches
    ///
    /// # Returns
    /// LoadingStats with edge count and duration
    pub async fn load_edges(
        &mut self,
        mut rx: mpsc::Receiver<Vec<GraphEdge>>,
    ) -> Result<LoadingStats> {
        let start_time = Instant::now();
        let mut total_loaded = 0;
        let mut batch_count = 0;

        info!("Starting edge loading with batch_size={}", self.batch_size);

        while let Some(batch) = rx.recv().await {
            let batch_size = batch.len();
            batch_count += 1;

            debug!("Received batch {} with {} edges", batch_count, batch_size);

            // Execute batch MERGE operation with timing
            let batch_start = Instant::now();
            match self.merge_edges_batch(&batch).await {
                Ok(_) => {
                    total_loaded += batch_size;
                    let batch_duration = batch_start.elapsed();
                    info!(
                        "Loaded batch {} with {} edges (total: {}) in {:?} ({:.0} edges/sec)",
                        batch_count,
                        batch_size,
                        total_loaded,
                        batch_duration,
                        batch_size as f64 / batch_duration.as_secs_f64()
                    );
                }
                Err(e) => {
                    error!(
                        "Failed to load edge batch {} (size: {}, total so far: {}) after {:?}: {}",
                        batch_count,
                        batch_size,
                        total_loaded,
                        batch_start.elapsed(),
                        e
                    );
                    return Err(SyncError::FalkorDB(format!(
                        "Edge batch {} failed after loading {}/{} edges: {}",
                        batch_count,
                        total_loaded,
                        total_loaded + batch_size,
                        e
                    )));
                }
            }
        }

        let duration = start_time.elapsed();
        let throughput = if duration.as_secs_f64() > 0.0 {
            total_loaded as f64 / duration.as_secs_f64()
        } else {
            0.0
        };

        info!(
            "✅ Completed loading {} edges in {} batches ({:?}, {:.0} edges/sec)",
            total_loaded, batch_count, duration, throughput
        );

        Ok(LoadingStats {
            nodes_loaded: 0,
            edges_loaded: total_loaded,
            duration,
        })
    }

    /// MERGE a batch of nodes using UNWIND pattern
    ///
    /// Builds a Cypher query that uses UNWIND to batch process nodes.
    /// Each node is merged by UUID and its properties are set.
    ///
    /// # Arguments
    /// * `nodes` - Slice of graph nodes to merge
    ///
    /// # Errors
    /// Returns error if query execution fails
    async fn merge_nodes_batch(&mut self, nodes: &[GraphNode]) -> Result<()> {
        if nodes.is_empty() {
            return Ok(());
        }

        debug!("Building MERGE query for {} nodes", nodes.len());

        // Group nodes by their label combinations for efficient batching
        // We need to create separate queries for different label combinations
        // because Cypher requires labels to be known at query time
        let mut nodes_by_labels: std::collections::HashMap<Vec<String>, Vec<&GraphNode>> =
            std::collections::HashMap::new();

        for node in nodes {
            let mut labels = node.labels.clone();
            labels.sort(); // Ensure consistent ordering
            nodes_by_labels.entry(labels).or_default().push(node);
        }

        // Process each label group separately
        for (labels, group_nodes) in nodes_by_labels {
            if group_nodes.is_empty() {
                continue;
            }

            // Build label string for Cypher (e.g., ":Entity:Episodic")
            let label_str = if labels.is_empty() {
                String::new()
            } else {
                format!(":{}", labels.join(":"))
            };

            for chunk in group_nodes.chunks(self.chunk_size.max(1)) {
                let mut query_lines = Vec::new();
                query_lines.push("UNWIND [".to_string());

                for (idx, node) in chunk.iter().enumerate() {
                    let node = *node;
                    let props = self.build_node_properties_map(node);
                    let item = format!("{{uuid: \"{}\", props: {}}}", node.uuid, props);

                    if idx < chunk.len() - 1 {
                        query_lines.push(format!("  {},", item));
                    } else {
                        query_lines.push(format!("  {}", item));
                    }
                }

                query_lines.push("] AS item".to_string());
                query_lines.push(format!("MERGE (n{} {{uuid: item.uuid}})", label_str));
                query_lines.push("SET n += item.props".to_string());

                let query = query_lines.join("\n");

                let chunk_start = Instant::now();
                debug!(
                    "Executing MERGE for {} nodes with labels {:?}",
                    chunk.len(),
                    labels
                );

                // Calculate approximate query size for logging
                let query_size_kb = query.len() as f64 / 1024.0;
                if query_size_kb > 100.0 {
                    warn!(
                        "Large query detected: {:.1} KB for {} nodes with labels {:?}",
                        query_size_kb,
                        chunk.len(),
                        labels
                    );
                }
                debug!("Query preview: {}...", &query[..query.len().min(200)]);

                let query_template = query.clone();
                let labels_clone = labels.clone();
                self.run_with_retry("falkordb_node_merge", move |loader| {
                    let query_clone = query_template.clone();
                    Box::pin(async move { loader.execute_query(query_clone).await })
                })
                .await
                .map_err(|e| {
                    SyncError::FalkorDB(format!(
                        "Failed to merge {} nodes with labels {:?} (query size: {:.1} KB): {}",
                        chunk.len(),
                        labels_clone,
                        query_size_kb,
                        e
                    ))
                })?;

                let chunk_duration = chunk_start.elapsed();
                debug!(
                    "Successfully merged {} nodes with labels {:?} in {:?} ({:.0} nodes/sec)",
                    chunk.len(),
                    labels,
                    chunk_duration,
                    chunk.len() as f64 / chunk_duration.as_secs_f64()
                );
            }
        }

        Ok(())
    }

    /// MERGE a batch of edges using UNWIND pattern
    ///
    /// Builds a Cypher query that uses UNWIND to batch process edges.
    /// Matches source and target nodes by UUID and merges the relationship.
    ///
    /// # Arguments
    /// * `edges` - Slice of graph edges to merge
    ///
    /// # Errors
    /// Returns error if query execution fails
    async fn merge_edges_batch(&mut self, edges: &[GraphEdge]) -> Result<()> {
        if edges.is_empty() {
            return Ok(());
        }

        debug!("Building MERGE query for {} edges", edges.len());

        // Group edges by relationship type for efficient batching
        let mut edges_by_type: std::collections::HashMap<String, Vec<&GraphEdge>> =
            std::collections::HashMap::new();

        for edge in edges {
            edges_by_type
                .entry(edge.relationship_type.clone())
                .or_default()
                .push(edge);
        }

        // Process each relationship type separately
        for (rel_type, group_edges) in edges_by_type {
            if group_edges.is_empty() {
                continue;
            }

            for chunk in group_edges.chunks(self.chunk_size.max(1)) {
                let mut query_lines = Vec::new();
                query_lines.push("UNWIND [".to_string());

                for (idx, edge) in chunk.iter().enumerate() {
                    let edge = *edge;
                    let props = self.build_edge_properties_map(edge);
                    let item = format!(
                        "{{source: \"{}\", target: \"{}\", props: {}}}",
                        edge.source_uuid, edge.target_uuid, props
                    );

                    if idx < chunk.len() - 1 {
                        query_lines.push(format!("  {},", item));
                    } else {
                        query_lines.push(format!("  {}", item));
                    }
                }

                query_lines.push("] AS item".to_string());
                query_lines.push("MATCH (source {uuid: item.source})".to_string());
                query_lines.push("MATCH (target {uuid: item.target})".to_string());
                query_lines.push(format!(
                    "MERGE (source)-[r:{}]->(target)",
                    Self::escape_identifier(&rel_type)
                ));
                query_lines.push("SET r += item.props".to_string());

                let query = query_lines.join("\n");

                let chunk_start = Instant::now();
                debug!(
                    "Executing MERGE for {} edges with type '{}'",
                    chunk.len(),
                    rel_type
                );

                // Calculate approximate query size for logging
                let query_size_kb = query.len() as f64 / 1024.0;
                if query_size_kb > 100.0 {
                    warn!(
                        "Large edge query detected: {:.1} KB for {} edges of type '{}'",
                        query_size_kb,
                        chunk.len(),
                        rel_type
                    );
                }
                debug!("Query preview: {}...", &query[..query.len().min(200)]);

                let query_template = query.clone();
                let rel_type_clone = rel_type.clone();
                self.run_with_retry("falkordb_edge_merge", move |loader| {
                    let query_clone = query_template.clone();
                    Box::pin(async move { loader.execute_query(query_clone).await })
                })
                .await
                .map_err(|e| {
                    SyncError::FalkorDB(format!(
                        "Failed to merge {} edges with type '{}' (query size: {:.1} KB): {}",
                        chunk.len(),
                        rel_type_clone,
                        query_size_kb,
                        e
                    ))
                })?;

                let chunk_duration = chunk_start.elapsed();
                debug!(
                    "Successfully merged {} edges with type '{}' in {:?} ({:.0} edges/sec)",
                    chunk.len(),
                    rel_type,
                    chunk_duration,
                    chunk.len() as f64 / chunk_duration.as_secs_f64()
                );
            }
        }

        Ok(())
    }

    /// Build a Cypher properties map for a node
    ///
    /// Converts the node's properties HashMap into a Cypher map literal string.
    /// Handles proper escaping of values.
    fn build_node_properties_map(&self, node: &GraphNode) -> String {
        let mut props = Vec::new();

        // Include uuid in properties (redundant but consistent)
        props.push(format!("uuid: \"{}\"", Self::escape_string(&node.uuid)));

        // Add all other properties
        for (key, value) in &node.properties {
            let escaped_key = Self::escape_identifier(key);
            let value_str = Self::property_value_to_cypher(value);
            props.push(format!("{}: {}", escaped_key, value_str));
        }

        format!("{{{}}}", props.join(", "))
    }

    /// Build a Cypher properties map for an edge
    ///
    /// Converts the edge's properties HashMap into a Cypher map literal string.
    /// Handles proper escaping of values.
    fn build_edge_properties_map(&self, edge: &GraphEdge) -> String {
        if edge.properties.is_empty() {
            return "{}".to_string();
        }

        let mut props = Vec::new();

        for (key, value) in &edge.properties {
            let escaped_key = Self::escape_identifier(key);
            let value_str = Self::property_value_to_cypher(value);
            props.push(format!("{}: {}", escaped_key, value_str));
        }

        format!("{{{}}}", props.join(", "))
    }

    /// Convert PropertyValue to Cypher literal syntax
    ///
    /// Handles all PropertyValue types and properly escapes strings.
    fn property_value_to_cypher(value: &PropertyValue) -> String {
        match value {
            PropertyValue::String(s) => format!("\"{}\"", Self::escape_string(s)),
            PropertyValue::Integer(i) => i.to_string(),
            PropertyValue::Float(f) => {
                // Handle special float values
                if f.is_nan() {
                    warn!("Encountered NaN value, converting to null");
                    "null".to_string()
                } else if f.is_infinite() {
                    warn!("Encountered infinite value, converting to null");
                    "null".to_string()
                } else {
                    f.to_string()
                }
            }
            PropertyValue::Boolean(b) => b.to_string(),
            PropertyValue::List(items) => {
                let values: Vec<String> =
                    items.iter().map(Self::property_value_to_cypher).collect();
                format!("[{}]", values.join(", "))
            }
            PropertyValue::Null => "null".to_string(),
        }
    }

    /// Escape a string for use in Cypher string literals
    ///
    /// Escapes double quotes, backslashes, and newlines.
    fn escape_string(s: &str) -> String {
        s.replace('\\', "\\\\")
            .replace('"', "\\\"")
            .replace('\n', "\\n")
            .replace('\r', "\\r")
            .replace('\t', "\\t")
    }

    /// Escape an identifier for use in Cypher
    ///
    /// Wraps identifiers with backticks if they contain special characters.
    fn escape_identifier(s: &str) -> String {
        // Check if identifier needs escaping
        let needs_escape = !s.chars().all(|c| c.is_alphanumeric() || c == '_')
            || s.chars().next().map_or(false, |c| c.is_numeric());

        if needs_escape {
            format!("`{}`", s.replace('`', "``"))
        } else {
            s.to_string()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_escape_string() {
        assert_eq!(FalkorDBLoader::escape_string("simple"), "simple");
        assert_eq!(
            FalkorDBLoader::escape_string("with \"quotes\""),
            "with \\\"quotes\\\""
        );
        assert_eq!(
            FalkorDBLoader::escape_string("with\nnewline"),
            "with\\nnewline"
        );
        assert_eq!(
            FalkorDBLoader::escape_string("back\\slash"),
            "back\\\\slash"
        );
    }

    #[test]
    fn test_escape_identifier() {
        assert_eq!(
            FalkorDBLoader::escape_identifier("simple_name"),
            "simple_name"
        );
        assert_eq!(
            FalkorDBLoader::escape_identifier("with space"),
            "`with space`"
        );
        assert_eq!(
            FalkorDBLoader::escape_identifier("123numeric"),
            "`123numeric`"
        );
        assert_eq!(
            FalkorDBLoader::escape_identifier("special-char"),
            "`special-char`"
        );
    }

    #[test]
    fn test_property_value_to_cypher() {
        assert_eq!(
            FalkorDBLoader::property_value_to_cypher(&PropertyValue::String("test".to_string())),
            "\"test\""
        );
        assert_eq!(
            FalkorDBLoader::property_value_to_cypher(&PropertyValue::Integer(42)),
            "42"
        );
        assert_eq!(
            FalkorDBLoader::property_value_to_cypher(&PropertyValue::Float(2.718)),
            "2.718"
        );
        assert_eq!(
            FalkorDBLoader::property_value_to_cypher(&PropertyValue::Boolean(true)),
            "true"
        );
        assert_eq!(
            FalkorDBLoader::property_value_to_cypher(&PropertyValue::Null),
            "null"
        );

        // Test list
        let list = PropertyValue::List(vec![
            PropertyValue::Integer(1),
            PropertyValue::Integer(2),
            PropertyValue::Integer(3),
        ]);
        assert_eq!(FalkorDBLoader::property_value_to_cypher(&list), "[1, 2, 3]");
    }

    #[test]
    fn test_property_value_to_cypher_with_escaping() {
        // Test string escaping
        assert_eq!(
            FalkorDBLoader::property_value_to_cypher(&PropertyValue::String(
                "with \"quotes\"".to_string()
            )),
            "\"with \\\"quotes\\\"\""
        );

        assert_eq!(
            FalkorDBLoader::property_value_to_cypher(&PropertyValue::String(
                "with\nnewline".to_string()
            )),
            "\"with\\nnewline\""
        );

        // Test nested list
        let nested_list = PropertyValue::List(vec![
            PropertyValue::String("a".to_string()),
            PropertyValue::String("b".to_string()),
            PropertyValue::Integer(42),
        ]);
        assert_eq!(
            FalkorDBLoader::property_value_to_cypher(&nested_list),
            "[\"a\", \"b\", 42]"
        );
    }
}
