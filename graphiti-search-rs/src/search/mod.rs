pub mod bfs;
pub mod cache;
pub mod fulltext;
pub mod reranking;
pub mod similarity;

use crate::error::SearchResult;
use crate::falkor::FalkorPool;
use crate::models::{
    Community, CommunitySearchConfig, Edge, EdgeSearchConfig, Episode, Node, NodeSearchConfig,
    SearchFilters, SearchMethod, SearchRequest, SearchResults,
};
use deadpool_redis::Pool as RedisPool;
use std::time::Instant;
use tracing::{debug, instrument};

use self::cache::EnhancedCache;

pub struct SearchEngine {
    falkor_pool: FalkorPool,
    redis_pool: RedisPool,
    cache: EnhancedCache,
}

impl SearchEngine {
    pub fn new(falkor_pool: FalkorPool, redis_pool: RedisPool) -> Self {
        let cache = EnhancedCache::new(redis_pool.clone());
        Self {
            falkor_pool,
            redis_pool,
            cache,
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

    pub async fn search_edges(
        &mut self,
        query: &str,
        config: &EdgeSearchConfig,
        _filters: &SearchFilters,
        query_vector: Option<&[f32]>,
    ) -> SearchResult<Vec<Edge>> {
        // Create cache key
        let cache_key = format!(
            "edges:{}:{:?}:{}",
            query, config.search_methods, config.sim_min_score
        );

        // Clone values needed in the closure
        let query_str = query.to_string();
        let config_clone = config.clone();
        let query_vector_clone = query_vector.map(|v| v.to_vec());
        let falkor_pool = self.falkor_pool.clone();

        // Use enhanced cache with adaptive TTL, request coalescing, and negative caching
        let result = self
            .cache
            .get_or_compute(&cache_key, move || async move {
                let mut falkor_conn = falkor_pool
                    .get()
                    .await
                    .map_err(|e| anyhow::anyhow!("Failed to get connection: {}", e))?;
                let mut method_results = Vec::new();

                for method in &config_clone.search_methods {
                    let edges = match method {
                        SearchMethod::Fulltext => {
                            fulltext::search_edges(&mut falkor_conn, &query_str, 100).await?
                        }
                        SearchMethod::Similarity if query_vector_clone.is_some() => {
                            similarity::search_edges_by_embedding(
                                &mut falkor_conn,
                                query_vector_clone.as_ref().unwrap(),
                                config_clone.sim_min_score,
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
                    &config_clone.reranker,
                    query_vector_clone.as_deref(),
                    config_clone.mmr_lambda,
                )?;

                if reranked.is_empty() {
                    Ok(None)
                } else {
                    Ok(Some(reranked))
                }
            })
            .await?;

        Ok(result.unwrap_or_else(Vec::new))
    }

    pub async fn search_nodes(
        &mut self,
        query: &str,
        config: &NodeSearchConfig,
        _filters: &SearchFilters,
        query_vector: Option<&[f32]>,
    ) -> SearchResult<Vec<Node>> {
        // Create cache key
        let cache_key = format!(
            "nodes:{}:{:?}:{}",
            query, config.search_methods, config.sim_min_score
        );

        // Clone values needed in the closure
        let query_str = query.to_string();
        let config_clone = config.clone();
        let query_vector_clone = query_vector.map(|v| v.to_vec());
        let falkor_pool = self.falkor_pool.clone();

        // Use enhanced cache with adaptive TTL, request coalescing, and negative caching
        let result = self
            .cache
            .get_or_compute(&cache_key, move || async move {
                let mut falkor_conn = falkor_pool
                    .get()
                    .await
                    .map_err(|e| anyhow::anyhow!("Failed to get connection: {}", e))?;
                let mut method_results = Vec::new();

                for method in &config_clone.search_methods {
                    let nodes = match method {
                        SearchMethod::Fulltext => {
                            fulltext::search_nodes(&mut falkor_conn, &query_str, 100).await?
                        }
                        SearchMethod::Similarity if query_vector_clone.is_some() => {
                            similarity::search_nodes_by_embedding(
                                &mut falkor_conn,
                                query_vector_clone.as_ref().unwrap(),
                                config_clone.sim_min_score,
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
                    &config_clone.reranker,
                    query_vector_clone.as_deref(),
                    config_clone.mmr_lambda,
                )?;

                if reranked.is_empty() {
                    Ok(None)
                } else {
                    Ok(Some(reranked))
                }
            })
            .await?;

        Ok(result.unwrap_or_else(Vec::new))
    }

    pub async fn search_episodes(
        &mut self,
        query: &str,
        _filters: &SearchFilters,
        limit: usize,
    ) -> SearchResult<Vec<Episode>> {
        // Create cache key
        let cache_key = format!("episodes:{}:{}", query, limit);

        // Clone values needed in the closure
        let query_str = query.to_string();
        let limit_clone = limit;
        let falkor_pool = self.falkor_pool.clone();

        // Use enhanced cache
        let result = self
            .cache
            .get_or_compute(&cache_key, move || async move {
                let mut falkor_conn = falkor_pool
                    .get()
                    .await
                    .map_err(|e| anyhow::anyhow!("Failed to get connection: {}", e))?;

                let episodes =
                    fulltext::search_episodes(&mut falkor_conn, &query_str, limit_clone).await?;

                if episodes.is_empty() {
                    Ok(None)
                } else {
                    Ok(Some(episodes))
                }
            })
            .await?;

        Ok(result.unwrap_or_else(Vec::new))
    }

    pub async fn search_communities(
        &mut self,
        _query: &str,
        config: &CommunitySearchConfig,
        _filters: &SearchFilters,
        query_vector: Option<&[f32]>,
    ) -> SearchResult<Vec<Community>> {
        // Communities are typically searched via similarity
        if let Some(embedding) = query_vector {
            let mut falkor_conn = self.falkor_pool.get().await.map_err(|e| {
                crate::error::SearchError::Database(format!("Failed to get connection: {}", e))
            })?;

            similarity::search_communities_by_embedding(
                &mut falkor_conn,
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
