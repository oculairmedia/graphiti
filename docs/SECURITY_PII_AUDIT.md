# Graphiti PII Logging Audit Report

## Summary
Found **4 HIGH-RISK** logging statements that expose entity/relationship metadata. ResponseLogger includes safeguards with truncation.

---

## CRITICAL FINDINGS

### 🔴 HIGH RISK: Raw Entity Names in Logs

**File**: `graphiti_core/ingestion/worker.py`

| Line | Severity | Issue | Log Statement |
|------|----------|-------|---------------|
| 673 | 🔴 HIGH | Logs actual entity name | `logger.info(f"Entity '{entity_name}' already exists with UUID {existing_uuid}")` |
| 708 | 🔴 HIGH | Logs entity name from payload | `logger.debug(f'Entity already exists: {payload.get("name")}')` |
| 810 | 🔴 HIGH | Logs 3 entity names + edge name | `logger.info(f'Created relationship: {source_node.name} -> {edge.name} -> {target_node.name}')` |

**Why this is PII risk**:
- Entity names could contain user references, personal info, or sensitive business data
- Direct interpolation without sanitization or truncation
- Appears in standard application logs

**Example exposure**:
```python
# Input: entity_name = "John Smith works at Acme Corp"
logger.info(f"Entity '{entity_name}' already exists with UUID {uuid}")
# Output: Entity 'John Smith works at Acme Corp' already exists with UUID 12345...
```

---

### 🟡 MEDIUM RISK: Relationship Metadata (Line 810)

**File**: `graphiti_core/ingestion/worker.py:810`

The relationship logging exposes:
- **source_node.name** - entity name
- **edge.name** - relationship type/label  
- **target_node.name** - entity name

This is the **most verbose PII exposure** in the codebase.

---

## ✅ SAFE PATTERNS (No PII)

### ResponseLogger (SANITIZED)
**File**: `graphiti_core/dspy/response_logger.py`

Good practices:
- **Line 264-268**: `_truncate_message()` limits message length
- **Line 370, 438, 508, 571**: Current messages truncated to `max_message_length` (default 10,000 chars)
- **Line 618**: Episode content preview truncated to first 500 chars
- **Lines 358-366**: Extracted entity data stored as `{'name': e.name, 'entity_type_id': e.entity_type_id}` — structured, not raw interpolated

**Verdict**: ResponseLogger is safe for training data collection.

---

## Consolidated Workflows (SAFE)

**File**: `graphiti_core/utils/consolidation/activities.py`

Logging patterns are safe:
- Line 346: Logs entity count only (no names)
- Line 356: Logs UUIDs only: `dup_uuid, canon_uuid`
- Line 453: Generic error messages
- Line 538: `LLM summary generation failed for %s` uses `name` — **RISKY but not in logs, only in format** (parameterized logging)
- Line 557, 621, 627: Generic progress/error messages (no entity data)
- Line 683, 688, 691: Logs query fragments only

**Verdict**: Safe due to parameterized logging (`%s` placeholders instead of f-strings).

---

## Temporal Visibility (Safe)

**Files**: `graphiti_core/utils/temporal_visibility/*`

- Episode UUID logging only (no content)
- Workflow IDs, task queue names
- No user/entity name exposure

---

## Non-Logging Data Exposure

### Response Logger Content Storage (SAFE)
**File**: `graphiti_core/dspy/response_logger.py:618`
```python
'content_preview': self._truncate_message(content[:500])
```
- Episode content truncated to 500 chars (line 618)
- Stored in JSONL files, not stdout logs
- `max_message_length` limit (default 10,000)

### DSPy Modules Training Data (SAFE)
**File**: `graphiti_core/dspy/modules.py`

Training data collection truncates inputs:
```python
processed_inputs = {
    'current_message': self._truncate_message(inputs.get('current_message', '')),
    ...
}
```

---

## RECOMMENDATIONS

### Immediate (Align with #1237)

**Fix Line 673**:
```python
# BEFORE
logger.info(f"Entity '{entity_name}' already exists with UUID {existing_uuid}")

# AFTER (redact entity name)
logger.info(f"Entity '{existing_uuid[:8]}...' already exists")
# OR sanitize:
logger.info(f"Entity already exists with UUID {existing_uuid}")
```

**Fix Line 708**:
```python
# BEFORE
logger.debug(f'Entity already exists: {payload.get("name")}')

# AFTER
logger.debug(f'Entity already exists (duplicate detected)')
```

**Fix Line 810** (Most critical):
```python
# BEFORE
logger.info(f'Created relationship: {source_node.name} -> {edge.name} -> {target_node.name}')

# AFTER (log structure instead)
logger.info(f'Created relationship: {source_node.uuid} -> {edge.uuid} -> {target_node.uuid}')
# OR generic:
logger.info('Relationship created successfully')
```

### Best Practice Additions

1. **Use parameterized logging** throughout (already done in consolidation):
   ```python
   # GOOD
   logger.info('Created entity %s', uuid)
   # vs BAD
   logger.info(f'Created entity {entity_name}')
   ```

2. **Create sanitization utility**:
   ```python
   def sanitize_for_logs(value: str, max_len: int = 50) -> str:
       """Truncate and anonymize for logging."""
       if len(value) > max_len:
           return value[:max_len] + '...[truncated]'
       return value  # or hash/uuid replace
   ```

3. **Apply to consolidation.py:538** (currently low-risk but preventive):
   ```python
   logger.warning('LLM summary generation failed for %s', uuid)
   # instead of passing name
   ```

---

## Risk Assessment Matrix

| File | Line(s) | Risk | Type | Fix Priority |
|------|---------|------|------|--------------|
| worker.py | 673 | HIGH | Entity name | **URGENT** |
| worker.py | 708 | HIGH | Entity name | **URGENT** |
| worker.py | 810 | CRITICAL | 3 entity names | **URGENT** |
| consolidation.py | 538 | MEDIUM | Entity name (param) | Medium |
| response_logger.py | All | LOW | Truncated content | None (safe) |

---

## Upstream Comparison (#1237)

Upstream PR #1237 removed PII from logs. Our codebase still contains:
- ✅ No raw message content in stdout (ResponseLogger stores truncated)
- ❌ **Entity names visible in operational logs** (Lines 673, 708, 810)
- ✅ No raw prompts logged
- ✅ No LLM responses logged
- ✅ Consolidation uses parameterized logging (safe)

