use crate::algorithms::{
    calculate_all_centralities, calculate_betweenness_centrality, calculate_degree_centrality,
    calculate_pagerank,
};
use crate::client::FalkorClient;
use crate::error::{CentralityError, Result};
use crate::models::{
    AllCentralitiesRequest, AllCentralitiesResponse, BetweennessRequest, CentralityResponse,
    DatabaseConfig, DegreeRequest, PageRankRequest, SingleNodeRequest, SingleNodeResponse,
};
use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::{IntoResponse, Json},
    routing::{get, post},
    Router,
};
use serde_json::json;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;
use tower_http::cors::CorsLayer;
use tracing::{error, info};

/// Application state containing the FalkorDB client
#[derive(Clone)]
pub struct AppState {
    client: Arc<FalkorClient>,
}

impl AppState {
    pub async fn new(config: DatabaseConfig) -> Result<Self> {
        let client = FalkorClient::new(config).await?;
        client.test_connection().await?;

        Ok(Self {
            client: Arc::new(client),
        })
    }
}

/// Create the HTTP server with all centrality endpoints
pub fn create_router(state: AppState) -> Router {
    Router::new()
        .route("/health", get(health_check))
        .route("/stats", get(get_stats))
        .route("/centrality/pagerank", post(pagerank_endpoint))
        .route("/centrality/degree", post(degree_endpoint))
        .route("/centrality/betweenness", post(betweenness_endpoint))
        .route("/centrality/all", post(all_centralities_endpoint))
        .route("/centrality/node/:uuid", post(single_node_endpoint))
        .layer(CorsLayer::permissive())
        .with_state(state)
}

/// Health check endpoint
async fn health_check() -> impl IntoResponse {
    Json(json!({
        "status": "healthy",
        "service": "graphiti-centrality-rs"
    }))
}

/// Get basic graph statistics
async fn get_stats(State(state): State<AppState>) -> impl IntoResponse {
    match state.client.get_graph_stats().await {
        Ok(stats) => {
            info!("Graph stats requested: {:?}", stats);
            Json(json!(stats)).into_response()
        }
        Err(e) => {
            error!("Failed to get graph stats: {}", e);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({
                    "error": "Failed to retrieve graph statistics",
                    "details": e.to_string()
                })),
            )
                .into_response()
        }
    }
}

/// PageRank centrality endpoint
async fn pagerank_endpoint(
    State(state): State<AppState>,
    Json(request): Json<PageRankRequest>,
) -> impl IntoResponse {
    let start = Instant::now();

    match calculate_pagerank(
        &state.client,
        request.group_id.as_deref(),
        request.damping_factor,
        request.iterations,
    )
    .await
    {
        Ok(result) => {
            let execution_time_ms = start.elapsed().as_millis();

            // Store results if requested
            if request.store_results {
                let formatted_scores: HashMap<String, HashMap<String, f64>> = result
                    .scores
                    .iter()
                    .map(|(uuid, score)| {
                        let mut scores = HashMap::new();
                        scores.insert("pagerank".to_string(), *score);
                        (uuid.clone(), scores)
                    })
                    .collect();

                if let Err(e) = state.client.store_centrality_scores(&formatted_scores).await {
                    error!("Failed to store PageRank scores: {}", e);
                }
            }

            Json(CentralityResponse {
                scores: result.scores,
                metric: "pagerank".to_string(),
                nodes_processed: result.nodes_processed,
                execution_time_ms,
            })
            .into_response()
        }
        Err(e) => {
            error!("PageRank calculation failed: {}", e);
            handle_error(e).into_response()
        }
    }
}

/// Degree centrality endpoint
async fn degree_endpoint(
    State(state): State<AppState>,
    Json(request): Json<DegreeRequest>,
) -> impl IntoResponse {
    let start = Instant::now();

    match calculate_degree_centrality(
        &state.client,
        &request.direction,
        request.group_id.as_deref(),
    )
    .await
    {
        Ok(mut result) => {
            let execution_time_ms = start.elapsed().as_millis();

            // Normalize degree scores to [0,1] range
            let max_degree = result.scores.values().fold(0.0_f64, |a, &b| a.max(b));
            if max_degree > 0.0 {
                for score in result.scores.values_mut() {
                    *score /= max_degree;
                }
            }

            // Store results if requested
            if request.store_results {
                let formatted_scores: HashMap<String, HashMap<String, f64>> = result
                    .scores
                    .iter()
                    .map(|(uuid, score)| {
                        let mut scores = HashMap::new();
                        scores.insert("degree".to_string(), *score);
                        (uuid.clone(), scores)
                    })
                    .collect();

                if let Err(e) = state.client.store_centrality_scores(&formatted_scores).await {
                    error!("Failed to store degree centrality scores: {}", e);
                }
            }

            Json(CentralityResponse {
                scores: result.scores,
                metric: format!("degree_{}", request.direction),
                nodes_processed: result.nodes_processed,
                execution_time_ms,
            })
            .into_response()
        }
        Err(e) => {
            error!("Degree centrality calculation failed: {}", e);
            handle_error(e).into_response()
        }
    }
}

/// Betweenness centrality endpoint
async fn betweenness_endpoint(
    State(state): State<AppState>,
    Json(request): Json<BetweennessRequest>,
) -> impl IntoResponse {
    let start = Instant::now();

    match calculate_betweenness_centrality(
        &state.client,
        request.group_id.as_deref(),
        request.sample_size,
    )
    .await
    {
        Ok(result) => {
            let execution_time_ms = start.elapsed().as_millis();

            // Store results if requested
            if request.store_results {
                let formatted_scores: HashMap<String, HashMap<String, f64>> = result
                    .scores
                    .iter()
                    .map(|(uuid, score)| {
                        let mut scores = HashMap::new();
                        scores.insert("betweenness".to_string(), *score);
                        (uuid.clone(), scores)
                    })
                    .collect();

                if let Err(e) = state.client.store_centrality_scores(&formatted_scores).await {
                    error!("Failed to store betweenness centrality scores: {}", e);
                }
            }

            Json(CentralityResponse {
                scores: result.scores,
                metric: "betweenness".to_string(),
                nodes_processed: result.nodes_processed,
                execution_time_ms,
            })
            .into_response()
        }
        Err(e) => {
            error!("Betweenness centrality calculation failed: {}", e);
            handle_error(e).into_response()
        }
    }
}

/// All centralities endpoint
async fn all_centralities_endpoint(
    State(state): State<AppState>,
    Json(request): Json<AllCentralitiesRequest>,
) -> impl IntoResponse {
    let start = Instant::now();

    match calculate_all_centralities(&state.client, request.group_id.as_deref()).await {
        Ok(result) => {
            let execution_time_ms = start.elapsed().as_millis();
            let nodes_processed = result.len();

            // Store results if requested
            if request.store_results {
                if let Err(e) = state.client.store_centrality_scores(&result).await {
                    error!("Failed to store all centrality scores: {}", e);
                } else {
                    info!("✅ Centrality scores stored successfully. Visualization server should reload data from http://localhost:3000/api/data/reload");
                }
            }

            Json(AllCentralitiesResponse {
                scores: result,
                nodes_processed,
                execution_time_ms,
            })
            .into_response()
        }
        Err(e) => {
            error!("All centralities calculation failed: {}", e);
            handle_error(e).into_response()
        }
    }
}

/// Convert errors to HTTP responses
fn handle_error(error: CentralityError) -> (StatusCode, Json<serde_json::Value>) {
    let (status, message) = match &error {
        CentralityError::Database(_) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            "Database connection error",
        ),
        CentralityError::InvalidParameter { .. } => (StatusCode::BAD_REQUEST, "Invalid parameter"),
        CentralityError::AlgorithmFailed { .. } => {
            (StatusCode::INTERNAL_SERVER_ERROR, "Algorithm execution failed")
        }
        CentralityError::GraphNotFound { .. } => (StatusCode::NOT_FOUND, "Graph not found"),
        CentralityError::NoNodesFound => (StatusCode::NOT_FOUND, "No nodes found"),
        CentralityError::Serialization(_) => {
            (StatusCode::INTERNAL_SERVER_ERROR, "Serialization error")
        }
        CentralityError::Http(_) => (StatusCode::INTERNAL_SERVER_ERROR, "HTTP server error"),
        CentralityError::Internal(_) => (StatusCode::INTERNAL_SERVER_ERROR, "Internal error"),
    };

    (
        status,
        Json(json!({
            "error": message,
            "details": error.to_string()
        })),
    )
}

/// Single node centrality endpoint
async fn single_node_endpoint(
    State(state): State<AppState>,
    Path(node_uuid): Path<String>,
    Json(request): Json<SingleNodeRequest>,
) -> impl IntoResponse {
    let start = Instant::now();
    
    // Calculate requested metrics for the single node
    let mut metrics = HashMap::new();
    
    // Calculate degree centrality if requested
    if request.metrics.contains(&"degree".to_string()) {
        match calculate_single_node_degree(&state.client, &node_uuid).await {
            Ok(degree) => {
                metrics.insert("degree".to_string(), degree);
            }
            Err(e) => {
                error!("Failed to calculate degree centrality for {}: {}", node_uuid, e);
                return handle_error(e).into_response();
            }
        }
    }
    
    // Calculate PageRank if requested (simplified local calculation)
    if request.metrics.contains(&"pagerank".to_string()) {
        match calculate_single_node_pagerank(&state.client, &node_uuid).await {
            Ok(pagerank) => {
                metrics.insert("pagerank".to_string(), pagerank);
            }
            Err(e) => {
                error!("Failed to calculate PageRank for {}: {}", node_uuid, e);
                return handle_error(e).into_response();
            }
        }
    }
    
    // Calculate betweenness if requested (simplified local calculation)
    if request.metrics.contains(&"betweenness".to_string()) {
        match calculate_single_node_betweenness(&state.client, &node_uuid).await {
            Ok(betweenness) => {
                metrics.insert("betweenness".to_string(), betweenness);
            }
            Err(e) => {
                error!("Failed to calculate betweenness for {}: {}", node_uuid, e);
                return handle_error(e).into_response();
            }
        }
    }
    
    // Store results if requested
    if request.store_results && !metrics.is_empty() {
        let mut scores_map = HashMap::new();
        scores_map.insert(node_uuid.clone(), metrics.clone());
        
        if let Err(e) = state.client.store_centrality_scores(&scores_map).await {
            error!("Failed to store centrality scores for {}: {}", node_uuid, e);
        }
    }
    
    let execution_time_ms = start.elapsed().as_millis();
    
    Json(SingleNodeResponse {
        node_id: node_uuid,
        metrics,
        execution_time_ms,
    })
    .into_response()
}

// Helper functions for single node calculations
async fn calculate_single_node_degree(
    client: &FalkorClient,
    node_uuid: &str,
) -> Result<f64> {
    let query = format!(
        r#"
        MATCH (n {{uuid: '{}'}})
        OPTIONAL MATCH (n)-[r]-(m)
        RETURN COUNT(DISTINCT m) as degree
        "#,
        node_uuid
    );
    
    let result = client.execute_query(&query, None).await?;
    
    if let Some(row) = result.first() {
        if let Some(degree_value) = row.get("degree") {
            if let Some(degree) = crate::client::falkor_value_to_i64(degree_value) {
                // Normalize degree (simple normalization by dividing by 10)
                return Ok(degree as f64 / 10.0);
            }
        }
    }
    
    Ok(0.0)
}

async fn calculate_single_node_pagerank(
    client: &FalkorClient,
    node_uuid: &str,
) -> Result<f64> {
    // Simplified PageRank calculation based on degree
    let degree = calculate_single_node_degree(client, node_uuid).await?;
    
    // Simple formula: base pagerank + scaled degree contribution
    Ok(0.15 + 0.85 * (degree / 100.0).min(1.0))
}

async fn calculate_single_node_betweenness(
    client: &FalkorClient,
    node_uuid: &str,
) -> Result<f64> {
    // Simplified betweenness calculation based on degree
    let degree = calculate_single_node_degree(client, node_uuid).await?;
    
    // Simple approximation
    Ok((degree / 20.0).min(1.0))
}