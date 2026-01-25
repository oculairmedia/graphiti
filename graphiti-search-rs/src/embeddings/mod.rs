use anyhow::Result;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::env;
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
}

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

        debug!(
            "Ollama embedder initialized with URL: {}, Model: {}",
            base_url, model
        );

        Self {
            client: Client::new(),
            base_url,
            model,
        }
    }

    pub async fn generate_embedding(&self, text: &str) -> Result<Option<Vec<f32>>> {
        let request = EmbeddingRequest {
            input: text.to_string(),
            model: self.model.clone(),
        };

        let url = format!("{}/embeddings", self.base_url);

        debug!("Generating embedding for text: '{}'", text);

        let response = self
            .client
            .post(&url)
            .header("Authorization", "Bearer ollama")
            .json(&request)
            .send()
            .await?;

        if response.status().is_success() {
            let embedding_response: EmbeddingResponse = response.json().await?;

            if let Some(data) = embedding_response.data.first() {
                debug!(
                    "Generated embedding with {} dimensions",
                    data.embedding.len()
                );
                return Ok(Some(data.embedding.clone()));
            }
        } else {
            warn!("Failed to generate embedding: {}", response.status());
        }

        Ok(None)
    }
}

// Singleton instance for reuse
lazy_static::lazy_static! {
    pub static ref EMBEDDER: OllamaEmbedder = OllamaEmbedder::new();
}
