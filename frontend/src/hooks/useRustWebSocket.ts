import { useEffect, useRef, useCallback } from 'react';
import type { GraphNode, GraphEdge } from '../types/graph';

// Production-safe logging
const isDev = import.meta.env.DEV;
const log = isDev ? console.log.bind(console) : () => {};
const logWarn = isDev ? console.warn.bind(console) : () => {};
const logError = console.error.bind(console);

interface DeltaUpdate {
  type: 'graph:delta';
  data: {
    operation: 'add' | 'update' | 'delete';
    nodes?: GraphNode[];
    edges?: GraphEdge[];
    timestamp: number;
  };
}

interface RustWebSocketOptions {
  onDeltaUpdate?: (update: DeltaUpdate) => void;
  reconnectAttempts?: number;
  reconnectDelay?: number;
}

export function useRustWebSocket(options: RustWebSocketOptions = {}) {
  const {
    onDeltaUpdate,
    reconnectAttempts = 5,
    reconnectDelay = 1000,
  } = options;

  const DELTA_BATCH_INTERVAL_MS = 500;

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | undefined>(undefined);
  const isConnectingRef = useRef(false);
  const deltaBatchRef = useRef<{ nodes: GraphNode[]; edges: GraphEdge[] }>({ nodes: [], edges: [] });
  const batchTimerRef = useRef<NodeJS.Timeout | undefined>(undefined);

  const flushDeltaBatch = useCallback(() => {
    const batch = deltaBatchRef.current;
    if ((batch.nodes.length === 0 && batch.edges.length === 0) || !onDeltaUpdate) return;

    const flushed: DeltaUpdate = {
      type: 'graph:delta',
      data: {
        operation: 'add',
        nodes: batch.nodes,
        edges: batch.edges,
        timestamp: Date.now(),
      },
    };
    deltaBatchRef.current = { nodes: [], edges: [] };
    onDeltaUpdate(flushed);
  }, [onDeltaUpdate]);

  const connect = useCallback(() => {
    // Prevent duplicate connections
    if (isConnectingRef.current || wsRef.current?.readyState === WebSocket.CONNECTING || wsRef.current?.readyState === WebSocket.OPEN) {
      log('[useRustWebSocket] Already connected or connecting, skipping');
      return;
    }
    
    isConnectingRef.current = true;
    
    // Use VITE_WS_URL for Rust server (port 3000)
    // Replace localhost with the actual IP if accessing from remote browser
    let rustWsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:3000/ws';
    
    // If we're accessing from a browser and the URL has localhost, replace with actual host
    if (typeof window !== 'undefined' && rustWsUrl.includes('localhost')) {
      const currentHost = window.location.hostname;
      if (currentHost !== 'localhost' && currentHost !== '127.0.0.1') {
        rustWsUrl = rustWsUrl.replace('localhost', currentHost);
      }
    }
    
    log('[useRustWebSocket] Connecting to Rust server:', rustWsUrl);
    
    try {
      const ws = new WebSocket(rustWsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        log('[useRustWebSocket] Connected to Rust server');
        isConnectingRef.current = false;
        reconnectCountRef.current = 0;
        
        // Subscribe to delta updates
        ws.send(JSON.stringify({
          type: 'subscribe',
          client_id: `rust-client-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
          use_deltas: true
        }));
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if ((message.type === 'graph:delta' || message.type === 'graph:update') && onDeltaUpdate) {
            const data = message.data;
            if (!data) return;

            const nodes = (data.nodes_added || data.nodes || []) as GraphNode[];
            const edges = (data.edges_added || data.edges || []) as GraphEdge[];

            if (nodes.length > 0) deltaBatchRef.current.nodes.push(...nodes);
            if (edges.length > 0) deltaBatchRef.current.edges.push(...edges);

            if (!batchTimerRef.current) {
              batchTimerRef.current = setTimeout(() => {
                batchTimerRef.current = undefined;
                flushDeltaBatch();
              }, DELTA_BATCH_INTERVAL_MS);
            }
          }
        } catch (error) {
          logError('[useRustWebSocket] Error parsing message:', error);
        }
      };

      ws.onerror = (error) => {
        logError('[useRustWebSocket] WebSocket error:', error);
        isConnectingRef.current = false;
      };

      ws.onclose = () => {
        log('[useRustWebSocket] Connection closed');
        wsRef.current = null;
        isConnectingRef.current = false;
        
        // Attempt reconnection
        if (reconnectCountRef.current < reconnectAttempts) {
          reconnectCountRef.current++;
          log(`[useRustWebSocket] Reconnecting... (${reconnectCountRef.current}/${reconnectAttempts})`);
          
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, reconnectDelay * Math.pow(2, reconnectCountRef.current - 1)); // Exponential backoff
        }
      };
    } catch (error) {
      logError('[useRustWebSocket] Failed to create WebSocket:', error);
      isConnectingRef.current = false;
    }
  }, [onDeltaUpdate, reconnectAttempts, reconnectDelay, flushDeltaBatch]);

  useEffect(() => {
    connect();

    return () => {
      if (batchTimerRef.current) {
        clearTimeout(batchTimerRef.current);
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  const sendMessage = useCallback((message: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    } else {
      logWarn('[useRustWebSocket] WebSocket not connected');
    }
  }, []);

  return {
    isConnected: wsRef.current?.readyState === WebSocket.OPEN,
    sendMessage,
  };
}