# Ingestion Fault Report – Missing `source_description`

## Overview
- **Detected by:** graphiti worker queue triage  
- **Window:** summaries returned to API clients but no FalkorDB writes  
- **Impact:** worker dequeues episode tasks and retries until DLQ; data never persisted.

## Symptoms
- Queue depth drops while Falkor graph remains unchanged.
- Worker logs contain `1 validation error for EpisodicNode -> source_description`.
- Dead-letter queue accumulates `episode` tasks with empty `source_description` payloads.

## Root Cause
- `Message` DTO and `QueueProxy` allowed empty `source_description` fields.
- `IngestionWorker._process_episode` forwards payloads directly to `Graphiti.add_episode_resilient`.
- `EpisodicNode` enforces non-empty `source_description`; validation failure raises `ValueError`.
- Worker treats the error as retryable, eventually moving the task to the DLQ—effectively “eating” the episode.

## Evidence
1. Reproduced validator failure with `EpisodicNode(... source_description=\"\")`, which raises `ValueError`.
2. Inspecting queued payload assembly showed `source_description` defaulting to `\"\"` whenever API callers omitted it.
3. Prior logs/metrics confirmed DLQ growth alongside ingestion success decrements.

## Remediation
- Normalized the public `Message` DTO so ingestion requests always carry a trimmed, non-empty `source_description` (defaults to `unspecified` or the `GRAPHITI_DEFAULT_SOURCE_DESCRIPTION` override).
- Captured the failure mode and guidance here so responders can rapidly verify queue payloads before reprocessing.
- Added regression tests for DTO normalization.

## Verification
- Unit test `tests/test_message_defaults.py` passes, confirming DTO normalization.
- Manual `python3 - <<'PY' …` check now returns sanitized descriptions instead of raising validation errors.
- Recommended production check: replay a sample DLQ task after redeploy and confirm FalkorDB writes via `GRAPH.QUERY ... RETURN count(n)`.

## Follow-Ups
- Monitor DLQ for stale entries and re-queue once sanitized.
- Communicate new `GRAPHITI_DEFAULT_SOURCE_DESCRIPTION` override to deployment docs.
