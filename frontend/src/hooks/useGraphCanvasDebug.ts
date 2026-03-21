import React, { useEffect, useRef, type RefObject, type MutableRefObject } from 'react';
import type { CosmographRef } from '@cosmograph/react';
import type { GraphNode } from '../types/graph';
import { useWebSocketContext } from '../contexts/WebSocketProvider';
import { inspectDuckDBSchema } from '../utils/inspectDuckDBSchema';
import { resetDuckDBStorage } from '../utils/resetDuckDB';
import type { WebSocketEvent } from '../types/graphCanvasV2Types';

declare global {
  interface Window {
    inspectDuckDBSchema: typeof inspectDuckDBSchema;
    resetDuckDBStorage: typeof resetDuckDBStorage;
    cosmographRef: React.RefObject<CosmographRef> | null;
  }
}

export interface UseGraphCanvasDebugDeps {
  cosmographRef: RefObject<CosmographRef>;
  nodes: GraphNode[];
  getNodeIndices: (ids: string[]) => number[];
  addGlowingNodes: (nodeIds: string[]) => void;
  clearGlowingNodes: () => void;
  glowTimeoutRef: MutableRefObject<ReturnType<typeof setTimeout> | null>;
  setCosmographRef: (ref: React.RefObject<unknown>) => void;
  onContextReady?: (isReady: boolean) => void;
}

export function useGraphCanvasDebug(deps: UseGraphCanvasDebugDeps): void {
  const {
    cosmographRef,
    nodes,
    getNodeIndices,
    addGlowingNodes,
    clearGlowingNodes,
    glowTimeoutRef,
    setCosmographRef,
    onContextReady,
  } = deps;

  // Node access highlighting via Python WebSocket
  // NOTE: Kept inline (not using useGraphNodeAccessEvents) due to stale closure issues
  const { subscribe: subscribeToWebSocket } = useWebSocketContext();
  useEffect(() => {
    const unsubscribe = subscribeToWebSocket((event: WebSocketEvent) => {
      if (event.type === 'node_access' && event.node_ids) {
        if (glowTimeoutRef.current) {
          clearTimeout(glowTimeoutRef.current);
        }

        addGlowingNodes(event.node_ids);

        if (cosmographRef.current && nodes) {
          const indices = getNodeIndices(event.node_ids);

          if (indices.length > 0) {
            if (cosmographRef.current.selectPoints) {
              cosmographRef.current.selectPoints(indices, false);
            }
            if (cosmographRef.current.setFocusedPoint) {
              cosmographRef.current.setFocusedPoint(indices[0]);
            }
          }
        }

        glowTimeoutRef.current = setTimeout(() => {
          clearGlowingNodes();
          if (cosmographRef.current) {
            if (cosmographRef.current.setFocusedPoint) {
              cosmographRef.current.setFocusedPoint(undefined);
            }
            if (cosmographRef.current.unselectAllPoints) {
              cosmographRef.current.unselectAllPoints();
            }
          }
        }, 2000);
      }
    });

    return () => {
      unsubscribe();
      if (glowTimeoutRef.current) {
        clearTimeout(glowTimeoutRef.current);
      }
    };
  }, [subscribeToWebSocket, nodes, getNodeIndices, addGlowingNodes, clearGlowingNodes, glowTimeoutRef]);

  // Expose DuckDB utilities on window for debugging
  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.inspectDuckDBSchema = inspectDuckDBSchema;
      window.resetDuckDBStorage = resetDuckDBStorage;
      window.cosmographRef = cosmographRef;
    }
  }, []);

  // PERFORMANCE FIX (GRAPH-37): Proper WebGL cleanup on unmount
  useEffect(() => {
    return () => {
      if (cosmographRef.current) {
        const cosmograph = cosmographRef.current as unknown as { dispose?: () => void };
        if (typeof cosmograph.dispose === 'function') {
          cosmograph.dispose();
        }
        if (typeof cosmographRef.current.trackPointPositionsByIndices === 'function') {
          cosmographRef.current.trackPointPositionsByIndices([]);
        }
        if (typeof cosmographRef.current.pause === 'function') {
          cosmographRef.current.pause();
        }
      }

      if (glowTimeoutRef.current) {
        clearTimeout(glowTimeoutRef.current);
      }

      if (onContextReady) {
        onContextReady(false);
      }
    };
  }, [onContextReady, glowTimeoutRef]);

  // Sync Cosmograph ref to config context (one-time)
  const hasSetRef = useRef(false);
  useEffect(() => {
    if (cosmographRef.current && !hasSetRef.current) {
      setCosmographRef(cosmographRef as unknown as React.RefObject<unknown>);
      hasSetRef.current = true;
    }
  }, [cosmographRef.current]); // eslint-disable-line react-hooks/exhaustive-deps
}
