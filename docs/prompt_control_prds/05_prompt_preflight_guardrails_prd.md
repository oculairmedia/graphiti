# Prompt Preflight Guardrails PRD

## Background & Problem Statement
- `LLMClient.generate_response` (`graphiti_core/llm_client/client.py:129`) sends prompts after lightweight sanitization; token estimates rely on heuristics and there is no last-mile validation.
- Over-limit prompts cause provider errors, retries, or silent truncation, and we lack structured telemetry when clipping occurs upstream.
- New control features (reranking, digests) require central verification before dispatch.

## Goals
- Introduce a preflight guard that validates prompt size and structure before hitting provider APIs.
- Provide standardized telemetry describing token usage, clipping decisions, and policy compliance.
- Offer synchronous remediation options (auto-drop lowest score passages, invoke reranker summarizer).

## Non-Goals
- Replacing provider-specific max token settings in `LLMConfig`.  
- Implementing UI dashboards (telemetry export only).

## Proposed Solution
1. **Tokenizer-Aware Measurement**  
   - Integrate `tiktoken` when available; fallback to heuristic.  
   - Compute per-message and aggregate token counts, store in `prompt_stats`.
2. **Rule Engine**  
   - Evaluate configured policies (from PRD #4) before sending:  
     - Hard caps (max messages, max tokens).  
     - Required roles (system + user).  
     - Field quotas (e.g., `previous_episodes_tokens <= X`).
   - On violation, execute remediation strategy: rerank drop, summary fallback, or fail fast.
3. **Telemetry & Logging**  
   - Attach `prompt_stats` to `response` metadata or emit via structured logs (JSON) for capture tooling.  
   - Update `PromptCaptureMonkeyPatch` to include preflight results and remediation actions.
4. **Feature Flags & Configuration**  
   - Controlled via `ENABLE_PROMPT_PREFLIGHT` and policy settings (per provider).  
   - Provide override to bypass for emergency scenarios.

## Technical Considerations
- Guard should operate inside `LLMClient.generate_response` to cover all callers.  
- Ensure async compatibility and minimal overhead (cached tokenizer).  
- On failure, raise descriptive error to upstream pipeline for graceful handling (e.g., skip ingestion item).

## Dependencies
- Policy layer (PRD #4) for thresholds.  
- Reranker & summarization capabilities for remediation steps.  
- Logging infrastructure to capture structured telemetry.

## Impact Metrics
- Number of prevented over-limit errors (compare provider error rate before/after).  
- Average token count reduction per prompt type.  
- Frequency of remediation actions taken.

## Rollout Plan
1. Implement instrumentation-only mode (log stats, no enforcement) to baseline.  
2. Enable soft enforcement (warn + optional auto-trim) in staging.  
3. Move to hard enforcement with fallback strategies once confidence established.  
4. Document runbooks for override if providers change limits.

## Risks & Mitigations
- **Performance Overhead**: Cache tokenizers and reuse computed stats per prompt.  
- **False Positives**: Test extensively via replay harness to tune thresholds.  
- **Operational Noise**: Aggregate telemetry to avoid log spam (batch logging, sampling).
