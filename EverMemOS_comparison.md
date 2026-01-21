# Comparative Analysis: Graphiti vs. EverMemOS

## Overview
**EverMemOS** (https://github.com/EverMind-AI/EverMemOS) is a newer entrant focusing on "OS-level Memory Management."

## 1. Core Philosophy
*   **Graphiti:** "The Temporal Database." Stores facts and their validity over time.
*   **EverMemOS:** "The Memory Controller." Focuses on *routing* information between Short-term (RAM) and Long-term (Disk) memory. It mimics a CPU's memory hierarchy.

## 2. Architecture Comparison

| Feature | Graphiti | EverMemOS |
| :--- | :--- | :--- |
| **Metaphor** | Database (Neo4j/Falkor) | Operating System (RAM/Disk) |
| **Storage** | Graph + Vector | Vector + Summary + Raw Logs |
| **Retrieval** | Semantic + Graph Traversal | Hierarchical (Short -> Medium -> Long) |
| **Ingestion** | Extract -> Dedup -> Graph | Stream -> Cluster -> Summarize |

## 3. Key Feature to Steal: "The Memory Tiering"
EverMemOS explicitly manages **tiers**:
1.  **Working Memory:** The current context window.
2.  **Episodic Memory:** Recent history (raw).
3.  **Semantic Memory:** Long-term facts (summarized).

**Graphiti's Version:**
We actually *have* this data, but we don't expose it as "Tiers".
*   *Working:* (Not our job, handled by Agent).
*   *Episodic:* `EpisodicNode`.
*   *Semantic:* `EntityNode` and `CommunityNode`.

**Recommendation:**
We should update our **API/MCP Tools** to reflect these tiers.
*   `search_episodes()` -> "What happened recently?"
*   `search_facts()` -> "What do we know to be true?"
*   `search_themes()` -> "What are the big concepts?"

This "Tiered Retrieval" is easier for an Agent to understand than "Search Nodes with config X".

## 4. Conclusion
EverMemOS validates our direction but focuses more on the *Agent Loop* (Process Management). Graphiti focuses on the *State Storage* (Data Management).
We should remain the "Storage Layer" but offer "Tiered Retrieval APIs" to make it easy for Agents to act like EverMemOS.
