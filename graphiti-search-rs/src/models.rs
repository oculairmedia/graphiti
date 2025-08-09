use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Node {
    pub uuid: Uuid,
    pub name: String,
    pub node_type: String,
    pub summary: Option<String>,
    pub created_at: DateTime<Utc>,
    pub embedding: Option<Vec<f32>>,
    pub group_id: Option<String>,
    pub centrality: Option<f32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Edge {
    pub uuid: Uuid,
    pub source_node_uuid: Uuid,
    pub target_node_uuid: Uuid,
    pub fact: String,
    pub created_at: DateTime<Utc>,
    pub episodes: Vec<Uuid>,
    pub group_id: Option<String>,
    pub weight: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Episode {
    pub uuid: Uuid,
    pub content: String,
    pub created_at: DateTime<Utc>,
    pub group_id: Option<String>,
    pub timestamp: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Community {
    pub uuid: Uuid,
    pub name: String,
    pub summary: String,
    pub members: Vec<Uuid>,
    pub created_at: DateTime<Utc>,
    pub embedding: Option<Vec<f32>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchRequest {
    pub query: String,
    pub config: SearchConfig,
    pub filters: SearchFilters,
    pub center_node_uuid: Option<Uuid>,
    pub bfs_origin_node_uuids: Option<Vec<Uuid>>,
    pub query_vector: Option<Vec<f32>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchConfig {
    pub edge_config: Option<EdgeSearchConfig>,
    pub node_config: Option<NodeSearchConfig>,
    pub episode_config: Option<EpisodeSearchConfig>,
    pub community_config: Option<CommunitySearchConfig>,
    pub limit: usize,
    pub reranker_min_score: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EdgeSearchConfig {
    pub search_methods: Vec<SearchMethod>,
    pub reranker: EdgeReranker,
    pub bfs_max_depth: usize,
    pub sim_min_score: f32,
    pub mmr_lambda: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NodeSearchConfig {
    pub search_methods: Vec<SearchMethod>,
    pub reranker: NodeReranker,
    pub bfs_max_depth: usize,
    pub sim_min_score: f32,
    pub mmr_lambda: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EpisodeSearchConfig {
    pub reranker: EpisodeReranker,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommunitySearchConfig {
    pub reranker: CommunityReranker,
    pub sim_min_score: f32,
    pub mmr_lambda: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SearchMethod {
    Fulltext,
    Similarity,
    Bfs,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EdgeReranker {
    Rrf,
    Mmr,
    CrossEncoder,
    NodeDistance,
    EpisodeMentions,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NodeReranker {
    Rrf,
    Mmr,
    CrossEncoder,
    EpisodeMentions,
    NodeDistance,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EpisodeReranker {
    Rrf,
    CrossEncoder,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CommunityReranker {
    Rrf,
    Mmr,
    CrossEncoder,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SearchFilters {
    pub node_types: Option<Vec<String>>,
    pub edge_types: Option<Vec<String>>,
    pub group_ids: Option<Vec<String>>,
    pub created_after: Option<DateTime<Utc>>,
    pub created_before: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResults {
    pub edges: Vec<Edge>,
    pub nodes: Vec<Node>,
    pub episodes: Vec<Episode>,
    pub communities: Vec<Community>,
    pub latency_ms: u64,
}
