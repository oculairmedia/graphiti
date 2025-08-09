use anyhow::Result;
use redis::aio::Connection;
use redis::Client;
use tracing::instrument;

use crate::config::Config;
use crate::falkor::parser;
use crate::models::{Edge, Episode, Node};

pub struct FalkorClient {
    _client: Client,
    conn: Connection,
    graph_name: String,
}

impl FalkorClient {
    pub async fn new(config: &Config) -> Result<Self> {
        let url = format!("redis://{}:{}", config.falkor_host, config.falkor_port);
        let client = Client::open(url)?;
        let conn = client.get_async_connection().await?;

        Ok(Self {
            _client: client,
            conn,
            graph_name: config.graph_name.clone(),
        })
    }

    pub async fn ping(&mut self) -> Result<()> {
        redis::cmd("PING")
            .query_async::<_, ()>(&mut self.conn)
            .await?;
        Ok(())
    }

    #[instrument(skip(self))]
    pub async fn fulltext_search_nodes(&mut self, query: &str, limit: usize) -> Result<Vec<Node>> {
        // For now, embed the query directly in the Cypher string
        // FalkorDB parameter binding needs specific format
        let cypher = format!(
            "MATCH (n) 
             WHERE n.name CONTAINS '{}' 
             RETURN n 
             LIMIT {}",
            query.replace("'", "\\'"), // Escape single quotes
            limit
        );

        let results: Vec<Vec<redis::Value>> = redis::cmd("GRAPH.QUERY")
            .arg(&self.graph_name)
            .arg(&cypher)
            .query_async(&mut self.conn)
            .await?;

        // Debug logging
        tracing::debug!("FalkorDB query result length: {}", results.len());
        if results.len() > 1 {
            tracing::debug!("Data rows count: {}", results[1].len());
            if !results[1].is_empty() {
                tracing::debug!("First row type: {:?}", results[1][0]);
            }
        }

        self.parse_nodes(results)
    }

    #[instrument(skip(self))]
    pub async fn similarity_search_nodes(
        &mut self,
        embedding: &[f32],
        limit: usize,
        min_score: f32,
    ) -> Result<Vec<Node>> {
        let embedding_str = embedding
            .iter()
            .map(|v| v.to_string())
            .collect::<Vec<_>>()
            .join(",");

        let cypher = format!(
            "MATCH (n:Entity) 
             WHERE n.embedding IS NOT NULL
             WITH n, vec.cosine_similarity(n.embedding, [{embedding_str}]) AS score
             WHERE score >= {min_score}
             RETURN n, score 
             ORDER BY score DESC 
             LIMIT {limit}"
        );

        let results: Vec<Vec<redis::Value>> = redis::cmd("GRAPH.QUERY")
            .arg(&self.graph_name)
            .arg(&cypher)
            .query_async(&mut self.conn)
            .await?;

        self.parse_nodes(results)
    }

    #[instrument(skip(self))]
    pub async fn bfs_search_nodes(
        &mut self,
        origin_uuids: &[String],
        max_depth: usize,
        limit: usize,
    ) -> Result<Vec<Node>> {
        let uuids_str = origin_uuids
            .iter()
            .map(|uuid| format!("'{uuid}'"))
            .collect::<Vec<_>>()
            .join(",");

        let cypher = format!(
            "MATCH (start:Entity) 
             WHERE start.uuid IN [{uuids_str}]
             CALL algo.BFS(start, {max_depth}, 'RELATES_TO') 
             YIELD nodes
             UNWIND nodes AS n
             RETURN DISTINCT n 
             LIMIT {limit}"
        );

        let results: Vec<Vec<redis::Value>> = redis::cmd("GRAPH.QUERY")
            .arg(&self.graph_name)
            .arg(&cypher)
            .query_async(&mut self.conn)
            .await?;

        self.parse_nodes(results)
    }

    #[instrument(skip(self))]
    pub async fn fulltext_search_edges(&mut self, query: &str, limit: usize) -> Result<Vec<Edge>> {
        // For now, embed the query directly in the Cypher string
        let cypher = format!(
            "MATCH (a)-[r]->(b)
             WHERE r.fact CONTAINS '{}' OR r.name CONTAINS '{}'
             RETURN a, r, b
             LIMIT {}",
            query.replace("'", "\\'"),
            query.replace("'", "\\'"),
            limit
        );

        let results: Vec<Vec<redis::Value>> = redis::cmd("GRAPH.QUERY")
            .arg(&self.graph_name)
            .arg(&cypher)
            .query_async(&mut self.conn)
            .await?;

        self.parse_edges(results)
    }

    #[instrument(skip(self))]
    pub async fn fulltext_search_episodes(
        &mut self,
        query: &str,
        limit: usize,
    ) -> Result<Vec<Episode>> {
        // For now, embed the query directly in the Cypher string
        let cypher = format!(
            "MATCH (e)
             WHERE e.content CONTAINS '{}' OR e.name CONTAINS '{}'
             RETURN e
             LIMIT {}",
            query.replace("'", "\\'"),
            query.replace("'", "\\'"),
            limit
        );

        let results: Vec<Vec<redis::Value>> = redis::cmd("GRAPH.QUERY")
            .arg(&self.graph_name)
            .arg(&cypher)
            .query_async(&mut self.conn)
            .await?;

        self.parse_episodes(results)
    }

    fn parse_nodes(&self, results: Vec<Vec<redis::Value>>) -> Result<Vec<Node>> {
        parser::parse_nodes_from_falkor(results)
    }

    fn parse_edges(&self, results: Vec<Vec<redis::Value>>) -> Result<Vec<Edge>> {
        parser::parse_edges_from_falkor(results)
    }

    fn parse_episodes(&self, results: Vec<Vec<redis::Value>>) -> Result<Vec<Episode>> {
        parser::parse_episodes_from_falkor(results)
    }
}
