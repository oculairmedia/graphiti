# How-to: Use MCP Tools

> **Keywords**: `mcp`, `tools`, `graphiti-memory`, `claude`, `cursor`, `http`, `stdio`

## What This Covers

This guide maps Graphiti MCP server setup and tool usage to a quick, task-oriented workflow.

---

## 1) Start the MCP Server

Standalone/dev mode from `mcp_server/`:

```bash
uv sync
uv run graphiti_mcp_server.py --transport http --port 3010
```

Stack mode with Docker (recommended for this repo):

```bash
docker compose up
```

Stack endpoint is typically `http://localhost:3010/mcp` (or `${MCP_PORT}/mcp`).

---

## 2) Configure Client Transport

### HTTP clients (stack default)

Use:

- `http://localhost:3010/mcp`

### stdio clients

Run through `uv` in `mcp_server/` and set required env vars.

---

## 3) Core Tools (High Value)

Main tools exposed by the MCP server include:

- `add_episode`
- `search_nodes`
- `search_facts`
- `get_episodes`
- `get_entity_edge`
- `delete_entity_edge`
- `delete_episode`
- `clear_graph`
- `get_status`

These are documented in `mcp_server/README.md`.

---

## 4) Example Usage Pattern

1. Ingest memory/event with `add_episode`.
2. Retrieve relevant facts with `search_facts`.
3. Retrieve related entities with `search_nodes`.
4. Fetch recent timeline with `get_episodes`.

This sequence gives a balanced memory read/write workflow for agent-driven tasks.

---

## 5) Required Environment Variables

Common required variables:

- `OPENAI_API_KEY`
- `FALKORDB_HOST`
- `FALKORDB_PORT`
- `FALKORDB_DATABASE`

Optional tuning:

- `MODEL_NAME`
- `SMALL_MODEL_NAME`
- `LLM_TEMPERATURE`
- `SEMAPHORE_LIMIT`

---

## 6) Troubleshooting MCP Tool Calls

### Server starts but tool calls fail

- Confirm DB connectivity and credentials.
- Check `mcp_server` logs for transport or auth errors.

### Slow ingestion or 429 errors

- Lower `SEMAPHORE_LIMIT` to reduce request concurrency.

### Client cannot connect

- Verify transport matches client capability (`sse`, `http`, or `stdio`).
- Confirm endpoint path and port.

---

## Files to Know

| File | Purpose |
|------|---------|
| `mcp_server/README.md` | Full setup and tool documentation |
| `mcp_server/graphiti_mcp_server.py` | MCP server entrypoint |
| `mcp_server/fastmcp_tools.py` | Tool definitions and wrappers |

---

## See Also

- [../reference/api-reference.md](../reference/api-reference.md) - REST API context
- [add-episode.md](add-episode.md) - Ingestion concepts used by MCP flows
- [../gotchas.md](../gotchas.md) - Operational pitfalls
