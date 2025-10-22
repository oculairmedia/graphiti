use thiserror::Error;

#[derive(Error, Debug)]
pub enum SyncError {
    #[error("Neo4j error: {0}")]
    Neo4j(#[from] neo4rs::Error),

    #[error("FalkorDB error: {0}")]
    FalkorDB(String),

    #[error("Configuration error: {0}")]
    Config(#[from] config::ConfigError),

    #[error("Channel send error: {0}")]
    ChannelSend(String),

    #[error("Channel receive error")]
    ChannelReceive,

    #[error("Serialization error: {0}")]
    Serialization(#[from] serde_json::Error),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Task join error: {0}")]
    TaskJoin(#[from] tokio::task::JoinError),

    #[error("Sync operation failed: {0}")]
    SyncFailed(String),

    #[error("Orchestration error: {0}")]
    Orchestration(String),

    #[error("Safety validation failed: {0}")]
    SafetyValidation(String),
}

pub type Result<T> = std::result::Result<T, SyncError>;
