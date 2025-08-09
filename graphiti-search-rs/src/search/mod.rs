pub mod bfs;
pub mod fulltext;
pub mod reranking;
pub mod similarity;

use crate::error::SearchResult;
use crate::falkor::FalkorConnection;
use crate::models::{
    Community, Edge, EdgeSearchConfig, Episode, Node, NodeSearchConfig, SearchFilters,
    SearchMethod, SearchRequest, SearchResults,
};
use deadpool_redis::Pool as RedisPool;
use std::collections::HashMap;
use std::time::Instant;
use tracing::{debug, instrument};

pub struct SearchEngine {
    falkor_conn: FalkorConnection,
    redis_pool: RedisPool,
}

impl SearchEngine {
    pub fn new(falkor_conn: FalkorConnection, redis_pool: RedisPool) -> Self {
        Self {
            falkor_conn,
            redis_pool,
        }
    }

    #[instrument(skip(self))]
    pub async fn search(&mut self, request: SearchRequest) -> SearchResult<SearchResults> {
        let start = Instant::now();

        let mut edges = Vec::new();
        let mut nodes = Vec::new();
        let mut episodes = Vec::new();
        let mut communities = Vec::new();

        // Execute edge search if configured
        if let Some(edge_config) = &request.config.edge_config {
            edges = self
                .search_edges(
                    &request.query,
                    edge_config,
                    &request.filters,
                    request.query_vector.as_deref(),
                )
                .await?;
        }

        // Execute node search if configured
        if let Some(node_config) = &request.config.node_config {
            nodes = self
                .search_nodes(
                    &request.query,
                    node_config,
                    &request.filters,
                    request.query_vector.as_deref(),
                )
                .await?;
        }

        // Execute episode search if configured
        if request.config.episode_config.is_some() {
            episodes = self
                .search_episodes(&request.query, &request.filters, request.config.limit)
                .await?;
        }

        // Execute community search if configured
        if let Some(community_config) = &request.config.community_config {
            communities = self
                .search_communities(
                    &request.query,
                    community_config,
                    &request.filters,
                    request.query_vector.as_deref(),
                )
                .await?;
        }

        let latency_ms = start.elapsed().as_millis() as u64;
        debug!("Search completed in {}ms", latency_ms);

        Ok(SearchResults {
            edges,
            nodes,
            episodes,
            communities,
            latency_ms,
        })
    }

    async fn search_edges(
        &mut self,
        query: &str,
        config: &EdgeSearchConfig,
        filters: &SearchFilters,
        query_vector: Option<&[f32]>,
    ) -> SearchResult<Vec<Edge>> {
        let mut all_edges = HashMap::new();
        let mut method_results = Vec::new();

        for method in &config.search_methods {
            let edges = match method {
                SearchMethod::Fulltext => {
                    fulltext::search_edges(&mut self.falkor_conn, query, 100).await?
                }
                SearchMethod::Similarity if query_vector.is_some() => {
                    similarity::search_edges_by_embedding(
                        &mut self.falkor_conn,
                        query_vector.unwrap(),
                        config.sim_min_score,
                        100,
                    )
                    .await?
                }
                SearchMethod::Bfs => {
                    // BFS requires origin nodes, skip if not provided
                    vec![]
                }
                _ => vec![],
            };

            method_results.push(edges);
        }

        // Apply reranking
        let reranked = reranking::rerank_edges(
            method_results,
            &config.reranker,
            query_vector,
            config.mmr_lambda,
        )?;

        Ok(reranked)
    }

    async fn search_nodes(
        &mut self,
        query: &str,
        config: &NodeSearchConfig,
        filters: &SearchFilters,
        query_vector: Option<&[f32]>,
    ) -> SearchResult<Vec<Node>> {
        let mut method_results = Vec::new();

        for method in &config.search_methods {
            let nodes = match method {
                SearchMethod::Fulltext => {
                    fulltext::search_nodes(&mut self.falkor_conn, query, 100).await?
                }
                SearchMethod::Similarity if query_vector.is_some() => {
                    similarity::search_nodes_by_embedding(
                        &mut self.falkor_conn,
                        query_vector.unwrap(),
                        config.sim_min_score,
                        100,
                    )
                    .await?
                }
                SearchMethod::Bfs => {
                    // BFS requires origin nodes, skip if not provided
                    vec![]
                }
                _ => vec![],
            };

            method_results.push(nodes);
        }

        // Apply reranking
        let reranked = reranking::rerank_nodes(
            method_results,
            &config.reranker,
            query_vector,
            config.mmr_lambda,
        )?;

        Ok(reranked)
    }

    async fn search_episodes(
        &mut self,
        query: &str,
        filters: &SearchFilters,
        limit: usize,
    ) -> SearchResult<Vec<Episode>> {
        fulltext::search_episodes(&mut self.falkor_conn, query, limit).await
    }

    async fn search_communities(
        &mut self,
        query: &str,
        config: &CommunitySearchConfig,
        filters: &SearchFilters,
        query_vector: Option<&[f32]>,
    ) -> SearchResult<Vec<Community>> {
        // Communities are typically searched via similarity
        if let Some(embedding) = query_vector {
            similarity::search_communities_by_embedding(
                &mut self.falkor_conn,
                embedding,
                config.sim_min_score,
                50,
            )
            .await
        } else {
            Ok(vec![])
        }
    }
}
