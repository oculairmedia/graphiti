import { useEffect, useRef, useState, useCallback } from 'react';
import { IncrementalUpdatePipeline, GraphDelta } from '@/services/incrementalUpdatePipeline';
import { versionSync } from '@/services/version-sync';
import { useRustWebSocket } from '@/contexts/RustWebSocketProvider';
import { GraphNode } from '@/api/types';
import { GraphLink } from '@/types/graph';
import { logger } from '@/utils/logger';

interface UseOptimizedIncrementalUpdatesOptions {
  enabled?: boolean;
  batchSize?: number;
  batchDelay?: number;
  enableDeduplication?: boolean;
  enableMerging?: boolean;
  onUpdate?: (nodes: GraphNode[], edges: GraphLink[]) => void;
  onError?: (error: Error) => void;
}

interface IncrementalUpdateState {
  isProcessing: boolean;
  queueSize: number;
  totalProcessed: number;
  totalDeduplicated: number;
  totalMerged: number;
  lastUpdateTime: number;
  currentSequence: number;
}

/**
 * Optimized hook for managing incremental graph updates with smart batching and deduplication
 */
export function useOptimizedIncrementalUpdates({
  enabled = true,
  batchSize = 100,
  batchDelay = 50,
  enableDeduplication = true,
  enableMerging = true,
  onUpdate,
  onError,
}: UseOptimizedIncrementalUpdatesOptions = {}) {
  const { subscribe } = useRustWebSocket();
  const pipelineRef = useRef<IncrementalUpdatePipeline | null>(null);
  
  // Current graph data
  const nodesRef = useRef<Map<string, GraphNode>>(new Map());
  const edgesRef = useRef<Map<string, GraphLink>>(new Map());
  
  const [state, setState] = useState<IncrementalUpdateState>({
    isProcessing: false,
    queueSize: 0,
    totalProcessed: 0,
    totalDeduplicated: 0,
    totalMerged: 0,
    lastUpdateTime: 0,
    currentSequence: 0,
  });
  
  // Initialize pipeline
  useEffect(() => {
    if (!enabled) return;
    
    // Create pipeline instance
    pipelineRef.current = new IncrementalUpdatePipeline({
      batchSize,
      batchDelay,
      maxQueueSize: 5000,
      enableDeduplication,
      enableMerging,
      priorityMode: 'smart',
    });
    
    // Set up batch processing callback
    pipelineRef.current.onBatch((delta: GraphDelta) => {
      applyDeltaToGraph(delta);
      updateState();
    });
    
    // Set up error callback
    pipelineRef.current.onErrorOccurred((error: Error) => {
      logger.error('Incremental update error:', error);
      onError?.(error);
    });
    
    return () => {
      pipelineRef.current?.destroy();
      pipelineRef.current = null;
    };
  }, [enabled, batchSize, batchDelay, enableDeduplication, enableMerging]);
  
  // Apply delta to current graph data
  const applyDeltaToGraph = useCallback((delta: GraphDelta) => {
    const startTime = performance.now();
    let nodesChanged = false;
    let edgesChanged = false;
    
    // Process node removals
    for (const nodeId of delta.nodes_removed) {
      if (nodesRef.current.delete(nodeId)) {
        nodesChanged = true;
        
        // Also remove edges connected to this node
        for (const [edgeId, edge] of edgesRef.current.entries()) {
          if (edge.source === nodeId || edge.target === nodeId) {
            edgesRef.current.delete(edgeId);
            edgesChanged = true;
          }
        }
      }
    }
    
    // Process node additions
    for (const node of delta.nodes_added) {
      nodesRef.current.set(node.id, node);
      nodesChanged = true;
    }
    
    // Process node updates
    for (const node of delta.nodes_updated) {
      const existing = nodesRef.current.get(node.id);
      if (existing) {
        // Merge update with existing node
        nodesRef.current.set(node.id, { ...existing, ...node });
      } else {
        // Node doesn't exist, add it
        nodesRef.current.set(node.id, node);
      }
      nodesChanged = true;
    }
    
    // Process edge removals
    for (const [source, target] of delta.edges_removed) {
      const edgeId = `${source}-${target}`;
      if (edgesRef.current.delete(edgeId)) {
        edgesChanged = true;
      }
    }
    
    // Process edge additions
    for (const edge of delta.edges_added) {
      const edgeId = `${edge.source}-${edge.target}`;
      
      // Only add edge if both nodes exist
      if (nodesRef.current.has(edge.source) && nodesRef.current.has(edge.target)) {
        edgesRef.current.set(edgeId, edge);
        edgesChanged = true;
      } else {
        logger.warn(`Skipping edge ${edgeId}: missing nodes`);
      }
    }
    
    // Process edge updates
    for (const edge of delta.edges_updated) {
      const edgeId = `${edge.source}-${edge.target}`;
      const existing = edgesRef.current.get(edgeId);
      if (existing) {
        // Merge update with existing edge
        edgesRef.current.set(edgeId, { ...existing, ...edge });
        edgesChanged = true;
      } else if (nodesRef.current.has(edge.source) && nodesRef.current.has(edge.target)) {
        // Edge doesn't exist but nodes do, add it
        edgesRef.current.set(edgeId, edge);
        edgesChanged = true;
      }
    }
    
    // Notify if there were changes
    if ((nodesChanged || edgesChanged) && onUpdate) {
      const nodes = Array.from(nodesRef.current.values());
      const edges = Array.from(edgesRef.current.values());
      
      // Use requestAnimationFrame to batch UI updates
      requestAnimationFrame(() => {
        onUpdate(nodes, edges);
      });
    }
    
    const processingTime = performance.now() - startTime;
    logger.log(`Applied delta in ${processingTime.toFixed(2)}ms`, {
      nodesChanged,
      edgesChanged,
      nodeCount: nodesRef.current.size,
      edgeCount: edgesRef.current.size,
    });
  }, [onUpdate]);
  
  // Update state from pipeline stats
  const updateState = useCallback(() => {
    if (!pipelineRef.current) return;
    
    const stats = pipelineRef.current.getStats();
    setState({
      isProcessing: stats.queueSize > 0,
      queueSize: stats.queueSize,
      totalProcessed: stats.totalProcessed,
      totalDeduplicated: stats.totalDeduplicated,
      totalMerged: stats.totalMerged,
      lastUpdateTime: Date.now(),
      currentSequence: stats.lastProcessedSequence,
    });
  }, []);
  
  // Subscribe to WebSocket updates
  useEffect(() => {
    if (!enabled || !pipelineRef.current) return;
    
    // Subscribe to delta updates from WebSocket
    const unsubscribe = subscribe('delta', (delta: any) => {
      logger.log('Received WebSocket delta:', {
        sequence: delta.sequence,
        operation: delta.operation,
      });
      
      // Add to pipeline for processing
      pipelineRef.current?.addDelta(delta);
    });
    
    return unsubscribe;
  }, [enabled, subscribe]);
  
  // Subscribe to version sync updates
  useEffect(() => {
    if (!enabled || !pipelineRef.current) return;
    
    // Subscribe to version sync deltas
    const unsubscribe = versionSync.onDelta((delta: GraphDelta) => {
      logger.log('Received version sync delta:', {
        sequence: delta.sequence,
        operation: delta.operation,
      });
      
      // Add to pipeline for processing
      pipelineRef.current?.addDelta(delta);
    });
    
    // Start version polling
    versionSync.startPolling();
    
    return () => {
      unsubscribe();
      versionSync.stopPolling();
    };
  }, [enabled]);
  
  // Manual functions
  const clearQueue = useCallback(() => {
    pipelineRef.current?.clear();
    updateState();
  }, [updateState]);
  
  const getStats = useCallback(() => {
    return pipelineRef.current?.getStats() || {
      totalProcessed: 0,
      totalDeduplicated: 0,
      totalMerged: 0,
      avgBatchSize: 0,
      avgProcessingTime: 0,
      queueSize: 0,
      lastProcessedSequence: 0,
    };
  }, []);
  
  const setGraphData = useCallback((nodes: GraphNode[], edges: GraphLink[]) => {
    // Clear existing data
    nodesRef.current.clear();
    edgesRef.current.clear();
    
    // Add new data
    for (const node of nodes) {
      nodesRef.current.set(node.id, node);
    }
    
    for (const edge of edges) {
      const edgeId = `${edge.source}-${edge.target}`;
      edgesRef.current.set(edgeId, edge);
    }
    
    logger.log('Set graph data:', {
      nodes: nodes.length,
      edges: edges.length,
    });
    
    // Notify update
    if (onUpdate) {
      onUpdate(nodes, edges);
    }
  }, [onUpdate]);
  
  const getCurrentData = useCallback(() => {
    return {
      nodes: Array.from(nodesRef.current.values()),
      edges: Array.from(edgesRef.current.values()),
    };
  }, []);
  
  const forceSync = useCallback(async () => {
    try {
      logger.log('Forcing version sync...');
      const deltas = await versionSync.sync();
      
      // Process all deltas through pipeline
      for (const delta of deltas) {
        pipelineRef.current?.addDelta(delta);
      }
      
      return deltas.length;
    } catch (error) {
      logger.error('Force sync failed:', error);
      onError?.(error as Error);
      return 0;
    }
  }, [onError]);
  
  return {
    ...state,
    clearQueue,
    getStats,
    setGraphData,
    getCurrentData,
    forceSync,
  };
}