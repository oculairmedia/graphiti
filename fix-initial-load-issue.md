# Fix Initial Load Issue - Cosmograph DuckDB Schema Mismatch

## Problem Analysis

The initial graph load is failing because Cosmograph v2.0's internal DuckDB validation expects specific column names and structure that don't match our current data schema. The error occurs when Cosmograph tries to query its internal `cosmograph_links` table with columns that don't exist.

### Root Cause
1. **Schema Mismatch**: Cosmograph v2.0 expects `sourceIndex` and `targetIndex` columns in the links data
2. **Column Naming**: Our DuckDB schema uses `sourceidx` and `targetidx` but Cosmograph expects different names
3. **Data Validation**: Cosmograph's internal DuckDB validation fails on initial load before delta updates can work

### Current State
- ✅ Delta updates work correctly (webhook test successful)
- ❌ Initial load fails due to DuckDB schema validation
- ✅ Rust backend has correct schema with `sourceidx`/`targetidx`
- ❌ Frontend configuration doesn't match Cosmograph expectations

## Solution Plan

### Phase 1: Fix Column Mapping (Immediate Fix)
**Estimated Time: 30 minutes**

Based on Cosmograph documentation analysis:
- `pointIndexBy`: "Numeric index column for each point. Used for efficient lookups and should be a sequential integer starting from 0."
- `linkSourceIndexBy`: "The column name for the index of the source point of each link. This is used for efficient lookups and should match the pointIndexBy values in the points data."
- `linkTargetIndexBy`: "The column name for the index of the target point of each link. This is used for efficient lookups and should match the pointIndexBy values in the points data."

**Root Cause Confirmed**: Our schema uses `sourceidx`/`targetidx` but Cosmograph expects standard index column names that match the `pointIndexBy` pattern.

1. **Update GraphCanvas Configuration**
   - Fix the `linkSourceIndexBy` and `linkTargetIndexBy` properties in GraphCanvas.tsx
   - Current: `linkSourceIndexBy={useDuckDBTables ? "sourceidx" : "sourceIndex"}`
   - Should be: `linkSourceIndexBy={useDuckDBTables ? "sourceIndex" : "sourceIndex"}`

2. **Verify DuckDB Service Column Names**
   - Check if `getEdgesTable()` returns the correct column names
   - Ensure Arrow table schema matches Cosmograph expectations

### Phase 2: Schema Standardization (Robust Fix)
**Estimated Time: 45 minutes**

1. **Update Rust Backend Schema**
   - Modify `duckdb_store.rs` to use standard column names
   - Change `sourceidx` → `sourceIndex` and `targetidx` → `targetIndex`
   - Update all SQL queries and Arrow schema definitions

2. **Update Frontend DuckDB Service**
   - Modify `duckdb-service.ts` to use standard column names
   - Update table creation and query logic
   - Ensure consistency with Rust backend

3. **Update GraphCanvas Configuration**
   - Simplify column mapping to use standard names
   - Remove conditional logic for DuckDB vs non-DuckDB cases

### Phase 3: Data Validation & Error Handling
**Estimated Time: 30 minutes**

1. **Add Schema Validation**
   - Implement validation in DuckDB service to check required columns
   - Add error handling for schema mismatches
   - Provide clear error messages for debugging

2. **Improve Error Recovery**
   - Add fallback mechanisms when DuckDB tables fail
   - Implement graceful degradation to non-DuckDB mode
   - Add logging for schema validation issues

## Implementation Steps

### Step 1: Quick Fix - Column Mapping
```typescript
// In GraphCanvas.tsx, update the Cosmograph configuration:
linkSourceIndexBy="sourceIndex"  // Remove conditional logic
linkTargetIndexBy="targetIndex"  // Use standard names
```

### Step 2: Backend Schema Update
```rust
// In duckdb_store.rs, update the edge schema:
Field::new("sourceIndex", DataType::UInt32, false),
Field::new("targetIndex", DataType::UInt32, false),

// Update table creation:
CREATE TABLE edges (
    source VARCHAR NOT NULL,
    sourceIndex INTEGER NOT NULL,  // Changed from sourceidx
    target VARCHAR NOT NULL,
    targetIndex INTEGER NOT NULL,  // Changed from targetidx
    edge_type VARCHAR NOT NULL,
    weight DOUBLE NOT NULL DEFAULT 1.0,
    color VARCHAR,
    PRIMARY KEY (source, target, edge_type)
)
```

### Step 3: Frontend Service Update
```typescript
// In duckdb-service.ts, update queries:
SELECT * FROM edges ORDER BY sourceIndex, targetIndex
```

### Step 4: Validation & Testing
1. Test initial load with new schema
2. Verify delta updates still work
3. Test with various graph sizes
4. Validate error handling

## Files to Modify

### High Priority (Phase 1)
1. `frontend/src/components/GraphCanvas.tsx` - Fix column mapping
2. `frontend/src/services/duckdb-service.ts` - Update column names

### Medium Priority (Phase 2)
3. `graph-visualizer-rust/src/duckdb_store.rs` - Standardize schema
4. `graph-visualizer-rust/src/main.rs` - Update queries if needed

### Low Priority (Phase 3)
5. Add validation and error handling across components

## Testing Strategy

### Unit Tests
- Test DuckDB service with new schema
- Validate Arrow table structure
- Test column mapping logic

### Integration Tests
- Test initial graph load with various data sizes
- Verify delta updates continue working
- Test error scenarios and fallbacks

### Performance Tests
- Measure initial load time improvement
- Verify no regression in delta update performance
- Test with large graphs (>10k nodes)

## Risk Assessment

### Low Risk
- Column name changes (backward compatible)
- Frontend configuration updates

### Medium Risk
- Backend schema changes (requires data migration)
- DuckDB service modifications

### High Risk
- Breaking existing delta update functionality
- Performance regression on large graphs

## Success Criteria

1. ✅ Initial graph load works without DuckDB validation errors
2. ✅ Delta updates continue to function correctly
3. ✅ No performance regression
4. ✅ Clear error messages for debugging
5. ✅ Graceful fallback when DuckDB fails

## Rollback Plan

If issues arise:
1. Revert column name changes in GraphCanvas.tsx
2. Restore original DuckDB schema in Rust backend
3. Use non-DuckDB mode as fallback
4. Investigate schema mismatch in isolated environment

## Next Steps After Fix

1. **Performance Optimization**: Optimize initial load performance
2. **Schema Evolution**: Plan for future Cosmograph updates
3. **Monitoring**: Add metrics for load success/failure rates
4. **Documentation**: Update integration documentation
