/**
 * useGraphCanvasEvents Hook
 * 
 * Handles all event logic for GraphCanvas including clicks and hover.
 * Extracted from GraphCanvasV2 to improve testability and separation of concerns.
 */

import { useCallback } from 'react';
import { GraphNode } from '../types/graph';

interface EventHandlersConfig {
  nodes: GraphNode[];
  cosmographRef: React.RefObject<any>;
  onNodeClick: (node: GraphNode) => void;
  onNodeSelect: (nodeId: string) => void;
  onClearSelection?: () => void;
}

interface GraphCanvasEventHandlers {
  handleClick: (index?: number, pointPosition?: [number, number], event?: MouseEvent) => Promise<void>;
  handleMouseOver: (index: number, pointPosition: [number, number], event: MouseEvent) => void;
  handleMouseOut: (event: MouseEvent) => void;
}

export const useGraphCanvasEvents = ({
  nodes,
  cosmographRef,
  onNodeClick,
  onNodeSelect,
  onClearSelection
}: EventHandlersConfig): GraphCanvasEventHandlers => {
  
  // Click handler - handles node selection and details fetching
  const handleClick = useCallback(async (
    index?: number, 
    pointPosition?: [number, number], 
    event?: MouseEvent
  ) => {
    if (typeof index === 'number' && index >= 0) {
      // Visual selection first for immediate feedback
      requestAnimationFrame(() => {
        if (cosmographRef.current?.selectPoint) {
          cosmographRef.current.selectPoint(index);
        } else if (cosmographRef.current?.selectPoints) {
          cosmographRef.current.selectPoints([index]);
        }
      });
      
      // Try to get node from local state first
      if (index < nodes.length) {
        const node = nodes[index];
        if (node) {
          // Show the panel immediately with existing data
          // PERFORMANCE FIX: Don't fetch from network - we already have all the data from DuckDB
          onNodeClick(node);
          onNodeSelect(node.id);
          return;
        }
      }
      
      // For incrementally added nodes, access node directly by index
      const nodeData = nodes[index];
      if (nodeData) {
        // Show the panel immediately with available data
        // PERFORMANCE FIX: Don't fetch from network - we already have all the data from DuckDB
        onNodeClick(nodeData);
        onNodeSelect(nodeData.id || '');
      }
    } else {
      // Clicked on empty space - clear selection
      onClearSelection?.();
      
      // Also clear visual selection in Cosmograph
      requestAnimationFrame(() => {
        if (cosmographRef.current?.unselectAllPoints) {
          cosmographRef.current.unselectAllPoints();
        }
      });
    }
  }, [nodes, cosmographRef, onNodeClick, onNodeSelect, onClearSelection]);

  // Mouse over handler - Cosmograph handles all visual effects
  const handleMouseOver = useCallback((
    index: number,
    pointPosition: [number, number],
    event: MouseEvent
  ) => {
    // Cosmograph handles ALL visual hover effects
    // No parent callbacks = no React re-renders = smooth performance
  }, []);

  // Mouse out handler - Cosmograph handles all visual effects
  const handleMouseOut = useCallback((event: MouseEvent) => {
    // Cosmograph handles ALL visual hover effects
  }, []);

  return {
    handleClick,
    handleMouseOver,
    handleMouseOut
  };
};
