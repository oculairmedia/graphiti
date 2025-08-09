/// Cypher query templates for FalkorDB operations
pub mod templates {
    pub const FULLTEXT_SEARCH_NODES: &str = r#"
        CALL db.idx.fulltext.queryNodes('node_name_index', $query) 
        YIELD node, score 
        WHERE node.group_id IN $group_ids OR $group_ids IS NULL
        RETURN node, score 
        ORDER BY score DESC 
        LIMIT $limit
    "#;

    pub const SIMILARITY_SEARCH_NODES: &str = r#"
        MATCH (n:Entity) 
        WHERE n.embedding IS NOT NULL
        AND (n.group_id IN $group_ids OR $group_ids IS NULL)
        WITH n, vec.cosine_similarity(n.embedding, $query_vector) AS score
        WHERE score >= $min_score
        RETURN n, score 
        ORDER BY score DESC 
        LIMIT $limit
    "#;

    pub const BFS_SEARCH_NODES: &str = r#"
        MATCH (start:Entity) 
        WHERE start.uuid IN $origin_uuids
        CALL algo.BFS(start, $max_depth, 'RELATES_TO') 
        YIELD nodes
        UNWIND nodes AS n
        WHERE n.group_id IN $group_ids OR $group_ids IS NULL
        RETURN DISTINCT n 
        LIMIT $limit
    "#;

    pub const FULLTEXT_SEARCH_EDGES: &str = r#"
        MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
        WHERE r.fact CONTAINS $query
        AND (r.group_id IN $group_ids OR $group_ids IS NULL)
        RETURN a, r, b
        ORDER BY r.created_at DESC
        LIMIT $limit
    "#;

    pub const FULLTEXT_SEARCH_EPISODES: &str = r#"
        MATCH (e:Episode)
        WHERE e.content CONTAINS $query
        AND (e.group_id IN $group_ids OR $group_ids IS NULL)
        RETURN e
        ORDER BY e.created_at DESC
        LIMIT $limit
    "#;

    pub const GET_NODE_NEIGHBORS: &str = r#"
        MATCH (n:Entity {uuid: $node_uuid})-[r:RELATES_TO]-(neighbor:Entity)
        RETURN neighbor, r
        ORDER BY r.weight DESC
        LIMIT $limit
    "#;

    pub const GET_EDGES_BY_EPISODES: &str = r#"
        MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
        WHERE ANY(episode_id IN r.episodes WHERE episode_id IN $episode_ids)
        RETURN a, r, b
        ORDER BY SIZE(r.episodes) DESC
        LIMIT $limit
    "#;

    pub const GET_COMMUNITY_MEMBERS: &str = r#"
        MATCH (c:Community {uuid: $community_uuid})-[:HAS_MEMBER]->(n:Entity)
        RETURN n
        ORDER BY n.centrality DESC
        LIMIT $limit
    "#;

    pub const SIMILARITY_SEARCH_COMMUNITIES: &str = r#"
        MATCH (c:Community)
        WHERE c.embedding IS NOT NULL
        WITH c, vec.cosine_similarity(c.embedding, $query_vector) AS score
        WHERE score >= $min_score
        RETURN c, score
        ORDER BY score DESC
        LIMIT $limit
    "#;
}
