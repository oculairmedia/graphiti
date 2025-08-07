use axum::{
    extract::{Path, Query, State, WebSocketUpgrade},
    http::{StatusCode, header, HeaderMap},
    response::{IntoResponse, Json, Response},
    routing::{get, patch, post},
    Router,
    body::Body,
};
use dashmap::DashMap;
use falkordb::{FalkorClientBuilder, FalkorConnectionInfo, FalkorValue, FalkorAsyncClient};
use serde::{Deserialize, Serialize};
use std::{collections::HashMap, sync::Arc};
use tower_http::{
    cors::CorsLayer,
    compression::CompressionLayer,
};
use tracing::{error, info, debug};
use tokio::sync::{broadcast, RwLock};
use arrow::record_batch::RecordBatch;
use bytes::Bytes;
use sha2::{Sha256, Digest};
use base64::{Engine as _, engine::general_purpose};

mod duckdb_store;
mod arrow_converter;
mod delta_tracker;

use duckdb_store::{DuckDBStore, GraphUpdate};
use arrow_converter::ArrowConverter;
use delta_tracker::{DeltaTracker, GraphDelta};

#[derive(Clone)]
struct AppState {
    client: Arc<FalkorAsyncClient>,
    graph_name: String,
    graph_cache: Arc<DashMap<String, GraphData>>,
    duckdb_store: Arc<DuckDBStore>,
    update_tx: broadcast::Sender<GraphUpdate>,
    delta_tx: broadcast::Sender<GraphDelta>,
    arrow_cache: Arc<RwLock<Option<ArrowCache>>>,
    delta_tracker: Arc<DeltaTracker>,
    http_client: Arc<reqwest::Client>,
    centrality_url: String,
}

#[derive(Clone)]
struct ArrowCache {
    nodes_batch: RecordBatch,
    edges_batch: RecordBatch,
    nodes_bytes: Bytes,
    edges_bytes: Bytes,
    nodes_etag: String,
    edges_etag: String,
    timestamp: std::time::Instant,
}

impl ArrowCache {
    fn generate_etag(data: &[u8]) -> String {
        let mut hasher = Sha256::new();
        hasher.update(data);
        let hash = hasher.finalize();
        format!("W/\"{}\"", general_purpose::URL_SAFE_NO_PAD.encode(&hash[..8]))
    }
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct GraphData {
    nodes: Vec<Node>,
    edges: Vec<Edge>,
    stats: GraphStats,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct Node {
    id: String,
    label: String,
    node_type: String,
    summary: Option<String>,  // Add summary field for NodeDetailsPanel
    // Remove frontend-calculated fields - let Cosmograph v2.0 handle transformations
    properties: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct Edge {
    from: String,
    to: String,
    edge_type: String,
    weight: f64,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct GraphStats {
    total_nodes: usize,
    total_edges: usize,
    node_types: HashMap<String, usize>,
    avg_degree: f64,
    max_degree: f64,
}

impl Default for GraphStats {
    fn default() -> Self {
        Self {
            total_nodes: 0,
            total_edges: 0,
            node_types: HashMap::new(),
            avg_degree: 0.0,
            max_degree: 0.0,
        }
    }
}

#[derive(Debug, Deserialize)]
struct QueryParams {
    query_type: String,
    limit: Option<usize>,
    offset: Option<usize>,
    search: Option<String>,
}

#[derive(Debug, Serialize)]
struct QueryResponse {
    data: GraphData,
    has_more: bool,
    execution_time_ms: u128,
}

#[derive(Debug, Serialize)]
struct ErrorResponse {
    error: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct CacheStats {
    total_entries: usize,
    cache_keys: Vec<String>,
}

#[derive(Debug, Serialize, Deserialize)]
struct CacheResponse {
    message: String,
    cleared_entries: usize,
}

#[derive(Debug, Serialize, Deserialize)]
struct UpdateSummaryRequest {
    summary: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct NodeUpdateResponse {
    uuid: String,
    name: String,
    summary: String,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter("graph_visualizer=debug,tower_http=debug")
        .init();

    // Connect to FalkorDB
    let falkor_host = std::env::var("FALKORDB_HOST").unwrap_or_else(|_| "falkordb".to_string());
    let falkor_port = std::env::var("FALKORDB_PORT").unwrap_or_else(|_| "6379".to_string());
    let graph_name = std::env::var("GRAPH_NAME").unwrap_or_else(|_| "graphiti_migration".to_string());
    
    let connection_string = format!("redis://{}:{}", falkor_host, falkor_port);
    info!("Connecting to FalkorDB at {}", connection_string);
    
    let connection_info: FalkorConnectionInfo = connection_string
        .as_str()
        .try_into()
        .expect("Invalid connection info");
    
    let client = FalkorClientBuilder::new_async()
        .with_connection_info(connection_info)
        .build()
        .await
        .expect("Failed to build FalkorDB client");
    
    // Initialize DuckDB store
    let duckdb_store = Arc::new(DuckDBStore::new().expect("Failed to create DuckDB store"));
    
    // Create update channel for real-time updates
    let (update_tx, _) = broadcast::channel::<GraphUpdate>(100);
    let (delta_tx, _) = broadcast::channel::<GraphDelta>(100);
    
    // Initialize delta tracker
    let delta_tracker = Arc::new(DeltaTracker::new());
    
    // Set up HTTP client for centrality service proxy
    let http_client = Arc::new(reqwest::Client::new());
    let centrality_url = std::env::var("CENTRALITY_SERVICE_URL")
        .unwrap_or_else(|_| "http://graphiti-centrality-rs:3003".to_string());
    
    let state = AppState {
        client: Arc::new(client),
        graph_name: graph_name.clone(),
        graph_cache: Arc::new(DashMap::new()),
        duckdb_store: duckdb_store.clone(),
        update_tx: update_tx.clone(),
        delta_tx: delta_tx.clone(),
        arrow_cache: Arc::new(RwLock::new(None)),
        delta_tracker: delta_tracker.clone(),
        http_client,
        centrality_url,
    };
    
    // Load initial data into DuckDB with optimized separate queries
    {
        // Read limits from environment variables
        let node_limit = std::env::var("NODE_LIMIT")
            .unwrap_or_else(|_| "1500".to_string())
            .parse::<usize>()
            .unwrap_or(1500);
        
        let edge_limit = std::env::var("EDGE_LIMIT")
            .unwrap_or_else(|_| "5000".to_string())
            .parse::<usize>()
            .unwrap_or(5000);
        
        let min_degree = std::env::var("MIN_DEGREE_CENTRALITY")
            .unwrap_or_else(|_| "0.001".to_string())
            .parse::<f64>()
            .unwrap_or(0.001);
        
        info!("Loading initial graph data into DuckDB with limits - Nodes: {}, Edges: {}, Min Degree: {}", 
              node_limit, edge_limit, min_degree);
        let prerender_start = std::time::Instant::now();
        
        // Step 1: Load nodes first (much more efficient)
        // If min_degree is 0, load ALL nodes without filtering
        let nodes_query = if min_degree <= 0.0 {
            format!(
                "MATCH (n) RETURN n.uuid as id, n.name as name, COALESCE(n.type, labels(n)[0]) as label, COALESCE(n.degree_centrality, 0.0) as degree, n.created_at as created_at, n.summary as summary, n.pagerank_centrality as pagerank, n.betweenness_centrality as betweenness, n.eigenvector_centrality as eigenvector ORDER BY COALESCE(n.degree_centrality, 0.0) DESC LIMIT {}",
                node_limit
            )
        } else {
            format!(
                "MATCH (n) WHERE EXISTS(n.degree_centrality) AND n.degree_centrality > {} RETURN n.uuid as id, n.name as name, COALESCE(n.type, labels(n)[0]) as label, n.degree_centrality as degree, n.created_at as created_at, n.summary as summary, n.pagerank_centrality as pagerank, n.betweenness_centrality as betweenness, n.eigenvector_centrality as eigenvector ORDER BY n.degree_centrality DESC LIMIT {}",
                min_degree, node_limit
            )
        };
        
        let mut graph = state.client.select_graph(&graph_name);
        let mut nodes_result = graph.query(&nodes_query).execute().await?;
        let mut node_ids = Vec::new();
        let mut nodes = Vec::new();
        
        while let Some(row) = nodes_result.data.next() {
            if let Some(id) = row.get(0).and_then(|v| v.as_string()) {
                node_ids.push(format!("'{}'", id));
                
                // Build properties map with real data
                let mut properties = HashMap::new();
                
                // Add degree centrality
                if let Some(degree) = row.get(3).and_then(|v| v.to_f64()) {
                    properties.insert("degree_centrality".to_string(), serde_json::Value::from(degree));
                }
                
                // Add created_at timestamp
                if let Some(created) = row.get(4).and_then(|v| v.as_string()) {
                    properties.insert("created_at".to_string(), serde_json::Value::String(created.to_string()));
                }
                
                // Get summary from row index 5
                let summary = row.get(5).and_then(|v| v.as_string()).map(|s| s.to_string());
                
                // Add pagerank centrality from row index 6
                if let Some(pagerank) = row.get(6).and_then(|v| v.to_f64()) {
                    properties.insert("pagerank_centrality".to_string(), serde_json::Value::from(pagerank));
                }
                
                // Add betweenness centrality from row index 7
                if let Some(betweenness) = row.get(7).and_then(|v| v.to_f64()) {
                    properties.insert("betweenness_centrality".to_string(), serde_json::Value::from(betweenness));
                }
                
                // Add eigenvector centrality from row index 8
                if let Some(eigenvector) = row.get(8).and_then(|v| v.to_f64()) {
                    properties.insert("eigenvector_centrality".to_string(), serde_json::Value::from(eigenvector));
                }
                
                nodes.push(Node {
                    id: id.to_string(),
                    label: row.get(1).and_then(|v| v.as_string()).map_or("", |v| v).to_string(),
                    node_type: row.get(2).and_then(|v| v.as_string()).map_or("Unknown", |v| v).to_string(),
                    summary,
                    properties,
                });
            }
        }
        
        // Step 2: Load edges only for loaded nodes
        let edges_query = format!(
            "MATCH (n)-[r]->(m) WHERE n.uuid IN [{}] AND m.uuid IN [{}] RETURN n.uuid, type(r), m.uuid, r.weight LIMIT {}",
            node_ids.join(","),
            node_ids.join(","),
            edge_limit
        );
        
        let mut graph = state.client.select_graph(&graph_name);
        let mut edges_result = graph.query(&edges_query).execute().await?;
        let mut edges = Vec::new();
        
        while let Some(row) = edges_result.data.next() {
            edges.push(Edge {
                from: row.get(0).and_then(|v| v.as_string()).map_or("", |v| v).to_string(),
                to: row.get(2).and_then(|v| v.as_string()).map_or("", |v| v).to_string(),
                edge_type: row.get(1).and_then(|v| v.as_string()).map_or("", |v| v).to_string(),
                weight: row.get(3).and_then(|v| v.to_f64()).unwrap_or(1.0),
            });
        }
        
        let initial_data = GraphData { 
            nodes: nodes.clone(),
            edges: edges.clone(),
            stats: GraphStats {
                total_nodes: nodes.len(),
                total_edges: edges.len(),
                node_types: HashMap::new(),
                avg_degree: 0.0,
                max_degree: 0.0,
            }
        };
        
        duckdb_store.load_initial_data(initial_data.nodes.clone(), initial_data.edges.clone()).await?;
        info!("Initial data loaded: {} nodes, {} edges", initial_data.nodes.len(), initial_data.edges.len());
        
        // Initialize delta tracker with initial data
        let initial_delta = delta_tracker.compute_delta(initial_data.nodes.clone(), initial_data.edges.clone()).await;
        info!("Delta tracker initialized with sequence: {}", initial_delta.sequence);
        
        // Prerender Arrow format for faster initial load
        info!("Prerendering Arrow format for instant load...");
        if let (Ok(nodes_batch), Ok(edges_batch)) = (
            duckdb_store.get_nodes_as_arrow().await,
            duckdb_store.get_edges_as_arrow().await
        ) {
            if let (Ok(nodes_bytes), Ok(edges_bytes)) = (
                ArrowConverter::record_batch_to_bytes(&nodes_batch),
                ArrowConverter::record_batch_to_bytes(&edges_batch)
            ) {
                let nodes_bytes = Bytes::from(nodes_bytes);
                let edges_bytes = Bytes::from(edges_bytes);
                let cache = ArrowCache {
                    nodes_batch: nodes_batch.clone(),
                    edges_batch: edges_batch.clone(),
                    nodes_etag: ArrowCache::generate_etag(&nodes_bytes),
                    edges_etag: ArrowCache::generate_etag(&edges_bytes),
                    nodes_bytes,
                    edges_bytes,
                    timestamp: std::time::Instant::now(),
                };
                
                *state.arrow_cache.write().await = Some(cache);
                info!("Arrow cache prerendered in {:?}. Initial load will be instant!", prerender_start.elapsed());
            }
        }
    }
    
    // Spawn background task for processing updates
    let store_clone = duckdb_store.clone();
    let tx_clone = update_tx.clone();
    tokio::spawn(async move {
        let mut interval = tokio::time::interval(tokio::time::Duration::from_millis(100));
        loop {
            interval.tick().await;
            
            if let Ok(Some(update)) = store_clone.process_updates().await {
                let _ = tx_clone.send(update);
            }
        }
    });

    // Build router - cleaned up for React frontend only
    let app = Router::new()
        .route("/api/stats", get(get_stats))
        .route("/api/visualize", get(visualize))
        .route("/api/search", get(search))
        .route("/api/cache/clear", post(clear_cache))
        .route("/api/cache/stats", get(get_cache_stats))
        .route("/api/nodes/:id/summary", patch(update_node_summary))
        // DuckDB endpoints
        .route("/api/duckdb/info", get(get_duckdb_info))
        .route("/api/arrow/nodes", get(get_nodes_arrow))
        .route("/api/arrow/edges", get(get_edges_arrow))
        .route("/api/duckdb/stats", get(get_duckdb_stats))
        .route("/api/arrow/refresh", post(refresh_arrow_cache))
        // Centrality proxy endpoints
        .route("/api/centrality/health", get(proxy_centrality_health))
        .route("/api/centrality/stats", get(proxy_centrality_stats))
        .route("/api/centrality/pagerank", post(proxy_centrality_pagerank))
        .route("/api/centrality/degree", post(proxy_centrality_degree))
        .route("/api/centrality/betweenness", post(proxy_centrality_betweenness))
        .route("/api/centrality/all", post(proxy_centrality_all))
        .route("/ws", get(websocket_handler))
        .layer(CompressionLayer::new())  // Add gzip/brotli compression
        .layer(CorsLayer::permissive())
        .with_state(state);

    let addr = std::env::var("BIND_ADDR").unwrap_or_else(|_| "0.0.0.0:3000".to_string());
    info!("Server starting on {}", addr);
    
    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;
    
    Ok(())
}


async fn get_stats(State(state): State<AppState>) -> Result<Json<GraphStats>, StatusCode> {
    match calculate_graph_stats(&state.client, &state.graph_name).await {
        Ok(stats) => Ok(Json(stats)),
        Err(e) => {
            error!("Failed to get stats: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

async fn visualize(
    State(state): State<AppState>,
    Query(params): Query<QueryParams>,
) -> Result<Json<QueryResponse>, (StatusCode, Json<ErrorResponse>)> {
    let start = std::time::Instant::now();
    
    // Check cache first
    let cache_key = format!("{:?}", params);
    if let Some(cached) = state.graph_cache.get(&cache_key) {
        return Ok(Json(QueryResponse {
            data: cached.value().clone(),
            has_more: false,
            execution_time_ms: 0,
        }));
    }
    
    let limit = if params.query_type == "entire_graph" {
        params.limit.unwrap_or(50000).min(100000)  // Allow up to 100k for entire graph
    } else {
        params.limit.unwrap_or(200).min(1000)  // Keep existing limit for other queries
    };
    let offset = params.offset.unwrap_or(0);
    
    let query = build_query(&params.query_type, limit, offset, params.search.as_deref());
    
    match execute_graph_query(&state.client, &state.graph_name, &query).await {
        Ok(data) => {
            // Cache the result
            state.graph_cache.insert(cache_key, data.clone());
            
            let execution_time_ms = start.elapsed().as_millis();
            Ok(Json(QueryResponse {
                data,
                has_more: false, // TODO: Implement proper pagination check
                execution_time_ms,
            }))
        }
        Err(e) => {
            error!("Query failed: {}", e);
            Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ErrorResponse {
                    error: format!("Query failed: {}", e),
                }),
            ))
        }
    }
}

async fn search(
    State(state): State<AppState>,
    Query(params): Query<QueryParams>,
) -> Result<Json<QueryResponse>, (StatusCode, Json<ErrorResponse>)> {
    if params.search.is_some() {
        let new_params = QueryParams {
            query_type: "search".to_string(),
            limit: params.limit,
            offset: params.offset,
            search: params.search,
        };
        visualize(State(state), Query(new_params)).await
    } else {
        Err((
            StatusCode::BAD_REQUEST,
            Json(ErrorResponse {
                error: "Search term required".to_string(),
            }),
        ))
    }
}

async fn websocket_handler(
    ws: WebSocketUpgrade,
    State(state): State<AppState>,
) -> impl IntoResponse {
    ws.on_upgrade(move |socket| handle_socket(socket, state))
}

async fn handle_socket(mut socket: axum::extract::ws::WebSocket, state: AppState) {
    use axum::extract::ws::Message;
    
    info!("WebSocket connection established");
    
    // Subscribe to channels
    let mut update_rx = state.update_tx.subscribe();
    let mut delta_rx = state.delta_tx.subscribe();
    
    // Send initial connection confirmation with delta support flag
    let _ = socket.send(Message::Text(
        serde_json::to_string(&serde_json::json!({
            "type": "connected",
            "timestamp": std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_millis(),
            "features": {
                "delta_updates": true,
                "compression": true,
                "batch_updates": true
            }
        })).unwrap()
    )).await;
    
    // Track client preferences
    let mut use_deltas = false;
    
    // Handle incoming messages and broadcast updates
    loop {
        tokio::select! {
            // Handle incoming WebSocket messages
            Some(msg) = socket.recv() => {
                match msg {
                    Ok(Message::Text(text)) => {
                        // Parse client commands
                        if let Ok(cmd) = serde_json::from_str::<serde_json::Value>(&text) {
                            if let Some(cmd_type) = cmd.get("type").and_then(|t| t.as_str()) {
                                match cmd_type {
                                    "subscribe:deltas" => {
                                        use_deltas = true;
                                        let _ = socket.send(Message::Text(
                                            serde_json::to_string(&serde_json::json!({
                                                "type": "subscribed:deltas",
                                                "status": "ok"
                                            })).unwrap()
                                        )).await;
                                    }
                                    "unsubscribe:deltas" => {
                                        use_deltas = false;
                                    }
                                    "ping" => {
                                        let _ = socket.send(Message::Text(
                                            serde_json::to_string(&serde_json::json!({
                                                "type": "pong",
                                                "timestamp": std::time::SystemTime::now()
                                                    .duration_since(std::time::UNIX_EPOCH)
                                                    .unwrap()
                                                    .as_millis()
                                            })).unwrap()
                                        )).await;
                                    }
                                    _ => {
                                        debug!("Unknown command: {}", cmd_type);
                                    }
                                }
                            }
                        }
                    }
                    Ok(Message::Close(_)) => {
                        info!("WebSocket connection closed by client");
                        break;
                    }
                    Err(e) => {
                        error!("WebSocket error: {}", e);
                        break;
                    }
                    _ => {}
                }
            }
            
            // Broadcast delta updates (preferred)
            Ok(delta) = delta_rx.recv() => {
                if use_deltas {
                    let msg = serde_json::json!({
                        "type": "graph:delta",
                        "data": delta
                    });
                    
                    if let Err(e) = socket.send(Message::Text(serde_json::to_string(&msg).unwrap())).await {
                        error!("Failed to send delta: {}", e);
                        break;
                    }
                }
            }
            
            // Broadcast full updates (fallback)
            Ok(update) = update_rx.recv() => {
                if !use_deltas {
                    let msg = serde_json::json!({
                        "type": "graph:update",
                        "data": update
                    });
                    
                    if let Err(e) = socket.send(Message::Text(serde_json::to_string(&msg).unwrap())).await {
                        error!("Failed to send update: {}", e);
                        break;
                    }
                }
            }
        }
    }
    
    info!("WebSocket connection closed");
}

// Cache management endpoints
async fn clear_cache(State(state): State<AppState>) -> Result<Json<CacheResponse>, StatusCode> {
    let cleared_entries = state.graph_cache.len();
    state.graph_cache.clear();
    
    info!("Cache cleared: {} entries removed", cleared_entries);
    
    Ok(Json(CacheResponse {
        message: "Cache cleared successfully".to_string(),
        cleared_entries,
    }))
}

async fn get_cache_stats(State(state): State<AppState>) -> Result<Json<CacheStats>, StatusCode> {
    let total_entries = state.graph_cache.len();
    let cache_keys: Vec<String> = state.graph_cache.iter().map(|entry| entry.key().clone()).collect();
    
    Ok(Json(CacheStats {
        total_entries,
        cache_keys,
    }))
}

fn build_query(query_type: &str, limit: usize, offset: usize, search: Option<&str>) -> String {
    match query_type {
        "entire_graph" => {
            // For entire_graph, we need a special handling to get ALL nodes and edges
            // The regular OPTIONAL MATCH approach misses some edges
            // We'll handle this differently in execute_graph_query
            "ENTIRE_GRAPH_SPECIAL".to_string()
        },
        
        "high_degree" => format!(
            r#"
            MATCH (n) 
            WHERE EXISTS(n.degree_centrality) AND n.degree_centrality > 0.001
            WITH n ORDER BY n.degree_centrality DESC SKIP {} LIMIT {}
            MATCH (n)-[r]->(m) 
            WHERE EXISTS(m.degree_centrality) AND m.degree_centrality > 0.0005
            RETURN DISTINCT 
                n.uuid as source_id, n.name as source_name, 
                type(r) as rel_type, 
                m.uuid as target_id, m.name as target_name,
                COALESCE(n.type, labels(n)[0]) as source_label, COALESCE(m.type, labels(m)[0]) as target_label,
                n.degree_centrality as source_degree, m.degree_centrality as target_degree,
                properties(n) as source_props, properties(m) as target_props
            LIMIT {}
            "#,
            offset, limit / 2, limit
        ),
        
        "agents" => format!(
            r#"
            MATCH (n) 
            WHERE n.name CONTAINS 'Agent' 
            WITH n SKIP {} LIMIT {}
            MATCH (n)-[r]->(m)
            RETURN DISTINCT 
                n.uuid as source_id, n.name as source_name, 
                type(r) as rel_type, 
                m.uuid as target_id, m.name as target_name,
                COALESCE(n.type, labels(n)[0]) as source_label, COALESCE(m.type, labels(m)[0]) as target_label,
                n.degree_centrality as source_degree, m.degree_centrality as target_degree,
                properties(n) as source_props, properties(m) as target_props
            LIMIT {}
            "#,
            offset, limit / 3, limit
        ),
        
        "search" => {
            if let Some(term) = search {
                format!(
                    r#"
                    MATCH (n) 
                    WHERE n.name CONTAINS '{}'
                    WITH n LIMIT 1
                    MATCH (n)-[r*1..2]-(m)
                    RETURN DISTINCT 
                        n.uuid as source_id, n.name as source_name, 
                        type(r[0]) as rel_type, 
                        m.uuid as target_id, m.name as target_name,
                        COALESCE(n.type, labels(n)[0]) as source_label, COALESCE(m.type, labels(m)[0]) as target_label,
                        n.degree_centrality as source_degree, m.degree_centrality as target_degree,
                        properties(n) as source_props, properties(m) as target_props
                    LIMIT {}
                    "#,
                    term, limit
                )
            } else {
                build_query("high_degree", limit, offset, None)
            }
        }
        
        _ => build_query("high_degree", limit, offset, None),
    }
}

async fn execute_graph_query(client: &FalkorAsyncClient, graph_name: &str, query: &str) -> anyhow::Result<GraphData> {
    let mut nodes_map: HashMap<String, Node> = HashMap::new();
    let mut edges = Vec::new();
    
    // Special handling for entire_graph query
    if query == "ENTIRE_GRAPH_SPECIAL" {
        // Query 1: Get all nodes
        let nodes_query = r#"
            MATCH (n)
            RETURN 
                n.uuid as id,
                n.name as name,
                COALESCE(n.type, labels(n)[0]) as node_type,
                COALESCE(n.degree_centrality, 0) as degree_centrality,
                properties(n) as props
        "#;
        
        let mut graph = client.select_graph(graph_name);
        let mut nodes_result = graph.query(nodes_query).execute().await?;
        
        // Process all nodes
        while let Some(row) = nodes_result.data.next() {
            if row.len() >= 5 {
                let node_id = value_to_string(&row[0]);
                let node_name = value_to_string(&row[1]);
                let node_type = value_to_string(&row[2]);
                let degree_centrality = value_to_f64(&row[3]);
                let mut node_props = value_to_properties(&row[4]);
                
                // Ensure required properties
                node_props.insert("name".to_string(), serde_json::Value::String(node_name.clone()));
                if !node_props.contains_key("degree_centrality") {
                    node_props.insert("degree_centrality".to_string(), serde_json::json!(degree_centrality));
                }
                node_props.insert("type".to_string(), serde_json::Value::String(node_type.clone()));
                
                // Extract summary
                let summary = node_props.get("summary")
                    .or_else(|| node_props.get("content"))
                    .or_else(|| node_props.get("source_description"))
                    .and_then(|v| match v {
                        serde_json::Value::String(s) => Some(s.clone()),
                        _ => v.as_str().map(|s| s.to_string())
                    });
                
                nodes_map.insert(node_id.clone(), Node {
                    id: node_id,
                    label: truncate_string(&node_name, 50),
                    node_type,
                    summary,
                    properties: node_props,
                });
            }
        }
        
        // Query 2: Get all edges
        let edges_query = r#"
            MATCH (n)-[r]->(m)
            RETURN 
                n.uuid as source_id,
                m.uuid as target_id,
                type(r) as rel_type
        "#;
        
        let mut graph = client.select_graph(graph_name);
        let mut edges_result = graph.query(edges_query).execute().await?;
        
        // Process all edges
        while let Some(row) = edges_result.data.next() {
            if row.len() >= 3 {
                let source_id = value_to_string(&row[0]);
                let target_id = value_to_string(&row[1]);
                let rel_type = value_to_string(&row[2]);
                
                edges.push(Edge {
                    from: source_id,
                    to: target_id,
                    edge_type: rel_type,
                    weight: 1.0,
                });
            }
        }
    } else {
        // Regular query processing
        let mut graph = client.select_graph(graph_name);
        let mut result_set = graph.query(query).execute().await?;
    
        // Process results
        while let Some(row) = result_set.data.next() {
            if row.len() >= 9 {
            // Process source node (always present)
            let source_id = value_to_string(&row[0]);
            let source_name = value_to_string(&row[1]);
            let source_label = value_to_string(&row[5]);
            let source_degree = value_to_f64(&row[7]);
            let source_props = if row.len() > 9 { value_to_properties(&row[9]) } else { HashMap::new() };
            
            if !nodes_map.contains_key(&source_id) {
                let mut node_props = source_props.clone();
                // Ensure name is in properties for Cosmograph
                node_props.insert("name".to_string(), serde_json::Value::String(source_name.clone()));
                // Only add degree_centrality if not already in properties
                if !node_props.contains_key("degree_centrality") {
                    node_props.insert("degree_centrality".to_string(), serde_json::json!(source_degree));
                }
                // Add node type for color mapping
                node_props.insert("type".to_string(), serde_json::Value::String(source_label.clone()));
                
                // Extract summary from content, source_description, or summary field
                let summary = node_props.get("summary")
                    .or_else(|| node_props.get("content"))
                    .or_else(|| node_props.get("source_description"))
                    .and_then(|v| match v {
                        serde_json::Value::String(s) => Some(s.clone()),
                        _ => v.as_str().map(|s| s.to_string())
                    });
                
                nodes_map.insert(source_id.clone(), Node {
                    id: source_id.clone(),
                    label: truncate_string(&source_name, 50),
                    node_type: source_label.clone(),
                    summary,
                    properties: node_props,
                });
            }
            
            // Check if there's a relationship (OPTIONAL MATCH may return null)
            let rel_type = value_to_string(&row[2]);
            let target_id = value_to_string(&row[3]);
            
            // Only process relationship if it exists (not null/empty)
            if !rel_type.is_empty() && !target_id.is_empty() {
                // Process target node
                let target_name = value_to_string(&row[4]);
                let target_label = value_to_string(&row[6]);
                let target_degree = value_to_f64(&row[8]);
                let target_props = if row.len() > 10 { value_to_properties(&row[10]) } else { HashMap::new() };
                
                if !nodes_map.contains_key(&target_id) {
                    let mut node_props = target_props.clone();
                    // Ensure name is in properties for Cosmograph
                    node_props.insert("name".to_string(), serde_json::Value::String(target_name.clone()));
                    // Only add degree_centrality if not already in properties
                    if !node_props.contains_key("degree_centrality") {
                        node_props.insert("degree_centrality".to_string(), serde_json::json!(target_degree));
                    }
                    // Add node type for color mapping
                    node_props.insert("type".to_string(), serde_json::Value::String(target_label.clone()));
                    
                    // Extract summary from content, source_description, or summary field
                    let summary = node_props.get("summary")
                        .or_else(|| node_props.get("content"))
                        .or_else(|| node_props.get("source_description"))
                        .and_then(|v| match v {
                            serde_json::Value::String(s) => Some(s.clone()),
                            _ => v.as_str().map(|s| s.to_string())
                        });
                    
                    nodes_map.insert(target_id.clone(), Node {
                        id: target_id.clone(),
                        label: truncate_string(&target_name, 50),
                        node_type: target_label.clone(),
                        summary,
                        properties: node_props,
                    });
                }
                
                // Add edge
                edges.push(Edge {
                    from: source_id,
                    to: target_id,
                    edge_type: rel_type,
                    weight: 1.0,
                });
            }
        }
    }
    } // Close the else block
    
    let nodes: Vec<Node> = nodes_map.into_values().collect();
    
    // Calculate stats
    let stats = GraphStats {
        total_nodes: nodes.len(),
        total_edges: edges.len(),
        node_types: nodes.iter()
            .fold(HashMap::new(), |mut acc, node| {
                *acc.entry(node.node_type.clone()).or_insert(0) += 1;
                acc
            }),
        avg_degree: edges.len() as f64 * 2.0 / nodes.len().max(1) as f64,
        max_degree: nodes.iter()
            .map(|n| n.properties.get("degree_centrality").and_then(|v| v.as_f64()).unwrap_or(0.0))
            .fold(0.0, f64::max),
    };
    
    Ok(GraphData { nodes, edges, stats })
}

async fn calculate_graph_stats(client: &FalkorAsyncClient, graph_name: &str) -> anyhow::Result<GraphStats> {
    let node_count_query = "MATCH (n) RETURN count(n) as count";
    let edge_count_query = "MATCH ()-[r]->() RETURN count(r) as count";
    let type_dist_query = "MATCH (n) RETURN COALESCE(n.type, labels(n)[0]) as type, count(n) as count";
    
    let mut graph = client.select_graph(graph_name);
    let mut node_result = graph.query(node_count_query).execute().await?;
    
    let mut graph = client.select_graph(graph_name);
    let mut edge_result = graph.query(edge_count_query).execute().await?;
    
    let mut graph = client.select_graph(graph_name);
    let mut type_result = graph.query(type_dist_query).execute().await?;
    
    let total_nodes = if let Some(row) = node_result.data.next() {
        if let Some(value) = row.get(0) {
            value_to_usize(value)
        } else { 0 }
    } else { 0 };
    
    let total_edges = if let Some(row) = edge_result.data.next() {
        if let Some(value) = row.get(0) {
            value_to_usize(value)
        } else { 0 }
    } else { 0 };
    
    let mut node_types = HashMap::new();
    while let Some(row) = type_result.data.next() {
        if row.len() >= 2 {
            let node_type = value_to_string(&row[0]);
            let count = value_to_usize(&row[1]);
            node_types.insert(node_type, count);
        }
    }
    
    Ok(GraphStats {
        total_nodes,
        total_edges,
        node_types,
        avg_degree: if total_nodes > 0 { 
            (total_edges * 2) as f64 / total_nodes as f64 
        } else { 
            0.0 
        },
        max_degree: 0.0, // TODO: Calculate actual max degree
    })
}

// Helper functions to convert FalkorValue to primitive types
fn value_to_string(value: &FalkorValue) -> String {
    match value {
        FalkorValue::String(s) => s.clone(),
        FalkorValue::I64(i) => i.to_string(),
        FalkorValue::F64(f) => f.to_string(),
        FalkorValue::Bool(b) => b.to_string(),
        FalkorValue::None => String::new(),
        _ => format!("{:?}", value),
    }
}

fn value_to_f64(value: &FalkorValue) -> f64 {
    match value {
        FalkorValue::F64(f) => *f,
        FalkorValue::I64(i) => *i as f64,
        FalkorValue::String(s) => s.parse::<f64>().unwrap_or(0.0),
        _ => 0.0,
    }
}

fn value_to_usize(value: &FalkorValue) -> usize {
    match value {
        FalkorValue::I64(i) => *i as usize,
        FalkorValue::F64(f) => *f as usize,
        FalkorValue::String(s) => s.parse::<usize>().unwrap_or(0),
        _ => 0,
    }
}


fn truncate_string(s: &str, max_len: usize) -> String {
    if s.len() <= max_len {
        s.to_string()
    } else {
        format!("{}...", &s[..max_len-3])
    }
}

fn value_to_properties(value: &FalkorValue) -> HashMap<String, serde_json::Value> {
    match value {
        FalkorValue::Map(map) => {
            let mut props = HashMap::new();
            for (key, val) in map {
                props.insert(key.clone(), falkor_value_to_json(val));
            }
            props
        }
        _ => HashMap::new(),
    }
}

fn falkor_value_to_json(value: &FalkorValue) -> serde_json::Value {
    match value {
        FalkorValue::String(s) => serde_json::Value::String(s.clone()),
        FalkorValue::I64(i) => serde_json::Value::Number(serde_json::Number::from(*i)),
        FalkorValue::F64(f) => serde_json::json!(*f),
        FalkorValue::Bool(b) => serde_json::Value::Bool(*b),
        FalkorValue::None => serde_json::Value::Null,
        FalkorValue::Array(arr) => {
            serde_json::Value::Array(arr.iter().map(falkor_value_to_json).collect())
        }
        FalkorValue::Map(map) => {
            let mut obj = serde_json::Map::new();
            for (k, v) in map {
                obj.insert(k.clone(), falkor_value_to_json(v));
            }
            serde_json::Value::Object(obj)
        }
        _ => serde_json::Value::String(format!("{:?}", value)),
    }
}

// Helper function to escape strings for Cypher queries
fn escape_cypher_string(s: &str) -> String {
    s.replace('\\', "\\\\")
        .replace('\'', "\\'")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
        .replace('\t', "\\t")
}

// ==================== Centrality Proxy Handlers ====================

async fn proxy_centrality_health(State(state): State<AppState>) -> Response {
    let url = format!("{}/health", state.centrality_url);
    match state.http_client.get(&url).send().await {
        Ok(resp) => {
            let status = StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::OK);
            let body = resp.bytes().await.unwrap_or_default();
            Response::builder()
                .status(status)
                .header("content-type", "application/json")
                .body(Body::from(body))
                .unwrap()
        }
        Err(e) => {
            error!("Failed to proxy health check: {}", e);
            (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({
                    "error": "Centrality service unavailable",
                    "details": e.to_string()
                }))
            ).into_response()
        }
    }
}

async fn proxy_centrality_stats(State(state): State<AppState>) -> Response {
    let url = format!("{}/stats", state.centrality_url);
    match state.http_client.get(&url).send().await {
        Ok(resp) => {
            let status = StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::OK);
            let body = resp.bytes().await.unwrap_or_default();
            Response::builder()
                .status(status)
                .header("content-type", "application/json")
                .body(Body::from(body))
                .unwrap()
        }
        Err(e) => {
            error!("Failed to proxy stats: {}", e);
            (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({
                    "error": "Centrality service unavailable",
                    "details": e.to_string()
                }))
            ).into_response()
        }
    }
}

async fn proxy_centrality_pagerank(
    State(state): State<AppState>,
    Json(payload): Json<serde_json::Value>,
) -> Response {
    let url = format!("{}/centrality/pagerank", state.centrality_url);
    match state.http_client.post(&url).json(&payload).send().await {
        Ok(resp) => {
            let status = StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::OK);
            let body = resp.bytes().await.unwrap_or_default();
            Response::builder()
                .status(status)
                .header("content-type", "application/json")
                .body(Body::from(body))
                .unwrap()
        }
        Err(e) => {
            error!("Failed to proxy PageRank: {}", e);
            (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({
                    "error": "Centrality service unavailable",
                    "details": e.to_string()
                }))
            ).into_response()
        }
    }
}

async fn proxy_centrality_degree(
    State(state): State<AppState>,
    Json(payload): Json<serde_json::Value>,
) -> Response {
    let url = format!("{}/centrality/degree", state.centrality_url);
    match state.http_client.post(&url).json(&payload).send().await {
        Ok(resp) => {
            let status = StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::OK);
            let body = resp.bytes().await.unwrap_or_default();
            Response::builder()
                .status(status)
                .header("content-type", "application/json")
                .body(Body::from(body))
                .unwrap()
        }
        Err(e) => {
            error!("Failed to proxy degree centrality: {}", e);
            (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({
                    "error": "Centrality service unavailable",
                    "details": e.to_string()
                }))
            ).into_response()
        }
    }
}

async fn proxy_centrality_betweenness(
    State(state): State<AppState>,
    Json(payload): Json<serde_json::Value>,
) -> Response {
    let url = format!("{}/centrality/betweenness", state.centrality_url);
    match state.http_client.post(&url).json(&payload).send().await {
        Ok(resp) => {
            let status = StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::OK);
            let body = resp.bytes().await.unwrap_or_default();
            Response::builder()
                .status(status)
                .header("content-type", "application/json")
                .body(Body::from(body))
                .unwrap()
        }
        Err(e) => {
            error!("Failed to proxy betweenness centrality: {}", e);
            (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({
                    "error": "Centrality service unavailable",
                    "details": e.to_string()
                }))
            ).into_response()
        }
    }
}

async fn proxy_centrality_all(
    State(state): State<AppState>,
    Json(payload): Json<serde_json::Value>,
) -> Response {
    let url = format!("{}/centrality/all", state.centrality_url);
    match state.http_client.post(&url).json(&payload).send().await {
        Ok(resp) => {
            let status = StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::OK);
            let body = resp.bytes().await.unwrap_or_default();
            Response::builder()
                .status(status)
                .header("content-type", "application/json")
                .body(Body::from(body))
                .unwrap()
        }
        Err(e) => {
            error!("Failed to proxy all centralities: {}", e);
            (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({
                    "error": "Centrality service unavailable",
                    "details": e.to_string()
                }))
            ).into_response()
        }
    }
}

async fn update_node_summary(
    Path(node_id): Path<String>,
    State(state): State<AppState>,
    Json(request): Json<UpdateSummaryRequest>,
) -> Result<Json<NodeUpdateResponse>, (StatusCode, Json<ErrorResponse>)> {
    // Update the node summary in FalkorDB
    let query = format!(
        r#"
        MATCH (n {{uuid: '{}'}})
        SET n.summary = '{}'
        RETURN n.uuid as uuid, n.name as name, n.summary as summary
        "#,
        escape_cypher_string(&node_id),
        escape_cypher_string(&request.summary)
    );
    
    let mut graph = state.client.select_graph(&state.graph_name);
    match graph.query(&query).execute().await {
        Ok(mut result) => {
            if let Some(row) = result.data.next() {
                if row.len() >= 3 {
                    let uuid = value_to_string(&row[0]);
                    let name = value_to_string(&row[1]);
                    let summary = value_to_string(&row[2]);
                    
                    // Clear cache to ensure fresh data
                    state.graph_cache.clear();
                    
                    Ok(Json(NodeUpdateResponse {
                        uuid,
                        name,
                        summary,
                    }))
                } else {
                    Err((
                        StatusCode::NOT_FOUND,
                        Json(ErrorResponse {
                            error: format!("Node with id {} not found", node_id),
                        }),
                    ))
                }
            } else {
                Err((
                    StatusCode::NOT_FOUND,
                    Json(ErrorResponse {
                        error: format!("Node with id {} not found", node_id),
                    }),
                ))
            }
        }
        Err(e) => {
            error!("Failed to update node summary: {}", e);
            Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ErrorResponse {
                    error: format!("Failed to update summary: {}", e),
                }),
            ))
        }
    }
}

// DuckDB endpoint handlers
async fn get_duckdb_info(State(_state): State<AppState>) -> Result<Json<serde_json::Value>, StatusCode> {
    Ok(Json(serde_json::json!({
        "status": "ready",
        "type": "in-memory",
        "tables": ["nodes", "edges"],
        "features": {
            "arrow_export": true,
            "incremental_updates": true,
            "real_time_sync": true
        }
    })))
}

async fn get_nodes_arrow(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Response<Body>, (StatusCode, Json<ErrorResponse>)> {
    // Check cache first
    let cache = state.arrow_cache.read().await;
    if let Some(ref cached) = *cache {
        // Check if client has the same version (ETag)
        if let Some(if_none_match) = headers.get(header::IF_NONE_MATCH) {
            if let Ok(client_etag) = if_none_match.to_str() {
                if client_etag == cached.nodes_etag {
                    debug!("Client has current version (ETag match)");
                    return Ok(Response::builder()
                        .status(StatusCode::NOT_MODIFIED)
                        .header(header::ETAG, &cached.nodes_etag)
                        .header("Cache-Control", "public, max-age=300")
                        .body(Body::empty())
                        .unwrap());
                }
            }
        }
        
        // Cache is valid for 30 seconds
        if cached.timestamp.elapsed() < std::time::Duration::from_secs(30) {
            debug!("Serving nodes from Arrow cache");
            return Ok(Response::builder()
                .status(StatusCode::OK)
                .header(header::CONTENT_TYPE, "application/vnd.apache.arrow.stream")
                .header("X-Arrow-Schema", "nodes")
                .header("X-Cache-Hit", "true")
                .header(header::ETAG, &cached.nodes_etag)
                .header("Cache-Control", "public, max-age=300")
                .header("Vary", "Accept-Encoding")
                .body(Body::from(cached.nodes_bytes.clone()))
                .unwrap());
        }
    }
    drop(cache); // Release read lock

    match state.duckdb_store.get_nodes_as_arrow().await {
        Ok(batch) => {
            match ArrowConverter::record_batch_to_bytes(&batch) {
                Ok(bytes) => {
                    let bytes = Bytes::from(bytes);
                    
                    // Generate ETag for new data
                    let etag = ArrowCache::generate_etag(&bytes);
                    
                    // Update cache if we have edges too
                    let mut cache = state.arrow_cache.write().await;
                    if let Some(cached) = cache.as_mut() {
                        cached.nodes_batch = batch;
                        cached.nodes_bytes = bytes.clone();
                        cached.nodes_etag = etag.clone();
                        cached.timestamp = std::time::Instant::now();
                    }
                    
                    // Note: Compression is handled by CompressionLayer middleware
                    Ok(Response::builder()
                        .status(StatusCode::OK)
                        .header(header::CONTENT_TYPE, "application/vnd.apache.arrow.stream")
                        .header("X-Arrow-Schema", "nodes")
                        .header("X-Cache-Hit", "false")
                        .header(header::ETAG, etag)
                        .header("Cache-Control", "public, max-age=300")
                        .header("Vary", "Accept-Encoding")
                        .body(Body::from(bytes))
                        .unwrap())
                }
                Err(e) => {
                    error!("Failed to convert nodes to Arrow: {}", e);
                    Err((
                        StatusCode::INTERNAL_SERVER_ERROR,
                        Json(ErrorResponse {
                            error: format!("Failed to convert to Arrow: {}", e),
                        }),
                    ))
                }
            }
        }
        Err(e) => {
            error!("Failed to get nodes from DuckDB: {}", e);
            Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ErrorResponse {
                    error: format!("Failed to retrieve nodes: {}", e),
                }),
            ))
        }
    }
}

async fn get_edges_arrow(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Response<Body>, (StatusCode, Json<ErrorResponse>)> {
    // Check cache first
    let cache = state.arrow_cache.read().await;
    if let Some(ref cached) = *cache {
        // Check if client has the same version (ETag)
        if let Some(if_none_match) = headers.get(header::IF_NONE_MATCH) {
            if let Ok(client_etag) = if_none_match.to_str() {
                if client_etag == cached.edges_etag {
                    debug!("Client has current version (ETag match)");
                    return Ok(Response::builder()
                        .status(StatusCode::NOT_MODIFIED)
                        .header(header::ETAG, &cached.edges_etag)
                        .header("Cache-Control", "public, max-age=300")
                        .body(Body::empty())
                        .unwrap());
                }
            }
        }
        
        // Cache is valid for 30 seconds
        if cached.timestamp.elapsed() < std::time::Duration::from_secs(30) {
            debug!("Serving edges from Arrow cache");
            return Ok(Response::builder()
                .status(StatusCode::OK)
                .header(header::CONTENT_TYPE, "application/vnd.apache.arrow.stream")
                .header("X-Arrow-Schema", "edges")
                .header("X-Cache-Hit", "true")
                .header(header::ETAG, &cached.edges_etag)
                .header("Cache-Control", "public, max-age=300")
                .header("Vary", "Accept-Encoding")
                .body(Body::from(cached.edges_bytes.clone()))
                .unwrap());
        }
    }
    drop(cache); // Release read lock

    match state.duckdb_store.get_edges_as_arrow().await {
        Ok(batch) => {
            match ArrowConverter::record_batch_to_bytes(&batch) {
                Ok(bytes) => {
                    let bytes = Bytes::from(bytes);
                    
                    // Generate ETag for new data
                    let etag = ArrowCache::generate_etag(&bytes);
                    
                    // Update cache if we have nodes too
                    let mut cache = state.arrow_cache.write().await;
                    if let Some(cached) = cache.as_mut() {
                        cached.edges_batch = batch;
                        cached.edges_bytes = bytes.clone();
                        cached.edges_etag = etag.clone();
                        cached.timestamp = std::time::Instant::now();
                    }
                    
                    // Note: Compression is handled by CompressionLayer middleware
                    Ok(Response::builder()
                        .status(StatusCode::OK)
                        .header(header::CONTENT_TYPE, "application/vnd.apache.arrow.stream")
                        .header("X-Arrow-Schema", "edges")
                        .header("X-Cache-Hit", "false")
                        .header(header::ETAG, etag)
                        .header("Cache-Control", "public, max-age=300")
                        .header("Vary", "Accept-Encoding")
                        .body(Body::from(bytes))
                        .unwrap())
                }
                Err(e) => {
                    error!("Failed to convert edges to Arrow: {}", e);
                    Err((
                        StatusCode::INTERNAL_SERVER_ERROR,
                        Json(ErrorResponse {
                            error: format!("Failed to convert to Arrow: {}", e),
                        }),
                    ))
                }
            }
        }
        Err(e) => {
            error!("Failed to get edges from DuckDB: {}", e);
            Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ErrorResponse {
                    error: format!("Failed to retrieve edges: {}", e),
                }),
            ))
        }
    }
}

async fn get_duckdb_stats(State(state): State<AppState>) -> Result<Json<serde_json::Value>, StatusCode> {
    match state.duckdb_store.get_stats().await {
        Ok((node_count, edge_count)) => {
            Ok(Json(serde_json::json!({
                "nodes": node_count,
                "edges": edge_count,
                "last_updated": std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_millis()
            })))
        }
        Err(e) => {
            error!("Failed to get DuckDB stats: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

async fn refresh_arrow_cache(State(state): State<AppState>) -> Result<Json<serde_json::Value>, StatusCode> {
    info!("Refreshing Arrow cache...");
    let start = std::time::Instant::now();
    
    match (
        state.duckdb_store.get_nodes_as_arrow().await,
        state.duckdb_store.get_edges_as_arrow().await
    ) {
        (Ok(nodes_batch), Ok(edges_batch)) => {
            match (
                ArrowConverter::record_batch_to_bytes(&nodes_batch),
                ArrowConverter::record_batch_to_bytes(&edges_batch)
            ) {
                (Ok(nodes_bytes), Ok(edges_bytes)) => {
                    let nodes_bytes = Bytes::from(nodes_bytes);
                    let edges_bytes = Bytes::from(edges_bytes);
                    let cache = ArrowCache {
                        nodes_batch,
                        edges_batch,
                        nodes_etag: ArrowCache::generate_etag(&nodes_bytes),
                        edges_etag: ArrowCache::generate_etag(&edges_bytes),
                        nodes_bytes,
                        edges_bytes,
                        timestamp: std::time::Instant::now(),
                    };
                    
                    *state.arrow_cache.write().await = Some(cache);
                    let elapsed = start.elapsed();
                    info!("Arrow cache refreshed in {:?}", elapsed);
                    
                    Ok(Json(serde_json::json!({
                        "status": "success",
                        "refresh_time_ms": elapsed.as_millis(),
                        "timestamp": std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .unwrap()
                            .as_millis()
                    })))
                }
                _ => {
                    error!("Failed to convert to Arrow format");
                    Err(StatusCode::INTERNAL_SERVER_ERROR)
                }
            }
        }
        _ => {
            error!("Failed to get data from DuckDB");
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

// Force rebuild for CI/CD workflow
// Trigger rebuild Wed Aug  6 01:14:42 AM EDT 2025
