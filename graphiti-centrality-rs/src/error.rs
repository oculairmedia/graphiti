use thiserror::Error;

/// Result type for centrality operations
pub type Result<T> = std::result::Result<T, CentralityError>;

/// Errors that can occur during centrality calculations
#[derive(Error, Debug)]
pub enum CentralityError {
    #[error("FalkorDB connection error: {0}")]
    Database(#[from] falkordb::FalkorDBError),

    #[error("Invalid algorithm parameter: {message}")]
    InvalidParameter { message: String },

    #[error("Algorithm execution failed: {message}")]
    AlgorithmFailed { message: String },

    #[error("Graph not found: {graph_name}")]
    GraphNotFound { graph_name: String },

    #[error("No nodes found matching criteria")]
    NoNodesFound,

    #[error("Serialization error: {0}")]
    Serialization(#[from] serde_json::Error),

    #[error("HTTP server error: {0}")]
    Http(#[from] axum::Error),

    #[error("Internal error: {0}")]
    Internal(String),
}

impl CentralityError {
    pub fn invalid_parameter(message: impl Into<String>) -> Self {
        Self::InvalidParameter {
            message: message.into(),
        }
    }

    pub fn algorithm_failed(message: impl Into<String>) -> Self {
        Self::AlgorithmFailed {
            message: message.into(),
        }
    }

    pub fn internal(message: impl Into<String>) -> Self {
        Self::Internal(message.into())
    }
}