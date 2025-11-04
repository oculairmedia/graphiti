# Refactoring Opportunities Analysis

## Overview
After implementing the hover performance fix, we now have comprehensive testing in place. This document identifies refactoring opportunities to improve code quality, maintainability, and performance.

## File Complexity Analysis

### Large Files Needing Refactoring

| File | Lines | Hooks | Priority | Issue |
|------|-------|-------|----------|-------|
| **GraphCanvasV2.tsx** | 1735 | 44 | HIGH | Monolithic component, too many responsibilities |
| **useGraphCamera.ts** | 880 | - | MEDIUM | Complex camera logic, can be simplified |
| **useGraphSelection.ts** | 796 | - | MEDIUM | Selection logic mixed with state management |
| **useGraphSimulation.ts** | 795 | - | MEDIUM | Physics simulation complexity |
| **useGraphInteractions.ts** | 731 | - | HIGH | Overlaps with GraphCanvasV2 interactions |
| **useGraphVisualEffects.ts** | 700 | - | LOW | Visual effects, mostly working well |

## Critical Refactoring Opportunities

### 1. GraphCanvasV2.tsx - Monolithic Component (CRITICAL)

**Current State:**
- 1735 lines, 44 React hooks
- Handles rendering, interactions, data, effects, camera, selection
- Difficult to test, maintain, and reason about

**Proposed Refactor:**
```
GraphCanvasV2.tsx (200 lines - orchestration only)
├── GraphCanvasRenderer.tsx - Pure Cosmograph rendering
├── GraphCanvasData.tsx - Data transformation & caching
├── GraphCanvasEvents.tsx - Event handling (click, hover, select)
├── GraphCanvasControls.tsx - Camera, zoom, pan controls
└── GraphCanvasEffects.tsx - Visual effects coordination
```

**Benefits:**
- Each component < 400 lines
- Clear separation of concerns
- Easier to test in isolation
- Better code reusability

### 2. Unused Hover Code (HIGH PRIORITY)

**Found in GraphCanvasV2.tsx:**
```typescript
// Lines 144-145: Unused refs after Cosmograph hover switch
const lastHoverTimeRef = useRef<number>(0);
const lastHoveredNodeIdRef = useRef<string | null>(null);

// Line 125: Unused prop
onNodeHover, // No longer called after Cosmograph switch

// Lines 434-439: Empty hover handler in useGraphInteractions
onNodeHover: (nodeId) => {
  // Hover is now handled by Cosmograph's built-in onPointMouseOver/Out
}
```

**Action:** Remove all unused hover infrastructure

### 3. Duplicate Data Transformations

**Issue:** Multiple places transform graph data
```typescript
// Location 1: GraphCanvasV2.tsx
const cosmographNodes = nodes.map(node => ({...}))

// Location 2: cosmographDataPreparer.ts
function prepareCosmographData({nodes, links}) {...}

// Location 3: useCosmographIncrementalUpdates.ts
function transformNodesForCosmograph(nodes) {...}
```

**Action:** Consolidate into single source of truth

### 4. Hook Composition Anti-patterns

**Issue:** GraphCanvasV2 uses 15+ custom hooks
```typescript
const camera = useGraphCamera(...)
const selection = useGraphSelection(...)
const simulation = useGraphSimulation(...)
const interactions = useGraphInteractions(...)
const effects = useGraphVisualEffects(...)
const data = useGraphDataManagement(...)
const websocket = useGraphWebSocket(...)
// ... 8 more hooks
```

**Problem:** Hook interdependencies create complex prop drilling

**Proposed Solution:** Create unified `useGraphCanvas` hook
```typescript
const useGraphCanvas = (config) => {
  // Compose all hooks internally
  // Return only essential interface
  return {
    canvasRef,
    handlers: { onClick, onSelect },
    state: { isLoading, error },
    controls: { zoomIn, zoomOut, fitView }
  }
}
```

### 5. Unused/Dead Code

**Found via static analysis:**

```typescript
// GraphCanvasV2.tsx - Unused imports/variables
import { prepareCosmographData } from '../utils/cosmographDataPreparer'; // HINT line 15
import { GraphData } from '../types/graph'; // HINT line 18
import { generateHSLColor } from '../utils/colorUtils'; // HINT line 20
import { useDebouncedCallback } from '../hooks/useDebouncedCallback'; // HINT line 23

// Unused destructured properties (HINT lines 232-470)
const { selectedLinkIds } = selection; // Never used
const { selectAll } = selection; // Never used
const { invertSelection } = selection; // Never used
const { pulseNodes } = effects; // Never used
const { createRipple } = effects; // Never used
// ... many more
```

**Action:** Remove 40+ unused variables/imports

### 6. Type Safety Issues

**Pre-existing TypeScript errors (30+ errors):**
```typescript
// ERROR: Property 'selectedNodeIds' does not exist (lines 234, 243)
// ERROR: Type 'string' is not assignable to union type (lines 607, 617)
// ERROR: Expected 2 arguments, but got 1 (lines 468, 876, 885)
// ERROR: Cannot find name 'generateNodeTypeColor' (lines 468, 876, 885)
```

**Action:** Fix all TypeScript errors to enable strict mode

### 7. Performance Opportunities

#### A. Memoization Cleanup
```typescript
// Over-memoization (unnecessary):
const someValue = useMemo(() => props.value, [props.value]); // Just use props.value!

// Under-memoization (causes re-renders):
const handleClick = (id) => onNodeSelect(id); // Should be useCallback
```

#### B. Ref vs State Usage
```typescript
// Currently using state for non-render values:
const [fpsInterval, setFpsInterval] = useState(1000);

// Should be refs:
const fpsIntervalRef = useRef(1000);
```

#### C. Effect Dependencies
```typescript
// Overly broad dependencies causing unnecessary runs:
useEffect(() => {
  updateCanvas();
}, [nodes, edges, config, selection, camera, effects]); // Too many!

// Should be more granular
```

### 8. Code Duplication

**Pattern 1: Color generation**
```typescript
// Found in 5+ files:
function generateNodeColor(node) {
  if (node.color) return node.color;
  return getColorByType(node.node_type);
}
```

**Pattern 2: Node filtering**
```typescript
// Duplicated in GraphCanvasV2, FilterPanel, NodeDetailsPanel:
const filteredNodes = nodes.filter(n => {
  if (filters.nodeType && n.node_type !== filters.nodeType) return false;
  if (filters.minDegree && n.degree < filters.minDegree) return false;
  return true;
});
```

**Action:** Extract to shared utilities

### 9. Testing Gaps

**Current test coverage:**
```
GraphCanvasV2.test.tsx - 50+ test errors
  - Tests reference old component structure
  - Mock dependencies outdated
  - Many tests disabled/skipped
```

**Action:** Update tests after refactoring

## Refactoring Priority Matrix

### Phase 1: Quick Wins (1-2 hours)
1. ✅ Remove unused hover code
2. ✅ Remove unused imports/variables
3. ✅ Fix TypeScript errors
4. ✅ Consolidate duplicate utilities

### Phase 2: Structural Improvements (4-6 hours)
1. 🔄 Split GraphCanvasV2 into smaller components
2. 🔄 Create unified useGraphCanvas hook
3. 🔄 Consolidate data transformation logic
4. 🔄 Optimize memoization patterns

### Phase 3: Testing & Validation (2-3 hours)
1. 🔄 Update component tests
2. 🔄 Add integration tests
3. 🔄 Performance regression tests
4. 🔄 Document new architecture

## Recommended Approach

### Step 1: Clean Dead Code (SAFE - No behavior change)
- Remove unused hover refs/handlers
- Remove unused imports
- Remove unused variables
- Remove commented code

### Step 2: Fix Type Errors (SAFE - Improves reliability)
- Add missing function parameters
- Fix type mismatches
- Enable stricter TypeScript mode

### Step 3: Extract Components (MEDIUM RISK)
- Start with pure rendering logic
- Extract event handlers
- Extract data transformations
- Maintain existing API

### Step 4: Consolidate Hooks (HIGHER RISK)
- Create useGraphCanvas facade
- Migrate existing usage
- Remove old hook exports
- Update documentation

## Success Metrics

### Before Refactoring
- Lines: 1735 (GraphCanvasV2)
- Hooks: 44
- TypeScript errors: 30+
- Test pass rate: ~60%
- Build warnings: 50+

### After Refactoring (Target)
- Lines: < 400 per component
- Hooks: < 10 per component
- TypeScript errors: 0
- Test pass rate: 95%+
- Build warnings: < 5

## Next Steps

1. **Review this document** - Get team/stakeholder approval
2. **Create feature branch** - `refactor/graph-canvas-cleanup`
3. **Start with Phase 1** - Quick wins, low risk
4. **Test thoroughly** - Ensure no regressions
5. **Document changes** - Update CLAUDE.md and docs

