# GraphCanvasV2 Modular Refactoring Plan

## Goal
Reduce GraphCanvasV2.tsx to a thin orchestration layer (<300 lines) by extracting all remaining inline logic into focused, composable hooks and components.

## Current State
- **Lines**: 1054
- **Hooks used**: ~18 custom hooks
- **Remaining inline logic**: Imperative handle, effect coordination, ref management, visual synchronization

## Phase 1: Extract Imperative Handle Logic

### 1.1 Create `useGraphCanvasImperativeHandle.ts`
**Purpose**: Encapsulate all imperative handle logic (selection, camera, data methods)

**Extracted logic**:
- All `useImperativeHandle` setup
- Ref management for handle dependencies
- Selection methods (clearSelection, selectNode, selectNodes)
- Camera methods (focusOnNodes, zoomIn, zoomOut, fitView, etc.)
- Data methods (setData, restart, getLiveStats)
- Selection tools (activateRectSelection, etc.)
- Incremental update methods (addIncrementalData, updateNodes, etc.)

**Interface**:
```typescript
function useGraphCanvasImperativeHandle(
  ref: ForwardedRef<GraphCanvasHandle>,
  deps: {
    cosmographRef: RefObject<CosmographRef>;
    nodes: GraphNode[];
    nodeIndexMap: Map<string, number>;
    statistics: GraphStatistics;
    config: GraphConfig;
    // ... other dependencies
  }
): void
```

**Lines saved**: ~300

### 1.2 Create `useGraphCanvasEffectCoordination.ts`
**Purpose**: Coordinate all useEffect hooks that synchronize state

**Extracted logic**:
- highlightedNodes effect (visual highlighting + cosmograph selection)
- selectedNodes effect (sync with internal selection state)
- statistics update effect
- simulation config re-application effect
- context ready notification effect
- fitView initialization effect

**Interface**:
```typescript
function useGraphCanvasEffectCoordination(deps: {
  cosmographRef: RefObject<CosmographRef>;
  cosmographData: CosmographData;
  highlightedNodes: string[];
  selectedNodes: string[];
  nodes: GraphNode[];
  links: GraphLink[];
  config: GraphConfig;
  // ... callbacks
}): void
```

**Lines saved**: ~150

## Phase 2: Extract Component Composition

### 2.1 Create `GraphCanvasCore.tsx`
**Purpose**: Pure rendering component with no business logic

**Responsibilities**:
- Render Cosmograph component
- Apply visual config
- Render overlays (loading, FPS, stats)
- CSS variable injection

**Props**:
```typescript
interface GraphCanvasCoreProps {
  cosmographRef: RefObject<CosmographRef>;
  cosmographData: CosmographData;
  visualConfig: CosmographVisualConfig;
  containerStyle: CSSProperties;
  isReady: boolean;
  loadingPhase: string;
  loadingProgress: { loaded: number; total: number };
  className?: string;
}
```

**Lines saved**: ~100

### 2.2 Create `useGraphCanvasOrchestration.ts`
**Purpose**: Top-level hook that composes all other hooks

**Responsibilities**:
- Initialize all sub-hooks in correct order
- Return orchestrated state and callbacks
- Handle hook dependency ordering

**Interface**:
```typescript
function useGraphCanvasOrchestration(props: GraphCanvasComponentProps): {
  // Refs
  cosmographRef: RefObject<CosmographRef>;
  
  // State
  isReady: boolean;
  cosmographData: CosmographData;
  visualConfig: CosmographVisualConfig;
  
  // Callbacks
  handleNodeClick: (node: GraphNode) => void;
  // ... other callbacks
}
```

**Lines saved**: ~100

## Phase 3: Extract Remaining Utilities

### 3.1 Create `useGraphCanvasDebug.ts`
**Purpose**: All debugging and development utilities

**Extracted logic**:
- Schema inspection
- DuckDB debugging
- Window object attachment
- Debug logging

**Lines saved**: ~50

### 3.2 Create `GraphCanvasTypes.ts`
**Purpose**: Centralize all type definitions

**Extracted types**:
- GraphStats
- WebSocketEvent
- DeltaUpdateEvent
- StatsUpdatePayload
- GraphCanvasComponentProps

**Lines saved**: ~50

## Phase 4: Final GraphCanvasV2 Structure

After all extractions, GraphCanvasV2.tsx becomes:

```typescript
import { useGraphCanvasOrchestration } from '../hooks/useGraphCanvasOrchestration';
import { useGraphCanvasImperativeHandle } from '../hooks/useGraphCanvasImperativeHandle';
import { useGraphCanvasEffectCoordination } from '../hooks/useGraphCanvasEffectCoordination';
import { GraphCanvasCore } from './GraphCanvasCore';

const GraphCanvasV2 = forwardRef<GraphCanvasHandle, GraphCanvasComponentProps>(
  (props, ref) => {
    // Orchestrate all hooks
    const orchestration = useGraphCanvasOrchestration(props);
    
    // Setup imperative handle
    useGraphCanvasImperativeHandle(ref, orchestration);
    
    // Coordinate effects
    useGraphCanvasEffectCoordination(orchestration);
    
    // Render
    return (
      <GraphCanvasCore
        cosmographRef={orchestration.cosmographRef}
        cosmographData={orchestration.cosmographData}
        visualConfig={orchestration.visualConfig}
        containerStyle={orchestration.containerStyle}
        isReady={orchestration.isReady}
        loadingPhase={orchestration.loadingPhase}
        loadingProgress={orchestration.loadingProgress}
        className={props.className}
      />
    );
  }
);
```

**Target lines**: <100

## Expected Outcomes

### Before
- GraphCanvasV2.tsx: 1054 lines
- Total files: ~45

### After
- GraphCanvasV2.tsx: <100 lines (95% reduction)
- GraphCanvasCore.tsx: ~100 lines (new)
- useGraphCanvasImperativeHandle.ts: ~300 lines (new)
- useGraphCanvasEffectCoordination.ts: ~150 lines (new)
- useGraphCanvasOrchestration.ts: ~100 lines (new)
- useGraphCanvasDebug.ts: ~50 lines (new)
- GraphCanvasTypes.ts: ~50 lines (new)
- Total files: ~51 (+6 new files)

### Benefits
1. **Testability**: Each hook can be unit tested in isolation
2. **Reusability**: Hooks can be reused in other graph components
3. **Maintainability**: Clear separation of concerns
4. **Performance**: Easier to identify and optimize bottlenecks
5. **Type Safety**: Centralized types reduce duplication
6. **Debugging**: Each module can be debugged independently

## Implementation Order

1. **Phase 1.1**: Extract imperative handle (highest complexity)
2. **Phase 3.2**: Extract types (enables other phases)
3. **Phase 1.2**: Extract effect coordination
4. **Phase 2.2**: Create orchestration hook
5. **Phase 2.1**: Create core component
6. **Phase 3.1**: Extract debug utilities
7. **Phase 4**: Refactor GraphCanvasV2 to use new structure

## Success Criteria

- [ ] GraphCanvasV2.tsx < 150 lines
- [ ] All existing tests pass
- [ ] No regression in functionality
- [ ] No performance degradation
- [ ] All new hooks have unit tests
- [ ] Documentation updated
