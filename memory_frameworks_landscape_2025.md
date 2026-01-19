# AI Memory Frameworks: 2025 Landscape Review

## Overview
This document summarizes the current state of "AI Memory Frameworks" to help position Graphiti. The market is splitting into **Infrastructure** (pipes/storage) and **Cognition** (reasoning/autonomy).

## 1. Top Competitors & Categories

### Category A: The "OS" for Agents (Cognition)
These frameworks try to manage the *entire* lifecycle of an agent's brain.
*   **Letta (formerly MemGPT):** The leader in "OS-like memory management."
    *   *Killer Feature:* Paging data in/out of context automatically.
    *   *Weakness:* Can be heavy; opinionated about how agents work.
*   **Agent Zero:** Focuses on "Agentic RAG" and tool use.
*   **General Agentic Memory (GAM):** Dual-agent architecture (Memorizer + Researcher).

### Category B: The "Memory Layer" (Infrastructure)
These frameworks provide a clean API for developers to "add memory" to their own agents.
*   **Mem0:** The "Auth0 for Memory." Simple API, hybrid vector+graph.
    *   *Killer Feature:* `m.add()`, `m.search()`. Extremely low barrier to entry.
*   **Zep:** (Our commercial cousin). Graph-based, cloud-hosted, polished.
*   **MemU:** Hierarchical file-system approach (unconventional, but interesting).

### Category C: The "Toolkit" (Building Blocks)
*   **LangChain / LlamaIndex:** Provide memory *primitives* (ConversationBufferWindowMemory), but lack the "Entity/Graph" intelligence of Graphiti.
*   **GraphRAG (Microsoft):** Global summarization, but expensive and batch-oriented.

## 2. Where Graphiti Fits
Graphiti is unique because it is **Infrastructure** (like Mem0) but with **Temporal Cognition** (like Letta).

| Feature | Mem0 | Letta | Graphiti |
| :--- | :--- | :--- | :--- |
| **Model** | Vector + Static Graph | Hierarchical Context | **Temporal Graph** |
| **Time** | Decays old facts | "Recency" bias | **ValidAt / InvalidAt** |
| **Control** | Passive (Developer calls API) | Active (LLM calls functions) | **Hybrid** (Ingest pipeline + Future Agent Tools) |
| **Use Case** | User Preferences | Long-running Chatbots | **Audit / State Tracking Agents** |

## 3. Critical Gaps & Opportunities

### A. The "Active Memory" Gap
Letta wins because the *Agent* decides what to save. Graphiti is currently a "Passive Pipe" (ingest everything).
*   **Opportunity:** We must expose Graphiti as a **Tool** (`save_fact`, `recall_facts`) that agents can call. This moves us from "Database" to "Cognitive Extension".

### B. The "Hierarchy" Gap
Mem0 and MemU emphasize "User / Session / Agent" scoping. Graphiti just has `group_id`.
*   **Opportunity:** Adopt standard metadata schemas for multi-tenancy.

### C. The "Latency" Gap
Zep claims sub-200ms latency. Graphiti's `search` currently does multiple LLM calls (RRF, Reranking) which can be slow (seconds).
*   **Opportunity:** We need a "Fast Path" (Vector Only) and a "Slow Path" (Deep Graph Traversal). Currently, we default to the Slow Path.

## 4. Final Recommendation
**Don't become an Agent Framework (Letta).**
**Don't just be a Vector DB (Chroma).**

**Be the "Time Machine" for Agents.**
Position Graphiti as the **only** solution that can answer: *"What did we know about Project X on Tuesday vs. Today?"* This is critical for Enterprise/Audit agents, which is a massive underserved market.
