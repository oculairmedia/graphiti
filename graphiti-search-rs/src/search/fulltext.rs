use crate::error::SearchResult;
use crate::falkor::FalkorConnection;
use crate::models::{Edge, Episode, Node, SearchFilters};
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
    let chars = escaped.chars().peekable();

    for ch in chars {
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
    filters: &SearchFilters,
    limit: usize,
) -> SearchResult<Vec<Node>> {
    let sanitized_query = sanitize_lucene_query(query);
    conn.fulltext_search_nodes(&sanitized_query, filters.group_ids.as_deref(), limit)
        .await
        .map_err(|e| crate::error::SearchError::Database(e.to_string()))
}

#[instrument(skip(conn))]
pub async fn search_edges(
    conn: &mut FalkorConnection,
    query: &str,
    filters: &SearchFilters,
    limit: usize,
) -> SearchResult<Vec<Edge>> {
    let sanitized_query = sanitize_lucene_query(query);
    conn.fulltext_search_edges(&sanitized_query, filters.group_ids.as_deref(), limit)
        .await
        .map_err(|e| crate::error::SearchError::Database(e.to_string()))
}

#[instrument(skip(conn))]
pub async fn search_episodes(
    conn: &mut FalkorConnection,
    query: &str,
    filters: &SearchFilters,
    limit: usize,
) -> SearchResult<Vec<Episode>> {
    let sanitized_query = sanitize_lucene_query(query);
    conn.fulltext_search_episodes(&sanitized_query, filters.group_ids.as_deref(), limit)
        .await
        .map_err(|e| crate::error::SearchError::Database(e.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn leaves_plain_text_queries_unchanged() {
        assert_eq!(sanitize_lucene_query("hello world"), "hello world");
    }

    #[test]
    fn escapes_lucene_special_characters() {
        assert_eq!(
            sanitize_lucene_query(r#"team+(alpha):beta/path\gamma"#),
            r#"team\+\(alpha\)\:beta\/path\\gamma"#
        );
        assert_eq!(sanitize_lucene_query("wild*card?"), r"wild\*card\?");
    }

    #[test]
    fn preserves_quotes_while_escaping_other_special_characters() {
        assert_eq!(
            sanitize_lucene_query("\"exact phrase\" +(beta)"),
            "\"exact phrase\" \\+\\(beta\\)"
        );
    }

    #[test]
    fn handles_empty_queries_without_panicking() {
        assert_eq!(sanitize_lucene_query(""), "");
    }

    #[test]
    fn preserves_unicode_text() {
        assert_eq!(sanitize_lucene_query("cafe 東京"), "cafe 東京");
    }

    #[test]
    fn sanitizes_lucene_injection_attempts() {
        assert_eq!(
            sanitize_lucene_query("title:foo OR body:*"),
            r"title\:foo OR body\:\*"
        );
    }
}
