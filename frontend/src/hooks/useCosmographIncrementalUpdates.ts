/**
 * useCosmographIncrementalUpdates Hook
 * 
 * Handles incremental updates to Cosmograph instance without full re-renders.
 * Uses Cosmograph's built-in incremental update API for smooth, real-time updates.
 */

import { useCallback, useRef, useState, useEffect } from 'react';
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
import {
  CosmographDataPreparer,
  getGlobalDataPreparer
} from '../utils/cosmographDataPreparer';

/**
 * Hook options
 */
export interface UseCosmographIncrementalUpdatesOptions {
  onError?: (error: Error) => void;
  onSuccess?: (operation: string, count: number) => void;
  debug?: boolean;
  fallbackToFullUpdate?: (nodes: GraphNode[], edges: GraphLink[]) => void;
  config?: {
    clusteringMethod?: string;
    centralityMetric?: string;
    clusterStrength?: number;
  };
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
    fallbackToFullUpdate,
    config = {}
  } = options;

  // Track node ID to index mapping
  const nodeIdToIndexRef = useRef<Map<string, number>>(new Map());
  
  // Data preparer for consistent data transformation
  const dataPreparerRef = useRef<CosmographDataPreparer>(getGlobalDataPreparer(config));
  
  // Update config when it changes
  useEffect(() => {
    dataPreparerRef.current.updateConfig(config);
  }, [config]);
  
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
   * Initialize or rebuild the node ID to index map and data preparer
   */
  const rebuildNodeIndexMap = useCallback(async () => {
    nodeIdToIndexRef.current = buildNodeIdToIndexMap(currentNodes);
    // Initialize data preparer with current graph data
    try {
      const result = await dataPreparerRef.current.prepareInitialData(currentNodes, currentEdges);
      // Update the local node index from the preparer's data
      if (result?.data?.nodes) {
        result.data.nodes.forEach((node: any) => {
          nodeIdToIndexRef.current.set(node.id, node.index);
        });
      }
      log(`Rebuilt node index map with ${nodeIdToIndexRef.current.size} nodes`);
    } catch (error) {
      log('Failed to prepare initial data:', error);
    }
  }, [currentNodes, currentEdges, log]);

  /**
   * Apply node additions incrementally
   */
  const applyNodeAdditions = useCallback(async (nodes: GraphNode[]): Promise<boolean> => {
    if (!cosmographRef.current?.addPoints) {
      log('Cosmograph addPoints method not available');
      return false;
    }

    try {
      // Use data preparer to ensure consistent transformation
      const { nodes: sanitizedNodes, links: _ } = await dataPreparerRef.current.prepareIncrementalData(nodes, []);
      
      if (sanitizedNodes.length === 0) {
        log('No new nodes to add');
        return true;
      }
      
      log(`Adding ${sanitizedNodes.length} nodes with sanitized data`);
      
      // Log sample for debugging (only if schema debugging is enabled)
      if (sanitizedNodes.length > 0 && debug) {
        const sample = sanitizedNodes[0];
        log('Sanitized node sample:', sample);
        
        // Check if schema debugging is enabled for detailed logging
        const schemaDebugEnabled = localStorage.getItem('debug_cosmograph_schema') === 'true' ||
                                   import.meta.env.VITE_DEBUG_COSMOGRAPH_SCHEMA === 'true';
        
        if (schemaDebugEnabled) {
          // Log exact field count and names for debugging
          const fieldNames = Object.keys(sample);
          console.log('[useCosmographIncrementalUpdates] Exact fields being sent:', fieldNames);
          console.log('[useCosmographIncrementalUpdates] Field count:', fieldNames.length);
          console.log('[useCosmographIncrementalUpdates] Field values:', fieldNames.map(f => `${f}: ${typeof sample[f]}`));
        }
        
        // Check for problematic fields
        const hasArrays = Object.values(sample).some(v => Array.isArray(v));
        const hasObjects = Object.values(sample).some(v => 
          v !== null && typeof v === 'object' && !Array.isArray(v) && v !== sample.properties
        );
        if (hasArrays || hasObjects) {
          console.warn('[useCosmographIncrementalUpdates] Node still has complex types!');
        }
      }
      
      await cosmographRef.current.addPoints(sanitizedNodes);
      
      // Update the index map
      sanitizedNodes.forEach((node) => {
        nodeIdToIndexRef.current.set(node.id, node.index);
      });
      
      // Reheat simulation after adding nodes to keep animation running smoothly
      // Using reheat instead of restart to avoid pausing the animation
      if (cosmographRef.current.reheat) {
        cosmographRef.current.reheat(0.1); // Small alpha value for gentle energy addition
        log('Reheated simulation after adding nodes');
      } else if (cosmographRef.current.restart) {
        // Fallback to restart if reheat is not available
        cosmographRef.current.restart();
        log('Restarted simulation after adding nodes');
      }
      
      onSuccess?.('addNodes', nodes.length);
      return true;
    } catch (error) {
      log('Failed to add nodes:', error);
      onError?.(error as Error);
      return false;
    }
  }, [cosmographRef, log, onSuccess, onError]);

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
      // Use data preparer to ensure consistent transformation
      const { links: sanitizedLinks } = await dataPreparerRef.current.prepareIncrementalData([], edges);
      
      if (sanitizedLinks.length === 0) {
        log('No valid links to add');
        return true; // Not an error, just no valid links
      }
      
      log(`Adding ${sanitizedLinks.length} sanitized edges (from ${edges.length} input)`);
      if (sanitizedLinks.length > 0) {
        const sample = sanitizedLinks[0];
        log('Sanitized link sample:', sample);
        
        // Debug: Check what fields are actually being sent
        const fieldNames = Object.keys(sample);
        const fieldTypes = Object.entries(sample).map(([k, v]) => `${k}:${typeof v}`);
        console.log('[DEBUG] Link fields being sent to DuckDB:', fieldNames);
        console.log('[DEBUG] Link field types:', fieldTypes);
        console.log('[DEBUG] Link field values:', Object.entries(sample).map(([k, v]) => `${k}=${v}`));
        console.log('[DEBUG] Link field count:', fieldNames.length);
        
        // Check for null/undefined
        const nullFields = Object.entries(sample).filter(([k, v]) => v === null || v === undefined);
        if (nullFields.length > 0) {
          console.error('[DEBUG] WARNING: Link has null/undefined fields:', nullFields.map(([k]) => k));
        }
      }
      
      await cosmographRef.current.addLinks(sanitizedLinks);
      
      // Reheat simulation after adding edges to keep animation running smoothly
      // Using reheat instead of restart to avoid pausing the animation
      if (cosmographRef.current.reheat) {
        cosmographRef.current.reheat(0.1); // Small alpha value for gentle energy addition
        log('Reheated simulation after adding edges');
      } else if (cosmographRef.current.restart) {
        // Fallback to restart if reheat is not available
        cosmographRef.current.restart();
        log('Restarted simulation after adding edges');
      }
      
      onSuccess?.('addEdges', sanitizedLinks.length);
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

    // Ensure node index map and data preparer are initialized
    if (nodeIdToIndexRef.current.size === 0 || dataPreparerRef.current.getNodeCount() === 0) {
      await rebuildNodeIndexMap();
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
   * Replace entire dataset using setConfig to avoid hard reloading
   * This is an alternative to incremental updates when full replacement is needed
   */
  const replaceDataWithConfig = useCallback(async (nodes: GraphNode[], edges: GraphLink[]): Promise<boolean> => {
    if (!cosmographRef.current?.setConfig) {
      log('Cosmograph setConfig method not available');
      return false;
    }

    try {
      const startTime = performance.now();
      log(`Replacing entire dataset: ${nodes.length} nodes, ${edges.length} edges`);
      
      // Reset and prepare all data
      dataPreparerRef.current.reset();
      const { data } = await dataPreparerRef.current.prepareInitialData(nodes, edges);
      
      // Use setConfig to replace data without hard reloading
      await cosmographRef.current.setConfig({
        points: data.nodes,
        links: data.links
      });
      
      // Rebuild index map
      rebuildNodeIndexMap(nodes);
      
      const duration = performance.now() - startTime;
      log(`Data replaced successfully using setConfig in ${duration.toFixed(2)}ms`);
      
      onSuccess?.('replaceData', nodes.length + edges.length);
      return true;
    } catch (error) {
      log('Failed to replace data with setConfig:', error);
      onError?.(error as Error);
      return false;
    }
  }, [cosmographRef, rebuildNodeIndexMap, log, onSuccess, onError, currentNodes]);

  /**
   * Reset the incremental update system
   */
  const reset = useCallback(() => {
    nodeIdToIndexRef.current.clear();
    dataPreparerRef.current.reset();
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
    
    // Full data replacement without hard reload
    replaceDataWithConfig,
    
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