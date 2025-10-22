use super::node::PropertyValue;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Represents a graph edge/relationship from Neo4j/FalkorDB
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphEdge {
    /// Source node UUID
    pub source_uuid: String,

    /// Target node UUID
    pub target_uuid: String,

    /// Relationship type (e.g., "RELATES_TO", "MENTIONS")
    pub relationship_type: String,

    /// Edge properties as key-value pairs
    pub properties: HashMap<String, PropertyValue>,
}

impl GraphEdge {
    pub fn new(source_uuid: String, target_uuid: String, relationship_type: String) -> Self {
        Self {
            source_uuid,
            target_uuid,
            relationship_type,
            properties: HashMap::new(),
        }
    }

    pub fn with_property(mut self, key: String, value: PropertyValue) -> Self {
        self.properties.insert(key, value);
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_edge_creation() {
        let edge = GraphEdge::new(
            "uuid-1".to_string(),
            "uuid-2".to_string(),
            "RELATES_TO".to_string(),
        );

        assert_eq!(edge.source_uuid, "uuid-1");
        assert_eq!(edge.target_uuid, "uuid-2");
        assert_eq!(edge.relationship_type, "RELATES_TO");
    }
}
