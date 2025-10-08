#!/bin/bash
echo "Verifying centrality data in FalkorDB..."

# Query a sample node to check if centrality properties exist
redis-cli -h localhost -p 6389 GRAPH.QUERY graphiti_migration "MATCH (n) WHERE n.pagerank_centrality IS NOT NULL RETURN n.uuid, n.pagerank_centrality, n.degree_centrality, n.betweenness_centrality, n.eigenvector_centrality LIMIT 5" | jq -r '.[][]' 2>/dev/null | head -20

echo -e "\nCounting nodes with centrality scores..."
redis-cli -h localhost -p 6389 GRAPH.QUERY graphiti_migration "MATCH (n) WHERE n.pagerank_centrality IS NOT NULL RETURN count(n) as count" 2>/dev/null | jq -r '.[1][][0]' 2>/dev/null