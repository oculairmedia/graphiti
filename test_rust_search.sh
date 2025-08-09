#!/bin/bash

echo "Testing Rust Search Service with parsing"
echo "========================================="

echo -e "\n1. Testing node search with fulltext:"
curl -X POST http://localhost:3004/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Node", 
    "config": {
      "node_config": {
        "search_methods": ["fulltext"],
        "reranker": "rrf",
        "bfs_max_depth": 2,
        "sim_min_score": 0.5,
        "mmr_lambda": 0.5
      },
      "limit": 5, 
      "reranker_min_score": 0.0
    }, 
    "filters": {}
  }' \
  2>/dev/null | jq

echo -e "\n2. Testing edge search with fulltext:"
curl -X POST http://localhost:3004/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "test", 
    "config": {
      "edge_config": {
        "search_methods": ["fulltext"],
        "reranker": "rrf",
        "bfs_max_depth": 2,
        "sim_min_score": 0.5,
        "mmr_lambda": 0.5
      },
      "limit": 3, 
      "reranker_min_score": 0.0
    }, 
    "filters": {}
  }' \
  2>/dev/null | jq

echo -e "\n3. Testing combined search:"
curl -X POST http://localhost:3004/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Node", 
    "config": {
      "node_config": {
        "search_methods": ["fulltext"],
        "reranker": "rrf",
        "bfs_max_depth": 2,
        "sim_min_score": 0.5,
        "mmr_lambda": 0.5
      },
      "edge_config": {
        "search_methods": ["fulltext"],
        "reranker": "rrf",
        "bfs_max_depth": 2,
        "sim_min_score": 0.5,
        "mmr_lambda": 0.5
      },
      "episode_config": {
        "reranker": "rrf"
      },
      "limit": 2, 
      "reranker_min_score": 0.0
    }, 
    "filters": {}
  }' \
  2>/dev/null | jq