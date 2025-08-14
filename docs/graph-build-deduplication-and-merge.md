# Graph Build, Deduplication, and Merge Design

This document summarizes how Graphiti builds the knowledge graph today, how deduplication works, where merging currently does not happen, and proposes safe improvements to preserve connections and centrality.

## High-level Pipeline

Single episode (graphiti_core/graphiti.py → add_episode):

1. Gather context
   - Retrieve previous episodes: `retrieve_episodes`
   - Ensure indices/constraints exist: `build_indices_and_constraints`
2. Extraction
   - Nodes: `extract_nodes`
   - Edges: `extract_edges`
3. Resolve & dedupe nodes
   - Resolve new nodes to existing ones (exact/LLM): `resolve_extracted_nodes`
   - Outputs: `resolved_nodes`, `uuid_map` (new→canonical), `node_duplicates`
   - Build duplicate edges: `build_duplicate_of_edges` → `IS_DUPLICATE_OF`
4. Resolve edges
   - Rewire pointers to canonical UUIDs: `resolve_edge_pointers`
   - Validate/classify: `resolve_extracted_edges` → `resolved_edges`, `invalidated_edges`
5. Episodic edges
   - Episode membership: `build_episodic_edges`
6. Persist
   - Save nodes, episodic edges, entity edges; generate embeddings as needed

Bulk episodes (graphiti_core/graphiti.py → add_episodes_bulk; graphiti_core/utils/bulk_utils.py):

1. Extract in parallel: `extract_nodes_and_edges_bulk`
2. Node dedupe across batch: `dedupe_nodes_bulk`
   - Embeddings → similarity → `duplicate_pairs`
   - `compress_uuid_map` → `compressed_map`
   - Remap all nodes to canonical per episode
3. Edge pointer resolution and edge dedupe
   - `resolve_edge_pointers`
   - `dedupe_edges_bulk` (embed + similarity)
4. Hydration & persistence
   - `extract_attributes_from_nodes`
   - `resolve_extracted_edges` per-episode
   - `add_nodes_and_edges_bulk` persists

## Key Modules & Functions

- Orchestration: `graphiti_core/graphiti.py`
- Node resolution & attributes:
  - `utils/maintenance/node_operations.py` → `resolve_extracted_nodes`, `extract_attributes_from_nodes`, `dedupe_node_list`
- Edge ops:
  - `utils/maintenance/edge_operations.py` → `build_duplicate_of_edges`, `resolve_extracted_edge(s)`
- Bulk helpers:
  - `utils/bulk_utils.py` → `extract_nodes_and_edges_bulk`, `dedupe_nodes_bulk`, `dedupe_edges_bulk`, `resolve_edge_pointers`, `add_nodes_and_edges_bulk`
- Communities:
  - `utils/maintenance/community_operations.py` → `build_communities`, `remove_communities`, `update_community`

## What Deduplication Does Today

- Single-episode path:
  - `resolve_extracted_nodes` chooses canonical nodes and returns `uuid_map`.
  - New edges are rewired to canonical nodes (`resolve_edge_pointers`).
  - `IS_DUPLICATE_OF` edges are created to record duplicates (`build_duplicate_of_edges`).
  - Important: There is no physical merge of pre-existing duplicate nodes in the DB here. Older dupes keep their historical edges.

- Bulk path:
  - In-memory remapping via `compressed_map` ensures only canonical node UUIDs are written for this batch.
  - Again, this avoids creating new dupes but does not merge previously persisted duplicates and their connections.

Implication:
- Centrality and connectivity remain split across historical duplicates. Canonical nodes accrue new edges; prior edges on non-canonical duplicates remain there. Unless analytics purposely collapse along `IS_DUPLICATE_OF`, centrality can appear “lost.”

## Centrality and Communities

- Community operations exist, but unless node merges occur or analytics treat `IS_DUPLICATE_OF` as an equivalence relation, metrics may not reflect the consolidated entity.

## Gaps and Opportunities

1. True merge operation (maintenance)
   - `merge_node_into(canonical_uuid, duplicate_uuid)` should:
     - Rewire all incoming/outgoing edges from duplicate → canonical
     - Merge attributes with a conflict policy (e.g., prefer canonical, keep provenance)
     - Optionally tombstone duplicate with `REDIRECTS_TO` or delete it
     - Maintain `IS_DUPLICATE_OF` for audit/history

2. Trigger merges at the right time
   - Single-episode: when `node_duplicates` are found, enqueue merges instead of only adding `IS_DUPLICATE_OF`.
   - Bulk: after `compressed_map` is built, produce merge tasks for any persisted duplicates.

3. Analytics over equivalence classes
   - Short-term, compute centrality/communities over a collapsed view that treats `IS_DUPLICATE_OF` clusters as a single supernode.
   - Long-term, run background merges and recompute metrics post-merge.

4. Safety and observability
   - Make merges idempotent and transactional.
   - Keep audit logs (episode UUID, decision rationale, before/after node IDs).
   - Provide dry-run reports of proposed merges.

## Proposed Merge Operation (Sketch)

Pseudo-steps (Neo4j-style Cypher shown as conceptual guide):

```cypher
// 1) Validate nodes
MATCH (c:Entity {uuid: $canonical}), (d:Entity {uuid: $duplicate})
WHERE c.uuid <> d.uuid
WITH c, d

// 2) Rewire incoming edges
CALL {
  WITH c, d
  MATCH (s)-[r]->(d)
  WHERE type(r) <> 'IS_DUPLICATE_OF'
  WITH s, r, c
  MERGE (s)-[r2:REL {name: r.name}]->(c)
  SET r2 += properties(r)
  DELETE r
}

// 3) Rewire outgoing edges
CALL {
  WITH c, d
  MATCH (d)-[r]->(t)
  WHERE type(r) <> 'IS_DUPLICATE_OF'
  WITH r, t, c
  MERGE (c)-[r2:REL {name: r.name}]->(t)
  SET r2 += properties(r)
  DELETE r
}

// 4) Merge attributes
SET c += apoc.map.clean(properties(d), ['uuid'], false)

// 5) Preserve audit edge
MERGE (d)-[:IS_DUPLICATE_OF]->(c)

// 6) Tombstone or delete duplicate
SET d:Duplicate, d.redirects_to = c.uuid, d.deleted_at = datetime()
// or: DETACH DELETE d
```

Notes:
- Use specific labels/relationship types present in the schema.
- Consider uniqueness constraints to prevent duplicate parallel edges.
- For property merging, preserve provenance or append arrays as appropriate.

## Where to Hook in Code

- Single-episode: `graphiti_core/graphiti.py`
  - After `node_duplicates` and before persisting edges.
- Bulk: `graphiti_core/utils/bulk_utils.py`
  - After `compressed_map` is computed, schedule merges for existing persisted duplicates.
- Implement helpers in `graphiti_core/utils/maintenance/node_operations.py` and/or a new `merge_operations.py`.

## Incremental Rollout Plan

Phase 1 (low risk): Collapsed analytics
- Provide query helpers/utilities to compute metrics over `IS_DUPLICATE_OF` equivalence classes without changing stored topology.
- Benefits: immediate improvement in centrality/communities with no writes.

Phase 2: Background merges
- Add `merge_node_into` + batch maintenance job.
- Idempotent, transactional, with audit logs and dry-run mode.
- Rebuild impacted communities/metrics after merges.

Phase 3: Real-time merges (optional)
- During ingestion, queue merges when high-confidence duplicates are identified.
- Use thresholds, safeguards, and operator review for low-confidence cases.

## Telemetry and Monitoring

- Emit events: merge initiated/completed, edges moved count, properties merged, errors.
- Dashboards for duplicate clusters, pending merges, merge outcomes.

## Open Questions

- Conflict resolution for attributes: which fields to union vs. prefer canonical?
- Edge type semantics: any that should not be transferred?
- Confidence thresholds for auto-merge vs. manual review?

## References (Direct Code Sections)

- graphiti_core/graphiti.py
  - add_episode: orchestrates single-episode flow (extract_nodes, resolve_extracted_nodes, extract_edges, resolve_edge_pointers, resolve_extracted_edges, build_duplicate_of_edges, build_episodic_edges, persistence)
  - add_episodes_bulk: orchestrates batch flow (extract_nodes_and_edges_bulk, dedupe_nodes_bulk, resolve_edge_pointers, dedupe_edges_bulk, resolve_extracted_edges, add_nodes_and_edges_bulk)

- graphiti_core/utils/maintenance/edge_operations.py
  - build_duplicate_of_edges(episode, created_at, duplicate_nodes)
  - build_episodic_edges(nodes, episode_uuid, created_at)
  - extract_edges(...)
  - resolve_extracted_edge(...), resolve_extracted_edges(...)

- graphiti_core/utils/maintenance/node_operations.py
  - resolve_extracted_nodes(clients, extracted_nodes, episode, previous_episodes, entity_types, existing_nodes_override)
  - extract_attributes_from_nodes(clients, nodes, episode, previous_episodes, entity_types)
  - dedupe_node_list(llm_client, nodes)
  - filter_existing_duplicate_of_edges(driver, node_duplicates)

- graphiti_core/utils/bulk_utils.py
  - extract_nodes_and_edges_bulk(clients, episode_tuples, edge_type_map, entity_types, excluded_entity_types, edge_types)
  - dedupe_nodes_bulk(clients, extracted_nodes, episode_tuples, entity_types) → compress_uuid_map
  - dedupe_edges_bulk(clients, extracted_edges, episode_tuples, entities, edge_types, edge_type_map)
  - resolve_edge_pointers(edges, uuid_map)
  - add_nodes_and_edges_bulk(driver, episodes, episodic_edges, nodes, entity_edges, embedder)
  - create_entity_node_embeddings(embedder, nodes)
  - create_entity_edge_embeddings(embedder, edges)

- graphiti_core/utils/maintenance/graph_data_operations.py
  - build_indices_and_constraints(...)
  - retrieve_episodes(...), EPISODE_WINDOW_LEN

- server/graph_service/zep_graphiti.py
  - initialize_graphiti(settings): constructs ZepGraphiti with LLM and embedder clients

- graphiti_core/telemetry.py
  - capture_event (if you want to instrument merges)

Proposed new module locations for merge logic:

- graphiti_core/utils/maintenance/merge_operations.py (new)
  - merge_node_into(canonical_uuid, duplicate_uuid)
  - optional: batch_merge_duplicates(pairs, dry_run=False)

Integration hooks:

- graphiti_core/graphiti.py
  - add_episode: after node_duplicates are computed
  - add_episodes_bulk: after compressed_map is computed

---

## Important thresholds & helper signatures

- Node dedupe threshold
  - File: graphiti_core/utils/bulk_utils.py
  - Function: dedupe_nodes_bulk
  - Detail: min_score = 0.8 (embedding similarity threshold for node duplicate candidates)

- Edge dedupe threshold
  - File: graphiti_core/utils/bulk_utils.py
  - Function: dedupe_edges_bulk
  - Detail: min_score = 0.6 (embedding similarity threshold for edge duplicate candidates)

- Edge invalidation candidate threshold
  - File: graphiti_core/utils/maintenance/edge_operations.py
  - Function: resolve_extracted_edges
  - Detail: get_edge_invalidation_candidates(..., threshold=0.2)

- UUID mapping utilities
  - File: graphiti_core/utils/bulk_utils.py
  - Function: compress_uuid_map(duplicate_pairs) → dict[str, str]
    - Uses Union-Find to map each UUID to the canonical representative in its duplicate set
  - Function: resolve_edge_pointers(edges, uuid_map)
    - Rewrites edge.source_node_uuid/target_node_uuid using uuid_map

- Duplicate-of filtering
  - File: graphiti_core/utils/maintenance/edge_operations.py
  - Function: filter_existing_duplicate_of_edges(driver, duplicates_node_tuples)
    - Prevents inserting duplicate IS_DUPLICATE_OF edges already present in the graph

- Embedding helpers (used before dedupe)
  - File: graphiti_core/utils/bulk_utils.py (usage)
  - Functions: create_entity_node_embeddings(embedder, nodes), create_entity_edge_embeddings(embedder, edges)

## Code excerpts

Node dedupe threshold (0.8):
<augment_code_snippet path="graphiti_core/utils/bulk_utils.py" mode="EXCERPT">
````python
async def dedupe_nodes_bulk(...):
    embedder = clients.embedder
    min_score = 0.8
    # generate embeddings
    await semaphore_gather(
````
</augment_code_snippet>

Edge dedupe threshold (0.6):
<augment_code_snippet path="graphiti_core/utils/bulk_utils.py" mode="EXCERPT">
````python
async def dedupe_edges_bulk(...):
    embedder = clients.embedder
    min_score = 0.6
    # generate embeddings
    await semaphore_gather(
````
</augment_code_snippet>

Compress UUID map (Union-Find):
<augment_code_snippet path="graphiti_core/utils/bulk_utils.py" mode="EXCERPT">
````python
def compress_uuid_map(duplicate_pairs: list[tuple[str, str]]) -> dict[str, str]:
    """
    returns: dict mapping each id -> lexicographically smallest id
    """
    uf = UnionFind(all_uuids)
````
</augment_code_snippet>

Resolve edge pointers to canonical nodes:
<augment_code_snippet path="graphiti_core/utils/bulk_utils.py" mode="EXCERPT">
````python
def resolve_edge_pointers(edges: list[E], uuid_map: dict[str, str]):
    for edge in edges:
        edge.source_node_uuid = uuid_map.get(source_uuid, source_uuid)
        edge.target_node_uuid = uuid_map.get(target_uuid, target_uuid)
````
</augment_code_snippet>

Filter existing IS_DUPLICATE_OF edges:
<augment_code_snippet path="graphiti_core/utils/maintenance/edge_operations.py" mode="EXCERPT">
````python
async def filter_existing_duplicate_of_edges(driver, duplicates_node_tuples):
    query = """
        UNWIND $duplicate_node_uuids AS duplicate_tuple
        MATCH (n:Entity)-[r:RELATES_TO {name: 'IS_DUPLICATE_OF'}]->(m:Entity)
````
</augment_code_snippet>

Edge invalidation threshold in resolution (0.2):
<augment_code_snippet path="graphiti_core/utils/maintenance/edge_operations.py" mode="EXCERPT">
````python
search_results = await semaphore_gather(
    get_relevant_edges(driver, extracted_edges, SearchFilters()),
    get_edge_invalidation_candidates(driver, extracted_edges, SearchFilters(), 0.2),
)
````
</augment_code_snippet>

This design enables both non-destructive “collapsed view” analytics and safe, auditable physical merges to preserve connections and centrality across deduplicated entities.

