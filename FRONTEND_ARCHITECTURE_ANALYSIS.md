# Frontend Architecture Analysis

## Executive Summary

**Root Cause Identified:** The timeline component is using an incorrect data access pattern. The `CosmographTimeline` component should automatically access data from the Cosmograph instance through the React context, but the timeline is trying to manually access data using non-existent methods.

## Architecture Overview

### 1. **CosmographProvider Context Architecture**

```jsx
// GraphViz.tsx:322
<CosmographProvider>
  <div className="h-screen w-full flex flex-col bg-background overflow-hidden">
    {/* All graph components including timeline */}
    <GraphTimeline />
  </div>
</CosmographProvider>
```

**Key Points:**
- `CosmographProvider` creates a React context that shares the Cosmograph instance
- All child components can access the same Cosmograph instance via `useCosmograph()`
- Timeline should automatically connect to this shared instance

### 2. **useCosmograph Hook Pattern**

```jsx
// GraphTimeline.tsx:40
const cosmograph = useCosmograph();
```

**Expected Behavior:**
- Returns the shared Cosmograph instance from context
- Timeline should automatically access node data through this instance
- No manual data fetching required

### 3. **CosmographTimeline Integration**

```jsx
// GraphTimeline.tsx:442-445
<CosmographTimeline
  ref={timelineRef}
  useLinksData={false}           // ✅ Use node data
  accessor="created_at_timestamp" // ✅ Correct field name
  // ... other props
/>
```

**Expected Behavior:**
- `CosmographTimeline` should automatically connect to the Cosmograph instance from context
- Should access node data using the `accessor="created_at_timestamp"` field
- Should not require manual data fetching

## Current Implementation Issues

### ❌ **Problem 1: Manual Data Access**

**File:** `frontend/src/components/GraphTimeline.tsx:45`
```jsx
// WRONG: Trying to manually access data
const data = cosmograph.getPointPositions?.();
```

**Issue:** `getPointPositions()` method doesn't exist on Cosmograph instance.

### ❌ **Problem 2: Timeline Not Auto-Connecting**

The `CosmographTimeline` component should automatically:
1. Connect to the Cosmograph instance from `useCosmograph()`
2. Access node data using the specified `accessor`
3. Build timeline from the `created_at_timestamp` field

But it's showing "empty or invalid timeline data" instead.

## Correct Architecture Pattern

### ✅ **How It Should Work**

```jsx
// Timeline component should NOT manually access data
export const GraphTimeline = forwardRef<GraphTimelineHandle, GraphTimelineProps>(
  ({ onTimeRangeChange, ... }, ref) => {
    const timelineRef = useRef<CosmographTimelineRef>(null);
    // ✅ Get cosmograph instance from context
    const cosmograph = useCosmograph();
    
    // ❌ REMOVE: Manual data access
    // const data = cosmograph.getPointPositions?.();
    
    return (
      <CosmographTimeline
        ref={timelineRef}
        useLinksData={false}
        accessor="created_at_timestamp"  // ✅ Timeline will use this automatically
        // ... other props
      />
    );
  }
);
```

### ✅ **Data Flow Should Be**

```
DuckDB → Arrow → Frontend → DuckDB-WASM → Cosmograph Instance → CosmographProvider Context → useCosmograph() → CosmographTimeline
                                                                                                                    ↑
                                                                                                            Auto-connects here
```

## Investigation Findings

### 1. **CosmographTimeline Constructor**

From `graph-visualizer-rust/static/vendor/modules/timeline/index.d.ts:10`:
```typescript
constructor(cosmograph: Cosmograph<CosmosInputNode, CosmosInputLink>, targetElement: HTMLElement, config?: CosmographTimelineInputConfig<Datum>);
```

**Key Insight:** The timeline takes a `cosmograph` instance as first parameter. The React wrapper should automatically pass the instance from `useCosmograph()`.

### 2. **Timeline Configuration**

From `graph-visualizer-rust/static/vendor/modules/timeline/config.d.ts:4-5`:
```typescript
/** `timeAccessor`: Data key to access time values from `L` data for the `CosmographTimeline`. Default: `date` */
accessor?: (d: Datum) => Date | number;
```

**Key Insight:** The `accessor` prop should be a function or field name that extracts time values from node data.

### 3. **Data Access Pattern**

The timeline should access data through the Cosmograph instance's internal data structures, not through public methods like `getPointPositions()`.

## Root Cause Analysis

### **Primary Issue: React Wrapper Integration**

The `CosmographTimeline` React component is not properly:
1. **Connecting to the Cosmograph instance** from `useCosmograph()`
2. **Accessing the node data** with timestamps
3. **Using the accessor function** to extract `created_at_timestamp`

### **Secondary Issue: Debug Code**

The debug code in `GraphTimeline.tsx:45` is using a non-existent method:
```jsx
const data = cosmograph.getPointPositions?.(); // ❌ This method doesn't exist
```

## Solution Strategy

### **Immediate Fixes**

1. **Remove manual data access code**
   ```jsx
   // Remove this debug code
   const data = cosmograph.getPointPositions?.();
   ```

2. **Verify CosmographTimeline React wrapper**
   - Ensure it properly connects to the Cosmograph instance from context
   - Verify it passes the instance to the underlying timeline constructor

3. **Debug the actual connection**
   ```jsx
   useEffect(() => {
     if (cosmograph) {
       console.log('[GraphTimeline] Cosmograph instance:', cosmograph);
       console.log('[GraphTimeline] Available methods:', Object.getOwnPropertyNames(cosmograph));
       console.log('[GraphTimeline] Prototype methods:', Object.getOwnPropertyNames(Object.getPrototypeOf(cosmograph)));
     }
   }, [cosmograph]);
   ```

### **Architecture Verification**

1. **Confirm data exists in Cosmograph**
   - Nodes have `created_at_timestamp` ✅ (verified)
   - Cosmograph instance has the data ✅ (verified)

2. **Verify React context flow**
   - `CosmographProvider` creates context ✅
   - `useCosmograph()` returns instance ✅
   - `CosmographTimeline` receives instance ❌ (needs verification)

## Next Steps

1. **Debug the cosmograph instance methods** to understand available APIs
2. **Verify CosmographTimeline React wrapper** implementation
3. **Remove manual data access code** that's causing confusion
4. **Test timeline with proper automatic data connection**

## Files to Investigate

- `@cosmograph/react` package - CosmographTimeline React wrapper implementation
- `frontend/src/components/GraphTimeline.tsx` - Remove manual data access
- Timeline vendor files - Understand proper integration pattern

## Conclusion

The frontend architecture is correctly designed with:
- ✅ CosmographProvider context
- ✅ useCosmograph hook
- ✅ Shared Cosmograph instance
- ✅ Data available in Cosmograph

The issue is that the `CosmographTimeline` React component is not properly connecting to the Cosmograph instance from context, or the manual debug code is interfering with the automatic connection.
