/**
 * useCosmographIncrementalUpdates Hook
 * 
 * Handles incremental updates to Cosmograph instance without full re-renders.
 * Uses Cosmograph's built-in incremental update API for smooth, real-time updates.
 */

import { useCallback, useRef, useState } from 'react';
import type { GraphNode } from '../api/types';
import type { GraphLink } from '../types/graph';
import {
  transformNodesForCosmograph,
  transformEdgesForCosmograph,
  extractEdgePairs,
  buildNodeIdToIndexMap,
  supportsIncrementalUpdates,
  type DeltaUpdate,
  type CosmographPointInput,
  type CosmographLinkInput
} from '../utils/cosmographTransformers';

/**
 * Hook options
 */
export interface UseCosmographIncrementalUpdatesOptions {
  onError?: (error: Error) => void;
  onSuccess?: (operation: string, count: number) => void;
  debug?: boolean;
  fallbackToFullUpdate?: (nodes: GraphNode[], edges: GraphLink[]) => void;
}

/**
 * Performance metrics for incremental updates
 */
export interface IncrementalUpdateMetrics {
  totalUpdates: number;
  successfulUpdates: number;
  failedUpdates: number;
  averageUpdateTime: number;
  lastUpdateTime: number;
  lastUpdateDuration: number;
}

/**
 * Hook for managing incremental Cosmograph updates
 */
export function useCosmographIncrementalUpdates(
  cosmographRef: React.RefObject<any>,
  currentNodes: GraphNode[],
  currentEdges: GraphLink[],
  options: UseCosmographIncrementalUpdatesOptions = {}
) {
  const {
    onError,
    onSuccess,
    debug = false,
    fallbackToFullUpdate
  } = options;

  // Track node ID to index mapping
  const nodeIdToIndexRef = useRef<Map<string, number>>(new Map());
  
  // Performance metrics
  const [metrics, setMetrics] = useState<IncrementalUpdateMetrics>({
    totalUpdates: 0,
    successfulUpdates: 0,
    failedUpdates: 0,
    averageUpdateTime: 0,
    lastUpdateTime: Date.now(),
    lastUpdateDuration: 0
  });

  // Logging helper
  const log = useCallback((message: string, ...args: any[]) => {
    if (debug) {
      console.log(`[useCosmographIncrementalUpdates] ${message}`, ...args);
    }
  }, [debug]);

  // Update metrics
  const updateMetrics = useCallback((success: boolean, duration: number) => {
    setMetrics(prev => {
      const newTotal = prev.totalUpdates + 1;
      const newSuccessful = success ? prev.successfulUpdates + 1 : prev.successfulUpdates;
      const newFailed = success ? prev.failedUpdates : prev.failedUpdates + 1;
      const totalDuration = prev.averageUpdateTime * prev.totalUpdates + duration;
      const newAverage = totalDuration / newTotal;

      return {
        totalUpdates: newTotal,
        successfulUpdates: newSuccessful,
        failedUpdates: newFailed,
        averageUpdateTime: newAverage,
        lastUpdateTime: Date.now(),
        lastUpdateDuration: duration
      };
    });
  }, []);

  /**
   * Initialize or rebuild the node ID to index map
   */
  const rebuildNodeIndexMap = useCallback(() => {
    nodeIdToIndexRef.current = buildNodeIdToIndexMap(currentNodes);
    log(`Rebuilt node index map with ${nodeIdToIndexRef.current.size} nodes`);
  }, [currentNodes, log]);

  /**
   * Apply node additions incrementally
   */
  const applyNodeAdditions = useCallback(async (nodes: GraphNode[]): Promise<boolean> => {
    if (!cosmographRef.current?.addPoints) {
      log('Cosmograph addPoints method not available');
      return false;
    }

    try {
      const startIndex = currentNodes.length;
      const transformedNodes = transformNodesForCosmograph(nodes, startIndex);
      
      log(`Adding ${nodes.length} nodes starting at index ${startIndex}`);
      await cosmographRef.current.addPoints(transformedNodes);
      
      // Update the index map
      nodes.forEach((node, i) => {
        nodeIdToIndexRef.current.set(node.id, startIndex + i);
      });
      
      onSuccess?.('addNodes', nodes.length);
      return true;
    } catch (error) {
      log('Failed to add nodes:', error);
      onError?.(error as Error);
      return false;
    }
  }, [cosmographRef, currentNodes.length, log, onSuccess, onError]);

  /**
   * Apply node updates incrementally
   * Note: Since Cosmograph doesn't have a direct update method, we skip updates
   * and rely on the React state update to handle them
   */
  const applyNodeUpdates = useCallback(async (nodes: GraphNode[]): Promise<boolean> => {
    if (!cosmographRef.current) {
      log('Cosmograph instance not available');
      return false;
    }

    try {
      // Cosmograph doesn't support updating existing nodes directly
      // The addPoints method expects new nodes with unique IDs
      // For now, we'll skip the incremental update and let the state update handle it
      log(`Skipping incremental update for ${nodes.length} nodes (not supported by Cosmograph)`);
      
      // Return false to indicate we couldn't do incremental update
      // This will trigger the fallback to state-based update
      return false;
    } catch (error) {
      log('Failed to update nodes:', error);
      onError?.(error as Error);
      return false;
    }
  }, [cosmographRef, log, onError]);

  /**
   * Apply node removals incrementally
   */
  const applyNodeRemovals = useCallback(async (nodeIds: string[]): Promise<boolean> => {
    if (!cosmographRef.current?.removePointsByIds) {
      log('Cosmograph removePointsByIds method not available');
      return false;
    }

    try {
      log(`Removing ${nodeIds.length} nodes`);
      await cosmographRef.current.removePointsByIds(nodeIds);
      
      // Remove from index map
      nodeIds.forEach(id => {
        nodeIdToIndexRef.current.delete(id);
      });
      
      onSuccess?.('removeNodes', nodeIds.length);
      return true;
    } catch (error) {
      log('Failed to remove nodes:', error);
      onError?.(error as Error);
      return false;
    }
  }, [cosmographRef, log, onSuccess, onError]);

  /**
   * Apply edge additions incrementally
   */
  const applyEdgeAdditions = useCallback(async (edges: GraphLink[]): Promise<boolean> => {
    if (!cosmographRef.current?.addLinks) {
      log('Cosmograph addLinks method not available');
      return false;
    }

    try {
      // Transform edges to ensure they have the required format
      const transformedEdges = edges.map(edge => ({
        source: edge.source || edge.from,
        target: edge.target || edge.to,
        // Don't include indices as Cosmograph will resolve them from IDs
        weight: edge.weight || 1,
        edge_type: edge.edge_type || 'default'
      }));
      
      log(`Adding ${edges.length} edges`);
      await cosmographRef.current.addLinks(transformedEdges);
      
      onSuccess?.('addEdges', edges.length);
      return true;
    } catch (error) {
      log('Failed to add edges:', error);
      onError?.(error as Error);
      return false;
    }
  }, [cosmographRef, log, onSuccess, onError]);

  /**
   * Apply edge removals incrementally
   */
  const applyEdgeRemovals = useCallback(async (edgePairs: [string, string][]): Promise<boolean> => {
    if (!cosmographRef.current?.removeLinksByPointIdPairs) {
      log('Cosmograph removeLinksByPointIdPairs method not available');
      return false;
    }

    try {
      log(`Removing ${edgePairs.length} edges`);
      await cosmographRef.current.removeLinksByPointIdPairs(edgePairs);
      
      onSuccess?.('removeEdges', edgePairs.length);
      return true;
    } catch (error) {
      log('Failed to remove edges:', error);
      onError?.(error as Error);
      return false;
    }
  }, [cosmographRef, log, onSuccess, onError]);

  /**
   * Apply a complete delta update
   */
  const applyDelta = useCallback(async (delta: DeltaUpdate): Promise<boolean> => {
    const startTime = performance.now();
    
    // Check if incremental updates are supported
    if (!supportsIncrementalUpdates(cosmographRef)) {
      log('Incremental updates not supported, falling back to full update');
      if (fallbackToFullUpdate && delta.nodes && delta.edges) {
        fallbackToFullUpdate(
          delta.operation === 'add' ? [...currentNodes, ...delta.nodes] : currentNodes,
          delta.operation === 'add' ? [...currentEdges, ...delta.edges] : currentEdges
        );
      }
      return false;
    }

    // Ensure node index map is initialized
    if (nodeIdToIndexRef.current.size === 0) {
      rebuildNodeIndexMap();
    }

    let success = true;

    try {
      log(`Applying delta: operation=${delta.operation}, nodes=${delta.nodes?.length || 0}, edges=${delta.edges?.length || 0}`);

      // Handle node operations
      if (delta.nodes && delta.nodes.length > 0) {
        switch (delta.operation) {
          case 'add':
            success = await applyNodeAdditions(delta.nodes) && success;
            break;
          case 'update':
            success = await applyNodeUpdates(delta.nodes) && success;
            break;
          case 'delete':
            const nodeIds = delta.nodeIds || delta.nodes.map(n => n.id);
            success = await applyNodeRemovals(nodeIds) && success;
            break;
        }
      }

      // Handle edge operations
      if (delta.edges && delta.edges.length > 0) {
        switch (delta.operation) {
          case 'add':
          case 'update': // Treat update as add for edges
            success = await applyEdgeAdditions(delta.edges) && success;
            break;
          case 'delete':
            const pairs = extractEdgePairs(delta.edgeIds || delta.edges);
            success = await applyEdgeRemovals(pairs) && success;
            break;
        }
      }

      const duration = performance.now() - startTime;
      updateMetrics(success, duration);
      
      if (success) {
        log(`Delta applied successfully in ${duration.toFixed(2)}ms`);
      } else {
        log(`Delta application partially failed in ${duration.toFixed(2)}ms`);
      }

      return success;
    } catch (error) {
      const duration = performance.now() - startTime;
      updateMetrics(false, duration);
      
      log('Failed to apply delta:', error);
      onError?.(error as Error);
      
      // Fall back to full update if available
      if (fallbackToFullUpdate) {
        log('Falling back to full update');
        fallbackToFullUpdate(currentNodes, currentEdges);
      }
      
      return false;
    }
  }, [
    cosmographRef,
    currentNodes,
    currentEdges,
    rebuildNodeIndexMap,
    applyNodeAdditions,
    applyNodeUpdates,
    applyNodeRemovals,
    applyEdgeAdditions,
    applyEdgeRemovals,
    updateMetrics,
    log,
    onError,
    fallbackToFullUpdate
  ]);

  /**
   * Reset the incremental update system
   */
  const reset = useCallback(() => {
    nodeIdToIndexRef.current.clear();
    setMetrics({
      totalUpdates: 0,
      successfulUpdates: 0,
      failedUpdates: 0,
      averageUpdateTime: 0,
      lastUpdateTime: Date.now(),
      lastUpdateDuration: 0
    });
    log('Incremental update system reset');
  }, [log]);

  return {
    // Main delta application method
    applyDelta,
    
    // Individual operation methods (for advanced use)
    applyNodeAdditions,
    applyNodeUpdates,
    applyNodeRemovals,
    applyEdgeAdditions,
    applyEdgeRemovals,
    
    // Utilities
    rebuildNodeIndexMap,
    reset,
    
    // Metrics
    metrics,
    
    // Check if ready
    isReady: supportsIncrementalUpdates(cosmographRef)
  };
}