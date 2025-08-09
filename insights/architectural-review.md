# Architectural Review & Refactoring Opportunities

This document summarizes backend and frontend improvement opportunities discovered during analysis of Graphiti. It records implemented refactors and proposes next steps focused on performance, modularity, and type safety.

Scope
- Backend: FastAPI service and Graphiti integration
- Frontend: React + TanStack Query + Cosmograph + DuckDB WASM

Implemented refactors (confirmed)
- Centralized client factories in [server/graph_service/factories.py](server/graph_service/factories.py)
- Removed duplication from [server/graph_service/zep_graphiti.py](server/graph_service/zep_graphiti.py) by using factories for LLM and Embedder creation
- Strengthened typing across modified modules and corrected optionals and collections

Backend opportunities
1) Event-driven post-write hooks
- Problem: Endpoints in [server/graph_service/routers/ingest.py](server/graph_service/routers/ingest.py) call cache invalidation and centrality directly.
- Change: Publish a single internal “data_changed” event; register subscribers on startup in [server/graph_service/main.py](server/graph_service/main.py).
- Handlers:
  - Cache invalidation subscriber (e.g. [server/graph_service/cache.py](server/graph_service/cache.py))
  - Centrality debounce subscriber (existing logic extracted from ingest router)
- Result: Decoupled endpoints; adding new side-effects requires only a new subscriber.

2) Replace in-memory AsyncWorker with a persistent queue
- Problem: [server/graph_service/routers/ingest.py](server/graph_service/routers/ingest.py) uses an in-memory asyncio.Queue without persistence or scaling.
- Change: Use ARQ (async Redis queue) or Celery workers for durability, retries, and horizontal scaling.
- Result: Higher throughput and resilience under load.

3) Batch ingestion and set-based DB ops
- Problem: Sequential episode ingestion and multi-roundtrip deletes in [server/graph_service/zep_graphiti.py](server/graph_service/zep_graphiti.py).
- Change: Support batch add_episode in Graphiti; use one Cypher/RedisGraph command to delete a group:
- Cypher:

```cypher
MATCH (n) WHERE n.group_id = $group_id
DETACH DELETE n
```

- Result: Fewer roundtrips, large reductions in latency.

4) Collapse Python↔Rust HTTP hops
- Problem: HTTP calls to Rust for cache clear and centrality add latency and complexity.
- Change: Wrap Rust as a Python extension via PyO3; call functions in-process.
- Result: Orders-of-magnitude faster and simpler deploy topology.

5) Settings construction via factories (done)
- Keep all client creation in [server/graph_service/factories.py](server/graph_service/factories.py); keep [server/graph_service/zep_graphiti.py](server/graph_service/zep_graphiti.py) focused on wiring.

Frontend opportunities
1) Provider composition cleanup
- Problem: Deep provider nesting in [frontend/src/App.tsx](frontend/src/App.tsx).
- Change: Introduce AppProviders component to compose Query, ParallelInit, DuckDB, WebSocket, Tooltip providers.
- Result: Clearer App root and easier testing.

2) Type-safe configuration
- Problem: Direct access to import.meta.env scattered.
- Change: Centralize with a config module validated by Zod (e.g. frontend/src/config.ts).
- Result: Fail-fast misconfigurations and typed access.

3) Route-based code splitting
- Problem: Eager import of pages in [frontend/src/App.tsx](frontend/src/App.tsx).
- Change: Use React.lazy + Suspense for Index and NotFound.
- Result: Smaller initial bundle and faster TTI.

4) ParallelInitProvider orchestration
- Problem: Mixed UI and orchestration logic in [frontend/src/contexts/ParallelInitProvider.tsx](frontend/src/contexts/ParallelInitProvider.tsx).
- Change:
  - Extract orchestration into a dedicated hook (useInitialization)
  - Replace multi-useState with useReducer for deterministic state transitions
  - Model startup steps as a data-driven task array for extensibility
- Result: Cleaner provider, easier unit tests, simpler extensibility.

5) GraphViz “god component” split
- Problem: Centralized UI state and prop drilling in [frontend/src/components/GraphViz.tsx](frontend/src/components/GraphViz.tsx).
- Change:
  - Introduce GraphUIProvider (context + reducer) for UI concerns (panels, timeline, fullscreen)
  - Extract feature hooks: useFullscreen, useGraphExports
  - Keep GraphViz as layout + high-level composition only
- Result: Lower cognitive load, easier feature evolution, fewer re-renders.

6) Performance and memory
- Memoize heavy computations; prefer stable refs for large arrays to avoid re-upload to WebGL
- Ensure Suspense fallbacks are light; add boundaries around heavy modals/timeline (already present)
- Audit event handlers for stable identity (useStableCallback already in use)
- Consider moving heavy data transforms into Web Workers if they grow (e.g., filter pipelines)

Cosmograph-specific guidance
- Maintain stable node/link object identity across frames to leverage internal diffing; avoid rebuilding arrays on minor UI changes.
- Use incremental updates (already present via useIncrementalUpdates) to apply diffs instead of full reloads.
- Pause simulation during bulk updates or selection floods; resume after (toggle via GraphCanvasHandle).
- Prefer numeric typed fields and pre-normalize data to minimize per-frame coercions.
- Batch selection/highlight updates to a single state commit to reduce render thrash.

Quick wins checklist
- [ ] Register internal subscribers for cache invalidation and centrality in [server/graph_service/main.py](server/graph_service/main.py)
- [ ] Move AsyncWorker jobs to ARQ/Celery; configure retries/backoff
- [ ] Replace group delete loops with a single set-based delete
- [ ] Add AppProviders and Zod-validated config module
- [ ] Lazy-load routes in [frontend/src/App.tsx](frontend/src/App.tsx)
- [ ] Extract useInitialization and a reducer into [frontend/src/contexts/ParallelInitProvider.tsx](frontend/src/contexts/ParallelInitProvider.tsx)
- [ ] Introduce GraphUIProvider and feature hooks; slim [frontend/src/components/GraphViz.tsx](frontend/src/components/GraphViz.tsx)

Risks and mitigations
- In-process Rust embedding increases build complexity → Isolate behind a minimal FFI, keep HTTP path as fallback
- Task queue introduces infra dependency → Start with ARQ (Redis) to minimize operational overhead
- Wider use of reducers/contexts → Add unit tests and storybook fixtures to verify UI behavior

References (key files)
- [server/graph_service/factories.py](server/graph_service/factories.py)
- [server/graph_service/zep_graphiti.py](server/graph_service/zep_graphiti.py)
- [server/graph_service/routers/ingest.py](server/graph_service/routers/ingest.py)
- [server/graph_service/main.py](server/graph_service/main.py)
- [frontend/src/App.tsx](frontend/src/App.tsx)
- [frontend/src/contexts/ParallelInitProvider.tsx](frontend/src/contexts/ParallelInitProvider.tsx)
- [frontend/src/components/GraphViz.tsx](frontend/src/components/GraphViz.tsx)

Appendix: sample factory flow (already implemented)

```Typescript
// App startup
// -> FastAPI lifespan: initialize_graphiti()
// -> Factories create LLM + Embedder (Ollama or OpenAI)
// -> ZepGraphiti constructed with proper driver (FalkorDB or Neo4j)