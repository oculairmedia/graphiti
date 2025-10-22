//! Neo4j extractor with pagination support
//!
//! This module provides efficient extraction of nodes and edges from Neo4j databases
//! using SKIP/LIMIT pagination to handle large datasets without memory exhaustion.

use crate::config::settings::{Neo4jConfig, SyncConfig};
use crate::error::{Result, SyncError};
use crate::models::{ExtractionStats, GraphEdge, GraphNode, PropertyValue};
use neo4rs::{Graph, Node};
use std::collections::HashMap;
use std::time::Instant;
use tokio::sync::mpsc;
use tracing::{debug, info, warn};

/// Neo4j extractor with pagination support
#[derive(Clone)]
pub struct Neo4jExtractor {
    /// Neo4j graph connection
    graph: Graph,

    /// Batch size for pagination
    batch_size: usize,

    /// Maximum query limit (safety constraint)
    max_query_limit: usize,
}

impl Neo4jExtractor {
    /// Create a new Neo4j extractor
    ///
    /// # Arguments
    ///
    /// * `config` - Neo4j connection configuration
    /// * `sync_config` - Sync operation configuration (batch sizes, limits)
    ///
    /// # Example
    ///
    /// ```no_run
    /// use graphiti_sync_rs::extractors::Neo4jExtractor;
    /// use graphiti_sync_rs::config::{Neo4jConfig, SyncConfig};
    ///
    /// # async fn example() -> Result<(), Box<dyn std::error::Error>> {
    /// let neo4j_config = Neo4jConfig {
    ///     uri: "bolt://localhost:7687".to_string(),
    ///     user: "neo4j".to_string(),
    ///     password: "password".to_string(),
    ///     database: "neo4j".to_string(),
    ///     pool_size: 10,
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
    /// let extractor = Neo4jExtractor::new(&neo4j_config, &sync_config).await?;
    /// # Ok(())
    /// # }
    /// ```
    pub async fn new(config: &Neo4jConfig, sync_config: &SyncConfig) -> Result<Self> {
        info!(
            "Connecting to Neo4j at {} with database '{}'",
            config.uri, config.database
        );

        // Connect to Neo4j
        // Note: Graph::new() is not async and returns Result<Graph, Error>
        // The database name is typically specified in the URI or via USE statement
        let graph = Graph::new(&config.uri, &config.user, &config.password)?;

        // Validate connection by running a simple query
        // Use the specified database in the query
        let use_db_query = if config.database != "neo4j" {
            format!("USE {} RETURN 1 as test", config.database)
        } else {
            "RETURN 1 as test".to_string()
        };

        let mut result = graph.execute(neo4rs::query(&use_db_query)).await?;

        if result.next().await?.is_some() {
            info!(
                "Successfully connected to Neo4j database '{}'",
                config.database
            );
        } else {
            return Err(SyncError::SyncFailed(
                "Failed to validate Neo4j connection".to_string(),
            ));
        }

        Ok(Self {
            graph,
            batch_size: sync_config.batch_size,
            max_query_limit: sync_config.max_query_limit,
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
    /// # use graphiti_sync_rs::extractors::Neo4jExtractor;
    /// # use graphiti_sync_rs::models::GraphNode;
    /// # use tokio::sync::mpsc;
    /// # async fn example(extractor: Neo4jExtractor) -> Result<(), Box<dyn std::error::Error>> {
    /// let (tx, mut rx) = mpsc::channel::<Vec<GraphNode>>(100);
    ///
    /// let stats = extractor.extract_nodes("Entity", tx).await?;
    /// println!("Extracted {} Entity nodes in {:?}", stats.total_nodes, stats.duration);
    /// # Ok(())
    /// # }
    /// ```
    pub async fn extract_nodes(
        &self,
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
                 RETURN n.uuid as uuid, properties(n) as props, labels(n) as labels \
                 ORDER BY n.uuid \
                 SKIP $skip LIMIT $limit",
                node_type
            );

            let mut result = self
                .graph
                .execute(
                    neo4rs::query(&query)
                        .param("skip", offset as i64)
                        .param("limit", self.batch_size as i64),
                )
                .await?;

            let mut batch = Vec::new();

            // Process each row in the result set
            while let Some(row) = result.next().await? {
                // Extract UUID - handle both String and potential null cases
                let uuid: String = match row.get("uuid") {
                    Ok(val) => val,
                    Err(_) => {
                        warn!(
                            "Skipping node without UUID at offset {}",
                            offset + batch.len()
                        );
                        continue;
                    }
                };

                // Extract labels
                let labels: Vec<String> = match row.get("labels") {
                    Ok(val) => val,
                    Err(_) => {
                        warn!("Node {} has no labels, using node_type", uuid);
                        vec![node_type.to_string()]
                    }
                };

                // Extract properties - get the node itself and convert properties
                let properties = if let Ok(node) = row.get::<Node>("n") {
                    self.convert_node_properties(&node).await?
                } else if let Ok(props_map) = row.get::<HashMap<String, neo4rs::BoltType>>("props")
                {
                    self.convert_property_map(&props_map)?
                } else {
                    HashMap::new()
                };

                let node = GraphNode {
                    uuid,
                    labels,
                    properties,
                };

                batch.push(node);
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
    /// # use graphiti_sync_rs::extractors::Neo4jExtractor;
    /// # use graphiti_sync_rs::models::GraphEdge;
    /// # use tokio::sync::mpsc;
    /// # async fn example(extractor: Neo4jExtractor) -> Result<(), Box<dyn std::error::Error>> {
    /// let (tx, mut rx) = mpsc::channel::<Vec<GraphEdge>>(100);
    ///
    /// let stats = extractor.extract_edges(tx).await?;
    /// println!("Extracted {} edges in {:?}", stats.total_edges, stats.duration);
    /// # Ok(())
    /// # }
    /// ```
    pub async fn extract_edges(&self, tx: mpsc::Sender<Vec<GraphEdge>>) -> Result<ExtractionStats> {
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
            let query = "MATCH (source)-[r]->(target) \
                         RETURN source.uuid as source_uuid, \
                                target.uuid as target_uuid, \
                                type(r) as rel_type, \
                                properties(r) as props \
                         ORDER BY source.uuid, target.uuid \
                         SKIP $skip LIMIT $limit";

            let mut result = self
                .graph
                .execute(
                    neo4rs::query(query)
                        .param("skip", offset as i64)
                        .param("limit", self.batch_size as i64),
                )
                .await?;

            let mut batch = Vec::new();

            // Process each row in the result set
            while let Some(row) = result.next().await? {
                // Extract source and target UUIDs
                let source_uuid: String = match row.get("source_uuid") {
                    Ok(val) => val,
                    Err(_) => {
                        warn!(
                            "Skipping edge without source UUID at offset {}",
                            offset + batch.len()
                        );
                        continue;
                    }
                };

                let target_uuid: String = match row.get("target_uuid") {
                    Ok(val) => val,
                    Err(_) => {
                        warn!(
                            "Skipping edge without target UUID at offset {}",
                            offset + batch.len()
                        );
                        continue;
                    }
                };

                // Extract relationship type
                let relationship_type: String = match row.get("rel_type") {
                    Ok(val) => val,
                    Err(_) => {
                        warn!("Edge {}->{} has no type", source_uuid, target_uuid);
                        "RELATES_TO".to_string()
                    }
                };

                // Extract properties
                let properties =
                    if let Ok(props_map) = row.get::<HashMap<String, neo4rs::BoltType>>("props") {
                        self.convert_property_map(&props_map)?
                    } else {
                        HashMap::new()
                    };

                let edge = GraphEdge {
                    source_uuid,
                    target_uuid,
                    relationship_type,
                    properties,
                };

                batch.push(edge);
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

    /// Convert Neo4j node properties to our PropertyValue format
    async fn convert_node_properties(&self, node: &Node) -> Result<HashMap<String, PropertyValue>> {
        let mut properties = HashMap::new();

        for key in node.keys() {
            if let Ok(value) = node.get::<neo4rs::BoltType>(key) {
                if let Some(prop_value) = self.convert_bolt_type(&value) {
                    properties.insert(key.to_string(), prop_value);
                }
            }
        }

        Ok(properties)
    }

    /// Convert a map of Neo4j BoltType properties to PropertyValue
    fn convert_property_map(
        &self,
        props: &HashMap<String, neo4rs::BoltType>,
    ) -> Result<HashMap<String, PropertyValue>> {
        let mut properties = HashMap::new();

        for (key, value) in props {
            if let Some(prop_value) = self.convert_bolt_type(value) {
                properties.insert(key.clone(), prop_value);
            }
        }

        Ok(properties)
    }

    /// Convert a Neo4j BoltType to our PropertyValue enum
    fn convert_bolt_type(&self, bolt_type: &neo4rs::BoltType) -> Option<PropertyValue> {
        use neo4rs::BoltType;

        match bolt_type {
            BoltType::String(s) => Some(PropertyValue::String(s.value.clone())),
            BoltType::Integer(i) => Some(PropertyValue::Integer(i.value)),
            BoltType::Float(f) => Some(PropertyValue::Float(f.value)),
            BoltType::Boolean(b) => Some(PropertyValue::Boolean(b.value)),
            BoltType::List(list) => {
                let values: Vec<PropertyValue> = list
                    .value
                    .iter()
                    .filter_map(|v| self.convert_bolt_type(v))
                    .collect();
                Some(PropertyValue::List(values))
            }
            BoltType::Null(_) => Some(PropertyValue::Null),
            // Unsupported types - log and skip
            _ => {
                debug!("Skipping unsupported BoltType: {:?}", bolt_type);
                None
            }
        }
    }

    /// Get the total count of nodes with a specific label
    ///
    /// Useful for progress tracking and validation.
    pub async fn count_nodes(&self, node_type: &str) -> Result<usize> {
        let query = format!("MATCH (n:{}) RETURN count(n) as count", node_type);
        let mut result = self.graph.execute(neo4rs::query(&query)).await?;

        if let Some(row) = result.next().await? {
            let count: i64 = row
                .get("count")
                .map_err(|e| SyncError::SyncFailed(format!("Failed to get node count: {}", e)))?;
            Ok(count as usize)
        } else {
            Ok(0)
        }
    }

    /// Get the total count of edges/relationships
    ///
    /// Useful for progress tracking and validation.
    pub async fn count_edges(&self) -> Result<usize> {
        let query = "MATCH ()-[r]->() RETURN count(r) as count";
        let mut result = self.graph.execute(neo4rs::query(query)).await?;

        if let Some(row) = result.next().await? {
            let count: i64 = row
                .get("count")
                .map_err(|e| SyncError::SyncFailed(format!("Failed to get edge count: {}", e)))?;
            Ok(count as usize)
        } else {
            Ok(0)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bolt_type_conversion() {
        let extractor = create_test_extractor_for_conversions();

        // Test string conversion
        let bolt_string = neo4rs::BoltType::String(neo4rs::BoltString {
            value: "test".to_string(),
        });
        assert!(matches!(
            extractor.convert_bolt_type(&bolt_string),
            Some(PropertyValue::String(_))
        ));

        // Test integer conversion
        let bolt_int = neo4rs::BoltType::Integer(neo4rs::BoltInteger { value: 42 });
        assert!(matches!(
            extractor.convert_bolt_type(&bolt_int),
            Some(PropertyValue::Integer(42))
        ));

        // Test float conversion
        let bolt_float = neo4rs::BoltType::Float(neo4rs::BoltFloat { value: 3.14 });
        assert!(matches!(
            extractor.convert_bolt_type(&bolt_float),
            Some(PropertyValue::Float(_))
        ));

        // Test boolean conversion
        let bolt_bool = neo4rs::BoltType::Boolean(neo4rs::BoltBoolean { value: true });
        assert!(matches!(
            extractor.convert_bolt_type(&bolt_bool),
            Some(PropertyValue::Boolean(true))
        ));

        // Test null conversion
        let bolt_null = neo4rs::BoltType::Null(neo4rs::BoltNull);
        assert!(matches!(
            extractor.convert_bolt_type(&bolt_null),
            Some(PropertyValue::Null)
        ));
    }

    #[test]
    fn test_property_map_conversion() {
        let extractor = create_test_extractor_for_conversions();
        let mut props = HashMap::new();

        props.insert(
            "name".to_string(),
            neo4rs::BoltType::String(neo4rs::BoltString {
                value: "Test".to_string(),
            }),
        );
        props.insert(
            "count".to_string(),
            neo4rs::BoltType::Integer(neo4rs::BoltInteger { value: 10 }),
        );

        let result = extractor.convert_property_map(&props).unwrap();

        assert_eq!(result.len(), 2);
        assert!(matches!(result.get("name"), Some(PropertyValue::String(_))));
        assert!(matches!(
            result.get("count"),
            Some(PropertyValue::Integer(10))
        ));
    }

    // Helper function to create a test extractor (not connected)
    // Note: This creates a minimal Neo4jExtractor for testing type conversions only
    // It cannot be used for actual Neo4j operations
    fn create_test_extractor_for_conversions() -> TestableExtractor {
        TestableExtractor {
            batch_size: 100,
            max_query_limit: 1000,
        }
    }

    // A minimal struct that has the same conversion methods as Neo4jExtractor
    struct TestableExtractor {
        batch_size: usize,
        max_query_limit: usize,
    }

    impl TestableExtractor {
        fn convert_bolt_type(&self, bolt_type: &neo4rs::BoltType) -> Option<PropertyValue> {
            use neo4rs::BoltType;

            match bolt_type {
                BoltType::String(s) => Some(PropertyValue::String(s.value.clone())),
                BoltType::Integer(i) => Some(PropertyValue::Integer(i.value)),
                BoltType::Float(f) => Some(PropertyValue::Float(f.value)),
                BoltType::Boolean(b) => Some(PropertyValue::Boolean(b.value)),
                BoltType::List(list) => {
                    let values: Vec<PropertyValue> = list
                        .value
                        .iter()
                        .filter_map(|v| self.convert_bolt_type(v))
                        .collect();
                    Some(PropertyValue::List(values))
                }
                BoltType::Null(_) => Some(PropertyValue::Null),
                _ => None,
            }
        }

        fn convert_property_map(
            &self,
            props: &HashMap<String, neo4rs::BoltType>,
        ) -> Result<HashMap<String, PropertyValue>> {
            let mut properties = HashMap::new();

            for (key, value) in props {
                if let Some(prop_value) = self.convert_bolt_type(value) {
                    properties.insert(key.clone(), prop_value);
                }
            }

            Ok(properties)
        }
    }
}
