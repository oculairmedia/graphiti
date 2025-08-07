import { useEffect, useRef, useCallback, useState } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import { logger } from '../utils/logger';

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
  onConnected?: () => void;
  onDisconnected?: () => void;
}

export function useWebSocketDeltas({
  enabled = true,
  onDelta,
  onConnected,
  onDisconnected,
}: UseWebSocketDeltasOptions = {}) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastDelta, setLastDelta] = useState<GraphDelta | null>(null);
  const [sequence, setSequence] = useState<number>(0);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  
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
    
    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        
        switch (message.type) {
          case 'connected':
            logger.log('WebSocket features:', message.features);
            break;
            
          case 'subscribed:deltas':
            logger.log('Successfully subscribed to delta updates');
            break;
            
          case 'graph:delta':
            const delta = message.data as GraphDelta;
            logger.log('Received delta update:', {
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
  }, [enabled, onDelta, onConnected, onDisconnected]);
  
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