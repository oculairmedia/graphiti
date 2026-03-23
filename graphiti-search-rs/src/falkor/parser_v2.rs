use anyhow::{anyhow, Result};
use chrono::{DateTime, Utc};
use falkordb::{FalkorValue, LazyResultSet};
use serde_json::{Map, Number, Value};
use std::collections::HashMap;
use uuid::Uuid;

use crate::models::{Edge, Episode, Node};

pub fn parse_nodes_from_falkor_v2(result: LazyResultSet<'_>) -> Result<Vec<Node>> {
    let mut nodes = Vec::new();
    let mut row_count = 0;

    for row in result {
        row_count += 1;
        for value in row {
            match &value {
                FalkorValue::Node(falkor_node) => {
                    if let Some(node) = parse_single_node_v2(falkor_node)? {
                        nodes.push(node);
                    }
                }
                FalkorValue::Unparseable(raw) => {
                    tracing::warn!(
                        "Row {}: Unparseable value (first 500 chars): {}",
                        row_count,
                        &raw.chars().take(500).collect::<String>()
                    );
                }
                other => {
                    tracing::debug!(
                        "Row {}: Skipping non-node value type: {:?}",
                        row_count,
                        std::mem::discriminant(other)
                    );
                }
            }
        }
    }

    tracing::debug!(
        "parse_nodes_from_falkor_v2: processed {} rows, parsed {} nodes",
        row_count,
        nodes.len()
    );
    Ok(nodes)
}

/// Parse nodes with scores from fulltext search results
/// Expects rows with format: [node, score]
pub fn parse_nodes_with_scores_from_falkor_v2(result: LazyResultSet<'_>) -> Result<Vec<Node>> {
    let mut nodes = Vec::new();
    let mut row_count = 0;

    for row in result {
        row_count += 1;
        if row.len() >= 2 {
            // Extract node and score from row
            if let FalkorValue::Node(falkor_node) = &row[0] {
                if let Some(mut node) = parse_single_node_v2(falkor_node)? {
                    // Extract score (second column)
                    let score = match &row[1] {
                        FalkorValue::F64(f) => Some(*f as f32),
                        FalkorValue::I64(i) => Some(*i as f32),
                        _ => {
                            tracing::warn!(
                                "Row {}: Expected numeric score, got {:?}",
                                row_count,
                                std::mem::discriminant(&row[1])
                            );
                            None
                        }
                    };
                    node.score = score;
                    nodes.push(node);
                }
            }
        } else {
            tracing::warn!(
                "Row {}: Expected 2 columns (node, score), got {}",
                row_count,
                row.len()
            );
        }
    }

    tracing::debug!(
        "parse_nodes_with_scores_from_falkor_v2: processed {} rows, parsed {} nodes with scores",
        row_count,
        nodes.len()
    );
    Ok(nodes)
}

pub fn parse_edges_from_falkor_v2(result: LazyResultSet<'_>) -> Result<Vec<Edge>> {
    let mut edges = Vec::new();

    for row in result {
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

pub fn parse_episodes_from_falkor_v2(result: LazyResultSet<'_>) -> Result<Vec<Episode>> {
    let mut episodes = Vec::new();

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

fn parse_single_node_v2(falkor_node: &falkordb::Node) -> Result<Option<Node>> {
    let uuid_str = get_string_property(falkor_node, "uuid")?;
    let name = get_string_property(falkor_node, "name")?;
    let node_type =
        get_string_property(falkor_node, "entity_type").unwrap_or_else(|_| "entity".to_string());
    let summary = get_optional_string_property(falkor_node, "summary");
    let group_id = get_optional_string_property(falkor_node, "group_id");
    let created_at =
        get_datetime_property(falkor_node, "created_at").unwrap_or_else(|_| Utc::now());
    let centrality = get_optional_float_property(falkor_node, "centrality").map(|f| f as f32);
    let attributes = node_attributes(falkor_node);
    let valid_at = get_optional_datetime_property(falkor_node, "valid_at");
    let invalid_at = get_optional_datetime_property(falkor_node, "invalid_at");

    let uuid = Uuid::parse_str(&uuid_str).map_err(|e| anyhow!("Failed to parse UUID: {}", e))?;

    Ok(Some(Node {
        uuid,
        name,
        node_type,
        summary,
        created_at,
        embedding: None,
        group_id,
        centrality,
        attributes,
        valid_at,
        invalid_at,
        score: None,
    }))
}

fn parse_single_edge_v2(
    source: &falkordb::Node,
    falkor_edge: &falkordb::Edge,
    target: &falkordb::Node,
) -> Result<Option<Edge>> {
    let uuid_str = get_edge_string_property(falkor_edge, "uuid")?;
    let fact = get_edge_string_property(falkor_edge, "fact")?;
    let created_at =
        get_edge_datetime_property(falkor_edge, "created_at").unwrap_or_else(|_| Utc::now());
    let group_id = get_edge_optional_string_property(falkor_edge, "group_id");
    let weight = get_edge_optional_float_property(falkor_edge, "weight").unwrap_or(1.0) as f32;
    let name = get_edge_optional_string_property(falkor_edge, "name");
    let valid_at = get_edge_optional_datetime_property(falkor_edge, "valid_at");
    let invalid_at = get_edge_optional_datetime_property(falkor_edge, "invalid_at");
    let expired_at = get_edge_optional_datetime_property(falkor_edge, "expired_at");
    let attributes = edge_attributes(falkor_edge);

    let uuid =
        Uuid::parse_str(&uuid_str).map_err(|e| anyhow!("Failed to parse edge UUID: {}", e))?;
    let source_node_uuid = Uuid::parse_str(&get_string_property(source, "uuid")?)?;
    let target_node_uuid = Uuid::parse_str(&get_string_property(target, "uuid")?)?;
    let episodes = get_edge_uuid_array_property(falkor_edge, "episodes").unwrap_or_default();

    Ok(Some(Edge {
        uuid,
        source_node_uuid,
        target_node_uuid,
        name,
        fact,
        created_at,
        episodes,
        group_id,
        weight,
        valid_at,
        invalid_at,
        expired_at,
        attributes,
        score: None,
    }))
}

fn parse_single_episode_v2(falkor_node: &falkordb::Node) -> Result<Option<Episode>> {
    if !falkor_node.labels.contains(&"Episode".to_string()) {
        return Ok(None);
    }

    let uuid_str = get_string_property(falkor_node, "uuid")?;
    let content = get_string_property(falkor_node, "content")?;
    let created_at =
        get_datetime_property(falkor_node, "created_at").unwrap_or_else(|_| Utc::now());
    let group_id = get_optional_string_property(falkor_node, "group_id");
    let name = get_optional_string_property(falkor_node, "name");
    let source = get_optional_string_property(falkor_node, "source");
    let source_description = get_optional_string_property(falkor_node, "source_description");
    let valid_at = get_optional_datetime_property(falkor_node, "valid_at")
        .or_else(|| get_optional_datetime_property(falkor_node, "timestamp"));
    let entity_edges = get_uuid_array_property(falkor_node, "entity_edges");
    let timestamp = get_optional_datetime_property(falkor_node, "timestamp");

    let uuid = Uuid::parse_str(&uuid_str)?;

    Ok(Some(Episode {
        uuid,
        name,
        content,
        created_at,
        group_id,
        source,
        source_description,
        valid_at,
        entity_edges,
        timestamp,
    }))
}

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
    node.properties
        .get(key)
        .and_then(parse_datetime_value)
        .ok_or_else(|| anyhow!("Missing datetime property: {}", key))
}

fn get_optional_datetime_property(node: &falkordb::Node, key: &str) -> Option<DateTime<Utc>> {
    node.properties.get(key).and_then(parse_datetime_value)
}

fn get_optional_float_property(node: &falkordb::Node, key: &str) -> Option<f64> {
    node.properties.get(key).and_then(|v| match v {
        FalkorValue::F64(f) => Some(*f),
        FalkorValue::I64(i) => Some(*i as f64),
        _ => None,
    })
}

fn get_uuid_array_property(node: &falkordb::Node, key: &str) -> Option<Vec<Uuid>> {
    node.properties.get(key).and_then(falkor_uuid_array)
}

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
    edge.properties
        .get(key)
        .and_then(parse_datetime_value)
        .ok_or_else(|| anyhow!("Missing edge datetime property: {}", key))
}

fn get_edge_optional_datetime_property(edge: &falkordb::Edge, key: &str) -> Option<DateTime<Utc>> {
    edge.properties.get(key).and_then(parse_datetime_value)
}

fn get_edge_optional_float_property(edge: &falkordb::Edge, key: &str) -> Option<f64> {
    edge.properties.get(key).and_then(|v| match v {
        FalkorValue::F64(f) => Some(*f),
        FalkorValue::I64(i) => Some(*i as f64),
        _ => None,
    })
}

fn get_edge_uuid_array_property(edge: &falkordb::Edge, key: &str) -> Option<Vec<Uuid>> {
    edge.properties.get(key).and_then(falkor_uuid_array)
}

fn parse_datetime_value(value: &FalkorValue) -> Option<DateTime<Utc>> {
    match value {
        FalkorValue::F64(f) => DateTime::from_timestamp(*f as i64, 0),
        FalkorValue::I64(i) => DateTime::from_timestamp(*i, 0),
        FalkorValue::String(s) => DateTime::parse_from_rfc3339(s)
            .ok()
            .map(|dt| dt.with_timezone(&Utc)),
        _ => None,
    }
}

fn falkor_uuid_array(value: &FalkorValue) -> Option<Vec<Uuid>> {
    match value {
        FalkorValue::Array(values) => Some(
            values
                .iter()
                .filter_map(|value| match value {
                    FalkorValue::String(raw) => Uuid::parse_str(raw).ok(),
                    _ => None,
                })
                .collect(),
        ),
        _ => None,
    }
}

fn node_attributes(node: &falkordb::Node) -> Option<Map<String, Value>> {
    let mut attributes = properties_to_json_map(&node.properties)?;
    prune_attributes(
        &mut attributes,
        &[
            "uuid",
            "name",
            "entity_type",
            "summary",
            "group_id",
            "created_at",
            "updated_at",
            "valid_at",
            "invalid_at",
            "centrality",
            "name_embedding",
        ],
    );
    (!attributes.is_empty()).then_some(attributes)
}

fn edge_attributes(edge: &falkordb::Edge) -> Option<Map<String, Value>> {
    let mut attributes = properties_to_json_map(&edge.properties)?;
    prune_attributes(
        &mut attributes,
        &[
            "uuid",
            "name",
            "fact",
            "group_id",
            "created_at",
            "updated_at",
            "episodes",
            "weight",
            "valid_at",
            "invalid_at",
            "expired_at",
            "fact_embedding",
        ],
    );
    (!attributes.is_empty()).then_some(attributes)
}

fn properties_to_json_map(properties: &HashMap<String, FalkorValue>) -> Option<Map<String, Value>> {
    let mut result = Map::new();
    for (key, value) in properties {
        if let Some(json_value) = falkor_value_to_json(value) {
            result.insert(key.clone(), json_value);
        }
    }
    Some(result)
}

fn prune_attributes(attributes: &mut Map<String, Value>, keys: &[&str]) {
    for key in keys {
        attributes.remove(*key);
    }
}

fn falkor_value_to_json(value: &FalkorValue) -> Option<Value> {
    match value {
        FalkorValue::String(s) => Some(Value::String(s.clone())),
        FalkorValue::Bool(b) => Some(Value::Bool(*b)),
        FalkorValue::I64(i) => Some(Value::Number((*i).into())),
        FalkorValue::F64(f) => Number::from_f64(*f).map(Value::Number),
        FalkorValue::Array(values) => Some(Value::Array(
            values.iter().filter_map(falkor_value_to_json).collect(),
        )),
        FalkorValue::Map(values) => Some(Value::Object(
            values
                .iter()
                .filter_map(|(key, value)| {
                    falkor_value_to_json(value).map(|json| (key.clone(), json))
                })
                .collect(),
        )),
        FalkorValue::Vec32(vec32) => Some(Value::Array(
            vec32
                .values
                .iter()
                .filter_map(|value| Number::from_f64(*value as f64).map(Value::Number))
                .collect(),
        )),
        FalkorValue::None => Some(Value::Null),
        FalkorValue::Point(point) => Some(Value::String(format!("{point:?}"))),
        FalkorValue::Path(path) => Some(Value::String(format!("{path:?}"))),
        FalkorValue::Node(_) | FalkorValue::Edge(_) | FalkorValue::Unparseable(_) => None,
    }
}
