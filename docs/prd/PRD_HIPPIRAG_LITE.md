# Product Requirement Document (PRD): Graphiti "HippoRAG-Lite" Evaluation

## 1. Executive Summary
**Objective:** Evaluate the effectiveness of "Spreading Activation" (a simplified version of Personalized PageRank) for improving retrieval accuracy in Graphiti.
**Problem:** Current graph RAG systems struggle with "multi-hop" questions where the answer lies 2-3 connections away from the entities mentioned in the query.
**Solution:** Implement a mechanism where "Activation Energy" flows from retrieved entities to their neighbors in FalkorDB, surfacing relevant context without expensive LLM reasoning loops.
**Goal:** Verify this approach in isolation before integrating it into the core Rust/Python codebase.

## 2. Technical Strategy: "Spreading Activation" on FalkorDB
Since FalkorDB's native `algo.pageRank` does not support a *personalization vector* (query-biased restart), we will simulate it using **Weighted Breadth-First Search (BFS)** via Cypher.

### The Algorithm (Simplified PPR)
1.  **Vector Activation (t=0):** Identify "Seed Nodes" using Vector Search.
    *   $S_{seed} = \text{VectorSimilarity}(Query, Node)$
2.  **Propagation (t=1):** Spread score to immediate neighbors.
    *   $S_{neighbor} = S_{seed} \times \text{decay\_factor} \times W_{edge}$
3.  **Aggregation:** Sum scores if a node is reached by multiple paths.

### Why this works
This mimics the "Associative Memory" of the human brain (HippoRAG's core thesis). If you activate "Project X", you naturally activate "Project X's Manager" slightly less, and "Project X's Deadline" slightly less.

## 3. Implementation Plan

### Step 1: Setup & Data Ingestion
*   **Dataset:** Use a small, controlled dataset where ground truth is obvious.
    *   *Theme:* "The Office" (TV Show).
    *   *Why:* Rich relationships (Reports To, Dates, Pranks, Sales) that require multi-hop reasoning.
    *   *Example Query:* "Who is the manager of the person who dates the receptionist?" (Requires: Receptionist -> Pam -> Dates -> Jim -> Manager -> Michael).
*   **Schema:**
    *   `Node`: `Person`, `Role`, `Department`, `Event`.
    *   `Edge`: `REPORTS_TO`, `DATES`, `WORKS_IN`, `PRANKED`.
    *   `Properties`: `embedding` (768d vector), `name`, `summary`.

### Step 2: Vector Indexing
*   Use `falkordb-py`.
*   Create a vector index on `Node.embedding`.
*   Generate dummy embeddings (or use a real local model like `all-MiniLM-L6-v2`) for nodes.

### Step 3: The "Spreading Activation" Query
This is the core deliverable. We will construct a Cypher query that performs the propagation.

**Draft Cypher Logic:**
```cypher
// 1. Find Seeds (Vector Search)
CALL db.idx.vector.queryNodes('Person', 'embedding', $query_embedding)
YIELD node AS seed, score AS similarity
WHERE similarity > 0.7

// 2. Propagate (Variable Length Path)
// Find neighbors up to 2 hops away
MATCH (seed)-[e*1..2]-(target)

// 3. Calculate "Energy"
// Simple decay model: Score = SeedScore * (0.5 ^ hop_distance)
WITH target, max(similarity * (0.5 ^ length(e))) AS activation_score

// 4. Return Top Activated Nodes
RETURN target.name, activation_score
ORDER BY activation_score DESC
LIMIT 5
```

### Step 4: Evaluation Script (`test_hipporag.py`)
*   **Inputs:** A list of 5 multi-hop questions.
*   **Process:**
    1.  Run standard Vector Search (Baseline).
    2.  Run "Spreading Activation" (HippoRAG-lite).
    3.  Compare results: Did the Spreading Activation find the answer when Vector Search failed?

## 4. Requirements
*   **Environment:**
    *   Python 3.10+
    *   `falkordb` python client
    *   `sentence-transformers` (for generating embeddings)
    *   Docker (to run FalkorDB)

## 5. Success Metrics
*   **Multi-hop Recall:** The system retrieves the correct "Answer Node" for >3 of the 5 test questions.
*   **Latency:** The "Spreading Activation" query returns in < 200ms.

## 6. Future Integration (Graphiti)
If successful, this logic will be ported to `graphiti-core` in Rust, replacing the current "RRF" (Reciprocal Rank Fusion) reranking step with this graph-aware scoring.

## 7. The "Graphiti Fusion" Strategy (Hybrid)
**Concept:** Combine Spreading Activation (Graph) + RRF Reranking (Vector).

Reranking (Cross-Encoder) is excellent at filtering out irrelevant *text*, but it can only rerank *what it is given*. If Vector Search misses the "Answer Node" because it's semantically distant (though graphically close), the Reranker never sees it.

**The Pipeline:**
1.  **Recall Phase (Broaden the Net):**
    *   Run **Vector Search** to find "Seed Nodes" (Top 5).
    *   Run **Spreading Activation** to find "Neighbor Nodes" (Top 10 neighbors of seeds).
    *   *Result:* A Candidate Set of ~15 nodes (5 direct, 10 inferred).
2.  **Rerank Phase (Precision):**
    *   Pass all 15 candidates to the **Reranker** (Cross-Encoder).
    *   The Reranker decides: "Is this 'Neighbor Node' actually relevant to the query?"

**Why this wins:**
*   **Spreading Activation** solves the *Recall* problem (finding the hidden answer).
*   **Reranking** solves the *Precision* problem (filtering out the noise introduced by spreading).
*   **Speed:** Both steps are fast enough (< 500ms total) for real-time chat.