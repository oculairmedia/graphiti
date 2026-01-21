use crate::error::{SearchError, SearchResult};
use crate::falkor::FalkorConnection;
use crate::models::{Node, SearchFilters};
use std::collections::HashMap;
use tracing::{debug, instrument};

#[derive(Debug, Clone)]
pub struct HippoRAGConfig {
    pub max_hops: usize,
    pub decay: f32,
    pub seed_count: usize,
    pub min_score: f32,
}

impl Default for HippoRAGConfig {
    fn default() -> Self {
        Self {
            max_hops: 2,
            decay: 0.85,
            seed_count: 10,
            min_score: 0.1,
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
) -> SearchResult<Vec<Node>> {
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

    let activated = spread_activation(conn, &seeds, config).await?;

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

    debug!("HippoRAG: Returning {} activated nodes", nodes.len());
    Ok(nodes)
}

/// Spreading activation algorithm: propagates scores from seed nodes through the graph.
/// Score formula: neighbor_score = max(current_score, source_score * decay)
async fn spread_activation(
    conn: &mut FalkorConnection,
    seeds: &[(String, f32)],
    config: &HippoRAGConfig,
) -> SearchResult<HashMap<String, f32>> {
    let mut activation_scores: HashMap<String, f32> = HashMap::new();

    for (uuid, score) in seeds {
        activation_scores.insert(uuid.clone(), *score);
    }

    let mut frontier: Vec<(String, f32)> = seeds.to_vec();

    for hop in 0..config.max_hops {
        if frontier.is_empty() {
            break;
        }

        let frontier_uuids: Vec<String> = frontier.iter().map(|(uuid, _)| uuid.clone()).collect();

        let neighbors = conn
            .get_node_neighbors(&frontier_uuids)
            .await
            .map_err(|e| SearchError::Database(format!("Neighbor query failed: {}", e)))?;

        debug!(
            "HippoRAG hop {}: {} frontier nodes, {} neighbor edges",
            hop,
            frontier.len(),
            neighbors.len()
        );

        let mut next_frontier: HashMap<String, f32> = HashMap::new();

        for (source_uuid, target_uuid) in neighbors {
            let source_score = match activation_scores.get(&source_uuid) {
                Some(s) => *s,
                None => continue,
            };

            let propagated_score = source_score * config.decay;
            let current_target_score = activation_scores.get(&target_uuid).copied().unwrap_or(0.0);

            if propagated_score > current_target_score {
                activation_scores.insert(target_uuid.clone(), propagated_score);
                next_frontier
                    .entry(target_uuid)
                    .and_modify(|s| *s = s.max(propagated_score))
                    .or_insert(propagated_score);
            }
        }

        frontier = next_frontier.into_iter().collect();
    }

    Ok(activation_scores)
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
