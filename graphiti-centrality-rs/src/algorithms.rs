use crate::client::{falkor_value_to_f64, falkor_value_to_i64, falkor_value_to_string, FalkorClient};
use crate::error::{CentralityError, Result};
use crate::models::CentralityScores;
use falkordb::FalkorValue;
use std::collections::{HashMap, HashSet};
use std::time::Instant;
use tracing::{debug, info, warn};

/// Calculate PageRank centrality using FalkorDB's native algorithm or custom fallback
pub async fn calculate_pagerank(
    client: &FalkorClient,
    group_id: Option<&str>,
    damping_factor: f64,
    iterations: u32,
) -> Result<CentralityScores> {
    let start = Instant::now();
    info!("Starting PageRank calculation");

    // Use FalkorDB's native PageRank algorithm
    let graph_name = client.graph_name();
    let native_algorithm = format!(
        "CALL algo.pageRank('{}', {{max_iter: {}, dampingFactor: {}}})", 
        graph_name, iterations, damping_factor
    );

    debug!("Running native PageRank: {}", native_algorithm);

    // Execute the algorithm (stores results in node properties)
    if let Ok(_) = client.execute_query(&native_algorithm, None).await {
        info!("FalkorDB native PageRank completed, retrieving results");
        
        // Now retrieve the stored results
        let results_query = if let Some(group_id) = group_id {
            format!(
                "MATCH (n) WHERE n.group_id = '{}' AND EXISTS(n.score) 
                 RETURN n.uuid as uuid, n.score as score",
                group_id
            )
        } else {
            "MATCH (n) WHERE EXISTS(n.score) 
             RETURN n.uuid as uuid, n.score as score"
                .to_string()
        };

        if let Ok(results) = client.execute_query(&results_query, None).await {
            if !results.is_empty() {
                info!("Using FalkorDB native PageRank algorithm");
                return process_pagerank_results(results, start);
            }
        }
    }

    info!("Native PageRank not available, using custom implementation");
    calculate_pagerank_custom(client, group_id, damping_factor, iterations).await
}

/// Process PageRank results from either native or custom implementation
fn process_pagerank_results(
    results: Vec<HashMap<String, FalkorValue>>,
    start: Instant,
) -> Result<CentralityScores> {
    let mut scores = HashMap::new();
    let mut processed = 0;

    for record in results {
        if let (Some(uuid_val), Some(score_val)) = (record.get("uuid"), record.get("score")) {
            let uuid = falkor_value_to_string(uuid_val);
            if let Some(score) = falkor_value_to_f64(score_val) {
                scores.insert(uuid, score);
                processed += 1;
            } else {
                warn!("Invalid score value for node: {:?}", uuid_val);
            }
        }
    }

    let duration = start.elapsed();
    info!(
        "PageRank calculation completed in {:?} for {} nodes",
        duration, processed
    );

    if scores.is_empty() {
        return Err(CentralityError::NoNodesFound);
    }

    Ok(CentralityScores {
        scores,
        nodes_processed: processed,
    })
}

/// Custom PageRank implementation using iterative algorithm
async fn calculate_pagerank_custom(
    client: &FalkorClient,
    group_id: Option<&str>,
    damping_factor: f64,
    max_iterations: u32,
) -> Result<CentralityScores> {
    info!("Starting custom PageRank calculation with damping_factor={}, iterations={}", damping_factor, max_iterations);

    // Get all nodes and their connections
    let nodes_query = if let Some(group_id) = group_id {
        format!(
            "MATCH (n) WHERE n.group_id = '{}' RETURN n.uuid as uuid",
            group_id
        )
    } else {
        "MATCH (n) RETURN n.uuid as uuid".to_string()
    };

    let edges_query = if let Some(group_id) = group_id {
        format!(
            "MATCH (source)-[r]->(target) 
             WHERE source.group_id = '{}' AND target.group_id = '{}' 
             RETURN source.uuid as source, target.uuid as target",
            group_id, group_id
        )
    } else {
        "MATCH (source)-[r]->(target) 
         RETURN source.uuid as source, target.uuid as target"
            .to_string()
    };

    debug!("Getting nodes with query: {}", nodes_query);
    let node_results = client.execute_query(&nodes_query, None).await?;
    
    debug!("Getting edges with query: {}", edges_query);
    let edge_results = client.execute_query(&edges_query, None).await?;

    // Build node list and adjacency information
    let nodes: Vec<String> = node_results
        .iter()
        .filter_map(|record| {
            record
                .get("uuid")
                .map(|v| falkor_value_to_string(v))
        })
        .collect();

    if nodes.is_empty() {
        return Err(CentralityError::NoNodesFound);
    }

    let node_count = nodes.len();
    info!("Processing {} nodes for PageRank", node_count);

    // Build adjacency lists and out-degree counts
    let mut out_links: HashMap<String, Vec<String>> = HashMap::new();
    let mut out_degree: HashMap<String, usize> = HashMap::new();

    // Initialize structures
    for node in &nodes {
        out_links.insert(node.clone(), Vec::new());
        out_degree.insert(node.clone(), 0);
    }

    // Process edges
    for record in edge_results {
        if let (Some(source_val), Some(target_val)) = (record.get("source"), record.get("target")) {
            let source = falkor_value_to_string(source_val);
            let target = falkor_value_to_string(target_val);
            
            if let Some(links) = out_links.get_mut(&source) {
                links.push(target);
                *out_degree.get_mut(&source).unwrap() += 1;
            }
        }
    }

    // Initialize PageRank scores
    let initial_score = 1.0 / node_count as f64;
    let mut scores: HashMap<String, f64> = nodes.iter()
        .map(|node| (node.clone(), initial_score))
        .collect();

    let mut new_scores = scores.clone();

    // Iterative PageRank calculation
    for iteration in 0..max_iterations {
        let mut total_diff = 0.0;

        for node in &nodes {
            let mut rank = (1.0 - damping_factor) / node_count as f64;
            
            // Sum contributions from incoming links
            for other_node in &nodes {
                if let Some(links) = out_links.get(other_node) {
                    if links.contains(node) {
                        let out_deg = *out_degree.get(other_node).unwrap() as f64;
                        if out_deg > 0.0 {
                            let contribution = scores.get(other_node).unwrap() / out_deg;
                            rank += damping_factor * contribution;
                        }
                    }
                }
            }

            let old_score = *scores.get(node).unwrap();
            new_scores.insert(node.clone(), rank);
            total_diff += (rank - old_score).abs();
        }

        // Update scores for next iteration
        scores = new_scores.clone();

        // Check for convergence
        let avg_diff = total_diff / node_count as f64;
        debug!("Iteration {}: average difference = {:.8}", iteration + 1, avg_diff);
        
        if avg_diff < 1e-6 {
            info!("PageRank converged after {} iterations", iteration + 1);
            break;
        }
    }

    let processed = scores.len();
    info!("Custom PageRank calculation completed for {} nodes", processed);

    Ok(CentralityScores {
        scores,
        nodes_processed: processed,
    })
}

/// Calculate degree centrality with optimized single queries
pub async fn calculate_degree_centrality(
    client: &FalkorClient,
    direction: &str,
    group_id: Option<&str>,
) -> Result<CentralityScores> {
    let start = Instant::now();
    info!("Starting degree centrality calculation for direction: {}", direction);

    let query = match direction {
        "both" => {
            if let Some(group_id) = group_id {
                format!(
                    "MATCH (n) WHERE n.group_id = '{}' 
                     OPTIONAL MATCH (n)-[r]-() 
                     RETURN n.uuid as uuid, count(r) as degree",
                    group_id
                )
            } else {
                "MATCH (n) OPTIONAL MATCH (n)-[r]-() 
                 RETURN n.uuid as uuid, count(r) as degree"
                    .to_string()
            }
        }
        "in" => {
            if let Some(group_id) = group_id {
                format!(
                    "MATCH (n) WHERE n.group_id = '{}' 
                     OPTIONAL MATCH ()-[r]->(n) 
                     RETURN n.uuid as uuid, count(r) as degree",
                    group_id
                )
            } else {
                "MATCH (n) OPTIONAL MATCH ()-[r]->(n) 
                 RETURN n.uuid as uuid, count(r) as degree"
                    .to_string()
            }
        }
        "out" => {
            if let Some(group_id) = group_id {
                format!(
                    "MATCH (n) WHERE n.group_id = '{}' 
                     OPTIONAL MATCH (n)-[r]->() 
                     RETURN n.uuid as uuid, count(r) as degree",
                    group_id
                )
            } else {
                "MATCH (n) OPTIONAL MATCH (n)-[r]->() 
                 RETURN n.uuid as uuid, count(r) as degree"
                    .to_string()
            }
        }
        _ => return Err(CentralityError::invalid_parameter(format!("Invalid direction: {}. Must be 'in', 'out', or 'both'", direction))),
    };

    debug!("Executing degree centrality query: {}", query);

    let results = client.execute_query(&query, None).await?;

    let mut scores = HashMap::new();
    let mut processed = 0;

    for record in results {
        if let (Some(uuid_val), Some(degree_val)) = (record.get("uuid"), record.get("degree")) {
            let uuid = falkor_value_to_string(uuid_val);
            if let Some(degree) = falkor_value_to_i64(degree_val) {
                scores.insert(uuid, degree as f64);
                processed += 1;
            } else {
                warn!("Invalid degree value for node: {:?}", uuid_val);
            }
        }
    }

    let duration = start.elapsed();
    info!(
        "Degree centrality calculation completed in {:?} for {} nodes",
        duration, processed
    );

    if scores.is_empty() {
        return Err(CentralityError::NoNodesFound);
    }

    Ok(CentralityScores {
        scores,
        nodes_processed: processed,
    })
}

/// Calculate betweenness centrality (simplified version with sampling)
pub async fn calculate_betweenness_centrality(
    client: &FalkorClient,
    group_id: Option<&str>,
    sample_size: Option<u32>,
) -> Result<CentralityScores> {
    let _start = Instant::now();
    info!("Starting betweenness centrality calculation");

    // Use FalkorDB's native betweenness algorithm
    let graph_name = client.graph_name();
    let native_algorithm = format!("CALL algo.betweenness('{}')", graph_name);
    
    debug!("Running native betweenness: {}", native_algorithm);
    
    if let Ok(_) = client.execute_query(&native_algorithm, None).await {
        info!("FalkorDB native betweenness completed, retrieving results");
        return calculate_betweenness_native(client, group_id).await;
    }

    info!("Using simplified betweenness centrality calculation");
    calculate_betweenness_approximation(client, group_id, sample_size).await
}

/// Use FalkorDB's native betweenness centrality if available
async fn calculate_betweenness_native(
    client: &FalkorClient,
    group_id: Option<&str>,
) -> Result<CentralityScores> {
    let start = Instant::now();
    
    // Retrieve the stored betweenness results (algo.betweenness stores in node.betweenness property)
    let query = if let Some(group_id) = group_id {
        format!(
            "MATCH (n) WHERE n.group_id = '{}' AND EXISTS(n.betweenness) 
             RETURN n.uuid as uuid, n.betweenness as score",
            group_id
        )
    } else {
        "MATCH (n) WHERE EXISTS(n.betweenness) 
         RETURN n.uuid as uuid, n.betweenness as score"
            .to_string()
    };

    debug!("Retrieving native betweenness results: {}", query);

    let results = client.execute_query(&query, None).await?;

    let mut scores = HashMap::new();
    let mut processed = 0;

    for record in results {
        if let (Some(uuid_val), Some(score_val)) = (record.get("uuid"), record.get("score")) {
            let uuid = falkor_value_to_string(uuid_val);
            if let Some(score) = falkor_value_to_f64(score_val) {
                scores.insert(uuid, score);
                processed += 1;
            }
        }
    }

    let duration = start.elapsed();
    info!(
        "Native betweenness results retrieved in {:?} for {} nodes",
        duration, processed
    );

    Ok(CentralityScores {
        scores,
        nodes_processed: processed,
    })
}

/// Simplified betweenness centrality approximation
async fn calculate_betweenness_approximation(
    client: &FalkorClient,
    group_id: Option<&str>,
    sample_size: Option<u32>,
) -> Result<CentralityScores> {
    // Get all nodes first
    let nodes_query = if let Some(group_id) = group_id {
        format!(
            "MATCH (n) WHERE n.group_id = '{}' RETURN n.uuid as uuid",
            group_id
        )
    } else {
        "MATCH (n) RETURN n.uuid as uuid".to_string()
    };

    let node_results = client.execute_query(&nodes_query, None).await?;
    let mut node_uuids: Vec<String> = node_results
        .iter()
        .filter_map(|record| {
            record
                .get("uuid")
                .map(|v| falkor_value_to_string(v))
        })
        .collect();

    // Apply sampling if requested
    if let Some(sample_size) = sample_size {
        if node_uuids.len() > sample_size as usize {
            // Simple sampling - take every nth node
            let step = node_uuids.len() / sample_size as usize;
            node_uuids = node_uuids.into_iter().step_by(step.max(1)).collect();
        }
    }

    let mut betweenness = HashMap::new();
    for uuid in &node_uuids {
        betweenness.insert(uuid.clone(), 0.0);
    }

    // For betweenness, we need to find shortest paths
    // This is a simplified version that counts paths through each node
    let path_query = "MATCH path = shortestPath((source)-[*..5]-(target))
                      WHERE source.uuid <> target.uuid
                      RETURN nodes(path) as path_nodes
                      LIMIT 1000"; // Limit for performance

    if let Ok(path_results) = client.execute_query(path_query, None).await {
        for record in path_results {
            if let Some(FalkorValue::Array(path_nodes)) = record.get("path_nodes") {
                // Count intermediate nodes in the path
                for i in 1..path_nodes.len().saturating_sub(1) {
                    if let Some(node_map) = path_nodes[i].as_map() {
                        if let Some(uuid_val) = node_map.get("uuid") {
                            let uuid = falkor_value_to_string(uuid_val);
                            if let Some(score) = betweenness.get_mut(&uuid) {
                                *score += 1.0;
                            }
                        }
                    }
                }
            }
        }
    }

    // Normalize scores
    let max_score = betweenness.values().fold(0.0_f64, |a, &b| a.max(b));
    if max_score > 0.0 {
        for score in betweenness.values_mut() {
            *score /= max_score;
        }
    }

    let processed = betweenness.len();

    Ok(CentralityScores {
        scores: betweenness,
        nodes_processed: processed,
    })
}

/// Calculate eigenvector centrality using power iteration method
pub async fn calculate_eigenvector_centrality(
    client: &FalkorClient,
    group_id: Option<&str>,
    max_iterations: u32,
    tolerance: f64,
) -> Result<CentralityScores> {
    let start = Instant::now();
    info!("Starting eigenvector centrality calculation");

    // First, get all nodes and their connections
    let adjacency_query = if let Some(group_id) = group_id {
        format!(
            "MATCH (n) WHERE n.group_id = '{}' 
             OPTIONAL MATCH (n)-[r]-(m)
             WHERE m.group_id = '{}'
             RETURN n.uuid as node, collect(DISTINCT m.uuid) as neighbors",
            group_id, group_id
        )
    } else {
        "MATCH (n)
         OPTIONAL MATCH (n)-[r]-(m)
         RETURN n.uuid as node, collect(DISTINCT m.uuid) as neighbors"
            .to_string()
    };

    debug!("Fetching adjacency list for eigenvector centrality");
    let results = client.execute_query(&adjacency_query, None).await?;
    
    // Build adjacency list
    let mut adjacency: HashMap<String, Vec<String>> = HashMap::new();
    let mut all_nodes: HashSet<String> = HashSet::new();
    
    for record in results {
        if let Some(node_val) = record.get("node") {
            let node = falkor_value_to_string(node_val);
            all_nodes.insert(node.clone());
            
            // Get neighbors
            let neighbors = if let Some(FalkorValue::Array(neighbors_array)) = record.get("neighbors") {
                neighbors_array
                    .iter()
                    .filter_map(|v| {
                        if let FalkorValue::String(s) = v {
                            Some(s.clone())
                        } else {
                            None
                        }
                    })
                    .collect()
            } else {
                Vec::new()
            };
            
            adjacency.insert(node, neighbors);
        }
    }
    
    if all_nodes.is_empty() {
        return Err(CentralityError::NoNodesFound);
    }
    
    let node_count = all_nodes.len();
    info!("Computing eigenvector centrality for {} nodes", node_count);
    
    // Initialize scores to 1/sqrt(n)
    let initial_value = 1.0 / (node_count as f64).sqrt();
    let mut scores: HashMap<String, f64> = HashMap::new();
    for node in &all_nodes {
        scores.insert(node.clone(), initial_value);
    }
    
    // Power iteration
    for iteration in 0..max_iterations {
        let mut new_scores: HashMap<String, f64> = HashMap::new();
        
        // Calculate new scores: score[v] = sum of neighbors' scores
        for node in &all_nodes {
            let mut score = 0.0;
            if let Some(neighbors) = adjacency.get(node) {
                for neighbor in neighbors {
                    if let Some(neighbor_score) = scores.get(neighbor) {
                        score += neighbor_score;
                    }
                }
            }
            new_scores.insert(node.clone(), score);
        }
        
        // Calculate L2 norm for normalization
        let norm: f64 = new_scores
            .values()
            .map(|s| s * s)
            .sum::<f64>()
            .sqrt();
        
        // Normalize scores
        if norm > 0.0 {
            for score in new_scores.values_mut() {
                *score /= norm;
            }
        } else {
            // If norm is 0, reinitialize to avoid degenerate case
            warn!("Eigenvector centrality norm is 0, reinitializing");
            for score in new_scores.values_mut() {
                *score = initial_value;
            }
        }
        
        // Check for convergence
        let mut total_diff = 0.0;
        for node in &all_nodes {
            let old_score = scores.get(node).unwrap_or(&0.0);
            let new_score = new_scores.get(node).unwrap_or(&0.0);
            total_diff += (old_score - new_score).abs();
        }
        
        let avg_diff = total_diff / node_count as f64;
        debug!("Iteration {}: average difference = {:.8}", iteration + 1, avg_diff);
        
        // Update scores for next iteration
        scores = new_scores;
        
        // Check convergence
        if avg_diff < tolerance {
            info!("Eigenvector centrality converged after {} iterations", iteration + 1);
            break;
        }
    }
    
    let duration = start.elapsed();
    info!(
        "Eigenvector centrality calculation completed in {:?} for {} nodes",
        duration, node_count
    );
    
    Ok(CentralityScores {
        scores,
        nodes_processed: node_count,
    })
}

/// Calculate all centrality metrics efficiently
pub async fn calculate_all_centralities(
    client: &FalkorClient,
    group_id: Option<&str>,
) -> Result<HashMap<String, HashMap<String, f64>>> {
    let start = Instant::now();
    info!("Starting calculation of all centrality metrics");

    // Calculate each metric
    let pagerank = calculate_pagerank(client, group_id, 0.85, 20).await?;
    let degree = calculate_degree_centrality(client, "both", group_id).await?;

    // For betweenness, use sampling for large graphs
    let stats = client.get_graph_stats().await?;
    let node_count = stats.get("nodes").unwrap_or(&0);
    let sample_size = if *node_count > 100 { Some(50) } else { None };

    let betweenness = calculate_betweenness_centrality(client, group_id, sample_size).await?;
    
    // Calculate true eigenvector centrality
    let eigenvector = calculate_eigenvector_centrality(client, group_id, 100, 1e-6).await?;

    // Find max degree for normalization
    let max_degree = degree.scores.values().fold(0.0_f64, |a, &b| a.max(b));
    
    // Combine all scores
    let mut all_scores = HashMap::new();
    let all_nodes: std::collections::HashSet<String> = pagerank
        .scores
        .keys()
        .chain(degree.scores.keys())
        .chain(betweenness.scores.keys())
        .chain(eigenvector.scores.keys())
        .cloned()
        .collect();

    for node_id in all_nodes {
        let mut node_scores = HashMap::new();

        // PageRank is already normalized by the algorithm
        let pagerank_score = pagerank.scores.get(&node_id).copied().unwrap_or(0.0);
        node_scores.insert("pagerank".to_string(), pagerank_score);
        
        // Normalize degree centrality to [0,1] by dividing by max degree
        let degree_raw = degree.scores.get(&node_id).copied().unwrap_or(0.0);
        let degree_normalized = if max_degree > 0.0 { degree_raw / max_degree } else { 0.0 };
        node_scores.insert("degree".to_string(), degree_normalized);
        
        // Betweenness is already normalized in the approximation function
        let betweenness_score = betweenness.scores.get(&node_id).copied().unwrap_or(0.0);
        node_scores.insert("betweenness".to_string(), betweenness_score);
        
        // True eigenvector centrality (already normalized by power iteration)
        let eigenvector_score = eigenvector.scores.get(&node_id).copied().unwrap_or(0.0);
        node_scores.insert("eigenvector".to_string(), eigenvector_score);

        // Calculate importance as a weighted combination
        // This is a composite metric, not eigenvector centrality
        let importance = (0.4 * pagerank_score + 0.3 * eigenvector_score + 0.2 * degree_normalized + 0.1 * betweenness_score).min(1.0);
        node_scores.insert("importance".to_string(), importance);

        all_scores.insert(node_id, node_scores);
    }

    let duration = start.elapsed();
    info!(
        "All centrality calculations completed in {:?} for {} nodes",
        duration,
        all_scores.len()
    );

    Ok(all_scores)
}