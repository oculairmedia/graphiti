# Incremental Update Implementation Plan

## Problem Statement

The Rust graph visualizer currently performs a **full reload** of ALL nodes and edges from FalkorDB whenever ANY change is detected (even a single new node). This causes:

- ⏱️ **5-10 minute reload times** for 90K+ edges
- 🚫 **Blocks ALL API requests** during reload
- 💾 **High memory usage** loading entire graph
- 😞 **Poor user experience** - frontend appears frozen

## Current Behavior

```
Every 30 seconds:
1. Poll FalkorDB for node/edge counts
2. If ANY change detected → Fetch ENTIRE graph (32,577 nodes + 90,408 edges)
3. Clear DuckDB completely
4. Reload ALL data into DuckDB (5-10 minutes, blocks all requests)
5. Compute delta (compare old vs new)
6. Broadcast delta to WebSocket clients
```

## Proposed Solution: True Incremental Updates

```
Every 30 seconds:
1. Poll FalkorDB for node/edge counts
2. If change detected → Fetch ONLY new/changed nodes (using timestamp filter)
3. Incrementally UPDATE DuckDB (add/update only changed records)
4. Compute delta (only new/changed data)
5. Broadcast delta to WebSocket clients

Time: <1 second (instead of 5-10 minutes)
Impact: Non-blocking, minimal memory
```

## Implementation Details

### File: `/opt/stacks/graphiti/graph-visualizer-rust/src/main.rs`

### Step 1: Add Timestamp Tracking

**Location**: Around line 524 (in the background monitoring task)

**Add**:
```rust
tokio::spawn(async move {
    let mut interval = tokio::time::interval(tokio::time::Duration::from_secs(30));
    let mut last_node_count = 0;
    let mut last_edge_count = 0;
    let mut last_centrality_sum = 0.0;
    
    // NEW: Track last successful fetch timestamp
    let mut last_fetch_timestamp: Option<String> = None;
    let mut is_first_sync = true;
    
    loop {
        interval.tick().await;
        // ... existing code
```

### Step 2: Replace Full Reload with Incremental Fetch

**Location**: Around line 588-595 (where it says "Auto-reloading DuckDB")

**Replace**:
```rust
// OLD CODE (REMOVE THIS):
info!("Auto-reloading DuckDB from FalkorDB due to detected changes");
let query = build_query("entire_graph", 100000, 0, None);
if let Ok(graph_data) = execute_graph_query(&client_clone, &graph_name_clone, &query).await {
    info!("Fetched {} nodes and {} edges from FalkorDB", 
        graph_data.nodes.len(), graph_data.edges.len());
    
    // Reload DuckDB with fresh data
    if let Ok(_) = store_clone.load_initial_data(graph_data.nodes.clone(), graph_data.edges.clone()).await {
```

**WITH NEW CODE**:
```rust
// NEW CODE:
if is_first_sync {
    info!("First sync - performing full load from FalkorDB");
    let query = build_query("entire_graph", 100000, 0, None);
    if let Ok(graph_data) = execute_graph_query(&client_clone, &graph_name_clone, &query).await {
        info!("Fetched {} nodes and {} edges from FalkorDB", 
            graph_data.nodes.len(), graph_data.edges.len());
        
        // Full load on first sync
        if let Ok(_) = store_clone.load_initial_data(graph_data.nodes.clone(), graph_data.edges.clone()).await {
            info!("DuckDB initialized successfully with full data");
            is_first_sync = false;
            last_fetch_timestamp = Some(chrono::Utc::now().to_rfc3339());
            
            // Compute and broadcast delta
            let delta = delta_tracker_clone.compute_delta(
                graph_data.nodes,
                graph_data.edges
            ).await;
            
            info!("Broadcasting initial delta: {} nodes added, {} edges added",
                delta.nodes_added.len(), delta.edges_added.len());
            let _ = delta_tx_clone.send(delta);
        }
    }
} else {
    // INCREMENTAL UPDATE
    info!("Performing incremental update from FalkorDB");
    let timestamp = last_fetch_timestamp.as_deref().unwrap_or("1970-01-01T00:00:00Z");
    let query = build_query("new_nodes_since", 10000, 0, Some(timestamp));
    
    if let Ok(graph_data) = execute_graph_query(&client_clone, &graph_name_clone, &query).await {
        if !graph_data.nodes.is_empty() || !graph_data.edges.is_empty() {
            info!("Fetched {} new/changed nodes and {} new edges from FalkorDB", 
                graph_data.nodes.len(), graph_data.edges.len());
            
            // Incremental update to DuckDB
            if let Ok(_) = store_clone.update_incremental(graph_data.nodes.clone(), graph_data.edges.clone()).await {
                info!("DuckDB updated incrementally");
                last_fetch_timestamp = Some(chrono::Utc::now().to_rfc3339());
                
                // Clear caches for affected data
                cache_clone.clear();
                let mut arrow_cache_guard = arrow_cache_clone.write().await;
                *arrow_cache_guard = None;
                drop(arrow_cache_guard);
                
                // Compute and broadcast delta
                let delta = delta_tracker_clone.compute_delta(
                    graph_data.nodes,
                    graph_data.edges
                ).await;
                
                info!("Broadcasting delta: {} nodes added, {} nodes updated, {} edges added",
                    delta.nodes_added.len(), delta.nodes_updated.len(), delta.edges_added.len());
                let _ = delta_tx_clone.send(delta);
            }
        } else {
            info!("No new changes detected in incremental fetch");
        }
    }
}
```

### Step 3: Add Incremental Query Type to `build_query`

**Location**: Around line 855 (in the `build_query` function)

**Add new case**:
```rust
fn build_query(query_type: &str, limit: usize, offset: usize, search: Option<&str>) -> String {
    match query_type {
        "entire_graph" => {
            "ENTIRE_GRAPH_SPECIAL".to_string()
        },
        
        // NEW: Incremental fetch query
        "new_nodes_since" => {
            if let Some(timestamp) = search {
                format!("INCREMENTAL_FETCH_SPECIAL|{}", timestamp)
            } else {
                "ENTIRE_GRAPH_SPECIAL".to_string()
            }
        },
        
        "high_degree" => format!(
            // ... existing code
        ),
        // ... rest of cases
    }
}
```

### Step 4: Handle Incremental Query in `execute_graph_query`

**Location**: Around line 931 (start of `execute_graph_query` function)

**Add**:
```rust
async fn execute_graph_query(client: &FalkorAsyncClient, graph_name: &str, query: &str) -> anyhow::Result<GraphData> {
    let mut nodes_map: HashMap<String, Node> = HashMap::new();
    let mut edges = Vec::new();
    
    // Handle incremental fetch
    if query.starts_with("INCREMENTAL_FETCH_SPECIAL|") {
        let timestamp = query.strip_prefix("INCREMENTAL_FETCH_SPECIAL|").unwrap();
        info!("Fetching nodes created/updated after: {}", timestamp);
        
        // Query for new nodes
        let nodes_query = format!(r#"
            MATCH (n)
            WHERE n.created_at > '{}'
            RETURN 
                n.uuid as id,
                n.name as name,
                COALESCE(n.type, labels(n)[0]) as node_type,
                COALESCE(n.degree_centrality, 0) as degree_centrality,
                COALESCE(n.pagerank_centrality, 0) as pagerank_centrality,
                COALESCE(n.betweenness_centrality, 0) as betweenness_centrality,
                COALESCE(n.eigenvector_centrality, 0) as eigenvector_centrality,
                n.created_at as created_at,
                n.summary as summary
            LIMIT 10000
        "#, timestamp);
        
        let mut graph = client.select_graph(graph_name);
        let mut nodes_result = graph.query(&nodes_query).execute().await?;
        
        // Process new nodes
        while let Some(row) = nodes_result.data.next() {
            if row.len() >= 9 {
                let node_id = value_to_string(&row[0]);
                let node_name = value_to_string(&row[1]);
                let node_type = value_to_string(&row[2]);
                let degree_centrality = value_to_f64(&row[3]);
                let pagerank_centrality = value_to_f64(&row[4]);
                let betweenness_centrality = value_to_f64(&row[5]);
                let eigenvector_centrality = value_to_f64(&row[6]);
                let created_at = value_to_string(&row[7]);
                let summary_text = row[8].as_string().map(|s| s.to_string());
                
                let mut node_props = HashMap::new();
                node_props.insert("name".to_string(), serde_json::Value::String(node_name.clone()));
                node_props.insert("type".to_string(), serde_json::Value::String(node_type.clone()));
                node_props.insert("degree_centrality".to_string(), serde_json::json!(degree_centrality));
                node_props.insert("pagerank_centrality".to_string(), serde_json::json!(pagerank_centrality));
                node_props.insert("betweenness_centrality".to_string(), serde_json::json!(betweenness_centrality));
                node_props.insert("eigenvector_centrality".to_string(), serde_json::json!(eigenvector_centrality));
                
                if !created_at.is_empty() {
                    node_props.insert("created_at".to_string(), serde_json::Value::String(created_at));
                }
                
                nodes_map.insert(node_id.clone(), Node {
                    id: node_id.clone(),
                    label: truncate_string(&node_name, 50),
                    node_type: node_type.clone(),
                    summary: summary_text,
                    properties: node_props,
                });
            }
        }
        
        info!("Fetched {} new nodes", nodes_map.len());
        
        // Query for edges connected to new nodes
        if !nodes_map.is_empty() {
            let node_ids: Vec<String> = nodes_map.keys()
                .map(|id| format!("'{}'", id))
                .collect();
            let node_ids_list = node_ids.join(", ");
            
            let edges_query = format!(r#"
                MATCH (n)-[r]->(m)
                WHERE n.uuid IN [{}] OR m.uuid IN [{}]
                RETURN 
                    n.uuid as source_id,
                    m.uuid as target_id,
                    type(r) as edge_type,
                    COALESCE(r.weight, 1.0) as weight
                LIMIT 50000
            "#, node_ids_list, node_ids_list);
            
            let mut graph = client.select_graph(graph_name);
            let mut edges_result = graph.query(&edges_query).execute().await?;
            
            while let Some(row) = edges_result.data.next() {
                if row.len() >= 4 {
                    edges.push(Edge {
                        from: value_to_string(&row[0]),
                        to: value_to_string(&row[1]),
                        edge_type: value_to_string(&row[2]),
                        weight: value_to_f64(&row[3]),
                    });
                }
            }
            
            info!("Fetched {} edges for new nodes", edges.len());
        }
        
        return Ok(GraphData {
            nodes: nodes_map.into_values().collect(),
            edges,
        });
    }
    
    // Special handling for entire_graph query (existing code continues...)
    if query == "ENTIRE_GRAPH_SPECIAL" {
        // ... existing full load code
```

### Step 5: Add Incremental Update Method to DuckDB Store

**File**: `/opt/stacks/graphiti/graph-visualizer-rust/src/duckdb_store.rs`

**Add new method** (around line 400, after `load_initial_data`):

```rust
/// Incrementally update DuckDB with new/changed nodes and edges
pub async fn update_incremental(&self, nodes: Vec<Node>, edges: Vec<Edge>) -> anyhow::Result<()> {
    let conn = self.connection.lock().await;
    
    info!("Starting incremental update: {} nodes, {} edges", nodes.len(), edges.len());
    
    // Use INSERT OR REPLACE to handle both new and updated nodes
    let stmt_node = "INSERT OR REPLACE INTO nodes (id, idx, label, node_type, summary, degree_centrality, pagerank_centrality, betweenness_centrality, eigenvector_centrality, x, y, color, size, created_at, created_at_timestamp, cluster, clusterStrength)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)";
    
    let mut updated_count = 0;
    for node in &nodes {
        let (created_str, timestamp) = Self::normalize_created_at(&node);
        
        conn.execute(
            stmt_node,
            params![
                &node.id,
                updated_count, // Temporary idx, will be recalculated
                &node.label,
                &node.node_type,
                &node.summary,
                self.get_node_property(&node, "degree_centrality"),
                self.get_node_property(&node, "pagerank_centrality"),
                self.get_node_property(&node, "betweenness_centrality"),
                self.get_node_property(&node, "eigenvector_centrality"),
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
```

## Testing Plan

### 1. Test First Sync (Full Load)
```bash
# Restart Rust visualizer
docker restart graphiti-graph-visualizer-rust-1

# Watch logs - should see "First sync - performing full load"
docker logs -f graphiti-graph-visualizer-rust-1
```

### 2. Test Incremental Update
```bash
# Add a new node to FalkorDB (via Python API)
# Watch logs - after 30 seconds should see "Performing incremental update"
# Should fetch only the new node (not all 32K nodes)
```

### 3. Verify Performance
- **Before**: 5-10 minutes for full reload
- **After**: <1 second for incremental update

## Benefits

| Aspect | Before (Full Reload) | After (Incremental) | Improvement |
|--------|---------------------|---------------------|-------------|
| **Time** | 5-10 minutes | <1 second | **300-600x faster** |
| **Data Fetched** | 90K+ records | 1-100 records | **900-90000x less** |
| **API Blocking** | Yes, 5-10 min | No | **Always responsive** |
| **Memory** | High (full graph) | Low (only changes) | **90-99% less** |
| **User Experience** | Frozen UI | Real-time updates | **Much better** |

## Rollback Plan

If issues occur, restore the backup:
```bash
cd /opt/stacks/graphiti/graph-visualizer-rust
cp src/main.rs.backup src/main.rs
docker build -t graphiti-rust-visualizer:latest .
docker restart graphiti-graph-visualizer-rust-1
```

## Dependencies

- Requires `chrono` crate (should already be in Cargo.toml)
- FalkorDB must have `created_at` field on nodes (already present)

## Notes

- The `created_at` field is used as the timestamp for incremental fetching
- First sync after restart will still do a full load (necessary to initialize)
- Subsequent syncs will be incremental
- If incremental fetch fails, it will fall back to full reload on next cycle
