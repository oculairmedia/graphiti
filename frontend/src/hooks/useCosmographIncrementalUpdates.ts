/**
 * useCosmographIncrementalUpdates Hook
 * 
 * Handles incremental updates to Cosmograph instance without full re-renders.
 * Uses Cosmograph's built-in incremental update API for smooth, real-time updates.
 */

import { useCallback, useRef, useEffect } from 'react';
import type { CosmographRef } from '@cosmograph/react';
import type { GraphNode, GraphLink } from '../types/graph';
import FallbackOrchestrator, { UpdateAttempt, ErrorClassifier } from '../utils/updateFallbackStrategies';
import {
  CosmographDataPreparer,
  getGlobalDataPreparer,
  transformNodesForCosmograph,
  transformEdgesForCosmograph,
  extractEdgePairs,
  buildNodeIdToIndexMap,
  supportsIncrementalUpdates,
  type DeltaUpdate,
  type CosmographPointInput,
  type CosmographLinkInput
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
    sizeMapping?: string;
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
  cosmographRef: React.RefObject<CosmographRef>,
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
  
  // Throttle simulation restarts across rapid-fire deltas
  const simRestartTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  
  // Data preparer for consistent data transformation
  const dataPreparerRef = useRef<CosmographDataPreparer>(getGlobalDataPreparer(config));
  
  // Initialize fallback orchestrator
  const fallbackOrchestratorRef = useRef<FallbackOrchestrator>(
    new FallbackOrchestrator({
      enableRetries: true,
      maxGlobalRetries: 3,
      enableQueueing: true,
      queueMaxSize: 50,
      enableBatching: true,
      batchDelay: 100,
      enableFullReload: !!fallbackToFullUpdate,
      onFallbackTriggered: (strategy, attempt) => {
        log(`Fallback strategy triggered: ${strategy} for ${attempt.operation}`);
      },
      onAllFallbacksFailed: (attempt) => {
        log(`All fallback strategies failed for ${attempt.operation}`, 'error');
        onError?.(new Error(`Failed to apply ${attempt.operation} after all fallback attempts`));
      }
    })
  );
  
  // Update config when it changes
  useEffect(() => {
    dataPreparerRef.current.updateConfig(config);
  }, [config]);
  
  // Performance metrics (ref to avoid re-renders on every delta)
  const metricsRef = useRef<IncrementalUpdateMetrics>({
    totalUpdates: 0,
    successfulUpdates: 0,
    failedUpdates: 0,
    averageUpdateTime: 0,
    lastUpdateTime: Date.now(),
    lastUpdateDuration: 0
  });

  // Logging helper
  const log = useCallback((message: string, ...args: unknown[]) => {
    if (debug) {
      console.log(`[useCosmographIncrementalUpdates] ${message}`, ...args);
    }
  }, [debug]);

  // Update metrics (mutate ref directly — no re-render)
  const updateMetrics = useCallback((success: boolean, duration: number) => {
    const prev = metricsRef.current;
    const newTotal = prev.totalUpdates + 1;
    const totalDuration = prev.averageUpdateTime * prev.totalUpdates + duration;

    metricsRef.current = {
      totalUpdates: newTotal,
      successfulUpdates: success ? prev.successfulUpdates + 1 : prev.successfulUpdates,
      failedUpdates: success ? prev.failedUpdates : prev.failedUpdates + 1,
      averageUpdateTime: totalDuration / newTotal,
      lastUpdateTime: Date.now(),
      lastUpdateDuration: duration
    };
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
        result.data.nodes.forEach((node: { id: string; index: number }) => {
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
          log('Exact fields being sent:', fieldNames);
          log('Field count:', fieldNames.length);
          log('Field values:', fieldNames.map(f => `${f}: ${typeof sample[f]}`));
        }
        
        // Check for problematic fields (only warn in debug mode)
        // SanitizedNode should only have primitive types after sanitization
        const hasArrays = Object.values(sample).some(v => Array.isArray(v));
        const hasObjects = Object.values(sample).some(v => 
          v !== null && typeof v === 'object' && !Array.isArray(v)
        );
        if ((hasArrays || hasObjects) && debug) {
          log('Warning: Node still has complex types!');
        }
      }
      
      await cosmographRef.current.addPoints(sanitizedNodes);
      
      sanitizedNodes.forEach((node) => {
        nodeIdToIndexRef.current.set(node.id, node.index);
      });
      
      onSuccess?.('addNodes', nodes.length);
      return true;
    } catch (error) {
      log('Failed to add nodes:', error);
      
      // Try fallback strategies for node addition failure
      const attempt: UpdateAttempt = {
        operation: 'addNodes',
        data: { nodes },
        error: error as Error,
        attemptNumber: 1,
        timestamp: Date.now()
      };
      
      const fallbackSuccess = await fallbackOrchestratorRef.current.handleFailure(attempt);
      if (!fallbackSuccess) {
        onError?.(error as Error);
      }
      return fallbackSuccess;
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

    // Guard: Skip if empty array (would cause SQL syntax error)
    if (!nodeIds || nodeIds.length === 0) {
      log('No nodes to remove (empty array)');
      return true; // Not an error, just nothing to do
    }

    // Filter to only include node IDs that exist in our index (prevents empty IN() SQL error)
    const existingNodeIds = nodeIds.filter(id => nodeIdToIndexRef.current.has(id));
    if (existingNodeIds.length === 0) {
      log(`No nodes to remove (none of ${nodeIds.length} node IDs exist in graph)`);
      return true; // Not an error, just nothing to do
    }

    try {
      log(`Removing ${existingNodeIds.length} nodes (${nodeIds.length - existingNodeIds.length} already removed)`);
      await cosmographRef.current.removePointsByIds(existingNodeIds);
      
      // Remove from index map
      existingNodeIds.forEach(id => {
        nodeIdToIndexRef.current.delete(id);
      });
      
      onSuccess?.('removeNodes', existingNodeIds.length);
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
      if (sanitizedLinks.length > 0 && debug) {
        const sample = sanitizedLinks[0];
        log('Sanitized link sample:', sample);
        
        // Debug: Check what fields are actually being sent
        const fieldNames = Object.keys(sample);
        const fieldTypes = Object.entries(sample).map(([k, v]) => `${k}:${typeof v}`);
        log('Link fields being sent to DuckDB:', fieldNames);
        log('Link field types:', fieldTypes);
        
        // Check for null/undefined
        const nullFields = Object.entries(sample).filter(([k, v]) => v === null || v === undefined);
        if (nullFields.length > 0) {
          log('WARNING: Link has null/undefined fields:', nullFields.map(([k]) => k));
        }
      }
      
      await cosmographRef.current.addLinks(sanitizedLinks);
      
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

    // Guard: Skip if empty array (would cause SQL syntax error)
    if (!edgePairs || edgePairs.length === 0) {
      log('No edges to remove (empty array)');
      return true; // Not an error, just nothing to do
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

    // Guard: Skip delta processing if initial data hasn't been loaded yet
    // This prevents errors like "IN ()" when trying to delete nodes before they exist
    if (currentNodes.length === 0) {
      log('Skipping delta - initial data not loaded yet');
      return true; // Not an error, just need to wait for initial data
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
            // Guard: Only call removal if we have node IDs
            if (nodeIds && nodeIds.length > 0) {
              success = await applyNodeRemovals(nodeIds) && success;
            }
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
            // Guard: Only call removal if we have edge pairs
            if (pairs && pairs.length > 0) {
              success = await applyEdgeRemovals(pairs) && success;
            }
            break;
        }
      }

      const duration = performance.now() - startTime;
      updateMetrics(success, duration);
      
      if (success) {
        log(`Delta applied successfully in ${duration.toFixed(2)}ms`);
        
        if (simRestartTimerRef.current) clearTimeout(simRestartTimerRef.current);
        simRestartTimerRef.current = setTimeout(() => {
          if (cosmographRef.current?.start) {
            cosmographRef.current.start(0.05);
          }
          simRestartTimerRef.current = null;
        }, 2000);
      } else {
        log(`Delta application partially failed in ${duration.toFixed(2)}ms`);
      }

      return success;
    } catch (error) {
      const duration = performance.now() - startTime;
      updateMetrics(false, duration);
      
      log('Failed to apply delta:', error);
      
      // Create update attempt for fallback handling
      const attempt: UpdateAttempt = {
        operation: `delta-${delta.operation}`,
        data: delta,
        error: error as Error,
        attemptNumber: 1,
        timestamp: Date.now()
      };
      
      // Classify the error to determine best recovery approach
      const classification = ErrorClassifier.classify(error as Error);
      log(`Error classified as ${classification.severity}, recoverable: ${classification.recoverable}`);
      
      // Try fallback strategies
      const fallbackSuccess = await fallbackOrchestratorRef.current.handleFailure(attempt);
      
      if (!fallbackSuccess) {
        // All fallbacks failed, try full reload as last resort
        onError?.(error as Error);
        
        if (fallbackToFullUpdate) {
          log('All fallbacks failed, attempting full update');
          fallbackToFullUpdate(currentNodes, currentEdges);
        }
      }
      
      return fallbackSuccess;
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
      
      // Rebuild index map - uses currentNodes from closure (which will be updated after this call returns)
      // Note: The nodes parameter here represents the new data, but rebuildNodeIndexMap will use currentNodes
      // which should be updated by the caller after calling this function
      await rebuildNodeIndexMap();
      
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
    metricsRef.current = {
      totalUpdates: 0,
      successfulUpdates: 0,
      failedUpdates: 0,
      averageUpdateTime: 0,
      lastUpdateTime: Date.now(),
      lastUpdateDuration: 0
    };
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
    metrics: metricsRef,
    
    // Check if ready
    isReady: supportsIncrementalUpdates(cosmographRef)
  };
}