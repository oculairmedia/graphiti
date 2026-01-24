# Retrieval Quality Analysis & Improvement Opportunities

## 1. Executive Summary
**Overall Status:** The current search architecture is functional but constrained by its siloed "Scatter-Gather" design. It treats Edges, Nodes, Episodes, and Communities as separate search domains, aggregating them only at the very end.
**Critical Gap:** There is no "Graph Traversal" during search. The system acts as a set of 4 parallel Vector Databases rather than a Knowledge Graph.
**Biggest Opportunity:** Implementing **"Temporal Traversal"** (filtering paths by valid_at/invalid_at) and **"Graph-Native Expansion"** (HippoRAG-style spreading activation) will yield the highest ROI.

## 2. Current Architecture Analysis (`graphiti_core/search/search.py`)

### The "Scatter-Gather" Pattern
The `search` function performs 4 parallel searches:
1.  `edge_search`
2.  `node_search`
3.  `episode_search`
4.  `community_search`

Each of these follows the same sub-pattern:
*   **Step A (Recall):** Parallel calls to `fulltext_search`, `similarity_search` (Vector), and `bfs_search`.
*   **Step B (Aggregation):** Merge results from Step A.
*   **Step C (Reranking):** Apply RRF, MMR, or Cross-Encoder to the merged list.

### Weaknesses
1.  **Context Isolation:** The `episode_search` doesn't know which *Nodes* were found in `node_search`. It blindly searches for episodes matching the *query text*, missing episodes that might be relevant because they contain key entities.
2.  **No Temporal Filtering:** The `SearchFilters` class has `created_after` but lacks `valid_at`. You cannot ask "What was true in 2023?". The system will return "Current Facts" and "Past Facts" mixed together if they match the query text.
3.  **Static Centrality:** `NodeReranker.node_distance` uses a pre-calculated distance from a *single center node*. It doesn't support multi-hop reasoning from the *query's entities*.

## 3. High-Impact Improvements

### A. Graph-Native Expansion (The "HippoRAG" integration)
*   **Problem:** If I ask "Who manages the sales team?", vector search might find "Sales Team" but miss "Michael Scott" (Manager) if the text overlap is low.
*   **Fix:** Implement the **Spreading Activation** layer we proof-of-concepted.
*   **Integration Point:** In `node_search`, instead of just `node_similarity_search`, add `hipporag_search`.
*   **Status:** *POC Validated. Ready for Rust Integration.*

### B. Temporal Traversal (Time-Travel)
*   **Problem:** "Who was CEO in 2020?" returns "Alice (2020)" and "Bob (2024)" with equal weight if semantic similarity is high.
*   **Fix:** Add `valid_at` filtering to the `SearchFilters` and enforce it in the Cypher `MATCH` clauses.
*   **Integration Point:** `graphiti_core/search/search_filters.py` and `falkordb_driver.py`.
*   **Status:** *PRD Ready.*

### C. Cross-Domain Signaling (The "Unified" Search)
*   **Problem:** Searching for "Project Alpha bugs" might find "Project Alpha" (Node) and "Bug Report" (Episode), but failing to link them if the episode doesn't explicitly say "Project Alpha".
*   **Fix:** **Two-Stage Retrieval**.
    1.  Run `node_search` to find "Project Alpha".
    2.  Use the UUIDs of found nodes as `bfs_origin_node_uuids` for `episode_search`.
*   **Implementation:** Refactor `search()` to be serial/cascading rather than purely parallel.
    ```python
    # Draft Logic
    nodes = await node_search(...)
    relevant_uuids = [n.uuid for n in nodes]
    episodes = await episode_search(..., bfs_origin_node_uuids=relevant_uuids)
    ```

## 4. Minor Tweaks (Low Effort, Medium Reward)

1.  **Hybrid Reranking:** Currently, you choose *one* reranker (`RRF` OR `CrossEncoder`).
    *   *Improvement:* Always use RRF to combine Vector+Keyword, *then* pass the Top-50 to CrossEncoder. This gives better recall before precision filtering.
2.  **Deduplication:** `node_search` might return "Project X" and "Project X (Duplicate)". The `dedupe_nodes_bulk` logic exists in ingestion but isn't applied at query time.
    *   *Improvement:* Apply `synonymy` collapsing in the search result object.

## 7. Context Sandwiching (Mitigating 'Lost in the Middle')

**Context:** Research (e.g., "Lost in the Middle", Liu et al. 2023) shows that LLM attention follows a U-shaped curve: recall is highest at the beginning and end of the context window, and significantly degrades in the middle.

**The Strategy:**
"Sandwich" the retrieved context blocks with the User Query/Instruction.

*   **Current Pattern:** `[System Prompt] + [Query] + [Retrieved Context]` (Query is far from the generation point).
*   **Optimized Pattern:** `[System Prompt] + [Query] + [Retrieved Context] + [Query (Reminder)]`.

**Mechanism:**
1.  **Primacy:** The initial Query sets the goal.
2.  **Recency:** Repeating the Query immediately before generation forces the model to re-attend to the specific question *after* processing the potentially noisy retrieved facts.

**Implementation:**
*   Modify `graphiti_core/prompts/qa.py` (and similar RAG templates) to inject the `query` variable a second time at the very end of the prompt string.
*   **Cost:** Negligible (adds ~10-20 tokens).
*   **Impact:** Reduces hallucinations where the model "forgets" the specific constraint of the question while reading long context.
