// Integration tests for DuckDB store
mod common;

use common::{create_test_node, create_test_edge, generate_test_graph, create_temp_duckdb, setup_test_logger};
use graph_visualizer_backend::duckdb_store::DuckDBStore;

#[cfg(test)]
mod duckdb_store_tests {
    use super::*;

    #[tokio::test]
    async fn test_store_initialization() {
        setup_test_logger();
        
        // Initialize DuckDBStore with temp database
        let temp_dir = create_temp_duckdb();
        let db_path = temp_dir.path().join("test.db");
        let store = DuckDBStore::new_with_path(Some(db_path.to_str().unwrap()));
        
        // Verify store was created successfully
        assert!(store.is_ok(), "Failed to create DuckDBStore: {:?}", store.err());
    }

    #[tokio::test]
    async fn test_load_initial_data() {
        setup_test_logger();
        
        // Create store and load test data
        let (nodes, edges) = generate_test_graph();
        let temp_dir = create_temp_duckdb();
        let db_path = temp_dir.path().join("test.db");
        let store = DuckDBStore::new_with_path(Some(db_path.to_str().unwrap()))
            .expect("Failed to create store");
        
        // Load data
        let result = store.load_initial_data(nodes.clone(), edges.clone()).await;
        assert!(result.is_ok(), "Failed to load initial data: {:?}", result.err());
        
        // Verify data was loaded - we can't easily query the count, but loading should succeed
        println!("Successfully loaded {} nodes and {} edges", nodes.len(), edges.len());
    }

    #[tokio::test]
    async fn test_load_initial_data_with_empty_graph() {
        setup_test_logger();
        
        // Test loading empty graph
        let temp_dir = create_temp_duckdb();
        let db_path = temp_dir.path().join("test.db");
        let store = DuckDBStore::new_with_path(Some(db_path.to_str().unwrap()))
            .expect("Failed to create store");
        
        let result = store.load_initial_data(vec![], vec![]).await;
        assert!(result.is_ok(), "Failed to load empty graph: {:?}", result.err());
        
        println!("Successfully loaded empty graph");
    }

    #[tokio::test]
    async fn test_incremental_update_new_nodes() {
        setup_test_logger();
        
        // Test incremental update with new nodes using queue system
        let (initial_nodes, initial_edges) = generate_test_graph();
        let temp_dir = create_temp_duckdb();
        let db_path = temp_dir.path().join("test.db");
        let store = DuckDBStore::new_with_path(Some(db_path.to_str().unwrap()))
            .expect("Failed to create store");
        
        // 1. Load initial data
        store.load_initial_data(initial_nodes.clone(), initial_edges.clone())
            .await
            .expect("Failed to load initial data");
        
        // 2. Add new nodes via queue
        let new_node = create_test_node("node4", "Charlie", "Person");
        store.queue_nodes(vec![new_node.clone()]).await;
        
        // 3. Process updates
        let update_result = store.process_updates().await;
        assert!(update_result.is_ok(), "Failed to process updates: {:?}", update_result.err());
        
        println!("Successfully queued and processed new node: {}", new_node.id);
    }

    #[tokio::test]
    async fn test_incremental_update_existing_nodes() {
        setup_test_logger();
        
        // Test updating existing nodes
        let (mut initial_nodes, initial_edges) = generate_test_graph();
        let temp_dir = create_temp_duckdb();
        let db_path = temp_dir.path().join("test.db");
        let store = DuckDBStore::new_with_path(Some(db_path.to_str().unwrap()))
            .expect("Failed to create store");
        
        // 1. Load initial data
        store.load_initial_data(initial_nodes.clone(), initial_edges.clone())
            .await
            .expect("Failed to load initial data");
        
        // 2. Update node with changed properties
        if let Some(node) = initial_nodes.get_mut(0) {
            node.label = "Alice Updated".to_string();
            node.properties.insert("updated".to_string(), serde_json::json!(true));
            
            store.queue_node_update(node.clone()).await;
            
            // 3. Process updates
            let update_result = store.process_updates().await;
            assert!(update_result.is_ok(), "Failed to process updates: {:?}", update_result.err());
            
            println!("Successfully updated node: {}", node.id);
        }
    }

    #[tokio::test]
    async fn test_query_nodes_by_type() {
        setup_test_logger();
        
        // TODO: Test querying nodes by type
        // 1. Load mixed node types
        // 2. Query for specific type
        // 3. Verify only matching nodes returned
    }

    #[tokio::test]
    async fn test_query_nodes_by_centrality() {
        setup_test_logger();
        
        // TODO: Test centrality-based queries
    }

    #[tokio::test]
    async fn test_concurrent_reads() {
        setup_test_logger();
        
        // TODO: Test multiple concurrent read operations
        // Use tokio::join! or similar to simulate concurrent access
    }

    #[tokio::test]
    async fn test_node_with_special_characters() {
        setup_test_logger();
        
        // TODO: Test SQL injection prevention
        // Create nodes with quotes, semicolons, etc.
    }

    #[tokio::test]
    async fn test_large_batch_insert() {
        setup_test_logger();
        
        // TODO: Test performance with large batches
        // Generate 10K+ nodes and measure time
    }
}

#[cfg(test)]
mod duckdb_edge_tests {
    use super::*;

    #[tokio::test]
    async fn test_edge_insertion() {
        setup_test_logger();
        
        // TODO: Test edge insertion with valid source/target
    }

    #[tokio::test]
    async fn test_edge_insertion_missing_nodes() {
        setup_test_logger();
        
        // TODO: Test edge insertion with invalid node references
        // Should handle gracefully or error
    }

    #[tokio::test]
    async fn test_duplicate_edge_handling() {
        setup_test_logger();
        
        // TODO: Test INSERT OR IGNORE behavior for duplicate edges
    }

    #[tokio::test]
    async fn test_edge_query_by_type() {
        setup_test_logger();
        
        // TODO: Query edges by type
    }
}
