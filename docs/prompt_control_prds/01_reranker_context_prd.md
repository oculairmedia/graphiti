# Prompt Relevance Gating PRD

## Background & Problem Statement
- Captured prompts show inflated token counts (avg 6,649; max 15,488) for `extract_nodes` calls (`scripts/prompt_analysis/analyze_results.py` run 2025-10-23 capture).  
- Current context trimmer (`graphiti_core/utils/prompt_utils.py:92`) removes previous episodes by order, not relevance, leading to loss of useful turns while still shipping noise.
- `OpenAIRerankerClient` (`graphiti_core/cross_encoder/openai_reranker_client.py:33`) already ranks passages but is unused in prompt assembly.

## Goals
- Reduce prompt tokens for ingestion prompts by 35–50% without lowering extraction recall.
- Ensure only high-signal conversational history reaches the LLM.
- Maintain deterministic clipping with telemetry for audit.

## Non-Goals
- Changing how `existing_nodes` are packaged (covered in separate PRD).
- Modifying downstream LLM client retry or caching logic.

## Proposed Solution
1. **Context Chunking**  
   - Split `previous_episodes` strings in `node_operations.py:245` into manageable passages (e.g., per message or paragraph) prior to rerank.
   - Attach metadata (episode id, timestamp) for traceability.
2. **Reranker Scoring Loop**  
   - Call `OpenAIRerankerClient.rank(query, passages)` using the episode’s `episode_content` (or a summary) as query.  
   - Use async gather to keep pipeline throughput.
   - Persist top-K passage ids and scores in context debug block (`__prompt_debug__`).
3. **Budget Manager**  
   - Replace FIFO trimming in `clip_previous_episodes` with a budget allocator: accumulate passages in descending score until target token cap (configurable `RERANKED_CONTEXT_MAX_TOKENS`) is met.  
   - Fallback to baseline if reranker unavailable or API fails (revert to current heuristic).
4. **Telemetry & Controls**  
   - Extend `PromptCaptureMonkeyPatch` to log reranker decision stats (kept vs dropped, total score).  
   - Add feature flag `ENABLE_CONTEXT_RERANKING`.

## Technical Considerations
- **Token Estimation**: Leverage existing `estimate_tokens` but prefer real tokenizer counts when `tiktoken` available (`prompt_compression.py:78`).
- **Caching**: Cache reranker scores per (episode uuid, context hash) to avoid recompute on retries.
- **Error Handling**: If reranker rate-limits, log via `GraphitiPromptCompressor` logger and continue with baseline clip.

## Dependencies
- `openai` API availability and cost; fallback path mandatory.
- Configuration updates via env or YAML (new limits, feature flag).

## Impact Metrics
- Token reduction (% decrease per prompt type).
- Extraction precision/recall (compare replay harness outputs from `scripts/prompt_analysis/replay_prompts.py`).
- Reranker latency overhead vs baseline ingestion SLA.

## Rollout Plan
1. Ship behind default-off flag.  
2. Run `replay_prompts.py` A/B: baseline vs reranked.  
3. Monitor capture telemetry for token & accuracy metrics.  
4. Gradually enable per environment once metrics pass threshold.

## Risks & Mitigations
- **Reranker Drift**: Passage similarity metrics may degrade—add periodic evaluation set.  
- **Latency Explosion**: Parallelize ranking, enforce timeout to fall back gracefully.  
- **Data Loss**: Guard with minimum passage count so we never send empty context.
