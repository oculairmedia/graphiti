# Landscape Analysis: Graphiti vs. The World

## Overview
This document positions Graphiti against the broader landscape of AI Memory Frameworks, identifying unique strengths and critical missing features.

## 1. The Competitors

### **Letta (formerly MemGPT)**
*   **Philosophy:** "OS for LLMs." Mimics virtual memory (paging data in/out of context window).
*   **Key Tech:** Context Re-writing, Archival Storage, "Heartbeat" events.
*   **Strength:** **Autonomy.** The LLM decides what to remember/forget via function calls.
*   **Weakness:** Can get "lost" in its own memory management. Less structured than a graph.

### **Zep (Commercial Competitor)**
*   **Philosophy:** "Long-term Memory Service."
*   **Key Tech:** Graphiti (ironically, Zep *uses* Graphiti-like concepts internally, but Graphiti is the open-source alternative).
*   **Strength:** Polished Cloud API, "Session Classification".
*   **Weakness:** Closed source (mostly).

### **Mem0**
*   **Philosophy:** "The Memory Layer."
*   **Strength:** DX. `m.add()`, `m.search()`. Simple.
*   **Weakness:** Less powerful temporal reasoning than Graphiti.

### **GraphRAG (Microsoft)**
*   **Philosophy:** "Global Summarization."
*   **Strength:** answering "What is this dataset about?" via hierarchical community detection.
*   **Weakness:** extremely expensive (tokens) and static (batch processing). Not for real-time agents.

## 2. Graphiti's Unique Niche: "The Temporal Graph"

Graphiti is the only framework that treats **Time** as a first-class citizen in a Graph.
*   **Letta:** "What did I store?"
*   **Mem0:** "What is relevant now?"
*   **Graphiti:** "How did this entity change from last week to today?"

### The "Killer Feature": Temporal Traversal
Agents need to understand cause-and-effect.
*   *User:* "Why is the build failing?"
*   *Graphiti:* "Because 2 hours ago, *Commit X* changed *Dependency Y*."
*   *Mem0:* "Here are facts about builds and dependencies." (Lacks the causal/temporal link).

## 3. Strategic Roadmap

### Phase 1: DX parity with Mem0 (Immediate)
*   **Goal:** Make `Graphiti` as easy to use as `Mem0`.
*   **Action:** Build the `GraphitiMemory` wrapper (as proposed previously). Hide the "Episode" complexity.

### Phase 2: Causal Reasoning (The Differentiator)
*   **Goal:** Prove why "Time" matters.
*   **Action:** Add "Time-Travel Search" to the API. `memory.search("status", change_since="1 hour ago")`.

### Phase 3: The "OS" Layer (Stealing from Letta)
*   **Goal:** Give the LLM control.
*   **Action:** Add `save_memory` and `recall_memory` TOOLS that the Agent can call itself. Currently, Graphiti is "Passive" (ingest pipeline). We need to make it "Active" (Agent decides what to save).

## 4. Conclusion
Graphiti is positioned correctly: **Graph + Time**.
*   **Vector-only** (Chroma) is too dumb.
*   **Graph-only** (Neo4j) is too static.
*   **Graph + Time** (Graphiti) is the model of the real world.

**Next Step:** Build the simple API wrapper. You have the engine of a Ferrari (Temporal Graph) with the dashboard of a tractor (Raw Graph API). Give it a steering wheel.
