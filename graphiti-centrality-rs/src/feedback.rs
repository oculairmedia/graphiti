use crate::client::FalkorClient;
use crate::error::Result;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use tracing::{debug, info, warn};
use chrono::{DateTime, Utc};
use falkordb::FalkorValue;

/// Feedback for memory relevance from Claude
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RelevanceFeedback {
    pub memory_id: String,
    pub query_id: String,
    pub score: f64,  // 0.0 to 1.0
    pub timestamp: DateTime<Utc>,
    pub source: FeedbackSource,
    pub metadata: Option<HashMap<String, String>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FeedbackSource {
    Claude,      // Direct feedback from Claude's evaluation
    Heuristic,   // Automatic heuristic-based scoring
    User,        // Explicit user feedback
}

/// Request to submit relevance feedback
#[derive(Debug, Deserialize)]
pub struct FeedbackRequest {
    pub query_id: String,
    pub query_text: String,
    pub memory_scores: HashMap<String, f64>,
    pub response_text: Option<String>,
    pub source: Option<FeedbackSource>,
}

/// Response after processing feedback
#[derive(Debug, Serialize)]
pub struct FeedbackResponse {
    pub status: String,
    pub processed_count: usize,
    pub updated_nodes: Vec<String>,
}

/// Feedback processor that updates graph with relevance scores
pub struct FeedbackProcessor {
    client: FalkorClient,
}

impl FeedbackProcessor {
    pub fn new(client: FalkorClient) -> Self {
        Self { client }
    }

    /// Process relevance feedback and update node scores
    pub async fn process_feedback(&self, request: FeedbackRequest) -> Result<FeedbackResponse> {
        let mut updated_nodes = Vec::new();
        let source = request.source.unwrap_or(FeedbackSource::Claude);
        
        info!(
            "Processing feedback for query {} with {} memories",
            request.query_id,
            request.memory_scores.len()
        );

        for (memory_id, score) in request.memory_scores.iter() {
            // Update the node with new relevance score
            // This uses exponential moving average to blend with existing score
            // FalkorDB doesn't support parameters in queries yet, so embed values
            let query = format!(
                r#"
                MATCH (n:Entity)
                WHERE n.memory_id = '{}' OR n.uuid = '{}'
                SET n.relevance_score = CASE 
                    WHEN n.relevance_score IS NULL THEN {}
                    ELSE (n.relevance_score * 0.7 + {} * 0.3)
                END,
                n.feedback_count = CASE
                    WHEN n.feedback_count IS NULL THEN 1
                    ELSE n.feedback_count + 1
                END,
                n.last_feedback = '{}',
                n.last_feedback_source = '{:?}'
                RETURN n.uuid as uuid, n.name as name, n.relevance_score as new_score
                "#,
                memory_id, memory_id, score, score, Utc::now().to_rfc3339(), source
            );

            match self.client.execute_query(&query, None).await {
                Ok(results) => {
                    if let Some(first_row) = results.first() {
                        if let Some(uuid_value) = first_row.get("uuid") {
                            // Extract string from FalkorValue
                            let uuid_str = match uuid_value {
                                FalkorValue::String(s) => s.clone(),
                                _ => format!("{:?}", uuid_value),
                            };
                            debug!(
                                "Updated node {} with relevance score {:.2}",
                                uuid_str, score
                            );
                            updated_nodes.push(uuid_str);
                        }
                    }
                }
                Err(e) => {
                    warn!("Failed to update node {}: {}", memory_id, e);
                }
            }
        }

        // Optionally trigger PageRank recalculation with feedback-weighted edges
        if updated_nodes.len() > 5 {
            info!("Triggering PageRank recalculation after significant feedback");
            self.trigger_pagerank_update().await?;
        }

        Ok(FeedbackResponse {
            status: "success".to_string(),
            processed_count: updated_nodes.len(),
            updated_nodes,
        })
    }

    /// Trigger PageRank recalculation with relevance weighting
    async fn trigger_pagerank_update(&self) -> Result<()> {
        // Update PageRank considering relevance scores as edge weights
        let query = r#"
            CALL algo.pageRank(
                'Entity', 
                'RELATES_TO',
                {
                    iterations: 20,
                    dampingFactor: 0.85,
                    weightProperty: 'relevance_score'
                }
            ) YIELD node, score
            SET node.pagerank = score
            RETURN count(node) as updated_count
        "#;

        match self.client.execute_query(query, None).await {
            Ok(_) => {
                info!("PageRank updated with relevance weighting");
                Ok(())
            }
            Err(e) => {
                warn!("Failed to update PageRank: {}", e);
                // Non-fatal error - feedback was still recorded
                Ok(())
            }
        }
    }

    /// Get feedback statistics for a query
    pub async fn get_feedback_stats(&self, query_id: &str) -> Result<HashMap<String, f64>> {
        let query = format!(r#"
            MATCH (n:Entity)
            WHERE n.last_query_id = '{}'
            RETURN 
                avg(n.relevance_score) as avg_score,
                max(n.relevance_score) as max_score,
                min(n.relevance_score) as min_score,
                count(n) as total_memories
        "#, query_id);
        
        let results = self.client.execute_query(&query, None).await?;
        
        if let Some(row) = results.first() {
            let mut stats = HashMap::new();
            if let Some(avg) = row.get("avg_score") {
                if let FalkorValue::F64(val) = avg {
                    stats.insert("avg_score".to_string(), *val);
                }
            }
            if let Some(max) = row.get("max_score") {
                if let FalkorValue::F64(val) = max {
                    stats.insert("max_score".to_string(), *val);
                }
            }
            if let Some(min) = row.get("min_score") {
                if let FalkorValue::F64(val) = min {
                    stats.insert("min_score".to_string(), *val);
                }
            }
            if let Some(total) = row.get("total_memories") {
                if let FalkorValue::I64(val) = total {
                    stats.insert("total_memories".to_string(), *val as f64);
                }
            }
            Ok(stats)
        } else {
            Ok(HashMap::new())
        }
    }
}