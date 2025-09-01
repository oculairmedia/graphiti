# Embedding Persistence & Restoration: Analysis and Action Plan

Owner: Sync/Platform
Status: Draft (ready for implementation)
Date: 2025-09-01

## Goal
Ensure embeddings persist across restarts and are correctly restored so we do not regenerate them on startup. FalkorDB is a cache layer; Neo4j is the system of record. Restoration should hydrate FalkorDB (and Neo4j during reverse sync) with correctly-typed vector properties.

## Architecture Context
- Source of truth: Neo4j
- Cache layer: FalkorDB
- On restart, FalkorDB is (re)hydrated by the Sync Service
- Workers currently initialize Graphiti with a FalkorDB driver (writes go to Falkor unless otherwise configured)

Key references:
- sync_service/orchestrator/sync_orchestrator.py — drives forward/reverse sync and “disaster recovery”
- sync_service/extractors/* — data extraction from Neo4j/Falkor
- sync_service/loaders/falkordb_loader.py — loads into Falkor (forward sync)
- sync_service/loaders/neo4j_loader.py — loads into Neo4j (reverse sync)
- sync_service/simple_migration.py — “proven” migration used by disaster recovery
- graphiti_core/utils/bulk_utils.py — Graphiti bulk save path; generates embeddings if missing
- graphiti_core/graph_queries.py — provider-specific bulk queries (vecf32 casting)
- graphiti_core/models/nodes/node_db_queries.py — Neo4j node queries (vecf32)
- graphiti_core/models/edges/edge_db_queries.py — Neo4j edge queries (vecf32)
- worker/worker_service.py — initializes Graphiti with FalkorDriver
- regenerate_*_embeddings_*.py — scripts that regenerate embeddings by writing vecf32 to DB

## Current State Analysis

How embeddings are generated and saved (normal writes):
- Graphiti bulk path creates embeddings if missing, then persists them.
  - graphiti_core/utils/bulk_utils.py:
    - EntityNode: generate_name_embedding() if None
    - EntityEdge: generate_embedding() if None
  - graphiti_core/graph_queries.py and node/edge_db_queries.py cast embeddings via vecf32(...).

How restoration works on restart:
- Orchestrator may trigger “disaster recovery” using simple_migration (Neo4j → Falkor) when Falkor is near-empty.
- Normal forward sync uses Neo4jExtractor + FalkorDBLoader; reverse uses FalkorDBExtractor + Neo4jLoader.

Persistence mechanisms and observed gaps:
- simple_migration skips embeddings and large arrays by design (embedding_properties filter; skip_large_arrays=True).
- FalkorDBLoader (forward) builds Cypher strings manually with a generic _safe_value_for_query, which stringifies lists and never casts vecf32.
- Neo4jLoader (reverse) uses SET n += $props; it does not cast vector fields to vecf32.
- Workers write via FalkorDriver (not Neo4j), so embeddings may exist only in Falkor unless reverse sync runs.

Error handling around restoration:
- Orchestrator and loaders log per-batch errors and counts. No special checks for vector typing or presence.

## Root Causes of Embedding Loss/Regeneration
1) Disaster recovery migration drops embeddings
   - sync_service/simple_migration.py intentionally skips known embedding properties and large arrays.
2) Forward sync to FalkorDB serializes arrays incorrectly and doesn’t cast vectors
   - sync_service/loaders/falkordb_loader.py writes properties via string concatenation; arrays become strings; no vecf32 casting.
3) Embeddings not guaranteed in Neo4j (authoritative store)
   - Workers write to FalkorDB; if Neo4j lacks embeddings, rehydration from Neo4j produces no embeddings.
4) Reverse sync to Neo4j does not cast vectors
   - sync_service/loaders/neo4j_loader.py doesn’t set vecf32(...) for embeddings, risking wrong types.
5) Startup path may clear Falkor and reimport without embeddings
   - If auto_recovery triggers, simple_migration runs and ensures vectors are missing post-restore.

## Best Practices (applied to our stack)
- Persist embeddings in the system of record (Neo4j) at write time (or promptly via reverse sync) so restoration can hydrate caches.
- Use parameterized UNWIND queries; avoid literal string building for lists/arrays.
- Cast embeddings to vector types on write (vecf32(...)) in both Neo4j and FalkorDB paths.
- Ensure recovery and normal sync paths are symmetric; never drop embeddings.
- Add post-restore validation (counts and spot checks for vector property types) and retry/backfill only missing embeddings.
- Initialize/create vector indexes as part of restore.

## Solution Overview
Make forward/reverse/DR paths share the same, provider-aware queries that correctly cast vectors and operate on parameters. Ensure embeddings exist in Neo4j at the time of restore.

Core principles:
- Reuse graphiti_core.graph_queries query builders in sync loaders (Falkor/Neo4j) for parity with Graphiti’s bulk save behavior.
- Remove/replace simple_migration’s embedding-skipping logic; either use the same loaders or parameterized queries with vecf32 casting.
- Ensure workers persist embeddings to Neo4j (switch driver or kick off reverse sync shortly after writes).

## Implementation Plan (Actionable Steps)

1) Fix FalkorDBLoader to write vectors correctly (Forward sync: Neo4j → Falkor)
- Replace manual property string-building with provider-aware queries:
  - For entity nodes: use graphiti_core.graph_queries.get_entity_node_save_bulk_query(nodes, 'falkordb') and execute returned queries/params (these set vecf32 for name_embedding when present).
  - For entity edges: use get_entity_edge_save_bulk_query('falkordb') (sets r.fact_embedding = vecf32(...)).
- Ensure episodic nodes/edges either have no embeddings or are treated similarly if applicable (e.g., content_embedding).

2) Fix Neo4jLoader to cast vectors on write (Reverse sync: Falkor → Neo4j)
- Split scalar props from embedding props and do vector casts explicitly:
  - Nodes: SET n += $props; if $props.name_embedding is not null, SET n.name_embedding = vecf32($props.name_embedding).
  - Edges: similar for r.fact_embedding.
- Alternatively, reuse graphiti_core provider-specific queries for Neo4j (ENTITY_NODE_SAVE_BULK, ENTITY_EDGE_SAVE_BULK) to maintain parity.

3) Replace Disaster Recovery path to preserve embeddings
- Prefer using the same Extractor+Loader pipeline (Neo4jExtractor + FalkorDBLoader) instead of simple_migration.
- If simple_migration must remain, remove embedding skipping and move to parameterized UNWIND with vector casting:
  - Do not skip 'name_embedding', 'fact_embedding', 'content_embedding', 'summary_embedding'.
  - Use vecf32(...) on those fields and pass arrays via parameters.

4) Ensure Neo4j has embeddings at write time (or immediately after)
- Option A (preferred): Initialize workers with Neo4j driver (or dual write) so embeddings land in Neo4j as well as Falkor.
- Option B: After Falkor-only writes, enqueue a reverse incremental sync task to persist embeddings into Neo4j with vecf32 casting.

5) Add validation and monitoring
- After any forward/DR sync: count nodes/edges with non-null embeddings in Falkor and compare to Neo4j counts; alert if deltas exceed a threshold.
- Add spot-check queries to verify property type is vector (not string).

6) Indexing
- Confirm/create necessary indices for vector search in Neo4j and FalkorDB after loads.

## Concrete Change Notes (by file)

- sync_service/loaders/falkordb_loader.py
  - Replace _safe_value_for_query-based string composing with parameterized UNWIND.
  - For entity nodes, use graphiti_core.graph_queries.get_entity_node_save_bulk_query(nodes, 'falkordb').
  - For entity edges, use get_entity_edge_save_bulk_query('falkordb').
  - Benefit: vecf32(...) applied; no stringified arrays.

- sync_service/loaders/neo4j_loader.py
  - When writing to Neo4j, cast embeddings:
    - Nodes: if name_embedding present, SET n.name_embedding = vecf32($name_embedding).
    - Edges: if fact_embedding present, SET r.fact_embedding = vecf32($fact_embedding).
  - Or reuse graphiti_core query builders for Neo4j provider (ENTITY_*_SAVE_BULK), aligning with Graphiti behavior.

- sync_service/simple_migration.py
  - Remove skipping of embedding properties and large arrays for embeddings.
  - Convert to parameterized UNWIND; apply vecf32(...) for known embedding fields.
  - Or retire this module in favor of sync_full with fixed FalkorDBLoader.

- worker/worker_service.py
  - Consider switching to Neo4j driver (or dual write) for embeddings persistence at write time.
  - If not feasible, ensure reverse incremental sync runs shortly after writes.

- regenerate_node_embeddings_ollama.py (and related regen scripts)
  - These scripts currently write vecf32(...) correctly; after the fixes, they should become rarely needed (only backfill/repair).

## Validation & Tests

Automated tests:
- Forward sync test: Insert nodes/edges with embeddings into Neo4j; run forward sync; assert Falkor nodes/edges have non-null embeddings and correct vector type.
- Reverse sync test: Insert into Falkor; run reverse sync; assert Neo4j has embeddings set via vecf32 and vector queries succeed.
- DR path test: Trigger auto_recovery; verify embeddings are preserved/rehydrated.

Runtime checks:
- Query counts: number of Entity nodes with name_embedding not null and number of RELATES_TO with fact_embedding not null, in both stores.
- Sample a few records to assert types are vector, not string.

## Rollout Strategy
1) Implement FalkorDBLoader and Neo4jLoader changes; deploy sync service.
2) Disable or refactor simple_migration; use sync_full for DR until migration is parity-compliant.
3) Choose Neo4j persistence approach (Option A or B above) and implement.
4) Add post-sync validators and alerts.
5) Run in staging with a backup; validate counts before/after; then roll to prod.

## Task Checklist (for implementers)
- [ ] FalkorDBLoader: switch to provider-aware bulk queries with vecf32
- [ ] Neo4jLoader: cast embeddings on write (or reuse provider-aware queries)
- [ ] simple_migration: remove embedding skipping; parameterize + vecf32, or retire
- [ ] Worker write path: ensure embeddings persist to Neo4j (direct or via scheduled reverse sync)
- [ ] Add post-sync validation scripts/metrics
- [ ] Confirm vector indexes present/enabled
- [ ] Add unit/integration tests per Validation & Tests

## References (paths)
- graphiti_core/utils/bulk_utils.py
- graphiti_core/graph_queries.py
- graphiti_core/models/nodes/node_db_queries.py
- graphiti_core/models/edges/edge_db_queries.py
- sync_service/orchestrator/sync_orchestrator.py
- sync_service/loaders/falkordb_loader.py
- sync_service/loaders/neo4j_loader.py
- sync_service/simple_migration.py
- worker/worker_service.py
- regenerate_node_embeddings_ollama.py / regenerate_edge_embeddings_ollama.py

