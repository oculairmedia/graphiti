# Cosmograph Schema Debugging

This document describes the debugging utilities available for troubleshooting Cosmograph DuckDB schema mismatches.

## Overview

Cosmograph uses an internal DuckDB instance that expects specific column counts and types. When there's a mismatch, you'll see errors like:
- `Binder Error: table cosmograph_points has 16 columns but 15 values were supplied`
- `Unable to infer Vector type from input values`

## Enabling Debug Mode

Debug mode is **disabled by default** to keep console output clean. You can enable it in three ways:

### 1. Via Browser Console (Easiest)
```javascript
// Enable debugging
window.enableSchemaDebug()
// Then refresh the page

// To disable
window.disableSchemaDebug()
// Then refresh the page
```

### 2. Via URL Parameter
Add `?debug_cosmograph_schema=true` to your URL:
```
http://localhost:8082/?debug_cosmograph_schema=true
```

### 3. Via Environment Variable
Set in your `.env` file:
```bash
VITE_DEBUG_COSMOGRAPH_SCHEMA=true
```

## What Gets Logged

When debug mode is enabled, you'll see:

1. **Cosmograph Internal Structure**
   - Internal keys and properties
   - DuckDB-related properties
   - Method signatures

2. **Field Analysis**
   - Exact fields being sent to Cosmograph
   - Field count and types
   - Sample data structure

3. **Schema Mismatches**
   - Expected vs actual column counts
   - Field type issues
   - Missing or extra fields

## Example Debug Output

```
[Schema Debug] Cosmograph internal keys: ['_dataManager', '_dbReadinessPromise', ...]
[Schema Debug] Sample point fields: ['index', 'id', 'label', 'node_type', ...]
[Schema Debug] Sample point field count: 18
[useCosmographIncrementalUpdates] Exact fields being sent: ['index', 'id', ...]
[useCosmographIncrementalUpdates] Field count: 14
```

## Common Issues and Solutions

### Issue: Column Count Mismatch
**Error**: `table cosmograph_points has 16 columns but 15 values were supplied`

**Solution**: The schema differs between initial load and incremental updates. The `sanitizeNode` function in `cosmographDataPreparer.ts` handles this by conditionally including fields based on the `isIncremental` flag.

### Issue: Vector Type Inference
**Error**: `Unable to infer Vector type from input values`

**Solution**: This occurs when non-primitive types (arrays, objects) are sent. All fields must be strings, numbers, booleans, or null.

## Architecture

The debugging system consists of:

1. **`debugCosmographSchema.ts`**: Core debugging utilities
   - `isSchemaDebuggingEnabled()`: Checks if debugging is enabled
   - `inspectCosmographSchema()`: Inspects Cosmograph internal structure
   - `attachSchemaDebugger()`: Attaches debugging functions to window

2. **Integration Points**:
   - `GraphCanvasV2.tsx`: Inspects schema on mount (if enabled)
   - `useCosmographIncrementalUpdates.ts`: Logs field details during updates

## Performance Impact

When debug mode is **disabled** (default):
- No performance impact
- No console logging
- No schema inspection

When debug mode is **enabled**:
- Minimal performance impact
- Additional console logging
- Schema inspection on mount only

## Troubleshooting Tips

1. **Enable debug mode first** before reproducing the issue
2. **Check field counts** - Cosmograph expects exact counts
3. **Verify field types** - All must be primitives
4. **Compare initial vs incremental** - They may have different schemas
5. **Check the browser console** for DuckDB errors

## Related Files

- `/src/utils/cosmographDataPreparer.ts` - Data sanitization and preparation
- `/src/utils/debugCosmographSchema.ts` - Debug utilities
- `/src/hooks/useCosmographIncrementalUpdates.ts` - Incremental update logic
- `/src/components/GraphCanvasV2.tsx` - Main graph component