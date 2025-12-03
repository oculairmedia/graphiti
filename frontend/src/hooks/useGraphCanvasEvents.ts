/**
 * useGraphCanvasEvents Hook
 * 
 * Handles all event logic for GraphCanvas including clicks and hover.
 * Extracted from GraphCanvasV2 to improve testability and separation of concerns.
 */

import { useCallback, useRef } from 'react';
import { GraphNode } from '../types/graph';
import { GraphClient } from '../api/graphClient';

// PERFORMANCE FIX: Cache node details to avoid redundant network requests
// LRU-style cache with max 500 entries
const NODE_DETAILS_CACHE_MAX = 500;
const nodeDetailsCache = new Map<string, GraphNode>();

function getCachedNodeDetails(nodeId: string): GraphNode | undefined {
  return nodeDetailsCache.get(nodeId);
}

function setCachedNodeDetails(nodeId: string, node: GraphNode): void {
  // Simple LRU: delete oldest entries if over limit
  if (nodeDetailsCache.size >= NODE_DETAILS_CACHE_MAX) {
    const firstKey = nodeDetailsCache.keys().next().value;
    if (firstKey) nodeDetailsCache.delete(firstKey);
  }
  nodeDetailsCache.set(nodeId, node);
}

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
          
          // PERFORMANCE FIX: Check cache first, then fetch if needed
          if (node.id) {
            const cached = getCachedNodeDetails(node.id);
            if (cached) {
              // Use cached data immediately
              onNodeClick(cached);
            } else {
              // Fetch full details in background and cache
              const client = new GraphClient();
              client.getNodeDetails(node.id)
                .then(fullNodeData => {
                  setCachedNodeDetails(node.id, fullNodeData as GraphNode);
                  onNodeClick(fullNodeData as any);
                })
                .catch(() => {
                  // Already showing basic data, so no need to do anything
                });
            }
          }
          return;
        }
      }
      
      // For incrementally added nodes, access node directly by index
      const nodeData = nodes[index];
      if (nodeData) {
        // Show the panel immediately with available data
        onNodeClick(nodeData);
        onNodeSelect(nodeData.id || '');
        
        // PERFORMANCE FIX: Check cache first, then fetch if needed
        if (nodeData.id) {
          const cached = getCachedNodeDetails(nodeData.id);
          if (cached) {
            onNodeClick(cached);
          } else {
            const client = new GraphClient();
            client.getNodeDetails(nodeData.id)
              .then(fullNodeData => {
                setCachedNodeDetails(nodeData.id, fullNodeData as GraphNode);
                onNodeClick(fullNodeData as any);
              })
              .catch(() => {
                // Already showing basic data, so no need to do anything
              });
          }
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
