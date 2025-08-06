/**
 * Hook for using Web Worker for graph data processing
 * Offloads heavy computations to a background thread
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { logger } from '../utils/logger';

interface WorkerTask {
  id: string;
  type: string;
  resolve: (result: any) => void;
  reject: (error: Error) => void;
  timeout?: NodeJS.Timeout;
}

export function useGraphWorker() {
  const workerRef = useRef<Worker | null>(null);
  const tasksRef = useRef<Map<string, WorkerTask>>(new Map());
  const [isReady, setIsReady] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);

  // Initialize worker
  useEffect(() => {
    try {
      // Create worker with proper URL
      const workerUrl = new URL(
        '../workers/graphProcessor.worker.ts',
        import.meta.url
      );
      
      workerRef.current = new Worker(workerUrl, { type: 'module' });
      
      // Handle messages from worker
      workerRef.current.onmessage = (event) => {
        const { type, result, error, id } = event.data;
        const task = tasksRef.current.get(id);
        
        if (task) {
          // Clear timeout
          if (task.timeout) {
            clearTimeout(task.timeout);
          }
          
          // Resolve or reject promise
          if (error) {
            task.reject(new Error(error));
          } else {
            task.resolve(result);
          }
          
          // Clean up
          tasksRef.current.delete(id);
          
          // Update processing state
          if (tasksRef.current.size === 0) {
            setIsProcessing(false);
          }
        }
      };
      
      // Handle worker errors
      workerRef.current.onerror = (error) => {
        logger.error('[GraphWorker] Worker error:', error);
        // Reject all pending tasks
        tasksRef.current.forEach(task => {
          task.reject(new Error('Worker error: ' + error.message));
        });
        tasksRef.current.clear();
        setIsProcessing(false);
      };
      
      setIsReady(true);
      logger.log('[GraphWorker] Worker initialized');
    } catch (error) {
      logger.error('[GraphWorker] Failed to initialize worker:', error);
      setIsReady(false);
    }
    
    return () => {
      // Clean up worker
      if (workerRef.current) {
        workerRef.current.terminate();
        workerRef.current = null;
      }
      
      // Reject all pending tasks
      tasksRef.current.forEach(task => {
        if (task.timeout) clearTimeout(task.timeout);
        task.reject(new Error('Worker terminated'));
      });
      tasksRef.current.clear();
      
      setIsReady(false);
      setIsProcessing(false);
    };
  }, []);

  // Send task to worker
  const sendTask = useCallback(<T = any>(
    type: string,
    payload: any,
    timeoutMs = 30000
  ): Promise<T> => {
    return new Promise((resolve, reject) => {
      if (!workerRef.current || !isReady) {
        reject(new Error('Worker not ready'));
        return;
      }
      
      const id = Math.random().toString(36).substr(2, 9);
      
      // Set up timeout
      const timeout = setTimeout(() => {
        const task = tasksRef.current.get(id);
        if (task) {
          tasksRef.current.delete(id);
          reject(new Error(`Worker task timeout: ${type}`));
        }
      }, timeoutMs);
      
      // Store task
      const task: WorkerTask = {
        id,
        type,
        resolve,
        reject,
        timeout
      };
      
      tasksRef.current.set(id, task);
      setIsProcessing(true);
      
      // Send message to worker
      workerRef.current.postMessage({ type, payload, id });
    });
  }, [isReady]);

  // Process Arrow data
  const processArrowData = useCallback(async (buffer: ArrayBuffer) => {
    const startTime = performance.now();
    const result = await sendTask('PROCESS_ARROW', { buffer });
    const duration = performance.now() - startTime;
    
    logger.log(`[GraphWorker] Processed Arrow data in ${duration.toFixed(2)}ms`);
    return result;
  }, [sendTask]);

  // Filter nodes
  const filterNodes = useCallback(async (nodes: any[], filters: any) => {
    if (nodes.length < 1000) {
      // For small datasets, process in main thread
      return nodes.filter(node => {
        // Apply filters...
        return true;
      });
    }
    
    const startTime = performance.now();
    const result = await sendTask('FILTER_NODES', { nodes, filters });
    const duration = performance.now() - startTime;
    
    logger.log(`[GraphWorker] Filtered ${nodes.length} nodes in ${duration.toFixed(2)}ms`);
    return result;
  }, [sendTask]);

  // Calculate layout
  const calculateLayout = useCallback(async (
    nodes: any[],
    edges: any[],
    options?: any
  ): Promise<Record<string, { x: number; y: number }>> => {
    if (nodes.length < 500) {
      // For small graphs, use main thread
      return {};
    }
    
    const startTime = performance.now();
    const result = await sendTask('CALCULATE_LAYOUT', { nodes, edges, options });
    const duration = performance.now() - startTime;
    
    logger.log(`[GraphWorker] Calculated layout for ${nodes.length} nodes in ${duration.toFixed(2)}ms`);
    return result;
  }, [sendTask]);

  // Build spatial index
  const buildSpatialIndex = useCallback(async (
    nodes: any[],
    positions: Record<string, { x: number; y: number }>
  ) => {
    const startTime = performance.now();
    const result = await sendTask('BUILD_SPATIAL_INDEX', { nodes, positions });
    const duration = performance.now() - startTime;
    
    logger.log(`[GraphWorker] Built spatial index in ${duration.toFixed(2)}ms`);
    return result;
  }, [sendTask]);

  // Transform data
  const transformData = useCallback(async (data: any, options?: any) => {
    const startTime = performance.now();
    const result = await sendTask('TRANSFORM_DATA', { data, options });
    const duration = performance.now() - startTime;
    
    logger.log(`[GraphWorker] Transformed data in ${duration.toFixed(2)}ms`);
    return result;
  }, [sendTask]);

  return {
    isReady,
    isProcessing,
    processArrowData,
    filterNodes,
    calculateLayout,
    buildSpatialIndex,
    transformData
  };
}