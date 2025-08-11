import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { GraphNode } from '../../../api/types';
import { GraphLink } from '../../../types/graph';
import { logger } from '../../../utils/logger';
import { graphClient } from '../../../api/graphClient';

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
  stats?: {
    total_nodes: number;
    total_edges: number;
    density?: number;
    node_types?: Record<string, number>;
  };
}

interface UseGraphDataOptions {
  autoLoad?: boolean;
  cacheKey?: string;
  refreshInterval?: number;
  onError?: (error: Error) => void;
  onSuccess?: (data: GraphData) => void;
}

interface UseGraphDataReturn {
  data: GraphData | null;
  isLoading: boolean;
  error: Error | null;
  refresh: () => Promise<void>;
  updateNode: (nodeId: string, updates: Partial<GraphNode>) => void;
  updateLink: (source: string, target: string, updates: Partial<GraphLink>) => void;
  addNode: (node: GraphNode) => void;
  addLink: (link: GraphLink) => void;
  removeNode: (nodeId: string) => void;
  removeLink: (source: string, target: string) => void;
  clearCache: () => void;
}

// Simple in-memory cache
const dataCache = new Map<string, { data: GraphData; timestamp: number }>();
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

/**
 * useGraphData - Hook for managing graph data fetching and caching
 * 
 * Features:
 * - Automatic data loading
 * - In-memory caching with TTL
 * - Incremental updates
 * - Error handling
 * - Memory leak prevention
 */
export function useGraphData(options: UseGraphDataOptions = {}): UseGraphDataReturn {
  const {
    autoLoad = true,
    cacheKey = 'default',
    refreshInterval,
    onError,
    onSuccess
  } = options;
  
  const [data, setData] = useState<GraphData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  
  // Use refs to prevent memory leaks
  const abortControllerRef = useRef<AbortController | null>(null);
  const refreshIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const isMountedRef = useRef(true);
  
  // Check cache validity
  const getCachedData = useCallback((): GraphData | null => {
    const cached = dataCache.get(cacheKey);
    if (!cached) return null;
    
    const isExpired = Date.now() - cached.timestamp > CACHE_TTL;
    if (isExpired) {
      dataCache.delete(cacheKey);
      return null;
    }
    
    return cached.data;
  }, [cacheKey]);
  
  // Fetch data from API
  const fetchData = useCallback(async (): Promise<GraphData> => {
    // Cancel previous request
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    
    try {
      const response = await graphClient.getGraphData({
        signal: abortControllerRef.current.signal
      });
      
      // Transform response to our format
      const graphData: GraphData = {
        nodes: response.nodes || [],
        links: response.edges?.map((edge: any) => ({
          source: edge.source || edge.from,
          target: edge.target || edge.to,
          from: edge.from || edge.source,
          to: edge.to || edge.target,
          weight: edge.weight || 1,
          edge_type: edge.edge_type || 'RELATED_TO'
        })) || [],
        stats: response.stats
      };
      
      return graphData;
    } catch (err: any) {
      if (err.name === 'AbortError') {
        throw new Error('Request cancelled');
      }
      throw err;
    }
  }, []);
  
  // Main refresh function
  const refresh = useCallback(async () => {
    if (!isMountedRef.current) return;
    
    setIsLoading(true);
    setError(null);
    
    try {
      // Check cache first
      const cached = getCachedData();
      if (cached && !isLoading) {
        setData(cached);
        logger.log('useGraphData: Using cached data');
        onSuccess?.(cached);
        setIsLoading(false);
        return;
      }
      
      // Fetch fresh data
      const freshData = await fetchData();
      
      if (!isMountedRef.current) return;
      
      // Update cache
      dataCache.set(cacheKey, {
        data: freshData,
        timestamp: Date.now()
      });
      
      setData(freshData);
      onSuccess?.(freshData);
      logger.log('useGraphData: Data refreshed', {
        nodes: freshData.nodes.length,
        links: freshData.links.length
      });
    } catch (err) {
      if (!isMountedRef.current) return;
      
      const error = err instanceof Error ? err : new Error('Failed to fetch data');
      setError(error);
      onError?.(error);
      logger.error('useGraphData: Failed to fetch data:', error);
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false);
      }
    }
  }, [cacheKey, getCachedData, fetchData, onSuccess, onError, isLoading]);
  
  // Node update operations
  const updateNode = useCallback((nodeId: string, updates: Partial<GraphNode>) => {
    setData(prev => {
      if (!prev) return null;
      
      const updatedNodes = prev.nodes.map(node =>
        node.id === nodeId ? { ...node, ...updates } : node
      );
      
      const updatedData = { ...prev, nodes: updatedNodes };
      
      // Update cache
      dataCache.set(cacheKey, {
        data: updatedData,
        timestamp: Date.now()
      });
      
      return updatedData;
    });
  }, [cacheKey]);
  
  // Link update operations
  const updateLink = useCallback((source: string, target: string, updates: Partial<GraphLink>) => {
    setData(prev => {
      if (!prev) return null;
      
      const updatedLinks = prev.links.map(link =>
        (link.source === source && link.target === target) ? { ...link, ...updates } : link
      );
      
      const updatedData = { ...prev, links: updatedLinks };
      
      // Update cache
      dataCache.set(cacheKey, {
        data: updatedData,
        timestamp: Date.now()
      });
      
      return updatedData;
    });
  }, [cacheKey]);
  
  // Add node
  const addNode = useCallback((node: GraphNode) => {
    setData(prev => {
      if (!prev) return null;
      
      // Check for duplicates
      if (prev.nodes.some(n => n.id === node.id)) {
        logger.warn('useGraphData: Node already exists:', node.id);
        return prev;
      }
      
      const updatedData = {
        ...prev,
        nodes: [...prev.nodes, node]
      };
      
      // Update cache
      dataCache.set(cacheKey, {
        data: updatedData,
        timestamp: Date.now()
      });
      
      return updatedData;
    });
  }, [cacheKey]);
  
  // Add link
  const addLink = useCallback((link: GraphLink) => {
    setData(prev => {
      if (!prev) return null;
      
      // Check for duplicates
      const exists = prev.links.some(l =>
        l.source === link.source && l.target === link.target
      );
      
      if (exists) {
        logger.warn('useGraphData: Link already exists:', link);
        return prev;
      }
      
      const updatedData = {
        ...prev,
        links: [...prev.links, link]
      };
      
      // Update cache
      dataCache.set(cacheKey, {
        data: updatedData,
        timestamp: Date.now()
      });
      
      return updatedData;
    });
  }, [cacheKey]);
  
  // Remove node
  const removeNode = useCallback((nodeId: string) => {
    setData(prev => {
      if (!prev) return null;
      
      const updatedData = {
        ...prev,
        nodes: prev.nodes.filter(n => n.id !== nodeId),
        // Also remove connected links
        links: prev.links.filter(l => l.source !== nodeId && l.target !== nodeId)
      };
      
      // Update cache
      dataCache.set(cacheKey, {
        data: updatedData,
        timestamp: Date.now()
      });
      
      return updatedData;
    });
  }, [cacheKey]);
  
  // Remove link
  const removeLink = useCallback((source: string, target: string) => {
    setData(prev => {
      if (!prev) return null;
      
      const updatedData = {
        ...prev,
        links: prev.links.filter(l => !(l.source === source && l.target === target))
      };
      
      // Update cache
      dataCache.set(cacheKey, {
        data: updatedData,
        timestamp: Date.now()
      });
      
      return updatedData;
    });
  }, [cacheKey]);
  
  // Clear cache
  const clearCache = useCallback(() => {
    dataCache.delete(cacheKey);
    logger.log('useGraphData: Cache cleared');
  }, [cacheKey]);
  
  // Auto-load on mount
  useEffect(() => {
    if (autoLoad) {
      refresh();
    }
  }, [autoLoad]); // Only run on mount
  
  // Setup refresh interval
  useEffect(() => {
    if (!refreshInterval) return;
    
    refreshIntervalRef.current = setInterval(refresh, refreshInterval);
    
    return () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current);
        refreshIntervalRef.current = null;
      }
    };
  }, [refreshInterval, refresh]);
  
  // Cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true;
    
    return () => {
      isMountedRef.current = false;
      abortControllerRef.current?.abort();
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current);
      }
    };
  }, []);
  
  return useMemo(() => ({
    data,
    isLoading,
    error,
    refresh,
    updateNode,
    updateLink,
    addNode,
    addLink,
    removeNode,
    removeLink,
    clearCache
  }), [
    data,
    isLoading,
    error,
    refresh,
    updateNode,
    updateLink,
    addNode,
    addLink,
    removeNode,
    removeLink,
    clearCache
  ]);
}

export default useGraphData;