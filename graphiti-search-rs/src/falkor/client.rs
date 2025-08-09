use anyhow::Result;
use redis::aio::Connection;
use redis::{AsyncCommands, Client};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use tracing::{debug, instrument};

use crate::config::Config;
use crate::models::{Edge, Episode, Node};

pub struct FalkorClient {
    client: Client,
    conn: Connection,
    graph_name: String,
}

impl FalkorClient {
    pub async fn new(config: &Config) -> Result<Self> {
        let url = format!("redis://{}:{}", config.falkor_host, config.falkor_port);
        let client = Client::open(url)?;
        let conn = client.get_async_connection().await?;

        Ok(Self {
            client,
            conn,
            graph_name: config.graph_name.clone(),
        })
    }

    pub async fn ping(&mut self) -> Result<()> {
        redis::cmd("PING").query_async(&mut self.conn).await?;
        Ok(())
    }

    #[instrument(skip(self))]
    pub async fn fulltext_search_nodes(&mut self, query: &str, limit: usize) -> Result<Vec<Node>> {
        let cypher = format!(
            "CALL db.idx.fulltext.queryNodes('node_name_index', $query) 
             YIELD node, score 
             RETURN node, score 
             ORDER BY score DESC 
             LIMIT {}",
            limit
        );

        let results: Vec<Vec<redis::Value>> = redis::cmd("GRAPH.QUERY")
            .arg(&self.graph_name)
            .arg(&cypher)
            .arg("query")
            .arg(query)
            .query_async(&mut self.conn)
            .await?;

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
             WITH n, vec.cosine_similarity(n.embedding, [{}]) AS score
             WHERE score >= {}
             RETURN n, score 
             ORDER BY score DESC 
             LIMIT {}",
            embedding_str, min_score, limit
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
            .map(|uuid| format!("'{}'", uuid))
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
            uuids_str, max_depth, limit
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
        let cypher = format!(
            "MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
             WHERE r.fact CONTAINS $query
             RETURN a.uuid, r, b.uuid, r.fact
             ORDER BY r.created_at DESC
             LIMIT {}",
            limit
        );

        let results: Vec<Vec<redis::Value>> = redis::cmd("GRAPH.QUERY")
            .arg(&self.graph_name)
            .arg(&cypher)
            .arg("query")
            .arg(query)
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
        let cypher = format!(
            "MATCH (e:Episode)
             WHERE e.content CONTAINS $query
             RETURN e
             ORDER BY e.created_at DESC
             LIMIT {}",
            limit
        );

        let results: Vec<Vec<redis::Value>> = redis::cmd("GRAPH.QUERY")
            .arg(&self.graph_name)
            .arg(&cypher)
            .arg("query")
            .arg(query)
            .query_async(&mut self.conn)
            .await?;

        self.parse_episodes(results)
    }

    fn parse_nodes(&self, results: Vec<Vec<redis::Value>>) -> Result<Vec<Node>> {
        // TODO: Implement proper parsing of FalkorDB results
        // This is a simplified version
        Ok(vec![])
    }

    fn parse_edges(&self, results: Vec<Vec<redis::Value>>) -> Result<Vec<Edge>> {
        // TODO: Implement proper parsing of FalkorDB results
        Ok(vec![])
    }

    fn parse_episodes(&self, results: Vec<Vec<redis::Value>>) -> Result<Vec<Episode>> {
        // TODO: Implement proper parsing of FalkorDB results
        Ok(vec![])
    }
}
