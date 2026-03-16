use graphiti_search_rs::reranker::RerankerClient;
use graphiti_search_rs::retry::RetryConfig;

use serde_json::json;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Duration;
use wiremock::matchers::{body_json, method, path};
use wiremock::{Mock, MockServer, Request, Respond, ResponseTemplate};

#[derive(Clone)]
struct SequencedResponder {
    attempts: Arc<AtomicUsize>,
    failures_before_success: usize,
    failure_status: u16,
}

impl Respond for SequencedResponder {
    fn respond(&self, _request: &Request) -> ResponseTemplate {
        let attempt = self.attempts.fetch_add(1, Ordering::SeqCst);
        if attempt < self.failures_before_success {
            ResponseTemplate::new(self.failure_status).set_body_string("temporary failure")
        } else {
            ResponseTemplate::new(200).set_body_json(json!({
                "results": [
                    {"index": 1, "relevance_score": 0.05},
                    {"index": 0, "relevance_score": 0.28}
                ]
            }))
        }
    }
}

#[tokio::test]
async fn test_reranker_client_success() {
    let mock_server = MockServer::start().await;

    Mock::given(method("POST"))
        .and(path("/rerank"))
        .and(body_json(json!({
            "model": "qwen3-reranker-4b",
            "query": "test query",
            "documents": ["doc1", "doc2"],
            "top_k": 10
        })))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "results": [
                {"index": 1, "relevance_score": 0.05},
                {"index": 0, "relevance_score": 0.28}
            ]
        })))
        .mount(&mock_server)
        .await;

    let client = RerankerClient::new(
        &mock_server.uri(),
        5_000,
        RetryConfig::new(3, Duration::from_millis(1)),
    )
    .unwrap();

    let ranked = client
        .rerank(
            "test query",
            vec!["doc1".to_string(), "doc2".to_string()],
            Some(10),
        )
        .await
        .unwrap();

    // Scores are returned directly (higher = more relevant)
    assert_eq!(ranked, vec![(1, 0.05), (0, 0.28)]);
}

#[tokio::test]
async fn test_reranker_client_timeout() {
    let mock_server = MockServer::start().await;

    Mock::given(method("POST"))
        .and(path("/rerank"))
        .respond_with(ResponseTemplate::new(200).set_delay(std::time::Duration::from_secs(5)))
        .mount(&mock_server)
        .await;

    let client = RerankerClient::new(
        &mock_server.uri(),
        10,
        RetryConfig::new(3, Duration::from_millis(1)),
    )
    .unwrap();
    let result = client.rerank("query", vec!["doc".to_string()], None).await;

    assert!(result.is_err());
}

#[tokio::test]
async fn test_reranker_client_retries_transient_failure() {
    let mock_server = MockServer::start().await;
    let attempts = Arc::new(AtomicUsize::new(0));

    Mock::given(method("POST"))
        .and(path("/rerank"))
        .respond_with(SequencedResponder {
            attempts: attempts.clone(),
            failures_before_success: 1,
            failure_status: 503,
        })
        .mount(&mock_server)
        .await;

    let client = RerankerClient::new(
        &mock_server.uri(),
        5_000,
        RetryConfig::new(3, Duration::from_millis(1)),
    )
    .unwrap();

    let ranked = client
        .rerank(
            "test query",
            vec!["doc1".to_string(), "doc2".to_string()],
            Some(10),
        )
        .await
        .unwrap();

    assert_eq!(attempts.load(Ordering::SeqCst), 2);
    assert_eq!(ranked, vec![(1, 0.05), (0, 0.28)]);
}

#[tokio::test]
async fn test_reranker_client_does_not_retry_client_errors() {
    let mock_server = MockServer::start().await;
    let attempts = Arc::new(AtomicUsize::new(0));

    Mock::given(method("POST"))
        .and(path("/rerank"))
        .respond_with(SequencedResponder {
            attempts: attempts.clone(),
            failures_before_success: 10,
            failure_status: 400,
        })
        .mount(&mock_server)
        .await;

    let client = RerankerClient::new(
        &mock_server.uri(),
        5_000,
        RetryConfig::new(3, Duration::from_millis(1)),
    )
    .unwrap();
    let result = client
        .rerank(
            "test query",
            vec!["doc1".to_string(), "doc2".to_string()],
            Some(10),
        )
        .await;

    assert!(result.is_err());
    assert_eq!(attempts.load(Ordering::SeqCst), 1);
}

#[tokio::test]
#[ignore]
async fn test_reranker_integration_real_service() {
    let client = RerankerClient::new(
        "http://100.81.139.20:11435",
        5_000,
        RetryConfig::new(3, Duration::from_millis(200)),
    )
    .unwrap();

    let ranked = client
        .rerank(
            "What is machine learning?",
            vec![
                "Machine learning is a subset of AI".to_string(),
                "The weather is nice today".to_string(),
                "Deep learning uses neural networks".to_string(),
            ],
            Some(3),
        )
        .await
        .unwrap();

    // The top result should not be the weather sentence.
    assert_ne!(ranked[0].0, 1);
}
