use crate::error::SearchResult;
use crate::models::{Edge, EdgeReranker, Node, NodeReranker};
use crate::reranker::RerankerClient;
use crate::search::similarity::cosine_similarity_simd;
use std::collections::{HashMap, HashSet};
use std::time::{Duration, Instant};
use tracing::instrument;

/// Reciprocal Rank Fusion (RRF) for combining multiple ranked lists
/// Returns items with their RRF scores
pub fn reciprocal_rank_fusion<T: Clone>(
    ranked_lists: Vec<Vec<T>>,
    k: f32,
    get_id: impl Fn(&T) -> String + Sync,
) -> Vec<(T, f32)> {
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
    results
}

/// Centrality-based boosting for structurally important nodes
/// Returns items with their combined scores
pub fn centrality_boosted_rerank<T: Clone>(
    items: Vec<T>,
    query_embedding: Option<&[f32]>,
    get_embedding: impl Fn(&T) -> Option<&[f32]> + Sync,
    get_centrality: impl Fn(&T) -> Option<f32> + Sync,
    boost_factor: f32,
    limit: usize,
) -> Vec<(T, f32)> {
    if items.is_empty() {
        return vec![];
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

    // Return top results with scores
    scored_items.into_iter().take(limit).collect()
}

/// Maximal Marginal Relevance (MMR) for diversity-aware reranking
/// Returns items with their MMR scores
/// 
/// IMPORTANT: MMR has O(n²) complexity. The timeout_ms parameter prevents runaway computation
/// when input size is large. If timeout is reached, partial results are returned.
pub fn maximal_marginal_relevance<T: Clone>(
    items: Vec<T>,
    query_embedding: Option<&[f32]>,
    get_embedding: impl Fn(&T) -> Option<&[f32]> + Sync,
    lambda: f32,
    limit: usize,
    timeout_ms: u64,
) -> Vec<(T, f32)> {
    if items.is_empty() || query_embedding.is_none() {
        // Return items with default scores when no embedding available
        return items
            .into_iter()
            .take(limit)
            .enumerate()
            .map(|(i, item)| (item, 1.0 / (i + 1) as f32))
            .collect();
    }

    let query = query_embedding.unwrap();
    let mut selected: Vec<(T, f32)> = Vec::new();
    let mut remaining: Vec<(usize, &T)> = items.iter().enumerate().collect();

    // Timeout protection for O(n²) complexity
    let start = Instant::now();
    let timeout = Duration::from_millis(timeout_ms);

    while selected.len() < limit && !remaining.is_empty() {
        // Check timeout at start of each iteration
        if start.elapsed() > timeout {
            tracing::warn!(
                "MMR timeout after {}ms, returning {} partial results (requested {}, input size {})",
                start.elapsed().as_millis(),
                selected.len(),
                limit,
                items.len()
            );
            break;
        }

        let scores: Vec<f32> = remaining
            .iter()
            .map(|(_, item)| {
                if let Some(item_emb) = get_embedding(item) {
                    let relevance = cosine_similarity_simd(query, item_emb);

                    let max_similarity = selected
                        .iter()
                        .filter_map(|(s, _): &(T, f32)| get_embedding(s))
                        .map(|s_emb| cosine_similarity_simd(item_emb, s_emb))
                        .max_by(|a, b| a.partial_cmp(b).unwrap())
                        .unwrap_or(0.0);

                    lambda * relevance - (1.0 - lambda) * max_similarity
                } else {
                    0.0
                }
            })
            .collect();

        if let Some((max_idx, &max_score)) = scores
            .iter()
            .enumerate()
            .max_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap())
        {
            let (orig_idx, _item) = remaining.remove(max_idx);
            selected.push((items[orig_idx].clone(), max_score));
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

/// Helper to apply scores to edges from scored tuples
fn apply_scores_to_edges(scored: Vec<(Edge, f32)>) -> Vec<Edge> {
    scored
        .into_iter()
        .map(|(mut edge, score)| {
            edge.score = Some(score);
            edge
        })
        .collect()
}

#[instrument(skip(method_results, query_vector, reranker_client))]
pub async fn rerank_edges(
    method_results: Vec<Vec<Edge>>,
    reranker: &EdgeReranker,
    query: &str,
    query_vector: Option<&[f32]>,
    mmr_lambda: f32,
    mmr_timeout_ms: u64,
    reranker_client: Option<&RerankerClient>,
    limit: usize,
) -> SearchResult<Vec<Edge>> {
    match reranker {
        EdgeReranker::Rrf => {
            let scored = reciprocal_rank_fusion(method_results, 60.0, |edge| edge.uuid.to_string());
            Ok(apply_scores_to_edges(scored)
                .into_iter()
                .take(limit)
                .collect())
        }
        EdgeReranker::Mmr => {
            let all_edges: Vec<Edge> = method_results.into_iter().flatten().collect();
            let scored = maximal_marginal_relevance(
                all_edges,
                query_vector,
                |_edge| None,
                mmr_lambda,
                limit,
                mmr_timeout_ms,
            );
            Ok(apply_scores_to_edges(scored))
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
                let top_k = Some(documents.len().min(limit));

                tracing::info!(
                    "CrossEncoder reranking {} edges for query: {}",
                    documents.len(),
                    query
                );

                match client.rerank(query, documents, top_k).await {
                    Ok(ranked) => {
                        tracing::info!("CrossEncoder returned {} ranked results", ranked.len());
                        let mut seen = HashSet::new();
                        let mut result = Vec::with_capacity(ranked.len().min(limit));
                        for (idx, score) in ranked {
                            if result.len() >= limit {
                                break;
                            }
                            if let Some(mut edge) = all_edges.get(idx).cloned() {
                                if seen.insert(edge.uuid) {
                                    edge.score = Some(score);
                                    result.push(edge);
                                }
                            }
                        }
                        Ok(result)
                    }
                    Err(e) => {
                        tracing::warn!("Cross-encoder failed, falling back to RRF: {}", e);
                        let scored = reciprocal_rank_fusion(method_results, 60.0, |edge| {
                            edge.uuid.to_string()
                        });
                        Ok(apply_scores_to_edges(scored)
                            .into_iter()
                            .take(limit)
                            .collect())
                    }
                }
            } else {
                tracing::debug!(
                    "CrossEncoder requested but no reranker_client available, using RRF"
                );
                let scored =
                    reciprocal_rank_fusion(method_results, 60.0, |edge| edge.uuid.to_string());
                Ok(apply_scores_to_edges(scored)
                    .into_iter()
                    .take(limit)
                    .collect())
            }
        }
        EdgeReranker::NodeDistance => {
            // Would require distance calculation from graph - assign decreasing scores
            let all_edges: Vec<Edge> = method_results.into_iter().flatten().collect();
            let len = all_edges.len();
            Ok(all_edges
                .into_iter()
                .take(limit)
                .enumerate()
                .map(|(i, mut edge)| {
                    edge.score = Some(1.0 - (i as f32 / len.max(1) as f32));
                    edge
                })
                .collect())
        }
        EdgeReranker::EpisodeMentions => {
            // Sort by number of episode mentions and assign scores based on episode count
            let mut all_edges: Vec<Edge> = method_results.into_iter().flatten().collect();
            all_edges.sort_by_key(|edge| std::cmp::Reverse(edge.episodes.len()));
            let max_episodes = all_edges
                .first()
                .map(|e| e.episodes.len())
                .unwrap_or(1)
                .max(1);
            Ok(all_edges
                .into_iter()
                .take(limit)
                .map(|mut edge| {
                    edge.score = Some(edge.episodes.len() as f32 / max_episodes as f32);
                    edge
                })
                .collect())
        }
    }
}

/// Helper to apply scores to nodes from scored tuples
fn apply_scores_to_nodes(scored: Vec<(Node, f32)>) -> Vec<Node> {
    scored
        .into_iter()
        .map(|(mut node, score)| {
            node.score = Some(score);
            node
        })
        .collect()
}

#[allow(clippy::too_many_arguments)]
#[instrument(skip(method_results, query_vector, reranker_client))]
pub async fn rerank_nodes(
    method_results: Vec<Vec<Node>>,
    reranker: &NodeReranker,
    query: &str,
    query_vector: Option<&[f32]>,
    mmr_lambda: f32,
    mmr_timeout_ms: u64,
    centrality_boost_factor: f32,
    reranker_client: Option<&RerankerClient>,
    limit: usize,
) -> SearchResult<Vec<Node>> {
    match reranker {
        NodeReranker::Rrf => {
            let scored = reciprocal_rank_fusion(method_results, 60.0, |node| node.uuid.to_string());
            Ok(apply_scores_to_nodes(scored)
                .into_iter()
                .take(limit)
                .collect())
        }
        NodeReranker::Mmr => {
            let all_nodes: Vec<Node> = method_results.into_iter().flatten().collect();
            let scored = maximal_marginal_relevance(
                all_nodes,
                query_vector,
                |node| node.embedding.as_deref(),
                mmr_lambda,
                limit,
                mmr_timeout_ms,
            );
            Ok(apply_scores_to_nodes(scored))
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
                let top_k = Some(documents.len().min(limit));

                match client.rerank(query, documents, top_k).await {
                    Ok(ranked) => {
                        let mut seen = HashSet::new();
                        let mut result = Vec::with_capacity(ranked.len().min(limit));
                        for (idx, score) in ranked {
                            if result.len() >= limit {
                                break;
                            }
                            if let Some(mut node) = all_nodes.get(idx).cloned() {
                                if seen.insert(node.uuid) {
                                    node.score = Some(score);
                                    result.push(node);
                                }
                            }
                        }
                        Ok(result)
                    }
                    Err(e) => {
                        tracing::warn!("Cross-encoder failed, falling back to RRF: {}", e);
                        let scored = reciprocal_rank_fusion(method_results, 60.0, |node| {
                            node.uuid.to_string()
                        });
                        Ok(apply_scores_to_nodes(scored)
                            .into_iter()
                            .take(limit)
                            .collect())
                    }
                }
            } else {
                let scored =
                    reciprocal_rank_fusion(method_results, 60.0, |node| node.uuid.to_string());
                Ok(apply_scores_to_nodes(scored)
                    .into_iter()
                    .take(limit)
                    .collect())
            }
        }
        NodeReranker::CentralityBoosted => {
            let all_nodes: Vec<Node> = method_results.into_iter().flatten().collect();
            let scored = centrality_boosted_rerank(
                all_nodes,
                query_vector,
                |node| node.embedding.as_deref(),
                |node| node.centrality,
                centrality_boost_factor,
                limit,
            );
            Ok(apply_scores_to_nodes(scored))
        }
        NodeReranker::NodeDistance | NodeReranker::EpisodeMentions => {
            // Would require additional context - assign decreasing scores
            let all_nodes: Vec<Node> = method_results.into_iter().flatten().collect();
            let len = all_nodes.len();
            Ok(all_nodes
                .into_iter()
                .take(limit)
                .enumerate()
                .map(|(i, mut node)| {
                    node.score = Some(1.0 - (i as f32 / len.max(1) as f32));
                    node
                })
                .collect())
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
            score: None,
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
            score: None,
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
        assert_eq!(result[0].0, "c");
        // Should have a score
        assert!(result[0].1 > 0.0);
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
        assert_eq!(result[0].0.id, "high_centrality");
        // Should have a score
        assert!(result[0].1 > 0.0);
    }

    #[tokio::test]
    async fn test_rerank_edges_crossencoder_falls_back_to_rrf_when_disabled() {
        let edge_a = test_edge("A");
        let edge_b = test_edge("B");

        let method_results = vec![vec![edge_a.clone(), edge_b.clone()], vec![edge_b.clone()]];
        let expected_scored =
            reciprocal_rank_fusion(method_results.clone(), 60.0, |e| e.uuid.to_string());
        let expected_uuids: Vec<Uuid> = expected_scored.iter().map(|(e, _)| e.uuid).collect();

        let got = rerank_edges(
            method_results,
            &EdgeReranker::CrossEncoder,
            "q",
            None,
            0.5,
            5000,
            None,
            100,
        )
        .await
        .unwrap();

        assert_eq!(edge_uuids(&got), expected_uuids);
        // Verify scores are set
        assert!(got.iter().all(|e| e.score.is_some()));
    }

    #[tokio::test]
    async fn test_rerank_nodes_crossencoder_falls_back_to_rrf_when_disabled() {
        let node_a = test_node("A", None);
        let node_b = test_node("B", None);

        let method_results = vec![vec![node_a.clone(), node_b.clone()], vec![node_b.clone()]];
        let expected_scored =
            reciprocal_rank_fusion(method_results.clone(), 60.0, |n| n.uuid.to_string());
        let expected_uuids: Vec<Uuid> = expected_scored.iter().map(|(n, _)| n.uuid).collect();

        let got = rerank_nodes(
            method_results,
            &NodeReranker::CrossEncoder,
            "q",
            None,
            0.5,
            5000,
            0.0,
            None,
            100,
        )
        .await
        .unwrap();

        assert_eq!(node_uuids(&got), expected_uuids);
        // Verify scores are set
        assert!(got.iter().all(|n| n.score.is_some()));
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
        let expected_scored =
            reciprocal_rank_fusion(method_results.clone(), 60.0, |n| n.uuid.to_string());
        let expected_uuids: Vec<Uuid> = expected_scored.iter().map(|(n, _)| n.uuid).collect();

        let got = rerank_nodes(
            method_results,
            &NodeReranker::CrossEncoder,
            "q",
            None,
            0.5,
            5000,
            0.0,
            Some(&client),
            100,
        )
        .await
        .unwrap();

        assert_eq!(node_uuids(&got), expected_uuids);
        // Verify scores are set
        assert!(got.iter().all(|n| n.score.is_some()));
    }
}
