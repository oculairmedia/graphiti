# Graphiti Memory Replay Operations Guide

## Why Memory Replay Exists

The memory replay system reprocesses under-enriched episodes so they benefit from the latest extraction models, cross-group deduplication, and prompt compression strategies. It targets episodes that failed to build strong entity relationships the first time, eliminating stale data pockets that hurt semantic search, recommendations, and downstream analytics.

## High-Level Architecture

Three cooperating components deliver replay capability:

1. **Replay Candidate Detector** (`ReplayCandidateDetector`) scans Neo4j/FalkorDB for episodes with poor enrichment signals.
2. **Memory Replay Scheduler** (`MemoryReplayScheduler`) ranks candidates, enforces cooldown/rate limits, and enqueues replay jobs via the new `TaskType.REPLAY` queue contract.
3. **Replay Executor** (`ReplayExecutor`) re-ingests the episode through the idempotent `graphiti.add_episode_resilient(..., replay_mode=True, replay_context=ReplayContext(...))` path while preserving episode UUIDs and enrichment provenance.

```
┌──────────────────────┐    ┌────────────────────┐    ┌─────────────────────┐
│ Candidate Detector   │──►│ Replay Scheduler    │──►│ Replay Executor      │
└──────────────────────┘    └────────────────────┘    └─────────────────────┘
          │                        │                           │
          ▼                        ▼                           ▼
  Replay Metadata Store     Queued Task Queue           Graphiti Ingestion
```

Replay provenance is stored directly inside FalkorDB/Neo4j via the `ReplayMetadata` nodes introduced in the migration work. These nodes track each episode’s last replayed timestamp, attempt count, confidence scores, reason codes, and now capture `last_failed_at`/`last_error` details when the executor surfaces an exception. This data drives prioritisation, backoff, and observability.

## Candidate Selection Process

Episodes are ranked by a weighted score that blends multiple heuristics:
- Fewer than three extracted entities or missing bi-directional edges
- No cross-group relationships despite shared embeddings
- Outdated extraction version or low entity confidence scores
- Recent user interactions (queries, follows, alerts) that reference the episode
- Explicit replay requests from operators or analytics jobs

Each candidate is wrapped in a `ReplayContext` payload that carries the reason, priority score, scheduling timestamp, and attempt number for auditability.

## Scheduling & Execution Flow

1. Scheduler loop wakes on `REPLAY_INTERVAL_SECONDS`, pulls batches using `ReplayCandidateDetector.identify_candidates(limit=REPLAY_BATCH_SIZE)` (internally the scheduler over-scans by `REPLAY_SCAN_MULTIPLIER`).
2. Candidates are filtered against per-group limits (`REPLAY_MAX_PER_GROUP_PER_HOUR` within `REPLAY_RATE_LIMIT_WINDOW_SECONDS`), replay attempt ceilings, and cooldown windows derived from `REPLAY_COOLDOWN_HOURS`.
3. Remaining items are pushed to the queue as `TaskType.REPLAY` with serialized `ReplayContext` metadata. The default target queue is `memory_replay`, configurable through `REPLAY_QUEUE_NAME`.
4. Ingestion workers now understand `TaskType.REPLAY`, hydrating `ReplayContext` and calling `add_episode_resilient(..., uuid=<original>, replay_mode=True, replay_context=context)` to ensure MERGE semantics, keep the UUID stable, and record pre/post enrichment deltas.
5. Replay outcomes update the metadata store: timestamp, attempts, entities/edges before vs. after, confidence delta, and terminal status.

## Replay Metadata Model

Replay provenance now lives entirely inside the graph layer:
- `ReplayMetadata` nodes are keyed by `episode_uuid` and track `group_id`, `last_replayed_at`, `replay_attempts`, `extraction_version`, `replay_reason`, `confidence_score`, plus `created_at`/`updated_at` timestamps. Neo4j/Falkor indexes on `(episode_uuid)` and `(group_id)` keep scheduler lookups fast.
- Episodic nodes carry enrichment metrics (`entity_count`, `edge_count`, `cross_group_connections`, `extraction_version`, `confidence_score`) so candidate heuristics avoid extra traversal work. Legacy records default these fields to zero/`null`.

Run `Graphiti.apply_replay_metadata_migration()` after deploying the code to create the indexes, add any missing `ReplayMetadata` nodes, and hydrate the new episodic counters in batches. If an environment needs to roll back, `Graphiti.rollback_replay_metadata_migration()` drops the indexes, deletes metadata nodes, and clears the added episodic properties.

## Configuration

Environment flags and their defaults (see `graphiti_core/config/replay_config.py`):
- `REPLAY_ENABLED` (default `false`): globally toggle the feature.
- `REPLAY_INTERVAL_SECONDS` (default `300`): scheduler wake cadence.
- `REPLAY_BATCH_SIZE` (default `10`): candidate batch size per loop.
- `REPLAY_SCAN_MULTIPLIER` (default `4`): how aggressively to over-fetch before filtering.
- `REPLAY_MIN_PRIORITY` (default `0.2`): minimum candidate priority that survives detection.
- `REPLAY_MAX_ATTEMPTS` (default `3`): cap retries for an episode.
- `REPLAY_COOLDOWN_HOURS` (default `24`): enforced pause after a replay.
- `REPLAY_MAX_PER_GROUP_PER_HOUR` (default `100`): rate limiting for hot tenants.
- `REPLAY_RATE_LIMIT_WINDOW_SECONDS` (default `3600`): sliding window applied to the per-group limit.
- `REPLAY_QUEUE_NAME` (default `memory_replay`): queue name used when publishing replay jobs.
- `REPLAY_CIRCUIT_BREAKER_THRESHOLD` / `REPLAY_CIRCUIT_BREAKER_RESET_SECONDS`: knobs for future circuit-breaker logic (values parsed but not yet enforced).
- `REPLAY_TARGET_GROUP_ID` (optional): restrict scheduling to a single tenant during phased rollouts.

Configuration values live under `ReplayConfig` and can be overridden via the standard Graphiti settings stack (environment, centralized config service, or deployment manifests).

## Data & Contract Commitments

### Graph Storage
- **Replay metadata nodes**: persist replay state as `ReplayMetadata` nodes keyed by `episode_uuid` with `group_id`, `last_replayed_at`, `replay_attempts`, `extraction_version`, `replay_reason`, `confidence_score`, and timestamps. Create indexes on `episode_uuid` and `group_id` in Neo4j/Falkor.
- **Episodic node enrichment**: extend Episodic nodes with properties (`entity_count`, `edge_count`, `cross_group_connections`, `extraction_version`, `confidence_score`) so replay heuristics operate without extra lookups. Defaults remain null/zero for legacy records.
- **Migration plan**: add graph migrations (Cypher scripts or loader updates) that backfill new properties and replay metadata entries; document rollback via property removal.

### Internal APIs
- Extend `graphiti_core/ingestion/queue_client.py:TaskType` with a `REPLAY` member; serialized payloads include a `replay_context` blob.
- Update `graphiti_core/graphiti.py:add_episode_resilient` signature to accept `replay_mode: bool` and `replay_context: ReplayContext | None`. Existing callers can omit these parameters.
- Standardize the `ReplayContext` structure (`reason`, `priority_score`, `scheduled_at`, `attempt_number`, optional `operator_id`) so manual triggers and automated schedulers publish identical payloads.
- Optional separate service API surface (if we split deployment) exposes `/replay/candidates`, `/replay/trigger`, and `/replay/metrics` endpoints guarded behind service auth. Keep the contract aligned with the internal queue payload schema.

### Configuration Surface
- Register the replay feature flag in centralized config (or Helm/Kube manifests) so environments can toggle without redeploy.
- Document default metric names and alert thresholds in the observability repo for consistency across environments.
- Capture any per-tenant overrides (e.g., bespoke `REPLAY_MAX_PER_GROUP_PER_HOUR`) in tenant configuration playbooks.

## Safety Controls

- **Circuit breakers**: Disable replay for a group after repeated failures; auto-reset after `REPLAY_COOLDOWN_HOURS`.
- **Adaptive throttling**: Scheduler tracks system load and scales batch sizes down before saturation.
- **Infinite loop protection**: Attempt counters and reason deduplication prevent replay storms on bad data.
- **Resource safeguards**: Executor respects ingestion pool limits and stops when queue latency or Neo4j pressure crosses guard rails.

## Observability

Key metrics exported to Prometheus/StatsD:
- Replay throughput (episodes/hour) and success rate
- Enrichment deltas (entities, edges, cross-group connections)
- Circuit breaker activations and time spent tripped
- Queue latency and executor runtime percentiles

Alerting rules should page when:
- Replay failure rate exceeds threshold for five minutes
- Any circuit breaker stays open past its cooldown
- Replay job backlog grows faster than it drains
- Replay increases ingestion latency by more than agreed SLOs

## Dependencies & Rollout Plan

### Service & Infrastructure Dependencies
- **Queue layer**: upgrade ingestion workers to understand `TaskType.REPLAY`, add dead-letter handling, and adjust autoscaling thresholds if replay load spikes.
- **Graph migrations**: ship Cypher/backfill scripts alongside releases and ensure indexes/backups cover ReplayMetadata nodes and episodic enrichment properties.
- **Config propagation**: wire replay environment variables into Terraform/Helm charts and centralized config management; add CI guardrails to keep defaults in sync.
- **Observability**: update Prometheus scrape configs, create Grafana panels for replay metrics, and integrate alert routing with the on-call pager.
- **Operational tooling**: extend admin dashboards or CLI tooling to surface replay status, recent failures, and manual trigger controls.

### Rollout Steps
1. **Schema-first deploy**: apply database migrations and ship idle config flags (`REPLAY_ENABLED=false`).
2. **Worker readiness**: deploy queue/worker changes with replay disabled; verify no regression in standard ingestion.
3. **Observability bake**: publish metrics/dashboards and validate alert wiring in staging.
4. **Pilot enablement**: flip `REPLAY_ENABLED` for a canary tenant with tight monitoring; capture enrichment deltas and error logs.
5. **Incremental expansion**: gradually raise batch sizes and tenant coverage, tuning heuristics and thresholds as real load patterns emerge.
6. **Post-launch review**: document learnings, finalize SLO adjustments, and update runbooks with operational best practices.

## Deployment Options

The design supports two modes:
1. **In-process**: Embed scheduler/executor alongside the ingestion worker for simple deployments.
2. **Separate replay service**: Decouple candidate detection and scheduling into a FastAPI microservice that publishes replay jobs over HTTP/queue boundaries. This isolates failures, allows independent scaling, and enables alternative storage backends for replay metadata.

Select the mode per environment; production scale typically favours the dedicated service once replay traffic becomes material.

## Testing & Rollout Checklist

- Unit tests for candidate scoring (`tests/test_replay_candidate_detector.py`), scheduler behaviour (`tests/test_memory_replay_scheduler.py`), replay execution metadata handling (`tests/test_memory_replay_executor.py`), replay execution idempotency, and metadata updates.
- Integration smoke tests that replay synthetic episodes and verify entity/edge deltas.
- Data validation in this implementation cycle runs against the FalkorDB test host at `http://192.168.50.80:6379/`; keep destructive experiments scoped to that sandbox only.
- Feature flag gated rollout: enable in dev, validate dashboards, then stage with mirrored production data before piloting specific group IDs.
- Post-launch review: compare enrichment metrics and search relevance against baseline, tune thresholds, and revisit heuristic weights.

### Runtime Monitoring
- `/metrics/replay` (FastAPI) — exposes scheduler status, last run timestamp, and last batch size for dashboarding.
- `/metrics/webhooks` — existing async dispatcher metrics (unchanged).
- `/replay/trigger?dry_run=true` — preview the next batch without publishing tasks.
- `/replay/trigger` — force an immediate scheduling cycle.

## References

- Detailed specification: `docs/memory_replay_specification.md`
- Ingestion entry point: `graphiti_core/graphiti.py:add_episode_resilient`
- Queue integration: extend `graphiti_core/ingestion/queue_client.py:TaskType` with a `REPLAY` entry

## Implementation Plan & Tracking

Project delivery lives in Huly under the **Graphiti Development (GRAPH)** project. Components map directly to the workstreams in this guide, and each backlog item has clear acceptance criteria.

### Components & Issues
- **Replay Core Services** — candidate heuristics, scheduler, executor
  - [GRAPH-602](http://nginx:80/workbench/agentspace/tracker/GRAPH-602) · Implement `ReplayCandidateDetector` heuristics and scoring
  - [GRAPH-603](http://nginx:80/workbench/agentspace/tracker/GRAPH-603) · Build `MemoryReplayScheduler` loop and queue publisher
  - [GRAPH-604](http://nginx:80/workbench/agentspace/tracker/GRAPH-604) · Extend `ReplayExecutor` and `add_episode_resilient` for replay mode
- **Persistence & Metadata** — schema changes and replay tracking store
  - [GRAPH-605](http://nginx:80/workbench/agentspace/tracker/GRAPH-605) · Ship `ReplayMetadata` nodes and episodic enrichment properties
  - [GRAPH-606](http://nginx:80/workbench/agentspace/tracker/GRAPH-606) · Implement metadata repository and cooldown logic
  - [GRAPH-607](http://nginx:80/workbench/agentspace/tracker/GRAPH-607) · Backfill enrichment metrics for existing episodes
- **Queue & Worker Integration** — queue contracts, workers, DLQ flow
  - [GRAPH-608](http://nginx:80/workbench/agentspace/tracker/GRAPH-608) · Extend `TaskType` and payload schema for replay jobs
  - [GRAPH-609](http://nginx:80/workbench/agentspace/tracker/GRAPH-609) · Process replay tasks in ingestion workers
  - [GRAPH-610](http://nginx:80/workbench/agentspace/tracker/GRAPH-610) · Enhance dead-letter handling and monitoring for replay failures
- **Configuration & Feature Flags** — config surfaces and operator toggles
  - [GRAPH-615](http://nginx:80/workbench/agentspace/tracker/GRAPH-615) · Propagate `ReplayConfig` via env/centralized config
  - [GRAPH-617](http://nginx:80/workbench/agentspace/tracker/GRAPH-617) · Implement feature flag switch for replay system
  - [GRAPH-618](http://nginx:80/workbench/agentspace/tracker/GRAPH-618) · Update operations docs with replay env variables
- **Observability & Tooling** — metrics, dashboards, operator UX
  - [GRAPH-619](http://nginx:80/workbench/agentspace/tracker/GRAPH-619) · Emit Prometheus/StatsD metrics for replay
  - [GRAPH-620](http://nginx:80/workbench/agentspace/tracker/GRAPH-620) · Build Grafana dashboard and alert rules
  - [GRAPH-621](http://nginx:80/workbench/agentspace/tracker/GRAPH-621) · Extend admin UI/CLI for manual replay controls
- **Rollout & QA** — validation, staged launch, runbooks
  - [GRAPH-622](http://nginx:80/workbench/agentspace/tracker/GRAPH-622) · Expand automated tests for replay flows
  - [GRAPH-623](http://nginx:80/workbench/agentspace/tracker/GRAPH-623) · Execute staged rollout checklist
  - [GRAPH-624](http://nginx:80/workbench/agentspace/tracker/GRAPH-624) · Update runbooks and post-launch review template

### Delivery Phases
1. **Foundation** — Persistence & Metadata, Configuration & Feature Flags (`GRAPH-605`, `GRAPH-606`, `GRAPH-607`, `GRAPH-615`, `GRAPH-617`, `GRAPH-618`).
2. **Core Services** — Core replay logic (`GRAPH-602`, `GRAPH-603`, `GRAPH-604`).
3. **Queue Integration** — Queue/worker execution path (`GRAPH-608`, `GRAPH-609`, `GRAPH-610`).
4. **Observability** — Metrics, dashboards, operator tooling (`GRAPH-619`, `GRAPH-620`, `GRAPH-621`).
5. **Rollout & QA** — Testing, staged deployment, runbooks (`GRAPH-622`, `GRAPH-623`, `GRAPH-624`).

Each phase should exit only after linked issues meet acceptance criteria and staging validation is complete.
