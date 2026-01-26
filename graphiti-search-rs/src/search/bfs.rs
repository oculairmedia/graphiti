use crate::error::SearchResult;
use crate::falkor::FalkorConnection;
use crate::models::{Edge, EdgeSearchConfig, Node, NodeSearchConfig};
use std::cmp::Ordering;
use std::collections::{BinaryHeap, HashMap, HashSet, VecDeque};
use tracing::{debug, instrument};

#[derive(Debug, Clone)]
struct ScoredNode {
    uuid: String,
    score: f32,
    distance: usize,
}

impl PartialEq for ScoredNode {
    fn eq(&self, other: &Self) -> bool {
        self.score == other.score
    }
}

impl Eq for ScoredNode {}

impl PartialOrd for ScoredNode {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for ScoredNode {
    fn cmp(&self, other: &Self) -> Ordering {
        self.partial_cmp(other).unwrap_or(Ordering::Equal)
    }
}

#[derive(Debug, Clone)]
pub struct BfsConfig {
    pub beam_width: usize,
    pub per_hop_limit: usize,
    pub max_expansions: usize,
    pub max_visited: usize,
    pub max_depth: usize,
    pub hub_degree_threshold: usize,
    pub decay: f32,
    pub min_score_cutoff: f32,
}

impl Default for BfsConfig {
    fn default() -> Self {
        Self {
            beam_width: 50,
            per_hop_limit: 100,
            max_expansions: 500,
            max_visited: 1000,
            max_depth: 3,
            hub_degree_threshold: 200,
            decay: 0.85,
            min_score_cutoff: 0.1,
        }
    }
}

impl From<&NodeSearchConfig> for BfsConfig {
    fn from(config: &NodeSearchConfig) -> Self {
        Self {
            beam_width: config.bfs_beam_width.unwrap_or(50),
            per_hop_limit: config.bfs_per_hop_limit.unwrap_or(100),
            max_expansions: config.bfs_max_expansions.unwrap_or(500),
            max_visited: config.bfs_max_visited.unwrap_or(1000),
            max_depth: config.bfs_max_depth,
            hub_degree_threshold: config.bfs_hub_degree_threshold.unwrap_or(200),
            decay: config.hipporag_decay.unwrap_or(0.85),
            min_score_cutoff: config.bfs_min_score_cutoff.unwrap_or(0.1),
        }
    }
}

impl From<&EdgeSearchConfig> for BfsConfig {
    fn from(config: &EdgeSearchConfig) -> Self {
        Self {
            beam_width: config.bfs_beam_width.unwrap_or(50),
            per_hop_limit: config.bfs_per_hop_limit.unwrap_or(100),
            max_expansions: config.bfs_max_expansions.unwrap_or(500),
            max_visited: config.bfs_max_visited.unwrap_or(1000),
            max_depth: config.bfs_max_depth,
            hub_degree_threshold: config.bfs_hub_degree_threshold.unwrap_or(200),
            decay: config.hipporag_decay.unwrap_or(0.85),
            min_score_cutoff: config.bfs_min_score_cutoff.unwrap_or(0.1),
        }
    }
}

#[instrument(skip(conn))]
pub async fn search_nodes_bfs(
    conn: &mut FalkorConnection,
    seed_nodes: Vec<Node>,
    config: &BfsConfig,
    group_ids: Option<&[String]>,
) -> SearchResult<Vec<Node>> {
    if seed_nodes.is_empty() {
        debug!("BFS: No seed nodes provided");
        return Ok(Vec::new());
    }

    let mut frontier = BinaryHeap::new();
    let mut visited = HashSet::new();
    let mut best_scores: HashMap<String, f32> = HashMap::new();
    let mut expansions = 0usize;

    for node in seed_nodes {
        let initial_score = node.score.unwrap_or(1.0);
        frontier.push(ScoredNode {
            uuid: node.uuid.to_string(),
            score: initial_score,
            distance: 0,
        });
        best_scores.insert(node.uuid.to_string(), initial_score);
    }

    while let Some(current) = frontier.pop() {
        if visited.contains(&current.uuid) {
            continue;
        }

        if visited.len() >= config.max_visited {
            debug!("BFS: Reached max_visited limit ({})", config.max_visited);
            break;
        }

        if current.distance >= config.max_depth {
            continue;
        }

        if current.score < config.min_score_cutoff {
            debug!(
                "BFS: Score {} below cutoff {}",
                current.score, config.min_score_cutoff
            );
            continue;
        }

        visited.insert(current.uuid.clone());
        expansions += 1;

        if expansions >= config.max_expansions {
            debug!(
                "BFS: Reached max_expansions limit ({})",
                config.max_expansions
            );
            break;
        }

        let neighbors_result = conn
            .get_node_neighbors(std::slice::from_ref(&current.uuid))
            .await
            .map_err(|e| crate::error::SearchError::Database(e.to_string()))?;

        let mut neighbor_uuids: Vec<String> = neighbors_result
            .into_iter()
            .map(|(_, target)| target)
            .collect::<HashSet<_>>()
            .into_iter()
            .collect();

        if neighbor_uuids.len() > config.hub_degree_threshold {
            debug!(
                "BFS: Hub node {} has {} neighbors, limiting to {}",
                current.uuid,
                neighbor_uuids.len(),
                config.per_hop_limit
            );
            neighbor_uuids.truncate(config.per_hop_limit);
        } else {
            neighbor_uuids.truncate(config.per_hop_limit);
        }

        let next_distance = current.distance + 1;
        let decay_factor = config.decay.powi(next_distance as i32);

        let mut scored_neighbors = Vec::new();
        for neighbor_uuid in neighbor_uuids {
            if visited.contains(&neighbor_uuid) {
                continue;
            }

            let neighbor_score = current.score * decay_factor;

            let existing_score = best_scores.get(&neighbor_uuid).copied().unwrap_or(0.0);
            if neighbor_score > existing_score {
                best_scores.insert(neighbor_uuid.clone(), neighbor_score);
                scored_neighbors.push(ScoredNode {
                    uuid: neighbor_uuid,
                    score: neighbor_score,
                    distance: next_distance,
                });
            }
        }

        scored_neighbors.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(Ordering::Equal));
        scored_neighbors.truncate(config.beam_width);

        for scored in scored_neighbors {
            frontier.push(scored);
        }
    }

    debug!(
        "BFS: Visited {} nodes, performed {} expansions",
        visited.len(),
        expansions
    );

    let uuids: Vec<String> = visited.into_iter().collect();
    if uuids.is_empty() {
        return Ok(Vec::new());
    }

    let mut nodes = conn
        .get_nodes_by_uuids(&uuids, group_ids)
        .await
        .map_err(|e| crate::error::SearchError::Database(e.to_string()))?;

    for node in &mut nodes {
        if let Some(&score) = best_scores.get(&node.uuid.to_string()) {
            node.score = Some(score);
        }
    }

    nodes.sort_by(|a, b| {
        let score_a = a.score.unwrap_or(0.0);
        let score_b = b.score.unwrap_or(0.0);
        score_b.partial_cmp(&score_a).unwrap_or(Ordering::Equal)
    });

    Ok(nodes)
}

pub async fn search_edges_bfs(
    conn: &mut FalkorConnection,
    seed_edges: Vec<Edge>,
    config: &BfsConfig,
    group_ids: Option<&[String]>,
) -> SearchResult<Vec<Edge>> {
    if seed_edges.is_empty() {
        debug!("BFS: No seed edges provided");
        return Ok(Vec::new());
    }

    let mut seed_node_uuids = HashSet::new();
    for edge in &seed_edges {
        seed_node_uuids.insert(edge.source_node_uuid.to_string());
        seed_node_uuids.insert(edge.target_node_uuid.to_string());
    }

    let seed_nodes_vec: Vec<String> = seed_node_uuids.into_iter().collect();
    let nodes = conn
        .get_nodes_by_uuids(&seed_nodes_vec, group_ids)
        .await
        .map_err(|e| crate::error::SearchError::Database(e.to_string()))?;

    let nodes_with_score: Vec<Node> = nodes
        .into_iter()
        .map(|mut n| {
            n.score = Some(1.0);
            n
        })
        .collect();

    let expanded_nodes = search_nodes_bfs(conn, nodes_with_score, config, group_ids).await?;

    if expanded_nodes.is_empty() {
        return Ok(Vec::new());
    }

    let node_uuids: Vec<String> = expanded_nodes.iter().map(|n| n.uuid.to_string()).collect();

    let node_scores: HashMap<String, f32> = expanded_nodes
        .iter()
        .map(|n| (n.uuid.to_string(), n.score.unwrap_or(0.0)))
        .collect();

    let edges = get_edges_between_nodes(conn, &node_uuids, group_ids).await?;

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
        score_b.partial_cmp(&score_a).unwrap_or(Ordering::Equal)
    });

    Ok(scored_edges)
}

async fn get_edges_between_nodes(
    conn: &mut FalkorConnection,
    node_uuids: &[String],
    group_ids: Option<&[String]>,
) -> SearchResult<Vec<Edge>> {
    conn.get_edges_between_nodes(node_uuids, group_ids)
        .await
        .map_err(|e| crate::error::SearchError::Database(e.to_string()))
}

/// Perform breadth-first search from origin nodes
#[instrument(skip(conn))]
pub async fn _bfs_search_nodes(
    conn: &mut FalkorConnection,
    origin_uuids: &[String],
    max_depth: usize,
    limit: usize,
) -> SearchResult<Vec<Node>> {
    conn.bfs_search_nodes(origin_uuids, max_depth, limit)
        .await
        .map_err(|e| crate::error::SearchError::Database(e.to_string()))
}

/// Perform BFS to find edges within a certain depth
#[instrument(skip(_conn))]
pub async fn _bfs_search_edges(
    _conn: &mut FalkorConnection,
    _origin_uuids: &[String],
    _max_depth: usize,
    _limit: usize,
) -> SearchResult<Vec<Edge>> {
    Ok(vec![])
}

/// Calculate shortest paths between nodes using BFS
pub fn _calculate_shortest_paths(
    adjacency_list: &std::collections::HashMap<String, Vec<String>>,
    start_node: &str,
) -> std::collections::HashMap<String, usize> {
    let mut distances = std::collections::HashMap::new();
    let mut visited = HashSet::new();
    let mut queue = VecDeque::new();

    distances.insert(start_node.to_string(), 0);
    visited.insert(start_node.to_string());
    queue.push_back(start_node.to_string());

    while let Some(current) = queue.pop_front() {
        let current_distance = *distances.get(&current).unwrap();

        if let Some(neighbors) = adjacency_list.get(&current) {
            for neighbor in neighbors {
                if !visited.contains(neighbor) {
                    visited.insert(neighbor.clone());
                    distances.insert(neighbor.clone(), current_distance + 1);
                    queue.push_back(neighbor.clone());
                }
            }
        }
    }

    distances
}

/// Find nodes within a certain distance from origin nodes
pub fn _find_nodes_within_distance(
    adjacency_list: &std::collections::HashMap<String, Vec<String>>,
    origin_nodes: &[String],
    max_distance: usize,
) -> HashSet<String> {
    let mut result = HashSet::new();
    let mut visited = HashSet::new();
    let mut queue = VecDeque::new();

    for origin in origin_nodes {
        queue.push_back((origin.clone(), 0));
        visited.insert(origin.clone());
        result.insert(origin.clone());
    }

    while let Some((current, distance)) = queue.pop_front() {
        if distance >= max_distance {
            continue;
        }

        if let Some(neighbors) = adjacency_list.get(&current) {
            for neighbor in neighbors {
                if !visited.contains(neighbor) {
                    visited.insert(neighbor.clone());
                    result.insert(neighbor.clone());
                    queue.push_back((neighbor.clone(), distance + 1));
                }
            }
        }
    }

    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    #[test]
    fn test_shortest_paths() {
        let mut adjacency = HashMap::new();
        adjacency.insert("A".to_string(), vec!["B".to_string(), "C".to_string()]);
        adjacency.insert("B".to_string(), vec!["D".to_string()]);
        adjacency.insert("C".to_string(), vec!["D".to_string()]);
        adjacency.insert("D".to_string(), vec![]);

        let distances = _calculate_shortest_paths(&adjacency, "A");

        assert_eq!(distances.get("A"), Some(&0));
        assert_eq!(distances.get("B"), Some(&1));
        assert_eq!(distances.get("C"), Some(&1));
        assert_eq!(distances.get("D"), Some(&2));
    }

    #[test]
    fn test_nodes_within_distance() {
        let mut adjacency = HashMap::new();
        adjacency.insert("A".to_string(), vec!["B".to_string(), "C".to_string()]);
        adjacency.insert("B".to_string(), vec!["D".to_string()]);
        adjacency.insert("C".to_string(), vec!["E".to_string()]);

        let nodes = _find_nodes_within_distance(&adjacency, &["A".to_string()], 2);

        assert!(nodes.contains("A"));
        assert!(nodes.contains("B"));
        assert!(nodes.contains("C"));
        assert!(nodes.contains("D"));
        assert!(nodes.contains("E"));
    }
}
