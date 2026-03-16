use graphiti_search_rs::embeddings::OllamaEmbedder;
use graphiti_search_rs::retry::RetryConfig;

use serde_json::json;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Duration;
use wiremock::matchers::{method, path};
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
                "data": [{"embedding": [1.0, 2.0, 3.0]}]
            }))
        }
    }
}

#[tokio::test]
async fn test_embedder_retries_transient_failure() {
    let mock_server = MockServer::start().await;
    let attempts = Arc::new(AtomicUsize::new(0));

    Mock::given(method("POST"))
        .and(path("/v1/embeddings"))
        .respond_with(SequencedResponder {
            attempts: attempts.clone(),
            failures_before_success: 1,
            failure_status: 503,
        })
        .mount(&mock_server)
        .await;

    let embedder = OllamaEmbedder::with_config(
        format!("{}/v1", mock_server.uri()),
        "test-model".to_string(),
        Duration::from_secs(5),
        RetryConfig::new(3, Duration::from_millis(1)),
    )
    .unwrap();

    let embedding = embedder.generate_embedding("hello world").await.unwrap();

    assert_eq!(attempts.load(Ordering::SeqCst), 2);
    assert_eq!(embedding, Some(vec![1.0, 2.0, 3.0]));
}

#[tokio::test]
async fn test_embedder_does_not_retry_client_errors() {
    let mock_server = MockServer::start().await;
    let attempts = Arc::new(AtomicUsize::new(0));

    Mock::given(method("POST"))
        .and(path("/v1/embeddings"))
        .respond_with(SequencedResponder {
            attempts: attempts.clone(),
            failures_before_success: 10,
            failure_status: 400,
        })
        .mount(&mock_server)
        .await;

    let embedder = OllamaEmbedder::with_config(
        format!("{}/v1", mock_server.uri()),
        "test-model".to_string(),
        Duration::from_secs(5),
        RetryConfig::new(3, Duration::from_millis(1)),
    )
    .unwrap();

    let result = embedder.generate_embedding("hello world").await;

    assert!(result.is_err());
    assert_eq!(attempts.load(Ordering::SeqCst), 1);
}
