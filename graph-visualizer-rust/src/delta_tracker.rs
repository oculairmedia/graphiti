use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use serde::{Serialize, Deserialize};
use crate::{Node, Edge};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphDelta {
    pub operation: DeltaOperation,
    pub nodes_added: Vec<Node>,
    pub nodes_updated: Vec<Node>,
    pub nodes_removed: Vec<String>,
    pub edges_added: Vec<Edge>,
    pub edges_updated: Vec<Edge>,
    pub edges_removed: Vec<(String, String)>,
    pub timestamp: u64,
    pub sequence: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DeltaOperation {
    Initial,
    Update,
    Refresh,
}

#[derive(Clone)]
pub struct DeltaTracker {
    current_nodes: Arc<RwLock<HashMap<String, Node>>>,
    current_edges: Arc<RwLock<HashMap<(String, String), Edge>>>,
    sequence_counter: Arc<RwLock<u64>>,
}

impl DeltaTracker {
    pub fn new() -> Self {
        Self {
            current_nodes: Arc::new(RwLock::new(HashMap::new())),
            current_edges: Arc::new(RwLock::new(HashMap::new())),
            sequence_counter: Arc::new(RwLock::new(0)),
        }
    }
    
    pub async fn compute_delta(&self, new_nodes: Vec<Node>, new_edges: Vec<Edge>) -> GraphDelta {
        let mut nodes_added = Vec::new();
        let mut nodes_updated = Vec::new();
        let mut nodes_removed = Vec::new();
        let mut edges_added = Vec::new();
        let mut edges_updated = Vec::new();
        let mut edges_removed = Vec::new();
        
        // Get current state
        let current_nodes = self.current_nodes.read().await;
        let current_edges = self.current_edges.read().await;
        
        // Create maps for new data
        let new_nodes_map: HashMap<String, Node> = new_nodes
            .into_iter()
            .map(|n| (n.id.clone(), n))
            .collect();
        
        let new_edges_map: HashMap<(String, String), Edge> = new_edges
            .into_iter()
            .map(|e| ((e.from.clone(), e.to.clone()), e))
            .collect();
        
        // Find added and updated nodes
        for (id, new_node) in &new_nodes_map {
            match current_nodes.get(id) {
                Some(old_node) => {
                    if !nodes_equal(old_node, new_node) {
                        nodes_updated.push(new_node.clone());
                    }
                }
                None => {
                    nodes_added.push(new_node.clone());
                }
            }
        }
        
        // Find removed nodes
        for id in current_nodes.keys() {
            if !new_nodes_map.contains_key(id) {
                nodes_removed.push(id.clone());
            }
        }
        
        // Find added and updated edges
        for (key, new_edge) in &new_edges_map {
            match current_edges.get(key) {
                Some(old_edge) => {
                    if !edges_equal(old_edge, new_edge) {
                        edges_updated.push(new_edge.clone());
                    }
                }
                None => {
                    edges_added.push(new_edge.clone());
                }
            }
        }
        
        // Find removed edges
        for key in current_edges.keys() {
            if !new_edges_map.contains_key(key) {
                edges_removed.push(key.clone());
            }
        }
        
        // Update current state
        drop(current_nodes);
        drop(current_edges);
        
        let mut nodes_write = self.current_nodes.write().await;
        let mut edges_write = self.current_edges.write().await;
        
        *nodes_write = new_nodes_map;
        *edges_write = new_edges_map;
        
        // Increment sequence counter
        let mut seq = self.sequence_counter.write().await;
        *seq += 1;
        let sequence = *seq;
        
        GraphDelta {
            operation: if sequence == 1 { DeltaOperation::Initial } else { DeltaOperation::Update },
            nodes_added,
            nodes_updated,
            nodes_removed,
            edges_added,
            edges_updated,
            edges_removed,
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_millis() as u64,
            sequence,
        }
    }
    
    pub async fn reset(&self) {
        let mut nodes = self.current_nodes.write().await;
        let mut edges = self.current_edges.write().await;
        let mut seq = self.sequence_counter.write().await;
        
        nodes.clear();
        edges.clear();
        *seq = 0;
    }
    
    pub async fn get_stats(&self) -> (usize, usize, u64) {
        let nodes = self.current_nodes.read().await;
        let edges = self.current_edges.read().await;
        let seq = self.sequence_counter.read().await;
        
        (nodes.len(), edges.len(), *seq)
    }
    
    pub async fn get_current_sequence(&self) -> u64 {
        let seq = self.sequence_counter.read().await;
        *seq
    }
    
    pub async fn get_changes_since(&self, _since_sequence: u64, _limit: usize) -> Vec<GraphDelta> {
        // TODO: Implement proper change history tracking
        // For now, return empty list as we don't store historical deltas yet
        // This would require storing a history of deltas in memory or database
        vec![]
    }
}

fn nodes_equal(a: &Node, b: &Node) -> bool {
    // Compare all relevant fields
    a.id == b.id &&
    a.label == b.label &&
    a.node_type == b.node_type &&
    a.summary == b.summary &&
    properties_equal_map(&a.properties, &b.properties)
}

fn edges_equal(a: &Edge, b: &Edge) -> bool {
    a.from == b.from &&
    a.to == b.to &&
    a.edge_type == b.edge_type &&
    (a.weight - b.weight).abs() < 0.001 // Float comparison tolerance
}

fn properties_equal_map(a: &HashMap<String, serde_json::Value>, b: &HashMap<String, serde_json::Value>) -> bool {
    // Deep comparison of HashMap properties
    a == b
}