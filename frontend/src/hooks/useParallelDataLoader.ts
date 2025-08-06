/**
 * Hook for parallel data loading with progress tracking
 * Coordinates multiple data sources and provides unified loading state
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { preloader } from '../services/preloader';
import { useDuckDB } from '../contexts/DuckDBProvider';
import { useGraphWorker } from './useGraphWorker';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import * as arrow from 'apache-arrow';
import { logger } from '../utils/logger';

interface ParallelLoadState {
  nodes: GraphNode[];
  links: GraphLink[];
  isLoading: boolean;
  progress: number;
  loadTime: number | null;
  error: Error | null;
  stats: {
    nodeCount: number;
    edgeCount: number;
    fromCache: boolean;
    fromPreload: boolean;
    loadMethod: 'preload' | 'cache' | 'network' | null;
  };
}

interface UseParallelDataLoaderOptions {
  autoLoad?: boolean;
  useWorker?: boolean;
  maxParallelRequests?: number;
}

export function useParallelDataLoader(options: UseParallelDataLoaderOptions = {}) {
  const {
    autoLoad = true,
    useWorker = true,
    maxParallelRequests = 3
  } = options;

  const [state, setState] = useState<ParallelLoadState>({
    nodes: [],
    links: [],
    isLoading: false,
    progress: 0,
    loadTime: null,
    error: null,
    stats: {
      nodeCount: 0,
      edgeCount: 0,
      fromCache: false,
      fromPreload: false,
      loadMethod: null
    }
  });

  const { getDuckDBConnection } = useDuckDB();
  const { processArrowData, isReady: workerReady } = useGraphWorker();
  const hasLoadedRef = useRef(false);
  const loadStartTimeRef = useRef<number>(0);

  /**
   * Load data from all sources in parallel
   */
  const loadDataParallel = useCallback(async () => {
    if (hasLoadedRef.current) {
      logger.log('[ParallelLoader] Data already loaded, skipping');
      return;
    }

    setState(prev => ({ ...prev, isLoading: true, progress: 0, error: null }));
    loadStartTimeRef.current = performance.now();
    logger.log('[ParallelLoader] Starting parallel data load...');

    try {
      // Step 1: Check preloaded data first (fastest)
      const preloadedData = await preloader.getAllPreloadedData();
      
      if (preloadedData.nodes && preloadedData.edges) {
        logger.log('[ParallelLoader] Using preloaded data');
        
        // Process with worker if available
        const processedData = await processData(
          preloadedData.nodes,
          preloadedData.edges,
          useWorker && workerReady
        );
        
        const loadTime = performance.now() - loadStartTimeRef.current;
        
        setState({
          nodes: processedData.nodes,
          links: processedData.links,
          isLoading: false,
          progress: 100,
          loadTime,
          error: null,
          stats: {
            nodeCount: processedData.nodes.length,
            edgeCount: processedData.links.length,
            fromCache: false,
            fromPreload: true,
            loadMethod: 'preload'
          }
        });
        
        hasLoadedRef.current = true;
        logger.log(`[ParallelLoader] Loaded from preloader in ${loadTime.toFixed(2)}ms`);
        return;
      }

      // Step 2: Try to load from DuckDB if available
      const duckdbConn = getDuckDBConnection();
      if (duckdbConn?.connection) {
        setState(prev => ({ ...prev, progress: 20 }));
        
        const [nodesResult, edgesResult] = await Promise.all([
          duckdbConn.connection.query('SELECT * FROM nodes LIMIT 10000'),
          duckdbConn.connection.query('SELECT * FROM edges LIMIT 20000')
        ]);
        
        if (nodesResult && edgesResult) {
          setState(prev => ({ ...prev, progress: 60 }));
          
          const nodes = nodesResult.toArray().map((n: any) => ({
            id: n.id,
            label: n.label || n.id,
            node_type: n.node_type || 'Unknown',
            properties: n
          }));
          
          const links = edgesResult.toArray().map((e: any) => ({
            source: e.source,
            target: e.target,
            edge_type: e.edge_type || 'RELATED',
            weight: e.weight || 1
          }));
          
          const loadTime = performance.now() - loadStartTimeRef.current;
          
          setState({
            nodes,
            links,
            isLoading: false,
            progress: 100,
            loadTime,
            error: null,
            stats: {
              nodeCount: nodes.length,
              edgeCount: links.length,
              fromCache: true,
              fromPreload: false,
              loadMethod: 'cache'
            }
          });
          
          hasLoadedRef.current = true;
          logger.log(`[ParallelLoader] Loaded from DuckDB in ${loadTime.toFixed(2)}ms`);
          return;
        }
      }

      // Step 3: Fallback to network fetch
      setState(prev => ({ ...prev, progress: 30 }));
      
      const rustServerUrl = import.meta.env.VITE_RUST_SERVER_URL || 'http://192.168.50.90:3000';
      const [nodesResponse, edgesResponse] = await Promise.all([
        fetch(`${rustServerUrl}/api/arrow/nodes`),
        fetch(`${rustServerUrl}/api/arrow/edges`)
      ]);
      
      setState(prev => ({ ...prev, progress: 50 }));
      
      if (!nodesResponse.ok || !edgesResponse.ok) {
        throw new Error('Failed to fetch data from network');
      }
      
      const [nodesBuffer, edgesBuffer] = await Promise.all([
        nodesResponse.arrayBuffer(),
        edgesResponse.arrayBuffer()
      ]);
      
      setState(prev => ({ ...prev, progress: 70 }));
      
      const processedData = await processData(
        nodesBuffer,
        edgesBuffer,
        useWorker && workerReady
      );
      
      const loadTime = performance.now() - loadStartTimeRef.current;
      
      setState({
        nodes: processedData.nodes,
        links: processedData.links,
        isLoading: false,
        progress: 100,
        loadTime,
        error: null,
        stats: {
          nodeCount: processedData.nodes.length,
          edgeCount: processedData.links.length,
          fromCache: false,
          fromPreload: false,
          loadMethod: 'network'
        }
      });
      
      hasLoadedRef.current = true;
      logger.log(`[ParallelLoader] Loaded from network in ${loadTime.toFixed(2)}ms`);
      
    } catch (error) {
      const loadTime = performance.now() - loadStartTimeRef.current;
      logger.error('[ParallelLoader] Failed to load data:', error);
      
      setState(prev => ({
        ...prev,
        isLoading: false,
        progress: 0,
        loadTime,
        error: error as Error
      }));
    }
  }, [getDuckDBConnection, processArrowData, workerReady, useWorker]);

  /**
   * Process Arrow data (with or without worker)
   */
  async function processData(
    nodesBuffer: ArrayBuffer,
    edgesBuffer: ArrayBuffer,
    useWorker: boolean
  ): Promise<{ nodes: GraphNode[]; links: GraphLink[] }> {
    if (useWorker) {
      try {
        const result = await processArrowData(nodesBuffer);
        const edgeResult = await processArrowData(edgesBuffer);
        return {
          nodes: result.nodes || [],
          links: edgeResult.edges || []
        };
      } catch (error) {
        logger.warn('[ParallelLoader] Worker processing failed, falling back to main thread');
      }
    }
    
    // Fallback to main thread processing
    const nodesTable = arrow.tableFromIPC(new Uint8Array(nodesBuffer));
    const edgesTable = arrow.tableFromIPC(new Uint8Array(edgesBuffer));
    
    const nodes = nodesTable.toArray().map((n: any) => ({
      id: n.id,
      label: n.label || n.id,
      node_type: n.node_type || 'Unknown',
      properties: n
    }));
    
    const links = edgesTable.toArray().map((e: any) => ({
      source: e.source || e.from,
      target: e.target || e.to,
      edge_type: e.edge_type || 'RELATED',
      weight: e.weight || 1
    }));
    
    return { nodes, links };
  }

  /**
   * Reload data (bypasses cache)
   */
  const reloadData = useCallback(() => {
    hasLoadedRef.current = false;
    preloader.clearPreloadedData();
    loadDataParallel();
  }, [loadDataParallel]);

  /**
   * Get loading statistics
   */
  const getLoadStats = useCallback(() => {
    const preloaderStats = preloader.getStats();
    return {
      ...state.stats,
      preloaderStats,
      loadTime: state.loadTime,
      hasData: state.nodes.length > 0
    };
  }, [state]);

  // Auto-load on mount if enabled
  useEffect(() => {
    if (autoLoad && !hasLoadedRef.current) {
      loadDataParallel();
    }
  }, [autoLoad, loadDataParallel]);

  return {
    // Data
    nodes: state.nodes,
    links: state.links,
    
    // Loading state
    isLoading: state.isLoading,
    progress: state.progress,
    error: state.error,
    
    // Stats
    stats: state.stats,
    loadTime: state.loadTime,
    
    // Actions
    loadData: loadDataParallel,
    reloadData,
    getLoadStats
  };
}