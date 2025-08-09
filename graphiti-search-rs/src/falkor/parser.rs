use anyhow::Result;
use chrono::{DateTime, Utc};
use redis::Value;
use uuid::Uuid;

use crate::models::{Edge, Episode, Node};

/// Parse FalkorDB node response format
/// Structure: [[["id", id], ["labels", [labels]], ["properties", [[key, val], ...]]]]
pub fn parse_nodes_from_falkor(results: Vec<Vec<Value>>) -> Result<Vec<Node>> {
    let mut nodes = Vec::new();

    // FalkorDB returns: [headers, data_rows, stats]
    if results.len() < 2 {
        return Ok(nodes);
    }

    // Process data rows (index 1)
    // Each row is a list of columns, each column is a node/edge/etc
    for row in &results[1] {
        // Each row should be a Bulk/Array containing columns
        if let Value::Bulk(columns) = row {
            for column in columns {
                // Each column is a node represented as a list of fields
                if let Some(node) = parse_single_node(column)? {
                    nodes.push(node);
                }
            }
        }
    }

    Ok(nodes)
}

/// Parse a single node from FalkorDB format
fn parse_single_node(node_data: &Value) -> Result<Option<Node>> {
    // Node data should be a Bulk/Array containing [["id", val], ["labels", [...]], ["properties", [...]]]
    let fields = match node_data {
        Value::Bulk(fields) => fields,
        _ => return Ok(None),
    };

    let mut uuid_str = String::new();
    let mut name = String::new();
    let mut node_type = String::new();
    let mut summary = None;
    let mut group_id = None;
    let mut created_at = Utc::now();
    let mut centrality = None;

    // Process each field in the node data
    for field in fields {
        if let Value::Bulk(ref field_data) = field {
            if field_data.len() >= 2 {
                let key = extract_string(&field_data[0]).unwrap_or_default();

                match key.as_str() {
                    "id" => {
                        if let Value::Int(id) = &field_data[1] {
                            uuid_str = format!("node-{}", id);
                        }
                    }
                    "labels" => {
                        if let Value::Bulk(ref labels) = &field_data[1] {
                            if let Some(first_label) = labels.first() {
                                node_type = extract_string(first_label)
                                    .unwrap_or_else(|| "Entity".to_string());
                            }
                        }
                    }
                    "properties" => {
                        if let Value::Bulk(ref props) = &field_data[1] {
                            parse_node_properties(
                                props,
                                &mut uuid_str,
                                &mut name,
                                &mut node_type,
                                &mut summary,
                                &mut group_id,
                                &mut created_at,
                                &mut centrality,
                            );
                        }
                    }
                    _ => {}
                }
            }
        }
    }

    // Only return a node if we have a valid UUID
    if !uuid_str.is_empty() {
        // Try to parse UUID, fallback to generated one if invalid
        let uuid = Uuid::parse_str(&uuid_str).unwrap_or_else(|_| {
            // If it's a FalkorDB ID format (node-123), generate a deterministic UUID
            if uuid_str.starts_with("node-") {
                Uuid::new_v5(&Uuid::NAMESPACE_OID, uuid_str.as_bytes())
            } else {
                Uuid::new_v4()
            }
        });

        Ok(Some(Node {
            uuid,
            name,
            node_type,
            summary,
            created_at,
            embedding: None,
            group_id,
            centrality,
        }))
    } else {
        Ok(None)
    }
}

/// Parse node properties from FalkorDB property list
fn parse_node_properties(
    props: &[Value],
    uuid: &mut String,
    name: &mut String,
    node_type: &mut String,
    summary: &mut Option<String>,
    group_id: &mut Option<String>,
    created_at: &mut DateTime<Utc>,
    centrality: &mut Option<f32>,
) {
    for prop in props {
        if let Value::Bulk(ref prop_data) = prop {
            if prop_data.len() >= 2 {
                let key = extract_string(&prop_data[0]).unwrap_or_default();

                match key.as_str() {
                    "uuid" => {
                        if let Some(val) = extract_string(&prop_data[1]) {
                            *uuid = val;
                        }
                    }
                    "name" => {
                        if let Some(val) = extract_string(&prop_data[1]) {
                            *name = val;
                        }
                    }
                    "type" | "node_type" => {
                        if let Some(val) = extract_string(&prop_data[1]) {
                            *node_type = val;
                        }
                    }
                    "summary" => {
                        *summary = extract_string(&prop_data[1]);
                    }
                    "group_id" => {
                        *group_id = extract_string(&prop_data[1]);
                    }
                    "created_at" => {
                        if let Some(date_str) = extract_string(&prop_data[1]) {
                            if let Ok(dt) = DateTime::parse_from_rfc3339(&date_str) {
                                *created_at = dt.with_timezone(&Utc);
                            }
                        }
                    }
                    "degree_centrality"
                    | "pagerank_centrality"
                    | "betweenness_centrality"
                    | "eigenvector_centrality" => {
                        if let Some(val_str) = extract_string(&prop_data[1]) {
                            if let Ok(val) = val_str.parse::<f32>() {
                                *centrality = Some(val);
                            }
                        } else if let Value::Int(val) = &prop_data[1] {
                            *centrality = Some(*val as f32);
                        }
                    }
                    _ => {}
                }
            }
        }
    }
}

/// Parse FalkorDB edge response format
pub fn parse_edges_from_falkor(results: Vec<Vec<Value>>) -> Result<Vec<Edge>> {
    let mut edges = Vec::new();

    if results.len() < 2 {
        return Ok(edges);
    }

    // Process data rows (index 1)
    for row in &results[1] {
        // Each row should be a Bulk/Array containing [source_node, edge, target_node]
        if let Value::Bulk(columns) = row {
            if columns.len() >= 3 {
                if let Some(edge) = parse_single_edge(&columns[0], &columns[1], &columns[2])? {
                    edges.push(edge);
                }
            }
        }
    }

    Ok(edges)
}

/// Parse a single edge from FalkorDB format
fn parse_single_edge(
    source_node: &Value,
    edge_data: &Value,
    target_node: &Value,
) -> Result<Option<Edge>> {
    let mut uuid_str = String::new();
    let mut source_uuid_str = String::new();
    let mut target_uuid_str = String::new();
    let mut fact = String::new();
    let mut created_at = Utc::now();
    let mut group_id = None;
    let mut weight = 1.0;

    // Extract source node UUID
    if let Value::Bulk(ref node_fields) = source_node {
        for field in node_fields {
            if let Value::Bulk(ref field_data) = field {
                if field_data.len() >= 2 {
                    let key = extract_string(&field_data[0]).unwrap_or_default();
                    if key == "id" {
                        if let Value::Int(id) = &field_data[1] {
                            source_uuid_str = format!("node-{}", id);
                        }
                    } else if key == "properties" {
                        if let Value::Bulk(ref props) = &field_data[1] {
                            for prop in props {
                                if let Value::Bulk(ref prop_data) = prop {
                                    if prop_data.len() >= 2 {
                                        let prop_key =
                                            extract_string(&prop_data[0]).unwrap_or_default();
                                        if prop_key == "uuid" {
                                            if let Some(val) = extract_string(&prop_data[1]) {
                                                source_uuid_str = val;
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // Extract target node UUID
    if let Value::Bulk(ref node_fields) = target_node {
        for field in node_fields {
            if let Value::Bulk(ref field_data) = field {
                if field_data.len() >= 2 {
                    let key = extract_string(&field_data[0]).unwrap_or_default();
                    if key == "id" {
                        if let Value::Int(id) = &field_data[1] {
                            target_uuid_str = format!("node-{}", id);
                        }
                    } else if key == "properties" {
                        if let Value::Bulk(ref props) = &field_data[1] {
                            for prop in props {
                                if let Value::Bulk(ref prop_data) = prop {
                                    if prop_data.len() >= 2 {
                                        let prop_key =
                                            extract_string(&prop_data[0]).unwrap_or_default();
                                        if prop_key == "uuid" {
                                            if let Some(val) = extract_string(&prop_data[1]) {
                                                target_uuid_str = val;
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // Extract edge properties
    if let Value::Bulk(ref edge_fields) = edge_data {
        for field in edge_fields {
            if let Value::Bulk(ref field_data) = field {
                if field_data.len() >= 2 {
                    let key = extract_string(&field_data[0]).unwrap_or_default();

                    match key.as_str() {
                        "id" => {
                            if let Value::Int(id) = &field_data[1] {
                                uuid_str = format!("edge-{}", id);
                            }
                        }
                        "properties" => {
                            if let Value::Bulk(ref props) = &field_data[1] {
                                parse_edge_properties(
                                    props,
                                    &mut uuid_str,
                                    &mut fact,
                                    &mut created_at,
                                    &mut group_id,
                                    &mut weight,
                                );
                            }
                        }
                        _ => {}
                    }
                }
            }
        }
    }

    // Create UUIDs
    let uuid = create_uuid(&uuid_str);
    let source_node_uuid = create_uuid(&source_uuid_str);
    let target_node_uuid = create_uuid(&target_uuid_str);

    Ok(Some(Edge {
        uuid,
        source_node_uuid,
        target_node_uuid,
        fact,
        created_at,
        episodes: Vec::new(),
        group_id,
        weight,
    }))
}

/// Parse edge properties
fn parse_edge_properties(
    props: &[Value],
    uuid: &mut String,
    fact: &mut String,
    created_at: &mut DateTime<Utc>,
    group_id: &mut Option<String>,
    weight: &mut f32,
) {
    for prop in props {
        if let Value::Bulk(ref prop_data) = prop {
            if prop_data.len() >= 2 {
                let key = extract_string(&prop_data[0]).unwrap_or_default();

                match key.as_str() {
                    "uuid" => {
                        if let Some(val) = extract_string(&prop_data[1]) {
                            *uuid = val;
                        }
                    }
                    "fact" | "name" => {
                        if let Some(val) = extract_string(&prop_data[1]) {
                            *fact = val;
                        }
                    }
                    "group_id" => {
                        *group_id = extract_string(&prop_data[1]);
                    }
                    "created_at" => {
                        if let Some(date_str) = extract_string(&prop_data[1]) {
                            if let Ok(dt) = DateTime::parse_from_rfc3339(&date_str) {
                                *created_at = dt.with_timezone(&Utc);
                            }
                        }
                    }
                    "weight" => {
                        if let Some(val_str) = extract_string(&prop_data[1]) {
                            if let Ok(val) = val_str.parse::<f32>() {
                                *weight = val;
                            }
                        } else if let Value::Int(val) = &prop_data[1] {
                            *weight = *val as f32;
                        }
                    }
                    _ => {}
                }
            }
        }
    }
}

/// Parse FalkorDB episode response format
pub fn parse_episodes_from_falkor(results: Vec<Vec<Value>>) -> Result<Vec<Episode>> {
    let mut episodes = Vec::new();

    if results.len() < 2 {
        return Ok(episodes);
    }

    // Process data rows (index 1)
    for row in &results[1] {
        // Each row should be a Bulk/Array containing columns
        if let Value::Bulk(columns) = row {
            for column in columns {
                if let Some(episode) = parse_single_episode(column)? {
                    episodes.push(episode);
                }
            }
        }
    }

    Ok(episodes)
}

/// Parse a single episode
fn parse_single_episode(episode_data: &Value) -> Result<Option<Episode>> {
    // Episode data should be a Bulk/Array
    let fields = match episode_data {
        Value::Bulk(fields) => fields,
        _ => return Ok(None),
    };

    let mut uuid_str = String::new();
    let mut content = String::new();
    let mut created_at = Utc::now();
    let mut group_id = None;
    let mut timestamp = None;

    for field in fields {
        if let Value::Bulk(ref field_data) = field {
            if field_data.len() >= 2 {
                let key = extract_string(&field_data[0]).unwrap_or_default();

                match key.as_str() {
                    "id" => {
                        if let Value::Int(id) = &field_data[1] {
                            uuid_str = format!("episode-{}", id);
                        }
                    }
                    "properties" => {
                        if let Value::Bulk(ref props) = &field_data[1] {
                            for prop in props {
                                if let Value::Bulk(ref prop_data) = prop {
                                    if prop_data.len() >= 2 {
                                        let prop_key =
                                            extract_string(&prop_data[0]).unwrap_or_default();

                                        match prop_key.as_str() {
                                            "uuid" => {
                                                if let Some(val) = extract_string(&prop_data[1]) {
                                                    uuid_str = val;
                                                }
                                            }
                                            "content" | "text" => {
                                                if let Some(val) = extract_string(&prop_data[1]) {
                                                    content = val;
                                                }
                                            }
                                            "group_id" => {
                                                group_id = extract_string(&prop_data[1]);
                                            }
                                            "created_at" => {
                                                if let Some(date_str) =
                                                    extract_string(&prop_data[1])
                                                {
                                                    if let Ok(dt) =
                                                        DateTime::parse_from_rfc3339(&date_str)
                                                    {
                                                        created_at = dt.with_timezone(&Utc);
                                                    }
                                                }
                                            }
                                            "timestamp" | "valid_at" => {
                                                if let Some(date_str) =
                                                    extract_string(&prop_data[1])
                                                {
                                                    if let Ok(dt) =
                                                        DateTime::parse_from_rfc3339(&date_str)
                                                    {
                                                        timestamp = Some(dt.with_timezone(&Utc));
                                                    }
                                                }
                                            }
                                            _ => {}
                                        }
                                    }
                                }
                            }
                        }
                    }
                    _ => {}
                }
            }
        }
    }

    let uuid = create_uuid(&uuid_str);

    Ok(Some(Episode {
        uuid,
        content,
        created_at,
        group_id,
        timestamp,
    }))
}

/// Helper function to extract string from Redis Value
fn extract_string(value: &Value) -> Option<String> {
    match value {
        Value::Data(bytes) => String::from_utf8(bytes.clone()).ok(),
        Value::Status(s) => Some(s.clone()),
        Value::Okay => Some("OK".to_string()),
        Value::Int(i) => Some(i.to_string()),
        _ => None,
    }
}

/// Create UUID from string, with fallback
fn create_uuid(uuid_str: &str) -> Uuid {
    if uuid_str.is_empty() {
        return Uuid::new_v4();
    }

    Uuid::parse_str(uuid_str).unwrap_or_else(|_| {
        // Generate deterministic UUID for FalkorDB IDs
        if uuid_str.starts_with("node-")
            || uuid_str.starts_with("edge-")
            || uuid_str.starts_with("episode-")
        {
            Uuid::new_v5(&Uuid::NAMESPACE_OID, uuid_str.as_bytes())
        } else {
            Uuid::new_v4()
        }
    })
}
