use crate::error::{SearchError, SearchResult};
use crate::falkor::FalkorConnection;
use crate::models::{Edge, Node, SearchFilters};
use std::collections::HashMap;
use std::time::Instant;
use tracing::{debug, instrument, warn};

#[derive(Debug, Clone)]
pub struct HippoRAGConfig {
    pub max_hops: usize,
    pub decay: f32,
    pub seed_count: usize,
    pub min_score: f32,
    pub hub_degree_threshold: usize,
    pub per_hop_limit: usize,
}

impl Default for HippoRAGConfig {
    fn default() -> Self {
        Self {
            max_hops: 2,
            decay: 0.85,
            seed_count: 10,
            min_score: 0.1,
            hub_degree_threshold: 200,
            per_hop_limit: 100,
        }
    }
}

#[instrument(skip(conn, embedding))]
pub async fn search_nodes_hipporag(
    conn: &mut FalkorConnection,
    embedding: &[f32],
    config: &HippoRAGConfig,
    filters: &SearchFilters,
    limit: usize,
    timeout_ms: u64,
    batch_size: usize,
) -> SearchResult<Vec<Node>> {
    let start_time = Instant::now();

    let seeds = conn
        .hnsw_search_nodes_with_scores(embedding, config.seed_count)
        .await
        .map_err(|e| SearchError::Database(format!("HNSW seed query failed: {}", e)))?;

    if seeds.is_empty() {
        debug!("HippoRAG: No seed nodes found from HNSW search");
        return Ok(Vec::new());
    }

    debug!(
        "HippoRAG: Found {} seed nodes, spreading activation with decay={}, max_hops={}",
        seeds.len(),
        config.decay,
        config.max_hops
    );

    let activated = spread_activation(conn, &seeds, config, timeout_ms, batch_size).await?;

    let mut results: Vec<(String, f32)> = activated
        .into_iter()
        .filter(|(_, score)| *score >= config.min_score)
        .collect();

    results.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    results.truncate(limit);

    if results.is_empty() {
        return Ok(Vec::new());
    }

    let uuids: Vec<String> = results.iter().map(|(uuid, _)| uuid.clone()).collect();
    let scores: HashMap<String, f32> = results.into_iter().collect();

    let mut nodes = conn
        .get_nodes_by_uuids(&uuids, filters.group_ids.as_deref())
        .await
        .map_err(|e| SearchError::Database(format!("Node fetch failed: {}", e)))?;

    for node in &mut nodes {
        if let Some(score) = scores.get(&node.uuid.to_string()) {
            node.score = Some(*score);
        }
    }

    nodes.sort_by(|a, b| {
        b.score
            .unwrap_or(0.0)
            .partial_cmp(&a.score.unwrap_or(0.0))
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    debug!(
        "HippoRAG: Returning {} activated nodes in {:?}",
        nodes.len(),
        start_time.elapsed()
    );
    Ok(nodes)
}

/// Spreading activation with batched queries, timeout, and hub filtering.
async fn spread_activation(
    conn: &mut FalkorConnection,
    seeds: &[(String, f32)],
    config: &HippoRAGConfig,
    timeout_ms: u64,
    batch_size: usize,
) -> SearchResult<HashMap<String, f32>> {
    let start_time = Instant::now();
    let timeout = std::time::Duration::from_millis(timeout_ms);

    let mut activation_scores: HashMap<String, f32> = HashMap::new();
    let mut db_queries = 0usize;
    let mut total_neighbors_processed = 0usize;

    for (uuid, score) in seeds {
        activation_scores.insert(uuid.clone(), *score);
    }

    let mut frontier: Vec<(String, f32)> = seeds.to_vec();

    for hop in 0..config.max_hops {
        if frontier.is_empty() {
            debug!("HippoRAG: No more frontier nodes at hop {}", hop);
            break;
        }

        if start_time.elapsed() > timeout {
            warn!(
                "HippoRAG: Timeout after {:?} at hop {}, activated {} nodes",
                start_time.elapsed(),
                hop,
                activation_scores.len()
            );
            break;
        }

        let mut all_neighbors: Vec<(String, String)> = Vec::new();

        for batch_start in (0..frontier.len()).step_by(batch_size) {
            if start_time.elapsed() > timeout {
                warn!("HippoRAG: Timeout during batch processing at hop {}", hop);
                break;
            }

            let batch_end = (batch_start + batch_size).min(frontier.len());
            let batch_uuids: Vec<String> = frontier[batch_start..batch_end]
                .iter()
                .map(|(uuid, _)| uuid.clone())
                .collect();

            let neighbors = conn
                .get_node_neighbors(&batch_uuids)
                .await
                .map_err(|e| SearchError::Database(format!("Neighbor query failed: {}", e)))?;

            db_queries += 1;
            all_neighbors.extend(neighbors);
        }

        let mut source_to_neighbors: HashMap<String, Vec<String>> = HashMap::new();
        for (source, target) in all_neighbors {
            source_to_neighbors.entry(source).or_default().push(target);
        }

        let mut next_frontier: HashMap<String, f32> = HashMap::new();

        for (source_uuid, source_score) in &frontier {
            let neighbors = match source_to_neighbors.get(source_uuid) {
                Some(n) => n,
                None => continue,
            };

            let neighbor_count = neighbors.len();
            if neighbor_count > config.hub_degree_threshold {
                debug!(
                    "HippoRAG: Hub node {} has {} neighbors (threshold {}), limiting to {}",
                    source_uuid, neighbor_count, config.hub_degree_threshold, config.per_hop_limit
                );
            }

            let limit = config.per_hop_limit.min(neighbor_count);
            for target_uuid in neighbors.iter().take(limit) {
                let propagated_score = source_score * config.decay;
                let current_target_score =
                    activation_scores.get(target_uuid).copied().unwrap_or(0.0);

                if propagated_score > current_target_score {
                    activation_scores.insert(target_uuid.clone(), propagated_score);
                    next_frontier
                        .entry(target_uuid.clone())
                        .and_modify(|s| *s = s.max(propagated_score))
                        .or_insert(propagated_score);
                }
                total_neighbors_processed += 1;
            }
        }

        debug!(
            "HippoRAG hop {}: {} frontier nodes, {} neighbors processed",
            hop,
            frontier.len(),
            total_neighbors_processed
        );

        frontier = next_frontier.into_iter().collect();
    }

    debug!(
        "HippoRAG: Activated {} nodes, {} DB queries, {} neighbors processed in {:?}",
        activation_scores.len(),
        db_queries,
        total_neighbors_processed,
        start_time.elapsed()
    );

    Ok(activation_scores)
}

#[instrument(skip(conn, embedding))]
pub async fn search_edges_hipporag(
    conn: &mut FalkorConnection,
    embedding: &[f32],
    config: &HippoRAGConfig,
    filters: &SearchFilters,
    limit: usize,
    timeout_ms: u64,
    batch_size: usize,
) -> SearchResult<Vec<Edge>> {
    let start_time = Instant::now();

    let activated_nodes = search_nodes_hipporag(
        conn,
        embedding,
        config,
        filters,
        limit * 2,
        timeout_ms,
        batch_size,
    )
    .await?;

    if activated_nodes.is_empty() {
        debug!("HippoRAG edge search: No activated nodes");
        return Ok(Vec::new());
    }

    let node_uuids: Vec<String> = activated_nodes.iter().map(|n| n.uuid.to_string()).collect();

    let node_scores: HashMap<String, f32> = activated_nodes
        .iter()
        .map(|n| (n.uuid.to_string(), n.score.unwrap_or(0.0)))
        .collect();

    let edges = conn
        .get_edges_between_nodes(&node_uuids, filters.group_ids.as_deref())
        .await
        .map_err(|e| SearchError::Database(format!("Edge fetch failed: {}", e)))?;

    let mut scored_edges: Vec<Edge> = edges
        .into_iter()
        .map(|mut edge| {
            let source_score = node_scores
                .get(&edge.source_node_uuid.to_string())
                .copied()
                .unwrap_or(0.0);
            let target_score = node_scores
                .get(&edge.target_node_uuid.to_string())
                .copied()
                .unwrap_or(0.0);
            edge.score = Some((source_score + target_score) / 2.0);
            edge
        })
        .collect();

    scored_edges.sort_by(|a, b| {
        let score_a = a.score.unwrap_or(0.0);
        let score_b = b.score.unwrap_or(0.0);
        score_b
            .partial_cmp(&score_a)
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    scored_edges.truncate(limit);

    debug!(
        "HippoRAG edge search: Returning {} edges in {:?}",
        scored_edges.len(),
        start_time.elapsed()
    );

    Ok(scored_edges)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hipporag_config_defaults() {
        let config = HippoRAGConfig::default();
        assert_eq!(config.max_hops, 2);
        assert!((config.decay - 0.85).abs() < 0.001);
        assert_eq!(config.seed_count, 10);
        assert!((config.min_score - 0.1).abs() < 0.001);
        assert_eq!(config.hub_degree_threshold, 200);
        assert_eq!(config.per_hop_limit, 100);
    }

    #[test]
    fn test_decay_calculation() {
        let initial_score = 0.9f32;
        let decay = 0.85f32;

        let hop1 = initial_score * decay;
        let hop2 = hop1 * decay;

        assert!((hop1 - 0.765).abs() < 0.001);
        assert!((hop2 - 0.65025).abs() < 0.001);
    }
}
