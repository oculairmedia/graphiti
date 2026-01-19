# Learning from Mem0: Graph Traversal Strategy

## Overview
Mem0 and GraphRAG both utilize graph traversal to solve "Multi-Hop Reasoning" problems, but they do it differently. Graphiti can learn from Mem0's "Hybrid & Selective" approach to improve performance and cost.

## 1. The Mem0 Approach: "Vector First, Graph Second"
Mem0 does not blindly traverse the graph for every query. It uses a tiered strategy:
1.  **Vector Search (Level 1):** Find the most relevant *Entities* using semantic similarity (Embeddings).
2.  **Selective Expansion (Level 2):** Only if `enable_graph=True` (or via heuristics), it expands from those entities to find *Relations*.
3.  **Scoring Layer:** It re-ranks the combined results (Vector Hits + Graph Neighbors) based on Recency and Relevance.

**Key Insight:** They treat the Graph as a "Context Augmentation" layer, not the primary search index. This is faster and cheaper than GraphRAG's "Global Clustering" or deep traversal.

## 2. Graphiti's Current State
Graphiti currently has `graphiti-search-rs` which supports:
*   `NodeDistance` (Shortest Path)
*   `RRF` (Reciprocal Rank Fusion of Vector + Keyword)
*   `MMR` (Maximal Marginal Relevance)

However, Graphiti tends to be "All or Nothing". You typically get neighbors or you don't.

## 3. Recommended Implementation: "Entity-Centric Expansion"

We can implement a high-level retrieval strategy in Python (or Rust) that mimics Mem0's logic:

### Algorithm: `hybrid_graph_traversal(query)`

1.  **Step 1: Anchor Identification (Vector)**
    *   Embed `query`.
    *   Search `EntityNodes` using Cosine Similarity.
    *   Keep top $K$ nodes (e.g., Top 5). These are your "Anchors".

2.  **Step 2: 1-Hop Expansion (Graph)**
    *   For each Anchor Node, fetch all connected `EntityEdges`.
    *   *Crucially:* Filter edges by time (valid_at) if temporal context is needed.

3.  **Step 3: Context Assembly**
    *   Context = `[Anchor Nodes]` + `[Neighbor Nodes]` + `[Edge Facts]`
    *   Limit context window by prioritizing:
        1.  Anchor Nodes (Direct hits)
        2.  Recent Edges (Time-aware)
        3.  Strongly Connected Neighbors (Centrality)

### Why this wins?
*   **Cheaper:** You only pay embedding costs for the initial search. Graph traversal is practically free (pointer lookups).
*   **Explainable:** You can say "I retrieved this because it is related to [Entity] which you mentioned."
*   **Temporal:** Graphiti's unique advantage is filtering Step 2 by `valid_at`. Mem0 cannot do this easily.

## 4. Proposed `GraphitiMemory` Wrapper API

To adopt this, we should expose it via the high-level wrapper suggested in the previous report.

```python
class GraphitiMemory:
    def search(self, query: str, date: datetime = now()):
        # 1. Vector Search for Anchors
        anchors = self.graph.search_nodes(query)
        
        # 2. Graph Traversal (1-Hop)
        context = []
        for node in anchors:
            neighbors = node.get_neighbors(valid_at=date)
            context.append(node)
            context.extend(neighbors)
            
        # 3. Rerank / Format
        return format_as_context(context)
```

## Conclusion
Mem0's "Graph Traversal" is actually quite simple: **Search -> Expand**. Graphiti should adopt this pattern as the *default* search behavior for Agents, because Agents usually ask questions about specific entities ("What does *user* like?", "Who is *Alice*?").
