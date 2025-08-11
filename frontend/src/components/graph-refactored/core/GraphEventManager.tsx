import React, { useEffect, useRef, useCallback } from 'react';
import { GraphNode } from '../../../api/types';
import { GraphLink } from '../../../types/graph';
import { logger } from '../../../utils/logger';

interface GraphEventManagerProps {
  // Event callbacks
  onNodeClick?: (node: GraphNode, event: MouseEvent) => void;
  onNodeDoubleClick?: (node: GraphNode, event: MouseEvent) => void;
  onNodeRightClick?: (node: GraphNode, event: MouseEvent) => void;
  onNodeHover?: (node: GraphNode | null, event: MouseEvent) => void;
  onNodeDragStart?: (node: GraphNode, event: MouseEvent) => void;
  onNodeDrag?: (node: GraphNode, event: MouseEvent) => void;
  onNodeDragEnd?: (node: GraphNode, event: MouseEvent) => void;
  
  onLinkClick?: (link: GraphLink, event: MouseEvent) => void;
  onLinkHover?: (link: GraphLink | null, event: MouseEvent) => void;
  
  onCanvasClick?: (event: MouseEvent) => void;
  onCanvasDoubleClick?: (event: MouseEvent) => void;
  onCanvasRightClick?: (event: MouseEvent) => void;
  onCanvasDragStart?: (event: MouseEvent) => void;
  onCanvasDrag?: (event: MouseEvent) => void;
  onCanvasDragEnd?: (event: MouseEvent) => void;
  
  onZoom?: (zoomLevel: number, event: WheelEvent) => void;
  onPan?: (deltaX: number, deltaY: number, event: MouseEvent) => void;
  
  // Configuration
  clickDelay?: number;
  doubleClickDelay?: number;
  dragThreshold?: number;
  enableContextMenu?: boolean;
  stopPropagation?: boolean;
  preventDefault?: boolean;
  
  // Target element
  targetElement?: HTMLElement | null;
}

interface EventState {
  isDragging: boolean;
  dragTarget: GraphNode | null;
  dragStartPos: { x: number; y: number } | null;
  lastClickTime: number;
  lastClickTarget: GraphNode | null;
  hoveredNode: GraphNode | null;
  hoveredLink: GraphLink | null;
  isPanning: boolean;
  panStartPos: { x: number; y: number } | null;
}

/**
 * GraphEventManager - Centralized event handling for graph interactions
 * 
 * Features:
 * - Unified event handling
 * - Click vs double-click detection
 * - Drag threshold detection
 * - Event delegation
 * - Memory-efficient listeners
 */
export const GraphEventManager: React.FC<GraphEventManagerProps> = ({
  onNodeClick,
  onNodeDoubleClick,
  onNodeRightClick,
  onNodeHover,
  onNodeDragStart,
  onNodeDrag,
  onNodeDragEnd,
  onLinkClick,
  onLinkHover,
  onCanvasClick,
  onCanvasDoubleClick,
  onCanvasRightClick,
  onCanvasDragStart,
  onCanvasDrag,
  onCanvasDragEnd,
  onZoom,
  onPan,
  clickDelay = 200,
  doubleClickDelay = 300,
  dragThreshold = 5,
  enableContextMenu = true,
  stopPropagation = true,
  preventDefault = true,
  targetElement
}) => {
  const stateRef = useRef<EventState>({
    isDragging: false,
    dragTarget: null,
    dragStartPos: null,
    lastClickTime: 0,
    lastClickTarget: null,
    hoveredNode: null,
    hoveredLink: null,
    isPanning: false,
    panStartPos: null
  });

  const clickTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Get event target (node, link, or canvas)
  const getEventTarget = useCallback((event: MouseEvent): { type: 'node' | 'link' | 'canvas'; data?: GraphNode | GraphLink } => {
    // This would typically check the event target against rendered elements
    // For now, return canvas as default
    // In production, you'd use data attributes or class names to identify targets
    
    const element = event.target as HTMLElement;
    
    if (element.dataset?.nodeId) {
      // Mock node data - would be retrieved from nodes map
      return {
        type: 'node',
        data: { id: element.dataset.nodeId } as GraphNode
      };
    }
    
    if (element.dataset?.linkId) {
      // Mock link data - would be retrieved from links map
      return {
        type: 'link',
        data: { source: '', target: '' } as GraphLink
      };
    }
    
    return { type: 'canvas' };
  }, []);

  // Calculate distance between two points
  const getDistance = (p1: { x: number; y: number }, p2: { x: number; y: number }): number => {
    const dx = p2.x - p1.x;
    const dy = p2.y - p1.y;
    return Math.sqrt(dx * dx + dy * dy);
  };

  // Handle mouse down
  const handleMouseDown = useCallback((event: MouseEvent) => {
    if (preventDefault) event.preventDefault();
    if (stopPropagation) event.stopPropagation();

    const target = getEventTarget(event);
    const state = stateRef.current;

    // Record drag start position
    const pos = { x: event.clientX, y: event.clientY };
    
    if (target.type === 'node' && target.data) {
      state.dragTarget = target.data as GraphNode;
      state.dragStartPos = pos;
    } else if (target.type === 'canvas') {
      state.isPanning = true;
      state.panStartPos = pos;
      onCanvasDragStart?.(event);
    }

    logger.debug('GraphEventManager: Mouse down', { target: target.type, pos });
  }, [getEventTarget, preventDefault, stopPropagation, onCanvasDragStart]);

  // Handle mouse move
  const handleMouseMove = useCallback((event: MouseEvent) => {
    const state = stateRef.current;
    const currentPos = { x: event.clientX, y: event.clientY };

    // Handle hover
    const target = getEventTarget(event);
    if (target.type === 'node' && target.data) {
      const node = target.data as GraphNode;
      if (state.hoveredNode?.id !== node.id) {
        state.hoveredNode = node;
        onNodeHover?.(node, event);
      }
    } else if (state.hoveredNode) {
      state.hoveredNode = null;
      onNodeHover?.(null, event);
    }

    // Handle dragging
    if (state.dragStartPos && state.dragTarget) {
      const distance = getDistance(state.dragStartPos, currentPos);
      
      if (!state.isDragging && distance > dragThreshold) {
        state.isDragging = true;
        onNodeDragStart?.(state.dragTarget, event);
      }
      
      if (state.isDragging) {
        onNodeDrag?.(state.dragTarget, event);
      }
    }

    // Handle panning
    if (state.isPanning && state.panStartPos) {
      const deltaX = currentPos.x - state.panStartPos.x;
      const deltaY = currentPos.y - state.panStartPos.y;
      onPan?.(deltaX, deltaY, event);
      onCanvasDrag?.(event);
    }
  }, [getEventTarget, dragThreshold, onNodeHover, onNodeDragStart, onNodeDrag, onPan, onCanvasDrag]);

  // Handle mouse up
  const handleMouseUp = useCallback((event: MouseEvent) => {
    if (preventDefault) event.preventDefault();
    if (stopPropagation) event.stopPropagation();

    const state = stateRef.current;
    const target = getEventTarget(event);
    const currentTime = Date.now();

    // Handle drag end
    if (state.isDragging && state.dragTarget) {
      onNodeDragEnd?.(state.dragTarget, event);
    } else if (state.isPanning) {
      onCanvasDragEnd?.(event);
    } else {
      // Handle clicks (not a drag)
      if (target.type === 'node' && target.data) {
        const node = target.data as GraphNode;
        
        // Check for double-click
        if (state.lastClickTarget?.id === node.id && 
            currentTime - state.lastClickTime < doubleClickDelay) {
          // Cancel single click timer
          if (clickTimerRef.current) {
            clearTimeout(clickTimerRef.current);
            clickTimerRef.current = null;
          }
          onNodeDoubleClick?.(node, event);
          state.lastClickTarget = null;
        } else {
          // Schedule single click
          if (clickTimerRef.current) {
            clearTimeout(clickTimerRef.current);
          }
          clickTimerRef.current = setTimeout(() => {
            onNodeClick?.(node, event);
            clickTimerRef.current = null;
          }, clickDelay);
          state.lastClickTarget = node;
        }
        
        state.lastClickTime = currentTime;
      } else if (target.type === 'link' && target.data) {
        onLinkClick?.(target.data as GraphLink, event);
      } else if (target.type === 'canvas') {
        // Check for double-click on canvas
        if (currentTime - state.lastClickTime < doubleClickDelay) {
          if (clickTimerRef.current) {
            clearTimeout(clickTimerRef.current);
            clickTimerRef.current = null;
          }
          onCanvasDoubleClick?.(event);
        } else {
          if (clickTimerRef.current) {
            clearTimeout(clickTimerRef.current);
          }
          clickTimerRef.current = setTimeout(() => {
            onCanvasClick?.(event);
            clickTimerRef.current = null;
          }, clickDelay);
        }
        state.lastClickTime = currentTime;
      }
    }

    // Reset drag state
    state.isDragging = false;
    state.dragTarget = null;
    state.dragStartPos = null;
    state.isPanning = false;
    state.panStartPos = null;

    logger.debug('GraphEventManager: Mouse up', { target: target.type });
  }, [
    getEventTarget,
    preventDefault,
    stopPropagation,
    doubleClickDelay,
    clickDelay,
    onNodeDragEnd,
    onCanvasDragEnd,
    onNodeDoubleClick,
    onNodeClick,
    onLinkClick,
    onCanvasDoubleClick,
    onCanvasClick
  ]);

  // Handle context menu
  const handleContextMenu = useCallback((event: MouseEvent) => {
    if (!enableContextMenu) {
      event.preventDefault();
      return;
    }

    const target = getEventTarget(event);
    
    if (target.type === 'node' && target.data) {
      onNodeRightClick?.(target.data as GraphNode, event);
    } else if (target.type === 'canvas') {
      onCanvasRightClick?.(event);
    }
  }, [enableContextMenu, getEventTarget, onNodeRightClick, onCanvasRightClick]);

  // Handle wheel (zoom)
  const handleWheel = useCallback((event: WheelEvent) => {
    if (preventDefault) event.preventDefault();
    
    // Calculate zoom level based on wheel delta
    const delta = event.deltaY > 0 ? 0.9 : 1.1;
    const currentZoom = 1; // Would get from graph state
    const newZoom = currentZoom * delta;
    
    onZoom?.(newZoom, event);
    
    logger.debug('GraphEventManager: Wheel', { delta: event.deltaY, zoom: newZoom });
  }, [preventDefault, onZoom]);

  // Attach event listeners
  useEffect(() => {
    const element = targetElement || document.body;
    
    if (!element) return;

    // Add event listeners
    element.addEventListener('mousedown', handleMouseDown);
    element.addEventListener('mousemove', handleMouseMove);
    element.addEventListener('mouseup', handleMouseUp);
    element.addEventListener('contextmenu', handleContextMenu);
    element.addEventListener('wheel', handleWheel, { passive: false });

    logger.log('GraphEventManager: Event listeners attached');

    return () => {
      // Remove event listeners
      element.removeEventListener('mousedown', handleMouseDown);
      element.removeEventListener('mousemove', handleMouseMove);
      element.removeEventListener('mouseup', handleMouseUp);
      element.removeEventListener('contextmenu', handleContextMenu);
      element.removeEventListener('wheel', handleWheel);

      // Clear timers
      if (clickTimerRef.current) {
        clearTimeout(clickTimerRef.current);
      }

      logger.log('GraphEventManager: Event listeners removed');
    };
  }, [targetElement, handleMouseDown, handleMouseMove, handleMouseUp, handleContextMenu, handleWheel]);

  return null; // This is a non-visual component
};

export default GraphEventManager;