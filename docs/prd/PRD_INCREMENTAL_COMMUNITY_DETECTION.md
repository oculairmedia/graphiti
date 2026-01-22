# Product Requirement Document (PRD): Incremental Community Detection & Summarization

## 1. Executive Summary
**Objective:** Integrate Community Detection and Summarization directly into the primary `add_episode` ingestion pipeline, transitioning it from a slow, batch-based post-process to a real-time, incremental operation.
**Problem:** Currently, communities are built by re-scanning the entire graph and re-summarizing all nodes from scratch. This is O(N) or worse, making it too slow to run during ingestion. As a result, community insights are often stale or missing until a maintenance job runs.
**Solution:** Leverage FalkorDB's high-speed native algorithms (`algo.labelPropagation`) for instant structural clustering, combined with an **Iterative Refinement** strategy for LLM summarization.
**Impact:** "Always-on" high-level summaries. As soon as a message is ingested, the relevant "Community" (e.g., "Project X Team") is updated with the new context.

## 2. Technical Strategy

### A. The "Fast & Incremental" Philosophy
To fit within the latency budget of `add_episode` (typically < 5s), we cannot re-read the whole graph.
1.  **Structure (Clustering):** Use `CALL algo.labelPropagation` (LPA). On FalkorDB, this runs in milliseconds even for large graphs because it's a C-level matrix operation.
2.  **Content (Summarization):** Use **Delta Summarization**.
    *   *Old Way:* `Summary = LLM(Node1 + Node2 + ... + Node100)` (Context Window Explosion).
    *   *New Way:* `Summary_New = LLM(Summary_Old + Node_New)` (Constant Context).

### B. Architecture Changes
*   **Modify:** `graphiti_core/utils/maintenance/community_operations.py`
*   **Deprecate:** The Python-based `label_propagation` loop.
*   **Introduce:** `IncrementalCommunityManager` class to handle state transitions.

## 3. Detailed Implementation Flow

### Step 1: Structural Analysis (FalkorDB Native)
Immediately after new nodes/edges are saved in `add_episode`:

```cypher
// 1. Run Native LPA to assign structural labels to ALL nodes
CALL algo.labelPropagation({
    nodeLabels: ['Entity'],
    relationshipTypes: ['RELATES_TO']
}) YIELD node, label

// 2. Return ONLY the labels for the *newly added* nodes
// (We filter this in Python or via a subsequent MATCH)
```
*   **Result:** We know that `Node A` (new) belongs to `Cluster 42`.

### Step 2: Community Mapping & Delta Detection
We check the database for `Cluster 42`.
*   **Scenario A (Existing Community):** We find a `CommunityNode` linked to other nodes in `Cluster 42`.
    *   *Action:* Link `Node A` to this Community.
    *   *Task:* **Incremental Update**.
*   **Scenario B (New Community):** `Cluster 42` is new (or a split).
    *   *Action:* Create a new `CommunityNode`.
    *   *Task:* **Full Initialization**.
*   **Scenario C (Merge):** `Node A` bridges `Cluster 42` and `Cluster 99`.
    *   *Action:* Merge the two `CommunityNode`s.
    *   *Task:* **Merge Summaries**.

### Step 3: Just-in-Time Summarization
Instead of re-reading all members, we perform a focused LLM call based on the scenario.

**Prompt Strategy: The "Ledger" Update**
```text
<CURRENT_COMMUNITY_SUMMARY>
Project Alpha is a backend initiative led by Sarah, focused on Rust migration.
</CURRENT_COMMUNITY_SUMMARY>

<NEW_INFORMATION>
Node: "Sarah" -> "OOO until Monday"
Edge: "Project Alpha" -> "Delayed"
</NEW_INFORMATION>

<TASK>
Update the community summary to reflect the new information. 
Keep it concise.
</TASK>
```
*   **Input Token Cost:** Minimal (Summary + 1 Node).
*   **Latency:** Fast (~1s).

## 4. FalkorDB Integration Specifications
Reference: [FalkorDB Algorithms](https://docs.falkordb.com/algorithms/)

### Algorithm: Label Propagation (CDLP)
*   **Procedure:** `algo.labelPropagation`
*   **Configuration:**
    *   `nodeLabels`: `['Entity']` (Focus on knowledge entities)
    *   `relationshipTypes`: `['RELATES_TO']` (Ignore episodic edges to avoid temporal noise)
    *   `iterations`: `10` (Sufficient for convergence)

### Algorithm: Graph Projection (Implicit)
FalkorDB algorithms run on the projected graph. By specifying `relationshipTypes`, we implicitly project a subgraph of semantic relationships, ignoring the high-volume `MENTIONS` edges which would otherwise merge unrelated communities (the "everything is related to the User" problem).

## 5. Feasibility & Risk Assessment

| Feature | Complexity | Risk | Mitigation |
| :--- | :--- | :--- | :--- |
| **Native LPA** | Low | Low | Algorithm is standard in FalkorDB. Fallback to Python if missing. |
| **Delta Summary** | Medium | Medium | "Drift" over time. The summary might lose detail if we only patch it. **Fix:** Run a full re-summary job nightly. |
| **Concurrency** | High | High | Race conditions if multiple episodes update the same community. **Fix:** Use Redis locks or `semaphore_gather` with localized locking on `group_id`. |

## 6. Success Metrics
*   **Ingestion Latency:** `add_episode` overhead < 500ms for community updates.
*   **Freshness:** Community Summary reflects facts from the *latest* episode immediately.
*   **Cost:** Reduce LLM tokens for community building by 90% (O(1) vs O(N)).

## 7. Migration Plan
1.  **Refactor `community_operations.py`:**
    *   Implement `detect_communities_native(driver)`.
    *   Implement `update_community_incremental(node, community, summary)`.
2.  **Update `graphiti.py`:**
    *   In `add_episode`, replace the parallel `update_community` loop with the new logic.
3.  **Backfill:**
    *   Provide a script to run Full Initialization for existing graphs to "seed" the communities for the incremental system to take over.
