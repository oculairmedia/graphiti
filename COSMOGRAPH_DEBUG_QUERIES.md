# Cosmograph Incremental Updates Debug Queries

This document contains queries and information requests needed to properly debug and fix the Cosmograph incremental update API issues.

> **Note**: This system is now using the refactored graph components. See `SYSTEM_INSIGHTS.md` for current architecture.

## Context

We're experiencing two critical errors when attempting to use Cosmograph's incremental update API:
1. **Vector Type Inference Error** - When calling `addPoints()`
2. **DuckDB Schema Mismatch** - When calling `addLinks()`

## System Information Needed

### 1. Cosmograph Internal Schema

#### Points/Nodes Schema
```javascript
// Need to understand the exact schema Cosmograph expects
// Current error: "Unable to infer Vector type from input values"

// Questions:
// 1. What are ALL the required fields for a point?
// 2. Which fields must be typed as numbers vs strings?
// 3. Are there any fields that MUST NOT be included?
// 4. What's the difference between initial data load vs incremental adds?

// Query commands needed:
cosmographRef.current?._duckdb?.query("DESCRIBE cosmograph_points")
cosmographRef.current?._duckdb?.query("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'cosmograph_points'")
cosmographRef.current?._duckdb?.query("SELECT * FROM cosmograph_points LIMIT 1") // See actual data structure
```

#### Links/Edges Schema
```javascript
// Error: "table cosmograph_links has 15 columns but 6 values were supplied"

// Questions:
// 1. What are ALL 15 columns in cosmograph_links table?
// 2. Which columns are required vs optional?
// 3. What are the correct data types for each column?
// 4. Can we pass null/undefined for unused columns?

// Query commands needed:
cosmographRef.current?._duckdb?.query("DESCRIBE cosmograph_links")
cosmographRef.current?._duckdb?.query("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'cosmograph_links'")
cosmographRef.current?._duckdb?.query("SELECT * FROM cosmograph_links LIMIT 1") // See actual data structure
```

### 2. Initial Data Structure Analysis

```javascript
// Need to compare initial load vs incremental add data structures

// Initial load (working):
console.log("Initial nodes sample:", nodes.slice(0, 2))
console.log("Initial links sample:", links.slice(0, 2))
console.log("Initial node keys:", Object.keys(nodes[0] || {}))
console.log("Initial link keys:", Object.keys(links[0] || {}))

// During incremental add (failing):
console.log("Incremental node being added:", transformedNodes[0])
console.log("Incremental link being added:", transformedEdges[0])
console.log("Node type check:", typeof transformedNodes[0].index, typeof transformedNodes[0].size)
```

### 3. Cosmograph Configuration State

```javascript
// Understanding how Cosmograph is configured
console.log("Cosmograph config:", {
  pointIdBy: cosmographRef.current?.config?.pointIdBy,
  pointIndexBy: cosmographRef.current?.config?.pointIndexBy,
  linkSourceBy: cosmographRef.current?.config?.linkSourceBy,
  linkTargetBy: cosmographRef.current?.config?.linkTargetBy,
  // All other relevant config
})

// Check if there's a type registry or schema definition
console.log("Type definitions:", cosmographRef.current?._typeDefinitions)
console.log("Schema:", cosmographRef.current?._schema)
```

### 4. DuckDB Type System

```javascript
// Understanding DuckDB's type expectations
cosmographRef.current?._duckdb?.query(`
  SELECT 
    typeof(id) as id_type,
    typeof(index) as index_type,
    typeof(size) as size_type,
    typeof(x) as x_type,
    typeof(y) as y_type
  FROM cosmograph_points 
  LIMIT 1
`)

// Check what happens with different value types
cosmographRef.current?._duckdb?.query(`
  SELECT 
    typeof(1) as int_type,
    typeof(1.0) as float_type,
    typeof('1') as string_type,
    typeof(NULL) as null_type
`)
```

### 5. Working vs Failing Data Comparison

```javascript
// Capture exact data structure differences

// Working initial upload:
const workingNode = nodes[0];
const workingLink = links[0];

// Failing incremental add:
const failingNode = newNodes[0];
const failingLink = newEdges[0];

// Deep comparison
console.log("Node differences:", {
  workingKeys: Object.keys(workingNode).sort(),
  failingKeys: Object.keys(failingNode).sort(),
  workingTypes: Object.entries(workingNode).map(([k,v]) => [k, typeof v]),
  failingTypes: Object.entries(failingNode).map(([k,v]) => [k, typeof v]),
})
```

### 6. Cosmograph Source Code Inspection

Need to look at:
- `@cosmograph/react` source for `addPoints()` and `addLinks()` implementation
- How `uploadObject()` works internally
- What Vector type inference means in this context
- The exact INSERT statement being generated for DuckDB

### 7. Error Stack Trace Analysis

```javascript
// Capture full error objects
try {
  await cosmographRef.current.addPoints(transformedNodes)
} catch (error) {
  console.log("Full error object:", error)
  console.log("Error constructor:", error.constructor.name)
  console.log("Error properties:", Object.getOwnPropertyNames(error))
  console.log("Error stack:", error.stack)
  
  // Check if error has additional context
  if (error.cause) console.log("Error cause:", error.cause)
  if (error.data) console.log("Error data:", error.data)
}
```

### 8. Alternative API Methods

```javascript
// Check if there are other methods we should use
console.log("Available methods:", Object.getOwnPropertyNames(cosmographRef.current))
console.log("Prototype methods:", Object.getOwnPropertyNames(Object.getPrototypeOf(cosmographRef.current)))

// Check for alternative add methods
console.log("Has appendPoints?", typeof cosmographRef.current.appendPoints)
console.log("Has insertPoints?", typeof cosmographRef.current.insertPoints)
console.log("Has updateData?", typeof cosmographRef.current.updateData)
```

## Debug Implementation Strategy

1. **Add comprehensive logging** before attempting incremental updates
2. **Capture working data structure** from initial load
3. **Compare with failing data structure** from incremental add
4. **Query DuckDB schema** to understand exact requirements
5. **Adjust transformation functions** to match exact schema
6. **Test with minimal data** (single node, single edge)
7. **Gradually increase complexity** once basic case works

## Questions for Cosmograph Team/Documentation

1. Is there a difference in data format between initial `points`/`links` props and `addPoints()`/`addLinks()` methods?
2. What does "explicit type declaration" mean in the Vector type error?
3. Are there required fields that must be present even if null?
4. Is there a specific order for fields in the data objects?
5. Should indices be pre-calculated or will Cosmograph assign them?
6. Can incremental adds reference nodes by ID or must they use indices?
7. Is there a way to bypass type inference with explicit typing?

## Test Cases to Try

```javascript
// Test 1: Minimal node with explicit types
const minimalNode = {
  id: String(node.id),
  index: Number(startIndex),
  x: 0.0,
  y: 0.0,
  size: 5.0
}

// Test 2: Node with all fields from working data
const completeNode = {
  ...workingNodeStructure,
  id: newNode.id,
  index: newIndex
}

// Test 3: Using Cosmograph's data preparation methods
const preparedNodes = cosmographRef.current._preparePointsData?.(nodes)

// Test 4: Direct DuckDB insert to understand schema
cosmographRef.current._duckdb?.query(`
  INSERT INTO cosmograph_points VALUES (?, ?, ?, ...)
`, [values])
```

## Next Steps

1. Run all these queries in browser console during runtime
2. Document the exact schema and type requirements
3. Update transformation functions to match requirements exactly
4. Test incremental updates with correct data format
5. Implement proper type checking and validation
6. Add fallback handling for schema mismatches