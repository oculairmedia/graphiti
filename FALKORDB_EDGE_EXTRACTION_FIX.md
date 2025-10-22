# FalkorDB Edge Extraction Fix - Developer Instructions

**Issue ID:** GRAPH-576 (Critical - Blocking Edge Sync)
**Date:** September 20, 2025
**Status:** 🔴 **IMMEDIATE FIX REQUIRED**
**Priority:** Critical - Zero edges syncing from FalkorDB to Neo4j

## Problem Summary

Edge synchronization from FalkorDB to Neo4j is completely broken. While 4,136 nodes sync successfully, **0 edges** are transferred due to FalkorDB Cypher function incompatibility.

## Root Cause

**FalkorDB does not support `startNode()` and `endNode()` functions** used in the current optimization.

**Current broken code** in `sync_service/extractors/falkordb_extractor.py` lines 35-40:
```python
EDGE_PROPERTY_EXPRESSIONS = {
    'uuid': 'r.uuid',
    'source_uuid': 'startNode(r).uuid',    # ❌ FAILS - Function not supported
    'target_uuid': 'endNode(r).uuid',      # ❌ FAILS - Function not supported
    'created_at': 'r.created_at',
    'updated_at': 'r.updated_at',
    'weight': 'r.weight',
    'valid_at': 'r.valid_at',
    'invalid_at': 'r.invalid_at',
}
```

**Error produced:**
```
errMsg: Invalid input 'N': expected START line: 5, column: 13, offset: 100
errCtx: startNode(r).uuid as source_uuid errCtxOffset: 12
```

## Required Fix

### Step 1: Update Edge Property Expressions

**File:** `sync_service/extractors/falkordb_extractor.py`
**Lines:** 35-40

**Replace the broken expressions with:**
```python
EDGE_PROPERTY_EXPRESSIONS = {
    'uuid': 'r.uuid',
    'source_uuid': 'source.uuid',    # ✅ FIXED - Use pattern match variable
    'target_uuid': 'target.uuid',    # ✅ FIXED - Use pattern match variable
    'created_at': 'r.created_at',
    'updated_at': 'r.updated_at',
    'weight': 'r.weight',
    'valid_at': 'r.valid_at',
    'invalid_at': 'r.invalid_at',
}
```

### Step 2: Update Query Pattern in extract_entity_edges_optimized()

**File:** `sync_service/extractors/falkordb_extractor.py`
**Function:** `extract_entity_edges_optimized()`
**Approximate Line:** ~500-550

**Find the query that looks like:**
```python
query = f"""
MATCH ()-[r:RELATES_TO]->()
RETURN {property_expressions}
ORDER BY r.uuid
SKIP {offset} LIMIT {page_limit}
"""
```

**Replace with:**
```python
query = f"""
MATCH (source)-[r:RELATES_TO]->(target)
RETURN {property_expressions}
ORDER BY r.uuid
SKIP {offset} LIMIT {page_limit}
"""
```

**Key change:** `()-[r:RELATES_TO]->()` → `(source)-[r:RELATES_TO]->(target)`

This gives us access to `source.uuid` and `target.uuid` variables in the property expressions.

## Verification Steps

### Step 1: Test Query in FalkorDB
```bash
docker exec graphiti-falkordb-1 redis-cli GRAPH.QUERY graphiti_migration \
  "MATCH (source)-[r:RELATES_TO]->(target) RETURN r.uuid, source.uuid, target.uuid LIMIT 3"
```

**Expected:** Should return edge UUIDs with source and target UUIDs (no errors)

### Step 2: Test Edge Extraction
```bash
docker exec graphiti-sync-service-1 python -c "
import asyncio
from extractors.falkordb_extractor import FalkorDBExtractor

async def test():
    ext = FalkorDBExtractor(host='falkordb', port=6379, database='graphiti_migration')
    await ext.connect()
    async for batch in ext.extract_entity_edges():
        print(f'SUCCESS: Got {len(batch)} edges')
        break
    await ext.disconnect()

asyncio.run(test())
"
```

**Expected:** Should print "SUCCESS: Got X edges" without errors

### Step 3: Full Sync Test
```bash
# Clear Neo4j
docker exec graphiti-neo4j-1 cypher-shell -u neo4j -p demodemo "MATCH (n) DETACH DELETE n"

# Restart sync service
docker-compose restart sync-service

# Wait 3 minutes then check edge count
docker exec graphiti-neo4j-1 cypher-shell -u neo4j -p demodemo "MATCH ()-[r]->() RETURN count(r)"
```

**Expected:** Should show ~7,366 edges (not 0)

## Why This Fix Works

1. **Tested Pattern**: `MATCH (source)-[r:RELATES_TO]->(target)` is verified working in FalkorDB
2. **Direct Property Access**: Uses `source.uuid` and `target.uuid` instead of unsupported functions
3. **FalkorDB Compatible**: Only uses basic Cypher syntax that FalkorDB supports
4. **Maintains Performance**: Still uses optimized direct edge access (not full property expansion)

## Files to Modify

1. **Primary:** `sync_service/extractors/falkordb_extractor.py`
   - Update `EDGE_PROPERTY_EXPRESSIONS` (lines 35-40)
   - Update query pattern in `extract_entity_edges_optimized()`

## Deployment

After making changes:
```bash
# Commit and push changes
git add sync_service/extractors/falkordb_extractor.py
git commit -m "fix: Use FalkorDB-compatible pattern match for edge extraction

- Replace unsupported startNode()/endNode() functions with source.uuid/target.uuid
- Update query pattern to MATCH (source)-[r]->(target) for variable access
- Fixes GRAPH-576: Zero edge sync issue"

git push origin feature/chutes-ai-integration

# Pull new image and test
docker-compose pull sync-service
docker-compose restart sync-service
```

## Expected Results

- ✅ **Edge extraction succeeds**: No syntax errors in logs
- ✅ **Edges sync to Neo4j**: ~7,366 edges transferred
- ✅ **Sync completes**: `last_sync` timestamp appears in health endpoint
- ✅ **Logs show progress**: "Executing edge query" and "Query completed" messages

## Confidence Level

**Very High** - The pattern `MATCH (source)-[r:RELATES_TO]->(target)` is tested and working in the current FalkorDB instance. This fix reverts to proven syntax while maintaining optimization benefits.