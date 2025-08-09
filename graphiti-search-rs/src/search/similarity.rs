use crate::error::{SearchError, SearchResult};
use crate::falkor::FalkorConnection;
use crate::models::{Community, Edge, Node};
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
    sorted_results.par_sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap());
    sorted_results
}

#[instrument(skip(conn, embedding))]
pub async fn search_nodes_by_embedding(
    conn: &mut FalkorConnection,
    embedding: &[f32],
    min_score: f32,
    limit: usize,
) -> SearchResult<Vec<Node>> {
    conn.similarity_search_nodes(embedding, limit, min_score)
        .await
        .map_err(|e| SearchError::Database(e.to_string()))
}

#[instrument(skip(_conn, _embedding))]
pub async fn search_edges_by_embedding(
    _conn: &mut FalkorConnection,
    _embedding: &[f32],
    _min_score: f32,
    _limit: usize,
) -> SearchResult<Vec<Edge>> {
    // For edges, we typically search based on connected nodes' embeddings
    // This is a simplified implementation
    Ok(vec![])
}

#[instrument(skip(_conn, _embedding))]
pub async fn search_communities_by_embedding(
    _conn: &mut FalkorConnection,
    _embedding: &[f32],
    _min_score: f32,
    _limit: usize,
) -> SearchResult<Vec<Community>> {
    // Community search by embedding
    Ok(vec![])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cosine_similarity() {
        let a = vec![1.0, 2.0, 3.0, 4.0];
        let b = vec![1.0, 2.0, 3.0, 4.0];
        assert!((cosine_similarity_simd(&a, &b) - 1.0).abs() < 0.0001);

        let c = vec![-1.0, -2.0, -3.0, -4.0];
        assert!((cosine_similarity_simd(&a, &c) + 1.0).abs() < 0.0001);
    }

    #[test]
    fn test_batch_similarity() {
        let query = vec![1.0, 2.0, 3.0];
        let vectors = vec![
            vec![1.0, 2.0, 3.0],    // Same as query
            vec![2.0, 4.0, 6.0],    // Same direction
            vec![-1.0, -2.0, -3.0], // Opposite direction
        ];

        let results = _batch_cosine_similarity(&query, &vectors, Some(0.5));
        assert_eq!(results.len(), 2); // Should filter out the negative similarity
        assert_eq!(results[0].0, 0); // First vector should be most similar
    }
}
