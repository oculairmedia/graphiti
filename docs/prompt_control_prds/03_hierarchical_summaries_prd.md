# Hierarchical Conversation Summaries PRD

## Background & Problem Statement
- `previous_episodes` payloads frequently exceed token thresholds, even after FIFO clipping (`prompt_utils.py:189`).  
- Valuable context is lost when trimming to last N turns, causing extraction misses that require reflexion loops.
- Summarization prompts already exist (`graphiti_core/prompts/summarize_nodes.py:69`) but are invoked ad hoc, not as part of ingestion pre-processing.

## Goals
- Maintain high recall for long-running conversations while keeping prompts under configurable token budgets.
- Reduce reliance on reflexion retries by preserving salient context in summaries.
- Enable incremental updates instead of resending entire history each call.

## Non-Goals
- Redesigning reflexion logic or entity attribute extraction details.  
- Replacing the existing summarization prompts (reuse current templates).

## Proposed Solution
1. **Persistent Digest Store**  
   - Maintain per-episode-group digests in storage (e.g., FalkorDB node property or Redis).  
   - Digest contains reranker-selected key facts plus summary generated via `summarize_context`.
2. **Delta Capture Workflow**  
   - On new episode ingestion, produce:  
     a. `delta_summary`: summary of latest episode via existing prompt.  
     b. `combined_summary`: merge previous digest with delta using `summarize_pair`.  
   - Store combined summary back; keep small set of raw excerpt candidates (reranked).
3. **Prompt Assembly Changes**  
   - Replace raw `previous_episodes` usage in `node_operations.py:245` with:  
     - Digest summary (tiny).  
     - Top reranked verbatim excerpts (1–3) when necessary.  
   - Include metadata in `__prompt_debug__` describing digest version and excerpt ids.
4. **Fallback Strategy**  
   - If digest unavailable (first run or cache miss), fall back to existing trimming path and regenerate summary asynchronously post-call.

## Technical Considerations
- Need asynchronous task runner to update digests without blocking ingestion (e.g., via existing worker queue).  
- Persisting summaries requires schema update or auxiliary store—coordinate with DB team.  
- Ensure digests respect attribute privacy filters if applied downstream.

## Dependencies
- Summarization prompt robustness; may require fine-tuning instructions for stability.  
- Reranker availability to select high-value excerpts for retention.

## Impact Metrics
- Token reduction relative to baseline for conversations >10 turns.  
- Reduction in reflexion iterations per episode (tracked via `node_operations.py:270`).  
- Entity extraction recall measured via replay harness comparing baseline vs summarized contexts.

## Rollout Plan
1. Pilot digest store on staging dataset; backfill existing conversations.  
2. Enable summary insertion for a subset of prompt types (e.g., `extract_nodes` only).  
3. Monitor extraction metrics and latency; iterate on digest size and excerpt thresholds.  
4. Gradually expand scope once stable.

## Risks & Mitigations
- **Summary Drift**: Accumulated summaries may diverge from source text—schedule periodic full refresh (weekly) using reranker to verify key facts.  
- **Storage Overhead**: Limit digest history (keep last N versions) and expire stale groups.  
- **Implementation Complexity**: Start with simple store (JSON blob keyed by group) before optimizing.
