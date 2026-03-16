# Documentation Maintenance Guide

> **Keywords**: `docs`, `maintenance`, `fresh`, `stale`, `update`, `keep-fresh`

## The Problem

Documentation rot is inevitable without active maintenance. When docs go stale:
- AI agents waste context on outdated information
- Users follow broken instructions
- Trust in documentation erodes

## Maintenance Mechanisms

### 1. Agent Prompt Enforcement

**AGENTS.md already includes**: Session completion workflow that mentions documentation updates.

**To enforce**: Before any code change, check if docs need updating:

```markdown
## Before Changing Code

Ask yourself:
1. Does this change affect a documented API endpoint?
2. Does this change a documented workflow?
3. Does this add a new feature that should be documented?
4. Does this deprecate or remove documented functionality?

If YES to any → Update relevant doc BEFORE merging.
```

### 2. Pre-commit Hook (Optional)

Create `.git/hooks/pre-commit` to check for doc updates:

```bash
#!/bin/bash
# Check if code changes require doc updates

# Files that changed
CHANGED_CODE=$(git diff --cached --name-only | grep -E '\.(py|ts|tsx|rs)$' | head -20)
CHANGED_DOCS=$(git diff --cached --name-only | grep -E 'docs/.*\.md$')

if [ -n "$CHANGED_CODE" ] && [ -z "$CHANGED_DOCS" ]; then
    echo "⚠️  Code changed but no docs updated."
    echo "   Consider if documentation needs updating:"
    echo "   $CHANGED_CODE"
    echo ""
    echo "   To skip this check: git commit --no-verify"
fi
```

### 3. Doc Freshness Check

Run periodically to find stale docs:

```bash
# Find docs not updated in 90 days
find docs -name "*.md" -mtime +90 -exec ls -la {} \;

# Check for broken links
grep -r "\[.*\](.*\.md)" docs/ | while read line; do
    file=$(echo "$line" | grep -oP '\(\K[^)]+')
    if [ ! -f "docs/$file" ] && [ ! -f "$file" ]; then
        echo "Broken link: $line"
    fi
done
```

Index coverage policy:
- Official docs are enforced in indexes: `docs/how-to/`, `docs/reference/`, `docs/explanation/`, `docs/tutorials/`, plus root docs `docs/INDEX.md`, `docs/gotchas.md`, `docs/MAINTENANCE.md`.
- Supplemental analysis/report docs outside those areas are allowed without `docs/INDEX.md` entries.

### 4. CI Check (GitHub Action)

```yaml
# .github/workflows/docs-check.yml
name: Documentation Check

on:
  pull_request:
    paths:
      - 'graphiti_core/**'
      - 'server/**'
      - 'mcp_server/**'
      - 'docs/**'

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Check for doc updates
        run: |
          CODE_CHANGED=$(git diff --name-only origin/main...HEAD | grep -E '\.(py|ts|tsx)$' || true)
          DOCS_CHANGED=$(git diff --name-only origin/main...HEAD | grep -E 'docs/.*\.md$' || true)
          
          if [ -n "$CODE_CHANGED" ] && [ -z "$DOCS_CHANGED" ]; then
            echo "::warning::Code changed but no documentation updated"
            echo "Changed files:"
            echo "$CODE_CHANGED"
          fi
      
      - name: Check markdown links
        run: |
          find docs -name "*.md" -exec grep -H '\[.*\](.*\.md)' {} \; | \
          while IFS=: read file content; do
            link=$(echo "$content" | grep -oP '\]\(\K[^)]+')
            dir=$(dirname "$file")
            target="$dir/$link"
            if [ ! -f "$target" ]; then
              echo "::error file=$file::Broken link to $link"
            fi
          done || true
```

### 5. Doc Ownership Tags

Add ownership metadata to each doc:

```markdown
<!-- 
DOC_OWNERSHIP:
- owner: @team-or-person
- last_reviewed: 2026-03-12
- freshness_check: quarterly
- related_code: graphiti_core/prompts/extract_nodes.py
-->
```

### 6. Automated Doc Generation

Some docs can be auto-generated:

```bash
# Generate API reference from OpenAPI spec
# (if/when OpenAPI spec exists)

# Generate schema reference from code
python3 scripts/generate_schema_docs.py

# Check for missing docs
python3 scripts/check_doc_coverage.py
```

---

## What to Update When

| Code Change | Doc to Update |
|-------------|---------------|
| New API endpoint | `docs/reference/api-reference.md`, `docs/how-to/add-api-endpoint.md` |
| Changed env variable | `docs/reference/config-reference.md` |
| New node/edge type | `docs/reference/schema-reference.md` |
| Pipeline change | `docs/explanation/ingestion-pipeline.md` |
| New service | `docs/explanation/architecture.md` |
| New gotcha | `docs/gotchas.md` |
| New common task | `docs/how-to/*.md`, `docs/INDEX.md` |

---

## Quick Commands

```bash
# Check doc freshness
find docs -name "*.md" -mtime +90 -exec ls -la {} \;

# Check for broken internal links
grep -r "\[.*\](.*\.md)" docs/ | grep -v node_modules

# Find docs mentioning a file
grep -r "graphiti_core/prompts/extract" docs/

# Check known stale references (paths/ports/endpoints)
python3 scripts/check_docs.py --consistency

# Count total doc lines
find docs -name "*.md" -exec cat {} \; | wc -l
```

---

## Responsibility

**Primary**: Developer making code changes
**Reviewer**: Should check docs are updated in PR review
**AI Agents**: Should follow AGENTS.md instructions to update docs

---

## See Also

- [../AGENTS.md](../AGENTS.md) - Session completion workflow
- [INDEX.md](INDEX.md) - Documentation index
