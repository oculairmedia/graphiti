use anyhow::Result;
use falkordb::{AsyncGraph, FalkorAsyncClient, FalkorClientBuilder, FalkorConnectionInfo};
use std::collections::HashMap;
use tracing::instrument;

use crate::config::Config;
use crate::falkor::parser_v2;
use crate::models::{Edge, Episode, Node};

pub struct FalkorClientV2 {
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
    pub async fn fulltext_search_nodes(&mut self, query: &str, limit: usize) -> Result<Vec<Node>> {
        let query_lower = query.to_lowercase();

        let mut params = HashMap::new();
        params.insert(
            "query".to_string(),
            format!("'{}'", query_lower.replace('\'', "\\'")),
        );
        params.insert("limit".to_string(), limit.to_string());

        let cypher = "MATCH (n:Entity) 
                     WHERE toLower(n.name) CONTAINS $query 
                        OR toLower(n.summary) CONTAINS $query
                     RETURN n 
                     LIMIT $limit";

        let result = self
            .graph
            .query(cypher)
            .with_params(&params)
            .execute()
            .await?;

        parser_v2::parse_nodes_from_falkor_v2(result.data)
    }

    #[instrument(skip(self, embedding))]
    pub async fn similarity_search_nodes(
        &mut self,
        embedding: &[f32],
        limit: usize,
        min_score: f32,
    ) -> Result<Vec<Node>> {
        // Build the vector string inline since FalkorDB params only support strings
        let embedding_str = embedding
            .iter()
            .map(|v| v.to_string())
            .collect::<Vec<_>>()
            .join(",");

        // Use inline vecf32() function to ensure proper vector type
        let cypher = format!(
            "MATCH (n:Entity) 
             WHERE n.name_embedding IS NOT NULL
             WITH n, (2 - vec.cosineDistance(n.name_embedding, vecf32([{}])))/2 AS score
             WHERE score >= {}
             RETURN n, score 
             ORDER BY score DESC 
             LIMIT {}",
            embedding_str, min_score, limit
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
    pub async fn fulltext_search_edges(&mut self, query: &str, limit: usize) -> Result<Vec<Edge>> {
        let query_lower = query.to_lowercase();

        let mut params = HashMap::new();
        params.insert(
            "query".to_string(),
            format!("'{}'", query_lower.replace('\'', "\\'")),
        );
        params.insert("limit".to_string(), limit.to_string());

        let cypher = "MATCH (a)-[r:RELATES_TO]->(b)
                     WHERE toLower(r.fact) CONTAINS $query 
                        OR toLower(r.name) CONTAINS $query
                     RETURN a, r, b
                     LIMIT $limit";

        let result = self
            .graph
            .query(cypher)
            .with_params(&params)
            .execute()
            .await?;

        parser_v2::parse_edges_from_falkor_v2(result.data)
    }

    #[instrument(skip(self, embedding))]
    pub async fn similarity_search_edges(
        &mut self,
        embedding: &[f32],
        limit: usize,
        min_score: f32,
    ) -> Result<Vec<Edge>> {
        // Build the vector string inline
        let embedding_str = embedding
            .iter()
            .map(|v| v.to_string())
            .collect::<Vec<_>>()
            .join(",");

        // Use inline vecf32() function to ensure proper vector type
        let cypher = format!(
            "MATCH (a)-[r:RELATES_TO]->(b)
             WHERE r.fact_embedding IS NOT NULL
             WITH a, r, b, (2 - vec.cosineDistance(r.fact_embedding, vecf32([{}])))/2 AS score
             WHERE score >= {}
             RETURN a, r, b, score 
             ORDER BY score DESC 
             LIMIT {}",
            embedding_str, min_score, limit
        );

        let result = self.graph.query(&cypher).execute().await?;

        parser_v2::parse_edges_from_falkor_v2(result.data)
    }

    #[instrument(skip(self))]
    pub async fn fulltext_search_episodes(
        &mut self,
        query: &str,
        limit: usize,
    ) -> Result<Vec<Episode>> {
        let query_lower = query.to_lowercase();

        let mut params = HashMap::new();
        params.insert(
            "query".to_string(),
            format!("'{}'", query_lower.replace('\'', "\\'")),
        );
        params.insert("limit".to_string(), limit.to_string());

        let cypher = "MATCH (e:Episode)
                     WHERE toLower(e.content) CONTAINS $query 
                        OR toLower(e.name) CONTAINS $query
                     RETURN e
                     LIMIT $limit";

        let result = self
            .graph
            .query(cypher)
            .with_params(&params)
            .execute()
            .await?;

        parser_v2::parse_episodes_from_falkor_v2(result.data)
    }
}
