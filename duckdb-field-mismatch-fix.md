# DuckDB Field Mismatch Fix - Incremental Updates

## Problem Description

The frontend was experiencing a critical error during incremental graph updates with the following error message:

```
[sanitizeNode] CRITICAL: DuckDB requires exactly 14 non-null fields. Have 15 fields with 0 nulls: 
(15) ['index: number', 'id: string', 'label: string', 'node_type: string', 'summary: string', 'degree_centrality: number', 'pagerank_centrality: number', 'betweenness_centrality: number', 'eigenvector_centrality: number', 'color: string', 'size: number', 'colorValue: number', 'cluster: string', 'clusterStrength: number', 'created_at_timestamp: number']
```

This error occurred in the `GraphCanvasV2.tsx` component during incremental data updates, specifically in the `sanitizeNode` function within `prepareIncrementalData`.

## Root Cause Analysis

### Schema Mismatch Investigation

1. **DuckDB Schema**: The actual `cosmograph_points` view in DuckDB expects **16 fields**:
   ```sql
   SELECT 
     idx as index, 
     id, 
     label, 
     node_type, 
     summary, 
     degree_centrality,
     pagerank_centrality,
     betweenness_centrality,
     eigenvector_centrality,
     x, 
     y, 
     color, 
     size,
     created_at_timestamp,
     NULL as cluster,
     NULL as clusterStrength
   FROM nodes
   ```

2. **Incremental Update Function**: The `sanitizeNode` function for incremental updates was creating **15 fields**:
   - ✅ Included: `index`, `id`, `label`, `node_type`, `summary`, `degree_centrality`, `pagerank_centrality`, `betweenness_centrality`, `eigenvector_centrality`, `color`, `size`, `colorValue`, `cluster`, `clusterStrength`, `created_at_timestamp`
   - ❌ Missing: `x`, `y` (required by cosmograph_points view)
   - ❌ Extra: `colorValue` (not in cosmograph_points view)

3. **Outdated Comments**: The function comments incorrectly stated "exactly 14 NON-NULL fields" when the actual schema requires 16 fields.

### The Core Issue

The `sanitizeNode` function in `frontend/src/utils/cosmographDataPreparer.ts` had diverged from the actual DuckDB schema:

- **Expected by DuckDB**: 16 fields matching the `cosmograph_points` view
- **Provided by sanitizeNode**: 15 fields with incorrect field composition
- **Result**: DuckDB rejected the incremental updates causing the error

## Solution Applied

### 1. Updated Field Composition for Incremental Updates

**Removed:**
- `colorValue` field (not in cosmograph_points schema)

**Added:**
- `x` field (set to `null` for incremental updates)
- `y` field (set to `null` for incremental updates)

### 2. Updated Field Count Validation

Changed the validation logic from expecting 14 fields to 16 fields:

```typescript
// Before
if (fieldCount !== 14 || nullCount > 0) {
  console.error(`[sanitizeNode] CRITICAL: DuckDB requires exactly 14 non-null fields...`);
}

// After  
if (fieldCount !== 16 || unexpectedNulls.length > 0) {
  console.error(`[sanitizeNode] CRITICAL: DuckDB cosmograph_points view requires exactly 16 fields...`);
}
```

### 3. Enhanced Null Value Handling

Added logic to allow `x` and `y` fields to be null for incremental updates (they'll be computed by Cosmograph):

```typescript
const allowedNulls = ['x', 'y']; // These fields can be null for incremental updates
const unexpectedNulls = actualNulls.filter(field => !allowedNulls.includes(field));
```

### 4. Updated Comments and Documentation

- Updated function comments to reflect the correct 16-field requirement
- Updated debugging documentation in `frontend/docs/COSMOGRAPH_DEBUGGING.md`
- Clarified the schema expectations for incremental vs initial loads

## Technical Details

### Schema Alignment

The fix ensures the incremental update data structure exactly matches the `cosmograph_points` view:

| Field | Type | Incremental Value | Notes |
|-------|------|------------------|-------|
| index | number | Node index | ✅ |
| id | string | Node ID | ✅ |
| label | string | Node label | ✅ |
| node_type | string | Node type | ✅ |
| summary | string | Node summary | ✅ |
| degree_centrality | number | Centrality value | ✅ |
| pagerank_centrality | number | Centrality value | ✅ |
| betweenness_centrality | number | Centrality value | ✅ |
| eigenvector_centrality | number | Centrality value | ✅ |
| x | number/null | null | ✅ Computed by Cosmograph |
| y | number/null | null | ✅ Computed by Cosmograph |
| color | string | Generated color | ✅ |
| size | number | Node size | ✅ |
| created_at_timestamp | number | Timestamp | ✅ |
| cluster | string | Cluster name | ✅ |
| clusterStrength | number | Cluster strength | ✅ |

### Code Changes Made

**File: `frontend/src/utils/cosmographDataPreparer.ts`**

1. **Lines 153-188**: Updated incremental update field creation
2. **Lines 214-227**: Updated field count validation logic
3. **Comments**: Updated to reflect correct schema requirements

## Files Modified

- `frontend/src/utils/cosmographDataPreparer.ts` - Core fix for field mismatch
- `frontend/docs/COSMOGRAPH_DEBUGGING.md` - Updated documentation

## Verification Steps

To verify the fix is working:

1. **Check Console**: The error `[sanitizeNode] CRITICAL: DuckDB requires exactly 14 non-null fields` should no longer appear
2. **Test Incremental Updates**: Perform actions that trigger incremental updates (adding nodes, WebSocket updates)
3. **Monitor Field Count**: Console should show successful field validation for 16 fields
4. **Verify Graph Rendering**: Incremental updates should render correctly without fallback to full reloads

## Impact

- ✅ **Fixed**: DuckDB field mismatch errors during incremental updates
- ✅ **Improved**: Schema validation and error reporting
- ✅ **Enhanced**: Documentation accuracy
- ✅ **Maintained**: Backward compatibility with existing data

## Additional Fix: Inconsistent View Definitions

### Secondary Issue Discovered

After the initial fix, a new error appeared:
```
Binder Error: table cosmograph_points has 15 columns but 14 values were supplied
```

### Root Cause

The DuckDB service had **three different cosmograph_points view definitions**:

1. **Line 266**: `SELECT * FROM nodes` (17 columns - all from nodes table)
2. **Lines 181-199**: Explicit 16-column view with `NULL as cluster, NULL as clusterStrength`
3. **Lines 349-367**: Same explicit 16-column view with `NULL as cluster, NULL as clusterStrength`

The inconsistency meant different code paths created different schemas.

### Final Solution

**Standardized all view definitions** to use the actual columns from the nodes table:

```sql
CREATE OR REPLACE VIEW cosmograph_points AS
SELECT
  idx as index,
  id,
  label,
  node_type,
  summary,
  degree_centrality,
  pagerank_centrality,
  betweenness_centrality,
  eigenvector_centrality,
  x,
  y,
  color,
  size,
  created_at_timestamp,
  cluster,        -- Now uses actual column instead of NULL
  clusterStrength -- Now uses actual column instead of NULL
FROM nodes
```

This ensures all code paths create the same 16-column view that matches our sanitizeNode output.

## Next Steps

1. Monitor for any remaining schema-related issues
2. Consider adding automated tests for schema validation
3. Review other components that might have similar schema assumptions
4. Update any remaining outdated field count references in the codebase
5. Add schema consistency checks to prevent future view definition drift
