use axum::{
    extract::{Query, State, WebSocketUpgrade},
    http::{StatusCode, header, HeaderMap, HeaderValue},
    response::{Html, IntoResponse, Json},
    routing::get,
    Router,
};
use dashmap::DashMap;
use falkordb::{FalkorClientBuilder, FalkorConnectionInfo, FalkorValue, FalkorAsyncClient};
use serde::{Deserialize, Serialize};
use std::{collections::HashMap, sync::Arc};
use tower_http::cors::CorsLayer;
use tower_http::services::ServeDir;
use tracing::{error, info};

#[derive(Clone)]
struct AppState {
    client: Arc<FalkorAsyncClient>,
    graph_name: String,
    graph_cache: Arc<DashMap<String, GraphData>>,
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
    size: f64,
    color: String,
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
    
    let connection_string = format!("falkor://{}:{}", falkor_host, falkor_port);
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
    
    let state = AppState {
        client: Arc::new(client),
        graph_name,
        graph_cache: Arc::new(DashMap::new()),
    };

    // Build router
    let app = Router::new()
        .route("/", get(index))
        .route("/cosmos", get(cosmos))
        .route("/cosmos-test", get(cosmos_test))
        .route("/cosmograph", get(cosmograph))
        .route("/api/stats", get(get_stats))
        .route("/api/visualize", get(visualize))
        .route("/api/search", get(search))
        .route("/ws", get(websocket_handler))
        .nest_service("/vendor", ServeDir::new("/static/vendor"))
        .layer(CorsLayer::permissive())
        .with_state(state);

    let addr = "0.0.0.0:3000";
    info!("Server starting on {}", addr);
    
    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;
    
    Ok(())
}

async fn index() -> Result<impl IntoResponse, StatusCode> {
    match tokio::fs::read_to_string("/static/index.html").await {
        Ok(content) => {
            let mut headers = HeaderMap::new();
            headers.insert(header::CACHE_CONTROL, HeaderValue::from_static("no-cache, no-store, must-revalidate"));
            headers.insert(header::PRAGMA, HeaderValue::from_static("no-cache"));
            headers.insert(header::EXPIRES, HeaderValue::from_static("0"));
            Ok((headers, Html(content)))
        },
        Err(_) => Err(StatusCode::INTERNAL_SERVER_ERROR),
    }
}

async fn cosmos() -> Result<impl IntoResponse, StatusCode> {
    match tokio::fs::read_to_string("/static/cosmos.html").await {
        Ok(content) => {
            let mut headers = HeaderMap::new();
            headers.insert(header::CACHE_CONTROL, HeaderValue::from_static("no-cache, no-store, must-revalidate"));
            headers.insert(header::PRAGMA, HeaderValue::from_static("no-cache"));
            headers.insert(header::EXPIRES, HeaderValue::from_static("0"));
            Ok((headers, Html(content)))
        },
        Err(_) => Err(StatusCode::INTERNAL_SERVER_ERROR),
    }
}

async fn cosmos_test() -> Result<impl IntoResponse, StatusCode> {
    match tokio::fs::read_to_string("/static/cosmos-test.html").await {
        Ok(content) => {
            let mut headers = HeaderMap::new();
            headers.insert(header::CACHE_CONTROL, HeaderValue::from_static("no-cache, no-store, must-revalidate"));
            headers.insert(header::PRAGMA, HeaderValue::from_static("no-cache"));
            headers.insert(header::EXPIRES, HeaderValue::from_static("0"));
            Ok((headers, Html(content)))
        },
        Err(_) => Err(StatusCode::INTERNAL_SERVER_ERROR),
    }
}

async fn cosmograph() -> Result<impl IntoResponse, StatusCode> {
    match tokio::fs::read_to_string("/static/cosmograph.html").await {
        Ok(content) => {
            let mut headers = HeaderMap::new();
            headers.insert(header::CACHE_CONTROL, HeaderValue::from_static("no-cache, no-store, must-revalidate"));
            headers.insert(header::PRAGMA, HeaderValue::from_static("no-cache"));
            headers.insert(header::EXPIRES, HeaderValue::from_static("0"));
            Ok((headers, Html(content)))
        },
        Err(_) => Err(StatusCode::INTERNAL_SERVER_ERROR),
    }
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

async fn handle_socket(_socket: axum::extract::ws::WebSocket, _state: AppState) {
    // TODO: Implement WebSocket streaming for large graph updates
    info!("WebSocket connection established");
}

fn build_query(query_type: &str, limit: usize, offset: usize, search: Option<&str>) -> String {
    match query_type {
        "entire_graph" => format!(
            r#"
            MATCH (n)-[r]-(m)
            RETURN DISTINCT 
                n.uuid as source_id, n.name as source_name, 
                type(r) as rel_type, 
                m.uuid as target_id, m.name as target_name,
                labels(n)[0] as source_label, labels(m)[0] as target_label,
                COALESCE(n.degree_centrality, 0) as source_degree, 
                COALESCE(m.degree_centrality, 0) as target_degree,
                properties(n) as source_props, properties(m) as target_props
            LIMIT {}
            "#,
            limit
        ),
        
        "high_degree" => format!(
            r#"
            MATCH (n) 
            WHERE EXISTS(n.degree_centrality) AND n.degree_centrality > 20
            WITH n ORDER BY n.degree_centrality DESC SKIP {} LIMIT {}
            MATCH (n)-[r]-(m) 
            WHERE EXISTS(m.degree_centrality) AND m.degree_centrality > 10
            RETURN DISTINCT 
                n.uuid as source_id, n.name as source_name, 
                type(r) as rel_type, 
                m.uuid as target_id, m.name as target_name,
                labels(n)[0] as source_label, labels(m)[0] as target_label,
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
            MATCH (n)-[r]-(m)
            RETURN DISTINCT 
                n.uuid as source_id, n.name as source_name, 
                type(r) as rel_type, 
                m.uuid as target_id, m.name as target_name,
                labels(n)[0] as source_label, labels(m)[0] as target_label,
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
                        labels(n)[0] as source_label, labels(m)[0] as target_label,
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
    let mut graph = client.select_graph(graph_name);
    let mut result_set = graph.query(query).execute().await?;
    
    let mut nodes_map: HashMap<String, Node> = HashMap::new();
    let mut edges = Vec::new();
    
    // Color mapping
    let color_map: HashMap<&str, &str> = [
        ("Entity", "#ff6b6b"),
        ("Episodic", "#4ecdc4"),
        ("Agent", "#ffe66d"),
    ].iter().cloned().collect();
    
    // Process results
    while let Some(row) = result_set.data.next() {
        if row.len() >= 9 {
            // Process source node
            let source_id = value_to_string(&row[0]);
            let source_name = value_to_string(&row[1]);
            let source_label = value_to_string(&row[5]);
            let source_degree = value_to_f64(&row[7]);
            let source_props = if row.len() > 9 { value_to_properties(&row[9]) } else { HashMap::new() };
            
            if !nodes_map.contains_key(&source_id) {
                let mut node_props = source_props.clone();
                // Ensure name is in properties
                node_props.insert("name".to_string(), serde_json::Value::String(source_name.clone()));
                
                nodes_map.insert(source_id.clone(), Node {
                    id: source_id.clone(),
                    label: truncate_string(&source_name, 50),
                    node_type: source_label.clone(),
                    size: calculate_node_size(source_degree),
                    color: color_map.get(source_label.as_str())
                        .unwrap_or(&"#95e1d3")
                        .to_string(),
                    properties: node_props,
                });
            }
            
            // Process target node
            let target_id = value_to_string(&row[3]);
            let target_name = value_to_string(&row[4]);
            let target_label = value_to_string(&row[6]);
            let target_degree = value_to_f64(&row[8]);
            let target_props = if row.len() > 10 { value_to_properties(&row[10]) } else { HashMap::new() };
            
            if !nodes_map.contains_key(&target_id) {
                let mut node_props = target_props.clone();
                // Ensure name is in properties
                node_props.insert("name".to_string(), serde_json::Value::String(target_name.clone()));
                
                nodes_map.insert(target_id.clone(), Node {
                    id: target_id.clone(),
                    label: truncate_string(&target_name, 50),
                    node_type: target_label.clone(),
                    size: calculate_node_size(target_degree),
                    color: color_map.get(target_label.as_str())
                        .unwrap_or(&"#95e1d3")
                        .to_string(),
                    properties: node_props,
                });
            }
            
            // Add edge
            let rel_type = value_to_string(&row[2]);
            edges.push(Edge {
                from: source_id,
                to: target_id,
                edge_type: rel_type,
                weight: 1.0,
            });
        }
    }
    
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
            .map(|n| n.size)
            .fold(0.0, f64::max),
    };
    
    Ok(GraphData { nodes, edges, stats })
}

async fn calculate_graph_stats(client: &FalkorAsyncClient, graph_name: &str) -> anyhow::Result<GraphStats> {
    let node_count_query = "MATCH (n) RETURN count(n) as count";
    let edge_count_query = "MATCH ()-[r]->() RETURN count(r) as count";
    let type_dist_query = "MATCH (n) RETURN labels(n)[0] as type, count(n) as count";
    
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

fn calculate_node_size(degree: f64) -> f64 {
    (15.0 + degree * 0.3).min(50.0)
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