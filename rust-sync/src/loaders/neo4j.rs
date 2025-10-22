use crate::config::settings::{Neo4jConfig, SyncConfig};
use crate::error::{Result, SyncError};
use crate::models::{GraphEdge, GraphNode, LoadingStats, PropertyValue};
use neo4rs::{query, BoltNull, BoltType, ConfigBuilder, Graph};
use std::collections::HashMap;
use std::future::Future;
use std::time::Instant;
use tokio::sync::mpsc;
use tokio::time::{sleep, Duration};
use tracing::{debug, error, info, warn};

/// Cache mapping node UUIDs to internal Neo4j node IDs
///
/// This optimization pre-loads all node IDs to avoid repeated UUID property lookups
/// during edge creation, providing 5-10x speedup for edge loading.
#[derive(Debug, Clone)]
pub struct NodeIdCache {
    /// Map from UUID string to internal Neo4j node ID
    cache: HashMap<String, i64>,
}

impl NodeIdCache {
    /// Create a new empty cache
    pub fn new() -> Self {
        Self {
            cache: HashMap::new(),
        }
    }

    /// Get internal node ID for a given UUID
    pub fn get(&self, uuid: &str) -> Option<i64> {
        self.cache.get(uuid).copied()
    }

    /// Insert a UUID → ID mapping
    pub fn insert(&mut self, uuid: String, id: i64) {
        self.cache.insert(uuid, id);
    }

    /// Get the number of cached node IDs
    pub fn len(&self) -> usize {
        self.cache.len()
    }

    /// Check if cache is empty
    pub fn is_empty(&self) -> bool {
        self.cache.is_empty()
    }
}

/// Neo4j loader that handles batch MERGE operations for nodes and edges
///
/// This loader receives data via tokio channels and performs batch writes
/// to Neo4j using Cypher UNWIND patterns for efficient bulk loading.
pub struct Neo4jLoader {
    graph: Graph,
    database: String,
    batch_size: usize,
    node_id_cache: Option<NodeIdCache>,
    retry_attempts: usize,
    retry_backoff_ms: u64,
}

impl Neo4jLoader {
    /// Create a new Neo4j loader with connection
    ///
    /// # Arguments
    /// * `neo4j_config` - Neo4j connection configuration
    /// * `sync_config` - Sync configuration including batch size
    ///
    /// # Errors
    /// Returns error if connection fails or database validation fails
    pub async fn new(neo4j_config: &Neo4jConfig, sync_config: &SyncConfig) -> Result<Self> {
        info!(
            "Connecting to Neo4j at {} with database '{}'",
            neo4j_config.uri, neo4j_config.database
        );

        let config = ConfigBuilder::default()
            .uri(&neo4j_config.uri)
            .user(&neo4j_config.user)
            .password(&neo4j_config.password)
            .db(neo4j_config.database.clone())
            .max_connections(neo4j_config.pool_size.max(1))
            .fetch_size(sync_config.batch_size.max(1))
            .build()?;

        let graph = Graph::connect(config)?;

        // Validate connection
        let use_db_query = if neo4j_config.database != "neo4j" {
            format!("USE {} RETURN 1 as test", neo4j_config.database)
        } else {
            "RETURN 1 as test".to_string()
        };

        let mut result = graph.execute(query(&use_db_query)).await?;

        if result.next().await?.is_none() {
            return Err(SyncError::SyncFailed(
                "Failed to validate Neo4j connection".to_string(),
            ));
        }

        info!("Connected to Neo4j for loading: {}", neo4j_config.database);

        Ok(Self {
            graph,
            database: neo4j_config.database.clone(),
            batch_size: sync_config.batch_size,
            node_id_cache: None,
            retry_attempts: sync_config.retry_attempts.max(1),
            retry_backoff_ms: sync_config.retry_backoff_ms.max(50),
        })
    }

    /// Get a reference to the node ID cache
    ///
    /// Returns None if cache has not been loaded yet
    pub fn get_node_id_cache(&self) -> Option<&NodeIdCache> {
        self.node_id_cache.as_ref()
    }

    async fn run_with_retry<T, Fut, F>(&self, op_name: &str, mut operation: F) -> Result<T>
    where
        F: FnMut() -> Fut,
        Fut: Future<Output = Result<T>>,
    {
        let mut attempt = 0usize;
        loop {
            match operation().await {
                Ok(value) => return Ok(value),
                Err(err) => {
                    attempt += 1;
                    if attempt >= self.retry_attempts {
                        return Err(err);
                    }

                    let backoff = self.retry_backoff_ms * (attempt as u64);
                    warn!(
                        "{} failed (attempt {}/{}) – retrying in {}ms: {}",
                        op_name, attempt, self.retry_attempts, backoff, err
                    );
                    sleep(Duration::from_millis(backoff)).await;
                }
            }
        }
    }

    async fn execute_batch_query(
        &self,
        cypher: &str,
        batch: &[HashMap<String, BoltType>],
    ) -> Result<()> {
        let query_str = cypher.to_string();
        let batch_vec: Vec<HashMap<String, BoltType>> = batch.to_vec();
        self.run_with_retry("neo4j_batch_write", || {
            let graph = self.graph.clone();
            let query = query(&query_str).param("batch", batch_vec.clone());
            async move {
                let mut result = graph.execute(query).await?;
                while result.next().await?.is_some() {}
                Ok(())
            }
        })
        .await
    }

    /// Take ownership of the node ID cache
    ///
    /// Returns None if cache has not been loaded yet.
    /// After calling this, the cache will be removed from the loader.
    pub fn take_node_id_cache(&mut self) -> Option<NodeIdCache> {
        self.node_id_cache.take()
    }

    fn transaction_chunk_rows(&self, batch_len: usize) -> usize {
        let chunk = self.batch_size.max(1);
        std::cmp::min(chunk, batch_len.max(1))
    }

    /// Load all node UUIDs and their internal IDs into cache
    ///
    /// This pre-loading optimization significantly speeds up edge creation
    /// by avoiding repeated UUID property lookups. Memory overhead is minimal
    /// (~80 bytes per node for UUID string + i64 ID).
    ///
    /// # Returns
    /// Number of nodes loaded into cache
    ///
    /// # Errors
    /// Returns error if query execution fails
    pub async fn load_node_id_cache(&mut self) -> Result<usize> {
        info!("Loading node ID cache for optimized edge creation...");
        let start_time = Instant::now();

        let mut cache = NodeIdCache::new();

        let mut count = 0;
        const CACHE_LABELS: &[&str] = &["Entity", "Episodic", "Community"];
        const PAGE_SIZE: usize = 5_000;

        for label in CACHE_LABELS {
            let mut page = 0usize;
            loop {
                let cypher = format!(
                    "MATCH (n:{label}) \
                     RETURN n.uuid AS uuid, id(n) AS id \
                     SKIP $skip LIMIT $limit"
                );

                let mut result = self
                    .graph
                    .execute(
                        query(&cypher)
                            .param("skip", (page * PAGE_SIZE) as i64)
                            .param("limit", PAGE_SIZE as i64),
                    )
                    .await?;

                let mut page_loaded = 0usize;
                while let Some(row) = result.next().await? {
                    let uuid: String = row.get("uuid").map_err(|e| {
                        SyncError::SyncFailed(format!("Failed to get uuid from row: {}", e))
                    })?;
                    let id: i64 = row.get("id").map_err(|e| {
                        SyncError::SyncFailed(format!("Failed to get id from row: {}", e))
                    })?;
                    cache.insert(uuid, id);
                    count += 1;
                    page_loaded += 1;
                }

                if page_loaded == 0 {
                    debug!("No nodes found for label '{}' page {}", label, page);
                    break;
                }

                if count % PAGE_SIZE == 0 {
                    debug!("Loaded {} node IDs into cache...", count);
                }

                if page_loaded < PAGE_SIZE {
                    break;
                }

                page += 1;
            }
        }

        // Handle any nodes without one of the known labels
        let mut result = self
            .graph
            .execute(query(
                "MATCH (n) \
                     WHERE size(labels(n)) = 0 \
                     RETURN n.uuid AS uuid, id(n) AS id",
            ))
            .await?;

        while let Some(row) = result.next().await? {
            let uuid: String = row.get("uuid").map_err(|e| {
                SyncError::SyncFailed(format!("Failed to get uuid from row: {}", e))
            })?;
            let id: i64 = row
                .get("id")
                .map_err(|e| SyncError::SyncFailed(format!("Failed to get id from row: {}", e)))?;
            if cache.get(&uuid).is_none() {
                cache.insert(uuid, id);
                count += 1;
            }
        }

        let duration = start_time.elapsed();
        info!(
            "Loaded {} node IDs into cache in {:?} (memory: ~{} MB)",
            count,
            duration,
            (count * 80) / 1_000_000 // Rough estimate: 80 bytes per entry
        );

        self.node_id_cache = Some(cache);
        Ok(count)
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

            match self.merge_nodes_batch(&batch).await {
                Ok(_) => {
                    total_loaded += batch_size;
                    info!(
                        "Loaded batch {} with {} nodes (total: {})",
                        batch_count, batch_size, total_loaded
                    );
                }
                Err(e) => {
                    error!("Failed to load batch {}: {}", batch_count, e);
                    return Err(e);
                }
            }
        }

        let duration = start_time.elapsed();
        info!(
            "Completed loading {} nodes in {} batches ({:?})",
            total_loaded, batch_count, duration
        );

        Ok(LoadingStats {
            nodes_loaded: total_loaded,
            edges_loaded: 0,
            duration,
        })
    }

    /// Load nodes in parallel using multiple worker tasks
    ///
    /// Spawns multiple worker tasks that concurrently process batches from the channel.
    /// This provides significant speedup for high-throughput scenarios by parallelizing
    /// the batch write operations to Neo4j.
    ///
    /// # Arguments
    /// * `rx` - Receiver channel for node batches
    /// * `num_workers` - Number of parallel worker tasks (recommended: 4-8)
    ///
    /// # Returns
    /// LoadingStats with node count and duration
    pub async fn load_nodes_parallel(
        rx: mpsc::Receiver<Vec<GraphNode>>,
        neo4j_config: &Neo4jConfig,
        sync_config: &SyncConfig,
        num_workers: usize,
    ) -> Result<LoadingStats> {
        use std::sync::Arc;
        use tokio::sync::Mutex;

        let start_time = Instant::now();

        info!(
            "Starting parallel node loading with {} workers, batch_size={}",
            num_workers, sync_config.batch_size
        );

        // Wrap the receiver in Arc<Mutex> so multiple workers can access it
        let rx = Arc::new(Mutex::new(rx));

        // Counters for statistics
        let total_loaded = Arc::new(Mutex::new(0usize));
        let batch_count = Arc::new(Mutex::new(0usize));

        // Spawn worker tasks
        let mut worker_handles = Vec::new();

        for worker_id in 0..num_workers {
            let rx = Arc::clone(&rx);
            let total_loaded = Arc::clone(&total_loaded);
            let batch_count = Arc::clone(&batch_count);
            let neo4j_config = neo4j_config.clone();
            let sync_config = sync_config.clone();

            let handle = tokio::spawn(async move {
                // Each worker creates its own loader instance (Neo4j connection)
                let mut loader = match Neo4jLoader::new(&neo4j_config, &sync_config).await {
                    Ok(l) => l,
                    Err(e) => {
                        error!("Worker {} failed to create loader: {}", worker_id, e);
                        return Err(e);
                    }
                };

                debug!("Worker {} started", worker_id);

                loop {
                    // Lock the receiver to get the next batch
                    let batch = {
                        let mut rx_guard = rx.lock().await;
                        rx_guard.recv().await
                    };

                    match batch {
                        Some(nodes) => {
                            let batch_size = nodes.len();
                            let current_batch = {
                                let mut count = batch_count.lock().await;
                                *count += 1;
                                *count
                            };

                            debug!(
                                "Worker {} processing batch {} with {} nodes",
                                worker_id, current_batch, batch_size
                            );

                            // Process the batch
                            match loader.merge_nodes_batch(&nodes).await {
                                Ok(_) => {
                                    let mut total = total_loaded.lock().await;
                                    *total += batch_size;
                                    info!(
                                        "Worker {} completed batch {} with {} nodes (total: {})",
                                        worker_id, current_batch, batch_size, *total
                                    );
                                }
                                Err(e) => {
                                    error!(
                                        "Worker {} failed to load batch {}: {}",
                                        worker_id, current_batch, e
                                    );
                                    return Err(e);
                                }
                            }
                        }
                        None => {
                            // Channel closed, worker is done
                            debug!("Worker {} finished (channel closed)", worker_id);
                            break;
                        }
                    }
                }

                Ok(())
            });

            worker_handles.push(handle);
        }

        // Wait for all workers to complete
        let mut had_error = false;
        for (worker_id, handle) in worker_handles.into_iter().enumerate() {
            match handle.await {
                Ok(Ok(())) => {
                    debug!("Worker {} completed successfully", worker_id);
                }
                Ok(Err(e)) => {
                    error!("Worker {} failed: {}", worker_id, e);
                    had_error = true;
                }
                Err(e) => {
                    error!("Worker {} panicked: {}", worker_id, e);
                    had_error = true;
                }
            }
        }

        if had_error {
            return Err(SyncError::SyncFailed(
                "One or more workers failed during parallel loading".to_string(),
            ));
        }

        let duration = start_time.elapsed();
        let final_total = *total_loaded.lock().await;
        let final_batches = *batch_count.lock().await;

        info!(
            "Completed parallel loading of {} nodes in {} batches using {} workers ({:?})",
            final_total, final_batches, num_workers, duration
        );

        Ok(LoadingStats {
            nodes_loaded: final_total,
            edges_loaded: 0,
            duration,
        })
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

            match self.merge_edges_batch(&batch).await {
                Ok(_) => {
                    total_loaded += batch_size;
                    info!(
                        "Loaded batch {} with {} edges (total: {})",
                        batch_count, batch_size, total_loaded
                    );
                }
                Err(e) => {
                    error!("Failed to load batch {}: {}", batch_count, e);
                    return Err(e);
                }
            }
        }

        let duration = start_time.elapsed();
        info!(
            "Completed loading {} edges in {} batches ({:?})",
            total_loaded, batch_count, duration
        );

        Ok(LoadingStats {
            nodes_loaded: 0,
            edges_loaded: total_loaded,
            duration,
        })
    }

    /// Load edges in parallel using multiple worker tasks with shared node ID cache
    ///
    /// Shares a single node ID cache across all workers via Arc to minimize memory usage
    /// while maximizing speed. The cache is loaded once and shared read-only, avoiding
    /// expensive UUID index lookups for each edge.
    ///
    /// # Arguments
    /// * `rx` - Receiver channel for edge batches
    /// * `neo4j_config` - Neo4j connection configuration
    /// * `sync_config` - Sync configuration
    /// * `node_id_cache` - Pre-loaded cache of node UUIDs → internal IDs
    /// * `num_workers` - Number of parallel worker tasks (recommended: 4-8)
    ///
    /// # Returns
    /// LoadingStats with edge count and duration
    pub async fn load_edges_parallel(
        rx: mpsc::Receiver<Vec<GraphEdge>>,
        neo4j_config: &Neo4jConfig,
        sync_config: &SyncConfig,
        node_id_cache: NodeIdCache,
        num_workers: usize,
    ) -> Result<LoadingStats> {
        use std::sync::Arc;
        use tokio::sync::Mutex;

        let start_time = Instant::now();

        info!(
            "Starting parallel edge loading with {} workers, batch_size={}, cache_size={} (using cached ID lookups)",
            num_workers, sync_config.batch_size, node_id_cache.len()
        );

        // Share the node ID cache via Arc - all workers share the same cache
        let shared_cache = Arc::new(node_id_cache);

        // Wrap the receiver in Arc<Mutex> so multiple workers can access it
        let rx = Arc::new(Mutex::new(rx));

        // Counters for statistics
        let total_loaded = Arc::new(Mutex::new(0usize));
        let batch_count = Arc::new(Mutex::new(0usize));

        // Spawn worker tasks
        let mut worker_handles = Vec::new();

        for worker_id in 0..num_workers {
            let rx = Arc::clone(&rx);
            let total_loaded = Arc::clone(&total_loaded);
            let batch_count = Arc::clone(&batch_count);
            let neo4j_config = neo4j_config.clone();
            let sync_config = sync_config.clone();
            let cache = Arc::clone(&shared_cache);

            let handle = tokio::spawn(async move {
                // Each worker creates its own loader instance (Neo4j connection)
                let loader = match Neo4jLoader::new(&neo4j_config, &sync_config).await {
                    Ok(l) => l,
                    Err(e) => {
                        error!("Worker {} failed to create loader: {}", worker_id, e);
                        return Err(e);
                    }
                };

                debug!("Worker {} started (cached ID lookup mode)", worker_id);

                loop {
                    // Lock the receiver to get the next batch
                    let batch = {
                        let mut rx_guard = rx.lock().await;
                        rx_guard.recv().await
                    };

                    match batch {
                        Some(edges) => {
                            let batch_size = edges.len();
                            let current_batch = {
                                let mut count = batch_count.lock().await;
                                *count += 1;
                                *count
                            };

                            debug!(
                                "Worker {} processing batch {} with {} edges",
                                worker_id, current_batch, batch_size
                            );

                            // Process batch with shared cache - fast cached ID lookups
                            // Arc allows sharing the cache without cloning
                            match loader
                                .merge_edges_batch_with_cache(&edges, Some(&cache))
                                .await
                            {
                                Ok(_) => {
                                    let total = {
                                        let mut t = total_loaded.lock().await;
                                        *t += batch_size;
                                        *t
                                    };
                                    // Only log every 10 batches to reduce overhead
                                    if current_batch % 10 == 0 {
                                        info!(
                                            "Worker {} progress: batch {} (total: {} edges)",
                                            worker_id, current_batch, total
                                        );
                                    }
                                }
                                Err(e) => {
                                    error!(
                                        "Worker {} failed to load batch {}: {}",
                                        worker_id, current_batch, e
                                    );
                                    return Err(e);
                                }
                            }

                            // Explicit drop to release batch memory immediately
                            drop(edges);
                        }
                        None => {
                            // Channel closed, worker is done
                            debug!("Worker {} finished (channel closed)", worker_id);
                            break;
                        }
                    }
                }

                Ok(())
            });

            worker_handles.push(handle);
        }

        // Wait for all workers to complete
        let mut had_error = false;
        for (worker_id, handle) in worker_handles.into_iter().enumerate() {
            match handle.await {
                Ok(Ok(())) => {
                    debug!("Worker {} completed successfully", worker_id);
                }
                Ok(Err(e)) => {
                    error!("Worker {} failed: {}", worker_id, e);
                    had_error = true;
                }
                Err(e) => {
                    error!("Worker {} panicked: {}", worker_id, e);
                    had_error = true;
                }
            }
        }

        if had_error {
            return Err(SyncError::SyncFailed(
                "One or more workers failed during parallel edge loading".to_string(),
            ));
        }

        let duration = start_time.elapsed();
        let final_total = *total_loaded.lock().await;
        let final_batches = *batch_count.lock().await;

        info!(
            "Completed parallel loading of {} edges in {} batches using {} workers ({:?})",
            final_total, final_batches, num_workers, duration
        );

        Ok(LoadingStats {
            nodes_loaded: 0,
            edges_loaded: final_total,
            duration,
        })
    }

    /// CREATE a batch of nodes using UNWIND pattern
    ///
    /// Builds a Cypher query that uses UNWIND to batch process nodes.
    /// NOTE: Uses CREATE instead of MERGE for initial sync/disaster recovery,
    /// assuming nodes are unique in the source data. This provides significant speedup
    /// by skipping existence checks (MERGE requires property lookups).
    /// Each node is created with UUID and its properties are set.
    /// Note: Neo4j doesn't support parameterized complex data structures easily,
    /// so we build the query string with escaped values (same as FalkorDB).
    ///
    /// # Arguments
    /// * `nodes` - Slice of graph nodes to create
    ///
    /// # Errors
    /// Returns error if query execution fails
    async fn merge_nodes_batch(&mut self, nodes: &[GraphNode]) -> Result<()> {
        if nodes.is_empty() {
            return Ok(());
        }

        debug!("Building CREATE query for {} nodes", nodes.len());

        // Group nodes by their label combinations for efficient batching
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

            // Prepare parameter payload
            let group_count = group_nodes.len();
            let mut batch_items: Vec<HashMap<String, BoltType>> = Vec::with_capacity(group_count);

            for node in group_nodes {
                let mut props_map = Self::convert_properties_map(&node.properties);
                // Ensure UUID is always present on the node
                props_map.insert("uuid".to_string(), BoltType::from(node.uuid.clone()));

                let mut item: HashMap<String, BoltType> = HashMap::with_capacity(1);
                item.insert("props".to_string(), BoltType::from(props_map));
                batch_items.push(item);
            }

            let batch_len = batch_items.len();
            let mut query_lines = Vec::new();
            if self.database != "neo4j" {
                query_lines.push(format!("USE {}", self.database));
            }
            query_lines.push("CALL {".to_string());
            query_lines.push("  WITH $batch AS batch".to_string());
            query_lines.push("  UNWIND batch AS item".to_string());
            query_lines.push(format!("  MERGE (n{} {{uuid: item.props.uuid}})", label_str));
            query_lines.push("  SET n = item.props".to_string());
            query_lines.push("}".to_string());
            query_lines.push(format!(
                "IN TRANSACTIONS OF {} ROWS",
                self.transaction_chunk_rows(batch_len)
            ));

            let cypher = query_lines.join("\n");

            debug!(
                "Executing parameterized CREATE for {} nodes with labels {:?}",
                batch_len, labels
            );

            self.execute_batch_query(&cypher, &batch_items).await?;

            debug!(
                "Successfully created {} nodes with labels {:?}",
                batch_len, labels
            );
        }

        Ok(())
    }

    /// CREATE a batch of edges using UNWIND pattern
    ///
    /// Builds a Cypher query that uses UNWIND to batch process edges.
    /// Matches source and target nodes by UUID and creates the relationship.
    /// NOTE: Uses CREATE instead of MERGE for initial sync/disaster recovery,
    /// assuming edges are unique in the source data. This provides 5-10x speedup
    /// by skipping existence checks.
    ///
    /// # Arguments
    /// * `edges` - Slice of graph edges to create
    ///
    /// # Errors
    /// Returns error if query execution fails
    async fn merge_edges_batch(&mut self, edges: &[GraphEdge]) -> Result<()> {
        self.merge_edges_batch_with_cache(edges, self.node_id_cache.as_ref())
            .await
    }

    /// CREATE a batch of edges using UNWIND pattern with optional external cache
    ///
    /// This method allows passing a cache reference without taking ownership,
    /// which is essential for parallel processing where the cache is shared via Arc.
    ///
    /// # Arguments
    /// * `edges` - Slice of graph edges to create
    /// * `cache` - Optional reference to node ID cache
    ///
    /// # Errors
    /// Returns error if query execution fails
    async fn merge_edges_batch_with_cache(
        &self,
        edges: &[GraphEdge],
        cache: Option<&NodeIdCache>,
    ) -> Result<()> {
        if edges.is_empty() {
            return Ok(());
        }

        debug!("Building CREATE query for {} edges", edges.len());

        let mut edges_by_type: std::collections::HashMap<String, Vec<&GraphEdge>> =
            std::collections::HashMap::new();

        for edge in edges {
            edges_by_type
                .entry(edge.relationship_type.clone())
                .or_default()
                .push(edge);
        }

        for (rel_type, group_edges) in edges_by_type {
            if group_edges.is_empty() {
                continue;
            }

            let use_cached_ids = if let Some(cache_ref) = cache {
                group_edges.iter().all(|edge| {
                    cache_ref
                        .get(&edge.source_uuid)
                        .zip(cache_ref.get(&edge.target_uuid))
                        .is_some()
                })
            } else {
                false
            };

            let mut batch_items: Vec<HashMap<String, BoltType>> =
                Vec::with_capacity(group_edges.len());

            for edge in &group_edges {
                let mut item: HashMap<String, BoltType> = HashMap::new();
                let props_map = Self::convert_properties_map(&edge.properties);
                item.insert("props".to_string(), BoltType::from(props_map));

                if use_cached_ids {
                    if let Some(cache_ref) = cache {
                        let source_id = cache_ref
                            .get(&edge.source_uuid)
                            .expect("source id should exist when using cache");
                        let target_id = cache_ref
                            .get(&edge.target_uuid)
                            .expect("target id should exist when using cache");
                        item.insert("source_id".to_string(), BoltType::from(source_id));
                        item.insert("target_id".to_string(), BoltType::from(target_id));
                    }
                } else {
                    item.insert(
                        "source".to_string(),
                        BoltType::from(edge.source_uuid.clone()),
                    );
                    item.insert(
                        "target".to_string(),
                        BoltType::from(edge.target_uuid.clone()),
                    );
                }

                batch_items.push(item);
            }

            let mut query_lines = Vec::new();
            if self.database != "neo4j" {
                query_lines.push(format!("USE {}", self.database));
            }
            query_lines.push("CALL {".to_string());
            query_lines.push("  WITH $batch AS batch".to_string());
            query_lines.push("  UNWIND batch AS item".to_string());

            if use_cached_ids {
                query_lines.push("  MATCH (source) WHERE id(source) = item.source_id".to_string());
                query_lines.push("  MATCH (target) WHERE id(target) = item.target_id".to_string());
            } else {
                if cache.is_some() {
                    warn!("Some nodes not found in cache, falling back to UUID lookups");
                }
                query_lines.push("  MATCH (source) WHERE source.uuid = item.source".to_string());
                query_lines.push("  MATCH (target) WHERE target.uuid = item.target".to_string());
            }

            query_lines.push(format!(
                "  MERGE (source)-[r:{}]->(target)",
                Self::escape_identifier(&rel_type)
            ));
            query_lines.push("  SET r += item.props".to_string());
            query_lines.push("}".to_string());

            let batch_len = batch_items.len();
            query_lines.push(format!(
                "IN TRANSACTIONS OF {} ROWS",
                self.transaction_chunk_rows(batch_len)
            ));

            let cypher = query_lines.join("\n");

            debug!(
                "Executing parameterized CREATE for {} edges with type '{}'",
                batch_len, rel_type
            );

            self.execute_batch_query(&cypher, &batch_items).await?;

            debug!(
                "Successfully created {} edges with type '{}'",
                batch_len, rel_type
            );
        }

        Ok(())
    }

    fn convert_properties_map(
        properties: &HashMap<String, PropertyValue>,
    ) -> HashMap<String, BoltType> {
        let mut converted = HashMap::with_capacity(properties.len());
        for (key, value) in properties {
            converted.insert(key.clone(), Self::property_value_to_bolt(value));
        }
        converted
    }

    fn property_value_to_bolt(value: &PropertyValue) -> BoltType {
        match value {
            PropertyValue::String(s) => BoltType::from(s.clone()),
            PropertyValue::Integer(i) => BoltType::from(*i),
            PropertyValue::Float(f) => BoltType::from(*f),
            PropertyValue::Boolean(b) => BoltType::from(*b),
            PropertyValue::List(items) => {
                let list: Vec<BoltType> = items.iter().map(Self::property_value_to_bolt).collect();
                BoltType::from(list)
            }
            PropertyValue::Null => BoltType::Null(BoltNull),
        }
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
    fn test_escape_identifier() {
        assert_eq!(Neo4jLoader::escape_identifier("simple_name"), "simple_name");
        assert_eq!(Neo4jLoader::escape_identifier("with space"), "`with space`");
        assert_eq!(Neo4jLoader::escape_identifier("123numeric"), "`123numeric`");
        assert_eq!(
            Neo4jLoader::escape_identifier("special-char"),
            "`special-char`"
        );
    }

    #[test]
    fn test_property_value_to_bolt() {
        assert_eq!(
            Neo4jLoader::property_value_to_bolt(&PropertyValue::String("test".to_string())),
            BoltType::from("test")
        );
        assert_eq!(
            Neo4jLoader::property_value_to_bolt(&PropertyValue::Integer(42)),
            BoltType::from(42)
        );
        assert_eq!(
            Neo4jLoader::property_value_to_bolt(&PropertyValue::Float(2.718)),
            BoltType::from(2.718)
        );
        assert_eq!(
            Neo4jLoader::property_value_to_bolt(&PropertyValue::Boolean(true)),
            BoltType::from(true)
        );
        assert_eq!(
            Neo4jLoader::property_value_to_bolt(&PropertyValue::Null),
            BoltType::Null(BoltNull)
        );

        let list = PropertyValue::List(vec![
            PropertyValue::Integer(1),
            PropertyValue::Integer(2),
            PropertyValue::Integer(3),
        ]);
        assert_eq!(
            Neo4jLoader::property_value_to_bolt(&list),
            BoltType::from(vec![1, 2, 3])
        );
    }

    #[test]
    fn test_convert_properties_map() {
        let mut props = HashMap::new();
        props.insert("name".to_string(), PropertyValue::String("Neo".to_string()));
        props.insert("count".to_string(), PropertyValue::Integer(7));

        let converted = Neo4jLoader::convert_properties_map(&props);
        assert_eq!(converted.get("name"), Some(&BoltType::from("Neo")));
        assert_eq!(converted.get("count"), Some(&BoltType::from(7)));
    }
}
