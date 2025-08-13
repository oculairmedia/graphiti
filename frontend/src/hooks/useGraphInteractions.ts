/**
 * Graph Interactions Hook
 * Handles user interactions with the graph including clicks, drags, hover, and gestures
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';

/**
 * Interaction types
 */
export type InteractionType = 
  | 'click'
  | 'double-click'
  | 'right-click'
  | 'drag'
  | 'hover'
  | 'pinch'
  | 'pan'
  | 'keyboard';

/**
 * Drag state
 */
export interface DragState {
  isDragging: boolean;
  draggedNode: string | null;
  dragStartPosition: { x: number; y: number } | null;
  dragCurrentPosition: { x: number; y: number } | null;
  dragDelta: { x: number; y: number };
}

/**
 * Gesture state
 */
export interface GestureState {
  isPinching: boolean;
  pinchScale: number;
  pinchCenter: { x: number; y: number } | null;
  isPanning: boolean;
  panDelta: { x: number; y: number };
}

/**
 * Context menu state
 */
export interface ContextMenuState {
  isOpen: boolean;
  position: { x: number; y: number } | null;
  target: {
    type: 'node' | 'link' | 'canvas';
    id?: string;
  } | null;
}

/**
 * Interaction event
 */
export interface InteractionEvent {
  type: InteractionType;
  target: 'node' | 'link' | 'canvas';
  targetId?: string;
  position: { x: number; y: number };
  modifiers: {
    shift: boolean;
    ctrl: boolean;
    alt: boolean;
    meta: boolean;
  };
  timestamp: number;
  prevented: boolean;
}

/**
 * Hook configuration
 */
export interface UseGraphInteractionsConfig {
  // Enable/disable interactions
  enableClick?: boolean;
  enableDoubleClick?: boolean;
  enableRightClick?: boolean;
  enableDrag?: boolean;
  enableHover?: boolean;
  enablePinch?: boolean;
  enablePan?: boolean;
  enableKeyboard?: boolean;
  
  // Drag configuration
  dragThreshold?: number; // Pixels to move before drag starts
  snapToGrid?: boolean;
  gridSize?: number;
  constrainToViewport?: boolean;
  
  // Double-click configuration
  doubleClickDelay?: number; // Max ms between clicks
  
  // Hover configuration
  hoverDelay?: number; // Ms to wait before hover triggers
  
  // Gesture configuration
  pinchSensitivity?: number;
  panSensitivity?: number;
  
  // Callbacks
  onNodeClick?: (nodeId: string, event: InteractionEvent) => void;
  onNodeDoubleClick?: (nodeId: string, event: InteractionEvent) => void;
  onNodeRightClick?: (nodeId: string, event: InteractionEvent) => void;
  onNodeDragStart?: (nodeId: string, position: { x: number; y: number }) => void;
  onNodeDrag?: (nodeId: string, position: { x: number; y: number }, delta: { x: number; y: number }) => void;
  onNodeDragEnd?: (nodeId: string, position: { x: number; y: number }) => void;
  onNodeHover?: (nodeId: string | null) => void;
  
  onLinkClick?: (linkId: string, event: InteractionEvent) => void;
  onLinkDoubleClick?: (linkId: string, event: InteractionEvent) => void;
  onLinkRightClick?: (linkId: string, event: InteractionEvent) => void;
  onLinkHover?: (linkId: string | null) => void;
  
  onCanvasClick?: (position: { x: number; y: number }, event: InteractionEvent) => void;
  onCanvasDoubleClick?: (position: { x: number; y: number }, event: InteractionEvent) => void;
  onCanvasRightClick?: (position: { x: number; y: number }, event: InteractionEvent) => void;
  onCanvasDrag?: (delta: { x: number; y: number }) => void;
  
  onPinch?: (scale: number, center: { x: number; y: number }) => void;
  onPan?: (delta: { x: number; y: number }) => void;
  
  // Debug mode
  debug?: boolean;
}

/**
 * Interaction history entry
 */
interface InteractionHistoryEntry {
  event: InteractionEvent;
  handled: boolean;
}

/**
 * Graph Interactions Hook
 */
export function useGraphInteractions(
  nodes: GraphNode[],
  links: GraphLink[],
  config: UseGraphInteractionsConfig = {}
) {
  const {
    enableClick = true,
    enableDoubleClick = true,
    enableRightClick = true,
    enableDrag = true,
    enableHover = true,
    enablePinch = true,
    enablePan = true,
    enableKeyboard = true,
    dragThreshold = 5,
    snapToGrid = false,
    gridSize = 10,
    constrainToViewport = false,
    doubleClickDelay = 300,
    hoverDelay = 500,
    pinchSensitivity = 1,
    panSensitivity = 1,
    onNodeClick,
    onNodeDoubleClick,
    onNodeRightClick,
    onNodeDragStart,
    onNodeDrag,
    onNodeDragEnd,
    onNodeHover,
    onLinkClick,
    onLinkDoubleClick,
    onLinkRightClick,
    onLinkHover,
    onCanvasClick,
    onCanvasDoubleClick,
    onCanvasRightClick,
    onCanvasDrag,
    onPinch,
    onPan,
    debug = false
  } = config;

  // Interaction states
  const [dragState, setDragState] = useState<DragState>({
    isDragging: false,
    draggedNode: null,
    dragStartPosition: null,
    dragCurrentPosition: null,
    dragDelta: { x: 0, y: 0 }
  });

  const [gestureState, setGestureState] = useState<GestureState>({
    isPinching: false,
    pinchScale: 1,
    pinchCenter: null,
    isPanning: false,
    panDelta: { x: 0, y: 0 }
  });

  const [contextMenu, setContextMenu] = useState<ContextMenuState>({
    isOpen: false,
    position: null,
    target: null
  });

  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [hoveredLink, setHoveredLink] = useState<string | null>(null);

  // Interaction tracking
  const interactionHistoryRef = useRef<InteractionHistoryEntry[]>([]);
  const clickTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const hoverTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastClickRef = useRef<{ time: number; target: string | null }>({ time: 0, target: null });
  const dragStartRef = useRef<{ x: number; y: number } | null>(null);
  const touchesRef = useRef<Map<number, Touch>>(new Map());

  /**
   * Log debug message
   */
  const log = useCallback((message: string, ...args: any[]) => {
    if (debug) {
      console.debug(`[useGraphInteractions] ${message}`, ...args);
    }
  }, [debug]);

  /**
   * Create interaction event
   */
  const createEvent = useCallback((
    type: InteractionType,
    target: 'node' | 'link' | 'canvas',
    targetId: string | undefined,
    position: { x: number; y: number },
    originalEvent?: MouseEvent | TouchEvent | KeyboardEvent
  ): InteractionEvent => {
    const modifiers = {
      shift: originalEvent ? 'shiftKey' in originalEvent ? originalEvent.shiftKey : false : false,
      ctrl: originalEvent ? 'ctrlKey' in originalEvent ? originalEvent.ctrlKey : false : false,
      alt: originalEvent ? 'altKey' in originalEvent ? originalEvent.altKey : false : false,
      meta: originalEvent ? 'metaKey' in originalEvent ? originalEvent.metaKey : false : false
    };

    return {
      type,
      target,
      targetId,
      position,
      modifiers,
      timestamp: Date.now(),
      prevented: false
    };
  }, []);

  /**
   * Add to interaction history
   */
  const addToHistory = useCallback((event: InteractionEvent, handled: boolean) => {
    interactionHistoryRef.current.unshift({ event, handled });
    interactionHistoryRef.current = interactionHistoryRef.current.slice(0, 100); // Keep last 100
  }, []);

  /**
   * Snap position to grid
   */
  const snapToGridPosition = useCallback((position: { x: number; y: number }) => {
    if (!snapToGrid) return position;
    
    return {
      x: Math.round(position.x / gridSize) * gridSize,
      y: Math.round(position.y / gridSize) * gridSize
    };
  }, [snapToGrid, gridSize]);

  /**
   * Handle node click
   */
  const handleNodeClick = useCallback((nodeId: string, position: { x: number; y: number }, originalEvent?: MouseEvent) => {
    if (!enableClick) return;
    
    log(`Node clicked: ${nodeId}`);
    
    const now = Date.now();
    const timeSinceLastClick = now - lastClickRef.current.time;
    
    // Check for double-click
    if (enableDoubleClick && 
        timeSinceLastClick < doubleClickDelay && 
        lastClickRef.current.target === nodeId) {
      
      // Cancel single click timeout
      if (clickTimeoutRef.current) {
        clearTimeout(clickTimeoutRef.current);
        clickTimeoutRef.current = null;
      }
      
      const event = createEvent('double-click', 'node', nodeId, position, originalEvent);
      
      if (onNodeDoubleClick) {
        onNodeDoubleClick(nodeId, event);
      }
      
      addToHistory(event, true);
      lastClickRef.current = { time: 0, target: null }; // Reset
    } else {
      // Single click (with delay to check for double-click)
      lastClickRef.current = { time: now, target: nodeId };
      
      if (enableDoubleClick) {
        clickTimeoutRef.current = setTimeout(() => {
          const event = createEvent('click', 'node', nodeId, position, originalEvent);
          
          if (onNodeClick) {
            onNodeClick(nodeId, event);
          }
          
          addToHistory(event, true);
        }, doubleClickDelay);
      } else {
        const event = createEvent('click', 'node', nodeId, position, originalEvent);
        
        if (onNodeClick) {
          onNodeClick(nodeId, event);
        }
        
        addToHistory(event, true);
      }
    }
  }, [enableClick, enableDoubleClick, doubleClickDelay, createEvent, onNodeClick, onNodeDoubleClick, addToHistory, log]);

  /**
   * Handle node right-click
   */
  const handleNodeRightClick = useCallback((nodeId: string, position: { x: number; y: number }, originalEvent?: MouseEvent) => {
    if (!enableRightClick) return;
    
    log(`Node right-clicked: ${nodeId}`);
    
    if (originalEvent) {
      originalEvent.preventDefault();
    }
    
    const event = createEvent('right-click', 'node', nodeId, position, originalEvent);
    
    setContextMenu({
      isOpen: true,
      position,
      target: { type: 'node', id: nodeId }
    });
    
    if (onNodeRightClick) {
      onNodeRightClick(nodeId, event);
    }
    
    addToHistory(event, true);
  }, [enableRightClick, createEvent, onNodeRightClick, addToHistory, log]);

  /**
   * Start node drag
   */
  const startNodeDrag = useCallback((nodeId: string, position: { x: number; y: number }) => {
    if (!enableDrag) return;
    
    log(`Starting drag for node: ${nodeId}`);
    
    dragStartRef.current = position;
    
    setDragState({
      isDragging: true,
      draggedNode: nodeId,
      dragStartPosition: position,
      dragCurrentPosition: position,
      dragDelta: { x: 0, y: 0 }
    });
    
    if (onNodeDragStart) {
      onNodeDragStart(nodeId, position);
    }
  }, [enableDrag, onNodeDragStart, log]);

  /**
   * Update node drag
   */
  const updateNodeDrag = useCallback((position: { x: number; y: number }) => {
    setDragState(prev => {
      if (!prev.isDragging || !prev.draggedNode || !prev.dragStartPosition) return prev;
      
      const delta = {
        x: position.x - prev.dragStartPosition.x,
        y: position.y - prev.dragStartPosition.y
      };
      
      // Check drag threshold only if not already passed
      if (dragThreshold > 0 && !dragStartRef.current) {
        const distance = Math.sqrt(delta.x * delta.x + delta.y * delta.y);
        if (distance < dragThreshold) return prev;
        dragStartRef.current = prev.dragStartPosition;
      }
      
      const snappedPosition = snapToGridPosition(position);
      
      if (onNodeDrag) {
        onNodeDrag(prev.draggedNode, snappedPosition, delta);
      }
      
      return {
        ...prev,
        dragCurrentPosition: snappedPosition,
        dragDelta: {
          x: snappedPosition.x - prev.dragStartPosition.x,
          y: snappedPosition.y - prev.dragStartPosition.y
        }
      };
    });
  }, [dragThreshold, snapToGridPosition, onNodeDrag]);

  /**
   * End node drag
   */
  const endNodeDrag = useCallback(() => {
    if (!dragState.isDragging || !dragState.draggedNode) return;
    
    log(`Ending drag for node: ${dragState.draggedNode}`);
    
    if (onNodeDragEnd && dragState.dragCurrentPosition) {
      onNodeDragEnd(dragState.draggedNode, dragState.dragCurrentPosition);
    }
    
    setDragState({
      isDragging: false,
      draggedNode: null,
      dragStartPosition: null,
      dragCurrentPosition: null,
      dragDelta: { x: 0, y: 0 }
    });
    
    dragStartRef.current = null;
  }, [dragState, onNodeDragEnd, log]);

  /**
   * Handle node hover
   */
  const handleNodeHover = useCallback((nodeId: string | null) => {
    if (!enableHover) return;
    
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current);
      hoverTimeoutRef.current = null;
    }
    
    if (nodeId) {
      hoverTimeoutRef.current = setTimeout(() => {
        log(`Node hover: ${nodeId}`);
        setHoveredNode(nodeId);
        if (onNodeHover) {
          onNodeHover(nodeId);
        }
      }, hoverDelay);
    } else {
      setHoveredNode(null);
      if (onNodeHover) {
        onNodeHover(null);
      }
    }
  }, [enableHover, hoverDelay, onNodeHover, log]);

  /**
   * Handle link interactions
   */
  const handleLinkClick = useCallback((linkId: string, position: { x: number; y: number }, originalEvent?: MouseEvent) => {
    if (!enableClick) return;
    
    log(`Link clicked: ${linkId}`);
    
    const event = createEvent('click', 'link', linkId, position, originalEvent);
    
    if (onLinkClick) {
      onLinkClick(linkId, event);
    }
    
    addToHistory(event, true);
  }, [enableClick, createEvent, onLinkClick, addToHistory, log]);

  const handleLinkHover = useCallback((linkId: string | null) => {
    if (!enableHover) return;
    
    setHoveredLink(linkId);
    if (onLinkHover) {
      onLinkHover(linkId);
    }
  }, [enableHover, onLinkHover]);

  /**
   * Handle canvas interactions
   */
  const handleCanvasClick = useCallback((position: { x: number; y: number }, originalEvent?: MouseEvent) => {
    if (!enableClick) return;
    
    log('Canvas clicked');
    
    const event = createEvent('click', 'canvas', undefined, position, originalEvent);
    
    // Close context menu
    setContextMenu({ isOpen: false, position: null, target: null });
    
    if (onCanvasClick) {
      onCanvasClick(position, event);
    }
    
    addToHistory(event, true);
  }, [enableClick, createEvent, onCanvasClick, addToHistory, log]);

  /**
   * Handle pinch gesture
   */
  const handlePinch = useCallback((scale: number, center: { x: number; y: number }) => {
    if (!enablePinch) return;
    
    log(`Pinch: scale=${scale}`);
    
    setGestureState(prev => ({
      ...prev,
      isPinching: true,
      pinchScale: scale * pinchSensitivity,
      pinchCenter: center
    }));
    
    if (onPinch) {
      onPinch(scale * pinchSensitivity, center);
    }
  }, [enablePinch, pinchSensitivity, onPinch, log]);

  /**
   * Handle pan gesture
   */
  const handlePan = useCallback((delta: { x: number; y: number }) => {
    if (!enablePan) return;
    
    log(`Pan: dx=${delta.x}, dy=${delta.y}`);
    
    const scaledDelta = {
      x: delta.x * panSensitivity,
      y: delta.y * panSensitivity
    };
    
    setGestureState(prev => ({
      ...prev,
      isPanning: true,
      panDelta: scaledDelta
    }));
    
    if (onPan) {
      onPan(scaledDelta);
    }
  }, [enablePan, panSensitivity, onPan, log]);

  /**
   * Get interaction history
   */
  const getInteractionHistory = useCallback((limit: number = 10): InteractionHistoryEntry[] => {
    return interactionHistoryRef.current.slice(0, limit);
  }, []);

  /**
   * Clear interaction history
   */
  const clearInteractionHistory = useCallback(() => {
    interactionHistoryRef.current = [];
  }, []);

  /**
   * Check if currently interacting
   */
  const isInteracting = useMemo(() => {
    return dragState.isDragging || 
           gestureState.isPinching || 
           gestureState.isPanning ||
           contextMenu.isOpen;
  }, [dragState.isDragging, gestureState.isPinching, gestureState.isPanning, contextMenu.isOpen]);

  /**
   * Get current interaction mode
   */
  const getInteractionMode = useCallback(() => {
    if (dragState.isDragging) return 'drag';
    if (gestureState.isPinching) return 'pinch';
    if (gestureState.isPanning) return 'pan';
    if (contextMenu.isOpen) return 'context-menu';
    return 'idle';
  }, [dragState.isDragging, gestureState.isPinching, gestureState.isPanning, contextMenu.isOpen]);

  /**
   * Cancel all interactions
   */
  const cancelAllInteractions = useCallback(() => {
    log('Cancelling all interactions');
    
    // Cancel drag
    if (dragState.isDragging) {
      endNodeDrag();
    }
    
    // Cancel gestures
    setGestureState({
      isPinching: false,
      pinchScale: 1,
      pinchCenter: null,
      isPanning: false,
      panDelta: { x: 0, y: 0 }
    });
    
    // Close context menu
    setContextMenu({
      isOpen: false,
      position: null,
      target: null
    });
    
    // Clear hovers
    setHoveredNode(null);
    setHoveredLink(null);
    
    // Clear timeouts
    if (clickTimeoutRef.current) {
      clearTimeout(clickTimeoutRef.current);
      clickTimeoutRef.current = null;
    }
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current);
      hoverTimeoutRef.current = null;
    }
  }, [dragState.isDragging, endNodeDrag, log]);

  // Keyboard shortcuts
  useEffect(() => {
    if (!enableKeyboard) return;
    
    const handleKeyDown = (e: KeyboardEvent) => {
      // Escape cancels all interactions
      if (e.key === 'Escape') {
        cancelAllInteractions();
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [enableKeyboard, cancelAllInteractions]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (clickTimeoutRef.current) {
        clearTimeout(clickTimeoutRef.current);
      }
      if (hoverTimeoutRef.current) {
        clearTimeout(hoverTimeoutRef.current);
      }
    };
  }, []);

  return {
    // States
    dragState,
    gestureState,
    contextMenu,
    hoveredNode,
    hoveredLink,
    isInteracting,
    
    // Node interactions
    handleNodeClick,
    handleNodeRightClick,
    handleNodeHover,
    startNodeDrag,
    updateNodeDrag,
    endNodeDrag,
    
    // Link interactions
    handleLinkClick,
    handleLinkHover,
    
    // Canvas interactions
    handleCanvasClick,
    
    // Gesture handlers
    handlePinch,
    handlePan,
    
    // Utilities
    getInteractionMode,
    getInteractionHistory,
    clearInteractionHistory,
    cancelAllInteractions,
    
    // Context menu controls
    openContextMenu: (position: { x: number; y: number }, target: ContextMenuState['target']) => {
      setContextMenu({ isOpen: true, position, target });
    },
    closeContextMenu: () => {
      setContextMenu({ isOpen: false, position: null, target: null });
    }
  };
}

/**
 * Simple interaction hook for basic click and hover
 */
export function useSimpleInteractions(
  onNodeClick?: (nodeId: string) => void,
  onNodeHover?: (nodeId: string | null) => void
) {
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  
  const handleClick = useCallback((nodeId: string) => {
    if (onNodeClick) {
      onNodeClick(nodeId);
    }
  }, [onNodeClick]);
  
  const handleHover = useCallback((nodeId: string | null) => {
    setHoveredNode(nodeId);
    if (onNodeHover) {
      onNodeHover(nodeId);
    }
  }, [onNodeHover]);
  
  return {
    hoveredNode,
    handleClick,
    handleHover
  };
}