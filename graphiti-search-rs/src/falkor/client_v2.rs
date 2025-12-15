#![allow(dead_code)]

use anyhow::Result;
use chrono::{DateTime, Utc};
use falkordb::{
    AsyncGraph, FalkorAsyncClient, FalkorClientBuilder, FalkorConnectionInfo, FalkorValue,
    LazyResultSet,
};
use tracing::instrument;
use uuid::Uuid;

use crate::config::Config;
use crate::falkor::parser_v2;
use crate::models::{Edge, Episode, Node};

/// Parse edges from property columns (optimized to avoid embedding data transfer)
/// Expected columns: source_uuid, source_name, edge_uuid, edge_fact, edge_created_at, edge_group_id, edge_weight, target_uuid, target_name
fn parse_edges_from_properties(result: LazyResultSet<'_>) -> Result<Vec<Edge>> {
    let mut edges = Vec::new();

    for row in result {
        if row.len() < 9 {
            continue;
        }

        // Extract source UUID
        let source_uuid = match &row[0] {
            FalkorValue::String(s) => match Uuid::parse_str(s) {
                Ok(u) => u,
                Err(_) => continue,
            },
            _ => continue,
        };

        // Extract edge UUID
        let edge_uuid = match &row[2] {
            FalkorValue::String(s) => match Uuid::parse_str(s) {
                Ok(u) => u,
                Err(_) => continue,
            },
            _ => continue,
        };

        // Extract edge fact
        let fact = match &row[3] {
            FalkorValue::String(s) => s.clone(),
            _ => String::new(),
        };

        // Extract created_at
        let created_at = match &row[4] {
            FalkorValue::F64(f) => DateTime::from_timestamp(*f as i64, 0).unwrap_or(Utc::now()),
            FalkorValue::I64(i) => DateTime::from_timestamp(*i, 0).unwrap_or(Utc::now()),
            FalkorValue::String(s) => s.parse().unwrap_or(Utc::now()),
            _ => Utc::now(),
        };

        // Extract group_id
        let group_id = match &row[5] {
            FalkorValue::String(s) => s.clone(),
            _ => String::new(),
        };

        // Extract weight
        let weight = match &row[6] {
            FalkorValue::F64(f) => *f,
            FalkorValue::I64(i) => *i as f64,
            _ => 1.0,
        };

        // Extract target UUID
        let target_uuid = match &row[7] {
            FalkorValue::String(s) => match Uuid::parse_str(s) {
                Ok(u) => u,
                Err(_) => continue,
            },
            _ => continue,
        };

        edges.push(Edge {
            uuid: edge_uuid,
            source_node_uuid: source_uuid,
            target_node_uuid: target_uuid,
            fact,
            created_at,
            episodes: vec![], // We don't fetch episodes in this optimized path
            group_id: if group_id.is_empty() {
                None
            } else {
                Some(group_id)
            },
            weight: weight as f32,
        });
    }

    Ok(edges)
}

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
        // Escape special characters for fulltext query
        let escaped_query = query
            .replace('\\', "\\\\")
            .replace('\'', "\\'")
            .replace('"', "\\\"");

        // Use FalkorDB's fulltext index procedure for fast search
        // This uses the index created on Entity(name) and Entity(summary)
        // The fulltext index returns nodes ordered by relevance
        let cypher = format!(
            "CALL db.idx.fulltext.queryNodes('Entity', '{}') YIELD node
             WITH node
             LIMIT {}
             RETURN node",
            escaped_query, limit
        );

        tracing::debug!("Fulltext node query: {}", cypher);

        match self.graph.query(&cypher).execute().await {
            Ok(result) => {
                let mut nodes = parser_v2::parse_nodes_from_falkor_v2(result.data)?;

                // Apply group filter if specified (post-filtering since fulltext index doesn't support it)
                if let Some(groups) = group_ids {
                    if !groups.is_empty() {
                        nodes.retain(|n| n.group_id.as_ref().is_some_and(|g| groups.contains(g)));
                    }
                }

                Ok(nodes)
            }
            Err(e) => {
                // Fallback to CONTAINS-based search if fulltext index fails
                tracing::warn!(
                    "Fulltext index query failed, falling back to CONTAINS: {:?}",
                    e
                );
                self.fulltext_search_nodes_fallback(query, group_ids, limit)
                    .await
            }
        }
    }

    /// Fallback fulltext search using CONTAINS (slower but works without index)
    async fn fulltext_search_nodes_fallback(
        &mut self,
        query: &str,
        group_ids: Option<&[String]>,
        limit: usize,
    ) -> Result<Vec<Node>> {
        let escaped_query = query.replace('\'', "\\'").to_lowercase();

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
        // Build the vector string inline for HNSW vector index query
        let embedding_str = embedding
            .iter()
            .map(|v| v.to_string())
            .collect::<Vec<_>>()
            .join(",");

        // Use FalkorDB's HNSW vector index procedure for fast ANN search
        // This uses the index created with:
        // CREATE VECTOR INDEX FOR (n:Entity) ON (n.name_embedding) OPTIONS {dimension: 2560, similarityFunction: 'cosine'}
        let vector_query_cypher = format!(
            "CALL db.idx.vector.queryNodes('Entity', 'name_embedding', {}, vecf32([{}])) 
             YIELD node, score
             WHERE score >= {}
             RETURN node.uuid AS uuid_str",
            limit, embedding_str, min_score
        );

        tracing::debug!("Using HNSW vector index for node similarity search");

        let mut node_uuids: Vec<String> = Vec::new();

        match self.graph.query(&vector_query_cypher).execute().await {
            Ok(result) => {
                for row in result.data {
                    if let Some(falkordb::FalkorValue::String(uuid)) = row.first() {
                        node_uuids.push(uuid.clone());
                    }
                }
            }
            Err(e) => {
                tracing::warn!(
                    "HNSW vector index query failed for nodes, falling back to brute-force: {:?}",
                    e
                );
                // Fallback to brute-force if vector index not available
                return self
                    .similarity_search_nodes_brute_force(embedding, limit, min_score, group_ids)
                    .await;
            }
        }

        if node_uuids.is_empty() {
            return Ok(Vec::new());
        }

        // Fetch full node data with optional group filter
        let uuid_list = node_uuids
            .iter()
            .map(|u| format!("'{}'", u))
            .collect::<Vec<_>>()
            .join(",");

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

        let fetch_cypher = format!(
            "MATCH (n:Entity) 
             WHERE n.uuid IN [{}]{}
             RETURN n",
            uuid_list, group_filter
        );

        let result = self.graph.query(&fetch_cypher).execute().await?;
        parser_v2::parse_nodes_from_falkor_v2(result.data)
    }

    /// Fallback brute-force node similarity search
    #[instrument(skip(self, embedding))]
    async fn similarity_search_nodes_brute_force(
        &mut self,
        embedding: &[f32],
        limit: usize,
        min_score: f32,
        group_ids: Option<&[String]>,
    ) -> Result<Vec<Node>> {
        let embedding_str = embedding
            .iter()
            .map(|v| v.to_string())
            .collect::<Vec<_>>()
            .join(",");

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
        // Escape special characters for fulltext query
        let escaped_query = query
            .replace('\\', "\\\\")
            .replace('\'', "\\'")
            .replace('"', "\\\"");

        // Use FalkorDB's fulltext index procedure for fast search
        // This uses the index created on RELATES_TO(fact)
        // Returns relationships ordered by relevance
        let cypher = format!(
            "CALL db.idx.fulltext.queryRelationships('RELATES_TO', '{}') YIELD relationship
             WITH relationship
             LIMIT {}
             RETURN relationship.uuid AS uuid_str",
            escaped_query, limit
        );

        tracing::debug!("Fulltext edge query (phase 1): {}", cypher);

        let edge_uuids: Vec<String> = match self.graph.query(&cypher).execute().await {
            Ok(result) => {
                let mut uuids = Vec::new();
                for row in result.data {
                    if let Some(falkordb::FalkorValue::String(uuid)) = row.first() {
                        uuids.push(uuid.clone());
                    }
                }
                uuids
            }
            Err(e) => {
                // Fallback to CONTAINS-based search if fulltext index fails
                tracing::warn!(
                    "Fulltext index query failed, falling back to CONTAINS: {:?}",
                    e
                );
                return self
                    .fulltext_search_edges_fallback(query, group_ids, limit)
                    .await;
            }
        };

        if edge_uuids.is_empty() {
            // FalkorDB doesn't support fulltext indexes on relationships,
            // so fall back to CONTAINS-based search
            tracing::debug!("Fulltext index returned no results, falling back to CONTAINS search");
            return self
                .fulltext_search_edges_fallback(query, group_ids, limit)
                .await;
        }

        // Fetch edge data WITHOUT embeddings for performance
        let uuid_list = edge_uuids
            .iter()
            .map(|u| format!("'{}'", u))
            .collect::<Vec<_>>()
            .join(",");

        // Build group filter for the fetch query
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

        // Return only the properties we need - avoids transferring ~10KB of embedding data per edge
        let fetch_cypher = format!(
            "MATCH (a)-[r:RELATES_TO]->(b)
             WHERE r.uuid IN [{}]{}
             RETURN a.uuid AS source_uuid, 
                    a.name AS source_name,
                    r.uuid AS edge_uuid, 
                    r.fact AS edge_fact, 
                    r.created_at AS edge_created_at, 
                    r.group_id AS edge_group_id, 
                    COALESCE(r.weight, 1.0) AS edge_weight,
                    b.uuid AS target_uuid,
                    b.name AS target_name",
            uuid_list, group_filter
        );

        tracing::debug!(
            "Fulltext edge query (phase 2 - fetch): fetching {} edges",
            edge_uuids.len()
        );

        let fetch_result = self.graph.query(&fetch_cypher).execute().await?;
        parse_edges_from_properties(fetch_result.data)
    }

    /// Fallback fulltext search using CONTAINS (slower but works without index)
    async fn fulltext_search_edges_fallback(
        &mut self,
        query: &str,
        group_ids: Option<&[String]>,
        limit: usize,
    ) -> Result<Vec<Edge>> {
        let escaped_query = query.replace('\'', "\\'").to_lowercase();

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
        // Build the vector string inline for HNSW vector index query
        let embedding_str = embedding
            .iter()
            .map(|v| v.to_string())
            .collect::<Vec<_>>()
            .join(",");

        // Use FalkorDB's HNSW vector index procedure for fast ANN search
        // This uses the index created with:
        // CREATE VECTOR INDEX FOR ()-[r:RELATES_TO]->() ON (r.fact_embedding) OPTIONS {dimension: 2560, similarityFunction: 'cosine'}
        //
        // The index returns results ordered by similarity (closest first)
        // Score is cosine similarity (0-1 range)
        let vector_query_cypher = format!(
            "CALL db.idx.vector.queryRelationships('RELATES_TO', 'fact_embedding', {}, vecf32([{}])) 
             YIELD relationship, score
             WHERE score >= {}
             RETURN relationship.uuid AS uuid_str, score",
            limit, embedding_str, min_score
        );

        let start = std::time::Instant::now();
        let mut edge_uuids: Vec<String> = Vec::new();

        match self.graph.query(&vector_query_cypher).execute().await {
            Ok(result) => {
                let query_time = start.elapsed();
                tracing::debug!(
                    "HNSW query completed in {:?}, got {} rows",
                    query_time,
                    result.data.len()
                );

                // Extract UUIDs from the vector index results
                for row in result.data {
                    if row.len() >= 2 {
                        if let Some(falkordb::FalkorValue::String(uuid)) = row.first() {
                            edge_uuids.push(uuid.clone());
                        }
                    }
                }
            }
            Err(e) => {
                tracing::warn!(
                    "HNSW vector index query failed, falling back to brute-force: {:?}",
                    e
                );
                // Fallback to brute-force if vector index not available
                return self
                    .similarity_search_edges_brute_force(embedding, limit, min_score, group_ids)
                    .await;
            }
        }

        // Apply group filter if specified (post-filtering since vector index doesn't support filters)
        if let Some(groups) = group_ids {
            if !groups.is_empty() && !edge_uuids.is_empty() {
                // Fetch edges with group filter applied, using optimized property return
                let uuid_list = edge_uuids
                    .iter()
                    .map(|u| format!("'{}'", u))
                    .collect::<Vec<_>>()
                    .join(",");

                let group_list = groups
                    .iter()
                    .map(|g| format!("'{}'", g.replace('\'', "\\'")))
                    .collect::<Vec<_>>()
                    .join(",");

                // Return only needed properties (no embeddings) with group filter
                let fetch_cypher = format!(
                    "MATCH (a)-[r:RELATES_TO]->(b)
                     WHERE r.uuid IN [{}] AND r.group_id IN [{}]
                     RETURN a.uuid AS source_uuid, 
                            a.name AS source_name,
                            r.uuid AS edge_uuid, 
                            r.fact AS edge_fact, 
                            r.created_at AS edge_created_at, 
                            r.group_id AS edge_group_id, 
                            COALESCE(r.weight, 1.0) AS edge_weight,
                            b.uuid AS target_uuid,
                            b.name AS target_name",
                    uuid_list, group_list
                );

                let fetch_result = self.graph.query(&fetch_cypher).execute().await?;
                return parse_edges_from_properties(fetch_result.data);
            }
        }

        if edge_uuids.is_empty() {
            return Ok(Vec::new());
        }

        // Fetch edge data WITHOUT embeddings for 100x faster performance
        // Returning full edge objects (a, r, b) includes fact_embedding which is 2560 floats per edge
        let fetch_start = std::time::Instant::now();

        let uuid_list = edge_uuids
            .iter()
            .map(|u| format!("'{}'", u))
            .collect::<Vec<_>>()
            .join(",");

        // Return only the properties we need - avoids transferring ~10KB of embedding data per edge
        let fetch_cypher = format!(
            "MATCH (a)-[r:RELATES_TO]->(b)
             WHERE r.uuid IN [{}]
             RETURN a.uuid AS source_uuid, 
                    a.name AS source_name,
                    r.uuid AS edge_uuid, 
                    r.fact AS edge_fact, 
                    r.created_at AS edge_created_at, 
                    r.group_id AS edge_group_id, 
                    COALESCE(r.weight, 1.0) AS edge_weight,
                    b.uuid AS target_uuid,
                    b.name AS target_name",
            uuid_list
        );

        let fetch_result = self.graph.query(&fetch_cypher).execute().await?;
        tracing::debug!(
            "Fetch query completed in {:?}, got {} results",
            fetch_start.elapsed(),
            fetch_result.data.len()
        );

        // Parse edges using the optimized property-based parser
        parse_edges_from_properties(fetch_result.data)
    }

    /// Fallback brute-force similarity search (used when vector index is not available)
    /// This version uses a single efficient batch query instead of multiple individual queries
    #[instrument(skip(self, embedding))]
    async fn similarity_search_edges_brute_force(
        &mut self,
        embedding: &[f32],
        limit: usize,
        min_score: f32,
        group_ids: Option<&[String]>,
    ) -> Result<Vec<Edge>> {
        tracing::info!(
            "Using brute-force similarity search for edges (limit: {}, min_score: {})",
            limit,
            min_score
        );
        let start = std::time::Instant::now();

        let embedding_str = embedding
            .iter()
            .map(|v| v.to_string())
            .collect::<Vec<_>>()
            .join(",");

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

        // Use a single efficient batch query with ORDER BY and LIMIT
        // This is MUCH faster than the previous 100-iteration approach
        let cypher = format!(
            "MATCH ()-[r:RELATES_TO]->()
             WHERE r.fact_embedding IS NOT NULL{}
             WITH r.uuid AS uuid_str, (2 - vec.cosineDistance(r.fact_embedding, vecf32([{}])))/2 AS score
             WHERE score >= {}
             RETURN uuid_str, score
             ORDER BY score DESC
             LIMIT {}",
            group_filter, embedding_str, min_score, limit
        );

        let mut edge_uuids: Vec<String> = Vec::new();

        match self.graph.query(&cypher).execute().await {
            Ok(result) => {
                let query_time = start.elapsed();
                tracing::info!(
                    "Brute-force query completed in {:?}, got {} rows",
                    query_time,
                    result.data.len()
                );

                for row in result.data {
                    if row.len() >= 2 {
                        if let Some(falkordb::FalkorValue::String(uuid)) = row.first() {
                            edge_uuids.push(uuid.clone());
                        }
                    }
                }
            }
            Err(e) => {
                tracing::warn!("Brute-force similarity query failed: {:?}", e);
                return Ok(Vec::new());
            }
        }

        if edge_uuids.is_empty() {
            return Ok(Vec::new());
        }

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
