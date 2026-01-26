# Codebase Audit & Improvement Proposal: Search Logic

## 1. Executive Summary
**Finding:** The `graphiti_core` Python client currently has "dead code" references to HippoRAG and uses a purely parallel "Scatter-Gather" search architecture that ignores graph connectivity.
**Proposal:** 
1.  **Activate HippoRAG:** Add the missing handler for `NodeSearchMethod.hipporag` in `search.py`.
2.  **Enable Graph Cascading:** Refactor `search()` to run `node_search` *first*, then use the found nodes as seeds for `edge_search` and `episode_search`.

## 2. Audit Findings (The "Failure")

### A. Dead Code: HippoRAG Config but No Implementation
*   **File:** `graphiti_core/search/search_config.py`
    *   Defines `NodeSearchMethod.hipporag = 'hipporag'`
    *   Defines config fields: `hipporag_max_hops`, `hipporag_decay`.
*   **File:** `graphiti_core/search/search.py`
    *   **Failure:** In `node_search` (Lines 330-350), there is **NO check** for `NodeSearchMethod.hipporag`.
    *   **Impact:** If a user sets `search_methods=['hipporag']`, the search will silently do nothing (return empty list).

### B. Architectural Weakness: Parallel Isolation
*   **File:** `graphiti_core/search/search.py` (Line 160)
    *   `edges, nodes, episodes, communities = await semaphore_gather(...)`
    *   **Failure:** All 4 searches start simultaneously.
    *   **Impact:** `edge_search` and `episode_search` have no knowledge of the Entities found by `node_search`. They are searching blindly for the *text query* rather than the *semantic topic*.
    *   **Example:** Query "Bugs in Auth".
        *   `node_search` finds `AuthService` (Good).
        *   `episode_search` finds text "bugs" but misses "Fixed login issue" because it doesn't know "login" is related to `AuthService`.

## 3. Improvement Proposal

### Step 1: Serialize Execution (Cascading)
Change `search()` to:
1.  **Stage 1:** Run `node_search` (Vector + Keyword).
    *   *Result:* 10 relevant Entity Nodes.
2.  **Stage 2:** Run `edge_search`, `episode_search`, `community_search`.
    *   *Input:* Query + **Context Seeds** (the 10 Entity UUIDs from Stage 1).
    *   *Mechanism:* Pass `bfs_origin_node_uuids = found_node_uuids`.

### Step 2: Implement HippoRAG Handler
In `node_search` and `edge_search`:
```python
if NodeSearchMethod.hipporag in config.search_methods:
    search_tasks.append(
        # New wrapper function in search_utils.py that calls the Rust endpoint
        node_hipporag_search(driver, query_vector, ...) 
    )
```

## 4. Expected Outcomes
*   **Precision:** Drastically reduced hallucinations because retrieval is grounded in known graph entities.
*   **Recall:** Finds episodes/edges that don't match the keyword but are connected to the relevant entity.
*   **Functional Parity:** The Python client finally uses the advanced Rust algorithms we built.
