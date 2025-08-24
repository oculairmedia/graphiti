#![allow(dead_code)]

use anyhow::Result;
use falkordb::{AsyncGraph, FalkorAsyncClient, FalkorClientBuilder, FalkorConnectionInfo};
use tracing::instrument;

use crate::config::Config;
use crate::falkor::parser_v2;
use crate::models::{Edge, Episode, Node};

pub struct FalkorClientV2 {
    #[allow(dead_code)]
    client: FalkorAsyncClient,
    graph: AsyncGraph,
}

impl FalkorClientV2 {
    pub async fn new(config: &Config) -> Result<Self> {
        // Build connection URL
        let conn_url = format!("redis://{}:{}", config.falkor_host, config.falkor_port);
        let conn_info: FalkorConnectionInfo = conn_url.try_into()?;

        // Create async client
        let client = FalkorClientBuilder::new_async()
            .with_connection_info(conn_info)
            .build()
            .await?;

        // Select the graph
        let graph = client.select_graph(&config.graph_name);

        Ok(Self { client, graph })
    }

    pub async fn ping(&mut self) -> Result<()> {
        // Test connection by running a simple query
        let _result = self.graph.query("RETURN 1").execute().await?;
        Ok(())
    }

    #[instrument(skip(self))]
    pub async fn fulltext_search_nodes(
        &mut self,
        query: &str,
        group_ids: Option<&[String]>,
        limit: usize,
    ) -> Result<Vec<Node>> {
        // FalkorDB SDK doesn't support parameters well, use direct string interpolation
        let escaped_query = query.replace('\'', "\\'").to_lowercase();

        // Build group filter clause
        let group_filter = if let Some(groups) = group_ids {
            if !groups.is_empty() {
                let group_list = groups
                    .iter()
                    .map(|g| format!("'{}'", g.replace('\'', "\\'")))
                    .collect::<Vec<_>>()
                    .join(",");
                format!(" AND n.group_id IN [{}]", group_list)
            } else {
                String::new()
            }
        } else {
            String::new()
        };

        let cypher = format!(
            "MATCH (n:Entity) 
             WHERE (toLower(n.name) CONTAINS '{}' 
                OR toLower(n.summary) CONTAINS '{}'){}
             RETURN n 
             LIMIT {}",
            escaped_query, escaped_query, group_filter, limit
        );

        let result = self.graph.query(&cypher).execute().await?;

        parser_v2::parse_nodes_from_falkor_v2(result.data)
    }

    #[instrument(skip(self, embedding))]
    pub async fn similarity_search_nodes(
        &mut self,
        embedding: &[f32],
        limit: usize,
        min_score: f32,
        group_ids: Option<&[String]>,
    ) -> Result<Vec<Node>> {
        // Build the vector string inline since FalkorDB params only support strings
        let embedding_str = embedding
            .iter()
            .map(|v| v.to_string())
            .collect::<Vec<_>>()
            .join(",");

        // Build group filter clause
        let group_filter = if let Some(groups) = group_ids {
            if !groups.is_empty() {
                let group_list = groups
                    .iter()
                    .map(|g| format!("'{}'", g.replace('\'', "\\'")))
                    .collect::<Vec<_>>()
                    .join(",");
                format!(" AND n.group_id IN [{}]", group_list)
            } else {
                String::new()
            }
        } else {
            String::new()
        };

        // Use inline vecf32() function to ensure proper vector type
        let cypher = format!(
            "MATCH (n:Entity) 
             WHERE n.name_embedding IS NOT NULL{}
             WITH n, (2 - vec.cosineDistance(n.name_embedding, vecf32([{}])))/2 AS score
             WHERE score >= {}
             RETURN n, score 
             ORDER BY score DESC 
             LIMIT {}",
            group_filter, embedding_str, min_score, limit
        );

        let result = self.graph.query(&cypher).execute().await?;

        parser_v2::parse_nodes_from_falkor_v2(result.data)
    }

    #[instrument(skip(self))]
    pub async fn bfs_search_nodes(
        &mut self,
        origin_uuids: &[String],
        max_depth: usize,
        limit: usize,
    ) -> Result<Vec<Node>> {
        // Build UUID list
        let uuid_list = origin_uuids
            .iter()
            .map(|u| format!("'{}'", u))
            .collect::<Vec<_>>()
            .join(",");

        let cypher = format!(
            "MATCH (start:Entity) 
             WHERE start.uuid IN [{}]
             CALL algo.BFS(start, {}, 'RELATES_TO') 
             YIELD nodes
             UNWIND nodes AS n
             RETURN DISTINCT n 
             LIMIT {}",
            uuid_list, max_depth, limit
        );

        let result = self.graph.query(&cypher).execute().await?;

        parser_v2::parse_nodes_from_falkor_v2(result.data)
    }

    #[instrument(skip(self))]
    pub async fn fulltext_search_edges(
        &mut self,
        query: &str,
        group_ids: Option<&[String]>,
        limit: usize,
    ) -> Result<Vec<Edge>> {
        // FalkorDB SDK doesn't support parameters well, use direct string interpolation
        let escaped_query = query.replace('\'', "\\'").to_lowercase();

        // Build group filter clause
        let group_filter = if let Some(groups) = group_ids {
            if !groups.is_empty() {
                let group_list = groups
                    .iter()
                    .map(|g| format!("'{}'", g.replace('\'', "\\'")))
                    .collect::<Vec<_>>()
                    .join(",");
                format!(" AND r.group_id IN [{}]", group_list)
            } else {
                String::new()
            }
        } else {
            String::new()
        };

        let cypher = format!(
            "MATCH (a)-[r:RELATES_TO]->(b)
             WHERE (toLower(r.fact) CONTAINS '{}' 
                OR toLower(r.name) CONTAINS '{}'){}
             RETURN a, r, b
             LIMIT {}",
            escaped_query, escaped_query, group_filter, limit
        );

        let result = self.graph.query(&cypher).execute().await?;

        parser_v2::parse_edges_from_falkor_v2(result.data)
    }

    #[instrument(skip(self, embedding))]
    pub async fn similarity_search_edges(
        &mut self,
        embedding: &[f32],
        limit: usize,
        min_score: f32,
        group_ids: Option<&[String]>,
    ) -> Result<Vec<Edge>> {
        // Build the vector string inline
        let embedding_str = embedding
            .iter()
            .map(|v| v.to_string())
            .collect::<Vec<_>>()
            .join(",");

        // Build group filter clause
        let group_filter = if let Some(groups) = group_ids {
            if !groups.is_empty() {
                let group_list = groups
                    .iter()
                    .map(|g| format!("'{}'", g.replace('\'', "\\'")))
                    .collect::<Vec<_>>()
                    .join(",");
                format!(" AND r.group_id IN [{}]", group_list)
            } else {
                String::new()
            }
        } else {
            String::new()
        };

        // WORKAROUND: FalkorDB SDK v0.1.11 has multiple issues with vector operations:
        // 1. Cannot deserialize edges containing vector properties
        // 2. Fails when LIMIT > 1 with vector calculations in WITH clause
        // 3. ORDER BY with SKIP also causes issues
        //
        // Solution: Get all scores in one query (LIMIT 1), then sort in Rust

        let mut edge_scores = Vec::new();

        // First, get all edges with scores above threshold
        // We have to get them one at a time due to the LIMIT > 1 bug
        // But we can't use ORDER BY or SKIP, so we'll collect all and sort later
        for i in 0..100 {
            // Max 100 iterations to prevent infinite loop
            let cypher = if i == 0 {
                // First query - no exclusions
                format!(
                    "MATCH ()-[r:RELATES_TO]->()
                     WHERE r.fact_embedding IS NOT NULL{}
                     WITH r.uuid AS uuid_str, (2 - vec.cosineDistance(r.fact_embedding, vecf32([{}])))/2 AS score
                     WHERE score >= {}
                     RETURN uuid_str, score
                     LIMIT 1",
                    group_filter, embedding_str, min_score
                )
            } else {
                // Subsequent queries - exclude already found UUIDs
                let exclude_list = edge_scores
                    .iter()
                    .map(|(uuid, _): &(String, f32)| format!("'{}'", uuid))
                    .collect::<Vec<_>>()
                    .join(",");

                format!(
                    "MATCH ()-[r:RELATES_TO]->()
                     WHERE r.fact_embedding IS NOT NULL AND r.uuid NOT IN [{}]{}
                     WITH r.uuid AS uuid_str, (2 - vec.cosineDistance(r.fact_embedding, vecf32([{}])))/2 AS score
                     WHERE score >= {}
                     RETURN uuid_str, score
                     LIMIT 1",
                    exclude_list, group_filter, embedding_str, min_score
                )
            };

            match self.graph.query(&cypher).execute().await {
                Ok(result) => {
                    // Extract UUID and score from the single result
                    let mut found = false;
                    for row in result.data {
                        if row.len() >= 2 {
                            if let (Some(falkordb::FalkorValue::String(uuid)), Some(score_val)) =
                                (row.first(), row.get(1))
                            {
                                let score = match score_val {
                                    falkordb::FalkorValue::F64(f) => *f as f32,
                                    falkordb::FalkorValue::I64(i) => *i as f32,
                                    _ => 0.0,
                                };
                                edge_scores.push((uuid.clone(), score));
                                found = true;
                                break;
                            }
                        }
                    }
                    // If no result found, we've exhausted all matches
                    if !found {
                        break;
                    }

                    // If we've collected enough results, stop
                    if edge_scores.len() >= limit {
                        break;
                    }
                }
                Err(_) => {
                    // Query failed, stop trying
                    break;
                }
            }
        }

        // Sort by score descending and take only the requested limit
        edge_scores.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        edge_scores.truncate(limit);

        // Extract just the UUIDs
        let edge_uuids: Vec<String> = edge_scores.into_iter().map(|(uuid, _)| uuid).collect();

        if edge_uuids.is_empty() {
            return Ok(Vec::new());
        }

        // Step 2: Fetch the full edge data without vector operations
        let uuid_list = edge_uuids
            .iter()
            .map(|u| format!("'{}'", u))
            .collect::<Vec<_>>()
            .join(",");

        let fetch_cypher = format!(
            "MATCH (a)-[r:RELATES_TO]->(b)
             WHERE r.uuid IN [{}]
             RETURN a, r, b",
            uuid_list
        );

        let fetch_result = self.graph.query(&fetch_cypher).execute().await?;

        // Parse edges using the standard parser
        parser_v2::parse_edges_from_falkor_v2(fetch_result.data)
    }

    #[instrument(skip(self))]
    pub async fn fulltext_search_episodes(
        &mut self,
        query: &str,
        group_ids: Option<&[String]>,
        limit: usize,
    ) -> Result<Vec<Episode>> {
        // FalkorDB SDK doesn't support parameters well, use direct string interpolation
        let escaped_query = query.replace('\'', "\\'").to_lowercase();

        // Build group filter clause
        let group_filter = if let Some(groups) = group_ids {
            if !groups.is_empty() {
                let group_list = groups
                    .iter()
                    .map(|g| format!("'{}'", g.replace('\'', "\\'")))
                    .collect::<Vec<_>>()
                    .join(",");
                format!(" AND e.group_id IN [{}]", group_list)
            } else {
                String::new()
            }
        } else {
            String::new()
        };

        let cypher = format!(
            "MATCH (e:Episode)
             WHERE (toLower(e.content) CONTAINS '{}' 
                OR toLower(e.name) CONTAINS '{}'){}
             RETURN e
             LIMIT {}",
            escaped_query, escaped_query, group_filter, limit
        );

        let result = self.graph.query(&cypher).execute().await?;

        parser_v2::parse_episodes_from_falkor_v2(result.data)
    }
}
