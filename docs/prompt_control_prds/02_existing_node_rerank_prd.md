# Existing Node Reranker Packager PRD

## Background & Problem Statement
- Dedupe prompts (`graphiti_core/utils/maintenance/node_operations.py:641`) embed entire `existing_nodes` arrays. Even with `GraphitiPromptCompressor` the prompt frequently exceeds 8K tokens.
- Captured payloads (`prompt_captures/prompts_20251023_231303.jsonl`) show dedupe requests consuming ~50% of total tokens despite many irrelevant candidates.
- High volume of low-relevance nodes increases LLM latency and duplicates.

## Goals
- Shrink dedupe prompt size by limiting to reranker-selected top candidates.
- Improve dedupe accuracy by surfacing the most similar nodes first.
- Preserve existing API contracts for `prompt_library.dedupe_nodes` while feeding higher-quality context.

## Non-Goals
- Replacing the existing compression model. (Enhancements to LLMLingua fall outside scope.)
- Changing database search logic.

## Proposed Solution
1. **Candidate Scoring**  
   - Use the reranker to score each candidate summary against the target node name and optional attributes.
   - Input passages: `existing_nodes_metadata` items formatted as `"Name: ... Summary: ..."`.
2. **Budgeted Selection**  
   - Introduce config `MAX_DEDUPE_CANDIDATES` and `MAX_DEDUPE_TOKENS`.  
   - Select top-N nodes by score within token budget before compression; fallback to score-only if token estimation unavailable.
3. **Structured Payload**  
   - Include reranker score in metadata (e.g., `{'idx': i, 'name': ..., 'score': 0.87}`) for analyzer tools.  
   - When building `existing_nodes_text`, concatenate in score order so compression drops the tail first.
4. **Instrumentation**  
   - Update debug telemetry (propagate via `__prompt_debug__`) and log to `PromptCaptureMonkeyPatch` for offline analysis.  
   - Add counters for nodes kept/dropped per batch.

## Technical Considerations
- Needs async encoder; reuse `semaphore_gather` pattern (see `openai_reranker_client.py:67`).  
- Cache reranker scores for identical candidate text across chunk retries.  
- Ensure deterministic `idx` mapping so downstream `duplication_candidates` remains valid after filtering.

## Dependencies
- Existing reranker client and API quota.  
- Configuration management (environment variables or settings file).

## Impact Metrics
- Mean/95th percentile token count for dedupe prompts.  
- Duplicate resolution success rate (compare `node_duplicates` logs pre/post).  
- Latency per dedupe batch.

## Rollout Plan
1. Implement behind `ENABLE_EXISTING_NODE_RERANKER` flag.  
2. Run `replay_prompts.py` with real captures to quantify improvements.  
3. Monitor for regressions; verify `NodeResolutions` quality manually on sample set.  
4. Gradual rollout in staging, then production.

## Risks & Mitigations
- **Score Threshold Too Aggressive**: Might miss true duplicates. Mitigate with minimum candidate floor (e.g., keep at least 10).  
- **API Cost**: Batch reranker calls and reuse scores across nodes sharing candidates.  
- **Complexity**: Ensure fallback path preserves baseline behavior when disabled.
