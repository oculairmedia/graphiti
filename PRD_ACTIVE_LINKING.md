# Product Requirement Document (PRD): Active Linking (Code-Graph Sync)

## 1. Executive Summary
**Objective:** Maintain real-time freshness of "Software Entities" (files, classes, functions) in the Knowledge Graph by establishing an active link between the source code and the graph.
**Problem:** Knowledge Graphs rot. A description of `graphiti.py` generated last week is outdated today. "Stale knowledge" leads to hallucinations when the agent relies on the graph for coding tasks.
**Solution:** A **File Watcher Agent** that detects filesystem changes, re-summarizes the changed code, and atomically updates the corresponding Entity Node in Graphiti via the API.
**Impact:** The Graph becomes a "Live Twin" of the codebase, ensuring Retrieval Augmented Generation (RAG) always operates on ground truth.

## 2. Technical Architecture

### A. The "Shadow Graph" Principle
We treat the codebase as a graph where:
*   **Entity Name:** `File:{relative_path}` (e.g., `File:graphiti_core/graphiti.py`)
*   **Group ID:** `codebase_v1` (or user defined)
*   **Summary:** The actual code summary/interface definition.

### B. The Watcher Pipeline
We will implement a standalone service `graphiti-watcher` (or integrate into `shepherd`).

1.  **Trigger:** `watchdog` (Python library) monitors the target directory.
2.  **Filter:** Ignore `.git`, `__pycache__`, and binary files.
3.  **Debounce:** Wait 5 seconds after last write to avoid thrashing.
4.  **Process:**
    *   Read File Content.
    *   **Generate Summary:** Use a fast LLM (e.g., `gpt-4o-mini` or local `Qwen-2.5-Coder`) to generate a "Graphiti-optimized" summary.
        *   *Prompt:* "Summarize this code file. Focus on its *responsibilities*, *exported classes*, and *key dependencies*. Do not recite code line-by-line."
    *   **Resolve UUID:** Use Graphiti's `generate_deterministic_uuid(name, group_id)`.
    *   **Push:** Call `PATCH /nodes/{uuid}/summary`.

### C. The API Integration
*   **Endpoint:** `PATCH /nodes/{uuid}/summary` (Confirmed existing).
*   **Payload:** `{"summary": "Updated summary..."}`.

## 3. Implementation Plan

### Step 1: The `CodeSummarizer` Module
*   Input: `file_content`, `file_path`.
*   Output: `summary_text`.
*   Logic: Simple LLM call. Can be enhanced with LSP (Language Server Protocol) later for structured symbols.

### Step 2: The `GraphitiSyncer` Class
*   Config: `base_url`, `group_id`.
*   Method: `sync_file(path)`
    1.  Name = `File:{path}`.
    2.  UUID = `uuid5(NAMESPACE, Name + Group)`.
    3.  Summary = `CodeSummarizer.summarize(path)`.
    4.  `client.patch(f"/nodes/{uuid}/summary", json={"summary": Summary})`.

### Step 3: The Watcher Daemon (`scripts/watch_codebase.py`)
*   Uses `watchdog.observers.Observer`.
*   Runs an infinite loop mapping file events to `GraphitiSyncer.sync_file`.

## 4. Advanced Features (Phase 2)

### LSP Integration
Instead of LLM summarization, query the LSP (e.g., `pyright` or `rust-analyzer`) for the "Symbol Hierarchy".
*   *Summary:* "Defines class `Graphiti` with methods `add_episode`, `search`..."
*   *Benefit:* 100% accurate, zero hallucination, faster.

### Dependency Linking
*   Parse `import` statements.
*   Create `[DEPENDS_ON]` edges between File Entities.
*   *Result:* The Graph reflects the actual dependency tree.

## 5. Success Metrics
*   **Latency:** Time from `Ctrl+S` to Graph Update < 10 seconds.
*   **Accuracy:** When I ask "What does `graphiti.py` do?", the answer reflects the code I just wrote.
