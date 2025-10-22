use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Represents a graph node from Neo4j/FalkorDB
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphNode {
    /// Unique identifier (UUID)
    pub uuid: String,

    /// Node labels (e.g., "Entity", "Episodic", "Community")
    pub labels: Vec<String>,

    /// Node properties as key-value pairs
    pub properties: HashMap<String, PropertyValue>,
}

/// Property value that can be of various types
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum PropertyValue {
    String(String),
    Integer(i64),
    Float(f64),
    Boolean(bool),
    List(Vec<PropertyValue>),
    Null,
}

impl GraphNode {
    pub fn new(uuid: String, labels: Vec<String>) -> Self {
        Self {
            uuid,
            labels,
            properties: HashMap::new(),
        }
    }

    pub fn with_property(mut self, key: String, value: PropertyValue) -> Self {
        self.properties.insert(key, value);
        self
    }

    /// Get node type from labels (Entity, Episodic, or Community)
    pub fn node_type(&self) -> Option<&str> {
        self.labels
            .iter()
            .find(|&label| matches!(label.as_str(), "Entity" | "Episodic" | "Community"))
            .map(|s| s.as_str())
    }
}

impl PropertyValue {
    /// Convert to string for Cypher query
    pub fn to_cypher_value(&self) -> String {
        match self {
            PropertyValue::String(s) => format!("\"{}\"", s.replace('"', "\\\"")),
            PropertyValue::Integer(i) => i.to_string(),
            PropertyValue::Float(f) => f.to_string(),
            PropertyValue::Boolean(b) => b.to_string(),
            PropertyValue::List(items) => {
                let values: Vec<String> = items.iter().map(|v| v.to_cypher_value()).collect();
                format!("[{}]", values.join(", "))
            }
            PropertyValue::Null => "null".to_string(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_node_creation() {
        let node = GraphNode::new("test-uuid".to_string(), vec!["Entity".to_string()]);

        assert_eq!(node.uuid, "test-uuid");
        assert_eq!(node.labels, vec!["Entity"]);
        assert_eq!(node.node_type(), Some("Entity"));
    }

    #[test]
    fn test_property_value_cypher() {
        assert_eq!(
            PropertyValue::String("test".to_string()).to_cypher_value(),
            "\"test\""
        );
        assert_eq!(PropertyValue::Integer(42).to_cypher_value(), "42");
        assert_eq!(PropertyValue::Boolean(true).to_cypher_value(), "true");
    }
}
