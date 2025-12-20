import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import type { GraphNode, GraphEdge } from '../types/graph';

interface SelectionState {
  // Selection state
  selectedNode: GraphNode | null;
  selectedNodeId: string | null;
  hoveredNode: GraphNode | null;
  hoveredNodeId: string | null;
  highlightedNodes: Set<string>;
  highlightedEdges: Set<string>;
  
  // Multi-selection
  selectedNodes: Set<string>;
  
  // Actions
  selectNode: (node: GraphNode | null) => void;
  selectNodeById: (nodeId: string | null) => void;
  hoverNode: (node: GraphNode | null) => void;
  hoverNodeById: (nodeId: string | null) => void;
  
  // Highlighting
  setHighlightedNodes: (nodeIds: Set<string> | string[]) => void;
  addHighlightedNode: (nodeId: string) => void;
  removeHighlightedNode: (nodeId: string) => void;
  clearHighlightedNodes: () => void;
  
  setHighlightedEdges: (edgeIds: Set<string> | string[]) => void;
  clearHighlightedEdges: () => void;
  
  // Multi-selection
  toggleNodeSelection: (nodeId: string) => void;
  addToSelection: (nodeIds: string[]) => void;
  removeFromSelection: (nodeIds: string[]) => void;
  clearSelection: () => void;
  
  // Bulk operations
  clearAll: () => void;
}

export const useSelectionStore = create<SelectionState>()(
  subscribeWithSelector((set, get) => ({
    // Initial state
    selectedNode: null,
    selectedNodeId: null,
    hoveredNode: null,
    hoveredNodeId: null,
    highlightedNodes: new Set(),
    highlightedEdges: new Set(),
    selectedNodes: new Set(),
    
    // Single selection
    selectNode: (node) => set({ 
      selectedNode: node, 
      selectedNodeId: node?.id ?? null 
    }),
    
    selectNodeById: (nodeId) => set({ 
      selectedNodeId: nodeId,
      // Note: selectedNode object should be updated by the component that has access to node data
    }),
    
    // Hover
    hoverNode: (node) => set({ 
      hoveredNode: node, 
      hoveredNodeId: node?.id ?? null 
    }),
    
    hoverNodeById: (nodeId) => set({ 
      hoveredNodeId: nodeId 
    }),
    
    // Highlighting
    setHighlightedNodes: (nodeIds) => set({ 
      highlightedNodes: nodeIds instanceof Set ? nodeIds : new Set(nodeIds) 
    }),
    
    addHighlightedNode: (nodeId) => set((state) => {
      const newSet = new Set(state.highlightedNodes);
      newSet.add(nodeId);
      return { highlightedNodes: newSet };
    }),
    
    removeHighlightedNode: (nodeId) => set((state) => {
      const newSet = new Set(state.highlightedNodes);
      newSet.delete(nodeId);
      return { highlightedNodes: newSet };
    }),
    
    clearHighlightedNodes: () => set({ highlightedNodes: new Set() }),
    
    setHighlightedEdges: (edgeIds) => set({ 
      highlightedEdges: edgeIds instanceof Set ? edgeIds : new Set(edgeIds) 
    }),
    
    clearHighlightedEdges: () => set({ highlightedEdges: new Set() }),
    
    // Multi-selection
    toggleNodeSelection: (nodeId) => set((state) => {
      const newSet = new Set(state.selectedNodes);
      if (newSet.has(nodeId)) {
        newSet.delete(nodeId);
      } else {
        newSet.add(nodeId);
      }
      return { selectedNodes: newSet };
    }),
    
    addToSelection: (nodeIds) => set((state) => {
      const newSet = new Set(state.selectedNodes);
      nodeIds.forEach(id => newSet.add(id));
      return { selectedNodes: newSet };
    }),
    
    removeFromSelection: (nodeIds) => set((state) => {
      const newSet = new Set(state.selectedNodes);
      nodeIds.forEach(id => newSet.delete(id));
      return { selectedNodes: newSet };
    }),
    
    clearSelection: () => set({ selectedNodes: new Set() }),
    
    // Clear everything
    clearAll: () => set({
      selectedNode: null,
      selectedNodeId: null,
      hoveredNode: null,
      hoveredNodeId: null,
      highlightedNodes: new Set(),
      highlightedEdges: new Set(),
      selectedNodes: new Set(),
    }),
  }))
);

// Selector helpers for optimized re-renders
export const selectSelectedNodeId = (state: SelectionState) => state.selectedNodeId;
export const selectHoveredNodeId = (state: SelectionState) => state.hoveredNodeId;
export const selectHighlightedNodes = (state: SelectionState) => state.highlightedNodes;
