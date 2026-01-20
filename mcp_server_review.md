# Graphiti MCP Server: Status & Opportunities

## 1. Overview
The Graphiti MCP Server is **Already Production Ready**. It uses `FastMCP` (modern pattern) and exposes all critical endpoints via Pydantic-typed tools. It connects to the FastAPI backend, which connects to FalkorDB.

**Current Capabilities:**
*   `add_memory`: Adds episodes (text/json).
*   `search_memory_nodes`: Hybrid search for Entities.
*   `search_memory_facts`: Hybrid search for Edges (Facts).
*   `search_important_nodes`: Centrality-boosted search.
*   `search_diverse_facts`: MMR-diversity search.
*   `search_by_similarity`: Pure vector search.
*   `get_episodes`: Retrieve history.
*   `delete_episode/edge`: CRUD operations.

## 2. Comparison with "Competitor Features"

| Feature | Competitor (Mem0/Letta) | Graphiti MCP (Current) | Gap |
| :--- | :--- | :--- | :--- |
| **Simple API** | `m.add()` | `add_memory(name, body)` | ✅ **Parity**. Very simple. |
| **Hybrid Search** | Vector + Graph | `search_memory_nodes(methods=['fulltext', 'similarity', 'bfs'])` | ✅ **Parity**. We support BFS expansion. |
| **Active Control** | Agent decides what to save | Agent calls `add_memory` | ✅ **Parity**. |
| **Global Search** | Summarize Themes | *Missing* | ❌ **Gap**. We need a `global_search` tool. |
| **Temporal Search** | "What changed?" | *Missing* | ❌ **Gap**. We need `search_history` tool. |

## 3. Recommended Enhancements (The "GraphRAG" Upgrade)

To fully realize the "GraphRAG-Lite" vision we discussed, we should add these tools to `fastmcp_tools.py`.

### A. `global_search` (The Big Picture)
Answers: "What is the main topic of the last 10 episodes?"
*   *Implementation:* Call the `global_search` method we planned to add to the Python core.
*   *Tool Signature:* `global_search(query: str, time_range: str)`

### B. `temporal_search` (The Time Machine)
Answers: "How did the status of Project X change?"
*   *Implementation:* Retrieve entity history (Episodic Nodes linked to Entity).
*   *Tool Signature:* `get_entity_history(entity_name: str)`

## 4. Architectural Cleanup (MMP)
The MCP server code is clean, but it duplicates some Pydantic models from the Core.
*   *Action:* As we consolidate the architecture, we should publish a `graphiti-sdk` (pypi package) that both the Worker and the MCP Server import, sharing the exact same Pydantic models. Currently, they are redefined in `fastmcp_tools.py`.

## 5. Conclusion
The MCP server is the **strongest part of the current stack**. It is clean, modern, and effective.
*   **Don't rewrite it.**
*   **Extend it** with the new "Global/Temporal" capabilities once they are added to the Core.
