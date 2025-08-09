use crate::error::SearchResult;
use crate::falkor::FalkorConnection;
use crate::models::{Node, Edge};
use std::collections::{HashSet, VecDeque};
use tracing::instrument;

/// Perform breadth-first search from origin nodes
#[instrument(skip(conn))]
pub async fn bfs_search_nodes(
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
#[instrument(skip(conn))]
pub async fn bfs_search_edges(
    conn: &mut FalkorConnection,
    origin_uuids: &[String],
    max_depth: usize,
    limit: usize,
) -> SearchResult<Vec<Edge>> {
    // This would require a more complex query to get edges along BFS paths
    // For now, returning empty vector
    Ok(vec![])
}

/// Calculate shortest paths between nodes using BFS
pub fn calculate_shortest_paths(
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
pub fn find_nodes_within_distance(
    adjacency_list: &std::collections::HashMap<String, Vec<String>>,
    origin_nodes: &[String],
    max_distance: usize,
) -> HashSet<String> {
    let mut result = HashSet::new();
    let mut visited = HashSet::new();
    let mut queue = VecDeque::new();
    
    // Initialize with origin nodes
    for origin in origin_nodes {
        queue.push_back((origin.clone(), 0));
        visited.insert(origin.clone());
        result.insert(origin.clone());
    }
    
    // BFS traversal
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
        
        let distances = calculate_shortest_paths(&adjacency, "A");
        
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
        
        let nodes = find_nodes_within_distance(&adjacency, &["A".to_string()], 2);
        
        assert!(nodes.contains("A"));
        assert!(nodes.contains("B"));
        assert!(nodes.contains("C"));
        assert!(nodes.contains("D"));
        assert!(nodes.contains("E"));
    }
}