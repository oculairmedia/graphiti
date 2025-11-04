// Common test utilities and fixtures
use graph_visualizer_backend::{Node, Edge};
use serde_json::json;
use std::collections::HashMap;

/// Create a test node with default values
pub fn create_test_node(id: &str, label: &str, node_type: &str) -> Node {
    let mut properties = HashMap::new();
    properties.insert("name".to_string(), json!(label));
    properties.insert("type".to_string(), json!(node_type));
    properties.insert("degree_centrality".to_string(), json!(0.5));
    properties.insert("pagerank_centrality".to_string(), json!(0.3));
    properties.insert("betweenness_centrality".to_string(), json!(0.2));
    properties.insert("eigenvector_centrality".to_string(), json!(0.4));
    properties.insert("created_at".to_string(), json!("2024-01-01T00:00:00Z"));
    
    Node {
        id: id.to_string(),
        label: label.to_string(),
        node_type: node_type.to_string(),
        summary: Some(format!("Test node: {}", label)),
        properties,
    }
}

/// Create a test edge with default values
pub fn create_test_edge(from: &str, to: &str, edge_type: &str) -> Edge {
    Edge {
        from: from.to_string(),
        to: to.to_string(),
        edge_type: edge_type.to_string(),
        weight: 1.0,
    }
}

/// Generate a small test graph
pub fn generate_test_graph() -> (Vec<Node>, Vec<Edge>) {
    let nodes = vec![
        create_test_node("node1", "Alice", "Person"),
        create_test_node("node2", "Bob", "Person"),
        create_test_node("node3", "Company", "Organization"),
    ];
    
    let edges = vec![
        create_test_edge("node1", "node2", "KNOWS"),
        create_test_edge("node1", "node3", "WORKS_AT"),
        create_test_edge("node2", "node3", "WORKS_AT"),
    ];
    
    (nodes, edges)
}

/// Generate a large test graph for performance testing
pub fn generate_large_test_graph(node_count: usize, edge_count: usize) -> (Vec<Node>, Vec<Edge>) {
    let nodes: Vec<Node> = (0..node_count)
        .map(|i| create_test_node(&format!("node_{}", i), &format!("Node {}", i), "TestType"))
        .collect();
    
    let edges: Vec<Edge> = (0..edge_count)
        .map(|i| {
            let from = format!("node_{}", i % node_count);
            let to = format!("node_{}", (i + 1) % node_count);
            create_test_edge(&from, &to, "TEST_EDGE")
        })
        .collect();
    
    (nodes, edges)
}

/// Create a temporary DuckDB database for testing
pub fn create_temp_duckdb() -> tempfile::TempDir {
    tempfile::tempdir().expect("Failed to create temp dir")
}

/// Setup test logger for debugging tests
pub fn setup_test_logger() {
    let _ = tracing_subscriber::fmt()
        .with_env_filter("debug")
        .with_test_writer()
        .try_init();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_create_test_node() {
        let node = create_test_node("test1", "TestNode", "TestType");
        assert_eq!(node.id, "test1");
        assert_eq!(node.label, "TestNode");
        assert_eq!(node.node_type, "TestType");
        assert!(node.summary.is_some());
    }

    #[test]
    fn test_create_test_edge() {
        let edge = create_test_edge("node1", "node2", "TEST");
        assert_eq!(edge.from, "node1");
        assert_eq!(edge.to, "node2");
        assert_eq!(edge.edge_type, "TEST");
        assert_eq!(edge.weight, 1.0);
    }

    #[test]
    fn test_generate_test_graph() {
        let (nodes, edges) = generate_test_graph();
        assert_eq!(nodes.len(), 3);
        assert_eq!(edges.len(), 3);
    }

    #[test]
    fn test_generate_large_test_graph() {
        let (nodes, edges) = generate_large_test_graph(100, 200);
        assert_eq!(nodes.len(), 100);
        assert_eq!(edges.len(), 200);
    }
}
