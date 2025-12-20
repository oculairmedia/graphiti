/**
 * Graph Selection Hook - GRAPH-85 Optimized
 * 
 * Handles node and edge selection with optimized memoization.
 * Uses refs for state access to prevent callback recreation on every state change.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { GraphNode, GraphLink } from '../types/graph';

// ============================================================================
// Types
// ============================================================================

export type SelectionMode = 'single' | 'multiple' | 'range' | 'path';
export type SelectionType = 'node' | 'link' | 'mixed';

export interface SelectionState {
  selectedNodes: Set<string>;
  selectedLinks: Set<string>;
  hoveredNode: string | null;
  hoveredLink: string | null;
  lastSelectedNode: string | null;
  lastSelectedLink: string | null;
  selectionBox: SelectionBox | null;
}

export interface SelectionBox {
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  active: boolean;
}

export interface SelectionEvent {
  type: 'select' | 'deselect' | 'clear' | 'hover';
  target: 'node' | 'link' | 'all';
  ids: string[];
  timestamp: number;
  modifiers: {
    shift: boolean;
    ctrl: boolean;
    alt: boolean;
  };
}

export interface UseGraphSelectionConfig {
  mode?: SelectionMode;
  maxSelection?: number;
  persistSelection?: boolean;
  storageKey?: string;
  onSelectionChange?: (event: SelectionEvent) => void;
  onHoverChange?: (nodeId: string | null, linkId: string | null) => void;
  enableKeyboardShortcuts?: boolean;
  enableAreaSelection?: boolean;
  debug?: boolean;
}

// ============================================================================
// Initial State
// ============================================================================

const createInitialState = (persistSelection: boolean, storageKey: string): SelectionState => {
  if (persistSelection && typeof window !== 'undefined') {
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) {
        const parsed = JSON.parse(saved);
        return {
          selectedNodes: new Set(parsed.selectedNodes || []),
          selectedLinks: new Set(parsed.selectedLinks || []),
          hoveredNode: null,
          hoveredLink: null,
          lastSelectedNode: parsed.lastSelectedNode || null,
          lastSelectedLink: parsed.lastSelectedLink || null,
          selectionBox: null
        };
      }
    } catch (e) {
      console.error('Failed to load persisted selection:', e);
    }
  }
  
  return {
    selectedNodes: new Set(),
    selectedLinks: new Set(),
    hoveredNode: null,
    hoveredLink: null,
    lastSelectedNode: null,
    lastSelectedLink: null,
    selectionBox: null
  };
};

// ============================================================================
// Main Hook
// ============================================================================

export function useGraphSelection(
  nodes: GraphNode[],
  links: GraphLink[],
  config: UseGraphSelectionConfig = {}
) {
  const {
    mode = 'multiple',
    maxSelection = Infinity,
    persistSelection = false,
    storageKey = 'graph-selection',
    onSelectionChange,
    onHoverChange,
    enableKeyboardShortcuts = true,
    enableAreaSelection = true,
    debug = false
  } = config;

  // State
  const [selectionState, setSelectionState] = useState<SelectionState>(() => 
    createInitialState(persistSelection, storageKey)
  );

  // GRAPH-85 OPTIMIZATION: Use refs for stable callback access
  // This prevents callbacks from recreating when state changes
  const stateRef = useRef(selectionState);
  const nodesRef = useRef(nodes);
  const linksRef = useRef(links);
  const configRef = useRef({ mode, maxSelection, onSelectionChange, onHoverChange, debug });
  const modifiersRef = useRef({ shift: false, ctrl: false, alt: false });

  // Keep refs in sync
  useEffect(() => { stateRef.current = selectionState; }, [selectionState]);
  useEffect(() => { nodesRef.current = nodes; }, [nodes]);
  useEffect(() => { linksRef.current = links; }, [links]);
  useEffect(() => { 
    configRef.current = { mode, maxSelection, onSelectionChange, onHoverChange, debug }; 
  }, [mode, maxSelection, onSelectionChange, onHoverChange, debug]);

  // ============================================================================
  // Internal Helpers (not memoized - only used internally)
  // ============================================================================

  const log = (message: string, ...args: any[]) => {
    if (configRef.current.debug) {
      console.debug(`[useGraphSelection] ${message}`, ...args);
    }
  };

  const triggerEvent = (
    type: SelectionEvent['type'],
    target: SelectionEvent['target'],
    ids: string[]
  ) => {
    configRef.current.onSelectionChange?.({
      type,
      target,
      ids,
      timestamp: Date.now(),
      modifiers: { ...modifiersRef.current }
    });
  };

  // ============================================================================
  // Selection Operations (stable callbacks using refs)
  // ============================================================================

  const selectNode = useCallback((nodeId: string, addToSelection: boolean = false) => {
    log(`Selecting node: ${nodeId}, addToSelection: ${addToSelection}`);
    
    setSelectionState(prev => {
      const { mode, maxSelection } = configRef.current;
      const newSelectedNodes = new Set(prev.selectedNodes);
      const newSelectedLinks = new Set(prev.selectedLinks);
      
      if (mode === 'single' || !addToSelection) {
        newSelectedNodes.clear();
        newSelectedLinks.clear();
      }
      
      if (newSelectedNodes.size >= maxSelection) {
        log(`Max selection limit reached: ${maxSelection}`);
        return prev;
      }
      
      newSelectedNodes.add(nodeId);
      triggerEvent('select', 'node', [nodeId]);
      
      return {
        ...prev,
        selectedNodes: newSelectedNodes,
        selectedLinks: newSelectedLinks,
        lastSelectedNode: nodeId
      };
    });
  }, []); // Empty deps - uses refs

  const selectNodes = useCallback((nodeIds: string[], addToSelection: boolean = false) => {
    log(`Selecting ${nodeIds.length} nodes`);
    
    setSelectionState(prev => {
      const { maxSelection } = configRef.current;
      const newSelectedNodes = new Set(addToSelection ? prev.selectedNodes : []);
      const newSelectedLinks = addToSelection ? new Set(prev.selectedLinks) : new Set();
      
      const availableSlots = maxSelection - newSelectedNodes.size;
      const nodesToAdd = nodeIds.slice(0, availableSlots);
      nodesToAdd.forEach(id => newSelectedNodes.add(id));
      
      triggerEvent('select', 'node', nodesToAdd);
      
      return {
        ...prev,
        selectedNodes: newSelectedNodes,
        selectedLinks: newSelectedLinks,
        lastSelectedNode: nodesToAdd[nodesToAdd.length - 1] || prev.lastSelectedNode
      };
    });
  }, []);

  const selectLink = useCallback((linkId: string, addToSelection: boolean = false) => {
    setSelectionState(prev => {
      const { maxSelection } = configRef.current;
      const newSelectedNodes = addToSelection ? new Set(prev.selectedNodes) : new Set();
      const newSelectedLinks = new Set(addToSelection ? prev.selectedLinks : []);
      
      if (newSelectedLinks.size >= maxSelection) return prev;
      
      newSelectedLinks.add(linkId);
      triggerEvent('select', 'link', [linkId]);
      
      return {
        ...prev,
        selectedNodes: newSelectedNodes,
        selectedLinks: newSelectedLinks,
        lastSelectedLink: linkId
      };
    });
  }, []);

  const deselectNode = useCallback((nodeId: string) => {
    setSelectionState(prev => {
      const newSelectedNodes = new Set(prev.selectedNodes);
      newSelectedNodes.delete(nodeId);
      triggerEvent('deselect', 'node', [nodeId]);
      
      return {
        ...prev,
        selectedNodes: newSelectedNodes,
        lastSelectedNode: prev.lastSelectedNode === nodeId ? null : prev.lastSelectedNode
      };
    });
  }, []);

  const deselectNodes = useCallback((nodeIds: string[]) => {
    setSelectionState(prev => {
      const newSelectedNodes = new Set(prev.selectedNodes);
      nodeIds.forEach(id => newSelectedNodes.delete(id));
      triggerEvent('deselect', 'node', nodeIds);
      
      return {
        ...prev,
        selectedNodes: newSelectedNodes,
        lastSelectedNode: nodeIds.includes(prev.lastSelectedNode || '') ? null : prev.lastSelectedNode
      };
    });
  }, []);

  const deselectLink = useCallback((linkId: string) => {
    setSelectionState(prev => {
      const newSelectedLinks = new Set(prev.selectedLinks);
      newSelectedLinks.delete(linkId);
      triggerEvent('deselect', 'link', [linkId]);
      
      return {
        ...prev,
        selectedLinks: newSelectedLinks,
        lastSelectedLink: prev.lastSelectedLink === linkId ? null : prev.lastSelectedLink
      };
    });
  }, []);

  const toggleNodeSelection = useCallback((nodeId: string) => {
    const state = stateRef.current;
    if (state.selectedNodes.has(nodeId)) {
      deselectNode(nodeId);
    } else {
      selectNode(nodeId, configRef.current.mode === 'multiple');
    }
  }, [selectNode, deselectNode]);

  const toggleLinkSelection = useCallback((linkId: string) => {
    const state = stateRef.current;
    if (state.selectedLinks.has(linkId)) {
      deselectLink(linkId);
    } else {
      selectLink(linkId, configRef.current.mode === 'multiple');
    }
  }, [selectLink, deselectLink]);

  const clearSelection = useCallback(() => {
    log('Clearing all selections');
    
    setSelectionState(prev => {
      const clearedNodes = Array.from(prev.selectedNodes);
      const clearedLinks = Array.from(prev.selectedLinks);
      
      if (clearedNodes.length > 0 || clearedLinks.length > 0) {
        triggerEvent('clear', 'all', [...clearedNodes, ...clearedLinks]);
      }
      
      return {
        selectedNodes: new Set(),
        selectedLinks: new Set(),
        hoveredNode: null,
        hoveredLink: null,
        lastSelectedNode: null,
        lastSelectedLink: null,
        selectionBox: null
      };
    });
  }, []);

  const selectAll = useCallback(() => {
    const { maxSelection } = configRef.current;
    const nodeIds = nodesRef.current.map(n => n.id).slice(0, maxSelection);
    selectNodes(nodeIds, false);
  }, [selectNodes]);

  const selectAllLinks = useCallback(() => {
    const { maxSelection } = configRef.current;
    const links = linksRef.current;
    const linkIds = links.map((l, i) => `${l.source}-${l.target}-${i}`).slice(0, maxSelection);
    
    setSelectionState(prev => {
      triggerEvent('select', 'link', linkIds);
      return {
        ...prev,
        selectedNodes: new Set(),
        selectedLinks: new Set(linkIds),
        lastSelectedLink: linkIds[linkIds.length - 1] || null
      };
    });
  }, []);

  const invertSelection = useCallback(() => {
    const { maxSelection } = configRef.current;
    const nodes = nodesRef.current;
    const state = stateRef.current;
    
    const allNodeIds = new Set(nodes.map(n => n.id));
    const newSelectedNodes = new Set<string>();
    
    allNodeIds.forEach(id => {
      if (!state.selectedNodes.has(id)) {
        newSelectedNodes.add(id);
      }
    });
    
    const limitedNodes = Array.from(newSelectedNodes).slice(0, maxSelection);
    
    setSelectionState(prev => {
      triggerEvent('select', 'node', limitedNodes);
      return {
        ...prev,
        selectedNodes: new Set(limitedNodes),
        selectedLinks: new Set(),
        lastSelectedNode: limitedNodes[limitedNodes.length - 1] || null
      };
    });
  }, []);

  const selectNodeRange = useCallback((targetNodeId: string) => {
    const state = stateRef.current;
    const nodes = nodesRef.current;
    
    if (!state.lastSelectedNode) {
      selectNode(targetNodeId);
      return;
    }
    
    const nodeIds = nodes.map(n => n.id);
    const startIdx = nodeIds.indexOf(state.lastSelectedNode);
    const endIdx = nodeIds.indexOf(targetNodeId);
    
    if (startIdx === -1 || endIdx === -1) {
      selectNode(targetNodeId);
      return;
    }
    
    const rangeStart = Math.min(startIdx, endIdx);
    const rangeEnd = Math.max(startIdx, endIdx);
    selectNodes(nodeIds.slice(rangeStart, rangeEnd + 1), false);
  }, [selectNode, selectNodes]);

  const selectConnectedNodes = useCallback((nodeId: string, depth: number = 1) => {
    const links = linksRef.current;
    const connected = new Set<string>([nodeId]);
    const toProcess = [nodeId];
    
    for (let d = 0; d < depth; d++) {
      const nextLevel: string[] = [];
      
      toProcess.forEach(currentId => {
        links.forEach(link => {
          const source = String(link.source);
          const target = String(link.target);
          
          if (source === currentId && !connected.has(target)) {
            connected.add(target);
            nextLevel.push(target);
          }
          if (target === currentId && !connected.has(source)) {
            connected.add(source);
            nextLevel.push(source);
          }
        });
      });
      
      toProcess.length = 0;
      toProcess.push(...nextLevel);
    }
    
    selectNodes(Array.from(connected), false);
  }, [selectNodes]);

  const selectNodesByType = useCallback((nodeType: string) => {
    const nodes = nodesRef.current;
    const matchingNodes = nodes.filter(n => n.node_type === nodeType).map(n => n.id);
    selectNodes(matchingNodes, false);
  }, [selectNodes]);

  // ============================================================================
  // Hover Operations
  // ============================================================================

  const setHoveredNode = useCallback((nodeId: string | null) => {
    setSelectionState(prev => {
      if (prev.hoveredNode === nodeId) return prev;
      configRef.current.onHoverChange?.(nodeId, prev.hoveredLink);
      return { ...prev, hoveredNode: nodeId };
    });
  }, []);

  const setHoveredLink = useCallback((linkId: string | null) => {
    setSelectionState(prev => {
      if (prev.hoveredLink === linkId) return prev;
      configRef.current.onHoverChange?.(prev.hoveredNode, linkId);
      return { ...prev, hoveredLink: linkId };
    });
  }, []);

  // ============================================================================
  // Area Selection
  // ============================================================================

  const startAreaSelection = useCallback((x: number, y: number) => {
    if (!enableAreaSelection) return;
    
    setSelectionState(prev => ({
      ...prev,
      selectionBox: { startX: x, startY: y, endX: x, endY: y, active: true }
    }));
  }, [enableAreaSelection]);

  const updateAreaSelection = useCallback((x: number, y: number) => {
    setSelectionState(prev => {
      if (!prev.selectionBox?.active) return prev;
      return {
        ...prev,
        selectionBox: { ...prev.selectionBox, endX: x, endY: y }
      };
    });
  }, []);

  const endAreaSelection = useCallback((nodePositions: Map<string, { x: number; y: number }>) => {
    const state = stateRef.current;
    const box = state.selectionBox;
    if (!box?.active) return;
    
    const minX = Math.min(box.startX, box.endX);
    const maxX = Math.max(box.startX, box.endX);
    const minY = Math.min(box.startY, box.endY);
    const maxY = Math.max(box.startY, box.endY);
    
    const selectedNodeIds: string[] = [];
    nodePositions.forEach((pos, nodeId) => {
      if (pos.x >= minX && pos.x <= maxX && pos.y >= minY && pos.y <= maxY) {
        selectedNodeIds.push(nodeId);
      }
    });
    
    selectNodes(selectedNodeIds, modifiersRef.current.shift);
    setSelectionState(prev => ({ ...prev, selectionBox: null }));
  }, [selectNodes]);

  // ============================================================================
  // Query Functions (use state directly - these are expected to change)
  // ============================================================================

  const isNodeSelected = useCallback((nodeId: string): boolean => {
    return stateRef.current.selectedNodes.has(nodeId);
  }, []);

  const isLinkSelected = useCallback((linkId: string): boolean => {
    return stateRef.current.selectedLinks.has(linkId);
  }, []);

  const getSelectedNodes = useCallback((): GraphNode[] => {
    const state = stateRef.current;
    const nodes = nodesRef.current;
    return nodes.filter(n => state.selectedNodes.has(n.id));
  }, []);

  const getSelectedLinks = useCallback((): GraphLink[] => {
    const state = stateRef.current;
    const links = linksRef.current;
    return links.filter((l, i) => state.selectedLinks.has(`${l.source}-${l.target}-${i}`));
  }, []);

  const getSelectionStats = useCallback(() => {
    const state = stateRef.current;
    const { maxSelection } = configRef.current;
    return {
      selectedNodeCount: state.selectedNodes.size,
      selectedLinkCount: state.selectedLinks.size,
      totalSelected: state.selectedNodes.size + state.selectedLinks.size,
      hasSelection: state.selectedNodes.size > 0 || state.selectedLinks.size > 0,
      isMaxed: state.selectedNodes.size + state.selectedLinks.size >= maxSelection
    };
  }, []);

  // ============================================================================
  // Persistence
  // ============================================================================

  useEffect(() => {
    if (persistSelection && typeof window !== 'undefined') {
      const toSave = {
        selectedNodes: Array.from(selectionState.selectedNodes),
        selectedLinks: Array.from(selectionState.selectedLinks),
        lastSelectedNode: selectionState.lastSelectedNode,
        lastSelectedLink: selectionState.lastSelectedLink
      };
      
      try {
        localStorage.setItem(storageKey, JSON.stringify(toSave));
      } catch (e) {
        console.error('Failed to persist selection:', e);
      }
    }
  }, [persistSelection, storageKey, selectionState]);

  // ============================================================================
  // Keyboard Shortcuts
  // ============================================================================

  useEffect(() => {
    if (!enableKeyboardShortcuts) return;
    
    const handleKeyDown = (e: KeyboardEvent) => {
      modifiersRef.current = {
        shift: e.shiftKey,
        ctrl: e.ctrlKey || e.metaKey,
        alt: e.altKey
      };
      
      if (e.ctrlKey && e.key === 'a') {
        e.preventDefault();
        selectAll();
      }
      
      if (e.key === 'Escape') {
        clearSelection();
      }
      
      if (e.ctrlKey && e.key === 'i') {
        e.preventDefault();
        invertSelection();
      }
    };
    
    const handleKeyUp = (e: KeyboardEvent) => {
      modifiersRef.current = {
        shift: e.shiftKey,
        ctrl: e.ctrlKey || e.metaKey,
        alt: e.altKey
      };
    };
    
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [enableKeyboardShortcuts, selectAll, clearSelection, invertSelection]);

  // ============================================================================
  // Return Value
  // ============================================================================

  return {
    // Selection state
    selectedNodes: selectionState.selectedNodes,
    selectedLinks: selectionState.selectedLinks,
    hoveredNode: selectionState.hoveredNode,
    hoveredLink: selectionState.hoveredLink,
    selectionBox: selectionState.selectionBox,
    
    // Renamed for GraphCanvasV2 compatibility
    selectedNodeIds: selectionState.selectedNodes,
    selectedLinkIds: selectionState.selectedLinks,
    
    // Selection operations
    selectNode,
    selectNodes,
    selectLink,
    deselectNode,
    deselectNodes,
    deselectLink,
    toggleNodeSelection,
    toggleLinkSelection,
    clearSelection,
    selectAll,
    selectAllNodes: selectAll,
    selectAllLinks,
    invertSelection,
    selectNodeRange,
    selectConnectedNodes,
    selectNodesByType,
    
    // Hover operations
    setHoveredNode,
    setHoveredLink,
    
    // Area selection
    startAreaSelection,
    updateAreaSelection,
    endAreaSelection,
    
    // Utilities
    isNodeSelected,
    isLinkSelected,
    getSelectedNodes,
    getSelectedLinks,
    getSelectionStats
  };
}

// ============================================================================
// Simple Selection Hook (for basic use cases)
// ============================================================================

export function useSimpleSelection() {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  
  const select = useCallback((id: string) => {
    setSelectedIds(prev => new Set(prev).add(id));
  }, []);
  
  const deselect = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }, []);
  
  const toggle = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);
  
  const clear = useCallback(() => {
    setSelectedIds(new Set());
  }, []);
  
  const isSelected = useCallback((id: string) => {
    return selectedIds.has(id);
  }, [selectedIds]);
  
  return { selectedIds, select, deselect, toggle, clear, isSelected };
}
