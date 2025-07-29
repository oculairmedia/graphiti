import { useCallback, useRef } from 'react';
import { GraphNode } from '../api/types';
import { logger } from '../utils/logger';

interface CosmographRef {
  selectPoint?: (index: number) => void;
  selectPoints?: (indices: number[]) => void;
  focusNode?: (node?: GraphNode) => void;
  focusPoint?: (index: number) => void;
  getAdjacentNodes?: (id: string) => GraphNode[] | undefined;
  zoomToPoint?: (index: number, duration?: number, scale?: number, canZoomOut?: boolean) => void;
}

interface EventHandlerOptions {
  nodes: GraphNode[];
  onNodeClick: (node: GraphNode) => void;
  onNodeSelect: (nodeId: string) => void;
  onNodeHover?: (node: GraphNode | null) => void;
  onClearSelection?: () => void;
  cosmographRef: React.RefObject<CosmographRef | null>;
  config?: {
    fitViewDuration?: number;
  };
}

export function useGraphEvents({
  nodes,
  onNodeClick,
  onNodeSelect,
  onNodeHover,
  onClearSelection,
  cosmographRef,
  config = {},
}: EventHandlerOptions) {
  // Track double-click state
  const doubleClickTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastClickTimeRef = useRef<number>(0);
  const lastClickedNodeRef = useRef<GraphNode | null>(null);
  
  // Track hover state
  const lastHoveredIndexRef = useRef<number | undefined>(undefined);

  /**
   * Handle mouse move events for hover detection
   */
  const handleMouseMove = useCallback((index?: number) => {
    // Only update if the hovered index changed
    if (index === lastHoveredIndexRef.current) return;
    
    lastHoveredIndexRef.current = index;
    
    if (index !== undefined && index >= 0 && index < nodes.length) {
      const hoveredNode = nodes[index];
      if (hoveredNode) {
        onNodeHover?.(hoveredNode);
      }
    } else {
      onNodeHover?.(null);
    }
  }, [nodes, onNodeHover]);

  /**
   * Handle click events with support for single/double clicks and modifiers
   */
  const handleClick = useCallback(async (
    index?: number, 
    pointPosition?: [number, number], 
    event?: MouseEvent
  ) => {
    if (typeof index !== 'number' || !cosmographRef.current) {
      // Clicked on empty space
      if (!event?.shiftKey && !event?.ctrlKey && !event?.metaKey) {
        onClearSelection?.();
      }
      return;
    }

    // Get the node from the index
    if (index < 0 || index >= nodes.length) {
      logger.warn('Click index out of bounds:', index);
      return;
    }

    const clickedNode = nodes[index];
    if (!clickedNode) {
      logger.warn('Could not find node for index:', index);
      return;
    }

    // Check for double-click
    const currentTime = Date.now();
    const isDoubleClick = lastClickedNodeRef.current?.id === clickedNode.id && 
                         (currentTime - lastClickTimeRef.current) < 500;
    
    // Clear any pending single-click timeout
    if (doubleClickTimeoutRef.current) {
      clearTimeout(doubleClickTimeoutRef.current);
      doubleClickTimeoutRef.current = null;
    }

    // Handle modifier keys (shift/ctrl/cmd for multi-selection)
    if (event?.shiftKey || event?.ctrlKey || event?.metaKey) {
      logger.log(`Modifier click on node ${clickedNode.label}`);
      
      // Log adjacent nodes info
      if (cosmographRef.current.getAdjacentNodes) {
        const adjacentNodes = cosmographRef.current.getAdjacentNodes(clickedNode.id);
        if (adjacentNodes && adjacentNodes.length > 0) {
          logger.log(`Node ${clickedNode.label} has ${adjacentNodes.length} adjacent nodes`);
        }
      }
      
      // Always call onNodeClick to show the info panel even with modifiers
      onNodeClick(clickedNode);
      onNodeSelect(clickedNode.id);
      return;
    }

    if (isDoubleClick) {
      // Double-click - select, focus, and zoom
      logger.log(`Double-click on node ${clickedNode.label}`);
      
      // Select the node
      if (cosmographRef.current.selectPoint) {
        cosmographRef.current.selectPoint(index);
      } else if (cosmographRef.current.selectPoints) {
        cosmographRef.current.selectPoints([index]);
      }
      
      // Focus the node
      if (cosmographRef.current.focusNode) {
        cosmographRef.current.focusNode(clickedNode);
      } else if (cosmographRef.current.focusPoint) {
        cosmographRef.current.focusPoint(index);
      }
      
      // Zoom to the node
      if (cosmographRef.current.zoomToPoint) {
        cosmographRef.current.zoomToPoint(
          index, 
          config.fitViewDuration || 1000, 
          6.0, 
          true
        );
      }
      
      // Show the info panel
      onNodeClick(clickedNode);
      onNodeSelect(clickedNode.id);
    } else {
      // Single click - wait to see if it's a double click
      doubleClickTimeoutRef.current = setTimeout(() => {
        logger.log(`Single click on node ${clickedNode.label}`);
        
        // Select the node
        if (cosmographRef.current?.selectPoint) {
          cosmographRef.current.selectPoint(index);
        } else if (cosmographRef.current?.selectPoints) {
          cosmographRef.current.selectPoints([index]);
        }
        
        // Show the info panel
        onNodeClick(clickedNode);
        onNodeSelect(clickedNode.id);
      }, 300);
    }
    
    // Update click tracking
    lastClickTimeRef.current = currentTime;
    lastClickedNodeRef.current = clickedNode;
  }, [nodes, onNodeClick, onNodeSelect, onClearSelection, cosmographRef, config.fitViewDuration]);

  // Cleanup function to clear timers
  const cleanup = useCallback(() => {
    if (doubleClickTimeoutRef.current) {
      clearTimeout(doubleClickTimeoutRef.current);
      doubleClickTimeoutRef.current = null;
    }
  }, []);

  return {
    handleClick,
    handleMouseMove,
    cleanup,
  };
}