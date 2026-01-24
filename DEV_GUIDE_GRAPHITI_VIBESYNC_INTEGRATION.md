# Developer Guide: Graphiti-Side Work for VibeSync Integration

## 1. Objective
Enable VibeSync (the Project Management Brain) to seamlessly write code-structure updates into Graphiti's Knowledge Graph. We need to ensure Graphiti's API can accept high-frequency updates for specific code entities without triggering redundant LLM extraction cycles.

## 2. Required Enhancements

### A. Deterministic UUID Exposure
**Goal:** VibeSync needs to know the exact UUID of "File:src/main.py" without querying the graph first.
**Action:** Expose the `generate_deterministic_uuid` logic via a lightweight utility endpoint or SDK function.
*   **New Endpoint:** `GET /utils/uuid?name={name}&group_id={group_id}`
*   **Logic:** Returns `uuid5(NAMESPACE_DNS, f'graphiti.entity.{group_id}::{name}')`.
*   **Why:** Allows VibeSync to generate IDs locally or verify them against the server.

### B. "Upsert" Semantics for `POST /entity-node`
**Goal:** If VibeSync sends `POST /entity-node` for an existing node, it should update it, not error.
**Current State:** `server/graph_service/routers/ingest.py` calls `graphiti.save_entity_node`.
**Action:** Verify `save_entity_node` performs a `MERGE` (Upsert) operation in FalkorDB.
*   *Check:* `graphiti_core/nodes.py` -> `save()`.
*   *Task:* Ensure `ON MATCH SET n.summary = $summary` is part of the query.

### C. Rate Limiting / Debouncing (Optional but Smart)
**Goal:** Prevent VibeSync from DDOSing Graphiti during a `git checkout`.
**Action:** Add a simple `Redis`-backed rate limiter to the `PATCH /nodes/{uuid}/summary` endpoint if not already present via middleware.

## 3. The "Shepherd" Integration (Hygiene)
**Goal:** Clean up "Deleted Files".
**Action:** Implement a `POST /tools/prune-missing` endpoint (or expose via Letta Shepherd).
*   **Logic:** VibeSync sends a list of *current* file paths. Graphiti finds `EntityNode` (Type: File) that are *not* in that list and marks them `invalid_at = NOW`.

## 4. Implementation Checklist

### Step 1: UUID Utility Endpoint
*   [ ] Create `server/graph_service/routers/utils.py`.
*   [ ] Add `GET /uuid` endpoint wrapping `graphiti_core.utils.uuid_utils.generate_deterministic_uuid`.
*   [ ] Register router in `main.py`.

### Step 2: Verify Upsert Logic
*   [ ] Review `graphiti_core/models/nodes/node_db_queries.py`.
*   [ ] Ensure `save_entity_node` uses `MERGE`. If it uses `CREATE`, refactor to `MERGE`.

### Step 3: Pruning Tool
*   [ ] Add `prune_stale_files(group_id, active_file_list)` to `graphiti_core/shepherd/tools.py`.
*   [ ] This allows VibeSync to say "Here is the master list of files. Delete anything else."

## 5. API Contract for VibeSync
Once completed, provide VibeSync developers with:
1.  `GET /api/utils/uuid`: To calculate IDs.
2.  `POST /api/entity-node`: To create/update structural nodes (Classes/Files).
3.  `PATCH /api/nodes/{uuid}/summary`: To update code summaries.
4.  `POST /api/messages`: To log commit messages.
