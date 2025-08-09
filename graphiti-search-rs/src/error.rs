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
