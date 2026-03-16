use axum::{
    body::Body,
    http::{Request, StatusCode},
};
use deadpool::managed::Pool;
use graphiti_search_rs::{config::Config, create_router, falkor::FalkorManager, AppState};
use tower::ServiceExt;

fn test_state() -> AppState {
    let mut config = Config::test_defaults();
    config.falkor_host = "127.0.0.1".to_string();
    config.falkor_port = 1;
    config.redis_url = "redis://127.0.0.1:6379".to_string();
    config.max_connections = 1;

    let falkor_pool = Pool::builder(FalkorManager::new(&config))
        .max_size(1)
        .build()
        .expect("falkor pool should build");
    let redis_pool = deadpool_redis::Config::from_url(config.redis_url.clone())
        .create_pool(Some(deadpool_redis::Runtime::Tokio1))
        .expect("redis pool should build");

    AppState {
        falkor_pool,
        redis_pool,
        config,
        reranker_client: None,
    }
}

fn test_app() -> axum::Router {
    create_router(test_state())
}

async fn malformed_post(path: &str) -> StatusCode {
    test_app()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri(path)
                .header("content-type", "application/json")
                .body(Body::from("{"))
                .unwrap(),
        )
        .await
        .unwrap()
        .status()
}

#[tokio::test]
async fn health_route_returns_service_unavailable_with_failing_pool() {
    let response = test_app()
        .oneshot(
            Request::builder()
                .uri("/health")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
}

#[tokio::test]
async fn search_route_rejects_malformed_json() {
    assert_eq!(malformed_post("/search").await, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn node_search_route_rejects_malformed_json() {
    assert_eq!(
        malformed_post("/search/nodes").await,
        StatusCode::BAD_REQUEST
    );
}

#[tokio::test]
async fn edge_search_route_rejects_malformed_json() {
    assert_eq!(
        malformed_post("/search/edges").await,
        StatusCode::BAD_REQUEST
    );
}

#[tokio::test]
async fn episode_search_route_rejects_malformed_json() {
    assert_eq!(
        malformed_post("/search/episodes").await,
        StatusCode::BAD_REQUEST
    );
}

#[tokio::test]
async fn community_search_route_rejects_malformed_json() {
    assert_eq!(
        malformed_post("/search/communities").await,
        StatusCode::BAD_REQUEST
    );
}

#[tokio::test]
async fn all_search_routes_are_registered() {
    for path in [
        "/search",
        "/search/nodes",
        "/search/edges",
        "/search/episodes",
        "/search/communities",
    ] {
        let status = malformed_post(path).await;
        assert_ne!(status, StatusCode::NOT_FOUND);
        assert_ne!(status, StatusCode::METHOD_NOT_ALLOWED);
    }
}
