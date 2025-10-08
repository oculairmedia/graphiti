# Medium Priority Issue #010: Inconsistent State Management

## Severity
🟡 **Medium**

## Component
`GraphViz.tsx` - Lines 25-34 (State management) and throughout application

## Issue Description
The application uses a mix of local component state, global context, and no clear separation of concerns for state management. This creates inconsistencies, makes debugging difficult, and leads to prop drilling issues throughout the component tree.

## Technical Details

### Current State Management Pattern
```typescript
// GraphViz.tsx - Multiple state management approaches
export const GraphViz: React.FC<GraphVizProps> = ({ className }) => {
  const { config } = useGraphConfig();                    // ← Global context
  const [leftPanelCollapsed, setLeftPanelCollapsed] = useState(false);     // ← Local state
  const [rightPanelCollapsed, setRightPanelCollapsed] = useState(false);   // ← Local state
  const [selectedNodes, setSelectedNodes] = useState<string[]>([]);        // ← Local state
  const [selectedNode, setSelectedNode] = useState<any>(null);             // ← Local state
  const [highlightedNodes, setHighlightedNodes] = useState<string[]>([]);  // ← Local state
  const [showFilterPanel, setShowFilterPanel] = useState(false);          // ← Local state
  const [showStatsPanel, setShowStatsPanel] = useState(false);            // ← Local state
  const [searchQuery, setSearchQuery] = useState('');                     // ← Local state (unused!)
  const [isFullscreen, setIsFullscreen] = useState(false);               // ← Local state

  // React Query for API state
  const { data, isLoading, error } = useQuery({...});    // ← Server state
```

### Problems with Current Approach

#### 1. Mixed State Management Paradigms
```typescript
// Three different state management approaches in one component:
// 1. Global Context (GraphConfig)
const { config } = useGraphConfig();

// 2. Local Component State  
const [selectedNodes, setSelectedNodes] = useState<string[]>([]);

// 3. Server State (React Query)
const { data, isLoading, error } = useQuery({...});

// No clear pattern for when to use which approach
```

#### 2. Prop Drilling Issues
```typescript
// GraphViz passes many props to children
<GraphSearch 
  onNodeSelect={handleNodeSelectWithCosmograph}
  onHighlightNodes={handleHighlightNodes}
  onSelectNodes={handleSelectNodes}
  onClearSelection={clearAllSelections}
  onFilterClick={() => setShowFilterPanel(true)}
/>

<GraphCanvas 
  onNodeClick={handleNodeClick}
  onNodeSelect={handleNodeSelect}
  onClearSelection={clearAllSelections}
  selectedNodes={selectedNodes}
  highlightedNodes={highlightedNodes}
  // ... many more props
/>

// State and handlers are passed down multiple levels
```

#### 3. State Synchronization Issues
```typescript
// Selection state is managed in multiple places:
// 1. React state (selectedNodes, selectedNode)
const [selectedNodes, setSelectedNodes] = useState<string[]>([]);
const [selectedNode, setSelectedNode] = useState<any>(null);

// 2. Cosmograph internal state (via ref calls)
if (graphCanvasRef.current && typeof graphCanvasRef.current.selectNode === 'function') {
  graphCanvasRef.current.selectNode(node);
}

// 3. Highlight state (separate from selection)
const [highlightedNodes, setHighlightedNodes] = useState<string[]>([]);

// These can get out of sync!
```

#### 4. Scattered State Logic
```typescript
// Selection logic scattered across multiple functions:
const handleNodeSelect = (nodeId: string) => {
  if (selectedNodes.includes(nodeId)) {
    setSelectedNodes(selectedNodes.filter(id => id !== nodeId));
  } else {
    setSelectedNodes([...selectedNodes, nodeId]);
  }
};

const handleNodeSelectWithCosmograph = (node: any) => {
  setSelectedNode(node);
  handleNodeSelect(node.id);
  if (graphCanvasRef.current && typeof graphCanvasRef.current.selectNode === 'function') {
    graphCanvasRef.current.selectNode(node);
  }
};

const handleSelectNodes = (nodes: any[]) => {
  // Different logic for multiple selection
  // More scattered state updates
};

// No centralized state management
```

## Root Cause Analysis

### 1. No State Architecture Pattern
The application lacks a clear state management architecture. Different types of state are handled inconsistently without established patterns.

### 2. Component Responsibility Confusion
```typescript
// GraphViz component has too many responsibilities:
// 1. UI layout (panels, modals)
// 2. Graph interaction (selection, highlighting)  
// 3. API data management
// 4. Animation state coordination
// 5. Event handling
```

### 3. Tightly Coupled Components
Components are tightly coupled through prop passing rather than sharing state through a consistent mechanism.

### 4. No State Persistence Strategy
UI state (panel collapsed states, selections) is lost on page refresh with no persistence strategy.

## Impact Assessment

### Development Issues
- **Debugging Difficulty**: Hard to trace state changes across multiple components
- **Code Duplication**: Similar state logic repeated in different places
- **Testing Complexity**: Difficult to test components in isolation
- **Refactoring Risk**: Changes to state logic require updates in multiple places

### User Experience Issues
- **State Loss**: User selections and UI preferences lost on refresh
- **Inconsistent Behavior**: Different interaction patterns for similar operations
- **Performance**: Unnecessary re-renders due to prop drilling

### Maintenance Problems
- **Feature Addition**: Adding new features requires touching multiple components
- **Bug Fixing**: State-related bugs are hard to isolate and fix
- **Code Understanding**: New developers struggle to understand state flow

## Proposed Solutions

### Solution 1: Centralized State with Redux Toolkit
```typescript
// src/store/store.ts
import { configureStore } from '@reduxjs/toolkit';
import { graphSlice } from './slices/graphSlice';
import { uiSlice } from './slices/uiSlice';

export const store = configureStore({
  reducer: {
    graph: graphSlice.reducer,
    ui: uiSlice.reducer,
  },
});

// src/store/slices/graphSlice.ts
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface GraphState {
  selectedNodes: string[];
  selectedNode: GraphNode | null;
  highlightedNodes: string[];
  focusedNode: string | null;
}

const graphSlice = createSlice({
  name: 'graph',
  initialState: {
    selectedNodes: [],
    selectedNode: null,
    highlightedNodes: [],
    focusedNode: null,
  } as GraphState,
  reducers: {
    selectNode: (state, action: PayloadAction<{node: GraphNode, multiple?: boolean}>) => {
      const { node, multiple } = action.payload;
      if (multiple) {
        if (!state.selectedNodes.includes(node.id)) {
          state.selectedNodes.push(node.id);
        }
      } else {
        state.selectedNodes = [node.id];
        state.selectedNode = node;
      }
    },
    clearSelection: (state) => {
      state.selectedNodes = [];
      state.selectedNode = null;
      state.highlightedNodes = [];
    },
    highlightNodes: (state, action: PayloadAction<string[]>) => {
      state.highlightedNodes = action.payload;
    },
  },
});
```

### Solution 2: Lightweight State Management with Zustand
```typescript
// src/store/graphStore.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface GraphStore {
  // State
  selectedNodes: string[];
  selectedNode: GraphNode | null;
  highlightedNodes: string[];
  
  // Actions
  selectNode: (node: GraphNode, multiple?: boolean) => void;
  clearSelection: () => void;
  highlightNodes: (nodeIds: string[]) => void;
  toggleNodeSelection: (nodeId: string) => void;
}

export const useGraphStore = create<GraphStore>()(
  persist(
    (set, get) => ({
      // Initial state
      selectedNodes: [],
      selectedNode: null,
      highlightedNodes: [],
      
      // Actions
      selectNode: (node, multiple = false) => 
        set((state) => ({
          selectedNode: node,
          selectedNodes: multiple 
            ? [...state.selectedNodes, node.id]
            : [node.id]
        })),
        
      clearSelection: () => 
        set({
          selectedNodes: [],
          selectedNode: null,
          highlightedNodes: []
        }),
        
      highlightNodes: (nodeIds) => 
        set({ highlightedNodes: nodeIds }),
        
      toggleNodeSelection: (nodeId) =>
        set((state) => ({
          selectedNodes: state.selectedNodes.includes(nodeId)
            ? state.selectedNodes.filter(id => id !== nodeId)
            : [...state.selectedNodes, nodeId]
        })),
    }),
    {
      name: 'graph-state', // localStorage key
      partialize: (state) => ({ 
        selectedNodes: state.selectedNodes // Only persist selection
      }),
    }
  )
);

// UI Store
interface UIStore {
  leftPanelCollapsed: boolean;
  rightPanelCollapsed: boolean;
  showFilterPanel: boolean;
  showStatsPanel: boolean;
  isFullscreen: boolean;
  
  toggleLeftPanel: () => void;
  toggleRightPanel: () => void;
  setShowFilterPanel: (show: boolean) => void;
  setShowStatsPanel: (show: boolean) => void;
  setFullscreen: (fullscreen: boolean) => void;
}

export const useUIStore = create<UIStore>()(
  persist(
    (set) => ({
      // Initial state
      leftPanelCollapsed: false,
      rightPanelCollapsed: false,
      showFilterPanel: false,
      showStatsPanel: false,
      isFullscreen: false,
      
      // Actions
      toggleLeftPanel: () => 
        set((state) => ({ leftPanelCollapsed: !state.leftPanelCollapsed })),
      toggleRightPanel: () => 
        set((state) => ({ rightPanelCollapsed: !state.rightPanelCollapsed })),
      setShowFilterPanel: (show) => 
        set({ showFilterPanel: show }),
      setShowStatsPanel: (show) => 
        set({ showStatsPanel: show }),
      setFullscreen: (fullscreen) => 
        set({ isFullscreen: fullscreen }),
    }),
    {
      name: 'ui-state',
      partialize: (state) => ({ 
        leftPanelCollapsed: state.leftPanelCollapsed,
        rightPanelCollapsed: state.rightPanelCollapsed
      }),
    }
  )
);
```

### Solution 3: Context-based State Management
```typescript
// src/contexts/GraphStateContext.tsx
interface GraphState {
  selectedNodes: string[];
  selectedNode: GraphNode | null;
  highlightedNodes: string[];
}

interface GraphActions {
  selectNode: (node: GraphNode, multiple?: boolean) => void;
  clearSelection: () => void;
  highlightNodes: (nodeIds: string[]) => void;
}

const GraphStateContext = createContext<GraphState & GraphActions | null>(null);

export const GraphStateProvider: React.FC<{children: React.ReactNode}> = ({ children }) => {
  const [state, setState] = useReducer(graphReducer, initialState);
  
  const actions = useMemo(() => ({
    selectNode: (node: GraphNode, multiple = false) => {
      setState({
        type: 'SELECT_NODE',
        payload: { node, multiple }
      });
    },
    clearSelection: () => {
      setState({ type: 'CLEAR_SELECTION' });
    },
    highlightNodes: (nodeIds: string[]) => {
      setState({
        type: 'HIGHLIGHT_NODES',
        payload: nodeIds
      });
    },
  }), []);
  
  return (
    <GraphStateContext.Provider value={{...state, ...actions}}>
      {children}
    </GraphStateContext.Provider>
  );
};

export const useGraphState = () => {
  const context = useContext(GraphStateContext);
  if (!context) {
    throw new Error('useGraphState must be used within GraphStateProvider');
  }
  return context;
};
```

### Solution 4: Updated Component with Clean State Management
```typescript
// GraphViz.tsx - Simplified with external state management
export const GraphViz: React.FC<GraphVizProps> = ({ className }) => {
  const { config } = useGraphConfig();
  const { data, isLoading, error } = useQuery({...});
  
  // Use external stores instead of local state
  const {
    selectedNodes,
    selectedNode, 
    highlightedNodes,
    selectNode,
    clearSelection,
    highlightNodes
  } = useGraphStore();
  
  const {
    leftPanelCollapsed,
    rightPanelCollapsed,
    showFilterPanel,
    showStatsPanel,
    toggleLeftPanel,
    toggleRightPanel,
    setShowFilterPanel,
    setShowStatsPanel
  } = useUIStore();
  
  // Simplified event handlers
  const handleNodeClick = useCallback((node: GraphNode) => {
    selectNode(node);
  }, [selectNode]);
  
  const handleMultipleNodeSelect = useCallback((nodes: GraphNode[]) => {
    if (nodes.length > 0) {
      selectNode(nodes[0]);
      // Handle multiple selection logic
    }
  }, [selectNode]);
  
  // Rest of component is much cleaner...
};
```

## Recommended Solution
**Solution 2 (Zustand)** provides the best balance of simplicity, performance, and features for this application's needs.

### Benefits
- **Lightweight**: Small bundle size, minimal boilerplate
- **TypeScript Support**: Excellent TypeScript integration
- **Persistence**: Built-in localStorage persistence
- **DevTools**: React DevTools support
- **Performance**: No unnecessary re-renders
- **Simplicity**: Easy to understand and maintain

## Implementation Plan

### Phase 1: Create State Stores
1. Create `src/stores/graphStore.ts` for graph-related state
2. Create `src/stores/uiStore.ts` for UI-related state
3. Define clear interfaces and actions

### Phase 2: Migrate GraphViz Component
1. Replace local state with store hooks
2. Simplify event handlers
3. Remove prop drilling

### Phase 3: Update Child Components
1. Update components to use stores directly
2. Remove unnecessary prop passing
3. Simplify component interfaces

### Phase 4: Add Persistence
1. Configure localStorage persistence for UI preferences
2. Add session storage for temporary selections
3. Implement state restoration on app load

## Testing Strategy
1. **State Testing**: Test store actions and state transitions
2. **Component Testing**: Test components with mocked stores
3. **Integration Testing**: Test state flow between components
4. **Persistence Testing**: Verify localStorage functionality

## Priority Justification
This is Medium Priority because:
- **Code Quality**: Significantly improves code organization and maintainability
- **Developer Experience**: Makes debugging and feature addition much easier
- **Performance**: Reduces unnecessary re-renders from prop drilling
- **User Experience**: Enables state persistence for better UX

## Related Issues
- [Issue #006: Infinite Re-renders](../high/006-infinite-re-renders.md)
- [Issue #023: Component Coupling Issues](../low/023-component-coupling-issues.md)
- [Issue #011: Missing Prop Validation](./011-missing-prop-validation.md)

## Dependencies
- Zustand state management library
- TypeScript for type safety
- localStorage API for persistence
- React hooks patterns

## Estimated Fix Time
**4-6 hours** for complete state management refactoring with Zustand implementation and testing