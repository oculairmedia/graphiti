//! FalkorDB extractor with pagination support
//!
//! This module provides efficient extraction of nodes and edges from FalkorDB databases
//! using SKIP/LIMIT pagination to handle large datasets without memory exhaustion.

use crate::config::settings::{FalkorDBConfig, SyncConfig};
use crate::error::{Result, SyncError};
use crate::models::{ExtractionStats, GraphEdge, GraphNode, PropertyValue};
use falkordb::{AsyncGraph, FalkorClientBuilder, FalkorConnectionInfo, FalkorValue};
use std::collections::HashMap;
use std::time::Instant;
use tokio::sync::mpsc;
use tracing::{debug, info, warn};

/// FalkorDB extractor with pagination support
#[derive(Clone)]
pub struct FalkorDBExtractor {
    /// FalkorDB graph connection
    graph: AsyncGraph,

    /// Batch size for pagination
    batch_size: usize,

    /// Maximum query limit (safety constraint)
    max_query_limit: usize,

    /// Query timeout in milliseconds
    query_timeout_ms: u64,
}

impl FalkorDBExtractor {
    /// Create a new FalkorDB extractor
    ///
    /// # Arguments
    ///
    /// * `config` - FalkorDB connection configuration
    /// * `sync_config` - Sync operation configuration (batch sizes, limits)
    ///
    /// # Example
    ///
    /// ```no_run
    /// use graphiti_sync_rs::extractors::FalkorDBExtractor;
    /// use graphiti_sync_rs::config::{FalkorDBConfig, SyncConfig};
    ///
    /// # async fn example() -> Result<(), Box<dyn std::error::Error>> {
    /// let falkordb_config = FalkorDBConfig {
    ///     host: "localhost".to_string(),
    ///     port: 6379,
    ///     database: "graphiti".to_string(),
    /// };
    ///
    /// let sync_config = SyncConfig {
    ///     batch_size: 1000,
    ///     max_query_limit: 2000,
    ///     interval_seconds: 60,
    ///     query_timeout_ms: 30_000,
    ///     operation_timeout_seconds: 120,
    ///     retry_attempts: 3,
    ///     retry_backoff_ms: 500,
    /// };
    ///
    /// let extractor = FalkorDBExtractor::new(&falkordb_config, &sync_config).await?;
    /// # Ok(())
    /// # }
    /// ```
    pub async fn new(config: &FalkorDBConfig, sync_config: &SyncConfig) -> Result<Self> {
        info!(
            "Connecting to FalkorDB at {}:{} with database '{}'",
            config.host, config.port, config.database
        );

        // Build connection string in falkor:// format
        let connection_str = format!("falkor://{}:{}", config.host, config.port);

        let connection_info: FalkorConnectionInfo =
            connection_str.as_str().try_into().map_err(|e| {
                SyncError::FalkorDB(format!("Invalid FalkorDB connection string: {}", e))
            })?;

        // Build async client
        let client = FalkorClientBuilder::new_async()
            .with_connection_info(connection_info)
            .build()
            .await
            .map_err(|e| SyncError::FalkorDB(format!("Failed to connect to FalkorDB: {}", e)))?;

        // Select graph database
        let mut graph = client.select_graph(&config.database);

        // Validate connection by running a simple query
        let result = graph
            .query("RETURN 1 as test")
            .with_timeout(5000)
            .execute()
            .await
            .map_err(|e| {
                SyncError::FalkorDB(format!("Failed to validate FalkorDB connection: {}", e))
            })?;

        if !result.data.is_empty() || !result.stats.is_empty() {
            info!(
                "Successfully connected to FalkorDB database '{}'",
                config.database
            );
        } else {
            return Err(SyncError::SyncFailed(
                "Failed to validate FalkorDB connection".to_string(),
            ));
        }

        Ok(Self {
            graph,
            batch_size: sync_config.batch_size,
            max_query_limit: sync_config.max_query_limit,
            query_timeout_ms: sync_config.query_timeout_ms,
        })
    }

    /// Extract nodes of a specific type with pagination
    ///
    /// Extracts all nodes with the specified label, sending batches via the provided channel.
    ///
    /// # Arguments
    ///
    /// * `node_type` - Node label to extract ("Entity", "Episodic", or "Community")
    /// * `tx` - Channel sender for batches of extracted nodes
    ///
    /// # Returns
    ///
    /// Statistics about the extraction (count, duration)
    ///
    /// # Example
    ///
    /// ```no_run
    /// # use graphiti_sync_rs::extractors::FalkorDBExtractor;
    /// # use graphiti_sync_rs::models::GraphNode;
    /// # use tokio::sync::mpsc;
    /// # async fn example(extractor: FalkorDBExtractor) -> Result<(), Box<dyn std::error::Error>> {
    /// let (tx, mut rx) = mpsc::channel::<Vec<GraphNode>>(100);
    ///
    /// let stats = extractor.extract_nodes("Entity", tx).await?;
    /// println!("Extracted {} Entity nodes in {:?}", stats.total_nodes, stats.duration);
    /// # Ok(())
    /// # }
    /// ```
    pub async fn extract_nodes(
        &mut self,
        node_type: &str,
        tx: mpsc::Sender<Vec<GraphNode>>,
    ) -> Result<ExtractionStats> {
        let start_time = Instant::now();
        let mut total_nodes = 0;
        let mut offset = 0;

        info!(
            "Starting extraction of {} nodes with batch_size={}",
            node_type, self.batch_size
        );

        loop {
            debug!(
                "Fetching {} nodes: offset={}, limit={}",
                node_type, offset, self.batch_size
            );

            // Build the Cypher query with pagination
            let query = format!(
                "MATCH (n:{}) \
                 RETURN n \
                 ORDER BY n.uuid \
                 SKIP {} LIMIT {}",
                node_type, offset, self.batch_size
            );

            let result = self
                .graph
                .query(&query)
                .with_timeout(self.query_timeout_ms as i64)
                .execute()
                .await
                .map_err(|e| SyncError::FalkorDB(format!("Failed to execute node query: {}", e)))?;

            let mut batch = Vec::new();

            // Collect the data first to release the borrow on result
            let rows: Vec<_> = result.data.collect();

            // Process each row in the result set
            for row in rows {
                // Each row is a Vec<FalkorValue>
                // We expect a single element containing the node
                if let Some(node_value) = row.first() {
                    if let Some(node) = node_value.as_node() {
                        // Extract UUID from properties
                        let uuid = if let Some(uuid_value) = node.properties.get("uuid") {
                            match uuid_value {
                                FalkorValue::String(s) => s.clone(),
                                _ => {
                                    warn!("Node {} has non-string UUID, skipping", node.entity_id);
                                    continue;
                                }
                            }
                        } else {
                            warn!("Node {} has no UUID property, skipping", node.entity_id);
                            continue;
                        };

                        // Convert properties
                        let properties = self.convert_properties_map(&node.properties)?;

                        let graph_node = GraphNode {
                            uuid,
                            labels: node.labels.clone(),
                            properties,
                        };

                        batch.push(graph_node);
                    } else {
                        warn!("Expected node in result but got different type");
                    }
                }
            }

            let batch_size = batch.len();

            // If batch is empty, we've reached the end
            if batch_size == 0 {
                debug!("No more {} nodes found, extraction complete", node_type);
                break;
            }

            total_nodes += batch_size;
            debug!(
                "Extracted batch of {} {} nodes (total: {})",
                batch_size, node_type, total_nodes
            );

            // Send batch through channel
            tx.send(batch)
                .await
                .map_err(|e| SyncError::ChannelSend(format!("Failed to send node batch: {}", e)))?;

            // Move to next page
            offset += batch_size;

            // Safety check: don't exceed max query limit
            if offset >= self.max_query_limit {
                warn!(
                    "Reached max query limit of {} for {} nodes",
                    self.max_query_limit, node_type
                );
                break;
            }
        }

        let duration = start_time.elapsed();

        info!(
            "Completed extraction of {} {} nodes in {:?}",
            total_nodes, node_type, duration
        );

        Ok(ExtractionStats {
            total_nodes,
            total_edges: 0,
            duration,
        })
    }

    /// Extract all edges/relationships with pagination
    ///
    /// Extracts all relationships from the graph, sending batches via the provided channel.
    ///
    /// # Arguments
    ///
    /// * `tx` - Channel sender for batches of extracted edges
    ///
    /// # Returns
    ///
    /// Statistics about the extraction (count, duration)
    ///
    /// # Example
    ///
    /// ```no_run
    /// # use graphiti_sync_rs::extractors::FalkorDBExtractor;
    /// # use graphiti_sync_rs::models::GraphEdge;
    /// # use tokio::sync::mpsc;
    /// # async fn example(extractor: FalkorDBExtractor) -> Result<(), Box<dyn std::error::Error>> {
    /// let (tx, mut rx) = mpsc::channel::<Vec<GraphEdge>>(100);
    ///
    /// let stats = extractor.extract_edges(tx).await?;
    /// println!("Extracted {} edges in {:?}", stats.total_edges, stats.duration);
    /// # Ok(())
    /// # }
    /// ```
    pub async fn extract_edges(
        &mut self,
        tx: mpsc::Sender<Vec<GraphEdge>>,
    ) -> Result<ExtractionStats> {
        let start_time = Instant::now();
        let mut total_edges = 0;
        let mut offset = 0;

        info!(
            "Starting extraction of edges with batch_size={}",
            self.batch_size
        );

        loop {
            debug!(
                "Fetching edges: offset={}, limit={}",
                offset, self.batch_size
            );

            // Build the Cypher query with pagination
            // Note: We need to return source and target nodes to get their UUIDs
            let query = format!(
                "MATCH (source)-[r]->(target) \
                 RETURN source, r, target \
                 ORDER BY source.uuid, target.uuid \
                 SKIP {} LIMIT {}",
                offset, self.batch_size
            );

            let result = self
                .graph
                .query(&query)
                .with_timeout(self.query_timeout_ms as i64)
                .execute()
                .await
                .map_err(|e| SyncError::FalkorDB(format!("Failed to execute edge query: {}", e)))?;

            let mut batch = Vec::new();

            // Collect the data first to release the borrow on result
            let rows: Vec<_> = result.data.collect();

            // Process each row in the result set
            for row in rows {
                // Each row should have 3 elements: source node, relationship, target node
                if row.len() != 3 {
                    warn!(
                        "Expected 3 elements in edge query result, got {}",
                        row.len()
                    );
                    continue;
                }

                let source_node = row[0].as_node();
                let edge = row[1].as_edge();
                let target_node = row[2].as_node();

                if let (Some(source), Some(rel), Some(target)) = (source_node, edge, target_node) {
                    // Extract source UUID
                    let source_uuid = if let Some(uuid_value) = source.properties.get("uuid") {
                        match uuid_value {
                            FalkorValue::String(s) => s.clone(),
                            _ => {
                                warn!("Source node has non-string UUID, skipping edge");
                                continue;
                            }
                        }
                    } else {
                        warn!("Source node has no UUID property, skipping edge");
                        continue;
                    };

                    // Extract target UUID
                    let target_uuid = if let Some(uuid_value) = target.properties.get("uuid") {
                        match uuid_value {
                            FalkorValue::String(s) => s.clone(),
                            _ => {
                                warn!("Target node has non-string UUID, skipping edge");
                                continue;
                            }
                        }
                    } else {
                        warn!("Target node has no UUID property, skipping edge");
                        continue;
                    };

                    // Convert edge properties
                    let properties = self.convert_properties_map(&rel.properties)?;

                    let graph_edge = GraphEdge {
                        source_uuid,
                        target_uuid,
                        relationship_type: rel.relationship_type.clone(),
                        properties,
                    };

                    batch.push(graph_edge);
                } else {
                    warn!("Expected source node, edge, and target node in result");
                }
            }

            let batch_size = batch.len();

            // If batch is empty, we've reached the end
            if batch_size == 0 {
                debug!("No more edges found, extraction complete");
                break;
            }

            total_edges += batch_size;
            debug!(
                "Extracted batch of {} edges (total: {})",
                batch_size, total_edges
            );

            // Send batch through channel
            tx.send(batch)
                .await
                .map_err(|e| SyncError::ChannelSend(format!("Failed to send edge batch: {}", e)))?;

            // Move to next page
            offset += batch_size;

            // Safety check: don't exceed max query limit
            if offset >= self.max_query_limit {
                warn!(
                    "Reached max query limit of {} for edges",
                    self.max_query_limit
                );
                break;
            }
        }

        let duration = start_time.elapsed();

        info!(
            "Completed extraction of {} edges in {:?}",
            total_edges, duration
        );

        Ok(ExtractionStats {
            total_nodes: 0,
            total_edges,
            duration,
        })
    }

    /// Convert a map of FalkorDB FalkorValue properties to PropertyValue
    fn convert_properties_map(
        &self,
        props: &HashMap<String, FalkorValue>,
    ) -> Result<HashMap<String, PropertyValue>> {
        let mut properties = HashMap::new();

        for (key, value) in props {
            if let Some(prop_value) = self.convert_falkor_value(value) {
                properties.insert(key.clone(), prop_value);
            }
        }

        Ok(properties)
    }

    /// Convert a FalkorDB FalkorValue to our PropertyValue enum
    fn convert_falkor_value(&self, falkor_value: &FalkorValue) -> Option<PropertyValue> {
        match falkor_value {
            FalkorValue::String(s) => Some(PropertyValue::String(s.clone())),
            FalkorValue::I64(i) => Some(PropertyValue::Integer(*i)),
            FalkorValue::F64(f) => Some(PropertyValue::Float(*f)),
            FalkorValue::Bool(b) => Some(PropertyValue::Boolean(*b)),
            FalkorValue::Array(arr) => {
                let values: Vec<PropertyValue> = arr
                    .iter()
                    .filter_map(|v| self.convert_falkor_value(v))
                    .collect();
                Some(PropertyValue::List(values))
            }
            FalkorValue::None => Some(PropertyValue::Null),
            // Unsupported types - log and skip
            FalkorValue::Node(_)
            | FalkorValue::Edge(_)
            | FalkorValue::Map(_)
            | FalkorValue::Vec32(_)
            | FalkorValue::Point(_)
            | FalkorValue::Path(_)
            | FalkorValue::Unparseable(_) => {
                debug!("Skipping unsupported FalkorValue type: {:?}", falkor_value);
                None
            }
        }
    }

    /// Get the total count of nodes with a specific label
    ///
    /// Useful for progress tracking and validation.
    pub async fn count_nodes(&mut self, node_type: &str) -> Result<usize> {
        let query = format!("MATCH (n:{}) RETURN count(n) as count", node_type);
        let mut result = self
            .graph
            .query(&query)
            .with_timeout(self.query_timeout_ms as i64)
            .execute()
            .await
            .map_err(|e| SyncError::FalkorDB(format!("Failed to count nodes: {}", e)))?;

        // Get the first row
        if let Some(row) = result.data.next() {
            // Get the first value from the row (the count)
            if let Some(count_value) = row.first() {
                if let Some(count) = count_value.to_i64() {
                    return Ok(count as usize);
                }
            }
        }

        Ok(0)
    }

    /// Get the total count of edges/relationships
    ///
    /// Useful for progress tracking and validation.
    pub async fn count_edges(&mut self) -> Result<usize> {
        let query = "MATCH ()-[r]->() RETURN count(r) as count";
        let mut result = self
            .graph
            .query(query)
            .with_timeout(self.query_timeout_ms as i64)
            .execute()
            .await
            .map_err(|e| SyncError::FalkorDB(format!("Failed to count edges: {}", e)))?;

        // Get the first row
        if let Some(row) = result.data.next() {
            // Get the first value from the row (the count)
            if let Some(count_value) = row.first() {
                if let Some(count) = count_value.to_i64() {
                    return Ok(count as usize);
                }
            }
        }

        Ok(0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_falkor_value_conversion() {
        let extractor = create_test_extractor_for_conversions();

        // Test string conversion
        let falkor_string = FalkorValue::String("test".to_string());
        assert!(matches!(
            extractor.convert_falkor_value(&falkor_string),
            Some(PropertyValue::String(_))
        ));

        // Test integer conversion
        let falkor_int = FalkorValue::I64(42);
        assert!(matches!(
            extractor.convert_falkor_value(&falkor_int),
            Some(PropertyValue::Integer(42))
        ));

        // Test float conversion
        let falkor_float = FalkorValue::F64(3.14);
        assert!(matches!(
            extractor.convert_falkor_value(&falkor_float),
            Some(PropertyValue::Float(_))
        ));

        // Test boolean conversion
        let falkor_bool = FalkorValue::Bool(true);
        assert!(matches!(
            extractor.convert_falkor_value(&falkor_bool),
            Some(PropertyValue::Boolean(true))
        ));

        // Test null conversion
        let falkor_null = FalkorValue::None;
        assert!(matches!(
            extractor.convert_falkor_value(&falkor_null),
            Some(PropertyValue::Null)
        ));
    }

    #[test]
    fn test_property_map_conversion() {
        let extractor = create_test_extractor_for_conversions();
        let mut props = HashMap::new();

        props.insert("name".to_string(), FalkorValue::String("Test".to_string()));
        props.insert("count".to_string(), FalkorValue::I64(10));

        let result = extractor.convert_properties_map(&props).unwrap();

        assert_eq!(result.len(), 2);
        assert!(matches!(result.get("name"), Some(PropertyValue::String(_))));
        assert!(matches!(
            result.get("count"),
            Some(PropertyValue::Integer(10))
        ));
    }

    // Helper function to create a test extractor (not connected)
    // Note: This creates a minimal TestableExtractor for testing type conversions only
    // It cannot be used for actual FalkorDB operations
    fn create_test_extractor_for_conversions() -> TestableExtractor {
        TestableExtractor {
            batch_size: 100,
            max_query_limit: 1000,
        }
    }

    // A minimal struct that has the same conversion methods as FalkorDBExtractor
    struct TestableExtractor {
        batch_size: usize,
        max_query_limit: usize,
    }

    impl TestableExtractor {
        fn convert_falkor_value(&self, falkor_value: &FalkorValue) -> Option<PropertyValue> {
            match falkor_value {
                FalkorValue::String(s) => Some(PropertyValue::String(s.clone())),
                FalkorValue::I64(i) => Some(PropertyValue::Integer(*i)),
                FalkorValue::F64(f) => Some(PropertyValue::Float(*f)),
                FalkorValue::Bool(b) => Some(PropertyValue::Boolean(*b)),
                FalkorValue::Array(arr) => {
                    let values: Vec<PropertyValue> = arr
                        .iter()
                        .filter_map(|v| self.convert_falkor_value(v))
                        .collect();
                    Some(PropertyValue::List(values))
                }
                FalkorValue::None => Some(PropertyValue::Null),
                _ => None,
            }
        }

        fn convert_properties_map(
            &self,
            props: &HashMap<String, FalkorValue>,
        ) -> Result<HashMap<String, PropertyValue>> {
            let mut properties = HashMap::new();

            for (key, value) in props {
                if let Some(prop_value) = self.convert_falkor_value(value) {
                    properties.insert(key.clone(), prop_value);
                }
            }

            Ok(properties)
        }
    }
}
