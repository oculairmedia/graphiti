# Centrality Analysis API

The Graphiti Centrality API provides endpoints for calculating and retrieving various centrality metrics for nodes in your knowledge graph. These metrics help identify the most important or influential entities in your graph.

## Overview

Centrality analysis helps answer questions like:
- Which entities are most connected? (Degree Centrality)
- Which entities are most influential in terms of information flow? (PageRank)
- Which entities act as bridges between different parts of the graph? (Betweenness Centrality)

## Endpoints

### Calculate All Centralities

Calculate all centrality metrics for the entire graph or a subset of nodes.

```http
POST /centrality/calculate
```

#### Request Body

```json
{
  "node_ids": ["node-uuid-1", "node-uuid-2"],  // Optional: specific nodes to calculate
  "recalculate": false                          // Optional: force recalculation
}
```

#### Response

```json
{
  "status": "success",
  "data": {
    "calculated_nodes": 150,
    "execution_time_ms": 2340,
    "metrics_calculated": ["pagerank", "degree", "betweenness"]
  }
}
```

### Get PageRank Scores

Retrieve PageRank centrality scores for nodes.

```http
GET /centrality/pagerank
```

#### Query Parameters

- `node_ids` (optional): Comma-separated list of node IDs
- `top_n` (optional): Return top N nodes by PageRank score
- `min_score` (optional): Minimum score threshold

#### Response

```json
{
  "status": "success",
  "data": [
    {
      "node_id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Machine Learning",
      "pagerank": 0.0834,
      "rank": 1
    },
    {
      "node_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
      "name": "Neural Networks",
      "pagerank": 0.0672,
      "rank": 2
    }
  ],
  "metadata": {
    "total_nodes": 150,
    "returned_nodes": 2,
    "calculation_timestamp": "2025-01-22T10:30:00Z"
  }
}
```

### Get Degree Centrality

Retrieve degree centrality scores (normalized by total possible connections).

```http
GET /centrality/degree
```

#### Query Parameters

- `node_ids` (optional): Comma-separated list of node IDs
- `top_n` (optional): Return top N nodes by degree
- `direction` (optional): "in", "out", or "total" (default: "total")

#### Response

```json
{
  "status": "success",
  "data": [
    {
      "node_id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Data Science",
      "degree_centrality": 0.342,
      "in_degree": 25,
      "out_degree": 30,
      "total_degree": 55,
      "rank": 1
    }
  ],
  "metadata": {
    "total_nodes": 150,
    "returned_nodes": 1,
    "max_possible_connections": 149
  }
}
```

### Get Betweenness Centrality

Retrieve betweenness centrality scores (how often a node appears on shortest paths).

```http
GET /centrality/betweenness
```

#### Query Parameters

- `node_ids` (optional): Comma-separated list of node IDs
- `top_n` (optional): Return top N nodes by betweenness
- `normalized` (optional): Return normalized scores (default: true)

#### Response

```json
{
  "status": "success",
  "data": [
    {
      "node_id": "7ba9b810-9dad-11d1-80b4-00c04fd430c8",
      "name": "Software Architecture",
      "betweenness_centrality": 0.156,
      "rank": 1
    }
  ],
  "metadata": {
    "total_nodes": 150,
    "returned_nodes": 1,
    "normalized": true,
    "sample_size": 50  // If sampling was used
  }
}
```

### Get Combined Centrality Report

Get a comprehensive report with all centrality metrics for specified nodes.

```http
GET /centrality/report/{node_id}
```

#### Response

```json
{
  "status": "success",
  "data": {
    "node": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Artificial Intelligence",
      "type": "CONCEPT"
    },
    "centrality_metrics": {
      "pagerank": {
        "score": 0.0834,
        "rank": 3,
        "percentile": 95.2
      },
      "degree": {
        "score": 0.298,
        "in_degree": 20,
        "out_degree": 25,
        "total_degree": 45,
        "rank": 5,
        "percentile": 92.1
      },
      "betweenness": {
        "score": 0.089,
        "rank": 8,
        "percentile": 88.5
      }
    },
    "interpretation": {
      "influence": "high",
      "connectivity": "very high",
      "bridge_role": "moderate"
    }
  }
}
```

## Usage Examples

### Python Client Example

```python
import requests
import json

# Base URL for Graphiti server
BASE_URL = "http://localhost:8000"

# Calculate centralities for all nodes
response = requests.post(f"{BASE_URL}/centrality/calculate")
result = response.json()
print(f"Calculated centralities for {result['data']['calculated_nodes']} nodes")

# Get top 10 most influential nodes by PageRank
response = requests.get(f"{BASE_URL}/centrality/pagerank", params={"top_n": 10})
pagerank_data = response.json()

for node in pagerank_data['data']:
    print(f"{node['name']}: PageRank = {node['pagerank']:.4f}")

# Get degree centrality for specific nodes
node_ids = ["node-id-1", "node-id-2"]
response = requests.get(
    f"{BASE_URL}/centrality/degree",
    params={"node_ids": ",".join(node_ids)}
)
degree_data = response.json()

# Get comprehensive report for a single node
node_id = "550e8400-e29b-41d4-a716-446655440000"
response = requests.get(f"{BASE_URL}/centrality/report/{node_id}")
report = response.json()
print(json.dumps(report, indent=2))
```

### cURL Examples

```bash
# Calculate all centralities
curl -X POST http://localhost:8000/centrality/calculate \
  -H "Content-Type: application/json" \
  -d '{"recalculate": true}'

# Get top 5 nodes by PageRank
curl "http://localhost:8000/centrality/pagerank?top_n=5"

# Get degree centrality for specific nodes
curl "http://localhost:8000/centrality/degree?node_ids=node1,node2,node3"

# Get betweenness centrality with minimum score threshold
curl "http://localhost:8000/centrality/betweenness?min_score=0.01&top_n=20"

# Get full report for a node
curl "http://localhost:8000/centrality/report/550e8400-e29b-41d4-a716-446655440000"
```

## Implementation Details

### Performance Considerations

1. **Caching**: Centrality scores are cached after calculation with a configurable TTL
2. **Incremental Updates**: When possible, only affected nodes are recalculated after graph changes
3. **Sampling**: For large graphs, betweenness centrality uses sampling for better performance
4. **Parallel Processing**: Calculations leverage Neo4j's parallel runtime when available

### Algorithm Details

- **PageRank**: Uses damping factor of 0.85, maximum 20 iterations
- **Degree Centrality**: Normalized by (n-1) where n is the number of nodes
- **Betweenness Centrality**: Uses Brandes' algorithm with optional sampling for graphs > 1000 nodes

### Error Handling

All endpoints return consistent error responses:

```json
{
  "status": "error",
  "error": {
    "code": "CENTRALITY_CALCULATION_FAILED",
    "message": "Failed to calculate centrality metrics",
    "details": "Neo4j connection timeout after 30 seconds"
  }
}
```

Common error codes:
- `CENTRALITY_CALCULATION_FAILED`: Calculation error
- `NODE_NOT_FOUND`: Specified node doesn't exist
- `INVALID_PARAMETERS`: Invalid query parameters
- `DATABASE_ERROR`: Neo4j connection or query error

## Integration with Graphiti Core

The centrality metrics are stored as node properties in Neo4j:

```cypher
// Example node with centrality metrics
{
  uuid: "550e8400-e29b-41d4-a716-446655440000",
  name: "Machine Learning",
  pagerank: 0.0834,
  degree_centrality: 0.298,
  betweenness_centrality: 0.089,
  centrality_updated_at: "2025-01-22T10:30:00Z"
}
```

These metrics can be used in graph queries and search operations:

```python
from graphiti_core import Graphiti
from graphiti_core.search import SearchConfig

graphiti = Graphiti(neo4j_uri, neo4j_user, neo4j_password)

# Search for highly influential nodes
config = SearchConfig(
    max_results=10,
    reranker=None,
    filters={
        "pagerank": {"$gte": 0.05}  # High PageRank threshold
    }
)

results = await graphiti.search("machine learning", config)
```