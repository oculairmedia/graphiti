# Comparative Analysis: Graphiti vs. Mem0

## Overview
This document compares **Graphiti** (our current project) with **Mem0** (an intelligent memory layer for AI). Both projects aim to solve the "context window limit" and "catastrophic forgetting" problems for AI agents, but they approach it with different philosophies and architectural choices.

## 1. Core Philosophy
*   **Graphiti:** Focuses on **Temporal Knowledge Graphs**. It models memory as a graph of *Entities* and *Relations* that evolve over time (ValidAt/InvalidAt). It is "Graph-Native" and treats time as a first-class citizen.
*   **Mem0:** Focuses on a **Hybrid Memory Layer**. It combines Vector Search (semantic), Graph (relationships), and User/Session/Agent scoping. It positions itself as a "managed memory service" (like Auth0 for memory) rather than just a graph database wrapper.

## 2. Architecture Comparison

| Feature | Graphiti (Current) | Mem0 (Competitor) | Learning Opportunity |
| :--- | :--- | :--- | :--- |
| **Storage** | **FalkorDB** (Graph) + **Rust** (Search/Compute) | **Vector DB** (Chroma/Qdrant) + **Graph DB** (Neo4j) + **SQL** (Metadata) | Mem0's hybrid approach (Vector first, Graph second) might be more robust for "fuzzy" recall, whereas Graphiti relies heavily on the Graph structure being correct. |
| **Extraction** | **DSPy** (Programmatic Prompts) | **LLM Fact Extraction** (JSON/Structured) | Graphiti's DSPy approach is likely *more advanced* and maintainable than standard prompt templates, provided it is configured correctly. |
| **Scoping** | Group ID (Basic partitioning) | **User / Agent / Session** (Hierarchical) | **CRITICAL:** Graphiti should adopt a standard hierarchical scoping model (User -> Session) to make it easier for multi-user apps. |
| **Updates** | **Temporal Edges** (ValidAt/InvalidAt) | **Memory Decay** & **Update Logic** | Graphiti's temporal model is unique and superior for "audit trails" and "rewinding time". Mem0 focuses on "current state" and "decay". |
| **Developer UX** | Low-level Graph API (Nodes/Edges) | High-level Memory API (`add`, `search`, `get_all`) | **CRITICAL:** Mem0 wins on DX. Its API abstracts away the "Graph" entirely. Graphiti exposes too much graph complexity (Nodes, Edges, UUIDs) to the end user. |

## 3. Key Takeaways for Graphiti

### A. Simplify the API (The "Mem0" Experience)
Mem0's API is dead simple:
```python
m.add("I like pizza", user_id="123")
m.search("What does user 123 like?")
```
Graphiti's API is verbose:
```python
graph.add_episode(name="...", content="I like pizza", source=...)
# Internal complexity: Nodes, Edges, Embeddings, Deduplication
```
**Action:** Create a high-level wrapper (e.g., `GraphitiMemory`) that hides the `add_episode` / `Node` / `Edge` complexity.

### B. Hybrid Retrieval is Mandatory
Mem0 explicitly markets "Vector + Graph". Graphiti has `graphiti-search-rs` which does Hybrid Search, but it is complex to configure.
**Action:** Ensure "Hybrid Search" is the *default* and *only* way to search. Don't make the user choose between RRF and MMR unless they want to.

### C. "User" is a First-Class Citizen
Mem0 scopes everything by `user_id`. Graphiti uses generic `group_id`.
**Action:** Standardize `group_id` patterns or introduce `user_id` / `session_id` metadata fields to align with how developers actually build apps.

### D. Documentation & Positioning
Mem0 positions itself as "The Memory Layer". Graphiti positions itself as "A Temporal Graph Library".
**Action:** Pivot messaging to focus on **"Time-Travel Memory for Agents"**. The temporal aspect is Graphiti's "Killer Feature" that Mem0 lacks (Mem0 has decay, but not full bi-temporal history).

## 4. Strategic Recommendation
**Don't copy Mem0's architecture** (Graphiti's Temporal Graph is technically superior for complex agents).
**DO copy Mem0's Developer Experience.** Make the simple things simple. Hide the graph. Expose the Memory.
