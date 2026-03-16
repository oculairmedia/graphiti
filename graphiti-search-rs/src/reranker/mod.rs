use crate::error::{SearchError, SearchResult};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::time::Duration;

/// Request format for vLLM /v1/rerank endpoint
#[derive(Debug, Serialize)]
struct RerankerRequest {
    /// Model name (e.g., "qwen3-reranker-4b")
    model: String,
    /// The search query
    query: String,
    /// Documents to rerank
    documents: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    top_k: Option<usize>,
}

#[derive(Debug, Deserialize)]
struct RerankerResult {
    index: usize,
    #[serde(alias = "score", alias = "relevance_score")]
    relevance_score: f32,
}

#[derive(Debug, Deserialize)]
struct RerankerResponse {
    results: Vec<RerankerResult>,
}

#[derive(Clone)]
pub struct RerankerClient {
    client: Client,
    base_url: String,
}

impl RerankerClient {
    pub fn new(base_url: &str, timeout_ms: u64) -> SearchResult<Self> {
        let client = Client::builder()
            .timeout(Duration::from_millis(timeout_ms))
            .pool_max_idle_per_host(10)
            .pool_idle_timeout(Duration::from_secs(300))
            .tcp_keepalive(Duration::from_secs(30))
            .build()
            .map_err(|e| SearchError::Reranking(format!("Failed to create HTTP client: {e}")))?;

        Ok(Self {
            client,
            base_url: base_url.trim_end_matches('/').to_string(),
        })
    }

    pub async fn rerank(
        &self,
        query: &str,
        documents: Vec<String>,
        top_k: Option<usize>,
    ) -> SearchResult<Vec<(usize, f32)>> {
        let request = RerankerRequest {
            model: "qwen3-reranker-4b".to_string(),
            query: query.to_string(),
            documents,
            top_k,
        };

        let response = self
            .client
            .post(format!("{}/rerank", self.base_url))
            .json(&request)
            .send()
            .await
            .map_err(|e| SearchError::Reranking(format!("Reranker request failed: {e}")))?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response
                .text()
                .await
                .unwrap_or_else(|_| "<failed to read body>".to_string());
            return Err(SearchError::Reranking(format!(
                "Reranker returned {status}: {body}"
            )));
        }

        let reranker_response: RerankerResponse = response
            .json()
            .await
            .map_err(|e| SearchError::Reranking(format!("Invalid reranker response: {e}")))?;

        // Return scores directly: the Qwen3-Reranker model produces relevance scores
        // where higher values indicate more relevant documents (0.99 = highly relevant, 0.01 = not relevant)
        Ok(reranker_response
            .results
            .into_iter()
            .map(|r| (r.index, r.relevance_score))
            .collect())
    }
}
