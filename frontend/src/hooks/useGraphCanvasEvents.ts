/**
 * useGraphCanvasEvents Hook
 * 
 * Handles all event logic for GraphCanvas including clicks and hover.
 * Extracted from GraphCanvasV2 to improve testability and separation of concerns.
 */

import { useCallback } from 'react';
import { GraphNode } from '../types/graph';
import { GraphClient } from '../api/graphClient';

interface EventHandlersConfig {
  nodes: GraphNode[];
  cosmographRef: React.RefObject<any>;
  onNodeClick: (node: GraphNode) => void;
  onNodeSelect: (nodeId: string) => void;
  onClearSelection: () => void;
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
          onNodeClick(node);
          onNodeSelect(node.id);
          
          // Fetch full details in background and update panel when ready
          if (node.id) {
            const client = new GraphClient();
            client.getNodeDetails(node.id)
              .then(fullNodeData => {
                console.log(`[useGraphCanvasEvents] Updated with full node details:`, fullNodeData);
                onNodeClick(fullNodeData as any);
              })
              .catch(error => {
                console.error(`[useGraphCanvasEvents] Failed to fetch node details:`, error);
                // Already showing basic data, so no need to do anything
              });
          }
          return;
        }
      }
      
      // For incrementally added nodes, access node directly by index
      const nodeData = nodes[index];
      if (nodeData) {
        console.log(`[useGraphCanvasEvents] Clicked on node:`, nodeData);
        
        // Show the panel immediately with available data
        onNodeClick(nodeData);
        onNodeSelect(nodeData.id || '');
        
        // Fetch full details in background if we have an ID
        if (nodeData.id) {
          const client = new GraphClient();
          client.getNodeDetails(nodeData.id)
            .then(fullNodeData => {
              console.log(`[useGraphCanvasEvents] Updated with full node details:`, fullNodeData);
              onNodeClick(fullNodeData as any);
            })
            .catch(error => {
              console.error(`[useGraphCanvasEvents] Failed to fetch node details:`, error);
              // Already showing basic data, so no need to do anything
            });
        }
      } else {
        console.warn(`[useGraphCanvasEvents] No node data found for index ${index}`);
      }
    } else {
      // Clicked on empty space - clear selection
      onClearSelection();
      
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
