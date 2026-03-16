use crate::retry::{retry_with_backoff, RetryConfig, RetryableError};
use anyhow::{anyhow, Result};
use reqwest::Client;
use reqwest::StatusCode;
use serde::{Deserialize, Serialize};
use std::env;
use std::time::Duration;
use std::{error::Error as StdError, fmt};
use tracing::{debug, warn};

pub fn l2_normalize_embedding(embedding: &mut [f32]) -> Option<f32> {
    let mut sumsq = 0f64;
    let mut non_finite = 0usize;

    for &v in embedding.iter() {
        if !v.is_finite() {
            non_finite += 1;
            continue;
        }
        let vf = v as f64;
        sumsq += vf * vf;
    }

    if non_finite > 0 {
        warn!(
            "Embedding contains {} non-finite values; leaving them unnormalized",
            non_finite
        );
    }

    let norm = sumsq.sqrt() as f32;
    if !norm.is_finite() || norm <= 0.0 {
        return None;
    }

    for v in embedding.iter_mut() {
        if v.is_finite() {
            *v /= norm;
        }
    }

    Some(norm)
}

#[derive(Debug, Serialize)]
struct EmbeddingRequest {
    input: String,
    model: String,
}

#[derive(Debug, Deserialize)]
struct EmbeddingResponse {
    data: Vec<EmbeddingData>,
}

#[derive(Debug, Deserialize)]
struct EmbeddingData {
    embedding: Vec<f32>,
}

pub struct OllamaEmbedder {
    client: Client,
    base_url: String,
    model: String,
    retry_config: RetryConfig,
}

#[derive(Debug)]
enum EmbeddingRequestError {
    Request(reqwest::Error),
    HttpStatus { status: StatusCode, body: String },
}

impl RetryableError for EmbeddingRequestError {
    fn is_retriable(&self) -> bool {
        match self {
            Self::Request(error) => error.is_timeout() || error.is_connect(),
            Self::HttpStatus { status, .. } => {
                *status == StatusCode::REQUEST_TIMEOUT
                    || *status == StatusCode::TOO_MANY_REQUESTS
                    || status.is_server_error()
            }
        }
    }
}

impl fmt::Display for EmbeddingRequestError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Request(error) => write!(f, "Embedding request failed: {error}"),
            Self::HttpStatus { status, body } => write!(f, "Embedding returned {status}: {body}"),
        }
    }
}

impl StdError for EmbeddingRequestError {}

impl Default for OllamaEmbedder {
    fn default() -> Self {
        Self::new()
    }
}

impl OllamaEmbedder {
    pub fn new() -> Self {
        let base_url = env::var("OLLAMA_BASE_URL")
            .unwrap_or_else(|_| "http://100.81.139.20:11434/v1".to_string());
        let model = env::var("OLLAMA_EMBEDDING_MODEL")
            .unwrap_or_else(|_| "dengcao/Qwen3-Embedding-4B:Q4_K_M".to_string());
        let retry_config = RetryConfig::new(
            env::var("EMBEDDER_MAX_RETRIES")
                .ok()
                .and_then(|value| value.parse().ok())
                .unwrap_or(3),
            Duration::from_millis(
                env::var("EMBEDDER_RETRY_BASE_MS")
                    .ok()
                    .and_then(|value| value.parse().ok())
                    .unwrap_or(200),
            ),
        );

        Self::with_config(base_url, model, Duration::from_secs(60), retry_config)
            .expect("Failed to build embedding HTTP client")
    }

    pub fn with_config(
        base_url: String,
        model: String,
        timeout: Duration,
        retry_config: RetryConfig,
    ) -> Result<Self> {
        debug!(
            "Ollama embedder initialized with URL: {}, Model: {}",
            base_url, model
        );

        let client = Client::builder()
            .pool_max_idle_per_host(10)
            .pool_idle_timeout(Duration::from_secs(300))
            .tcp_keepalive(Duration::from_secs(30))
            .timeout(timeout)
            .build()
            .map_err(|error| anyhow!("Failed to build embedding HTTP client: {error}"))?;

        Ok(Self {
            client,
            base_url,
            model,
            retry_config,
        })
    }

    pub async fn generate_embedding(&self, text: &str) -> Result<Option<Vec<f32>>> {
        let request = EmbeddingRequest {
            input: text.to_string(),
            model: self.model.clone(),
        };

        let url = format!("{}/embeddings", self.base_url);

        debug!("Generating embedding for text: '{}'", text);

        let response = retry_with_backoff("embedding request", self.retry_config, || async {
            let response = self
                .client
                .post(&url)
                .header("Authorization", "Bearer ollama")
                .json(&request)
                .send()
                .await
                .map_err(EmbeddingRequestError::Request)?;

            if response.status().is_success() {
                Ok(response)
            } else {
                let status = response.status();
                let body = response
                    .text()
                    .await
                    .unwrap_or_else(|_| "<failed to read body>".to_string());
                Err(EmbeddingRequestError::HttpStatus { status, body })
            }
        })
        .await
        .map_err(anyhow::Error::new)?;

        let embedding_response: EmbeddingResponse = response.json().await?;

        if let Some(data) = embedding_response.data.first() {
            debug!(
                "Generated embedding with {} dimensions",
                data.embedding.len()
            );
            return Ok(Some(data.embedding.clone()));
        }

        warn!("Embedding response did not include any vectors");
        Ok(None)
    }
}

// Singleton instance for reuse
lazy_static::lazy_static! {
    pub static ref EMBEDDER: OllamaEmbedder = OllamaEmbedder::new();
}
