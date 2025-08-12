import { useEffect, useRef, useCallback, useState } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import { logger } from '../utils/logger';

interface GraphNotification {
  type: 'graph:notification';
  operation: 'insert' | 'update' | 'delete' | 'bulk_insert' | 'bulk_update' | 'bulk_delete';
  entity_type: 'node' | 'edge' | 'episode';
  entity_ids: string[];
  sequence: number;
  timestamp: string;
  metadata?: Record<string, any>;
}

interface GraphDelta {
  operation: 'initial' | 'update' | 'refresh';
  nodes_added: GraphNode[];
  nodes_updated: GraphNode[];
  nodes_removed: string[];
  edges_added: GraphLink[];
  edges_updated: GraphLink[];
  edges_removed: [string, string][];
  timestamp: number;
  sequence: number;
}

interface UseWebSocketDeltasOptions {
  enabled?: boolean;
  onDelta?: (delta: GraphDelta) => void;
  onNotification?: (notification: GraphNotification) => void;
  onConnected?: () => void;
  onDisconnected?: () => void;
  apiBaseUrl?: string; // Base URL for fetching incremental updates
}

export function useWebSocketDeltas({
  enabled = true,
  onDelta,
  onNotification,
  onConnected,
  onDisconnected,
  apiBaseUrl = 'http://localhost:3000',
}: UseWebSocketDeltasOptions = {}) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastDelta, setLastDelta] = useState<GraphDelta | null>(null);
  const [lastNotification, setLastNotification] = useState<GraphNotification | null>(null);
  const [sequence, setSequence] = useState<number>(0);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  
  // Function to fetch incremental data when notification is received
  const fetchIncrementalData = useCallback(async (notification: GraphNotification) => {
    try {
      if (notification.entity_type === 'node') {
        // Fetch specific nodes
        const response = await fetch(
          `${apiBaseUrl}/api/graph/nodes?ids=${notification.entity_ids.join(',')}`
        );
        
        if (response.ok) {
          const nodes = await response.json();
          logger.log('Fetched incremental nodes:', nodes.length);
          
          // Convert to delta format for compatibility
          const delta: GraphDelta = {
            operation: notification.operation === 'insert' ? 'update' : 'update',
            nodes_added: notification.operation === 'insert' ? nodes : [],
            nodes_updated: notification.operation === 'update' ? nodes : [],
            nodes_removed: notification.operation === 'delete' ? notification.entity_ids : [],
            edges_added: [],
            edges_updated: [],
            edges_removed: [],
            timestamp: Date.now(),
            sequence: notification.sequence,
          };
          
          setLastDelta(delta);
          onDelta?.(delta);
        }
      } else if (notification.entity_type === 'edge') {
        // Fetch specific edges
        const response = await fetch(
          `${apiBaseUrl}/api/graph/edges?ids=${notification.entity_ids.join(',')}`
        );
        
        if (response.ok) {
          const edges = await response.json();
          logger.log('Fetched incremental edges:', edges.length);
          
          // Convert to delta format for compatibility
          const delta: GraphDelta = {
            operation: notification.operation === 'insert' ? 'update' : 'update',
            nodes_added: [],
            nodes_updated: [],
            nodes_removed: [],
            edges_added: notification.operation === 'insert' ? edges : [],
            edges_updated: notification.operation === 'update' ? edges : [],
            edges_removed: notification.operation === 'delete' ? 
              notification.entity_ids.map(id => {
                const [source, target] = id.split('-');
                return [source, target] as [string, string];
              }) : [],
            timestamp: Date.now(),
            sequence: notification.sequence,
          };
          
          setLastDelta(delta);
          onDelta?.(delta);
        }
      }
    } catch (error) {
      logger.error('Failed to fetch incremental data:', error);
    }
  }, [apiBaseUrl, onDelta]);
  
  const connect = useCallback(() => {
    if (!enabled || wsRef.current?.readyState === WebSocket.OPEN) return;
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.hostname}:3000/ws`;
    
    logger.log('Connecting to WebSocket:', wsUrl);
    
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    
    ws.onopen = () => {
      logger.log('WebSocket connected');
      setIsConnected(true);
      reconnectAttemptsRef.current = 0;
      
      // Subscribe to delta updates
      ws.send(JSON.stringify({ type: 'subscribe:deltas' }));
      
      // Start ping interval to keep connection alive
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        } else {
          clearInterval(pingInterval);
        }
      }, 30000); // Ping every 30 seconds
      
      onConnected?.();
    };
    
    ws.onmessage = async (event) => {
      try {
        const message = JSON.parse(event.data);
        
        switch (message.type) {
          case 'connected':
            logger.log('WebSocket features:', message.features);
            break;
            
          case 'subscribed:deltas':
            logger.log('Successfully subscribed to delta updates');
            break;
            
          case 'graph:notification':
            // Handle notification-only message
            const notification = message as GraphNotification;
            logger.log('Received graph notification:', {
              operation: notification.operation,
              entityType: notification.entity_type,
              entityCount: notification.entity_ids.length,
              sequence: notification.sequence,
            });
            
            setLastNotification(notification);
            setSequence(notification.sequence);
            onNotification?.(notification);
            
            // Fetch actual data based on notification
            if (notification.entity_ids.length > 0) {
              await fetchIncrementalData(notification);
            }
            break;
            
          case 'node_access':
            // Handle node access notifications
            logger.log('Node access notification:', {
              nodeCount: message.node_ids?.length || 0,
              accessType: message.access_type,
              sequence: message.sequence,
            });
            setSequence(message.sequence || sequence);
            break;
            
          case 'graph:delta':
            // Legacy delta message (for backward compatibility)
            const delta = message.data as GraphDelta;
            logger.log('Received delta update (legacy):', {
              sequence: delta.sequence,
              nodesAdded: delta.nodes_added.length,
              nodesUpdated: delta.nodes_updated.length,
              nodesRemoved: delta.nodes_removed.length,
              edgesAdded: delta.edges_added.length,
              edgesUpdated: delta.edges_updated.length,
              edgesRemoved: delta.edges_removed.length,
            });
            
            setLastDelta(delta);
            setSequence(delta.sequence);
            onDelta?.(delta);
            break;
            
          case 'pong':
            // Heartbeat response, connection is alive
            break;
            
          default:
            logger.log('Unknown WebSocket message type:', message.type);
        }
      } catch (error) {
        logger.error('Failed to parse WebSocket message:', error);
      }
    };
    
    ws.onerror = (error) => {
      logger.error('WebSocket error:', error);
    };
    
    ws.onclose = () => {
      logger.log('WebSocket disconnected');
      setIsConnected(false);
      onDisconnected?.();
      
      // Attempt to reconnect with exponential backoff
      if (enabled && reconnectAttemptsRef.current < 10) {
        const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000);
        reconnectAttemptsRef.current++;
        
        logger.log(`Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current})`);
        
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      }
    };
  }, [enabled, onDelta, onNotification, onConnected, onDisconnected, fetchIncrementalData]);
  
  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    
    setIsConnected(false);
  }, []);
  
  const sendMessage = useCallback((message: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
      return true;
    }
    return false;
  }, []);
  
  // Connect on mount if enabled
  useEffect(() => {
    if (enabled) {
      connect();
    }
    
    return () => {
      disconnect();
    };
  }, [enabled, connect, disconnect]);
  
  return {
    isConnected,
    lastDelta,
    lastNotification,
    sequence,
    connect,
    disconnect,
    sendMessage,
  };
}

// Helper function to apply delta to existing data
export function applyDelta(
  currentNodes: GraphNode[],
  currentEdges: GraphLink[],
  delta: GraphDelta
): { nodes: GraphNode[], edges: GraphLink[] } {
  // Create maps for efficient lookups
  const nodeMap = new Map(currentNodes.map(n => [n.id, n]));
  const edgeMap = new Map(currentEdges.map(e => [`${e.source}-${e.target}`, e]));
  
  // Apply node removals
  delta.nodes_removed.forEach(id => nodeMap.delete(id));
  
  // Apply node additions
  delta.nodes_added.forEach(node => nodeMap.set(node.id, node));
  
  // Apply node updates
  delta.nodes_updated.forEach(node => {
    const existing = nodeMap.get(node.id);
    if (existing) {
      nodeMap.set(node.id, { ...existing, ...node });
    }
  });
  
  // Apply edge removals
  delta.edges_removed.forEach(([source, target]) => {
    edgeMap.delete(`${source}-${target}`);
  });
  
  // Apply edge additions
  delta.edges_added.forEach(edge => {
    edgeMap.set(`${edge.source}-${edge.target}`, edge);
  });
  
  // Apply edge updates
  delta.edges_updated.forEach(edge => {
    const key = `${edge.source}-${edge.target}`;
    const existing = edgeMap.get(key);
    if (existing) {
      edgeMap.set(key, { ...existing, ...edge });
    }
  });
  
  return {
    nodes: Array.from(nodeMap.values()),
    edges: Array.from(edgeMap.values()),
  };
}