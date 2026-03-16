# API Reference

> **Keywords**: `api`, `rest`, `fastapi`, `endpoints`, `server`, `http`

## REST API (Port 8003)

### Base URL

```
http://localhost:8003
```

---

## Endpoints

### Health

```
GET /healthcheck
```

**Response**:
```json
{
  "status": "healthy"
}
```

### Graph Ping

```
GET /api/graph/ping
```

**Response**:
```json
{
  "ok": true,
  "service": "graph"
}
```

---

### Search

```
POST /api/graph/search
```

**Request Body**:
```json
{
  "query": "string",
  "num_results": 10,
  "search_type": "hybrid",
  "group_ids": ["optional"],
  "min_created_at": "2026-01-01T00:00:00Z",
  "max_created_at": "2026-03-01T00:00:00Z"
}
```

**Response**:
```json
{
  "edges": [
    {
      "uuid": "string",
      "fact": "string",
      "source_node_uuid": "string",
      "target_node_uuid": "string",
      "created_at": "timestamp"
    }
  ]
}
```

---

### Add Episode

```
POST /api/graph/episodes
```

**Request Body**:
```json
{
  "name": "episode_name",
  "source_content": "Content to extract entities from",
  "source_description": "Optional context",
  "reference_time": "2026-03-12T00:00:00Z",
  "group_id": "optional_group",
  "previous_episode_uuid": "optional_uuid"
}
```

**Response**:
```json
{
  "uuid": "episode_uuid",
  "name": "episode_name",
  "created_at": "timestamp"
}
```

---

### Get Node

```
GET /api/graph/nodes/{uuid}
```

**Response**:
```json
{
  "uuid": "string",
  "name": "string",
  "summary": "string",
  "created_at": "timestamp",
  "labels": ["Entity"]
}
```

---

### Get Edge

```
GET /api/graph/edges/{uuid}
```

**Response**:
```json
{
  "uuid": "string",
  "fact": "string",
  "source_node_uuid": "string",
  "target_node_uuid": "string",
  "created_at": "timestamp",
  "t_valid_at": "timestamp",
  "t_invalid_at": "timestamp or null"
}
```

---

### Search Nodes

```
POST /api/graph/nodes/search
```

**Request Body**:
```json
{
  "query": "string",
  "num_results": 10,
  "entity_types": ["Entity"]
}
```

**Response**:
```json
{
  "nodes": [
    {
      "uuid": "string",
      "name": "string",
      "summary": "string"
    }
  ]
}
```

---

### Centrality

```
GET /api/centrality/{node_uuid}
```

**Response**:
```json
{
  "uuid": "string",
  "pagerank": 0.015,
  "degree_centrality": 0.23,
  "betweenness": 0.008
}
```

---

### MCP Server (Port 3010)

The MCP server provides tools for Claude integration.

#### Tools Available

| Tool | Description |
|------|-------------|
| `add_memory` | Add episode to knowledge graph |
| `search_memory` | Search the knowledge graph |
| `get_entity` | Get entity by UUID or name |
| `get_entities` | List entities with filters |
| `delete_entity` | Delete an entity |
| `add_episode` | Add episode to graph |
| `get_episode` | Get episode by UUID |
| `delete_episode` | Delete an episode |
| `search_nodes` | Search for nodes |
| `search_edges` | Search for edges |

See the MCP server README at `mcp_server/README.md` for detailed MCP usage.

---

## Error Responses

All endpoints return consistent error format:

```json
{
  "error": "Error type",
  "message": "Human-readable message",
  "details": {}
}
```

### Common HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad Request - invalid input |
| 404 | Not Found |
| 500 | Internal Server Error |
| 503 | Service Unavailable |

---

## Authentication

Currently no authentication required for local development.

For production, configure via environment variables:

```bash
API_KEY=your-api-key
```

---

## Rate Limiting

Rate limiting is configured via Temporal:

```bash
TEMPORAL_MAX_CONCURRENT_ACTIVITIES=5
TEMPORAL_RATE_LIMIT_POST_LLM_DELAY=2.0
```

---

## Files to Know

| File | Purpose |
|------|---------|
| `server/graph_service/main.py` | FastAPI app entry point |
| `server/graph_service/routers/` | API route handlers |
| `mcp_server/graphiti_mcp_server.py` | MCP server implementation |

---

## See Also

- [schema-reference.md](schema-reference.md) - Data schemas
- [config-reference.md](config-reference.md) - Configuration
- [../how-to/add-api-endpoint.md](../how-to/add-api-endpoint.md) - Add new endpoints
