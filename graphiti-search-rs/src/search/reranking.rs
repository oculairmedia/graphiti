use crate::error::{SearchError, SearchResult};
use crate::models::{Edge, EdgeReranker, Node, NodeReranker};
use crate::search::similarity::cosine_similarity_simd;
use rayon::prelude::*;
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

    let mut results: Vec<(T, f32)> = scores.into_iter().map(|(_, v)| v).collect();
    results.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap());
    results.into_iter().map(|(item, _)| item).collect()
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
            .par_iter()
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
            let (orig_idx, item) = remaining.remove(max_idx);
            selected.push(items[orig_idx].clone());
        } else {
            break;
        }
    }

    selected
}

/// Node distance reranking based on graph distance from center node
pub fn node_distance_rerank<T>(
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

    items_with_distance.into_iter().map(|(item, _)| item).collect()
}

#[instrument(skip(method_results, query_vector))]
pub fn rerank_edges(
    method_results: Vec<Vec<Edge>>,
    reranker: &EdgeReranker,
    query_vector: Option<&[f32]>,
    mmr_lambda: f32,
) -> SearchResult<Vec<Edge>> {
    match reranker {
        EdgeReranker::Rrf => {
            Ok(reciprocal_rank_fusion(
                method_results,
                60.0,
                |edge| edge.uuid.to_string(),
            ))
        }
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
            // Cross-encoder reranking would require a model
            // For now, just combine and deduplicate
            let mut seen = HashSet::new();
            let mut result = Vec::new();
            for edges in method_results {
                for edge in edges {
                    if seen.insert(edge.uuid) {
                        result.push(edge);
                    }
                }
            }
            Ok(result)
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

#[instrument(skip(method_results, query_vector))]
pub fn rerank_nodes(
    method_results: Vec<Vec<Node>>,
    reranker: &NodeReranker,
    query_vector: Option<&[f32]>,
    mmr_lambda: f32,
) -> SearchResult<Vec<Node>> {
    match reranker {
        NodeReranker::Rrf => {
            Ok(reciprocal_rank_fusion(
                method_results,
                60.0,
                |node| node.uuid.to_string(),
            ))
        }
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
            // Cross-encoder reranking would require a model
            let mut seen = HashSet::new();
            let mut result = Vec::new();
            for nodes in method_results {
                for node in nodes {
                    if seen.insert(node.uuid) {
                        result.push(node);
                    }
                }
            }
            Ok(result)
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
    use uuid::Uuid;

    #[test]
    fn test_rrf() {
        let list1 = vec!["a", "b", "c"];
        let list2 = vec!["b", "c", "d"];
        let list3 = vec!["c", "d", "e"];

        let result = reciprocal_rank_fusion(
            vec![list1, list2, list3],
            60.0,
            |s| s.to_string(),
        );

        // "c" should rank highest as it appears in all lists
        assert_eq!(result[0], "c");
    }
}