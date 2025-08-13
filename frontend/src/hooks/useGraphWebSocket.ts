/**
 * Graph WebSocket Hook
 * Consolidates WebSocket connections for real-time graph updates
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import { useWebSocketContext } from '../contexts/WebSocketProvider';
import { useRustWebSocket } from '../contexts/RustWebSocketProvider';

/**
 * WebSocket event types
 */
export type WebSocketEventType = 
  | 'node_access'
  | 'graph_update'
  | 'delta_update'
  | 'cache_invalidate'
  | 'connection_change'
  | 'error';

/**
 * Delta operation types
 */
export type DeltaOperation = 'add' | 'update' | 'delete';

/**
 * Node access event
 */
export interface NodeAccessEvent {
  type: 'node_access';
  node_ids: string[];
  timestamp: number;
}

/**
 * Graph update event
 */
export interface GraphUpdateEvent {
  type: 'graph_update';
  nodes?: GraphNode[];
  edges?: GraphLink[];
  timestamp: number;
}

/**
 * Delta update event
 */
export interface DeltaUpdateEvent {
  type: 'delta_update';
  operation: DeltaOperation;
  nodes?: GraphNode[];
  edges?: GraphLink[];
  nodeIds?: string[];
  edgeIds?: string[];
  timestamp: number;
  source: 'python' | 'rust';
}

/**
 * Cache invalidate event
 */
export interface CacheInvalidateEvent {
  type: 'cache_invalidate';
  keys?: string[];
  timestamp: number;
}

/**
 * Connection status
 */
export interface ConnectionStatus {
  python: {
    connected: boolean;
    quality: 'excellent' | 'good' | 'poor' | 'disconnected';
    latency: number;
  };
  rust: {
    connected: boolean;
    reconnectCount: number;
  };
  overall: 'connected' | 'partial' | 'disconnected';
}

/**
 * Update statistics
 */
export interface UpdateStatistics {
  totalUpdates: number;
  deltaUpdates: number;
  nodeAccessEvents: number;
  cacheInvalidations: number;
  lastUpdateTime: number | null;
  updateRate: number; // Updates per second
}

/**
 * Hook configuration
 */
export interface UseGraphWebSocketConfig {
  // Enable Python WebSocket
  enablePython?: boolean;
  
  // Enable Rust WebSocket
  enableRust?: boolean;
  
  // Auto-reconnect on disconnect
  autoReconnect?: boolean;
  
  // Reconnect delay in ms
  reconnectDelay?: number;
  
  // Max reconnect attempts
  maxReconnectAttempts?: number;
  
  // Batch update interval in ms
  batchInterval?: number;
  
  // Max batch size
  maxBatchSize?: number;
  
  // Callbacks
  onNodeAccess?: (event: NodeAccessEvent) => void;
  onGraphUpdate?: (event: GraphUpdateEvent) => void;
  onDeltaUpdate?: (event: DeltaUpdateEvent) => void;
  onCacheInvalidate?: (event: CacheInvalidateEvent) => void;
  onConnectionChange?: (status: ConnectionStatus) => void;
  onError?: (error: Error) => void;
  
  // Debug mode
  debug?: boolean;
}

/**
 * Batched update queue
 */
interface UpdateBatch {
  nodes: Map<string, GraphNode>;
  edges: Map<string, GraphLink>;
  deletedNodeIds: Set<string>;
  deletedEdgeIds: Set<string>;
  timestamp: number;
}

/**
 * Graph WebSocket Hook
 */
export function useGraphWebSocket(config: UseGraphWebSocketConfig = {}) {
  const {
    enablePython = true,
    enableRust = true,
    autoReconnect = true,
    reconnectDelay = 1000,
    maxReconnectAttempts = 5,
    batchInterval = 100,
    maxBatchSize = 100,
    onNodeAccess,
    onGraphUpdate,
    onDeltaUpdate,
    onCacheInvalidate,
    onConnectionChange,
    onError,
    debug = false
  } = config;

  // Get WebSocket contexts (may be null if not provided)
  const pythonWs = enablePython ? useWebSocketContext() : null;
  const rustWs = enableRust ? useRustWebSocket() : null;

  // Connection status
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>({
    python: {
      connected: false,
      quality: 'disconnected',
      latency: 0
    },
    rust: {
      connected: false,
      reconnectCount: 0
    },
    overall: 'disconnected'
  });

  // Update statistics
  const [statistics, setStatistics] = useState<UpdateStatistics>({
    totalUpdates: 0,
    deltaUpdates: 0,
    nodeAccessEvents: 0,
    cacheInvalidations: 0,
    lastUpdateTime: null,
    updateRate: 0
  });

  // Recent events cache
  const recentEventsRef = useRef<{
    nodeAccess: NodeAccessEvent[];
    graphUpdate: GraphUpdateEvent[];
    deltaUpdate: DeltaUpdateEvent[];
  }>({
    nodeAccess: [],
    graphUpdate: [],
    deltaUpdate: []
  });

  // Update batch queue
  const updateBatchRef = useRef<UpdateBatch>({
    nodes: new Map(),
    edges: new Map(),
    deletedNodeIds: new Set(),
    deletedEdgeIds: new Set(),
    timestamp: Date.now()
  });

  // Batch processing timer
  const batchTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Update rate calculation
  const updateTimestampsRef = useRef<number[]>([]);

  /**
   * Log debug message
   */
  const log = useCallback((message: string, ...args: any[]) => {
    if (debug) {
      console.debug(`[useGraphWebSocket] ${message}`, ...args);
    }
  }, [debug]);

  /**
   * Calculate update rate
   */
  const calculateUpdateRate = useCallback(() => {
    const now = Date.now();
    const oneSecondAgo = now - 1000;
    
    // Keep only timestamps from last second
    updateTimestampsRef.current = updateTimestampsRef.current.filter(t => t > oneSecondAgo);
    
    return updateTimestampsRef.current.length;
  }, []);

  /**
   * Update statistics
   */
  const updateStats = useCallback((type: 'delta' | 'nodeAccess' | 'cache' | 'update') => {
    const now = Date.now();
    updateTimestampsRef.current.push(now);
    
    setStatistics(prev => ({
      ...prev,
      totalUpdates: prev.totalUpdates + 1,
      deltaUpdates: type === 'delta' ? prev.deltaUpdates + 1 : prev.deltaUpdates,
      nodeAccessEvents: type === 'nodeAccess' ? prev.nodeAccessEvents + 1 : prev.nodeAccessEvents,
      cacheInvalidations: type === 'cache' ? prev.cacheInvalidations + 1 : prev.cacheInvalidations,
      lastUpdateTime: now,
      updateRate: calculateUpdateRate()
    }));
  }, [calculateUpdateRate]);

  /**
   * Process batched updates
   */
  const processBatch = useCallback(() => {
    const batch = updateBatchRef.current;
    
    if (batch.nodes.size === 0 && batch.edges.size === 0 && 
        batch.deletedNodeIds.size === 0 && batch.deletedEdgeIds.size === 0) {
      return;
    }
    
    log(`Processing batch: ${batch.nodes.size} nodes, ${batch.edges.size} edges`);
    
    // Create delta update event
    const event: DeltaUpdateEvent = {
      type: 'delta_update',
      operation: batch.deletedNodeIds.size > 0 || batch.deletedEdgeIds.size > 0 ? 'delete' : 'update',
      nodes: Array.from(batch.nodes.values()),
      edges: Array.from(batch.edges.values()),
      nodeIds: Array.from(batch.deletedNodeIds),
      edgeIds: Array.from(batch.deletedEdgeIds),
      timestamp: batch.timestamp,
      source: 'rust'
    };
    
    // Trigger callback
    if (onDeltaUpdate) {
      onDeltaUpdate(event);
    }
    
    // Clear batch
    updateBatchRef.current = {
      nodes: new Map(),
      edges: new Map(),
      deletedNodeIds: new Set(),
      deletedEdgeIds: new Set(),
      timestamp: Date.now()
    };
    
    updateStats('delta');
  }, [onDeltaUpdate, updateStats, log]);

  /**
   * Add update to batch
   */
  const addToBatch = useCallback((
    operation: DeltaOperation,
    nodes?: GraphNode[],
    edges?: GraphLink[],
    nodeIds?: string[],
    edgeIds?: string[]
  ) => {
    const batch = updateBatchRef.current;
    
    // Handle nodes
    if (nodes) {
      nodes.forEach(node => {
        if (operation === 'delete' || nodeIds?.includes(node.id)) {
          batch.deletedNodeIds.add(node.id);
          batch.nodes.delete(node.id);
        } else {
          batch.nodes.set(node.id, node);
          batch.deletedNodeIds.delete(node.id);
        }
      });
    }
    
    // Handle deleted node IDs
    if (nodeIds && operation === 'delete') {
      nodeIds.forEach(id => batch.deletedNodeIds.add(id));
    }
    
    // Handle edges
    if (edges) {
      edges.forEach(edge => {
        const edgeId = `${edge.source}-${edge.target}`;
        if (operation === 'delete' || edgeIds?.includes(edgeId)) {
          batch.deletedEdgeIds.add(edgeId);
          batch.edges.delete(edgeId);
        } else {
          batch.edges.set(edgeId, edge);
          batch.deletedEdgeIds.delete(edgeId);
        }
      });
    }
    
    // Handle deleted edge IDs
    if (edgeIds && operation === 'delete') {
      edgeIds.forEach(id => batch.deletedEdgeIds.add(id));
    }
    
    // Update timestamp
    batch.timestamp = Date.now();
    
    // Check batch size
    const batchSize = batch.nodes.size + batch.edges.size + 
                     batch.deletedNodeIds.size + batch.deletedEdgeIds.size;
    
    if (batchSize >= maxBatchSize) {
      // Process immediately if batch is full
      if (batchTimerRef.current) {
        clearTimeout(batchTimerRef.current);
        batchTimerRef.current = null;
      }
      processBatch();
    } else {
      // Schedule batch processing
      if (!batchTimerRef.current) {
        batchTimerRef.current = setTimeout(() => {
          processBatch();
          batchTimerRef.current = null;
        }, batchInterval);
      }
    }
  }, [maxBatchSize, batchInterval, processBatch]);

  /**
   * Handle node access event
   */
  const handleNodeAccess = useCallback((nodeIds: string[]) => {
    log(`Node access event: ${nodeIds.length} nodes`);
    
    const event: NodeAccessEvent = {
      type: 'node_access',
      node_ids: nodeIds,
      timestamp: Date.now()
    };
    
    // Add to recent events
    recentEventsRef.current.nodeAccess.unshift(event);
    recentEventsRef.current.nodeAccess = recentEventsRef.current.nodeAccess.slice(0, 10);
    
    // Trigger callback
    if (onNodeAccess) {
      onNodeAccess(event);
    }
    
    updateStats('nodeAccess');
  }, [onNodeAccess, updateStats, log]);

  /**
   * Handle graph update event
   */
  const handleGraphUpdate = useCallback((nodes?: GraphNode[], edges?: GraphLink[]) => {
    log(`Graph update event: ${nodes?.length || 0} nodes, ${edges?.length || 0} edges`);
    
    const event: GraphUpdateEvent = {
      type: 'graph_update',
      nodes,
      edges,
      timestamp: Date.now()
    };
    
    // Add to recent events
    recentEventsRef.current.graphUpdate.unshift(event);
    recentEventsRef.current.graphUpdate = recentEventsRef.current.graphUpdate.slice(0, 10);
    
    // Trigger callback
    if (onGraphUpdate) {
      onGraphUpdate(event);
    }
    
    updateStats('update');
  }, [onGraphUpdate, updateStats, log]);

  /**
   * Handle cache invalidate event
   */
  const handleCacheInvalidate = useCallback((keys?: string[]) => {
    log(`Cache invalidate event: ${keys?.length || 'all'} keys`);
    
    const event: CacheInvalidateEvent = {
      type: 'cache_invalidate',
      keys,
      timestamp: Date.now()
    };
    
    // Trigger callback
    if (onCacheInvalidate) {
      onCacheInvalidate(event);
    }
    
    updateStats('cache');
  }, [onCacheInvalidate, updateStats, log]);

  /**
   * Force flush batched updates
   */
  const flushBatch = useCallback(() => {
    if (batchTimerRef.current) {
      clearTimeout(batchTimerRef.current);
      batchTimerRef.current = null;
    }
    processBatch();
  }, [processBatch]);

  /**
   * Get recent events
   */
  const getRecentEvents = useCallback((type?: 'nodeAccess' | 'graphUpdate' | 'deltaUpdate', limit: number = 10) => {
    const events = recentEventsRef.current;
    
    if (type) {
      return events[type].slice(0, limit);
    }
    
    // Return all types merged and sorted by timestamp
    const allEvents = [
      ...events.nodeAccess,
      ...events.graphUpdate,
      ...events.deltaUpdate
    ].sort((a, b) => b.timestamp - a.timestamp);
    
    return allEvents.slice(0, limit);
  }, []);

  /**
   * Clear statistics
   */
  const clearStatistics = useCallback(() => {
    setStatistics({
      totalUpdates: 0,
      deltaUpdates: 0,
      nodeAccessEvents: 0,
      cacheInvalidations: 0,
      lastUpdateTime: null,
      updateRate: 0
    });
    updateTimestampsRef.current = [];
  }, []);

  // Subscribe to Python WebSocket events
  useEffect(() => {
    if (!pythonWs || !enablePython) return;
    
    log('Setting up Python WebSocket subscriptions');
    
    // Subscribe to node access events
    const unsubNodeAccess = pythonWs.subscribeToNodeAccess((event) => {
      handleNodeAccess(event.node_ids);
    });
    
    // Subscribe to graph updates
    const unsubGraphUpdate = pythonWs.subscribeToGraphUpdate((event) => {
      handleGraphUpdate(event.nodes, event.edges);
    });
    
    // Subscribe to delta updates
    const unsubDeltaUpdate = pythonWs.subscribeToDeltaUpdate((event) => {
      const deltaEvent: DeltaUpdateEvent = {
        type: 'delta_update',
        operation: event.operation,
        nodes: event.nodes,
        edges: event.edges,
        nodeIds: event.nodeIds,
        edgeIds: event.edgeIds,
        timestamp: event.timestamp || Date.now(),
        source: 'python'
      };
      
      if (batchInterval > 0) {
        addToBatch(event.operation, event.nodes, event.edges, event.nodeIds, event.edgeIds);
      } else if (onDeltaUpdate) {
        onDeltaUpdate(deltaEvent);
        updateStats('delta');
      }
    });
    
    // Subscribe to cache invalidation
    const unsubCacheInvalidate = pythonWs.subscribeToCacheInvalidate((event) => {
      handleCacheInvalidate(event.keys);
    });
    
    // Update connection status
    setConnectionStatus(prev => ({
      ...prev,
      python: {
        connected: pythonWs.isConnected,
        quality: pythonWs.connectionQuality,
        latency: pythonWs.latency
      }
    }));
    
    return () => {
      log('Cleaning up Python WebSocket subscriptions');
      unsubNodeAccess();
      unsubGraphUpdate();
      unsubDeltaUpdate();
      unsubCacheInvalidate();
    };
  }, [pythonWs, enablePython, handleNodeAccess, handleGraphUpdate, handleCacheInvalidate, 
      addToBatch, onDeltaUpdate, updateStats, batchInterval, log]);

  // Subscribe to Rust WebSocket events
  useEffect(() => {
    if (!rustWs || !enableRust) return;
    
    log('Setting up Rust WebSocket subscription');
    
    const unsubscribe = rustWs.subscribe((update) => {
      log('Received update from Rust:', update);
      
      if (update.type === 'graph:delta' || update.type === 'graph:update') {
        const { operation, nodes, edges } = update.data;
        
        if (batchInterval > 0) {
          addToBatch(operation, nodes, edges);
        } else {
          const event: DeltaUpdateEvent = {
            type: 'delta_update',
            operation,
            nodes,
            edges,
            timestamp: update.data.timestamp || Date.now(),
            source: 'rust'
          };
          
          if (onDeltaUpdate) {
            onDeltaUpdate(event);
          }
          updateStats('delta');
        }
      }
    });
    
    // Update connection status
    setConnectionStatus(prev => ({
      ...prev,
      rust: {
        connected: rustWs.isConnected,
        reconnectCount: 0
      }
    }));
    
    return () => {
      log('Cleaning up Rust WebSocket subscription');
      unsubscribe();
    };
  }, [rustWs, enableRust, addToBatch, onDeltaUpdate, updateStats, batchInterval, log]);

  // Update overall connection status
  useEffect(() => {
    const pythonConnected = connectionStatus.python.connected;
    const rustConnected = connectionStatus.rust.connected;
    
    let overall: ConnectionStatus['overall'];
    if (pythonConnected && rustConnected) {
      overall = 'connected';
    } else if (pythonConnected || rustConnected) {
      overall = 'partial';
    } else {
      overall = 'disconnected';
    }
    
    setConnectionStatus(prev => {
      const newStatus = { ...prev, overall };
      
      if (prev.overall !== overall && onConnectionChange) {
        onConnectionChange(newStatus);
      }
      
      return newStatus;
    });
  }, [connectionStatus.python.connected, connectionStatus.rust.connected, onConnectionChange]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (batchTimerRef.current) {
        clearTimeout(batchTimerRef.current);
        processBatch(); // Process any remaining updates
      }
    };
  }, [processBatch]);

  return {
    // Connection status
    connectionStatus,
    isConnected: connectionStatus.overall !== 'disconnected',
    
    // Statistics
    statistics,
    clearStatistics,
    
    // Recent events
    getRecentEvents,
    
    // Manual event triggers (for testing or manual updates)
    triggerNodeAccess: handleNodeAccess,
    triggerGraphUpdate: handleGraphUpdate,
    triggerCacheInvalidate: handleCacheInvalidate,
    
    // Batch control
    flushBatch,
    
    // Raw WebSocket contexts (if needed for advanced use)
    pythonWebSocket: pythonWs,
    rustWebSocket: rustWs
  };
}

/**
 * Simple WebSocket hook for basic real-time updates
 */
export function useSimpleGraphUpdates(
  onUpdate: (nodes: GraphNode[], edges: GraphLink[]) => void
) {
  const { statistics } = useGraphWebSocket({
    onDeltaUpdate: (event) => {
      if (event.nodes || event.edges) {
        onUpdate(event.nodes || [], event.edges || []);
      }
    },
    onGraphUpdate: (event) => {
      if (event.nodes || event.edges) {
        onUpdate(event.nodes || [], event.edges || []);
      }
    },
    batchInterval: 100
  });
  
  return {
    updateCount: statistics.totalUpdates,
    updateRate: statistics.updateRate
  };
}