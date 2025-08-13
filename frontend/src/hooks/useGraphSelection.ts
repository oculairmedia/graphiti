/**
 * Graph Selection Hook
 * Handles node and edge selection, multi-selection, and selection operations
 */

import { useState, useCallback, useRef, useMemo, useEffect } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';

/**
 * Selection mode types
 */
export type SelectionMode = 'single' | 'multiple' | 'range' | 'path';

/**
 * Selection type
 */
export type SelectionType = 'node' | 'link' | 'mixed';

/**
 * Selection state
 */
export interface SelectionState {
  selectedNodes: Set<string>;
  selectedLinks: Set<string>;
  hoveredNode: string | null;
  hoveredLink: string | null;
  lastSelectedNode: string | null;
  lastSelectedLink: string | null;
  selectionBox: SelectionBox | null;
}

/**
 * Selection box for area selection
 */
export interface SelectionBox {
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  active: boolean;
}

/**
 * Selection event
 */
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

/**
 * Hook configuration
 */
export interface UseGraphSelectionConfig {
  // Selection mode
  mode?: SelectionMode;
  
  // Maximum number of items that can be selected
  maxSelection?: number;
  
  // Enable selection persistence
  persistSelection?: boolean;
  
  // Storage key for persistence
  storageKey?: string;
  
  // Callback when selection changes
  onSelectionChange?: (event: SelectionEvent) => void;
  
  // Callback when hover changes
  onHoverChange?: (nodeId: string | null, linkId: string | null) => void;
  
  // Enable keyboard shortcuts
  enableKeyboardShortcuts?: boolean;
  
  // Enable area selection
  enableAreaSelection?: boolean;
  
  // Debug mode
  debug?: boolean;
}

/**
 * Graph Selection Hook
 */
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

  // Selection state
  const [selectionState, setSelectionState] = useState<SelectionState>(() => {
    // Load persisted selection if enabled
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
  });

  // Track keyboard modifiers
  const modifiersRef = useRef({
    shift: false,
    ctrl: false,
    alt: false
  });

  /**
   * Log debug message
   */
  const log = useCallback((message: string, ...args: any[]) => {
    if (debug) {
      console.debug(`[useGraphSelection] ${message}`, ...args);
    }
  }, [debug]);

  /**
   * Trigger selection event
   */
  const triggerEvent = useCallback((
    type: SelectionEvent['type'],
    target: SelectionEvent['target'],
    ids: string[]
  ) => {
    if (onSelectionChange) {
      const event: SelectionEvent = {
        type,
        target,
        ids,
        timestamp: Date.now(),
        modifiers: { ...modifiersRef.current }
      };
      onSelectionChange(event);
    }
  }, [onSelectionChange]);

  /**
   * Select a single node
   */
  const selectNode = useCallback((nodeId: string, addToSelection: boolean = false) => {
    log(`Selecting node: ${nodeId}, addToSelection: ${addToSelection}`);
    
    setSelectionState(prev => {
      const newSelectedNodes = new Set(prev.selectedNodes);
      const newSelectedLinks = new Set(prev.selectedLinks);
      
      if (mode === 'single' || !addToSelection) {
        // Clear existing selection
        newSelectedNodes.clear();
        newSelectedLinks.clear();
      }
      
      // Check max selection limit
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
  }, [mode, maxSelection, triggerEvent, log]);

  /**
   * Select multiple nodes
   */
  const selectNodes = useCallback((nodeIds: string[], addToSelection: boolean = false) => {
    log(`Selecting ${nodeIds.length} nodes, addToSelection: ${addToSelection}`);
    
    setSelectionState(prev => {
      const newSelectedNodes = new Set(addToSelection ? prev.selectedNodes : []);
      const newSelectedLinks = addToSelection ? new Set(prev.selectedLinks) : new Set();
      
      // Add nodes up to max selection limit
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
  }, [maxSelection, triggerEvent, log]);

  /**
   * Select a single link
   */
  const selectLink = useCallback((linkId: string, addToSelection: boolean = false) => {
    log(`Selecting link: ${linkId}, addToSelection: ${addToSelection}`);
    
    setSelectionState(prev => {
      const newSelectedNodes = addToSelection ? new Set(prev.selectedNodes) : new Set();
      const newSelectedLinks = new Set(addToSelection ? prev.selectedLinks : []);
      
      if (newSelectedLinks.size >= maxSelection) {
        log(`Max selection limit reached: ${maxSelection}`);
        return prev;
      }
      
      newSelectedLinks.add(linkId);
      
      triggerEvent('select', 'link', [linkId]);
      
      return {
        ...prev,
        selectedNodes: newSelectedNodes,
        selectedLinks: newSelectedLinks,
        lastSelectedLink: linkId
      };
    });
  }, [maxSelection, triggerEvent, log]);

  /**
   * Deselect a node
   */
  const deselectNode = useCallback((nodeId: string) => {
    log(`Deselecting node: ${nodeId}`);
    
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
  }, [triggerEvent, log]);

  /**
   * Deselect multiple nodes
   */
  const deselectNodes = useCallback((nodeIds: string[]) => {
    log(`Deselecting ${nodeIds.length} nodes`);
    
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
  }, [triggerEvent, log]);

  /**
   * Deselect a link
   */
  const deselectLink = useCallback((linkId: string) => {
    log(`Deselecting link: ${linkId}`);
    
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
  }, [triggerEvent, log]);

  /**
   * Toggle node selection
   */
  const toggleNodeSelection = useCallback((nodeId: string) => {
    const isSelected = selectionState.selectedNodes.has(nodeId);
    
    if (isSelected) {
      deselectNode(nodeId);
    } else {
      selectNode(nodeId, mode === 'multiple');
    }
  }, [selectionState.selectedNodes, selectNode, deselectNode, mode]);

  /**
   * Toggle link selection
   */
  const toggleLinkSelection = useCallback((linkId: string) => {
    const isSelected = selectionState.selectedLinks.has(linkId);
    
    if (isSelected) {
      deselectLink(linkId);
    } else {
      selectLink(linkId, mode === 'multiple');
    }
  }, [selectionState.selectedLinks, selectLink, deselectLink, mode]);

  /**
   * Clear all selections
   */
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
  }, [triggerEvent, log]);

  /**
   * Select all nodes
   */
  const selectAllNodes = useCallback(() => {
    const nodeIds = nodes.map(n => n.id).slice(0, maxSelection);
    selectNodes(nodeIds, false);
  }, [nodes, maxSelection, selectNodes]);

  /**
   * Select all links
   */
  const selectAllLinks = useCallback(() => {
    const linkIds = links.map((l, i) => `${l.source}-${l.target}-${i}`).slice(0, maxSelection);
    
    setSelectionState(prev => {
      const newSelectedLinks = new Set(linkIds);
      
      triggerEvent('select', 'link', linkIds);
      
      return {
        ...prev,
        selectedNodes: new Set(),
        selectedLinks: newSelectedLinks,
        lastSelectedLink: linkIds[linkIds.length - 1] || null
      };
    });
  }, [links, maxSelection, triggerEvent]);

  /**
   * Invert selection
   */
  const invertSelection = useCallback(() => {
    const allNodeIds = new Set(nodes.map(n => n.id));
    const newSelectedNodes = new Set<string>();
    
    allNodeIds.forEach(id => {
      if (!selectionState.selectedNodes.has(id)) {
        newSelectedNodes.add(id);
      }
    });
    
    // Limit to max selection
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
  }, [nodes, selectionState.selectedNodes, maxSelection, triggerEvent]);

  /**
   * Select nodes by range (between last selected and target)
   */
  const selectNodeRange = useCallback((targetNodeId: string) => {
    if (!selectionState.lastSelectedNode) {
      selectNode(targetNodeId);
      return;
    }
    
    const nodeIds = nodes.map(n => n.id);
    const startIdx = nodeIds.indexOf(selectionState.lastSelectedNode);
    const endIdx = nodeIds.indexOf(targetNodeId);
    
    if (startIdx === -1 || endIdx === -1) {
      selectNode(targetNodeId);
      return;
    }
    
    const rangeStart = Math.min(startIdx, endIdx);
    const rangeEnd = Math.max(startIdx, endIdx);
    const rangeNodes = nodeIds.slice(rangeStart, rangeEnd + 1);
    
    selectNodes(rangeNodes, false);
  }, [nodes, selectionState.lastSelectedNode, selectNode, selectNodes]);

  /**
   * Select connected nodes
   */
  const selectConnectedNodes = useCallback((nodeId: string, depth: number = 1) => {
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
  }, [links, selectNodes]);

  /**
   * Select nodes by type
   */
  const selectNodesByType = useCallback((nodeType: string) => {
    const matchingNodes = nodes
      .filter(n => n.node_type === nodeType)
      .map(n => n.id);
    
    selectNodes(matchingNodes, false);
  }, [nodes, selectNodes]);

  /**
   * Set hover state
   */
  const setHoveredNode = useCallback((nodeId: string | null) => {
    setSelectionState(prev => {
      if (prev.hoveredNode === nodeId) return prev;
      
      if (onHoverChange) {
        onHoverChange(nodeId, prev.hoveredLink);
      }
      
      return { ...prev, hoveredNode: nodeId };
    });
  }, [onHoverChange]);

  const setHoveredLink = useCallback((linkId: string | null) => {
    setSelectionState(prev => {
      if (prev.hoveredLink === linkId) return prev;
      
      if (onHoverChange) {
        onHoverChange(prev.hoveredNode, linkId);
      }
      
      return { ...prev, hoveredLink: linkId };
    });
  }, [onHoverChange]);

  /**
   * Start area selection
   */
  const startAreaSelection = useCallback((x: number, y: number) => {
    if (!enableAreaSelection) return;
    
    log('Starting area selection at', x, y);
    
    setSelectionState(prev => ({
      ...prev,
      selectionBox: {
        startX: x,
        startY: y,
        endX: x,
        endY: y,
        active: true
      }
    }));
  }, [enableAreaSelection, log]);

  /**
   * Update area selection
   */
  const updateAreaSelection = useCallback((x: number, y: number) => {
    setSelectionState(prev => {
      if (!prev.selectionBox?.active) return prev;
      
      return {
        ...prev,
        selectionBox: {
          ...prev.selectionBox,
          endX: x,
          endY: y
        }
      };
    });
  }, []);

  /**
   * End area selection
   */
  const endAreaSelection = useCallback((
    nodePositions: Map<string, { x: number; y: number }>
  ) => {
    const box = selectionState.selectionBox;
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
    
    setSelectionState(prev => ({
      ...prev,
      selectionBox: null
    }));
  }, [selectionState.selectionBox, selectNodes]);

  /**
   * Get selection statistics
   */
  const getSelectionStats = useCallback(() => ({
    selectedNodeCount: selectionState.selectedNodes.size,
    selectedLinkCount: selectionState.selectedLinks.size,
    totalSelected: selectionState.selectedNodes.size + selectionState.selectedLinks.size,
    hasSelection: selectionState.selectedNodes.size > 0 || selectionState.selectedLinks.size > 0,
    isMaxed: selectionState.selectedNodes.size + selectionState.selectedLinks.size >= maxSelection
  }), [selectionState, maxSelection]);

  /**
   * Check if node is selected
   */
  const isNodeSelected = useCallback((nodeId: string): boolean => {
    return selectionState.selectedNodes.has(nodeId);
  }, [selectionState.selectedNodes]);

  /**
   * Check if link is selected
   */
  const isLinkSelected = useCallback((linkId: string): boolean => {
    return selectionState.selectedLinks.has(linkId);
  }, [selectionState.selectedLinks]);

  /**
   * Get selected nodes
   */
  const getSelectedNodes = useCallback((): GraphNode[] => {
    return nodes.filter(n => selectionState.selectedNodes.has(n.id));
  }, [nodes, selectionState.selectedNodes]);

  /**
   * Get selected links
   */
  const getSelectedLinks = useCallback((): GraphLink[] => {
    return links.filter((l, i) => 
      selectionState.selectedLinks.has(`${l.source}-${l.target}-${i}`)
    );
  }, [links, selectionState.selectedLinks]);

  // Persist selection if enabled
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

  // Keyboard event handlers
  useEffect(() => {
    if (!enableKeyboardShortcuts) return;
    
    const handleKeyDown = (e: KeyboardEvent) => {
      modifiersRef.current = {
        shift: e.shiftKey,
        ctrl: e.ctrlKey || e.metaKey,
        alt: e.altKey
      };
      
      // Ctrl+A: Select all
      if (e.ctrlKey && e.key === 'a') {
        e.preventDefault();
        selectAllNodes();
      }
      
      // Escape: Clear selection
      if (e.key === 'Escape') {
        clearSelection();
      }
      
      // Ctrl+I: Invert selection
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
  }, [enableKeyboardShortcuts, selectAllNodes, clearSelection, invertSelection]);

  return {
    // Selection state
    selectedNodes: selectionState.selectedNodes,
    selectedLinks: selectionState.selectedLinks,
    hoveredNode: selectionState.hoveredNode,
    hoveredLink: selectionState.hoveredLink,
    selectionBox: selectionState.selectionBox,
    
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
    selectAllNodes,
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

/**
 * Simple selection hook for basic use cases
 */
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
  
  return {
    selectedIds,
    select,
    deselect,
    toggle,
    clear,
    isSelected
  };
}