//! HippoRAG vs Graphiti Search Comparison
//!
//! Compares HNSW vector index search against HippoRAG-style spreading activation
//! search using the production graph. Uses FalkorDB's db.idx.vector.queryNodes
//! procedure for fast approximate nearest neighbor search.

#![allow(dead_code)]

use anyhow::Result;
use falkordb::{FalkorClientBuilder, FalkorConnectionInfo, FalkorValue};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::Instant;

const EMBEDDING_URL: &str = "http://100.81.139.20:11450/v1/embeddings";
const EMBEDDING_MODEL: &str = "qwen3-embedding";
const GRAPH_NAME: &str = "graphiti_migration";

#[derive(Debug, Serialize)]
struct EmbeddingRequest {
    model: String,
    input: String,
}

#[derive(Debug, Deserialize)]
struct EmbeddingResponse {
    data: Vec<EmbeddingData>,
}

#[derive(Debug, Deserialize)]
struct EmbeddingData {
    embedding: Vec<f32>,
}

#[derive(Debug, Clone)]
struct SearchResult {
    name: String,
    summary: String,
    score: f64,
}

#[derive(Debug, Clone)]
struct SeedNode {
    uuid: String,
    name: String,
    score: f64,
}

async fn get_embedding(client: &Client, text: &str) -> Result<Vec<f32>> {
    let request = EmbeddingRequest {
        model: EMBEDDING_MODEL.to_string(),
        input: text.to_string(),
    };

    let response: EmbeddingResponse = client
        .post(EMBEDDING_URL)
        .json(&request)
        .send()
        .await?
        .json()
        .await?;

    Ok(response.data.into_iter().next().unwrap().embedding)
}

fn embedding_to_cypher(embedding: &[f32]) -> String {
    embedding
        .iter()
        .map(|v| v.to_string())
        .collect::<Vec<_>>()
        .join(",")
}

async fn graphiti_search(
    graph: &mut falkordb::AsyncGraph,
    embedding: &[f32],
    top_k: usize,
    max_distance: f64,
) -> Result<(Vec<SearchResult>, std::time::Duration)> {
    let start = Instant::now();
    let embedding_str = embedding_to_cypher(embedding);

    let query = format!(
        r#"CALL db.idx.vector.queryNodes('Entity', 'name_embedding', {}, vecf32([{}])) 
           YIELD node, score 
           WHERE score <= {}
           RETURN node.name, node.summary, score 
           ORDER BY score ASC"#,
        top_k * 2,
        embedding_str,
        max_distance
    );

    let result = graph.query(&query).execute().await?;
    let elapsed = start.elapsed();

    let mut results = Vec::new();
    for row in result.data {
        let name = match &row[0] {
            FalkorValue::String(s) => s.clone(),
            _ => continue,
        };
        let summary = match &row[1] {
            FalkorValue::String(s) => s.clone(),
            FalkorValue::None => String::new(),
            _ => String::new(),
        };
        let distance = match &row[2] {
            FalkorValue::F64(f) => *f,
            FalkorValue::I64(i) => *i as f64,
            _ => continue,
        };
        let similarity = 1.0 - distance;
        results.push(SearchResult {
            name,
            summary,
            score: similarity,
        });
    }

    results.truncate(top_k);
    Ok((results, elapsed))
}

async fn hipporag_search(
    graph: &mut falkordb::AsyncGraph,
    embedding: &[f32],
    top_k: usize,
    max_distance: f64,
    max_hops: usize,
    decay: f64,
) -> Result<(Vec<SearchResult>, std::time::Duration, Vec<SeedNode>)> {
    let start = Instant::now();
    let embedding_str = embedding_to_cypher(embedding);

    let seed_query = format!(
        r#"CALL db.idx.vector.queryNodes('Entity', 'name_embedding', 5, vecf32([{}])) 
           YIELD node, score 
           WHERE score <= {}
           RETURN node.uuid, node.name, score 
           ORDER BY score ASC"#,
        embedding_str, max_distance
    );

    let seed_result = graph.query(&seed_query).execute().await?;

    let mut seeds: Vec<SeedNode> = Vec::new();
    let mut seed_scores: HashMap<String, f64> = HashMap::new();

    for row in seed_result.data {
        let uuid = match &row[0] {
            FalkorValue::String(s) => s.clone(),
            _ => continue,
        };
        let name = match &row[1] {
            FalkorValue::String(s) => s.clone(),
            _ => continue,
        };
        let distance = match &row[2] {
            FalkorValue::F64(f) => *f,
            FalkorValue::I64(i) => *i as f64,
            _ => continue,
        };
        let similarity = 1.0 - distance;
        seed_scores.insert(uuid.clone(), similarity);
        seeds.push(SeedNode {
            uuid,
            name,
            score: similarity,
        });
    }

    if seeds.is_empty() {
        return Ok((Vec::new(), start.elapsed(), seeds));
    }

    // Step 2: Spread activation via graph traversal
    let seed_uuids: Vec<String> = seeds.iter().map(|s| format!("'{}'", s.uuid)).collect();
    let seed_list = seed_uuids.join(",");

    let propagation_query = format!(
        r#"MATCH path = (seed:Entity)-[*1..{}]-(target:Entity) 
           WHERE seed.uuid IN [{}] AND seed <> target 
           WITH DISTINCT target, seed, length(path) as hops 
           WITH target, seed.uuid as seed_uuid, {} ^ hops as decay_score 
           RETURN target.uuid, target.name, target.summary, collect(seed_uuid), sum(decay_score) as activation 
           ORDER BY activation DESC 
           LIMIT {}"#,
        max_hops, seed_list, decay, top_k
    );

    let prop_result = graph.query(&propagation_query).execute().await?;
    let elapsed = start.elapsed();

    let mut results = Vec::new();
    for row in prop_result.data {
        let name = match &row[1] {
            FalkorValue::String(s) => s.clone(),
            _ => continue,
        };
        let summary = match &row[2] {
            FalkorValue::String(s) => s.clone(),
            FalkorValue::None => String::new(),
            _ => String::new(),
        };
        let activation = match &row[4] {
            FalkorValue::F64(f) => *f,
            FalkorValue::I64(i) => *i as f64,
            _ => continue,
        };

        // Weight by seed scores
        let contributing_seeds = match &row[3] {
            FalkorValue::Array(arr) => arr
                .iter()
                .filter_map(|v| match v {
                    FalkorValue::String(s) => Some(s.clone()),
                    _ => None,
                })
                .collect::<Vec<_>>(),
            _ => Vec::new(),
        };

        let mut weighted_score = activation;
        for seed_uuid in &contributing_seeds {
            if let Some(&seed_score) = seed_scores.get(seed_uuid) {
                weighted_score *= seed_score;
            }
        }

        results.push(SearchResult {
            name,
            summary,
            score: weighted_score,
        });
    }

    Ok((results, elapsed, seeds))
}

#[derive(Debug, Clone)]
struct HybridResult {
    uuid: String,
    name: String,
    summary: String,
    vector_score: f64,
    graph_score: f64,
    combined_score: f64,
}

async fn hybrid_search(
    graph: &mut falkordb::AsyncGraph,
    embedding: &[f32],
    top_k: usize,
    max_distance: f64,
    max_hops: usize,
    decay: f64,
    vector_weight: f64,
) -> Result<(Vec<HybridResult>, std::time::Duration)> {
    let start = Instant::now();
    let embedding_str = embedding_to_cypher(embedding);

    let seed_query = format!(
        r#"CALL db.idx.vector.queryNodes('Entity', 'name_embedding', {}, vecf32([{}])) 
           YIELD node, score 
           WHERE score <= {}
           RETURN node.uuid, node.name, node.summary, score 
           ORDER BY score ASC"#,
        top_k, embedding_str, max_distance
    );

    let seed_result = graph.query(&seed_query).execute().await?;

    let mut candidates: HashMap<String, HybridResult> = HashMap::new();
    let mut seed_uuids: Vec<String> = Vec::new();
    let mut seed_similarities: HashMap<String, f64> = HashMap::new();

    for row in seed_result.data {
        let uuid = match &row[0] {
            FalkorValue::String(s) => s.clone(),
            _ => continue,
        };
        let name = match &row[1] {
            FalkorValue::String(s) => s.clone(),
            _ => continue,
        };
        let summary = match &row[2] {
            FalkorValue::String(s) => s.clone(),
            FalkorValue::None => String::new(),
            _ => String::new(),
        };
        let distance = match &row[3] {
            FalkorValue::F64(f) => *f,
            FalkorValue::I64(i) => *i as f64,
            _ => continue,
        };

        let vector_score = 1.0 - distance;
        seed_uuids.push(uuid.clone());
        seed_similarities.insert(uuid.clone(), vector_score);

        candidates.insert(
            uuid.clone(),
            HybridResult {
                uuid,
                name,
                summary,
                vector_score,
                graph_score: 0.0,
                combined_score: 0.0,
            },
        );
    }

    if !seed_uuids.is_empty() {
        let uuid_list = seed_uuids
            .iter()
            .map(|u| format!("'{}'", u))
            .collect::<Vec<_>>()
            .join(",");

        let neighbor_query = format!(
            r#"MATCH path = (seed:Entity)-[*1..{}]-(neighbor:Entity)
               WHERE seed.uuid IN [{}] AND neighbor.name_embedding IS NOT NULL
               WITH neighbor, seed, min(length(path)) as min_hops
               RETURN neighbor.uuid, neighbor.name, neighbor.summary, 
                      collect(seed.uuid) as seeds, collect(min_hops) as hops"#,
            max_hops, uuid_list
        );

        if let Ok(neighbor_result) = graph.query(&neighbor_query).execute().await {
            let mut neighbor_uuids: Vec<String> = Vec::new();

            for row in neighbor_result.data {
                let uuid = match &row[0] {
                    FalkorValue::String(s) => s.clone(),
                    _ => continue,
                };
                let name = match &row[1] {
                    FalkorValue::String(s) => s.clone(),
                    _ => continue,
                };
                let summary = match &row[2] {
                    FalkorValue::String(s) => s.clone(),
                    FalkorValue::None => String::new(),
                    _ => String::new(),
                };

                let contributing_seeds: Vec<String> = match &row[3] {
                    FalkorValue::Array(arr) => arr
                        .iter()
                        .filter_map(|v| match v {
                            FalkorValue::String(s) => Some(s.clone()),
                            _ => None,
                        })
                        .collect(),
                    _ => Vec::new(),
                };

                let hops: Vec<i64> = match &row[4] {
                    FalkorValue::Array(arr) => arr
                        .iter()
                        .filter_map(|v| match v {
                            FalkorValue::I64(i) => Some(*i),
                            _ => None,
                        })
                        .collect(),
                    _ => Vec::new(),
                };

                let mut graph_score = 0.0;
                for (seed_uuid, hop_count) in contributing_seeds.iter().zip(hops.iter()) {
                    let hop_decay = decay.powi(*hop_count as i32);
                    let seed_sim = seed_similarities.get(seed_uuid).unwrap_or(&0.5);
                    graph_score += hop_decay * seed_sim;
                }

                if candidates.contains_key(&uuid) {
                    if let Some(existing) = candidates.get_mut(&uuid) {
                        existing.graph_score = graph_score.max(existing.graph_score);
                    }
                    continue;
                }

                neighbor_uuids.push(uuid.clone());
                candidates.insert(
                    uuid.clone(),
                    HybridResult {
                        uuid,
                        name,
                        summary,
                        vector_score: 0.0,
                        graph_score,
                        combined_score: 0.0,
                    },
                );
            }

            if !neighbor_uuids.is_empty() {
                let neighbor_uuid_list = neighbor_uuids
                    .iter()
                    .map(|u| format!("'{}'", u))
                    .collect::<Vec<_>>()
                    .join(",");

                let vector_query = format!(
                    r#"CALL db.idx.vector.queryNodes('Entity', 'name_embedding', {}, vecf32([{}]))
                       YIELD node, score
                       WHERE node.uuid IN [{}]
                       RETURN node.uuid, score"#,
                    neighbor_uuids.len() * 2,
                    embedding_str,
                    neighbor_uuid_list
                );

                if let Ok(vector_result) = graph.query(&vector_query).execute().await {
                    for row in vector_result.data {
                        let uuid = match &row[0] {
                            FalkorValue::String(s) => s.clone(),
                            _ => continue,
                        };
                        let distance = match &row[1] {
                            FalkorValue::F64(f) => *f,
                            FalkorValue::I64(i) => *i as f64,
                            _ => continue,
                        };

                        if let Some(candidate) = candidates.get_mut(&uuid) {
                            candidate.vector_score = 1.0 - distance;
                        }
                    }
                }
            }
        }
    }

    let graph_weight = 1.0 - vector_weight;
    let mut results: Vec<HybridResult> = candidates
        .into_values()
        .map(|mut c| {
            c.combined_score = (vector_weight * c.vector_score) + (graph_weight * c.graph_score);
            c
        })
        .collect();

    results.sort_by(|a, b| b.combined_score.partial_cmp(&a.combined_score).unwrap());
    results.truncate(top_k);

    Ok((results, start.elapsed()))
}

fn compare_results(graphiti: &[SearchResult], hipporag: &[SearchResult]) {
    let g_names: std::collections::HashSet<_> = graphiti.iter().take(10).map(|r| &r.name).collect();
    let h_names: std::collections::HashSet<_> = hipporag.iter().take(10).map(|r| &r.name).collect();

    let overlap = g_names.intersection(&h_names).count();
    let only_hippo: Vec<_> = h_names.difference(&g_names).collect();
    let only_graphiti: Vec<_> = g_names.difference(&h_names).collect();

    println!("\n[COMPARISON]");
    println!(
        "  Overlap: {}/{} entities in common",
        overlap,
        g_names.len().min(h_names.len())
    );
    if !only_hippo.is_empty() {
        println!("  Unique to HippoRAG: {:?}", only_hippo);
    }
    if !only_graphiti.is_empty() {
        println!("  Unique to Graphiti: {:?}", only_graphiti);
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();

    let conn_info: FalkorConnectionInfo = "falkor://localhost:6379".try_into()?;
    let client = FalkorClientBuilder::new_async()
        .with_connection_info(conn_info)
        .build()
        .await?;
    let mut graph = client.select_graph(GRAPH_NAME);
    let http_client = Client::new();

    println!("Connected to FalkorDB");
    println!("Using embedding endpoint: {}", EMBEDDING_URL);
    println!();

    let queries = [
        "Emmanuel",
        "Graphiti knowledge graph",
        "Temporal workflow",
        "FalkorDB database",
        "project management",
    ];

    for query in queries {
        println!("\n{}", "=".repeat(70));
        println!("Query: '{}'", query);
        println!("{}", "=".repeat(70));

        print!("Generating embedding... ");
        let embedding = get_embedding(&http_client, query).await?;
        println!("done ({} dimensions)", embedding.len());

        println!("\n[GRAPHITI - HNSW Vector Index]");
        let (g_results, g_time) = graphiti_search(&mut graph, &embedding, 10, 0.5).await?;
        println!(
            "Time: {:.1}ms | Results: {}",
            g_time.as_millis(),
            g_results.len()
        );
        for (i, r) in g_results.iter().take(5).enumerate() {
            println!(
                "  {}. {}: {:.4}",
                i + 1,
                &r.name[..r.name.len().min(40)],
                r.score
            );
        }

        println!("\n[HIPPORAG - Spreading Activation (2-hop)]");
        let (h_results, h_time, seeds) =
            hipporag_search(&mut graph, &embedding, 10, 0.5, 2, 0.5).await?;
        let seed_names: Vec<_> = seeds.iter().take(3).map(|s| s.name.as_str()).collect();
        println!(
            "Time: {:.1}ms | Seeds: {:?}",
            h_time.as_millis(),
            seed_names
        );
        for (i, r) in h_results.iter().take(5).enumerate() {
            println!(
                "  {}. {}: {:.4}",
                i + 1,
                &r.name[..r.name.len().min(40)],
                r.score
            );
        }

        println!("\n[HYBRID - Vector(0.7) + Graph(0.3)]");
        let (hybrid_results, hybrid_time) =
            hybrid_search(&mut graph, &embedding, 10, 0.5, 2, 0.5, 0.7).await?;
        println!(
            "Time: {:.1}ms | Results: {}",
            hybrid_time.as_millis(),
            hybrid_results.len()
        );
        for (i, r) in hybrid_results.iter().take(5).enumerate() {
            println!(
                "  {}. {} [v:{:.2} g:{:.2}]: {:.4}",
                i + 1,
                &r.name[..r.name.len().min(30)],
                r.vector_score,
                r.graph_score,
                r.combined_score
            );
        }

        compare_results(&g_results, &h_results);

        let hybrid_names: std::collections::HashSet<_> =
            hybrid_results.iter().take(10).map(|r| &r.name).collect();
        let g_names: std::collections::HashSet<_> =
            g_results.iter().take(10).map(|r| &r.name).collect();
        let h_names: std::collections::HashSet<_> =
            h_results.iter().take(10).map(|r| &r.name).collect();

        let from_vector = hybrid_names.intersection(&g_names).count();
        let from_graph = hybrid_names.intersection(&h_names).count();
        println!(
            "\n[HYBRID COMPOSITION] {} from vector, {} from graph traversal",
            from_vector, from_graph
        );
    }

    println!("\n{}", "=".repeat(70));
    println!("Comparison complete!");

    Ok(())
}
