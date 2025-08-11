/**
 * React hook for using Web Worker pool for graph processing
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { WorkerPool, WorkerTask, getDefaultWorkerPool } from '../workers/workerPool';
import { WorkerMessageType } from '../workers/graphProcessor.worker';
import { GraphNode } from '../../../api/types';
import { GraphLink } from '../../../types/graph';
import { logger } from '../../../utils/logger';

interface UseWorkerPoolOptions {
  useSharedPool?: boolean;
  maxWorkers?: number;
  autoScale?: boolean;
}

interface UseWorkerPoolReturn {
  // Processing functions
  processNodes: (nodes: GraphNode[], options?: any) => Promise<GraphNode[]>;
  processLinks: (links: GraphLink[], nodeIds: Set<string>) => Promise<GraphLink[]>;
  calculateLayout: (nodes: GraphNode[], links: GraphLink[], iterations?: number) => Promise<any>;
  calculateCentrality: (nodes: GraphNode[], links: GraphLink[], metric?: string) => Promise<Map<string, number>>;
  calculateClusters: (nodes: GraphNode[], links: GraphLink[]) => Promise<Map<string, number>>;
  
  // Search and filter
  filterNodes: (nodes: GraphNode[], criteria: any) => Promise<GraphNode[]>;
  searchNodes: (nodes: GraphNode[], query: string) => Promise<any[]>;
  findPaths: (nodes: GraphNode[], links: GraphLink[], source: string, target: string) => Promise<string[][]>;
  
  // Data operations
  transformData: (raw: any[]) => Promise<{ nodes: GraphNode[]; links: GraphLink[] }>;
  mergeDeltas: (current: any, deltas: any[]) => Promise<any>;
  validateData: (nodes: GraphNode[], links: GraphLink[]) => Promise<any>;
  calculateStats: (nodes: GraphNode[], links: GraphLink[]) => Promise<any>;
  
  // Control
  cancel: (taskId: string) => boolean;
  cancelAll: () => void;
  getStats: () => any;
  
  // State
  isProcessing: boolean;
  queueLength: number;
}

/**
 * Hook for using Web Worker pool
 */
export function useWorkerPool(options: UseWorkerPoolOptions = {}): UseWorkerPoolReturn {
  const {
    useSharedPool = true,
    maxWorkers,
    autoScale = true
  } = options;

  const poolRef = useRef<WorkerPool | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [queueLength, setQueueLength] = useState(0);
  const taskCounter = useRef(0);

  // Initialize pool
  useEffect(() => {
    if (useSharedPool) {
      poolRef.current = getDefaultWorkerPool();
    } else {
      poolRef.current = new WorkerPool({
        maxWorkers,
        autoScale
      });
    }

    logger.log('useWorkerPool: Initialized', {
      shared: useSharedPool,
      maxWorkers
    });

    // Update stats periodically
    const interval = setInterval(() => {
      if (poolRef.current) {
        const stats = poolRef.current.getStats();
        setQueueLength(stats.queueLength);
        setIsProcessing(stats.busyWorkers > 0 || stats.queueLength > 0);
      }
    }, 100);

    return () => {
      clearInterval(interval);
      
      // Clean up dedicated pool
      if (!useSharedPool && poolRef.current) {
        poolRef.current.terminate();
      }
    };
  }, [useSharedPool, maxWorkers, autoScale]);

  // Generate unique task ID
  const generateTaskId = useCallback(() => {
    return `task-${Date.now()}-${++taskCounter.current}`;
  }, []);

  // Execute task helper
  const executeTask = useCallback(async <T = any>(
    type: WorkerMessageType,
    payload: any
  ): Promise<T> => {
    if (!poolRef.current) {
      throw new Error('Worker pool not initialized');
    }

    const task: WorkerTask = {
      id: generateTaskId(),
      type,
      payload
    };

    try {
      setIsProcessing(true);
      const result = await poolRef.current.execute<T>(task);
      return result;
    } finally {
      // Update state will happen in interval
    }
  }, [generateTaskId]);

  // Process nodes
  const processNodes = useCallback(async (
    nodes: GraphNode[],
    options?: any
  ): Promise<GraphNode[]> => {
    return executeTask(WorkerMessageType.ProcessNodes, { nodes, options });
  }, [executeTask]);

  // Process links
  const processLinks = useCallback(async (
    links: GraphLink[],
    nodeIds: Set<string>
  ): Promise<GraphLink[]> => {
    return executeTask(WorkerMessageType.ProcessLinks, {
      links,
      nodeIds: Array.from(nodeIds)
    });
  }, [executeTask]);

  // Calculate layout
  const calculateLayout = useCallback(async (
    nodes: GraphNode[],
    links: GraphLink[],
    iterations?: number
  ): Promise<any> => {
    return executeTask(WorkerMessageType.CalculateLayout, {
      nodes,
      links,
      iterations
    });
  }, [executeTask]);

  // Calculate centrality
  const calculateCentrality = useCallback(async (
    nodes: GraphNode[],
    links: GraphLink[],
    metric?: string
  ): Promise<Map<string, number>> => {
    const result = await executeTask<any>(WorkerMessageType.CalculateCentrality, {
      nodes,
      links,
      metric
    });
    return new Map(Object.entries(result));
  }, [executeTask]);

  // Calculate clusters
  const calculateClusters = useCallback(async (
    nodes: GraphNode[],
    links: GraphLink[]
  ): Promise<Map<string, number>> => {
    const result = await executeTask<any>(WorkerMessageType.CalculateClusters, {
      nodes,
      links
    });
    return new Map(Object.entries(result));
  }, [executeTask]);

  // Filter nodes
  const filterNodes = useCallback(async (
    nodes: GraphNode[],
    criteria: any
  ): Promise<GraphNode[]> => {
    return executeTask(WorkerMessageType.FilterNodes, {
      nodes,
      criteria
    });
  }, [executeTask]);

  // Search nodes
  const searchNodes = useCallback(async (
    nodes: GraphNode[],
    query: string
  ): Promise<any[]> => {
    return executeTask(WorkerMessageType.SearchNodes, {
      nodes,
      query
    });
  }, [executeTask]);

  // Find paths
  const findPaths = useCallback(async (
    nodes: GraphNode[],
    links: GraphLink[],
    source: string,
    target: string
  ): Promise<string[][]> => {
    return executeTask(WorkerMessageType.FindPaths, {
      nodes,
      links,
      source,
      target
    });
  }, [executeTask]);

  // Transform data
  const transformData = useCallback(async (
    raw: any[]
  ): Promise<{ nodes: GraphNode[]; links: GraphLink[] }> => {
    return executeTask(WorkerMessageType.TransformData, { raw });
  }, [executeTask]);

  // Merge deltas
  const mergeDeltas = useCallback(async (
    current: any,
    deltas: any[]
  ): Promise<any> => {
    return executeTask(WorkerMessageType.MergeDeltas, {
      current,
      deltas
    });
  }, [executeTask]);

  // Validate data
  const validateData = useCallback(async (
    nodes: GraphNode[],
    links: GraphLink[]
  ): Promise<any> => {
    return executeTask(WorkerMessageType.ValidateData, {
      nodes,
      links
    });
  }, [executeTask]);

  // Calculate stats
  const calculateStats = useCallback(async (
    nodes: GraphNode[],
    links: GraphLink[]
  ): Promise<any> => {
    return executeTask(WorkerMessageType.CalculateStats, {
      nodes,
      links
    });
  }, [executeTask]);

  // Cancel task
  const cancel = useCallback((taskId: string): boolean => {
    if (!poolRef.current) return false;
    return poolRef.current.cancel(taskId);
  }, []);

  // Cancel all tasks
  const cancelAll = useCallback(() => {
    if (!poolRef.current) return;
    poolRef.current.cancelAll();
  }, []);

  // Get statistics
  const getStats = useCallback(() => {
    if (!poolRef.current) return null;
    return poolRef.current.getStats();
  }, []);

  return {
    // Processing functions
    processNodes,
    processLinks,
    calculateLayout,
    calculateCentrality,
    calculateClusters,
    
    // Search and filter
    filterNodes,
    searchNodes,
    findPaths,
    
    // Data operations
    transformData,
    mergeDeltas,
    validateData,
    calculateStats,
    
    // Control
    cancel,
    cancelAll,
    getStats,
    
    // State
    isProcessing,
    queueLength
  };
}

export default useWorkerPool;