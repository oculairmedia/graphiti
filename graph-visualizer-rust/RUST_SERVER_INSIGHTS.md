# Graph Visualizer Rust Server: Date Handling Analysis & Implementation Issues

## Executive Summary

The Rust graph visualizer server has **critical date handling inconsistencies** that cause frontend parsing failures. The root cause is **inconsistent type conversion logic** across different code paths, leading to missing or malformed `created_at` timestamps in API responses.

## Current Implementation Analysis

### Architecture Overview
- **Server**: Axum-based REST API (`graph-visualizer-rust/src/main.rs`)
- **Data Flow**: FalkorDB → DuckDB → JSON API responses
- **Node Model**: Timestamps stored in `Node.properties` HashMap, not as top-level fields

```rust
#[derive(Debug, Serialize, Deserialize, Clone)]
struct Node {
    id: String,
    label: String,
    node_type: String,
    summary: Option<String>,
    properties: HashMap<String, serde_json::Value>, // ← created_at lives here
}
```

### API Route Structure
**Missing Routes** (causing curl failures):
- No `GET /` (root endpoint)
- No `GET /api/nodes` (node list endpoint)

**Available Routes**:
```rust
.route("/api/stats", get(get_stats))
.route("/api/visualize", get(visualize))
.route("/api/nodes/:id", get(get_node_by_id))
.route("/api/graph/nodes", get(get_nodes_by_ids))
```

## The Date Handling Problem

### Problem 1: Inconsistent Type Conversion Logic

**Initial Load Path** (lines 342-345):
```rust
// Add created_at timestamp
if let Some(created) = row.get(4).and_then(|v| v.as_string()) {
    properties.insert("created_at".to_string(), serde_json::Value::String(created.to_string()));
}
```
**Issue**: Only processes `created_at` if FalkorDB returns it as a string. Numeric timestamps (epoch seconds/millis) are **silently dropped**.

**Entire Graph Path** (lines 944-957):
```rust
let created_at = value_to_string(&row[6]);
...
if !created_at.is_empty() {
    node_props.insert("created_at".to_string(), serde_json::Value::String(created_at));
}
```
**Issue**: Uses `value_to_string()` which converts numeric values to strings, but may produce inconsistent formats.

### Problem 2: FalkorValue Conversion Inconsistencies

The `value_to_string()` helper function:
```rust
fn value_to_string(value: &FalkorValue) -> String {
    match value {
        FalkorValue::String(s) => s.clone(),
        FalkorValue::I64(i) => i.to_string(),      // ← Raw number as string
        FalkorValue::F64(f) => f.to_string(),      // ← Raw number as string
        FalkorValue::Bool(b) => b.to_string(),
        FalkorValue::None => String::new(),
        _ => format!("{:?}", value),
    }
}
```

**Critical Issues**:
1. **Epoch timestamps become raw numbers**: `1703123456` instead of `2023-12-20T20:30:56Z`
2. **No format standardization**: Different data types produce different string formats
3. **Frontend parsing failures**: JavaScript `new Date("1703123456")` returns `Invalid Date`

### Problem 3: Data Loss Scenarios

**Scenario A**: FalkorDB stores `created_at` as epoch seconds (numeric)
- Initial load path: **DROPPED** (only accepts strings)
- Entire graph path: **MALFORMED** (raw number string)

**Scenario B**: FalkorDB stores `created_at` as ISO string
- Initial load path: **WORKS** (string accepted)
- Entire graph path: **WORKS** (string passed through)

**Scenario C**: FalkorDB stores `created_at` as epoch milliseconds (numeric)
- Initial load path: **DROPPED** (only accepts strings)
- Entire graph path: **MALFORMED** (raw number string)

## Frontend Impact Analysis

### JavaScript Date Parsing Behavior
```javascript
// These FAIL:
new Date("1703123456")        // Invalid Date
new Date("1703123456000")     // Invalid Date

// These WORK:
new Date("2023-12-20T20:30:56Z")  // Valid Date object
new Date(1703123456000)           // Valid Date object (numeric)
```

### Current Frontend Symptoms
- **Missing timestamps**: Nodes appear without creation dates
- **Invalid Date objects**: Frontend date parsing throws errors
- **Inconsistent sorting**: Timeline views break due to unparseable dates
- **UI rendering issues**: Date-dependent components fail gracefully or crash

## Root Cause Analysis

### 1. Type System Mismatch
- **FalkorDB**: Stores dates as various types (string, i64, f64)
- **Rust Server**: Inconsistent conversion logic across code paths
- **Frontend**: Expects standardized date format (ISO 8601 or numeric epoch)

### 2. Missing Normalization Layer
The server lacks a **centralized date normalization function** that:
- Detects date format (string vs numeric)
- Converts to consistent output format
- Handles edge cases (invalid dates, null values)

### 3. Code Path Divergence
Two different loading mechanisms use **different conversion strategies**:
- Initial load: String-only filtering
- Entire graph: Generic string conversion

## Recommended Solution

### Phase 1: Implement Date Normalization

Add a centralized normalization function:
```rust
fn normalize_created_at(value: &FalkorValue) -> Option<serde_json::Value> {
    match value {
        // Handle string dates
        FalkorValue::String(s) => {
            // Try parsing as RFC3339/ISO 8601
            if let Ok(dt) = chrono::DateTime::parse_from_rfc3339(s) {
                return Some(serde_json::Value::String(dt.with_timezone(&chrono::Utc).to_rfc3339()));
            }
            // Try parsing as epoch string
            if let Ok(epoch) = s.parse::<i64>() {
                return epoch_to_iso8601(epoch);
            }
            // Keep original string if it looks like a date
            if s.contains('-') || s.contains('T') {
                return Some(serde_json::Value::String(s.clone()));
            }
            None
        }
        // Handle numeric epochs
        FalkorValue::I64(epoch) => epoch_to_iso8601(*epoch),
        FalkorValue::F64(epoch) => epoch_to_iso8601(*epoch as i64),
        _ => None,
    }
}

fn epoch_to_iso8601(epoch: i64) -> Option<serde_json::Value> {
    // Auto-detect seconds vs milliseconds
    let millis = if epoch > 10_000_000_000 { epoch } else { epoch * 1000 };

    if let Some(naive) = chrono::NaiveDateTime::from_timestamp_millis(millis) {
        let dt = chrono::DateTime::<chrono::Utc>::from_utc(naive, chrono::Utc);
        Some(serde_json::Value::String(dt.to_rfc3339()))
    } else {
        None
    }
}
```

### Phase 2: Update Both Code Paths

**Replace Initial Load Logic**:
```rust
// OLD: String-only filtering
if let Some(created) = row.get(4).and_then(|v| v.as_string()) {
    properties.insert("created_at".to_string(), serde_json::Value::String(created.to_string()));
}

// NEW: Normalized conversion
if let Some(created_at) = normalize_created_at(&row[4]) {
    properties.insert("created_at".to_string(), created_at);
}
```

**Replace Entire Graph Logic**:
```rust
// OLD: Generic string conversion
let created_at = value_to_string(&row[6]);
if !created_at.is_empty() {
    node_props.insert("created_at".to_string(), serde_json::Value::String(created_at));
}

// NEW: Normalized conversion
if let Some(created_at) = normalize_created_at(&row[6]) {
    node_props.insert("created_at".to_string(), created_at);
}
```

### Phase 3: Add Dual Format Support (Optional)

For maximum frontend compatibility, provide both formats:
```rust
if let Some(created_at_iso) = normalize_created_at(&row[4]) {
    properties.insert("created_at".to_string(), created_at_iso);

    // Also provide epoch millis for easy sorting/filtering
    if let Ok(dt) = chrono::DateTime::parse_from_rfc3339(created_at_iso.as_str().unwrap()) {
        properties.insert("created_at_epoch_ms".to_string(),
                         serde_json::Value::Number(dt.timestamp_millis().into()));
    }
}
```

## Testing Strategy

### 1. Unit Tests
```rust
#[cfg(test)]
mod tests {
    #[test]
    fn test_normalize_created_at_epoch_seconds() {
        let value = FalkorValue::I64(1703123456);
        let result = normalize_created_at(&value);
        assert_eq!(result, Some(serde_json::Value::String("2023-12-20T20:30:56Z".to_string())));
    }

    #[test]
    fn test_normalize_created_at_iso_string() {
        let value = FalkorValue::String("2023-12-20T20:30:56Z".to_string());
        let result = normalize_created_at(&value);
        assert_eq!(result, Some(serde_json::Value::String("2023-12-20T20:30:56Z".to_string())));
    }
}
```

### 2. Integration Tests
```bash
# Test API responses contain valid ISO 8601 dates
curl -s "http://localhost:3000/api/visualize?query_type=high_degree&limit=5" | \
  jq '.data.nodes[].properties.created_at' | \
  grep -E '^"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"$'
```

## Implementation Priority

1. **HIGH**: Fix date normalization (prevents data loss)
2. **MEDIUM**: Add unit tests (prevents regressions)
3. **LOW**: Add health endpoint (improves debugging)

## Expected Outcomes

- **100% date preservation**: No more dropped timestamps
- **Consistent format**: All dates as ISO 8601 strings
- **Frontend compatibility**: JavaScript Date parsing works reliably
- **Improved UX**: Timeline views and date sorting function correctly

---
*Analysis based on source code review of `graph-visualizer-rust/src/main.rs` - Lines 342-345, 944-957, 1237-1255*

