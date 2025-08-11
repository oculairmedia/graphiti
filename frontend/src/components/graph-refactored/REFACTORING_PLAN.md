# GraphCanvas Refactoring Plan

## Current State
- GraphCanvas.tsx: 3,617 lines
- Too many responsibilities: rendering, state management, WebSocket handling, data processing, event handling
- Memory leaks from event listeners and refs not being cleaned up
- Poor TypeScript typing in many places

## Target Architecture

### Core Components (New Structure)

```
src/components/graph-refactored/
├── core/
│   ├── GraphRenderer.tsx          (200 lines) - Pure Cosmograph wrapper
│   ├── GraphDataManager.tsx       (150 lines) - Data state management
│   └── GraphEventManager.tsx      (150 lines) - Event handling
├── features/
│   ├── DeltaProcessor.tsx         (200 lines) - WebSocket delta processing
│   ├── NodeGlowManager.tsx        (100 lines) - Node highlighting/glowing
│   ├── SelectionManager.tsx       (150 lines) - Selection state & logic
│   ├── SimulationManager.tsx      (100 lines) - Physics simulation control
│   └── PopupManager.tsx           (100 lines) - Node popups/tooltips
├── hooks/
│   ├── useGraphData.ts            (100 lines) - Data fetching & transformation
│   ├── useGraphSelection.ts       (80 lines)  - Selection logic
│   ├── useGraphDelta.ts           (120 lines) - Delta updates
│   ├── useGraphLayout.ts          (80 lines)  - Layout algorithms
│   └── useGraphInteraction.ts     (100 lines) - Mouse/keyboard events
├── utils/
│   ├── colorUtils.ts              (50 lines)  - Node/edge coloring
│   ├── transformUtils.ts          (80 lines)  - Data transformations
│   ├── memoryUtils.ts             (60 lines)  - Memory management
│   └── performanceUtils.ts        (50 lines)  - Performance monitoring
└── GraphCanvas.tsx                (150 lines) - Thin orchestration layer

Total: ~2,000 lines (45% reduction)
Average component size: ~120 lines
```

## Implementation Steps

### Step 1: Extract Data Management (Week 1)
1. Create `GraphDataManager.tsx` to handle:
   - Data state (nodes, links, stats)
   - Data transformations
   - DuckDB integration
   - Data validation

2. Create `useGraphData` hook to:
   - Fetch initial data
   - Handle data updates
   - Manage caching

### Step 2: Extract Delta Processing (Week 1)
1. Create `DeltaProcessor.tsx` to handle:
   - WebSocket subscriptions
   - Delta queue management
   - Batch processing
   - Conflict resolution

2. Create `useGraphDelta` hook for:
   - Delta subscriptions
   - Update notifications

### Step 3: Extract Selection Logic (Week 2)
1. Create `SelectionManager.tsx` for:
   - Selection state
   - Multi-selection
   - Keyboard shortcuts
   - Selection events

2. Create `useGraphSelection` hook for:
   - Selection API
   - Selection persistence

### Step 4: Extract Rendering Core (Week 2)
1. Create `GraphRenderer.tsx` as pure Cosmograph wrapper:
   - Props interface
   - Ref forwarding
   - Configuration
   - No business logic

### Step 5: Extract Event Management (Week 3)
1. Create `GraphEventManager.tsx` for:
   - Click/double-click handling
   - Hover events
   - Drag events
   - Zoom events

### Step 6: Extract Feature Components (Week 3)
1. `NodeGlowManager.tsx` - Glowing/highlighting
2. `SimulationManager.tsx` - Physics control
3. `PopupManager.tsx` - Node tooltips

### Step 7: Memory Management (Week 4)
1. Implement object pooling in `memoryUtils.ts`
2. Add cleanup tracking
3. Fix event listener leaks
4. Add WeakMap/WeakSet usage

### Step 8: TypeScript Strict Mode (Week 4)
1. Enable strict mode in tsconfig
2. Fix all type errors
3. Add proper interfaces
4. Remove all `any` types

## Success Metrics
- [ ] No component > 200 lines
- [ ] Memory growth < 10MB/hour
- [ ] 100% TypeScript strict compliance
- [ ] 90%+ test coverage
- [ ] Zero memory leaks
- [ ] 60fps with 10k nodes

## Migration Strategy
1. Create new components alongside old
2. Use feature flag to switch
3. Migrate incrementally
4. Run performance tests at each step
5. Remove old code once stable