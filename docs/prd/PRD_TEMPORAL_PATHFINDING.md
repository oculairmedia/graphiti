# Product Requirement Document (PRD): Temporal Pathfinding (Time-Travel Traversal)

## 1. Executive Summary
**Objective:** Implement a graph traversal algorithm that respects the *temporal validity* of edges, enabling queries that reconstruct the state of the graph at a specific point in time or interval.
**Problem:** Standard graph searches return all edges ever created, leading to hallucinations where past facts (e.g., "CEO is Alice") conflict with present facts ("CEO is Bob"), or where causality is violated (retrieving a consequence that happened before the cause).
**Solution:** Implement `search_temporal_path` in FalkorDB (via Cypher) that filters edges based on `valid_at` and `invalid_at` properties during traversal.
**Goal:** Enable "Time-Travel" debugging and audit trails for AI agents.

## 2. Technical Context
Graphiti stores edges with bi-temporal properties:
*   `valid_at` (Datetime, ISO8601 String): When the relationship became true.
*   `invalid_at` (Datetime, ISO8601 String | Null): When the relationship ceased to be true.

### Challenge: FalkorDB Cypher Limitations
FalkorDB's `algo.shortestPath` does not currently support complex edge filtering predicates (like checking if a timestamp falls within an interval) natively in the procedure call.
Therefore, we must use **Variable Length Path Matching** with `WHERE all()` clauses or **Recursive CTEs** (if supported, though likely standard MATCH is safer).

## 3. Implementation Strategy

### A. The Schema (Confirmed)
Edges (`EntityEdge` in `graphiti_core/edges.py`) have:
- `valid_at`: ISO8601 String (from `falkordb_driver.py` conversion)
- `invalid_at`: ISO8601 String (nullable)

### B. The Algorithm: "Temporal Walk"
We define a path $P = (n_0, e_1, n_1, ..., e_k, n_k)$ as **valid at time $t$** if for all edges $e_i$:
1.  $e_i.\text{valid\_at} \le t$
2.  ($e_i.\text{invalid\_at}$ is NULL) OR ($e_i.\text{invalid\_at} > t$)

### C. Cypher Implementation
We will implement this in `graphiti-search-rs` (or Python core if necessary, but Rust is preferred for search services).

**Query Template:**
```cypher
MATCH path = (startNode)-[edge*1..5]->(endNode)
WHERE startNode.uuid = $start_uuid
  AND endNode.uuid = $end_uuid
  AND all(rel IN relationships(path) WHERE 
      (rel.valid_at IS NULL OR rel.valid_at <= $query_time) AND
      (rel.invalid_at IS NULL OR rel.invalid_at > $query_time)
  )
RETURN path
LIMIT 1
```

## 4. Concrete Examples

### Scenario: The CEO Succession
*   **2020-01-01:** Alice becomes CEO of TechCorp.
    *   Edge 1: `(Alice)-[ROLE:CEO {valid_at: "2020-01-01"}]->(TechCorp)`
*   **2022-01-01:** Alice steps down, Bob becomes CEO.
    *   Update Edge 1: `invalid_at = "2022-01-01"`
    *   Edge 2: `(Bob)-[ROLE:CEO {valid_at: "2022-01-01"}]->(TechCorp)`

### Query 1: "Who was CEO in 2021?" ($t = \text{"2021-06-01"}$)
*   **Edge 1 Check:** `valid_at` ("2020") <= "2021" AND `invalid_at` ("2022") > "2021". **PASS**.
*   **Edge 2 Check:** `valid_at` ("2022") <= "2021". **FAIL**.
*   **Result:** Alice.

### Query 2: "Who is CEO now?" ($t = \text{"2025-01-01"}$)
*   **Edge 1 Check:** `invalid_at` ("2022") > "2025". **FAIL**.
*   **Edge 2 Check:** `valid_at` ("2022") <= "2025" AND `invalid_at` (NULL). **PASS**.
*   **Result:** Bob.

## 5. Implementation Plan

### Phase 1: Python Prototype (`search_temporal.py`)
1.  Extend `search_proxy.py` to accept a `valid_at` query parameter.
2.  Implement the Cypher query generation logic.
3.  Add unit tests with the "CEO Succession" scenario.

### Phase 2: Rust Integration (`graphiti-search-rs`)
1.  Add `temporal_mode` to `SearchConfig`.
2.  Modify `bfs.rs` or create `temporal_bfs.rs`.
3.  Inject the `WHERE all(...)` clause into the path finding queries.

## 6. Performance Considerations
*   **String Comparison:** ISO8601 string comparison is lexicographically correct and supported by FalkorDB, but slower than integer comparison.
    *   *Mitigation:* Ensure `valid_at` is indexed if possible, though edge indexing is limited in Redis/Falkor.
*   **Path Explosion:** Variable length paths can explode.
    *   *Mitigation:* Keep max depth low (e.g., 3-4 hops) for temporal queries.

## 7. Success Metrics
*   **Accuracy:** 100% correct retrieval of state in controlled temporal test cases.
*   **Latency:** < 200ms overhead compared to non-temporal search.
