# GraphRAG vs. Graphiti: Architectural Alignment & Implementation Plan

## 1. Concept Mapping: GraphRAG -> Graphiti

The Microsoft GraphRAG model aligns well with Graphiti's ambitions, but Graphiti implements it uniquely due to its temporal focus.

| GraphRAG Concept | Graphiti Implementation | Alignment |
| :--- | :--- | :--- |
| **Indexing Pipeline** | `add_episode` -> `extract_nodes` -> `persist` | ✅ **Aligned**. Graphiti does this natively. |
| **Community Detection** | `build_communities` (Leiden/Louvain) | ✅ **Aligned**. Graphiti uses LLM summarization. |
| **Community Summaries** | `CommunityNode.summary` | ✅ **Aligned**. Graphiti stores summaries on the `CommunityNode`. |
| **Global Search** | *Missing* (The "Synthesis" Step) | ❌ **Gap**. Graphiti retrieves communities but lacks synthesis logic. |
| **Local Search** | `search()` (Vector + Rerank) | ✅ **Aligned**. This is Graphiti's core strength. |
| **DRIFT Search** | `NodeDistance` Reranker | ⚠️ **Partial**. Graphiti finds shortest paths, but "DRIFT" is more iterative. |

## 2. Implementation Plan: "GraphRAG-Lite" (Non-Breaking)

We can implement the core value of GraphRAG ("Global Search") by adding a new method to the `Graphiti` class without altering existing interfaces.

### A. Add `global_search` to `Graphiti` class
This method retrieves high-level `CommunitySummaries` and asks the LLM to synthesize them into a coherent answer. This answers questions like "What are the main themes?" without traversing granular edges.

```python
# graphiti_core/graphiti.py

    async def global_search(
        self,
        query: str,
        group_ids: list[str] | None = None,
        limit: int = 20,
    ) -> str:
        """
        GraphRAG-style Global Search.
        Retrieves high-level Community Summaries and synthesizes an answer.
        Does NOT traverse specific edges; focuses on the "Big Picture".
        """
        # 1. Retrieve relevant communities (uses existing search logic)
        results = await search(
            self.clients,
            query=query,
            group_ids=group_ids,
            config=SearchConfig(
                # Only search communities
                community_config=CommunitySearchConfig(limit=limit),
                edge_config=None,
                node_config=None,
                episode_config=None
            ),
            search_filter=SearchFilters(),
        )
        
        if not results.communities:
            return "No relevant information found."

        # 2. Prepare Context from Summaries
        context = "\n\n".join([
            f"Community '{c.name}': {c.summary}" 
            for c in results.communities
        ])

        # 3. Synthesize (The GraphRAG "Map-Reduce" step)
        prompt = f"""
        Based on the following community summaries, answer the query: '{query}'
        
        Context:
        {context}
        
        Synthesized Answer:
        """
        
        # Use simple generation (assumes LLMClient has this method or similar)
        response = await self.llm_client.generate_response(prompt)
        return response
```

### B. Upgrade `add_episode` (Silent Fix)
To ensure existing integrations benefit from the DSPy pipeline without code changes, update the synchronous `add_episode` method to respect the `use_dspy` flag initialized in the constructor.

```python
# graphiti_core/graphiti.py

    async def add_episode(self, ...):
        # ... validation logic ...

        # Use DSPy extraction if enabled
        if self.use_dspy:
            # Reuses the logic from add_episode_resilient
            extracted_nodes = await self._extract_nodes_dspy(
                episode, previous_episodes, entity_types
            )
        else:
            # Fallback to legacy Jinja2 extraction
            extracted_nodes = await extract_nodes(
                self.clients, episode, previous_episodes, entity_types, excluded_entity_types
            )
            
        # ... resolution and persistence logic ...
```

## 3. The "DRIFT" Opportunity (Connective Reasoning)

GraphRAG's "DRIFT" search follows semantic threads.
*   *Query:* "How does the weather affect deployment?"
*   *Process:* Weather -> Server Room -> Cooling -> Failure -> Deployment.

**Recommendation:** Enhance `search()` to support **Multi-Hop Retrieval** by returning paths, not just neighbors. This can be added as a new `search_paths` method later.

## 4. Strategic Plan

1.  **Don't rebuild GraphRAG.** Microsoft's library is expensive and batch-oriented.
2.  **Focus on Temporal Global Search.**
    *   *GraphRAG:* "What are the themes?"
    *   *Graphiti:* "How have the themes *changed* since last week?"
    
    **Implementation:**
    Fetch `CommunityNodes` valid at `T1`. Fetch `CommunityNodes` valid at `T2`. Compare Summaries.

## Conclusion
Graphiti already has the *data structures* (Communities, Summaries) to do GraphRAG. It just lacks the *query patterns* (Global Synthesis). We can unlock "GraphRAG features" simply by adding the `global_search` helper function to the Client.

```