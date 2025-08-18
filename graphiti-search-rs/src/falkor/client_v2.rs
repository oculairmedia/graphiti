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
    pub async fn fulltext_search_nodes(&mut self, query: &str, limit: usize) -> Result<Vec<Node>> {
        // FalkorDB SDK doesn't support parameters well, use direct string interpolation
        let escaped_query = query.replace('\'', "\\'").to_lowercase();
        let cypher = format!(
            "MATCH (n:Entity) 
             WHERE toLower(n.name) CONTAINS '{}' 
                OR toLower(n.summary) CONTAINS '{}'
             RETURN n 
             LIMIT {}",
            escaped_query, escaped_query, limit
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
        // FalkorDB SDK doesn't support parameters well, use direct string interpolation
        let escaped_query = query.replace('\'', "\\'").to_lowercase();
        let cypher = format!(
            "MATCH (a)-[r:RELATES_TO]->(b)
             WHERE toLower(r.fact) CONTAINS '{}' 
                OR toLower(r.name) CONTAINS '{}'
             RETURN a, r, b
             LIMIT {}",
            escaped_query, escaped_query, limit
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
    ) -> Result<Vec<Edge>> {
        // Build the vector string inline
        let embedding_str = embedding
            .iter()
            .map(|v| v.to_string())
            .collect::<Vec<_>>()
            .join(",");

        // WORKAROUND: FalkorDB SDK fails when vector operations return complex types
        // We need to avoid any query that returns edges with vector properties
        // Instead, we'll use a two-step approach:
        // 1. Calculate similarities and get UUIDs (avoiding edge object deserialization)
        // 2. Fetch full edge data separately
        
        // First, get edge UUIDs sorted by similarity score
        // We avoid returning the edge object itself to prevent SDK deserialization issues
        let cypher = format!(
            "MATCH ()-[r:RELATES_TO]->()
             WHERE r.fact_embedding IS NOT NULL AND r.uuid IS NOT NULL
             WITH r.uuid AS uuid_str, (2 - vec.cosineDistance(r.fact_embedding, vecf32([{}])))/2 AS score
             WHERE score >= {}
             RETURN uuid_str
             ORDER BY score DESC
             LIMIT {}",
            embedding_str, min_score, limit
        );

        let result = self.graph.query(&cypher).execute().await?;
        
        // Extract UUIDs from the result
        let mut edge_uuids = Vec::new();
        for row in result.data {
            if let Some(falkordb::FalkorValue::String(uuid)) = row.get(0) {
                edge_uuids.push(uuid.clone());
            }
        }
        
        if edge_uuids.is_empty() {
            return Ok(Vec::new());
        }
        
        // Step 2: Fetch the full edge data (including nodes) without vector operations
        // We explicitly exclude fact_embedding from the result to avoid deserialization issues
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
        limit: usize,
    ) -> Result<Vec<Episode>> {
        // FalkorDB SDK doesn't support parameters well, use direct string interpolation
        let escaped_query = query.replace('\'', "\\'").to_lowercase();
        let cypher = format!(
            "MATCH (e:Episode)
             WHERE toLower(e.content) CONTAINS '{}' 
                OR toLower(e.name) CONTAINS '{}'
             RETURN e
             LIMIT {}",
            escaped_query, escaped_query, limit
        );

        let result = self.graph.query(&cypher).execute().await?;

        parser_v2::parse_episodes_from_falkor_v2(result.data)
    }
}
