use crate::client::{
    falkor_value_to_f64, falkor_value_to_i64, falkor_value_to_string, FalkorClient,
};
use crate::error::{CentralityError, Result};
use crate::models::CentralityScores;
use falkordb::FalkorValue;
use std::collections::{HashMap, HashSet, VecDeque};
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

    // First check if PageRank centrality values already exist (pre-computed)
    let precomputed_query = if let Some(group_id) = group_id {
        format!(
            "MATCH (n) WHERE n.group_id = '{}' AND EXISTS(n.pagerank_centrality) 
             RETURN n.uuid as uuid, n.pagerank_centrality as score",
            group_id
        )
    } else {
        "MATCH (n) WHERE EXISTS(n.pagerank_centrality) 
         RETURN n.uuid as uuid, n.pagerank_centrality as score"
            .to_string()
    };

    debug!("Checking for pre-computed PageRank values: {}", precomputed_query);
    if let Ok(results) = client.execute_query(&precomputed_query, None).await {
        if !results.is_empty() {
            info!("Using pre-computed FalkorDB PageRank values");
            return process_pagerank_results(results, start);
        }
    }

    // Use FalkorDB's native PageRank algorithm with correct syntax
    let native_algorithm = "CALL algo.pageRank(null, null)";

    debug!("Running native PageRank: {}", native_algorithm);

    // Execute the algorithm (stores results in node properties)
    if let Ok(_) = client.execute_query(native_algorithm, None).await {
        info!("FalkorDB native PageRank completed, retrieving results");

        // Now retrieve the stored results using correct property name
        let results_query = if let Some(group_id) = group_id {
            format!(
                "MATCH (n) WHERE n.group_id = '{}' AND EXISTS(n.pagerank_centrality) 
                 RETURN n.uuid as uuid, n.pagerank_centrality as score",
                group_id
            )
        } else {
            "MATCH (n) WHERE EXISTS(n.pagerank_centrality) 
             RETURN n.uuid as uuid, n.pagerank_centrality as score"
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
    info!(
        "Starting custom PageRank calculation with damping_factor={}, iterations={}",
        damping_factor, max_iterations
    );

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
        .filter_map(|record| record.get("uuid").map(|v| falkor_value_to_string(v)))
        .collect();

    if nodes.is_empty() {
        return Err(CentralityError::NoNodesFound);
    }

    let node_count = nodes.len();
    info!("Processing {} nodes for PageRank", node_count);

    // Build incoming adjacency list and out-degree counts
    // incoming: target -> [sources that link TO target]
    // out_degree: source -> number of outgoing edges
    let mut incoming: HashMap<String, Vec<String>> = HashMap::new();
    let mut out_degree: HashMap<String, usize> = HashMap::new();
    let node_set: HashSet<String> = nodes.iter().cloned().collect();

    // Initialize incoming lists for all nodes
    for node in &nodes {
        incoming.insert(node.clone(), Vec::new());
        out_degree.insert(node.clone(), 0);
    }

    // Process edges — build incoming adjacency and out-degree
    for record in edge_results {
        if let (Some(source_val), Some(target_val)) = (record.get("source"), record.get("target")) {
            let source = falkor_value_to_string(source_val);
            let target = falkor_value_to_string(target_val);

            if node_set.contains(&source) && node_set.contains(&target) {
                if let Some(sources) = incoming.get_mut(&target) {
                    sources.push(source.clone());
                }
                *out_degree.entry(source).or_insert(0) += 1;
            }
        }
    }

    info!("Loaded edges for {} nodes — running PageRank in-memory", node_count);

    // Initialize PageRank scores
    let initial_score = 1.0 / node_count as f64;
    let mut scores: HashMap<String, f64> = nodes
        .iter()
        .map(|node| (node.clone(), initial_score))
        .collect();

    let mut new_scores = scores.clone();

    // Iterative PageRank calculation
    for iteration in 0..max_iterations {
        let mut total_diff = 0.0;

        for node in &nodes {
            let mut rank = (1.0 - damping_factor) / node_count as f64;

            // Sum contributions from incoming links — O(in-degree) per node
            let empty_vec = Vec::new();
            for source in incoming.get(node).unwrap_or(&empty_vec) {
                let out_deg = *out_degree.get(source).unwrap_or(&1) as f64;
                if out_deg > 0.0 {
                    let contribution = scores.get(source).unwrap_or(&initial_score) / out_deg;
                    rank += damping_factor * contribution;
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
        debug!(
            "Iteration {}: average difference = {:.8}",
            iteration + 1,
            avg_diff
        );

        if avg_diff < 1e-6 {
            info!("PageRank converged after {} iterations", iteration + 1);
            break;
        }
    }

    let processed = scores.len();
    info!(
        "Custom PageRank calculation completed for {} nodes",
        processed
    );

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
    info!(
        "Starting degree centrality calculation for direction: {}",
        direction
    );

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
        _ => {
            return Err(CentralityError::invalid_parameter(format!(
                "Invalid direction: {}. Must be 'in', 'out', or 'both'",
                direction
            )))
        }
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

    // First check if betweenness centrality values already exist (pre-computed)
    let precomputed_query = if let Some(group_id) = group_id {
        format!(
            "MATCH (n) WHERE n.group_id = '{}' AND EXISTS(n.betweenness_centrality) 
             RETURN n.uuid as uuid, n.betweenness_centrality as score",
            group_id
        )
    } else {
        "MATCH (n) WHERE EXISTS(n.betweenness_centrality) 
         RETURN n.uuid as uuid, n.betweenness_centrality as score"
            .to_string()
    };

    debug!("Checking for pre-computed betweenness values: {}", precomputed_query);
    if let Ok(results) = client.execute_query(&precomputed_query, None).await {
        if !results.is_empty() {
            info!("Using pre-computed FalkorDB betweenness values");
            let start = Instant::now();
            return process_pagerank_results(results, start);
        }
    }

    // Use FalkorDB's native betweenness algorithm with correct syntax
    let native_algorithm = "CALL algo.betweenness({nodeLabels: [], relationshipTypes: []})";

    debug!("Running native betweenness: {}", native_algorithm);

    if let Ok(_) = client.execute_query(native_algorithm, None).await {
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

    // Retrieve the stored betweenness results (stored as betweenness_centrality property)
    let query = if let Some(group_id) = group_id {
        format!(
            "MATCH (n) WHERE n.group_id = '{}' AND EXISTS(n.betweenness_centrality) 
             RETURN n.uuid as uuid, n.betweenness_centrality as score",
            group_id
        )
    } else {
        "MATCH (n) WHERE EXISTS(n.betweenness_centrality) 
         RETURN n.uuid as uuid, n.betweenness_centrality as score"
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

/// In-memory Brandes betweenness centrality approximation
/// Replaces the old O(N²) shortestPath-query approach with O(V+E) BFS per source
async fn calculate_betweenness_approximation(
    client: &FalkorClient,
    group_id: Option<&str>,
    sample_size: Option<u32>,
) -> Result<CentralityScores> {
    let start = Instant::now();
    info!("Starting in-memory Brandes betweenness approximation");

    // Get all nodes
    let nodes_query = if let Some(group_id) = group_id {
        format!(
            "MATCH (n) WHERE n.group_id = '{}' RETURN n.uuid as uuid",
            group_id
        )
    } else {
        "MATCH (n) RETURN n.uuid as uuid".to_string()
    };

    let node_results = client.execute_query(&nodes_query, None).await?;
    let all_nodes: Vec<String> = node_results
        .iter()
        .filter_map(|record| record.get("uuid").map(|v| falkor_value_to_string(v)))
        .collect();

    let num_nodes = all_nodes.len();
    if num_nodes == 0 {
        return Err(CentralityError::NoNodesFound);
    }

    // Load ALL edges once — O(1) DB query
    let edges_query = if let Some(group_id) = group_id {
        format!(
            "MATCH (source)-[r]->(target)
             WHERE source.group_id = '{}' OR target.group_id = '{}'
             RETURN source.uuid as source, target.uuid as target",
            group_id, group_id
        )
    } else {
        "MATCH (source)-[r]->(target)
         RETURN source.uuid as source, target.uuid as target"
            .to_string()
    };

    let edge_results = client.execute_query(&edges_query, None).await?;

    // Build adjacency list in memory (directed: source -> [targets])
    let mut adjacency: HashMap<String, Vec<String>> = HashMap::new();
    let node_set: HashSet<String> = all_nodes.iter().cloned().collect();

    for record in edge_results {
        if let (Some(source_val), Some(target_val)) = (record.get("source"), record.get("target")) {
            let source = falkor_value_to_string(source_val);
            let target = falkor_value_to_string(target_val);

            if node_set.contains(&source) && node_set.contains(&target) {
                adjacency.entry(source).or_default().push(target);
            }
        }
    }

    info!(
        "Loaded edges for {} nodes — running Brandes algorithm in-memory",
        num_nodes
    );

    // Sample source nodes for BFS
    let source_nodes: Vec<&String> = if let Some(sample_size) = sample_size {
        if all_nodes.len() > sample_size as usize {
            let step = all_nodes.len() / sample_size as usize;
            all_nodes.iter().step_by(step.max(1)).collect()
        } else {
            all_nodes.iter().collect()
        }
    } else {
        all_nodes.iter().collect()
    };

    // Initialize betweenness scores for ALL nodes
    let mut betweenness: HashMap<String, f64> =
        all_nodes.iter().map(|n| (n.clone(), 0.0)).collect();

    // Brandes' algorithm: BFS from each source, accumulate dependency
    let empty_adj: Vec<String> = Vec::new();
    for (i, source) in source_nodes.iter().enumerate() {
        if i % 10 == 0 {
            debug!(
                "Brandes BFS from source {}/{}",
                i + 1,
                source_nodes.len()
            );
        }

        // BFS / shortest path counting
        let mut stack: Vec<String> = Vec::new();
        let mut predecessors: HashMap<String, Vec<String>> = HashMap::new();
        let mut sigma: HashMap<String, u64> = HashMap::new();
        sigma.insert((*source).clone(), 1);
        let mut dist: HashMap<String, i64> = HashMap::new();
        dist.insert((*source).clone(), 0);
        let mut queue: VecDeque<String> = VecDeque::new();
        queue.push_back((*source).clone());

        while let Some(v) = queue.pop_front() {
            stack.push(v.clone());
            let v_dist = *dist.get(&v).unwrap();

            for w in adjacency.get(&v).unwrap_or(&empty_adj) {
                // w found for the first time?
                if !dist.contains_key(w) {
                    dist.insert(w.clone(), v_dist + 1);
                    queue.push_back(w.clone());
                }
                // shortest path to w via v?
                if dist.get(w) == Some(&(v_dist + 1)) {
                    let sigma_v = *sigma.get(&v).unwrap_or(&0);
                    *sigma.entry(w.clone()).or_insert(0) += sigma_v;
                    predecessors.entry(w.clone()).or_default().push(v.clone());
                }
            }
        }

        // Accumulation — back-propagation of dependencies
        let mut delta: HashMap<String, f64> = HashMap::new();
        let empty_preds: Vec<String> = Vec::new();
        while let Some(w) = stack.pop() {
            for v in predecessors.get(&w).unwrap_or(&empty_preds) {
                let sigma_v = *sigma.get(v).unwrap_or(&1) as f64;
                let sigma_w = *sigma.get(&w).unwrap_or(&1) as f64;
                let delta_w = *delta.get(&w).unwrap_or(&0.0);
                *delta.entry(v.clone()).or_insert(0.0) +=
                    (sigma_v / sigma_w) * (1.0 + delta_w);
            }
            if &w != *source {
                *betweenness.entry(w.clone()).or_insert(0.0) +=
                    *delta.get(&w).unwrap_or(&0.0);
            }
        }
    }

    // Normalize scores
    if num_nodes > 2 {
        let scale = if let Some(sample_size) = sample_size {
            if (sample_size as usize) < num_nodes {
                (num_nodes as f64) / (source_nodes.len() as f64)
            } else {
                1.0
            }
        } else {
            1.0
        };
        let normalization = scale / ((num_nodes - 1) as f64 * (num_nodes - 2) as f64);
        for score in betweenness.values_mut() {
            *score *= normalization;
        }
    }

    let duration = start.elapsed();
    let processed = betweenness.len();
    info!(
        "Brandes betweenness completed in {:?}: {} source BFS runs, {} nodes scored",
        duration,
        source_nodes.len(),
        processed
    );

    Ok(CentralityScores {
        scores: betweenness,
        nodes_processed: processed,
    })
}

/// Graph connectivity types for choosing appropriate centrality algorithm
#[derive(Debug, Clone)]
enum GraphConnectivity {
    WeaklyConnected, // Single weakly connected component
    Disconnected,    // Multiple components
}

/// Analyze graph connectivity using FalkorDB's WCC algorithm
async fn analyze_graph_connectivity(
    client: &FalkorClient,
    group_id: Option<&str>,
) -> Result<GraphConnectivity> {
    let wcc_query = if let Some(group_id) = group_id {
        format!(
            "CALL algo.wcc({{
                nodeLabels: [],
                relationshipTypes: []
            }})
            YIELD node, componentId
            WHERE node.group_id = '{}'
            RETURN componentId, count(*) as size
            ORDER BY size DESC",
            group_id
        )
    } else {
        "CALL algo.wcc({
            nodeLabels: [],
            relationshipTypes: []
        })
        YIELD node, componentId
        RETURN componentId, count(*) as size
        ORDER BY size DESC"
            .to_string()
    };

    debug!("Analyzing graph connectivity with WCC");
    let results = client.execute_query(&wcc_query, None).await?;

    if results.len() <= 1 {
        Ok(GraphConnectivity::WeaklyConnected)
    } else {
        Ok(GraphConnectivity::Disconnected)
    }
}

/// Calculate damped eigenvector centrality (PageRank-style) for non-strongly connected graphs
async fn calculate_damped_eigenvector_centrality(
    client: &FalkorClient,
    group_id: Option<&str>,
    max_iterations: u32,
    tolerance: f64,
    damping_factor: f64,
) -> Result<CentralityScores> {
    let start = Instant::now();
    info!(
        "Starting damped eigenvector centrality calculation with damping={}",
        damping_factor
    );

    // Get nodes with both in-neighbors and out-degree
    let query = if let Some(group_id) = group_id {
        format!(
            "MATCH (n) WHERE n.group_id = '{}'
             OPTIONAL MATCH (n)<-[r_in]-(m_in) WHERE m_in.group_id = '{}'
             WITH n, collect(DISTINCT m_in.uuid) as in_neighbors
             OPTIONAL MATCH (n)-[r_out]->(m_out) WHERE m_out.group_id = '{}'
             RETURN n.uuid as node, in_neighbors, count(m_out) as out_degree",
            group_id, group_id, group_id
        )
    } else {
        "MATCH (n)
         OPTIONAL MATCH (n)<-[r_in]-(m_in)
         WITH n, collect(DISTINCT m_in.uuid) as in_neighbors
         OPTIONAL MATCH (n)-[r_out]->(m_out)
         RETURN n.uuid as node, in_neighbors, count(m_out) as out_degree"
            .to_string()
    };

    let results = client.execute_query(&query, None).await?;

    let mut adjacency: HashMap<String, Vec<String>> = HashMap::new();
    let mut out_degrees: HashMap<String, f64> = HashMap::new();
    let mut all_nodes: HashSet<String> = HashSet::new();

    for record in results {
        if let Some(node_val) = record.get("node") {
            let node = falkor_value_to_string(node_val);
            all_nodes.insert(node.clone());

            // Get in-neighbors
            let in_neighbors =
                if let Some(FalkorValue::Array(neighbors_array)) = record.get("in_neighbors") {
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

            // Get out-degree
            let out_degree = if let Some(degree_val) = record.get("out_degree") {
                falkor_value_to_f64(degree_val).unwrap_or(0.0).max(1.0) // Avoid division by zero
            } else {
                1.0
            };

            adjacency.insert(node.clone(), in_neighbors);
            out_degrees.insert(node, out_degree);
        }
    }

    if all_nodes.is_empty() {
        return Err(CentralityError::NoNodesFound);
    }

    let node_count = all_nodes.len();
    let uniform_value = (1.0 - damping_factor) / node_count as f64;

    // Initialize scores uniformly
    let mut scores: HashMap<String, f64> = HashMap::new();
    for node in &all_nodes {
        scores.insert(node.clone(), 1.0 / node_count as f64);
    }

    // Power iteration with damping
    for iteration in 0..max_iterations {
        let mut new_scores: HashMap<String, f64> = HashMap::new();

        for node in &all_nodes {
            let mut score = uniform_value; // Damping term: (1-d)/N

            // Add contributions from in-neighbors
            if let Some(in_neighbors) = adjacency.get(node) {
                for neighbor in in_neighbors {
                    if let Some(neighbor_score) = scores.get(neighbor) {
                        let neighbor_out_degree = out_degrees.get(neighbor).unwrap_or(&1.0);
                        score += damping_factor * (neighbor_score / neighbor_out_degree);
                    }
                }
            }

            new_scores.insert(node.clone(), score);
        }

        // Calculate convergence (L1 and max difference)
        let mut l1_diff = 0.0;
        let mut max_diff: f64 = 0.0;

        for node in &all_nodes {
            let old_score = scores.get(node).unwrap_or(&0.0);
            let new_score = new_scores.get(node).unwrap_or(&0.0);
            let diff = (old_score - new_score).abs();
            l1_diff += diff;
            max_diff = max_diff.max(diff);
        }

        let avg_diff = l1_diff / node_count as f64;
        debug!(
            "Iteration {}: L1 avg={:.8}, max diff={:.8}",
            iteration + 1,
            avg_diff,
            max_diff
        );

        scores = new_scores;

        // Enhanced convergence criteria
        if avg_diff < tolerance && max_diff < tolerance * 10.0 {
            info!(
                "Damped eigenvector centrality converged after {} iterations",
                iteration + 1
            );
            break;
        }
    }

    let duration = start.elapsed();
    info!(
        "Damped eigenvector centrality calculation completed in {:?} for {} nodes",
        duration, node_count
    );

    Ok(CentralityScores {
        scores,
        nodes_processed: node_count,
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

    // Always recalculate fresh — pre-computed check removed due to feedback loop
    // where garbage values from failed runs get read back, perpetuating bad data.

    // Analyze graph connectivity to choose appropriate algorithm
    let connectivity = analyze_graph_connectivity(client, group_id).await?;

    match connectivity {
        GraphConnectivity::WeaklyConnected => {
            info!("Graph is weakly connected, using pure eigenvector centrality");
            calculate_pure_eigenvector_centrality(client, group_id, max_iterations, tolerance).await
        }
        GraphConnectivity::Disconnected => {
            info!("Graph has multiple components, using damped eigenvector centrality");
            calculate_damped_eigenvector_centrality(
                client,
                group_id,
                max_iterations,
                tolerance,
                0.85,
            )
            .await
        }
    }
}

/// Calculate pure eigenvector centrality for strongly/weakly connected graphs
async fn calculate_pure_eigenvector_centrality(
    client: &FalkorClient,
    group_id: Option<&str>,
    max_iterations: u32,
    tolerance: f64,
) -> Result<CentralityScores> {
    let start = Instant::now();
    info!("Starting pure eigenvector centrality calculation");

    // First, get all nodes and their incoming connections (for eigenvector centrality)
    let adjacency_query = if let Some(group_id) = group_id {
        format!(
            "MATCH (n) WHERE n.group_id = '{}' 
             OPTIONAL MATCH (n)<-[r]-(m)
             WHERE m.group_id = '{}'
             RETURN n.uuid as node, collect(DISTINCT m.uuid) as in_neighbors",
            group_id, group_id
        )
    } else {
        "MATCH (n)
         OPTIONAL MATCH (n)<-[r]-(m)
         RETURN n.uuid as node, collect(DISTINCT m.uuid) as in_neighbors"
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

            // Get in-neighbors (nodes that point to this node)
            let neighbors =
                if let Some(FalkorValue::Array(neighbors_array)) = record.get("in_neighbors") {
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
        let norm: f64 = new_scores.values().map(|s| s * s).sum::<f64>().sqrt();

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

        // Enhanced convergence check (L1 and max difference)
        let mut l1_diff = 0.0;
        let mut max_diff: f64 = 0.0;

        for node in &all_nodes {
            let old_score = scores.get(node).unwrap_or(&0.0);
            let new_score = new_scores.get(node).unwrap_or(&0.0);
            let diff = (old_score - new_score).abs();
            l1_diff += diff;
            max_diff = max_diff.max(diff);
        }

        let avg_diff = l1_diff / node_count as f64;
        debug!(
            "Iteration {}: L1 avg={:.8}, max diff={:.8}",
            iteration + 1,
            avg_diff,
            max_diff
        );

        // Update scores for next iteration
        scores = new_scores;

        // Enhanced convergence criteria - both L1 and max difference must be small
        if avg_diff < tolerance && max_diff < tolerance * 10.0 {
            info!(
                "Pure eigenvector centrality converged after {} iterations",
                iteration + 1
            );
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
        let degree_normalized = if max_degree > 0.0 {
            degree_raw / max_degree
        } else {
            0.0
        };
        node_scores.insert("degree".to_string(), degree_normalized);

        // Betweenness is already normalized in the approximation function
        let betweenness_score = betweenness.scores.get(&node_id).copied().unwrap_or(0.0);
        node_scores.insert("betweenness".to_string(), betweenness_score);

        // True eigenvector centrality (already normalized by power iteration)
        let eigenvector_score = eigenvector.scores.get(&node_id).copied().unwrap_or(0.0);
        node_scores.insert("eigenvector".to_string(), eigenvector_score);

        // Calculate importance as a weighted combination
        // This is a composite metric, not eigenvector centrality
        let importance = (0.4 * pagerank_score
            + 0.3 * eigenvector_score
            + 0.2 * degree_normalized
            + 0.1 * betweenness_score)
            .min(1.0);
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
