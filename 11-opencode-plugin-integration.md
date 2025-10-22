# OpenCode Plugin Integration Guide

This chapter summarizes the OpenCode plugin bundle that streams OpenCode development sessions into the Graphiti knowledge graph. It complements `docs/integrations/OPENCODE_PLUGIN_INTEGRATION.md`, which contains the full 400+ line implementation reference.

## Objectives
- Provide always-on capture of OpenCode sessions without developer overhead
- Generate concise AI-authored summaries for every buffered conversation segment
- Route captured knowledge into Graphiti with consistent metadata, grouped per project
- Offer a single installation recipe that works across local and remote shells
- Preserve history of the TypeScript → JavaScript migration for future maintenance

## Components
1. `.opencode/plugin/graphiti-context-collector.js`
   - Buffers six turns (user + assistant) then requests an OpenCode SDK summary
   - Emits session-start/session-end markers and summarized conversation episodes
   - Chooses `GROUP_ID` dynamically (`opencode-{project}`) with overrides via env vars
   - Extracts referenced file paths plus git branch and commit metadata
2. `.opencode/plugin/graphiti-integration.js`
   - Shared helper utilities for HTTP POST, logging, and metadata formatting
   - Encapsulates Graphiti API wiring so other project plugins can reuse it
3. `.opencode/plugin/README.md`
   - Quick start: installation, configuration, verification checklist
   - Links to the full integration guide and troubleshooting recipes
4. `.opencode.backup/plugin/README.md`
   - Migration notice that archives the deprecated TypeScript (v1/v2) sources
5. `docs/integrations/OPENCODE_PLUGIN_INTEGRATION.md`
   - Canonical documentation covering architecture, buffering logic, troubleshooting, and history

## Installation Workflow
1. Copy or symlink the JavaScript plugins into the OpenCode global directory (`/root/.config/opencode/plugin/`).
2. Confirm Graphiti API availability, usually via `docker-compose up -d graph` at repository root.
3. Start an OpenCode session; the plugins log readiness, buffer size, and flush cadence.
4. Optionally set environment overrides (examples below) to customize grouping or buffer thresholds.

```bash
export GRAPHITI_API_URL="http://localhost:8003"
export GRAPHITI_BUFFER_SIZE="6"
export GRAPHITI_AUTO_COLLECT="true"
export GRAPHITI_GROUP_ID="opencode-graphiti"
```

## Operational Notes
- **Buffering & Flush:** Default buffer of six messages with a 60s auto-flush; either condition triggers a summary push.
- **AI Summaries:** Uses OpenCode SDK; gracefully falls back to truncated plaintext when the SDK is offline.
- **Episode Types:** Session start, buffered summary, and session end entries keep the timeline compact.
- **File Harvesting:** References files mentioned in either user or assistant turns and attaches them to the episode payload.
- **Git Context:** Records current branch and HEAD commit to anchor summaries to repository history.

## Troubleshooting Snapshot
- Missing logs → verify plugin placement and permissions in `/root/.config/opencode/plugin`.
- No episodes → confirm Graphiti API health (`curl http://localhost:8003/health`) and buffer flush triggers.
- CRLF issues → run `sed -i 's/\r$//'` on plugin and hook directories.
- Duplicate episodes → ensure only one plugin instance (remove stale TypeScript versions or extra copies).

## Development History
- **v1 (TypeScript + granular episodes):** functional but required local npm resolution and produced excessive knowledge nodes.
- **v2 (JavaScript, still granular):** resolved module loading but retained noisy per-message uploads.
- **v3 (current JavaScript bundle):** introduces buffering, AI summarization, dynamic grouping, and consolidated episodes.

## Related References
- `docs/integrations/OPENCODE_PLUGIN_INTEGRATION.md` – full architecture and configuration reference
- `.opencode/plugin/README.md` – quick start and day-to-day operational guidance
- `.opencode.backup/plugin/` – deprecated TypeScript sources for historical context
