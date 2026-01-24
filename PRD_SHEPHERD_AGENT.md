# Product Requirement Document (PRD): Shepherd Agent (Conflict Resolution System)

## 1. Executive Summary
**Objective:** Implement a "Shepherd Agent" (Background Conflict Resolver) to actively detect and resolve contradictions in the Graphiti knowledge graph.
**Problem:** Graphiti currently operates as an append-only system. Conflicting facts (e.g., "User is in New York" vs "User is in London") coexist, leading to retrieval noise and hallucinations.
**Solution:** A scheduled agent that scans the graph for semantic conflicts, uses an LLM to adjudicate the truth based on recency and confidence, and marks incorrect edges as invalid (`invalid_at=NOW`).
**Metaphor:** The "Shepherd" tends the flock (graph), culling sick sheep (bad facts) so the herd remains healthy.

## 2. Technical Architecture

### A. The "Shepherd" Workflow
1.  **Detection (The Nose):** Identify potentially conflicting edges.
    *   *Strategy:* Cluster edges by `Source` + `Relation` (e.g., `(User)-[LOCATION]->?`).
    *   *Heuristic:* If `(User)-[LOCATION]->(A)` and `(User)-[LOCATION]->(B)` exist and are both VALID, this is a potential conflict (unless the user is quantum).
2.  **Adjudication (The Brain):** Ask an LLM to resolve the conflict.
    *   *Input:* Conflicting Edges + Metadata (Creation Date, Confidence Score, Source Episode).
    *   *Prompt:* "Given these two facts, are they contradictory? If so, which one is current?"
3.  **Resolution (The Staff):** Update the graph.
    *   *Action:* Set `invalid_at` on the loser. Create a `(Loser)-[REPLACED_BY]->(Winner)` edge for audit trails.

### B. Conflict Patterns
| Pattern | Example | Logic |
| :--- | :--- | :--- |
| **Functional Property** | `(User)-[CURRENT_CITY]->(A)` vs `(User)-[CURRENT_CITY]->(B)` | **Mutually Exclusive.** Last write wins (usually). |
| **State Change** | `(Task)-[STATUS]->(In Progress)` vs `(Task)-[STATUS]->(Done)` | **Progression.** "Done" supersedes "In Progress". |
| **Correction** | `(User)-[NAME]->(Jon)` vs `(User)-[NAME]->(John)` | **Correction.** "John" supersedes "Jon" if explicitly corrected. |

## 3. Implementation Plan

### Phase 1: The `Shepherd` Service (Python)
We will create a standalone service (or a module in `graphiti_core`) that runs periodically.

**Component 1: `ConflictDetector`**
*   Uses FalkorDB queries to find nodes with high degree of similar edges.
*   *Query:* `MATCH (s)-[r1:LOCATION]->(t1), (s)-[r2:LOCATION]->(t2) WHERE id(r1) < id(r2) AND r1.invalid_at IS NULL AND r2.invalid_at IS NULL RETURN s, r1, r2`

**Component 2: `ConflictResolver` (LLM)**
*   Accepts a list of `ConflictCandidates`.
*   Uses a specialized prompt (`resolve_conflict`) to determine the winner.

**Component 3: `GraphGardener` (Write Back)**
*   Executes the `SET edge.invalid_at = $now` operations.

### Phase 2: Integration with `add_episode`
*   Instead of running purely on a schedule, trigger the Shepherd for specific *Entities* mentioned in the new episode.
*   "While we're here updating the 'User' node, let's check if their location creates a conflict."

## 4. Proposed API
```python
class ShepherdAgent:
    async def scan_conflicts(self, group_id: str):
        """Scans the graph for heuristic conflicts."""
        
    async def resolve_conflicts(self, conflicts: list[Conflict]):
        """Calls LLM to adjudicate."""
        
    async def prune_graph(self, resolutions: list[Resolution]):
        """Applies invalid_at timestamps."""
```

## 5. Success Metrics
*   **Graph Hygiene:** Reduction in active conflicting edges for single-value predicates (like `CURRENT_CITY`, `JOB_TITLE`).
*   **Retrieval Precision:** Search results no longer return contradicting facts.
*   **Auditability:** Every "deletion" is actually a soft-delete (temporal invalidation), preserving history.

## 6. Risks
*   **Over-pruning:** The Shepherd might kill valid multi-value facts (e.g., "User likes Pizza" vs "User likes Sushi" - both are true).
    *   *Mitigation:* The LLM prompt must explicitly allow "Both are true" as an output.
*   **Cost:** LLM calls for every pair of edges is expensive.
    *   *Mitigation:* Strict heuristics. Only check specific edge types (e.g., `STATUS`, `LOCATION`, `ROLE`) defined in a config.
