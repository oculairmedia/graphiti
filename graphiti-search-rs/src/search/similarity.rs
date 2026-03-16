use crate::error::{SearchError, SearchResult};
use crate::falkor::FalkorConnection;
use crate::models::{Community, Edge, Node, SearchFilters};
use rayon::prelude::*;
use std::sync::Arc;
use tracing::instrument;

/// Calculate cosine similarity between two vectors
#[inline]
pub fn cosine_similarity_simd(a: &[f32], b: &[f32]) -> f32 {
    if a.len() != b.len() {
        return 0.0;
    }

    // For now, use scalar implementation
    // TODO: Add SIMD optimization later
    cosine_similarity_scalar(a, b)
}

/// Scalar fallback for cosine similarity
fn cosine_similarity_scalar(a: &[f32], b: &[f32]) -> f32 {
    let mut dot_product = 0.0;
    let mut norm_a = 0.0;
    let mut norm_b = 0.0;

    for i in 0..a.len() {
        dot_product += a[i] * b[i];
        norm_a += a[i] * a[i];
        norm_b += b[i] * b[i];
    }

    if norm_a == 0.0 || norm_b == 0.0 {
        return 0.0;
    }

    dot_product / (norm_a.sqrt() * norm_b.sqrt())
}

/// Batch cosine similarity calculation with parallelization
pub fn _batch_cosine_similarity(
    query_vector: &[f32],
    vectors: &[Vec<f32>],
    threshold: Option<f32>,
) -> Vec<(usize, f32)> {
    let query = Arc::new(query_vector.to_vec());

    let results: Vec<(usize, f32)> = vectors
        .par_iter()
        .enumerate()
        .filter_map(|(idx, vec)| {
            let similarity = cosine_similarity_simd(&query, vec);
            if let Some(min_score) = threshold {
                if similarity >= min_score {
                    Some((idx, similarity))
                } else {
                    None
                }
            } else {
                Some((idx, similarity))
            }
        })
        .collect();

    // Sort by similarity descending
    let mut sorted_results = results;
    sorted_results.par_sort_by(|a, b| b.1.total_cmp(&a.1));
    sorted_results
}

#[instrument(skip(conn, embedding))]
pub async fn search_nodes_by_embedding(
    conn: &mut FalkorConnection,
    embedding: &[f32],
    min_score: f32,
    filters: &SearchFilters,
    limit: usize,
) -> SearchResult<Vec<Node>> {
    conn.similarity_search_nodes(embedding, limit, min_score, filters.group_ids.as_deref())
        .await
        .map_err(|e| SearchError::Database(e.to_string()))
}

#[instrument(skip(conn, embedding))]
pub async fn search_edges_by_embedding(
    conn: &mut FalkorConnection,
    embedding: &[f32],
    min_score: f32,
    filters: &SearchFilters,
    limit: usize,
) -> SearchResult<Vec<Edge>> {
    conn.similarity_search_edges(embedding, limit, min_score, filters.group_ids.as_deref())
        .await
        .map_err(|e| SearchError::Database(e.to_string()))
}

#[instrument(skip(_conn, _embedding))]
pub async fn search_communities_by_embedding(
    _conn: &mut FalkorConnection,
    _embedding: &[f32],
    _min_score: f32,
    _filters: &SearchFilters,
    _limit: usize,
) -> SearchResult<Vec<Community>> {
    // Community search by embedding
    Ok(vec![])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cosine_identical_vectors_is_one() {
        let vector = vec![1.0, 2.0, 3.0, 4.0];
        assert!((cosine_similarity_simd(&vector, &vector) - 1.0).abs() < 0.0001);
    }

    #[test]
    fn cosine_orthogonal_vectors_is_zero() {
        let a = vec![1.0, 0.0, 0.0];
        let b = vec![0.0, 1.0, 0.0];
        assert!(cosine_similarity_simd(&a, &b).abs() < 0.0001);
    }

    #[test]
    fn cosine_opposite_vectors_is_negative_one() {
        let a = vec![1.0, 2.0, 3.0, 4.0];
        let b = vec![-1.0, -2.0, -3.0, -4.0];
        assert!((cosine_similarity_simd(&a, &b) + 1.0).abs() < 0.0001);
    }

    #[test]
    fn cosine_mismatched_dimensions_returns_zero() {
        let a = vec![1.0, 0.0];
        let b = vec![1.0, 0.0, 0.0];
        assert_eq!(cosine_similarity_simd(&a, &b), 0.0);
    }

    #[test]
    fn cosine_zero_vector_returns_zero_without_nan() {
        let a = vec![0.0, 0.0, 0.0];
        let b = vec![1.0, 0.0, 0.0];
        let similarity = cosine_similarity_simd(&a, &b);
        assert_eq!(similarity, 0.0);
        assert!(!similarity.is_nan());
    }

    #[test]
    fn cosine_empty_vectors_returns_zero_without_nan() {
        let a: Vec<f32> = vec![];
        let b: Vec<f32> = vec![];
        let similarity = cosine_similarity_simd(&a, &b);
        assert_eq!(similarity, 0.0);
        assert!(!similarity.is_nan());
    }

    #[test]
    fn cosine_nan_input_does_not_panic() {
        let a = vec![f32::NAN, 1.0];
        let b = vec![1.0, 0.0];
        let similarity = cosine_similarity_simd(&a, &b);
        assert!(similarity.is_nan());
    }

    #[test]
    fn batch_similarity_filters_and_sorts_descending() {
        let query = vec![1.0, 0.0];
        let vectors = vec![vec![1.0, 0.0], vec![0.5, 0.5], vec![-1.0, 0.0]];

        let results = _batch_cosine_similarity(&query, &vectors, Some(0.5));
        assert_eq!(results.len(), 2);
        assert_eq!(results[0].0, 0);
        assert!(results[0].1 >= results[1].1);
    }

    #[test]
    fn batch_similarity_handles_nan_scores_without_panicking() {
        let query = vec![1.0, 0.0];
        let vectors = vec![vec![f32::NAN, 0.0], vec![1.0, 0.0]];

        let results = _batch_cosine_similarity(&query, &vectors, None);
        assert_eq!(results.len(), 2);
        assert!(results.iter().any(|(_, score)| score.is_nan()));
        assert!(results
            .iter()
            .any(|(idx, score)| *idx == 1 && score.is_finite()));
    }
}
