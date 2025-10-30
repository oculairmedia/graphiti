# Prompt Policy Layer PRD

## Background & Problem Statement
- Prompt behavior (budgets, instructions, features) is scattered across individual prompt functions (`graphiti_core/prompts/extract_nodes.py:74`, etc.) and utils (`prompt_utils.py:137`), making provider- or task-specific tuning hard.
- No centralized configuration to coordinate new controls (reranking, summaries, field quotas).

## Goals
- Introduce an extensible policy abstraction that defines prompt constraints per task/provider.
- Enable experimentation (A/B) and dynamic configuration without editing prompt templates.
- Provide a single source of truth for telemetry and feature toggles.

## Non-Goals
- Changing base prompt copy (instruction text).  
- Handling provider-specific low-level API differences (temp, max tokens) already covered in `LLMConfig`.

## Proposed Solution
1. **Policy Definition**  
   - Create `graphiti_core/prompts/policy.py` housing `PromptPolicy` dataclass with fields:  
     `max_prompt_tokens`, `max_previous_episodes`, `enable_rerank`, `enable_digests`, `max_existing_nodes`, etc.  
   - Support provider overrides keyed by provider name from `LLMClient`.
2. **Policy Registry**  
   - Extend `graphiti_core/prompts/lib.py:53` `VersionWrapper` to accept policy on invocation.  
   - `prompt_library.extract_nodes.extract_message(context, policy=...)` applies policy before returning messages.
3. **Integration with Call Sites**  
   - Update ingestion workflows (`node_operations.py:245`, dedupe, summarize) to fetch policy from configuration.  
   - Provide default policy mapping in new config file (e.g., `config/prompt_policies.yaml`).
4. **Telemetry & Enforcement**  
   - Policy includes `track_metrics` flag; when enabled, append policy metadata into `__prompt_debug__`.  
   - Validation layer ensures context obeys policy before calling `LLMClient`.

## Technical Considerations
- Backwards compatibility: supply default policy that mirrors current behavior (no features enabled).  
- Ensure prompt call signatures remain ergonomic; may need helper functions to auto-inject policies.  
- Consider caching resolved policies per (task, provider) for performance.

## Dependencies
- Configuration loader (existing env-based or new YAML parser).  
- Agreement on provider taxonomy from `GraphitiClientFactory`.

## Impact Metrics
- Configuration change lead time (should drop from code deploy to config edit).  
- Frequency of policy violations (monitored via telemetry).  
- Ability to run A/B tests with `replay_prompts.py` toggling policy parameters.

## Rollout Plan
1. Implement core policy classes with defaults matching current behavior.  
2. Update one prompt type (`extract_nodes`) to use policy as pilot.  
3. Add policy editing support (config reload or env).  
4. Incrementally adopt across other prompts once stable.

## Risks & Mitigations
- **Configuration Drift**: Introduce automated validation in CI to catch invalid policies.  
- **Complexity**: Provide sensible defaults and fallback to baseline when policy missing.  
- **Performance**: Cache policies and avoid heavy computation inside wrappers.
