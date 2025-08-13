/**
 * Graph Data Management Hook
 * Handles data fetching, caching, updates, and state management
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import { 
  mergeNodeArrays, 
  removeNodesFromArray, 
  updateNodesInArray,
  filterValidNodes 
} from '../utils/graphNodeOperations';
import { 
  mergeLinkArrays, 
  removeLinksFromArray, 
  updateLinksInArray,
  filterValidLinks,
  removeLinksByNodeIds
} from '../utils/graphLinkOperations';

/**
 * Data source configuration
 */
export interface DataSourceConfig {
  // API endpoint or data source URL
  endpoint?: string;
  
  // Polling interval in milliseconds (0 = disabled)
  pollingInterval?: number;
  
  // Enable caching
  enableCache?: boolean;
  
  // Cache duration in milliseconds
  cacheDuration?: number;
  
  // Maximum cache size (number of entries)
  maxCacheSize?: number;
}

/**
 * Data update event
 */
export interface DataUpdateEvent {
  type: 'add' | 'update' | 'remove' | 'reset';
  nodes?: GraphNode[];
  links?: GraphLink[];
  timestamp: number;
  source: 'api' | 'websocket' | 'manual' | 'cache';
}

/**
 * Data state
 */
export interface GraphDataState {
  nodes: GraphNode[];
  links: GraphLink[];
  loading: boolean;
  error: Error | null;
  lastUpdate: number;
  updateCount: number;
}

/**
 * Hook configuration
 */
export interface UseGraphDataManagementConfig {
  // Initial data
  initialNodes?: GraphNode[];
  initialLinks?: GraphLink[];
  
  // Data source configuration
  dataSource?: DataSourceConfig;
  
  // Enable optimistic updates
  optimisticUpdates?: boolean;
  
  // Enable automatic deduplication
  autoDedup?: boolean;
  
  // Callback for data updates
  onDataUpdate?: (event: DataUpdateEvent) => void;
  
  // Callback for errors
  onError?: (error: Error) => void;
  
  // Enable debug logging
  debug?: boolean;
}

/**
 * Cache entry
 */
interface CacheEntry {
  nodes: GraphNode[];
  links: GraphLink[];
  timestamp: number;
  key: string;
}

/**
 * Graph Data Management Hook
 */
export function useGraphDataManagement(config: UseGraphDataManagementConfig = {}) {
  const {
    initialNodes = [],
    initialLinks = [],
    dataSource,
    optimisticUpdates = true,
    autoDedup = true,
    onDataUpdate,
    onError,
    debug = false
  } = config;

  // Core data state
  const [dataState, setDataState] = useState<GraphDataState>({
    nodes: initialNodes,
    links: initialLinks,
    loading: false,
    error: null,
    lastUpdate: Date.now(),
    updateCount: 0
  });
  
  // Log initial state
  if (debug) {
    console.log('[useGraphDataManagement] Initial state:', {
      nodeCount: initialNodes.length,
      linkCount: initialLinks.length
    });
  }

  // Cache management
  const cacheRef = useRef<Map<string, CacheEntry>>(new Map());
  const cacheSizeRef = useRef(0);
  
  // Polling interval reference
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  
  // Pending operations queue for optimistic updates
  const pendingOpsRef = useRef<DataUpdateEvent[]>([]);

  /**
   * Log debug message
   */
  const log = useCallback((message: string, ...args: any[]) => {
    if (debug) {
      console.debug(`[useGraphDataManagement] ${message}`, ...args);
    }
  }, [debug]);

  /**
   * Cache management functions
   */
  const cacheOperations = useMemo(() => ({
    get: (key: string): CacheEntry | null => {
      const entry = cacheRef.current.get(key);
      if (!entry) return null;
      
      const age = Date.now() - entry.timestamp;
      const maxAge = dataSource?.cacheDuration || 5 * 60 * 1000; // 5 minutes default
      
      if (age > maxAge) {
        cacheRef.current.delete(key);
        return null;
      }
      
      return entry;
    },
    
    set: (key: string, nodes: GraphNode[], links: GraphLink[]) => {
      if (!dataSource?.enableCache) return;
      
      const maxSize = dataSource?.maxCacheSize || 100;
      
      // Evict oldest entries if cache is full
      if (cacheRef.current.size >= maxSize) {
        const oldestKey = Array.from(cacheRef.current.entries())
          .sort((a, b) => a[1].timestamp - b[1].timestamp)[0][0];
        cacheRef.current.delete(oldestKey);
      }
      
      cacheRef.current.set(key, {
        nodes,
        links,
        timestamp: Date.now(),
        key
      });
      
      cacheSizeRef.current = cacheRef.current.size;
    },
    
    clear: () => {
      cacheRef.current.clear();
      cacheSizeRef.current = 0;
    }
  }), [dataSource, log]);

  /**
   * Add nodes to the graph
   */
  const addNodes = useCallback((newNodes: GraphNode[], source: DataUpdateEvent['source'] = 'manual') => {
    log(`Adding ${newNodes.length} nodes from ${source}`);
    
    setDataState(prev => {
      const validNodes = filterValidNodes(newNodes);
      const merged = autoDedup 
        ? mergeNodeArrays(prev.nodes, validNodes)
        : [...prev.nodes, ...validNodes];
      
      const event: DataUpdateEvent = {
        type: 'add',
        nodes: validNodes,
        timestamp: Date.now(),
        source
      };
      
      if (optimisticUpdates) {
        pendingOpsRef.current.push(event);
      }
      
      if (onDataUpdate) {
        onDataUpdate(event);
      }
      
      return {
        ...prev,
        nodes: merged,
        lastUpdate: Date.now(),
        updateCount: prev.updateCount + 1
      };
    });
  }, [autoDedup, optimisticUpdates, onDataUpdate, log]);

  /**
   * Add links to the graph
   */
  const addLinks = useCallback((newLinks: GraphLink[], source: DataUpdateEvent['source'] = 'manual') => {
    log(`Adding ${newLinks.length} links from ${source}`);
    
    setDataState(prev => {
      const nodeIds = new Set(prev.nodes.map(n => n.id));
      const validLinks = filterValidLinks(newLinks, nodeIds);
      const merged = autoDedup
        ? mergeLinkArrays(prev.links, validLinks)
        : [...prev.links, ...validLinks];
      
      const event: DataUpdateEvent = {
        type: 'add',
        links: validLinks,
        timestamp: Date.now(),
        source
      };
      
      if (optimisticUpdates) {
        pendingOpsRef.current.push(event);
      }
      
      if (onDataUpdate) {
        onDataUpdate(event);
      }
      
      return {
        ...prev,
        links: merged,
        lastUpdate: Date.now(),
        updateCount: prev.updateCount + 1
      };
    });
  }, [autoDedup, optimisticUpdates, onDataUpdate, log]);

  /**
   * Update existing nodes
   */
  const updateNodes = useCallback((updatedNodes: GraphNode[], source: DataUpdateEvent['source'] = 'manual') => {
    log(`Updating ${updatedNodes.length} nodes from ${source}`);
    
    setDataState(prev => {
      const updated = updateNodesInArray(prev.nodes, updatedNodes);
      
      const event: DataUpdateEvent = {
        type: 'update',
        nodes: updatedNodes,
        timestamp: Date.now(),
        source
      };
      
      if (optimisticUpdates) {
        pendingOpsRef.current.push(event);
      }
      
      if (onDataUpdate) {
        onDataUpdate(event);
      }
      
      return {
        ...prev,
        nodes: updated,
        lastUpdate: Date.now(),
        updateCount: prev.updateCount + 1
      };
    });
  }, [optimisticUpdates, onDataUpdate, log]);

  /**
   * Update existing links
   */
  const updateLinks = useCallback((updatedLinks: GraphLink[], source: DataUpdateEvent['source'] = 'manual') => {
    log(`Updating ${updatedLinks.length} links from ${source}`);
    
    setDataState(prev => {
      const updated = updateLinksInArray(prev.links, updatedLinks);
      
      const event: DataUpdateEvent = {
        type: 'update',
        links: updatedLinks,
        timestamp: Date.now(),
        source
      };
      
      if (optimisticUpdates) {
        pendingOpsRef.current.push(event);
      }
      
      if (onDataUpdate) {
        onDataUpdate(event);
      }
      
      return {
        ...prev,
        links: updated,
        lastUpdate: Date.now(),
        updateCount: prev.updateCount + 1
      };
    });
  }, [optimisticUpdates, onDataUpdate, log]);

  /**
   * Remove nodes from the graph
   */
  const removeNodes = useCallback((nodeIds: string[], source: DataUpdateEvent['source'] = 'manual') => {
    log(`Removing ${nodeIds.length} nodes from ${source}`);
    
    setDataState(prev => {
      const filteredNodes = removeNodesFromArray(prev.nodes, nodeIds);
      const filteredLinks = removeLinksByNodeIds(prev.links, nodeIds);
      
      const event: DataUpdateEvent = {
        type: 'remove',
        nodes: prev.nodes.filter(n => nodeIds.includes(n.id)),
        timestamp: Date.now(),
        source
      };
      
      if (optimisticUpdates) {
        pendingOpsRef.current.push(event);
      }
      
      if (onDataUpdate) {
        onDataUpdate(event);
      }
      
      return {
        ...prev,
        nodes: filteredNodes,
        links: filteredLinks,
        lastUpdate: Date.now(),
        updateCount: prev.updateCount + 1
      };
    });
  }, [optimisticUpdates, onDataUpdate, log]);

  /**
   * Remove links from the graph
   */
  const removeLinks = useCallback((linksToRemove: GraphLink[], source: DataUpdateEvent['source'] = 'manual') => {
    log(`Removing ${linksToRemove.length} links from ${source}`);
    
    setDataState(prev => {
      const filtered = removeLinksFromArray(prev.links, linksToRemove);
      
      const event: DataUpdateEvent = {
        type: 'remove',
        links: linksToRemove,
        timestamp: Date.now(),
        source
      };
      
      if (optimisticUpdates) {
        pendingOpsRef.current.push(event);
      }
      
      if (onDataUpdate) {
        onDataUpdate(event);
      }
      
      return {
        ...prev,
        links: filtered,
        lastUpdate: Date.now(),
        updateCount: prev.updateCount + 1
      };
    });
  }, [optimisticUpdates, onDataUpdate, log]);

  /**
   * Reset graph data
   */
  const resetData = useCallback((nodes: GraphNode[], links: GraphLink[], source: DataUpdateEvent['source'] = 'manual') => {
    console.log(`[useGraphDataManagement] resetData called with ${nodes.length} nodes and ${links.length} links from ${source}`);
    log(`Resetting data with ${nodes.length} nodes and ${links.length} links from ${source}`);
    
    setDataState(prev => {
      const validNodes = filterValidNodes(nodes);
      const nodeIds = new Set(validNodes.map(n => n.id));
      const validLinks = filterValidLinks(links, nodeIds);
      
      const event: DataUpdateEvent = {
        type: 'reset',
        nodes: validNodes,
        links: validLinks,
        timestamp: Date.now(),
        source
      };
      
      // Clear pending operations on reset
      pendingOpsRef.current = [];
      
      if (onDataUpdate) {
        onDataUpdate(event);
      }
      
      const newState = {
        ...prev,
        nodes: validNodes,
        links: validLinks,
        lastUpdate: Date.now(),
        updateCount: prev.updateCount + 1,
        error: null
      };
      
      console.log('[useGraphDataManagement] New state after reset:', {
        nodeCount: newState.nodes.length,
        linkCount: newState.links.length
      });
      
      return newState;
    });
  }, [onDataUpdate, log]);

  /**
   * Clear all data
   */
  const clearData = useCallback(() => {
    resetData([], [], 'manual');
    cacheOperations.clear();
  }, [resetData, cacheOperations]);

  /**
   * Fetch data from API
   */
  const fetchData = useCallback(async (force: boolean = false) => {
    if (!dataSource?.endpoint) return;
    
    const cacheKey = dataSource.endpoint;
    
    // Check cache first
    if (!force && dataSource.enableCache) {
      const cached = cacheOperations.get(cacheKey);
      if (cached) {
        log('Using cached data');
        resetData(cached.nodes, cached.links, 'cache');
        return;
      }
    }
    
    log('Fetching data from API');
    setDataState(prev => ({ ...prev, loading: true, error: null }));
    
    try {
      const response = await fetch(dataSource.endpoint);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      const { nodes = [], links = [] } = data;
      
      // Cache the data
      cacheOperations.set(cacheKey, nodes, links);
      
      // Update state
      resetData(nodes, links, 'api');
      
    } catch (error) {
      const err = error as Error;
      log('Fetch error:', err);
      
      setDataState(prev => ({
        ...prev,
        loading: false,
        error: err
      }));
      
      if (onError) {
        onError(err);
      }
    } finally {
      setDataState(prev => ({ ...prev, loading: false }));
    }
  }, [dataSource, cacheOperations, resetData, onError, log]);

  /**
   * Refresh data (force fetch)
   */
  const refresh = useCallback(() => {
    return fetchData(true);
  }, [fetchData]);

  /**
   * Rollback optimistic updates
   */
  const rollbackOptimisticUpdates = useCallback((count: number = 1) => {
    if (!optimisticUpdates || pendingOpsRef.current.length === 0) return;
    
    log(`Rolling back ${count} optimistic updates`);
    
    // Remove the specified number of operations from the queue
    const removed = pendingOpsRef.current.splice(-count, count);
    
    // TODO: Implement actual rollback logic based on operation types
    // This would require maintaining a history of previous states
    log('Rollback operations:', removed);
  }, [optimisticUpdates, log]);

  /**
   * Get data statistics
   */
  const getDataStats = useCallback(() => ({
    nodeCount: dataState.nodes.length,
    linkCount: dataState.links.length,
    cacheSize: cacheSizeRef.current,
    pendingOps: pendingOpsRef.current.length,
    lastUpdate: dataState.lastUpdate,
    updateCount: dataState.updateCount
  }), [dataState]);

  /**
   * Batch update operations
   */
  const batchUpdate = useCallback((operations: Array<{
    type: 'add' | 'update' | 'remove';
    target: 'nodes' | 'links';
    data: any[];
  }>) => {
    log(`Executing ${operations.length} batch operations`);
    
    setDataState(prev => {
      let nodes = [...prev.nodes];
      let links = [...prev.links];
      
      operations.forEach(op => {
        if (op.target === 'nodes') {
          switch (op.type) {
            case 'add':
              nodes = autoDedup ? mergeNodeArrays(nodes, op.data) : [...nodes, ...op.data];
              break;
            case 'update':
              nodes = updateNodesInArray(nodes, op.data);
              break;
            case 'remove':
              nodes = removeNodesFromArray(nodes, op.data.map(n => n.id || n));
              links = removeLinksByNodeIds(links, op.data.map(n => n.id || n));
              break;
          }
        } else {
          switch (op.type) {
            case 'add':
              const nodeIds = new Set(nodes.map(n => n.id));
              const validLinks = filterValidLinks(op.data, nodeIds);
              links = autoDedup ? mergeLinkArrays(links, validLinks) : [...links, ...validLinks];
              break;
            case 'update':
              links = updateLinksInArray(links, op.data);
              break;
            case 'remove':
              links = removeLinksFromArray(links, op.data);
              break;
          }
        }
      });
      
      return {
        ...prev,
        nodes,
        links,
        lastUpdate: Date.now(),
        updateCount: prev.updateCount + 1
      };
    });
  }, [autoDedup, log]);

  // Set up polling if configured
  useEffect(() => {
    if (!dataSource?.endpoint || !dataSource?.pollingInterval) return;
    
    log(`Setting up polling with interval ${dataSource.pollingInterval}ms`);
    
    pollingIntervalRef.current = setInterval(() => {
      fetchData(false);
    }, dataSource.pollingInterval);
    
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    };
  }, [dataSource, fetchData, log]);

  // Initial fetch if endpoint is configured
  useEffect(() => {
    if (dataSource?.endpoint) {
      // Only fetch on first mount, not on every re-render
      const timeoutId = setTimeout(() => {
        fetchData(false);
      }, 0);
      return () => clearTimeout(timeoutId);
    }
  }, [dataSource?.endpoint]); // Include minimal stable dependency

  return {
    // Data state
    nodes: dataState.nodes,
    links: dataState.links,
    loading: dataState.loading,
    error: dataState.error,
    
    // Data operations
    addNodes,
    addLinks,
    updateNodes,
    updateLinks,
    removeNodes,
    removeLinks,
    resetData,
    clearData,
    batchUpdate,
    
    // Fetch operations
    fetchData,
    refresh,
    
    // Optimistic updates
    rollbackOptimisticUpdates,
    
    // Statistics
    getDataStats,
    
    // Cache operations
    cacheOperations,
    
    // Metadata
    lastUpdate: dataState.lastUpdate,
    updateCount: dataState.updateCount
  };
}

/**
 * Simple data management hook for basic use cases
 */
export function useSimpleGraphData(
  initialNodes: GraphNode[] = [],
  initialLinks: GraphLink[] = []
) {
  const [nodes, setNodes] = useState(initialNodes);
  const [links, setLinks] = useState(initialLinks);
  
  const updateData = useCallback((newNodes: GraphNode[], newLinks: GraphLink[]) => {
    setNodes(newNodes);
    setLinks(newLinks);
  }, []);
  
  return {
    nodes,
    links,
    updateData
  };
}