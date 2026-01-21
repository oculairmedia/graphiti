# Product Requirement Document (PRD): FalkorDB Native Graph Optimization

## 1. Executive Summary
**Objective:** Replace the current slow, memory-intensive Python implementation of Community Detection (Label Propagation) with FalkorDB's native, high-performance graph algorithms.
**Problem:** `graphiti_core` currently performs Label Propagation in Python (`community_operations.py`), fetching all edges into memory and iterating. This is $O(N+M)$ in memory and slow for large graphs.
**Solution:** Switch to `CALL algo.labelPropagation()` (CDLP) within FalkorDB.
**Impact:** Orders of magnitude faster community detection, reduced API server memory footprint.

## 2. Technical Analysis

### A. Current Implementation (Python)
*   **File:** `graphiti_core/utils/maintenance/community_operations.py`
*   **Method:** `get_community_clusters` -> `label_propagation`
*   **Logic:**
    1.  `MATCH (n)-[r]-(m) RETURN m.uuid, count(r)` (Expensive fetch)
    2.  In-memory loop updating community IDs until convergence.
    3.  Group nodes by community ID.

### B. Target Implementation (FalkorDB Native)
*   **Algorithm:** Community Detection using Label Propagation (CDLP)
*   **Procedure:** `CALL algo.labelPropagation(config)`
*   **Documentation:** https://docs.falkordb.com/algorithms/CDLP/ (verified via search)
*   **Syntax:**
    ```cypher
    CALL algo.labelPropagation({
        nodeLabels: ['Entity'],  // Optional: restrict to Entity nodes
        relationshipTypes: ['RELATES_TO'] // Optional: restrict to relevant edges
    })
    YIELD node, label
    RETURN label, collect(node.uuid) AS members
    ```

### C. Feasibility Check
*   **Status:** ✅ Confirmed `algo.labelPropagation` exists in FalkorDB.
*   **Constraints:**
    *   The Python code handles `group_id` partitioning manually. FalkorDB's `algo` calls usually run on the *whole* graph projection unless filtered.
    *   **Mitigation:** If we cannot pass `WHERE group_id = $id` to the algo, we might need to rely on the fact that disconnected components (different groups) naturally form separate communities anyway. `algo.labelPropagation` respects graph topology.

## 3. Implementation Plan

### Step 1: Create `native_community_detection.py` (POC)
Create a script to verify `algo.labelPropagation` works on a test graph and returns expected clusters.

```python
# POC Draft
async def test_native_cdlp(client, graph_id):
    # 1. Create a graph with 2 distinct clusters (Group A, Group B)
    # 2. CALL algo.labelPropagation()
    # 3. Assert nodes in Group A have same label, distinct from Group B
```

### Step 2: Refactor `community_operations.py`
Modify `get_community_clusters` to use the native call.

**Old Code:**
```python
# Fetches all neighbors...
projection = ... 
cluster_uuids = label_propagation(projection)
```

**New Code:**
```python
# Native call
query = """
    CALL algo.labelPropagation({
        nodeLabels: ['Entity'],
        relationshipTypes: ['RELATES_TO']
    })
    YIELD node, label
    WITH label, collect(node.uuid) as members
    RETURN members
"""
records, _, _ = await driver.execute_query(query)
return [r['members'] for r in records]
```

### Step 3: Performance Benchmark
Compare the execution time of Python-LPA vs Native-CDLP on a graph with 10,000 nodes.

## 4. Risks & Mitigations
*   **Risk:** `algo.labelPropagation` might overwrite existing node properties if we aren't careful (usually it returns results, but some variants write back).
    *   *Mitigation:* Check if it writes a `community_id` property. If so, ensure it doesn't conflict with our `group_id`.
*   **Risk:** Determinism. LPA is non-deterministic by nature (tie-breaking).
    *   *Mitigation:* Accept that communities might shift slightly between runs. This is acceptable for summarization.

## 5. Success Metrics
*   **Speed:** < 1s for 10k nodes (vs ~10s+ in Python).
*   **Memory:** Near-zero application memory usage (offloaded to DB).
