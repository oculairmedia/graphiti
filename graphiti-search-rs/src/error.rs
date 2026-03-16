use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::json;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum SearchError {
    #[error("Database error: {0}")]
    Database(String),

    #[error("Cache error: {0}")]
    Cache(String),

    #[error("Invalid query: {0}")]
    InvalidQuery(String),

    #[error("Serialization error: {0}")]
    Serialization(#[from] serde_json::Error),

    #[error("Vector operation error: {0}")]
    VectorOperation(String),

    #[error("Reranking error: {0}")]
    Reranking(String),

    #[error("Configuration error: {0}")]
    Configuration(String),

    #[error("Internal error: {0}")]
    Internal(#[from] anyhow::Error),
}

impl IntoResponse for SearchError {
    fn into_response(self) -> Response {
        let (status, error_message) = match self {
            SearchError::InvalidQuery(msg) => (StatusCode::BAD_REQUEST, msg),
            SearchError::Database(msg) => (StatusCode::SERVICE_UNAVAILABLE, msg),
            SearchError::Cache(msg) => {
                tracing::warn!("Cache error (non-fatal): {}", msg);
                (
                    StatusCode::OK,
                    "Cache miss, proceeding without cache".to_string(),
                )
            }
            _ => (StatusCode::INTERNAL_SERVER_ERROR, self.to_string()),
        };

        let body = Json(json!({
            "error": error_message,
            "status": status.as_u16(),
        }));

        (status, body).into_response()
    }
}

pub type SearchResult<T> = Result<T, SearchError>;

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::to_bytes;
    use serde_json::Value;

    async fn response_body(error: SearchError) -> Value {
        let response = error.into_response();
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn invalid_query_maps_to_bad_request() {
        let response = SearchError::InvalidQuery("bad query".to_string()).into_response();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);

        let body = response_body(SearchError::InvalidQuery("bad query".to_string())).await;
        assert_eq!(body["error"], "bad query");
        assert_eq!(body["status"], 400);
    }

    #[tokio::test]
    async fn database_error_maps_to_service_unavailable() {
        let response = SearchError::Database("redis down".to_string()).into_response();
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);

        let body = response_body(SearchError::Database("redis down".to_string())).await;
        assert_eq!(body["error"], "redis down");
        assert_eq!(body["status"], 503);
    }

    #[tokio::test]
    async fn cache_error_maps_to_ok_with_degraded_message() {
        let response = SearchError::Cache("cache offline".to_string()).into_response();
        assert_eq!(response.status(), StatusCode::OK);

        let body = response_body(SearchError::Cache("cache offline".to_string())).await;
        assert_eq!(body["error"], "Cache miss, proceeding without cache");
        assert_eq!(body["status"], 200);
    }

    #[tokio::test]
    async fn reranking_error_maps_to_internal_server_error() {
        let response = SearchError::Reranking("reranker failed".to_string()).into_response();
        assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);

        let body = response_body(SearchError::Reranking("reranker failed".to_string())).await;
        assert_eq!(body["error"], "Reranking error: reranker failed");
        assert_eq!(body["status"], 500);
    }

    #[tokio::test]
    async fn internal_error_maps_to_internal_server_error() {
        let response = SearchError::Internal(anyhow::anyhow!("unexpected")).into_response();
        assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);

        let body = response_body(SearchError::Internal(anyhow::anyhow!("unexpected"))).await;
        assert_eq!(body["error"], "Internal error: unexpected");
        assert_eq!(body["status"], 500);
    }
}
