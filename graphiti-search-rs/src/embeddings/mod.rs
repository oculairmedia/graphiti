use anyhow::Result;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::env;
use tracing::{debug, warn};

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

impl OllamaEmbedder {
    pub fn new() -> Self {
        let base_url = env::var("OLLAMA_BASE_URL")
            .unwrap_or_else(|_| "http://192.168.50.80:11434/v1".to_string());
        let model = env::var("OLLAMA_EMBEDDING_MODEL")
            .unwrap_or_else(|_| "mxbai-embed-large:latest".to_string());

        debug!("Ollama embedder initialized with URL: {}, Model: {}", base_url, model);

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

        let response = self.client
            .post(&url)
            .header("Authorization", "Bearer ollama")
            .json(&request)
            .send()
            .await?;

        if response.status().is_success() {
            let embedding_response: EmbeddingResponse = response.json().await?;
            
            if let Some(data) = embedding_response.data.first() {
                debug!("Generated embedding with {} dimensions", data.embedding.len());
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