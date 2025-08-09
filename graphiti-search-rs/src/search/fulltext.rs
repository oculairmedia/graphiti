use crate::error::SearchResult;
use crate::falkor::FalkorConnection;
use crate::models::{Edge, Episode, Node};
use regex::Regex;
use tracing::instrument;

lazy_static::lazy_static! {
    // Don't escape double quotes - we need them for exact phrase matching
    static ref SPECIAL_CHARS: Regex = Regex::new(r#"[\\+\-!(){}\[\]^~*?:/]"#).unwrap();
}

fn sanitize_lucene_query(query: &str) -> String {
    // Escape special Lucene characters
    let escaped = SPECIAL_CHARS.replace_all(query, r"\$0");

    // Handle AND/OR/NOT operators
    let mut result = String::new();
    let mut in_quotes = false;
    let mut chars = escaped.chars().peekable();

    while let Some(ch) = chars.next() {
        if ch == '"' {
            in_quotes = !in_quotes;
        }
        result.push(ch);
    }

    // Don't add wildcard - FalkorDB CONTAINS already does partial matching
    // if !in_quotes && !result.contains('*') && !result.contains('?') {
    //     result.push('*');
    // }

    result
}

#[instrument(skip(conn))]
pub async fn search_nodes(
    conn: &mut FalkorConnection,
    query: &str,
    limit: usize,
) -> SearchResult<Vec<Node>> {
    let sanitized_query = sanitize_lucene_query(query);
    conn.fulltext_search_nodes(&sanitized_query, limit)
        .await
        .map_err(|e| crate::error::SearchError::Database(e.to_string()))
}

#[instrument(skip(conn))]
pub async fn search_edges(
    conn: &mut FalkorConnection,
    query: &str,
    limit: usize,
) -> SearchResult<Vec<Edge>> {
    let sanitized_query = sanitize_lucene_query(query);
    conn.fulltext_search_edges(&sanitized_query, limit)
        .await
        .map_err(|e| crate::error::SearchError::Database(e.to_string()))
}

#[instrument(skip(conn))]
pub async fn search_episodes(
    conn: &mut FalkorConnection,
    query: &str,
    limit: usize,
) -> SearchResult<Vec<Episode>> {
    let sanitized_query = sanitize_lucene_query(query);
    conn.fulltext_search_episodes(&sanitized_query, limit)
        .await
        .map_err(|e| crate::error::SearchError::Database(e.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sanitize_lucene_query() {
        // We no longer add wildcards automatically since FalkorDB CONTAINS does partial matching
        assert_eq!(sanitize_lucene_query("hello world"), "hello world");
        assert_eq!(sanitize_lucene_query("test+query"), r"test\+query");
        assert_eq!(
            sanitize_lucene_query("\"exact phrase\""),
            "\"exact phrase\""
        );
        // Wildcards are escaped since they're special Lucene characters
        assert_eq!(sanitize_lucene_query("wild*card"), r"wild\*card");
    }
}
