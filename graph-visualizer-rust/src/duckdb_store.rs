use anyhow::Result;
use arrow::array::{ArrayRef, Float64Array, RecordBatch, StringArray, UInt32Array};
use arrow::datatypes::{DataType, Field, Schema};
use arrow_schema::SchemaRef;
use chrono::{DateTime, Utc};
use duckdb::{params, Connection, Appender};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::{Mutex, RwLock};
use tracing::{debug, info, warn};

use crate::{Edge, Node};

#[derive(Clone)]
pub struct DuckDBStore {
    conn: Arc<Mutex<Connection>>,
    schema_nodes: SchemaRef,
    schema_edges: SchemaRef,
    update_queue: Arc<RwLock<UpdateQueue>>,
}

#[derive(Debug, Clone)]
struct PendingEdge {
    edge: Edge,
    retry_count: u32,
    first_seen: chrono::DateTime<Utc>,
    last_retry: chrono::DateTime<Utc>,
}

#[derive(Default)]
struct UpdateQueue {
    nodes_to_add: Vec<Node>,
    edges_to_add: Vec<Edge>,
    nodes_to_update: HashMap<String, Node>,
    pending_edges: Vec<PendingEdge>,
    // GRAPH-506: Add deletion queues for proper synchronization
    nodes_to_delete: Vec<String>, // Store node IDs to delete
    edges_to_delete: Vec<(String, String)>, // Store (source, target) pairs to delete
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct GraphUpdate {
    pub operation: UpdateOperation,
    pub nodes: Option<Vec<Node>>,
    pub edges: Option<Vec<Edge>>,
    // GRAPH-506: Add fields to track deleted entities
    pub deleted_nodes: Option<Vec<String>>, // IDs of deleted nodes
    pub deleted_edges: Option<Vec<(String, String)>>, // (source, target) pairs of deleted edges
    pub timestamp: u64,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum UpdateOperation {
    AddNodes,
    AddEdges,
    UpdateNodes,
    DeleteNodes,
    DeleteEdges,
}

impl DuckDBStore {
    /// Centralized date normalization to prevent synthetic timestamps
    /// Returns (created_at_string, timestamp_f64) tuple
    fn normalize_created_at(node: &Node) -> (String, f64) {
        if let Some(created_str) = node.properties.get("created_at").and_then(|v| v.as_str()) {
            // Parse existing timestamp
            match DateTime::parse_from_rfc3339(created_str) {
                Ok(dt) => {
                    let timestamp = dt.timestamp_millis() as f64;
                    (created_str.to_string(), timestamp)
                }
                Err(e) => {
                    warn!("Failed to parse created_at '{}': {}, using current time", created_str, e);
                    let now = Utc::now();
                    (now.to_rfc3339(), now.timestamp_millis() as f64)
                }
            }
        } else {
            // Missing created_at - use current time instead of synthetic 1979 timestamps
            debug!("Node {} missing created_at, using current time instead of synthetic timestamp", node.id);
            let now = Utc::now();
            (now.to_rfc3339(), now.timestamp_millis() as f64)
        }
    }

    pub fn new() -> Result<Self> {
        Self::new_with_path(None)
    }

    pub fn new_with_path(path: Option<&str>) -> Result<Self> {
        let conn = if let Some(db_path) = path {
            // Create parent directory if it doesn't exist
            if let Some(parent) = std::path::Path::new(db_path).parent() {
                std::fs::create_dir_all(parent)?;
            }
            info!("Opening persistent DuckDB at: {}", db_path);
            Connection::open(db_path)?
        } else {
            info!("Opening in-memory DuckDB");
            Connection::open_in_memory()?
        };

        // Create node schema for Arrow
        let schema_nodes = Arc::new(Schema::new(vec![
            Field::new("id", DataType::Utf8, false),
            Field::new("idx", DataType::UInt32, false), // Required by Cosmograph v2
            Field::new("label", DataType::Utf8, false),
            Field::new("node_type", DataType::Utf8, false),
            Field::new("summary", DataType::Utf8, true),
            Field::new("degree_centrality", DataType::Float64, true),
            Field::new("pagerank_centrality", DataType::Float64, true),
            Field::new("betweenness_centrality", DataType::Float64, true),
            Field::new("eigenvector_centrality", DataType::Float64, true),
            Field::new("x", DataType::Float64, true),
            Field::new("y", DataType::Float64, true),
            Field::new("color", DataType::Utf8, true),
            Field::new("size", DataType::Float64, true),
            Field::new("created_at", DataType::Utf8, true),           // ISO string
            Field::new("created_at_timestamp", DataType::Float64, true), // For timeline
            Field::new("cluster", DataType::Utf8, true), // For clustering
            Field::new("clusterStrength", DataType::Float64, true), // Clustering strength
        ]));
        
        // Create edge schema for Arrow
        let schema_edges = Arc::new(Schema::new(vec![
            Field::new("source", DataType::Utf8, false),
            Field::new("sourceidx", DataType::UInt32, false), // Required by Cosmograph v2
            Field::new("target", DataType::Utf8, false),
            Field::new("targetidx", DataType::UInt32, false), // Required by Cosmograph v2
            Field::new("edge_type", DataType::Utf8, false),
            Field::new("weight", DataType::Float64, false),
            Field::new("color", DataType::Utf8, true),
            Field::new("strength", DataType::Float64, true), // Link strength for Cosmograph
        ]));
        
        // Create tables
        conn.execute(
            "CREATE TABLE IF NOT EXISTS nodes (
                id VARCHAR PRIMARY KEY,
                idx INTEGER NOT NULL,
                label VARCHAR NOT NULL,
                node_type VARCHAR NOT NULL,
                summary VARCHAR,
                degree_centrality DOUBLE,
                pagerank_centrality DOUBLE,
                betweenness_centrality DOUBLE,
                eigenvector_centrality DOUBLE,
                x DOUBLE,
                y DOUBLE,
                color VARCHAR,
                size DOUBLE,
                created_at VARCHAR,              -- ISO string
                created_at_timestamp DOUBLE,     -- milliseconds since epoch
                cluster VARCHAR,
                clusterStrength DOUBLE
            )",
            params![],
        )?;

        conn.execute(
            "CREATE TABLE IF NOT EXISTS edges (
                source VARCHAR NOT NULL,
                sourceidx INTEGER NOT NULL,
                target VARCHAR NOT NULL,
                targetidx INTEGER NOT NULL,
                edge_type VARCHAR NOT NULL,
                weight DOUBLE NOT NULL DEFAULT 1.0,
                color VARCHAR,
                strength DOUBLE DEFAULT 1.0,
                PRIMARY KEY (source, target, edge_type)
            )",
            params![]
        )?;
        
        // Migration: Try to add created_at column if it doesn't exist (for existing databases)
        // This is a best-effort migration - if it fails, we assume the column already exists
        let _ = conn.execute("ALTER TABLE nodes ADD COLUMN created_at VARCHAR", params![]);
        
        // Create indexes for performance
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type)", params![])?;
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_idx ON nodes(idx)", params![])?;
        conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(sourceidx)", params![])?;
        conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(targetidx)", params![])?;

        // Create metadata table for cache invalidation
        conn.execute(
            "CREATE TABLE IF NOT EXISTS metadata (
                key VARCHAR PRIMARY KEY,
                value VARCHAR NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )",
            params![]
        )?;

        if path.is_some() {
            info!("DuckDB store initialized with persistent database");
        } else {
            info!("DuckDB store initialized with in-memory database");
        }
        
        Ok(Self {
            conn: Arc::new(Mutex::new(conn)),
            schema_nodes,
            schema_edges,
            update_queue: Arc::new(RwLock::new(UpdateQueue::default())),
        })
    }
    
    /// Compute a simple checksum of the graph data for cache invalidation
    fn compute_data_checksum(nodes: &[Node], edges: &[Edge]) -> String {
        use sha2::{Sha256, Digest};
        let mut hasher = Sha256::new();

        // Hash node count and edge count
        hasher.update(nodes.len().to_le_bytes());
        hasher.update(edges.len().to_le_bytes());

        // Hash first and last few node IDs for quick verification
        let sample_size = 10.min(nodes.len());
        for node in nodes.iter().take(sample_size) {
            hasher.update(node.id.as_bytes());
        }
        for node in nodes.iter().rev().take(sample_size) {
            hasher.update(node.id.as_bytes());
        }

        format!("{:x}", hasher.finalize())
    }

    /// Check if cached data is still valid by comparing checksums
    pub async fn is_cache_valid(&self, nodes: &[Node], edges: &[Edge]) -> bool {
        let conn = self.conn.lock().await;

        // Get stored checksum
        let stored_checksum: Option<String> = conn.query_row(
            "SELECT value FROM metadata WHERE key = 'data_checksum'",
            params![],
            |row| row.get(0)
        ).ok();

        if let Some(stored) = stored_checksum {
            let current = Self::compute_data_checksum(nodes, edges);
            let valid = stored == current;
            if !valid {
                warn!("Cache invalid: checksum mismatch (stored: {}, current: {})",
                      &stored[..8], &current[..8]);
            } else {
                info!("Cache valid: checksum match");
            }
            valid
        } else {
            info!("No stored checksum found, cache considered invalid");
            false
        }
    }

    pub async fn load_initial_data(&self, nodes: Vec<Node>, edges: Vec<Edge>) -> Result<()> {
        info!("Loading initial data: {} nodes, {} edges (using batch inserts)", nodes.len(), edges.len());
        let start_time = std::time::Instant::now();

        // Compute checksum before loading
        let checksum = Self::compute_data_checksum(&nodes, &edges);

        let mut conn = self.conn.lock().await;
        
        // GRAPH-504: Implement Atomic TRUNCATE+Reload Strategy
        // Clear existing data to ensure deleted nodes/edges are properly removed
        info!("Clearing existing data for atomic reload (deletion handling)");
        conn.execute("DELETE FROM edges", [])?; // Delete edges first due to foreign key constraints
        conn.execute("DELETE FROM nodes", [])?;
        info!("Existing data cleared, proceeding with fresh data load");
        
        let mut node_to_idx = HashMap::new();
        
        // Sort nodes by UUID for deterministic index assignment
        // This ensures the same UUID always gets the same index across reloads
        let mut sorted_nodes = nodes.clone();
        sorted_nodes.sort_by(|a, b| a.id.cmp(&b.id));
        
        // Build node_to_idx map first
        for (idx, node) in sorted_nodes.iter().enumerate() {
            node_to_idx.insert(node.id.clone(), idx as u32);
        }
        
        // BATCH INSERT NODES using Appender for ~10-50x speedup
        {
            let mut appender = conn.appender("nodes")?;
            
            for (idx, node) in sorted_nodes.iter().enumerate() {
                let degree = node.properties.get("degree_centrality")
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0);
                
                let pagerank = node.properties.get("pagerank_centrality")
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0);
                
                let betweenness = node.properties.get("betweenness_centrality")
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0);
                
                let eigenvector = node.properties.get("eigenvector_centrality")
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0);
                
                let color = self.get_node_color(&node.node_type);
                let size = 4.0 + (degree * 20.0); // Size based on centrality
                
                // Default clustering by node_type with strength 0.7
                let cluster = node.node_type.clone();
                let cluster_strength = 0.7;
                
                // Use centralized date normalization
                let (created_str, timestamp) = Self::normalize_created_at(&node);
                
                appender.append_row(params![
                    &node.id,
                    idx as i32,  // idx as INTEGER
                    &node.label,
                    &node.node_type,
                    &node.summary,
                    degree,
                    pagerank,
                    betweenness,
                    eigenvector,
                    Option::<f64>::None, // x - will be computed by layout
                    Option::<f64>::None, // y - will be computed by layout
                    color,
                    size,
                    &created_str,      // created_at string
                    timestamp,         // created_at_timestamp
                    cluster,
                    cluster_strength
                ])?;
            }
            
            appender.flush()?;
        }
        
        let nodes_elapsed = start_time.elapsed();
        info!("Inserted {} nodes in {:?}", sorted_nodes.len(), nodes_elapsed);
        
        // BATCH INSERT EDGES using Appender for ~10-50x speedup
        let mut edge_count = 0;
        {
            let mut appender = conn.appender("edges")?;
            
            for edge in edges.iter() {
                if let (Some(&source_idx), Some(&target_idx)) = 
                    (node_to_idx.get(&edge.from), node_to_idx.get(&edge.to)) {
                    
                    let color = self.get_edge_color(&edge.edge_type);
                    
                    // Calculate link strength based on edge type
                    let strength = match edge.edge_type.as_str() {
                        "entity_entity" | "relates_to" => 1.5,  // Stronger Entity-Entity connections
                        "episodic" | "temporal" | "mentioned_in" => 0.5,  // Weaker Episodic connections
                        _ => 1.0,  // Default strength
                    };
                    
                    appender.append_row(params![
                        &edge.from,
                        source_idx as i32,
                        &edge.to,
                        target_idx as i32,
                        &edge.edge_type,
                        edge.weight,
                        color,
                        strength
                    ])?;
                    
                    edge_count += 1;
                }
            }
            
            appender.flush()?;
        }
        
        // Store checksum for cache validation
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('data_checksum', ?)",
            params![&checksum]
        )?;

        let total_elapsed = start_time.elapsed();
        info!("Initial data loaded successfully: {} nodes, {} edges in {:?} (batch insert)", 
              sorted_nodes.len(), edge_count, total_elapsed);
        Ok(())
    }

    /// Incrementally update DuckDB with new/changed nodes and edges
    /// This method uses INSERT OR REPLACE to handle both new and updated nodes
    pub async fn update_incremental(&self, nodes: Vec<Node>, edges: Vec<Edge>) -> Result<()> {
        let conn = self.conn.lock().await;
        
        info!("Starting incremental update: {} nodes, {} edges", nodes.len(), edges.len());
        
        // Use INSERT OR REPLACE to handle both new and updated nodes
        let stmt_node = "INSERT OR REPLACE INTO nodes (id, idx, label, node_type, summary, degree_centrality, pagerank_centrality, betweenness_centrality, eigenvector_centrality, x, y, color, size, created_at, created_at_timestamp, cluster, clusterStrength)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)";
        
        let mut updated_count = 0;
        for node in &nodes {
            let (created_str, timestamp) = Self::normalize_created_at(&node);
            
            let degree = node.properties.get("degree_centrality")
                .and_then(|v| v.as_f64())
                .unwrap_or(0.0);
            
            let pagerank = node.properties.get("pagerank_centrality")
                .and_then(|v| v.as_f64())
                .unwrap_or(0.0);
            
            let betweenness = node.properties.get("betweenness_centrality")
                .and_then(|v| v.as_f64())
                .unwrap_or(0.0);
            
            let eigenvector = node.properties.get("eigenvector_centrality")
                .and_then(|v| v.as_f64())
                .unwrap_or(0.0);
            
            conn.execute(
                stmt_node,
                params![
                    &node.id,
                    updated_count, // Temporary idx, will be recalculated
                    &node.label,
                    &node.node_type,
                    &node.summary,
                    degree,
                    pagerank,
                    betweenness,
                    eigenvector,
                    0.0, // x
                    0.0, // y
                    "#3b82f6", // default color
                    1.0, // default size
                    created_str,
                    timestamp,
                    None::<String>, // cluster
                    None::<f64>,    // clusterStrength
                ],
            )?;
            updated_count += 1;
        }
        
        // Recalculate indices to maintain proper ordering
        conn.execute("UPDATE nodes SET idx = (SELECT COUNT(*) FROM nodes n2 WHERE n2.rowid <= nodes.rowid) - 1", [])?;
        
        // Insert edges (use INSERT OR IGNORE to avoid duplicates)
        let stmt_edge = "INSERT OR IGNORE INTO edges (source, target, sourceidx, targetidx, edge_type, weight, strength)
                         VALUES (?, ?, (SELECT idx FROM nodes WHERE id = ?), (SELECT idx FROM nodes WHERE id = ?), ?, ?, ?)";
        
        let mut edge_count = 0;
        for edge in &edges {
            conn.execute(
                stmt_edge,
                params![
                    &edge.from,
                    &edge.to,
                    &edge.from,
                    &edge.to,
                    &edge.edge_type,
                    edge.weight,
                    edge.weight,
                ],
            )?;
            edge_count += 1;
        }
        
        info!("Incremental update complete: {} nodes, {} edges inserted/updated", updated_count, edge_count);
        
        Ok(())
    }

    pub async fn get_nodes_as_arrow(&self) -> Result<RecordBatch> {
        let conn = self.conn.lock().await;
        
        let mut stmt = conn.prepare(
            "SELECT id, idx, label, node_type, summary, degree_centrality, pagerank_centrality, betweenness_centrality, eigenvector_centrality, x, y, color, size, created_at, created_at_timestamp, cluster, clusterStrength 
             FROM nodes 
             ORDER BY idx"
        )?;
        
        let mut ids = Vec::new();
        let mut indices = Vec::new();
        let mut labels = Vec::new();
        let mut node_types = Vec::new();
        let mut summaries = Vec::new();
        let mut degrees = Vec::new();
        let mut pageranks = Vec::new();
        let mut betweennesses = Vec::new();
        let mut eigenvectors = Vec::new();
        let mut xs = Vec::new();
        let mut ys = Vec::new();
        let mut colors = Vec::new();
        let mut sizes = Vec::new();
        let mut created_ats = Vec::new();     // ISO string dates
        let mut timestamps = Vec::new();      // Numeric timestamps
        let mut clusters = Vec::new();
        let mut cluster_strengths = Vec::new();
        
        let rows = stmt.query_map(params![], |row| {
            Ok((
                row.get::<_, String>(0)?,     // id
                row.get::<_, u32>(1)?,        // idx
                row.get::<_, String>(2)?,     // label
                row.get::<_, String>(3)?,     // node_type
                row.get::<_, Option<String>>(4)?, // summary
                row.get::<_, Option<f64>>(5)?,    // degree_centrality
                row.get::<_, Option<f64>>(6)?,    // pagerank_centrality
                row.get::<_, Option<f64>>(7)?,    // betweenness_centrality
                row.get::<_, Option<f64>>(8)?,    // eigenvector_centrality
                row.get::<_, Option<f64>>(9)?,    // x
                row.get::<_, Option<f64>>(10)?,   // y
                row.get::<_, Option<String>>(11)?, // color
                row.get::<_, Option<f64>>(12)?,   // size
                row.get::<_, Option<String>>(13)?, // created_at
                row.get::<_, Option<f64>>(14)?,   // created_at_timestamp
                row.get::<_, Option<String>>(15)?, // cluster
                row.get::<_, Option<f64>>(16)?,   // clusterStrength
            ))
        })?;
        
        for row in rows {
            let (id, idx, label, node_type, summary, degree, pagerank, betweenness, eigenvector, x, y, color, size, created_at, timestamp, cluster, cluster_strength) = row?;
            ids.push(id);
            indices.push(idx);
            labels.push(label);
            node_types.push(node_type);
            summaries.push(summary);
            degrees.push(degree);
            pageranks.push(pagerank);
            betweennesses.push(betweenness);
            eigenvectors.push(eigenvector);
            xs.push(x);
            ys.push(y);
            colors.push(color);
            sizes.push(size);
            created_ats.push(created_at);
            timestamps.push(timestamp);
            clusters.push(cluster);
            cluster_strengths.push(cluster_strength);
        }
        
        let batch = RecordBatch::try_new(
            self.schema_nodes.clone(),
            vec![
                Arc::new(StringArray::from(ids)) as ArrayRef,
                Arc::new(UInt32Array::from(indices)) as ArrayRef,
                Arc::new(StringArray::from(labels)) as ArrayRef,
                Arc::new(StringArray::from(node_types)) as ArrayRef,
                Arc::new(StringArray::from(summaries)) as ArrayRef,
                Arc::new(Float64Array::from(degrees)) as ArrayRef,
                Arc::new(Float64Array::from(pageranks)) as ArrayRef,
                Arc::new(Float64Array::from(betweennesses)) as ArrayRef,
                Arc::new(Float64Array::from(eigenvectors)) as ArrayRef,
                Arc::new(Float64Array::from(xs)) as ArrayRef,
                Arc::new(Float64Array::from(ys)) as ArrayRef,
                Arc::new(StringArray::from(colors)) as ArrayRef,
                Arc::new(Float64Array::from(sizes)) as ArrayRef,
                Arc::new(StringArray::from(created_ats)) as ArrayRef,    // created_at strings
                Arc::new(Float64Array::from(timestamps)) as ArrayRef,     // created_at_timestamp
                Arc::new(StringArray::from(clusters)) as ArrayRef,
                Arc::new(Float64Array::from(cluster_strengths)) as ArrayRef,
            ],
        )?;
        
        Ok(batch)
    }
    
    pub async fn get_edges_as_arrow(&self) -> Result<RecordBatch> {
        let conn = self.conn.lock().await;
        
        // First, get the actual nodes to build an ID to index mapping
        let mut node_stmt = conn.prepare("SELECT id, idx FROM nodes ORDER BY idx")?;
        let node_rows = node_stmt.query_map(params![], |row| {
            Ok((
                row.get::<_, String>(0)?,  // id
                row.get::<_, u32>(1)?,     // idx
            ))
        })?;
        
        // Build a map from node ID to its actual index in the current node array
        let mut node_id_to_index = std::collections::HashMap::new();
        let mut current_index = 0u32;
        for row in node_rows {
            let (id, _) = row?;
            node_id_to_index.insert(id, current_index);
            current_index += 1;
        }
        
        // Now get edges and recalculate indices based on current node positions
        let mut stmt = conn.prepare(
            "SELECT e.source, e.target, e.edge_type, e.weight, e.color, e.strength 
             FROM edges e
             INNER JOIN nodes n1 ON e.source = n1.id
             INNER JOIN nodes n2 ON e.target = n2.id"
        )?;
        
        let mut sources = Vec::new();
        let mut source_indices = Vec::new();
        let mut targets = Vec::new();
        let mut target_indices = Vec::new();
        let mut edge_types = Vec::new();
        let mut weights = Vec::new();
        let mut colors = Vec::new();
        let mut strengths = Vec::new();
        
        let rows = stmt.query_map(params![], |row| {
            Ok((
                row.get::<_, String>(0)?,     // source
                row.get::<_, String>(1)?,     // target
                row.get::<_, String>(2)?,     // edge_type
                row.get::<_, f64>(3)?,        // weight
                row.get::<_, Option<String>>(4)?, // color
                row.get::<_, Option<f64>>(5)?, // strength
            ))
        })?;
        
        for row in rows {
            let (source, target, edge_type, weight, color, strength) = row?;
            
            // Look up the actual indices based on current node positions
            if let (Some(&source_idx), Some(&target_idx)) = 
                (node_id_to_index.get(&source), node_id_to_index.get(&target)) {
                sources.push(source);
                source_indices.push(source_idx);
                targets.push(target);
                target_indices.push(target_idx);
                edge_types.push(edge_type);
                weights.push(weight);
                colors.push(color);
                strengths.push(strength.unwrap_or(1.0));
            }
        }
        
        let batch = RecordBatch::try_new(
            self.schema_edges.clone(),
            vec![
                Arc::new(StringArray::from(sources)) as ArrayRef,
                Arc::new(UInt32Array::from(source_indices)) as ArrayRef,
                Arc::new(StringArray::from(targets)) as ArrayRef,
                Arc::new(UInt32Array::from(target_indices)) as ArrayRef,
                Arc::new(StringArray::from(edge_types)) as ArrayRef,
                Arc::new(Float64Array::from(weights)) as ArrayRef,
                Arc::new(StringArray::from(colors)) as ArrayRef,
                Arc::new(Float64Array::from(strengths)) as ArrayRef,
            ],
        )?;
        
        Ok(batch)
    }
    
    pub async fn queue_node_update(&self, node: Node) {
        let mut queue = self.update_queue.write().await;
        queue.nodes_to_update.insert(node.id.clone(), node);
    }
    
    pub async fn queue_nodes(&self, nodes: Vec<Node>) {
        let mut queue = self.update_queue.write().await;
        queue.nodes_to_add.extend(nodes);
    }
    
    pub async fn queue_edges(&self, edges: Vec<Edge>) {
        let mut queue = self.update_queue.write().await;
        queue.edges_to_add.extend(edges);
    }
    
    // GRAPH-506: Add deletion operation queueing methods
    pub async fn queue_node_deletions(&self, node_ids: Vec<String>) {
        let mut queue = self.update_queue.write().await;
        queue.nodes_to_delete.extend(node_ids);
    }
    
    pub async fn queue_edge_deletions(&self, edge_pairs: Vec<(String, String)>) {
        let mut queue = self.update_queue.write().await;
        queue.edges_to_delete.extend(edge_pairs);
    }
    
    pub async fn process_updates(&self) -> Result<Option<GraphUpdate>> {
        let mut queue = self.update_queue.write().await;
        
        // GRAPH-506: Include deletion queues in empty check
        if queue.nodes_to_add.is_empty() && 
           queue.edges_to_add.is_empty() && 
           queue.nodes_to_update.is_empty() &&
           queue.pending_edges.is_empty() &&
           queue.nodes_to_delete.is_empty() &&
           queue.edges_to_delete.is_empty() {
            return Ok(None);
        }
        
        let mut conn = self.conn.lock().await;
        let tx = conn.transaction()?;
        
        let mut update = GraphUpdate {
            operation: UpdateOperation::AddNodes,
            nodes: None,
            edges: None,
            // GRAPH-506: Initialize new deletion tracking fields
            deleted_nodes: None,
            deleted_edges: None,
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_millis() as u64,
        };
        
        // Process new nodes
        if !queue.nodes_to_add.is_empty() {
            debug!("Processing {} new nodes", queue.nodes_to_add.len());
            
            // Get current max index
            let max_idx: i32 = tx.query_row(
                "SELECT COALESCE(MAX(idx), -1) FROM nodes",
                params![],
                |row| row.get(0)
            )?;
            
            let mut start_idx = (max_idx + 1).max(0) as u32;
            let mut new_nodes = queue.nodes_to_add.drain(..).collect::<Vec<_>>();
            
            // Sort new nodes by UUID for consistent index assignment
            new_nodes.sort_by(|a, b| a.id.cmp(&b.id));
            
            for node in &new_nodes {
                let degree = node.properties.get("degree_centrality")
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0);
                
                let pagerank = node.properties.get("pagerank_centrality")
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0);
                
                let betweenness = node.properties.get("betweenness_centrality")
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0);
                
                let eigenvector = node.properties.get("eigenvector_centrality")
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0);
                
                let color = self.get_node_color(&node.node_type);
                let size = 4.0 + (degree * 20.0);
                
                // Default clustering by node_type with strength 0.7
                let cluster = node.node_type.clone();
                let cluster_strength = 0.7;
                
                // Use centralized date normalization
                let (created_str, timestamp) = Self::normalize_created_at(&node);

                tx.execute(
                    "INSERT OR REPLACE INTO nodes (id, idx, label, node_type, summary, degree_centrality, pagerank_centrality, betweenness_centrality, eigenvector_centrality, x, y, color, size, created_at, created_at_timestamp, cluster, clusterStrength) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    params![
                        &node.id,
                        start_idx,
                        &node.label,
                        &node.node_type,
                        &node.summary,
                        degree,
                        pagerank,
                        betweenness,
                        eigenvector,
                        Option::<f64>::None,
                        Option::<f64>::None,
                        color,
                        size,
                        &created_str,     // created_at string
                        timestamp,        // created_at_timestamp
                        cluster,
                        cluster_strength
                    ],
                )?;
                
                start_idx += 1;
            }
            
            update.operation = UpdateOperation::AddNodes;
            update.nodes = Some(new_nodes);
        }
        
        // Process node updates
        if !queue.nodes_to_update.is_empty() {
            debug!("Processing {} node updates", queue.nodes_to_update.len());
            
            let updates = queue.nodes_to_update.drain().collect::<Vec<_>>();
            
            for (_, node) in &updates {
                tx.execute(
                    "UPDATE nodes SET label = ?, summary = ? WHERE id = ?",
                    params![&node.label, &node.summary, &node.id],
                )?;
            }
            
            if update.nodes.is_none() {
                update.operation = UpdateOperation::UpdateNodes;
                update.nodes = Some(updates.into_iter().map(|(_, n)| n).collect());
            }
        }
        
        // Process new edges with validation
        let mut validated_edges = Vec::new();
        let now = Utc::now();
        
        if !queue.edges_to_add.is_empty() {
            debug!("Processing {} new edges", queue.edges_to_add.len());
            
            let new_edges = queue.edges_to_add.drain(..).collect::<Vec<_>>();
            
            for edge in new_edges {
                // Get indices for source and target
                let source_idx: Option<u32> = tx.query_row(
                    "SELECT idx FROM nodes WHERE id = ?",
                    params![&edge.from],
                    |row| row.get(0)
                ).ok();
                
                let target_idx: Option<u32> = tx.query_row(
                    "SELECT idx FROM nodes WHERE id = ?",
                    params![&edge.to],
                    |row| row.get(0)
                ).ok();
                
                if let (Some(src_idx), Some(tgt_idx)) = (source_idx, target_idx) {
                    let color = self.get_edge_color(&edge.edge_type);
                    
                    // Calculate link strength based on edge type
                    let strength = match edge.edge_type.as_str() {
                        "entity_entity" | "relates_to" => 1.5,  // Stronger Entity-Entity connections
                        "episodic" | "temporal" | "mentioned_in" => 0.5,  // Weaker Episodic connections
                        _ => 1.0,  // Default strength
                    };
                    
                    tx.execute(
                        "INSERT OR IGNORE INTO edges (source, sourceidx, target, targetidx, edge_type, weight, color, strength)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        params![
                            &edge.from,
                            src_idx,
                            &edge.to,
                            tgt_idx,
                            &edge.edge_type,
                            edge.weight,
                            color,
                            strength
                        ],
                    )?;
                    
                    validated_edges.push(edge.clone());
                } else {
                    // Buffer edge for later retry
                    warn!("Edge references unknown nodes, buffering: {} -> {} (source_idx: {:?}, target_idx: {:?})",
                          edge.from, edge.to, source_idx, target_idx);
                    queue.pending_edges.push(PendingEdge {
                        edge: edge.clone(),
                        retry_count: 0,
                        first_seen: now,
                        last_retry: now,
                    });
                }
            }
        }
        
        // Process pending edges (retry buffered edges)
        if !queue.pending_edges.is_empty() {
            debug!("Processing {} pending edges", queue.pending_edges.len());
            
            let mut still_pending = Vec::new();
            let max_retries = 10;
            let stale_threshold = chrono::Duration::minutes(5);
            
            for mut pending in queue.pending_edges.drain(..) {
                // Check if edge is too old
                if now.signed_duration_since(pending.first_seen) > stale_threshold {
                    warn!("Dropping stale pending edge after 5 minutes: {} -> {}", 
                          pending.edge.from, pending.edge.to);
                    continue;
                }
                
                // Check if max retries exceeded
                if pending.retry_count >= max_retries {
                    warn!("Dropping pending edge after {} retries: {} -> {}", 
                          max_retries, pending.edge.from, pending.edge.to);
                    continue;
                }
                
                // Try to process the edge again
                let source_idx: Option<u32> = tx.query_row(
                    "SELECT idx FROM nodes WHERE id = ?",
                    params![&pending.edge.from],
                    |row| row.get(0)
                ).ok();
                
                let target_idx: Option<u32> = tx.query_row(
                    "SELECT idx FROM nodes WHERE id = ?",
                    params![&pending.edge.to],
                    |row| row.get(0)
                ).ok();
                
                if let (Some(src_idx), Some(tgt_idx)) = (source_idx, target_idx) {
                    let color = self.get_edge_color(&pending.edge.edge_type);
                    
                    // Calculate link strength based on edge type
                    let strength = match pending.edge.edge_type.as_str() {
                        "entity_entity" | "relates_to" => 1.5,  // Stronger Entity-Entity connections
                        "episodic" | "temporal" | "mentioned_in" => 0.5,  // Weaker Episodic connections
                        _ => 1.0,  // Default strength
                    };
                    
                    tx.execute(
                        "INSERT OR IGNORE INTO edges (source, sourceidx, target, targetidx, edge_type, weight, color, strength)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        params![
                            &pending.edge.from,
                            src_idx,
                            &pending.edge.to,
                            tgt_idx,
                            &pending.edge.edge_type,
                            pending.edge.weight,
                            color,
                            strength
                        ],
                    )?;
                    
                    info!("Successfully resolved pending edge after {} retries: {} -> {}", 
                          pending.retry_count, pending.edge.from, pending.edge.to);
                    validated_edges.push(pending.edge);
                } else {
                    // Still missing nodes, keep in pending
                    pending.retry_count += 1;
                    pending.last_retry = now;
                    still_pending.push(pending);
                }
            }
            
            // Put still-pending edges back in queue
            queue.pending_edges = still_pending;
            
            if !queue.pending_edges.is_empty() {
                debug!("{} edges still pending", queue.pending_edges.len());
            }
        }
        
        // Only set edges in update if we have validated edges
        if !validated_edges.is_empty() {
            if update.nodes.is_none() {
                update.operation = UpdateOperation::AddEdges;
            }
            update.edges = Some(validated_edges);
        }
        
        // GRAPH-506: Process deletion operations
        let mut deleted_nodes = Vec::new();
        let mut deleted_edges = Vec::new();
        
        // Process node deletions (delete edges first due to foreign key constraints)
        if !queue.nodes_to_delete.is_empty() {
            let nodes_to_delete = queue.nodes_to_delete.drain(..).collect::<Vec<_>>();
            debug!("Processing {} node deletions", nodes_to_delete.len());
            
            for node_id in &nodes_to_delete {
                // First delete edges referencing this node
                let edge_delete_count = tx.execute(
                    "DELETE FROM edges WHERE source = ? OR target = ?",
                    params![node_id, node_id]
                )?;
                if edge_delete_count > 0 {
                    debug!("Deleted {} edges referencing node {}", edge_delete_count, node_id);
                }
                
                // Then delete the node itself
                let node_delete_count = tx.execute(
                    "DELETE FROM nodes WHERE id = ?",
                    params![node_id]
                )?;
                if node_delete_count > 0 {
                    debug!("Deleted node: {}", node_id);
                    deleted_nodes.push(node_id.clone());
                }
            }
            
            if !deleted_nodes.is_empty() {
                update.operation = UpdateOperation::DeleteNodes;
                update.deleted_nodes = Some(deleted_nodes.clone());
            }
        }
        
        // Process edge deletions
        if !queue.edges_to_delete.is_empty() {
            let edges_to_delete = queue.edges_to_delete.drain(..).collect::<Vec<_>>();
            debug!("Processing {} edge deletions", edges_to_delete.len());
            
            for (source, target) in &edges_to_delete {
                let delete_count = tx.execute(
                    "DELETE FROM edges WHERE source = ? AND target = ?",
                    params![source, target]
                )?;
                if delete_count > 0 {
                    debug!("Deleted edge: {} -> {}", source, target);
                    deleted_edges.push((source.clone(), target.clone()));
                }
            }
            
            if !deleted_edges.is_empty() && update.operation != UpdateOperation::DeleteNodes {
                update.operation = UpdateOperation::DeleteEdges;
            }
            if !deleted_edges.is_empty() {
                update.deleted_edges = Some(deleted_edges.clone());
            }
        }
        
        tx.commit()?;
        
        // GRAPH-506: Return None if update has no actual data (including deletions)
        if update.nodes.is_none() && update.edges.is_none() && 
           update.deleted_nodes.is_none() && update.deleted_edges.is_none() {
            return Ok(None);
        }
        
        Ok(Some(update))
    }
    
    pub async fn get_stats(&self) -> Result<(usize, usize)> {
        let conn = self.conn.lock().await;
        
        let node_count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM nodes",
            params![],
            |row| row.get(0)
        )?;
        
        let edge_count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM edges",
            params![],
            |row| row.get(0)
        )?;
        
        Ok((node_count as usize, edge_count as usize))
    }

    /// GRAPH-113: Get all node IDs from DuckDB for reconciliation
    ///
    /// Returns a HashSet of all node IDs currently stored in DuckDB.
    /// Used by the reconciliation task to compare with FalkorDB state.
    pub async fn get_all_node_ids(&self) -> Result<std::collections::HashSet<String>> {
        let conn = self.conn.lock().await;
        let mut stmt = conn.prepare("SELECT id FROM nodes")?;
        let ids: Vec<String> = stmt
            .query_map(params![], |row| row.get(0))?
            .filter_map(|r| r.ok())
            .collect();
        Ok(ids.into_iter().collect())
    }

    /// GRAPH-113: Get all edge IDs from DuckDB for reconciliation
    ///
    /// Returns a HashSet of edge identifiers (source_id + "->" + target_id).
    /// Used by the reconciliation task to compare with FalkorDB state.
    pub async fn get_all_edge_ids(&self) -> Result<std::collections::HashSet<String>> {
        let conn = self.conn.lock().await;
        let mut stmt = conn.prepare("SELECT source, target FROM edges")?;
        let ids: Vec<String> = stmt
            .query_map(params![], |row| {
                let source: String = row.get(0)?;
                let target: String = row.get(1)?;
                Ok(format!("{}->{}", source, target))
            })?
            .filter_map(|r| r.ok())
            .collect();
        Ok(ids.into_iter().collect())
    }

    /// GRAPH-113: Delete nodes by IDs (for reconciliation cleanup)
    ///
    /// Removes nodes that exist in DuckDB but not in FalkorDB.
    /// Also removes any edges connected to these nodes.
    pub async fn delete_nodes_by_ids(&self, ids: &[String]) -> Result<usize> {
        if ids.is_empty() {
            return Ok(0);
        }

        let conn = self.conn.lock().await;

        // Build placeholders for IN clause
        let placeholders: Vec<String> = ids.iter().enumerate()
            .map(|(i, _)| format!("${}", i + 1))
            .collect();
        let placeholders_str = placeholders.join(", ");

        // First delete edges connected to these nodes
        let edge_query = format!(
            "DELETE FROM edges WHERE source IN ({}) OR target IN ({})",
            placeholders_str, placeholders_str
        );
        // Double the params for source and target
        let mut edge_params: Vec<&dyn duckdb::ToSql> = Vec::new();
        for id in ids.iter() {
            edge_params.push(id);
        }
        for id in ids.iter() {
            edge_params.push(id);
        }
        conn.execute(&edge_query, edge_params.as_slice())?;

        // Then delete the nodes
        let node_query = format!(
            "DELETE FROM nodes WHERE id IN ({})",
            placeholders_str
        );
        let node_params: Vec<&dyn duckdb::ToSql> = ids.iter().map(|s| s as &dyn duckdb::ToSql).collect();
        let deleted = conn.execute(&node_query, node_params.as_slice())?;

        Ok(deleted)
    }

    /// GRAPH-113: Delete edges by source-target pairs (for reconciliation cleanup)
    ///
    /// Removes edges that exist in DuckDB but not in FalkorDB.
    pub async fn delete_edges_by_pairs(&self, pairs: &[(String, String)]) -> Result<usize> {
        if pairs.is_empty() {
            return Ok(0);
        }

        let conn = self.conn.lock().await;
        let mut deleted = 0;

        // Delete edges one by one (safer for large batches)
        for (source, target) in pairs {
            let result = conn.execute(
                "DELETE FROM edges WHERE source = $1 AND target = $2",
                params![source, target],
            )?;
            deleted += result;
        }

        Ok(deleted)
    }
    
    fn get_node_color(&self, node_type: &str) -> String {
        match node_type {
            "EntityNode" => "#4CAF50".to_string(),
            "EpisodicNode" => "#2196F3".to_string(),
            "GroupNode" => "#FF9800".to_string(),
            _ => "#9E9E9E".to_string(),
        }
    }
    
    fn get_edge_color(&self, edge_type: &str) -> String {
        match edge_type {
            "RELATES_TO" => "#666666".to_string(),
            "MENTIONS" => "#999999".to_string(),
            "HAS_MEMBER" => "#FF9800".to_string(),
            _ => "#CCCCCC".to_string(),
        }
    }
    
    pub async fn get_nodes_by_ids(&self, ids: &[String]) -> Result<Vec<Node>> {
        if ids.is_empty() {
            return Ok(vec![]);
        }
        
        let conn = self.conn.lock().await;
        
        // Build placeholders for IN clause
        let placeholders: Vec<String> = ids.iter().enumerate()
            .map(|(i, _)| format!("${}", i + 1))
            .collect();
        let query = format!(
            "SELECT * FROM nodes WHERE id IN ({}) ORDER BY idx",
            placeholders.join(", ")
        );
        
        let mut stmt = conn.prepare(&query)?;
        
        // Convert ids to params
        let params: Vec<&dyn duckdb::ToSql> = ids.iter()
            .map(|id| id as &dyn duckdb::ToSql)
            .collect();
        
        let node_iter = stmt.query_map(&params[..], |row| {
            let mut properties: HashMap<String, serde_json::Value> = HashMap::new();
            
            // Add all metadata to properties based on correct column indices
            properties.insert("idx".to_string(), serde_json::json!(row.get::<_, i32>(1)?));
            
            // Add centrality metrics
            if let Ok(degree) = row.get::<_, f64>(5) {
                properties.insert("degree_centrality".to_string(), serde_json::json!(degree));
            }
            if let Ok(pagerank) = row.get::<_, f64>(6) {
                properties.insert("pagerank_centrality".to_string(), serde_json::json!(pagerank));
            }
            if let Ok(betweenness) = row.get::<_, f64>(7) {
                properties.insert("betweenness_centrality".to_string(), serde_json::json!(betweenness));
            }
            if let Ok(eigenvector) = row.get::<_, f64>(8) {
                properties.insert("eigenvector_centrality".to_string(), serde_json::json!(eigenvector));
            }
            
            // Add visual properties
            if let Ok(color) = row.get::<_, String>(11) {
                properties.insert("color".to_string(), serde_json::json!(color));
            }
            if let Ok(size) = row.get::<_, f64>(12) {
                properties.insert("size".to_string(), serde_json::json!(size));
            }
            
            // Add created_at string and timestamp
            if let Ok(created_str) = row.get::<_, String>(13) {  // created_at column
                properties.insert("created_at".to_string(), serde_json::json!(created_str));
            }
            if let Ok(timestamp) = row.get::<_, f64>(14) {  // created_at_timestamp column
                properties.insert("created_at_timestamp".to_string(), serde_json::json!(timestamp));
                
                // If created_at string is missing, synthesize it from timestamp
                if !properties.contains_key("created_at") {
                    let datetime = DateTime::<Utc>::from_timestamp_millis(timestamp as i64)
                        .unwrap_or_else(|| Utc::now());
                    properties.insert("created_at".to_string(), serde_json::json!(datetime.to_rfc3339()));
                }
            }
            
            Ok(Node {
                id: row.get(0)?,
                label: row.get(2)?,
                node_type: row.get(3)?,
                summary: row.get(4).ok(),
                properties,
            })
        })?;
        
        let mut nodes = Vec::new();
        for node in node_iter {
            nodes.push(node?);
        }
        
        Ok(nodes)
    }
    
    pub async fn get_edges_by_pairs(&self, pairs: &[(String, String)]) -> Result<Vec<Edge>> {
        if pairs.is_empty() {
            return Ok(vec![]);
        }
        
        let conn = self.conn.lock().await;
        
        // Build WHERE clause for multiple source-target pairs
        let conditions: Vec<String> = pairs.iter().enumerate()
            .map(|(i, _)| format!("(source = ${} AND target = ${})", i * 2 + 1, i * 2 + 2))
            .collect();
        
        let query = format!(
            "SELECT * FROM edges WHERE {} ORDER BY sourceidx, targetidx",
            conditions.join(" OR ")
        );
        
        let mut stmt = conn.prepare(&query)?;
        
        // Flatten pairs into params
        let mut params: Vec<&dyn duckdb::ToSql> = Vec::new();
        for (source, target) in pairs {
            params.push(source as &dyn duckdb::ToSql);
            params.push(target as &dyn duckdb::ToSql);
        }
        
        let edge_iter = stmt.query_map(&params[..], |row| {
            Ok(Edge {
                from: row.get(0)?,
                to: row.get(2)?,
                edge_type: row.get(4)?,
                weight: row.get(5)?,
            })
        })?;
        
        let mut edges = Vec::new();
        for edge in edge_iter {
            edges.push(edge?);
        }
        
        Ok(edges)
    }
    
    pub async fn get_node_by_id(&self, id: &str) -> Result<Option<Node>> {
        let conn = self.conn.lock().await;
        
        // Query for a single node by ID with all properties including centrality
        let query = "SELECT * FROM nodes WHERE id = $1 LIMIT 1";
        
        let mut stmt = conn.prepare(query)?;
        let mut rows = stmt.query_map(&[&id], |row| {
            // Extract all properties including centrality metrics
            let mut properties = HashMap::new();
            
            // Add centrality metrics if they exist
            if let Ok(degree) = row.get::<_, f64>(5) {  // degree_centrality column
                properties.insert("degree_centrality".to_string(), serde_json::Value::from(degree));
            }
            if let Ok(betweenness) = row.get::<_, f64>(7) {  // betweenness_centrality column (was wrong index)
                properties.insert("betweenness_centrality".to_string(), serde_json::Value::from(betweenness));
            }
            if let Ok(pagerank) = row.get::<_, f64>(6) {  // pagerank_centrality column (was wrong index)
                properties.insert("pagerank_centrality".to_string(), serde_json::Value::from(pagerank));
            }
            if let Ok(eigenvector) = row.get::<_, f64>(8) {  // eigenvector_centrality column
                properties.insert("eigenvector_centrality".to_string(), serde_json::Value::from(eigenvector));
            }
            
            // Add created_at string and timestamp
            if let Ok(created_str) = row.get::<_, String>(13) {  // created_at column
                properties.insert("created_at".to_string(), serde_json::Value::from(created_str));
            }
            if let Ok(timestamp) = row.get::<_, f64>(14) {  // created_at_timestamp column
                properties.insert("created_at_timestamp".to_string(), serde_json::Value::from(timestamp));
                
                // If created_at string is missing, synthesize it from timestamp
                if !properties.contains_key("created_at") {
                    let datetime = DateTime::<Utc>::from_timestamp_millis(timestamp as i64)
                        .unwrap_or_else(|| Utc::now());
                    properties.insert("created_at".to_string(), serde_json::Value::from(datetime.to_rfc3339()));
                }
            }
            
            // Add other visual properties
            if let Ok(size) = row.get::<_, f64>(12) {  // size column
                properties.insert("size".to_string(), serde_json::Value::from(size));
            }
            if let Ok(color) = row.get::<_, String>(11) {  // color column
                properties.insert("color".to_string(), serde_json::Value::from(color));
            }
            
            Ok(Node {
                id: row.get(0)?,
                label: row.get(2)?,  // label is at index 2, not 1
                node_type: row.get(3)?,  // node_type is at index 3, not 2
                summary: row.get(4).ok(),  // summary is at index 4, not 3
                properties,
            })
        })?;
        
        if let Some(result) = rows.next() {
            Ok(Some(result?))
        } else {
            Ok(None)
        }
    }
}