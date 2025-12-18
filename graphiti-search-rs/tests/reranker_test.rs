use graphiti_search_rs::reranker::RerankerClient;

use serde_json::json;
use wiremock::matchers::{body_json, method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

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

    let client = RerankerClient::new(&mock_server.uri(), 5_000).unwrap();

    let ranked = client
        .rerank(
            "test query",
            vec!["doc1".to_string(), "doc2".to_string()],
            Some(10),
        )
        .await
        .unwrap();

    // Scores are inverted (1.0 - score), so 0.05 -> 0.95, 0.28 -> 0.72
    assert_eq!(ranked, vec![(1, 0.95), (0, 0.72)]);
}

#[tokio::test]
async fn test_reranker_client_timeout() {
    let mock_server = MockServer::start().await;

    Mock::given(method("POST"))
        .and(path("/rerank"))
        .respond_with(ResponseTemplate::new(200).set_delay(std::time::Duration::from_secs(5)))
        .mount(&mock_server)
        .await;

    let client = RerankerClient::new(&mock_server.uri(), 10).unwrap();
    let result = client.rerank("query", vec!["doc".to_string()], None).await;

    assert!(result.is_err());
}

#[tokio::test]
#[ignore]
async fn test_reranker_integration_real_service() {
    let client = RerankerClient::new("http://100.81.139.20:11435", 5_000).unwrap();

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
