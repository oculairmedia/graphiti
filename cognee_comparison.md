# Comparative Analysis: Graphiti vs. Cognee

## Overview
This document compares **Graphiti** with **Cognee** (https://github.com/topoteretes/cognee), a framework that positions itself as a "Cognitive Memory Layer" for AI. Like Mem0, Cognee uses a hybrid Vector + Graph approach, but it places a much stronger emphasis on **"Cognification"** (data processing pipelines) and **Ontology**.

## 1. Core Philosophy Differences
*   **Graphiti:** "A Temporal Knowledge Graph." The core atom is the **Episode** (event), which creates **Entities** and **Edges** that are valid for specific time ranges. The philosophy is "History is immutable; knowledge evolves."
*   **Cognee:** "Extract -> Cognify -> Load." The core philosophy is **ETL for Agents**. It emphasizes breaking data into chunks, classifying them, and mapping them to a strict ontology (Data Models) before loading them into a Graph/Vector store.

## 2. Architecture Comparison

| Feature | Graphiti (Current) | Cognee (Competitor) | Learning Opportunity |
| :--- | :--- | :--- | :--- |
| **Pipeline** | Episode -> Extraction (DSPy) -> Dedupe -> Persistence | `add` -> `cognify` -> `search` | Cognee's `cognify` step is explicit and separates "Ingestion" from "Understanding". Graphiti bundles these into `add_episode`. Separating them could allow for background "deep thinking" or graph refinement. |
| **Storage** | **FalkorDB** (Graph) + **Rust** (Compute) | **Relational** (Provenance) + **Vector** (Chunks) + **Graph** (Network) | Cognee explicitly maintains a **Relational Store** for provenance (source tracking). Graphiti stores source metadata on nodes/edges but lacks a dedicated provenance catalog. |
| **Ontology** | Dynamic (Labels/Types from LLM) | **Pydantic Models** (Strict) | Cognee encourages defining your graph schema (Ontology) using Pydantic models *before* ingestion. Graphiti is more "schema-on-read" / dynamic. |
| **Retrieval** | `search_nodes` (Hybrid) | `search` (Vector/Graph/Hybrid) | Cognee allows searching for "subgraphs" based on relationships. Graphiti's retrieval is currently node-centric. |

## 3. Key Takeaways for Graphiti

### A. The "Cognify" Step (Background Refinement)
Cognee acknowledges that "Understanding" is expensive and maybe shouldn't happen purely at ingestion time.
*   **Current Graphiti:** `add_episode` does everything (Extract, Dedupe, Embed, Persist). This is slow.
*   **Recommendation:** Split `add_episode` into `ingest_episode` (fast, just save content) and a background `process_episode` (the heavy lifting). You already have a Worker for this, but the API suggests synchronous blocking behavior.

### B. Provenance Tracking
Cognee's Relational Store tracks "Where did this node come from?" down to the document chunk.
*   **Current Graphiti:** Tracks `episodes` list on Edges.
*   **Recommendation:** This is actually a strength of Graphiti. The `EpisodicNode` *is* the provenance. We should double down on this and expose APIs like `get_history(entity_id)` to show the timeline of how an entity evolved.

### C. Strict vs. Dynamic Ontology
Cognee forces you to define what a "User" or "Order" looks like. Graphiti lets the LLM decide.
*   **Recommendation:** For Agents, **Dynamic is better**. Agents encounter novel situations. Do not adopt Cognee's strict schema approach, but perhaps allow "hinting" schema (which Graphiti already does via `entity_types`).

## 4. Strategic Positioning
*   **Cognee** = "ETL Tool for building Graphs". Good for static knowledge bases (documents, wikis).
*   **Mem0** = "User Profile Manager". Good for chat personalization.
*   **Graphiti** = "The Time-Traveling Brain". Good for **Long-Running Agents** that need to understand *sequences of events* (e.g., "The project status changed from Green to Red yesterday").

## 5. Actionable Implementation: "The Graphiti API"
We should adopt the "Verb-based" API simplicity found in both Cognee and Mem0.

**Proposed High-Level API:**
```python
# Initialize
g = Graphiti("redis://...")

# 1. Ingest (The "Add" step)
g.add("Meeting with Alice about Project X")

# 2. Recall (The "Search" step)
# "Time-Traveling" search is our unique differentiator
g.search("What is the status of Project X?", at=datetime(2023, 10, 1)) 
```

**Conclusion:** Cognee is a heavy ETL framework. Graphiti is a dynamic memory engine. We should avoid Cognee's complexity (3 separate databases) and focus on our strength: **Time**.
