use anyhow::{anyhow, Result};
use chrono::{DateTime, Utc};
use falkordb::{FalkorValue, LazyResultSet};
use uuid::Uuid;

use crate::models::{Edge, Episode, Node};

/// Parse nodes from FalkorDB LazyResultSet
pub fn parse_nodes_from_falkor_v2(result: LazyResultSet<'_>) -> Result<Vec<Node>> {
    let mut nodes = Vec::new();

    // Iterate over the lazy result set
    for row in result {
        // Each row can contain one or more values
        for value in row {
            if let FalkorValue::Node(falkor_node) = value {
                if let Some(node) = parse_single_node_v2(&falkor_node)? {
                    nodes.push(node);
                }
            }
        }
    }

    Ok(nodes)
}

/// Parse edges from FalkorDB LazyResultSet
pub fn parse_edges_from_falkor_v2(result: LazyResultSet<'_>) -> Result<Vec<Edge>> {
    let mut edges = Vec::new();

    // Iterate over the lazy result set
    for row in result {
        // For edge queries, we expect [source_node, edge, target_node] or [source, edge, target, score]
        if row.len() >= 3 {
            if let (FalkorValue::Node(source), FalkorValue::Edge(edge), FalkorValue::Node(target)) =
                (&row[0], &row[1], &row[2])
            {
                if let Some(parsed_edge) = parse_single_edge_v2(source, edge, target)? {
                    edges.push(parsed_edge);
                }
            }
        }
    }

    Ok(edges)
}

/// Parse episodes from FalkorDB LazyResultSet
pub fn parse_episodes_from_falkor_v2(result: LazyResultSet<'_>) -> Result<Vec<Episode>> {
    let mut episodes = Vec::new();

    // Iterate over the lazy result set
    for row in result {
        for value in row {
            if let FalkorValue::Node(falkor_node) = value {
                if let Some(episode) = parse_single_episode_v2(&falkor_node)? {
                    episodes.push(episode);
                }
            }
        }
    }

    Ok(episodes)
}

/// Parse a single node from FalkorDB Node
fn parse_single_node_v2(falkor_node: &falkordb::Node) -> Result<Option<Node>> {
    // Extract properties
    let uuid_str = get_string_property(falkor_node, "uuid")?;
    let name = get_string_property(falkor_node, "name")?;
    let node_type =
        get_string_property(falkor_node, "entity_type").unwrap_or_else(|_| "entity".to_string());
    let summary = get_optional_string_property(falkor_node, "summary");
    let group_id = get_optional_string_property(falkor_node, "group_id");
    let created_at =
        get_datetime_property(falkor_node, "created_at").unwrap_or_else(|_| Utc::now());
    let centrality = get_optional_float_property(falkor_node, "centrality").map(|f| f as f32);

    // Parse UUID
    let uuid = Uuid::parse_str(&uuid_str).map_err(|e| anyhow!("Failed to parse UUID: {}", e))?;

    Ok(Some(Node {
        uuid,
        name,
        node_type,
        summary,
        created_at,
        embedding: None, // Embeddings are not returned in queries
        group_id,
        centrality,
    }))
}

/// Parse a single edge from FalkorDB Edge with source and target nodes
fn parse_single_edge_v2(
    source: &falkordb::Node,
    falkor_edge: &falkordb::Edge,
    target: &falkordb::Node,
) -> Result<Option<Edge>> {
    // Extract edge properties
    let uuid_str = get_edge_string_property(falkor_edge, "uuid")?;
    let fact = get_edge_string_property(falkor_edge, "fact")?;
    let created_at =
        get_edge_datetime_property(falkor_edge, "created_at").unwrap_or_else(|_| Utc::now());
    let group_id = get_edge_optional_string_property(falkor_edge, "group_id");
    let weight = get_edge_optional_float_property(falkor_edge, "weight").unwrap_or(1.0) as f32;

    // Parse edge UUID
    let uuid =
        Uuid::parse_str(&uuid_str).map_err(|e| anyhow!("Failed to parse edge UUID: {}", e))?;

    // Parse source and target UUIDs
    let source_node_uuid = Uuid::parse_str(&get_string_property(source, "uuid")?)?;
    let target_node_uuid = Uuid::parse_str(&get_string_property(target, "uuid")?)?;

    // TODO: Extract episodes if they exist as a property
    let episodes = Vec::new();

    Ok(Some(Edge {
        uuid,
        source_node_uuid,
        target_node_uuid,
        fact,
        created_at,
        episodes,
        group_id,
        weight,
    }))
}

/// Parse a single episode from FalkorDB Node
fn parse_single_episode_v2(falkor_node: &falkordb::Node) -> Result<Option<Episode>> {
    // Check if this is an Episode node
    if !falkor_node.labels.contains(&"Episode".to_string()) {
        return Ok(None);
    }

    let uuid_str = get_string_property(falkor_node, "uuid")?;
    let content = get_string_property(falkor_node, "content")?;
    let created_at =
        get_datetime_property(falkor_node, "created_at").unwrap_or_else(|_| Utc::now());
    let group_id = get_optional_string_property(falkor_node, "group_id");
    let timestamp = get_optional_datetime_property(falkor_node, "timestamp");

    let uuid = Uuid::parse_str(&uuid_str)?;

    Ok(Some(Episode {
        uuid,
        content,
        created_at,
        group_id,
        timestamp,
    }))
}

// Helper functions for extracting properties from FalkorNode
fn get_string_property(node: &falkordb::Node, key: &str) -> Result<String> {
    node.properties
        .get(key)
        .and_then(|v| match v {
            FalkorValue::String(s) => Some(s.clone()),
            _ => None,
        })
        .ok_or_else(|| anyhow!("Missing property: {}", key))
}

fn get_optional_string_property(node: &falkordb::Node, key: &str) -> Option<String> {
    node.properties.get(key).and_then(|v| match v {
        FalkorValue::String(s) => Some(s.clone()),
        _ => None,
    })
}

fn get_datetime_property(node: &falkordb::Node, key: &str) -> Result<DateTime<Utc>> {
    let timestamp = node
        .properties
        .get(key)
        .and_then(|v| match v {
            FalkorValue::F64(f) => Some(*f as i64),
            FalkorValue::I64(i) => Some(*i),
            _ => None,
        })
        .ok_or_else(|| anyhow!("Missing datetime property: {}", key))?;

    Ok(DateTime::from_timestamp(timestamp, 0).unwrap_or(Utc::now()))
}

fn get_optional_datetime_property(node: &falkordb::Node, key: &str) -> Option<DateTime<Utc>> {
    node.properties
        .get(key)
        .and_then(|v| match v {
            FalkorValue::F64(f) => Some(*f as i64),
            FalkorValue::I64(i) => Some(*i),
            _ => None,
        })
        .and_then(|timestamp| DateTime::from_timestamp(timestamp, 0))
}

fn get_optional_float_property(node: &falkordb::Node, key: &str) -> Option<f64> {
    node.properties.get(key).and_then(|v| match v {
        FalkorValue::F64(f) => Some(*f),
        FalkorValue::I64(i) => Some(*i as f64),
        _ => None,
    })
}

// Helper functions for extracting properties from FalkorEdge
fn get_edge_string_property(edge: &falkordb::Edge, key: &str) -> Result<String> {
    edge.properties
        .get(key)
        .and_then(|v| match v {
            FalkorValue::String(s) => Some(s.clone()),
            _ => None,
        })
        .ok_or_else(|| anyhow!("Missing edge property: {}", key))
}

fn get_edge_optional_string_property(edge: &falkordb::Edge, key: &str) -> Option<String> {
    edge.properties.get(key).and_then(|v| match v {
        FalkorValue::String(s) => Some(s.clone()),
        _ => None,
    })
}

fn get_edge_datetime_property(edge: &falkordb::Edge, key: &str) -> Result<DateTime<Utc>> {
    let timestamp = edge
        .properties
        .get(key)
        .and_then(|v| match v {
            FalkorValue::F64(f) => Some(*f as i64),
            FalkorValue::I64(i) => Some(*i),
            _ => None,
        })
        .ok_or_else(|| anyhow!("Missing edge datetime property: {}", key))?;

    Ok(DateTime::from_timestamp(timestamp, 0).unwrap_or(Utc::now()))
}

#[allow(dead_code)]
fn get_edge_optional_datetime_property(edge: &falkordb::Edge, key: &str) -> Option<DateTime<Utc>> {
    edge.properties
        .get(key)
        .and_then(|v| match v {
            FalkorValue::F64(f) => Some(*f as i64),
            FalkorValue::I64(i) => Some(*i),
            _ => None,
        })
        .and_then(|timestamp| DateTime::from_timestamp(timestamp, 0))
}

fn get_edge_optional_float_property(edge: &falkordb::Edge, key: &str) -> Option<f64> {
    edge.properties.get(key).and_then(|v| match v {
        FalkorValue::F64(f) => Some(*f),
        FalkorValue::I64(i) => Some(*i as f64),
        _ => None,
    })
}
