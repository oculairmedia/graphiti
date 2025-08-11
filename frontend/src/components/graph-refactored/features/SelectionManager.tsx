import React, { useState, useCallback, useEffect, useRef } from 'react';
import { GraphNode } from '../../../api/types';
import { logger } from '../../../utils/logger';

interface SelectionManagerProps {
  nodes: GraphNode[];
  onSelectionChange?: (selectedNodes: GraphNode[]) => void;
  onNodeClick?: (node: GraphNode, event: MouseEvent) => void;
  onNodeDoubleClick?: (node: GraphNode, event: MouseEvent) => void;
  maxSelection?: number;
  multiSelectKey?: 'ctrl' | 'shift' | 'alt';
  enableKeyboardShortcuts?: boolean;
  persistSelection?: boolean;
  selectionStorageKey?: string;
}

interface SelectionState {
  selectedNodeIds: Set<string>;
  lastSelectedId: string | null;
  selectionMode: 'single' | 'multi' | 'range';
  isSelecting: boolean;
}

/**
 * SelectionManager - Manages node selection state and interactions
 * 
 * Features:
 * - Single and multi-selection
 * - Range selection with Shift
 * - Keyboard shortcuts
 * - Selection persistence
 * - Event handling
 */
export const SelectionManager: React.FC<SelectionManagerProps> = ({
  nodes,
  onSelectionChange,
  onNodeClick,
  onNodeDoubleClick,
  maxSelection = Infinity,
  multiSelectKey = 'ctrl',
  enableKeyboardShortcuts = true,
  persistSelection = false,
  selectionStorageKey = 'graph-selection'
}) => {
  const [state, setState] = useState<SelectionState>({
    selectedNodeIds: new Set(),
    lastSelectedId: null,
    selectionMode: 'single',
    isSelecting: false
  });

  // Refs for event handling
  const nodesMapRef = useRef<Map<string, GraphNode>>(new Map());
  const keyPressedRef = useRef<Set<string>>(new Set());

  // Update nodes map
  useEffect(() => {
    const nodesMap = new Map<string, GraphNode>();
    nodes.forEach(node => {
      nodesMap.set(node.id, node);
    });
    nodesMapRef.current = nodesMap;
  }, [nodes]);

  // Load persisted selection
  useEffect(() => {
    if (!persistSelection) return;

    try {
      const stored = localStorage.getItem(selectionStorageKey);
      if (stored) {
        const selectedIds = JSON.parse(stored);
        setState(prev => ({
          ...prev,
          selectedNodeIds: new Set(selectedIds)
        }));
        logger.log('SelectionManager: Loaded persisted selection:', selectedIds);
      }
    } catch (error) {
      logger.error('SelectionManager: Failed to load persisted selection:', error);
    }
  }, [persistSelection, selectionStorageKey]);

  // Save selection to storage
  useEffect(() => {
    if (!persistSelection) return;

    try {
      const selectedIds = Array.from(state.selectedNodeIds);
      localStorage.setItem(selectionStorageKey, JSON.stringify(selectedIds));
      logger.debug('SelectionManager: Persisted selection:', selectedIds);
    } catch (error) {
      logger.error('SelectionManager: Failed to persist selection:', error);
    }
  }, [state.selectedNodeIds, persistSelection, selectionStorageKey]);

  // Notify selection changes
  useEffect(() => {
    const selectedNodes = Array.from(state.selectedNodeIds)
      .map(id => nodesMapRef.current.get(id))
      .filter((node): node is GraphNode => node !== undefined);

    onSelectionChange?.(selectedNodes);
    
    logger.debug('SelectionManager: Selection changed:', {
      count: selectedNodes.length,
      mode: state.selectionMode
    });
  }, [state.selectedNodeIds, state.selectionMode, onSelectionChange]);

  // Select a single node
  const selectNode = useCallback((nodeId: string, addToSelection = false) => {
    setState(prev => {
      const newSelectedIds = addToSelection ? new Set(prev.selectedNodeIds) : new Set<string>();
      
      if (newSelectedIds.has(nodeId)) {
        newSelectedIds.delete(nodeId);
      } else if (newSelectedIds.size < maxSelection) {
        newSelectedIds.add(nodeId);
      }

      return {
        ...prev,
        selectedNodeIds: newSelectedIds,
        lastSelectedId: nodeId,
        selectionMode: addToSelection ? 'multi' : 'single'
      };
    });
  }, [maxSelection]);

  // Select multiple nodes
  const selectNodes = useCallback((nodeIds: string[], replace = true) => {
    setState(prev => {
      const newSelectedIds = replace ? new Set<string>() : new Set(prev.selectedNodeIds);
      
      nodeIds.forEach(id => {
        if (newSelectedIds.size < maxSelection) {
          newSelectedIds.add(id);
        }
      });

      return {
        ...prev,
        selectedNodeIds: newSelectedIds,
        lastSelectedId: nodeIds[nodeIds.length - 1] || prev.lastSelectedId,
        selectionMode: 'multi'
      };
    });
  }, [maxSelection]);

  // Select range of nodes
  const selectRange = useCallback((fromId: string, toId: string) => {
    const fromIndex = nodes.findIndex(n => n.id === fromId);
    const toIndex = nodes.findIndex(n => n.id === toId);
    
    if (fromIndex === -1 || toIndex === -1) return;

    const start = Math.min(fromIndex, toIndex);
    const end = Math.max(fromIndex, toIndex);
    const rangeNodes = nodes.slice(start, end + 1);

    setState(prev => {
      const newSelectedIds = new Set(prev.selectedNodeIds);
      
      rangeNodes.forEach(node => {
        if (newSelectedIds.size < maxSelection) {
          newSelectedIds.add(node.id);
        }
      });

      return {
        ...prev,
        selectedNodeIds: newSelectedIds,
        lastSelectedId: toId,
        selectionMode: 'range'
      };
    });
  }, [nodes, maxSelection]);

  // Clear selection
  const clearSelection = useCallback(() => {
    setState(prev => ({
      ...prev,
      selectedNodeIds: new Set(),
      lastSelectedId: null,
      selectionMode: 'single'
    }));
    logger.log('SelectionManager: Selection cleared');
  }, []);

  // Toggle selection for a node
  const toggleNodeSelection = useCallback((nodeId: string) => {
    setState(prev => {
      const newSelectedIds = new Set(prev.selectedNodeIds);
      
      if (newSelectedIds.has(nodeId)) {
        newSelectedIds.delete(nodeId);
      } else if (newSelectedIds.size < maxSelection) {
        newSelectedIds.add(nodeId);
      }

      return {
        ...prev,
        selectedNodeIds: newSelectedIds,
        lastSelectedId: nodeId
      };
    });
  }, [maxSelection]);

  // Select all nodes
  const selectAll = useCallback(() => {
    const allNodeIds = nodes.slice(0, maxSelection).map(n => n.id);
    selectNodes(allNodeIds, true);
    logger.log('SelectionManager: Selected all nodes');
  }, [nodes, maxSelection, selectNodes]);

  // Invert selection
  const invertSelection = useCallback(() => {
    setState(prev => {
      const newSelectedIds = new Set<string>();
      
      nodes.forEach(node => {
        if (!prev.selectedNodeIds.has(node.id) && newSelectedIds.size < maxSelection) {
          newSelectedIds.add(node.id);
        }
      });

      return {
        ...prev,
        selectedNodeIds: newSelectedIds,
        selectionMode: 'multi'
      };
    });
    logger.log('SelectionManager: Inverted selection');
  }, [nodes, maxSelection]);

  // Handle keyboard events
  useEffect(() => {
    if (!enableKeyboardShortcuts) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      keyPressedRef.current.add(e.key.toLowerCase());

      // Select all (Ctrl+A)
      if (e.ctrlKey && e.key === 'a') {
        e.preventDefault();
        selectAll();
      }
      
      // Clear selection (Escape)
      if (e.key === 'Escape') {
        clearSelection();
      }
      
      // Invert selection (Ctrl+I)
      if (e.ctrlKey && e.key === 'i') {
        e.preventDefault();
        invertSelection();
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      keyPressedRef.current.delete(e.key.toLowerCase());
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [enableKeyboardShortcuts, selectAll, clearSelection, invertSelection]);

  // Handle node click
  const handleNodeClick = useCallback((node: GraphNode, event: MouseEvent) => {
    event.preventDefault();
    
    const isMultiSelect = event[`${multiSelectKey}Key` as keyof MouseEvent] as boolean;
    const isRangeSelect = event.shiftKey;

    if (isRangeSelect && state.lastSelectedId) {
      selectRange(state.lastSelectedId, node.id);
    } else if (isMultiSelect) {
      toggleNodeSelection(node.id);
    } else {
      selectNode(node.id, false);
    }

    onNodeClick?.(node, event);
  }, [
    multiSelectKey,
    state.lastSelectedId,
    selectRange,
    toggleNodeSelection,
    selectNode,
    onNodeClick
  ]);

  // Handle node double-click
  const handleNodeDoubleClick = useCallback((node: GraphNode, event: MouseEvent) => {
    event.preventDefault();
    
    // Select node and its neighbors
    const neighbors = getNodeNeighbors(node.id);
    selectNodes([node.id, ...neighbors], true);
    
    onNodeDoubleClick?.(node, event);
  }, [selectNodes, onNodeDoubleClick]);

  // Get node neighbors (placeholder - would need graph structure)
  const getNodeNeighbors = (nodeId: string): string[] => {
    // This would typically query the graph structure
    // For now, return empty array
    return [];
  };

  // Public API via imperative handle would go here if needed
  
  return null; // This is a non-visual component
};

// Hook for selection state
export const useSelection = () => {
  const [selectedNodes, setSelectedNodes] = useState<GraphNode[]>([]);
  const [selectionMode, setSelectionMode] = useState<'single' | 'multi' | 'range'>('single');

  const selectNode = useCallback((node: GraphNode, multi = false) => {
    setSelectedNodes(prev => {
      if (multi) {
        const exists = prev.some(n => n.id === node.id);
        if (exists) {
          return prev.filter(n => n.id !== node.id);
        }
        return [...prev, node];
      }
      return [node];
    });
    setSelectionMode(multi ? 'multi' : 'single');
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedNodes([]);
    setSelectionMode('single');
  }, []);

  const isSelected = useCallback((nodeId: string) => {
    return selectedNodes.some(n => n.id === nodeId);
  }, [selectedNodes]);

  return {
    selectedNodes,
    selectionMode,
    selectNode,
    clearSelection,
    isSelected
  };
};

export default SelectionManager;