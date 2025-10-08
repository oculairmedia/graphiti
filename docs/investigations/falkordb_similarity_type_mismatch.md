## FalkorDB Similarity Search Failure (Rust service)

### Problem summary
- Error when similarity search is enabled in the Rust search microservice:
  Type: mismatch: expected Null or Vectorf32 but was List
- Full‑text search works. Embeddings exist in DB. Ollama returns 1024‑d vectors. Cypher looks syntactically correct.

### Architecture (relevant parts)
- Rust service builds Cypher and queries FalkorDB via Redis GRAPH.QUERY
- Python Graphiti core writes nodes/edges and also performs similar queries (works in direct tests)

## What I inspected
- Rust query construction used for similarity search on nodes and edges
- Python write paths that persist embeddings to FalkorDB
- Python query helpers for FalkorDB vector similarity

### Rust service: current similarity queries
- Nodes: uses name_embedding and casts query to Vectorf32 via vecf32([...])
<augment_code_snippet path="graphiti-search-rs/src/falkor/client.rs" mode="EXCERPT">
````rust
WITH n, (2 - vec.cosineDistance(n.name_embedding,
          vecf32([<embedding_str>])))/2 AS score
````
</augment_code_snippet>

- Edges: uses fact_embedding and casts query to Vectorf32 via vecf32([...])
<augment_code_snippet path="graphiti-search-rs/src/falkor/client.rs" mode="EXCERPT">
````rust
WITH a, r, b, (2 - vec.cosineDistance(r.fact_embedding,
          vecf32([<embedding_str>])))/2 AS score
````
</augment_code_snippet>

Notes
- The Rust code inlines the numeric list and relies on vecf32([...]) to make a Vectorf32 for the query vector.
- It expects the stored property (n.name_embedding or r.fact_embedding) to already be of type Vectorf32.

### Python write paths (Graphiti core)
- All primary save queries explicitly wrap embeddings with vecf32(...) when writing to FalkorDB
<augment_code_snippet path="graphiti_core/models/nodes/node_db_queries.py" mode="EXCERPT">
````python
SET n.name_embedding = vecf32($entity_data.name_embedding)
````
</augment_code_snippet>
<augment_code_snippet path="graphiti_core/models/edges/edge_db_queries.py" mode="EXCERPT">
````python
SET r.fact_embedding = vecf32($edge_data.fact_embedding)
````
</augment_code_snippet>
<augment_code_snippet path="graphiti_core/graph_queries.py" mode="EXCERPT">
````python
SET n.name_embedding = vecf32(node.name_embedding)
````
</augment_code_snippet>

- One utility script assigns node embeddings without vecf32 (likely for ad‑hoc updates)
<augment_code_snippet path="batch_generate_embeddings.py" mode="EXCERPT">
````python
SET n.name_embedding = $embedding
````
</augment_code_snippet>

### Python similarity queries (for reference)
- Helper uses Falkor syntax that casts the query vector with vecf32($param)
<augment_code_snippet path="graphiti_core/graph_queries.py" mode="EXCERPT">
````python
(2 - vec.cosineDistance(vec1, vecf32(vec2)))/2
````
</augment_code_snippet>

## Analysis and hypothesis
- The error message comes from FalkorDB’s vector function receiving a List where a Vectorf32 is required.
- In our Rust queries, the right‑hand argument is "vecf32([..])" (correct) so the only remaining source of a List is the stored property itself.
- Conclusion: some records’ r.fact_embedding (edges) or n.name_embedding (nodes) are stored as a plain List[] instead of Vectorf32. This can happen if:
  - Historical data was inserted before we added vecf32(...) in write queries, OR
  - Ad‑hoc maintenance scripts updated embeddings without vecf32 (e.g., batch_generate_embeddings.py for nodes; a similar path could exist for edges), OR
  - Mixed data from earlier runs (different dimensions or types) remained.

This exactly matches the error text: "expected Null or Vectorf32 but was List" — Falkor accepted the record but the runtime vector function rejects List.

## What already works and what fails in code
- Node saves and Edge saves in Graphiti core now coerce to Vectorf32 using vecf32(...). New data should be okay.
- Rust queries assume DB properties are typed Vectorf32; they do not cast DB properties on read.
- If any legacy rows have List‑typed embeddings, the Rust similarity queries will fail at evaluation time.

## Reproduction/verification steps
Run these in redis-cli against your graph (adjust graph name):

1) Inspect an example edge embedding to see its textual form
- Vectorf32 appears like "<0.1, 0.2, ...>"
- List appears like "[0.1, 0.2, ...]"

Command:
GRAPH.QUERY graphiti_migration "MATCH ()-[r:RELATES_TO]->() WHERE r.fact_embedding IS NOT NULL RETURN r.fact_embedding LIMIT 3"

2) Count how many are vectors vs lists (if Falkor supports type())
GRAPH.QUERY graphiti_migration "MATCH ()-[r:RELATES_TO]->() WHERE r.fact_embedding IS NOT NULL WITH r, type(r.fact_embedding) AS t RETURN t, count(*) ORDER BY count(*) DESC"

If type() is not available, you can brute‑force convert a small sample:
GRAPH.QUERY graphiti_migration "MATCH ()-[r:RELATES_TO]->() WHERE r.fact_embedding IS NOT NULL WITH r, toString(r.fact_embedding) AS s RETURN substring(s,0,1) AS first, count(*)"
- first = "<" likely indicates Vectorf32; "[" indicates List

3) Also quickly spot check nodes
GRAPH.QUERY graphiti_migration "MATCH (n:Entity) WHERE n.name_embedding IS NOT NULL RETURN n.name_embedding LIMIT 3"

## Recommended fixes

A) One‑time data migration to coerce existing List embeddings to Vectorf32
- For edges:
GRAPH.QUERY graphiti_migration "MATCH ()-[r:RELATES_TO]->() WHERE r.fact_embedding IS NOT NULL SET r.fact_embedding = vecf32(r.fact_embedding) RETURN count(r)"

- For nodes (if needed):
GRAPH.QUERY graphiti_migration "MATCH (n:Entity) WHERE n.name_embedding IS NOT NULL SET n.name_embedding = vecf32(n.name_embedding) RETURN count(n)"

Notes:
- If some properties are already Vectorf32, Falkor may either no‑op or throw on double casting; if it errors, run the SET inside a filtered MATCH that only includes rows with list‑like values (use the substring heuristic or a temporary batch script).

B) Keep all write paths casting to Vectorf32
- We already do this in core save queries; avoid using update scripts that assign lists directly. If you need batch updates, mirror the vecf32(...) wrappers.

C) Optionally harden the Rust queries (defensive casting)
- If you want the query to succeed even in presence of a few legacy list rows, you can cast the stored property on read. However, double‑casting a Vectorf32 can be unsafe. If Falkor has a safe cast or predicate (e.g., vec.isVector(x)), prefer:
  (2 - vec.cosineDistance(
     CASE WHEN predicate_indicates_list THEN vecf32(r.fact_embedding) ELSE r.fact_embedding END,
     vecf32([...])
  ))/2 AS score
- Without a reliable predicate, prefer the data migration route (A) which keeps queries clean and fast.

## Additional observations
- There was an earlier variant of the Rust node similarity using vec.cosine_similarity(n.embedding, [...]) and a different property name; the current code uses name_embedding plus cosineDistance and appears correct.
- Python tests in test_direct_query.py demonstrate vecf32($search_vector) works with FalkorDB parameter binding.
- Ensure dimensions match the underlying model (Ollama mxbai-embed-large = 1024); mixed dimensions would produce a different error (dimension mismatch), so that’s not the current issue.

## Proposed next steps
1) Run the verification queries above to confirm presence of List‑typed embeddings (especially on edges).
2) If found, run the one‑time migration SET ... = vecf32(...) (edges first), and re‑test the Rust similarity search.
3) Remove or fix any scripts that set embeddings without vecf32 (e.g., update batch_generate_embeddings.py to use vecf32 if you intend to keep it for FalkorDB).
4) If errors persist, capture the exact failing row by limiting and adding RETURN types to pinpoint which side is List.

