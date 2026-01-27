pub mod bfs;
pub mod cache;
pub mod fulltext;
pub mod hipporag;
pub mod reranking;
pub mod similarity;

use crate::error::SearchResult;
use crate::falkor::FalkorPool;
use crate::models::{
    Community, CommunitySearchConfig, Edge, EdgeSearchConfig, Episode, Node, NodeSearchConfig,
    SearchFilters, SearchMethod, SearchRequest, SearchResults,
};
use deadpool_redis::Pool as RedisPool;
use std::cmp::Ordering;
use std::time::Instant;
use tracing::{debug, info, instrument};

/// Maximum number of seed edges/nodes to use for BFS expansion
/// Prevents exponential growth when BFS is combined with other search methods
const MAX_BFS_SEEDS: usize = 50;

use self::cache::EnhancedCache;

pub struct SearchEngine {
    falkor_pool: FalkorPool,
    #[allow(dead_code)]
    redis_pool: RedisPool,
    cache: EnhancedCache,
    max_method_results: usize,
    mmr_timeout_ms: u64,
    max_pre_rerank_results: usize,
    reranker_client: Option<crate::reranker::RerankerClient>,
}

impl SearchEngine {
    pub fn new(
        falkor_pool: FalkorPool,
        redis_pool: RedisPool,
        max_method_results: usize,
        mmr_timeout_ms: u64,
        max_pre_rerank_results: usize,
        reranker_client: Option<crate::reranker::RerankerClient>,
    ) -> Self {
        let cache = EnhancedCache::new(redis_pool.clone());
        Self {
            falkor_pool,
            redis_pool,
            cache,
            max_method_results,
            mmr_timeout_ms,
            max_pre_rerank_results,
            reranker_client,
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
                    request.config.limit,
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
                    request.config.limit,
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
        filters: &SearchFilters,
        query_vector: Option<&[f32]>,
        limit: usize,
    ) -> SearchResult<Vec<Edge>> {
        // Direct execution without cache
        let mut falkor_conn = self.falkor_pool.get().await.map_err(|e| {
            crate::error::SearchError::Database(format!("Failed to get connection: {}", e))
        })?;

        let mut method_results = Vec::new();

        for method in &config.search_methods {
            let edges = match method {
                SearchMethod::Fulltext => {
                    fulltext::search_edges(
                        &mut falkor_conn,
                        query,
                        filters,
                        self.max_method_results,
                    )
                    .await?
                }
                SearchMethod::Similarity if query_vector.is_some() => {
                    similarity::search_edges_by_embedding(
                        &mut falkor_conn,
                        query_vector.unwrap(),
                        config.sim_min_score,
                        filters,
                        self.max_method_results,
                    )
                    .await?
                }
                SearchMethod::Bfs => {
                    if method_results.is_empty() {
                        vec![]
                    } else {
                        let total_seeds: usize =
                            method_results.iter().map(|r: &Vec<Edge>| r.len()).sum();
                        let mut seed_edges: Vec<Edge> =
                            method_results.iter().flatten().cloned().collect();

                        seed_edges.sort_by(|a, b| {
                            b.score.partial_cmp(&a.score).unwrap_or(Ordering::Equal)
                        });
                        seed_edges.truncate(MAX_BFS_SEEDS);

                        if seed_edges.len() < total_seeds {
                            info!(
                                "BFS edge seeds capped from {} to {}",
                                total_seeds,
                                seed_edges.len()
                            );
                        }

                        let bfs_config = bfs::BfsConfig::from(config);
                        bfs::search_edges_bfs(
                            &mut falkor_conn,
                            seed_edges,
                            &bfs_config,
                            filters.group_ids.as_deref(),
                        )
                        .await
                        .unwrap_or_default()
                    }
                }
                SearchMethod::Hipporag => {
                    debug!("HippoRAG edge search not yet implemented, skipping");
                    vec![]
                }
                _ => vec![],
            };

            method_results.push(edges);
        }

        // Cap total results before reranking to prevent O(n²) explosion
        let total_results: usize = method_results.iter().map(|v| v.len()).sum();
        let method_results = if total_results > self.max_pre_rerank_results {
            tracing::warn!(
                "Capping {} edge results to {} before reranking",
                total_results,
                self.max_pre_rerank_results
            );
            let mut capped = Vec::new();
            let mut remaining = self.max_pre_rerank_results;
            for mut list in method_results {
                if remaining == 0 {
                    break;
                }
                list.truncate(remaining);
                remaining = remaining.saturating_sub(list.len());
                capped.push(list);
            }
            capped
        } else {
            method_results
        };

        // Apply reranking
        let reranked = reranking::rerank_edges(
            method_results,
            &config.reranker,
            query,
            query_vector,
            config.mmr_lambda,
            self.mmr_timeout_ms,
            self.reranker_client.as_ref(),
            limit,
        )
        .await?;

        Ok(reranked)
    }

    pub async fn search_nodes(
        &mut self,
        query: &str,
        config: &NodeSearchConfig,
        filters: &SearchFilters,
        query_vector: Option<&[f32]>,
        limit: usize,
    ) -> SearchResult<Vec<Node>> {
        // Direct execution without cache
        let mut falkor_conn = self.falkor_pool.get().await.map_err(|e| {
            crate::error::SearchError::Database(format!("Failed to get connection: {}", e))
        })?;

        let mut method_results = Vec::new();

        for method in &config.search_methods {
            let nodes = match method {
                SearchMethod::Fulltext => {
                    fulltext::search_nodes(
                        &mut falkor_conn,
                        query,
                        filters,
                        self.max_method_results,
                    )
                    .await?
                }
                SearchMethod::Similarity if query_vector.is_some() => {
                    similarity::search_nodes_by_embedding(
                        &mut falkor_conn,
                        query_vector.unwrap(),
                        config.sim_min_score,
                        filters,
                        self.max_method_results,
                    )
                    .await?
                }
                SearchMethod::Bfs => {
                    if method_results.is_empty() {
                        vec![]
                    } else {
                        let total_seeds: usize =
                            method_results.iter().map(|r: &Vec<Node>| r.len()).sum();
                        let mut seed_nodes: Vec<Node> =
                            method_results.iter().flatten().cloned().collect();

                        seed_nodes.sort_by(|a, b| {
                            b.score.partial_cmp(&a.score).unwrap_or(Ordering::Equal)
                        });
                        seed_nodes.truncate(MAX_BFS_SEEDS);

                        if seed_nodes.len() < total_seeds {
                            info!(
                                "BFS node seeds capped from {} to {}",
                                total_seeds,
                                seed_nodes.len()
                            );
                        }

                        let bfs_config = bfs::BfsConfig::from(config);
                        bfs::search_nodes_bfs(
                            &mut falkor_conn,
                            seed_nodes,
                            &bfs_config,
                            filters.group_ids.as_deref(),
                        )
                        .await
                        .unwrap_or_default()
                    }
                }
                SearchMethod::Hipporag if query_vector.is_some() => {
                    let hipporag_config = hipporag::HippoRAGConfig {
                        max_hops: config.hipporag_max_hops.unwrap_or(2),
                        decay: config.hipporag_decay.unwrap_or(0.85),
                        seed_count: config.hipporag_seed_count.unwrap_or(10),
                        min_score: config.sim_min_score,
                    };
                    hipporag::search_nodes_hipporag(
                        &mut falkor_conn,
                        query_vector.unwrap(),
                        &hipporag_config,
                        filters,
                        self.max_method_results,
                    )
                    .await?
                }
                _ => vec![],
            };

            method_results.push(nodes);
        }

        // Cap total results before reranking to prevent O(n²) explosion
        let total_results: usize = method_results.iter().map(|v| v.len()).sum();
        let method_results = if total_results > self.max_pre_rerank_results {
            tracing::warn!(
                "Capping {} node results to {} before reranking",
                total_results,
                self.max_pre_rerank_results
            );
            let mut capped = Vec::new();
            let mut remaining = self.max_pre_rerank_results;
            for mut list in method_results {
                if remaining == 0 {
                    break;
                }
                list.truncate(remaining);
                remaining = remaining.saturating_sub(list.len());
                capped.push(list);
            }
            capped
        } else {
            method_results
        };

        // Apply reranking with centrality boost factor
        let reranked = reranking::rerank_nodes(
            method_results,
            &config.reranker,
            query,
            query_vector,
            config.mmr_lambda,
            self.mmr_timeout_ms,
            config.centrality_boost_factor.unwrap_or(1.0),
            self.reranker_client.as_ref(),
            limit,
        )
        .await?;

        Ok(reranked)
    }

    pub async fn search_episodes(
        &mut self,
        query: &str,
        filters: &SearchFilters,
        limit: usize,
    ) -> SearchResult<Vec<Episode>> {
        // Create cache key
        let cache_key = format!("episodes:{query}:{limit}");

        // Clone values needed in the closure
        let query_str = query.to_string();
        let limit_clone = limit;
        let filters_clone = filters.clone();
        let falkor_pool = self.falkor_pool.clone();

        // Use enhanced cache
        let result = self
            .cache
            .get_or_compute(&cache_key, move || async move {
                let mut falkor_conn = falkor_pool
                    .get()
                    .await
                    .map_err(|e| anyhow::anyhow!("Failed to get connection: {}", e))?;

                let episodes = fulltext::search_episodes(
                    &mut falkor_conn,
                    &query_str,
                    &filters_clone,
                    limit_clone,
                )
                .await?;

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
        filters: &SearchFilters,
        query_vector: Option<&[f32]>,
    ) -> SearchResult<Vec<Community>> {
        // Communities are typically searched via similarity
        if let Some(embedding) = query_vector {
            let mut falkor_conn = self.falkor_pool.get().await.map_err(|e| {
                crate::error::SearchError::Database(format!("Failed to get connection: {e}"))
            })?;

            similarity::search_communities_by_embedding(
                &mut falkor_conn,
                embedding,
                config.sim_min_score,
                filters,
                50,
            )
            .await
        } else {
            Ok(vec![])
        }
    }
}
