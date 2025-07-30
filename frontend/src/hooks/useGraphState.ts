import { useReducer, useCallback, useMemo } from 'react';
import { GraphNode } from '../api/types';

// Combined state for all graph-related UI state
interface GraphState {
  // Selection state
  selectedNodes: string[];
  selectedNode: GraphNode | null;
  highlightedNodes: string[];
  
  // Hover state
  hoveredNode: GraphNode | null;
  hoveredConnectedNodes: string[];
  
  // UI state
  isFilterPanelOpen: boolean;
  isStatsPanelOpen: boolean;
  isLayoutPanelOpen: boolean;
  isLeftPanelCollapsed: boolean;
  isRightPanelCollapsed: boolean;
  isFullscreen: boolean;
  isSimulationRunning: boolean;
  
  // Performance state
  isIncrementalUpdate: boolean;
  isGraphInitialized: boolean;
}

// Action types
type GraphAction =
  | { type: 'SELECT_NODE'; nodeId: string }
  | { type: 'DESELECT_NODE'; nodeId: string }
  | { type: 'SELECT_NODES'; nodeIds: string[] }
  | { type: 'SET_SELECTED_NODE'; node: GraphNode | null }
  | { type: 'SET_HIGHLIGHTED_NODES'; nodeIds: string[] }
  | { type: 'SET_HOVERED_NODE'; node: GraphNode | null; connectedNodes?: string[] }
  | { type: 'CLEAR_ALL_SELECTIONS' }
  | { type: 'TOGGLE_FILTER_PANEL' }
  | { type: 'TOGGLE_STATS_PANEL' }
  | { type: 'TOGGLE_LAYOUT_PANEL' }
  | { type: 'TOGGLE_LEFT_PANEL' }
  | { type: 'TOGGLE_RIGHT_PANEL' }
  | { type: 'TOGGLE_FULLSCREEN' }
  | { type: 'TOGGLE_SIMULATION' }
  | { type: 'SET_INCREMENTAL_UPDATE'; value: boolean }
  | { type: 'SET_GRAPH_INITIALIZED'; value: boolean }
  | { type: 'BATCH_UPDATE'; updates: Partial<GraphState> };

// Initial state
const initialState: GraphState = {
  selectedNodes: [],
  selectedNode: null,
  highlightedNodes: [],
  hoveredNode: null,
  hoveredConnectedNodes: [],
  isFilterPanelOpen: false,
  isStatsPanelOpen: false,
  isLayoutPanelOpen: false,
  isLeftPanelCollapsed: false,
  isRightPanelCollapsed: false,
  isFullscreen: false,
  isSimulationRunning: true,
  isIncrementalUpdate: false,
  isGraphInitialized: false,
};

// Reducer function
function graphReducer(state: GraphState, action: GraphAction): GraphState {
  switch (action.type) {
    case 'SELECT_NODE':
      if (state.selectedNodes.includes(action.nodeId)) {
        return state;
      }
      return {
        ...state,
        selectedNodes: [...state.selectedNodes, action.nodeId],
      };
      
    case 'DESELECT_NODE':
      return {
        ...state,
        selectedNodes: state.selectedNodes.filter(id => id !== action.nodeId),
      };
      
    case 'SELECT_NODES':
      return {
        ...state,
        selectedNodes: action.nodeIds,
      };
      
    case 'SET_SELECTED_NODE':
      return {
        ...state,
        selectedNode: action.node,
      };
      
    case 'SET_HIGHLIGHTED_NODES':
      return {
        ...state,
        highlightedNodes: action.nodeIds,
      };
      
    case 'SET_HOVERED_NODE':
      return {
        ...state,
        hoveredNode: action.node,
        hoveredConnectedNodes: action.connectedNodes || [],
      };
      
    case 'CLEAR_ALL_SELECTIONS':
      return {
        ...state,
        selectedNodes: [],
        selectedNode: null,
        highlightedNodes: [],
      };
      
    case 'TOGGLE_FILTER_PANEL':
      return {
        ...state,
        isFilterPanelOpen: !state.isFilterPanelOpen,
      };
      
    case 'TOGGLE_STATS_PANEL':
      return {
        ...state,
        isStatsPanelOpen: !state.isStatsPanelOpen,
      };
      
    case 'TOGGLE_LAYOUT_PANEL':
      return {
        ...state,
        isLayoutPanelOpen: !state.isLayoutPanelOpen,
      };
      
    case 'TOGGLE_LEFT_PANEL':
      return {
        ...state,
        isLeftPanelCollapsed: !state.isLeftPanelCollapsed,
      };
      
    case 'TOGGLE_RIGHT_PANEL':
      return {
        ...state,
        isRightPanelCollapsed: !state.isRightPanelCollapsed,
      };
      
    case 'TOGGLE_FULLSCREEN':
      return {
        ...state,
        isFullscreen: !state.isFullscreen,
      };
      
    case 'TOGGLE_SIMULATION':
      return {
        ...state,
        isSimulationRunning: !state.isSimulationRunning,
      };
      
    case 'SET_INCREMENTAL_UPDATE':
      return {
        ...state,
        isIncrementalUpdate: action.value,
      };
      
    case 'SET_GRAPH_INITIALIZED':
      return {
        ...state,
        isGraphInitialized: action.value,
      };
      
    case 'BATCH_UPDATE':
      return {
        ...state,
        ...action.updates,
      };
      
    default:
      return state;
  }
}

export function useGraphState() {
  const [state, dispatch] = useReducer(graphReducer, initialState);
  
  // Memoized action creators
  const actions = useMemo(() => ({
    selectNode: (nodeId: string) => dispatch({ type: 'SELECT_NODE', nodeId }),
    deselectNode: (nodeId: string) => dispatch({ type: 'DESELECT_NODE', nodeId }),
    selectNodes: (nodeIds: string[]) => dispatch({ type: 'SELECT_NODES', nodeIds }),
    setSelectedNode: (node: GraphNode | null) => dispatch({ type: 'SET_SELECTED_NODE', node }),
    setHighlightedNodes: (nodeIds: string[]) => dispatch({ type: 'SET_HIGHLIGHTED_NODES', nodeIds }),
    setHoveredNode: (node: GraphNode | null, connectedNodes?: string[]) => 
      dispatch({ type: 'SET_HOVERED_NODE', node, connectedNodes }),
    clearAllSelections: () => dispatch({ type: 'CLEAR_ALL_SELECTIONS' }),
    toggleFilterPanel: () => dispatch({ type: 'TOGGLE_FILTER_PANEL' }),
    toggleStatsPanel: () => dispatch({ type: 'TOGGLE_STATS_PANEL' }),
    toggleLayoutPanel: () => dispatch({ type: 'TOGGLE_LAYOUT_PANEL' }),
    toggleLeftPanel: () => dispatch({ type: 'TOGGLE_LEFT_PANEL' }),
    toggleRightPanel: () => dispatch({ type: 'TOGGLE_RIGHT_PANEL' }),
    toggleFullscreen: () => dispatch({ type: 'TOGGLE_FULLSCREEN' }),
    toggleSimulation: () => dispatch({ type: 'TOGGLE_SIMULATION' }),
    setIncrementalUpdate: (value: boolean) => dispatch({ type: 'SET_INCREMENTAL_UPDATE', value }),
    setGraphInitialized: (value: boolean) => dispatch({ type: 'SET_GRAPH_INITIALIZED', value }),
    batchUpdate: (updates: Partial<GraphState>) => dispatch({ type: 'BATCH_UPDATE', updates }),
  }), []);
  
  // Memoized getters for commonly accessed combinations
  const selectors = useMemo(() => ({
    hasSelections: state.selectedNodes.length > 0 || state.selectedNode !== null || state.highlightedNodes.length > 0,
    allSelectedNodeIds: [...new Set([...state.selectedNodes, ...(state.selectedNode ? [state.selectedNode.id] : [])])],
    isAnyPanelOpen: state.isFilterPanelOpen || state.isStatsPanelOpen || state.isLayoutPanelOpen,
  }), [state.selectedNodes, state.selectedNode, state.highlightedNodes, state.isFilterPanelOpen, state.isStatsPanelOpen, state.isLayoutPanelOpen]);
  
  return {
    state,
    actions,
    selectors,
  };
}