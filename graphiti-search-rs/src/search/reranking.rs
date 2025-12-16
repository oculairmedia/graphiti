use crate::error::SearchResult;
use crate::models::{Edge, EdgeReranker, Node, NodeReranker};
use crate::reranker::RerankerClient;
use crate::search::similarity::cosine_similarity_simd;
use std::collections::{HashMap, HashSet};
use tracing::instrument;

/// Reciprocal Rank Fusion (RRF) for combining multiple ranked lists
pub fn reciprocal_rank_fusion<T: Clone>(
    ranked_lists: Vec<Vec<T>>,
    k: f32,
    get_id: impl Fn(&T) -> String + Sync,
) -> Vec<T> {
    let mut scores: HashMap<String, (T, f32)> = HashMap::new();

    for list in ranked_lists {
        for (rank, item) in list.into_iter().enumerate() {
            let id = get_id(&item);
            let score = 1.0 / (k + rank as f32 + 1.0);

            scores
                .entry(id)
                .and_modify(|e| e.1 += score)
                .or_insert((item, score));
        }
    }

    let mut results: Vec<(T, f32)> = scores.into_values().collect();
    results.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap());
    results.into_iter().map(|(item, _)| item).collect()
}

/// Centrality-based boosting for structurally important nodes
pub fn centrality_boosted_rerank<T: Clone>(
    items: Vec<T>,
    query_embedding: Option<&[f32]>,
    get_embedding: impl Fn(&T) -> Option<&[f32]> + Sync,
    get_centrality: impl Fn(&T) -> Option<f32> + Sync,
    boost_factor: f32,
    limit: usize,
) -> Vec<T> {
    if items.is_empty() {
        return items;
    }

    let query = query_embedding.unwrap_or(&[]);

    let mut scored_items: Vec<(T, f32)> = items
        .into_iter()
        .map(|item| {
            // Calculate base relevance score
            let relevance_score = if !query.is_empty() {
                if let Some(item_emb) = get_embedding(&item) {
                    cosine_similarity_simd(query, item_emb)
                } else {
                    0.5 // Default relevance for items without embeddings
                }
            } else {
                1.0 // No query bias, treat all as equally relevant
            };

            // Get centrality score and apply boost
            let centrality = get_centrality(&item).unwrap_or(0.0);
            let centrality_boost = centrality * boost_factor;

            // Combined score: base relevance + centrality boost
            let final_score = relevance_score + centrality_boost;

            (item, final_score)
        })
        .collect();

    // Sort by combined score (descending)
    scored_items.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

    // Return top results
    scored_items
        .into_iter()
        .take(limit)
        .map(|(item, _)| item)
        .collect()
}

/// Maximal Marginal Relevance (MMR) for diversity-aware reranking
pub fn maximal_marginal_relevance<T: Clone>(
    items: Vec<T>,
    query_embedding: Option<&[f32]>,
    get_embedding: impl Fn(&T) -> Option<&[f32]> + Sync,
    lambda: f32,
    limit: usize,
) -> Vec<T> {
    if items.is_empty() || query_embedding.is_none() {
        return items.into_iter().take(limit).collect();
    }

    let query = query_embedding.unwrap();
    let mut selected = Vec::new();
    let mut remaining: Vec<(usize, &T)> = items.iter().enumerate().collect();

    while selected.len() < limit && !remaining.is_empty() {
        let scores: Vec<f32> = remaining
            .iter()
            .map(|(_, item)| {
                if let Some(item_emb) = get_embedding(item) {
                    let relevance = cosine_similarity_simd(query, item_emb);

                    let max_similarity = selected
                        .iter()
                        .filter_map(|s: &T| get_embedding(s))
                        .map(|s_emb| cosine_similarity_simd(item_emb, s_emb))
                        .max_by(|a, b| a.partial_cmp(b).unwrap())
                        .unwrap_or(0.0);

                    lambda * relevance - (1.0 - lambda) * max_similarity
                } else {
                    0.0
                }
            })
            .collect();

        if let Some((max_idx, _)) = scores
            .iter()
            .enumerate()
            .max_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap())
        {
            let (orig_idx, _item) = remaining.remove(max_idx);
            selected.push(items[orig_idx].clone());
        } else {
            break;
        }
    }

    selected
}

/// Node distance reranking based on graph distance from center node
pub fn _node_distance_rerank<T>(
    items: Vec<T>,
    get_node_id: impl Fn(&T) -> String,
    distances: &HashMap<String, usize>,
    ascending: bool,
) -> Vec<T> {
    let mut items_with_distance: Vec<(T, usize)> = items
        .into_iter()
        .map(|item| {
            let node_id = get_node_id(&item);
            let distance = distances.get(&node_id).copied().unwrap_or(usize::MAX);
            (item, distance)
        })
        .collect();

    if ascending {
        items_with_distance.sort_by_key(|&(_, dist)| dist);
    } else {
        items_with_distance.sort_by_key(|&(_, dist)| std::cmp::Reverse(dist));
    }

    items_with_distance
        .into_iter()
        .map(|(item, _)| item)
        .collect()
}

#[instrument(skip(method_results, query_vector, reranker_client))]
pub async fn rerank_edges(
    method_results: Vec<Vec<Edge>>,
    reranker: &EdgeReranker,
    query: &str,
    query_vector: Option<&[f32]>,
    mmr_lambda: f32,
    reranker_client: Option<&RerankerClient>,
) -> SearchResult<Vec<Edge>> {
    match reranker {
        EdgeReranker::Rrf => Ok(reciprocal_rank_fusion(method_results, 60.0, |edge| {
            edge.uuid.to_string()
        })),
        EdgeReranker::Mmr => {
            let all_edges: Vec<Edge> = method_results.into_iter().flatten().collect();
            Ok(maximal_marginal_relevance(
                all_edges,
                query_vector,
                |_edge| None, // Edges typically don't have embeddings
                mmr_lambda,
                100,
            ))
        }
        EdgeReranker::CrossEncoder => {
            if method_results.iter().all(|list| list.is_empty()) {
                return Ok(vec![]);
            }

            if let Some(client) = reranker_client {
                let all_edges: Vec<Edge> = method_results
                    .iter()
                    .flat_map(|list| list.iter().cloned())
                    .collect();
                let documents: Vec<String> = all_edges.iter().map(|e| e.fact.clone()).collect();
                let top_k = Some(documents.len().min(100));

                tracing::info!(
                    "CrossEncoder reranking {} edges for query: {}",
                    documents.len(),
                    query
                );

                match client.rerank(query, documents, top_k).await {
                    Ok(ranked) => {
                        tracing::info!("CrossEncoder returned {} ranked results", ranked.len());
                        let mut seen = HashSet::new();
                        let mut result = Vec::with_capacity(ranked.len());
                        for (idx, _score) in ranked {
                            if let Some(edge) = all_edges.get(idx).cloned() {
                                if seen.insert(edge.uuid) {
                                    result.push(edge);
                                }
                            }
                        }
                        Ok(result)
                    }
                    Err(e) => {
                        tracing::warn!("Cross-encoder failed, falling back to RRF: {}", e);
                        Ok(reciprocal_rank_fusion(method_results, 60.0, |edge| {
                            edge.uuid.to_string()
                        }))
                    }
                }
            } else {
                tracing::debug!(
                    "CrossEncoder requested but no reranker_client available, using RRF"
                );
                Ok(reciprocal_rank_fusion(method_results, 60.0, |edge| {
                    edge.uuid.to_string()
                }))
            }
        }
        EdgeReranker::NodeDistance => {
            // Would require distance calculation from graph
            let all_edges: Vec<Edge> = method_results.into_iter().flatten().collect();
            Ok(all_edges)
        }
        EdgeReranker::EpisodeMentions => {
            // Sort by number of episode mentions
            let mut all_edges: Vec<Edge> = method_results.into_iter().flatten().collect();
            all_edges.sort_by_key(|edge| std::cmp::Reverse(edge.episodes.len()));
            Ok(all_edges)
        }
    }
}

#[instrument(skip(method_results, query_vector, reranker_client))]
pub async fn rerank_nodes(
    method_results: Vec<Vec<Node>>,
    reranker: &NodeReranker,
    query: &str,
    query_vector: Option<&[f32]>,
    mmr_lambda: f32,
    centrality_boost_factor: f32,
    reranker_client: Option<&RerankerClient>,
) -> SearchResult<Vec<Node>> {
    match reranker {
        NodeReranker::Rrf => Ok(reciprocal_rank_fusion(method_results, 60.0, |node| {
            node.uuid.to_string()
        })),
        NodeReranker::Mmr => {
            let all_nodes: Vec<Node> = method_results.into_iter().flatten().collect();
            Ok(maximal_marginal_relevance(
                all_nodes,
                query_vector,
                |node| node.embedding.as_deref(),
                mmr_lambda,
                100,
            ))
        }
        NodeReranker::CrossEncoder => {
            if method_results.iter().all(|list| list.is_empty()) {
                return Ok(vec![]);
            }

            if let Some(client) = reranker_client {
                let all_nodes: Vec<Node> = method_results
                    .iter()
                    .flat_map(|list| list.iter().cloned())
                    .collect();
                let documents: Vec<String> = all_nodes
                    .iter()
                    .map(|n| n.summary.clone().unwrap_or_else(|| n.name.clone()))
                    .collect();
                let top_k = Some(documents.len().min(100));

                match client.rerank(query, documents, top_k).await {
                    Ok(ranked) => {
                        let mut seen = HashSet::new();
                        let mut result = Vec::with_capacity(ranked.len());
                        for (idx, _score) in ranked {
                            if let Some(node) = all_nodes.get(idx).cloned() {
                                if seen.insert(node.uuid) {
                                    result.push(node);
                                }
                            }
                        }
                        Ok(result)
                    }
                    Err(e) => {
                        tracing::warn!("Cross-encoder failed, falling back to RRF: {}", e);
                        Ok(reciprocal_rank_fusion(method_results, 60.0, |node| {
                            node.uuid.to_string()
                        }))
                    }
                }
            } else {
                Ok(reciprocal_rank_fusion(method_results, 60.0, |node| {
                    node.uuid.to_string()
                }))
            }
        }
        NodeReranker::CentralityBoosted => {
            let all_nodes: Vec<Node> = method_results.into_iter().flatten().collect();
            Ok(centrality_boosted_rerank(
                all_nodes,
                query_vector,
                |node| node.embedding.as_deref(),
                |node| node.centrality,
                centrality_boost_factor,
                100,
            ))
        }
        NodeReranker::NodeDistance | NodeReranker::EpisodeMentions => {
            // Would require additional context
            let all_nodes: Vec<Node> = method_results.into_iter().flatten().collect();
            Ok(all_nodes)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use uuid::Uuid;
    use wiremock::matchers::{body_string_contains, method, path};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    #[derive(Debug, Clone)]
    struct MockNode {
        id: String,
        centrality: Option<f32>,
        embedding: Option<Vec<f32>>,
    }

    fn test_edge(fact: &str) -> Edge {
        Edge {
            uuid: Uuid::new_v4(),
            source_node_uuid: Uuid::new_v4(),
            target_node_uuid: Uuid::new_v4(),
            fact: fact.to_string(),
            created_at: Utc::now(),
            episodes: vec![],
            group_id: None,
            weight: 1.0,
        }
    }

    fn test_node(name: &str, summary: Option<&str>) -> Node {
        Node {
            uuid: Uuid::new_v4(),
            name: name.to_string(),
            node_type: "Test".to_string(),
            summary: summary.map(|s| s.to_string()),
            created_at: Utc::now(),
            embedding: None,
            group_id: None,
            centrality: None,
        }
    }

    fn edge_uuids(edges: &[Edge]) -> Vec<Uuid> {
        edges.iter().map(|e| e.uuid).collect()
    }

    fn node_uuids(nodes: &[Node]) -> Vec<Uuid> {
        nodes.iter().map(|n| n.uuid).collect()
    }

    #[test]
    fn test_rrf() {
        let list1 = vec!["a", "b", "c"];
        let list2 = vec!["b", "c", "d"];
        let list3 = vec!["c", "d", "e"];

        let result = reciprocal_rank_fusion(vec![list1, list2, list3], 60.0, |s| s.to_string());

        // "c" should rank highest as it appears in all lists
        assert_eq!(result[0], "c");
    }

    #[test]
    fn test_centrality_boosted_rerank() {
        let nodes = vec![
            MockNode {
                id: "low_centrality".to_string(),
                centrality: Some(0.1),
                embedding: Some(vec![1.0, 0.0, 0.0]),
            },
            MockNode {
                id: "high_centrality".to_string(),
                centrality: Some(0.8),
                embedding: Some(vec![0.5, 0.5, 0.0]),
            },
            MockNode {
                id: "medium_centrality".to_string(),
                centrality: Some(0.4),
                embedding: Some(vec![0.8, 0.2, 0.0]),
            },
        ];

        let query_embedding = vec![1.0, 0.0, 0.0]; // Should match low_centrality best
        let boost_factor = 2.0;

        let result = centrality_boosted_rerank(
            nodes,
            Some(&query_embedding),
            |node| node.embedding.as_deref(),
            |node| node.centrality,
            boost_factor,
            10,
        );

        // Despite lower semantic similarity, high_centrality should rank first due to boost
        assert_eq!(result[0].id, "high_centrality");
    }

    #[tokio::test]
    async fn test_rerank_edges_crossencoder_falls_back_to_rrf_when_disabled() {
        let edge_a = test_edge("A");
        let edge_b = test_edge("B");

        let method_results = vec![vec![edge_a.clone(), edge_b.clone()], vec![edge_b.clone()]];
        let expected = reciprocal_rank_fusion(method_results.clone(), 60.0, |e| e.uuid.to_string());

        let got = rerank_edges(
            method_results,
            &EdgeReranker::CrossEncoder,
            "q",
            None,
            0.5,
            None,
        )
        .await
        .unwrap();

        assert_eq!(edge_uuids(&got), edge_uuids(&expected));
    }

    #[tokio::test]
    async fn test_rerank_nodes_crossencoder_falls_back_to_rrf_when_disabled() {
        let node_a = test_node("A", None);
        let node_b = test_node("B", None);

        let method_results = vec![vec![node_a.clone(), node_b.clone()], vec![node_b.clone()]];
        let expected = reciprocal_rank_fusion(method_results.clone(), 60.0, |n| n.uuid.to_string());

        let got = rerank_nodes(
            method_results,
            &NodeReranker::CrossEncoder,
            "q",
            None,
            0.5,
            0.0,
            None,
        )
        .await
        .unwrap();

        assert_eq!(node_uuids(&got), node_uuids(&expected));
    }

    #[tokio::test]
    async fn test_rerank_nodes_crossencoder_falls_back_to_rrf_on_http_error() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/rerank"))
            .and(body_string_contains("\"query\""))
            .respond_with(ResponseTemplate::new(500).set_body_string("boom"))
            .mount(&server)
            .await;

        let client = RerankerClient::new(&server.uri(), 2_000).unwrap();

        let node_a = test_node("A", Some("node A"));
        let node_b = test_node("B", Some("node B"));

        let method_results = vec![vec![node_a.clone(), node_b.clone()], vec![node_b.clone()]];
        let expected = reciprocal_rank_fusion(method_results.clone(), 60.0, |n| n.uuid.to_string());

        let got = rerank_nodes(
            method_results,
            &NodeReranker::CrossEncoder,
            "q",
            None,
            0.5,
            0.0,
            Some(&client),
        )
        .await
        .unwrap();

        assert_eq!(node_uuids(&got), node_uuids(&expected));
    }
}
