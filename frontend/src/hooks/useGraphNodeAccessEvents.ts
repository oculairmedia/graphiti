/**
 * useGraphNodeAccessEvents Hook
 * Handles WebSocket node access events for real-time highlighting
 * Extracted from GraphCanvasV2 for better separation of concerns (GRAPH-35)
 */

import { useEffect, useCallback } from 'react';
import { useWebSocketContext } from '../contexts/WebSocketProvider';
import type { CosmographRef } from '@cosmograph/react';
import type { WebSocketEvent, NodeAccessEvent } from './useWebSocket';

interface NodeAccessEventsOptions {
  cosmographRef: React.RefObject<CosmographRef | null>;
  getNodeIndices: (nodeIds: string[]) => number[];
  addGlowingNodes: (nodeIds: string[]) => void;
  clearGlowingNodes: () => void;
  glowTimeoutRef: React.MutableRefObject<NodeJS.Timeout | null>;
  glowDuration?: number;
  debug?: boolean;
}

function isNodeAccessEvent(event: WebSocketEvent): event is NodeAccessEvent {
  return event.type === 'node_access' && 'node_ids' in event;
}

export function useGraphNodeAccessEvents(options: NodeAccessEventsOptions): void {
  const {
    cosmographRef,
    getNodeIndices,
    addGlowingNodes,
    clearGlowingNodes,
    glowTimeoutRef,
    glowDuration = 2000,
    debug = false
  } = options;
  
  const { subscribe: subscribeToWebSocket } = useWebSocketContext();
  
  useEffect(() => {
    const unsubscribe = subscribeToWebSocket((event: any) => {
      if (event.type === 'node_access' && event.node_ids) {
        if (debug) {
          console.log('[useGraphNodeAccessEvents] Node access event received:', {
            nodeIds: event.node_ids,
            nodeCount: event.node_ids.length
          });
        }
        
        // Cancel any existing glow timeout
        if (glowTimeoutRef.current) {
          clearTimeout(glowTimeoutRef.current);
        }
        
        // Update glowing nodes
        addGlowingNodes(event.node_ids);
        
        // Highlight nodes in Cosmograph using O(1) lookups
        if (cosmographRef.current) {
          const indices = getNodeIndices(event.node_ids);
          
          if (indices.length > 0) {
            // Select all nodes for visual effect
            if (cosmographRef.current.selectPoints) {
              cosmographRef.current.selectPoints(indices, false);
            }
            // Focus on the first node to show the ring
            if (cosmographRef.current.setFocusedPoint) {
              cosmographRef.current.setFocusedPoint(indices[0]);
            }
          }
        }
        
        // Remove glow after duration
        glowTimeoutRef.current = setTimeout(() => {
          clearGlowingNodes();
          
          // Clear focus and selection in Cosmograph
          if (cosmographRef.current) {
            if (cosmographRef.current.setFocusedPoint) {
              cosmographRef.current.setFocusedPoint(undefined);
            }
            if (cosmographRef.current.unselectAllPoints) {
              cosmographRef.current.unselectAllPoints();
            }
          }
        }, glowDuration);
      }
    });
    
    return () => {
      unsubscribe();
      if (glowTimeoutRef.current) {
        clearTimeout(glowTimeoutRef.current);
      }
    };
  }, [
    subscribeToWebSocket,
    cosmographRef,
    getNodeIndices,
    addGlowingNodes,
    clearGlowingNodes,
    glowTimeoutRef,
    glowDuration,
    debug
  ]);
}
