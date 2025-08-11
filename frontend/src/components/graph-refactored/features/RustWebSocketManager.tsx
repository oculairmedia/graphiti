import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { GraphNode, GraphEdge } from '../../../api/types';

interface RustMessage {
  type: 'delta' | 'snapshot' | 'metrics' | 'error' | 'ping' | 'pong';
  data?: any;
  timestamp: number;
  sequence?: number;
  version?: string;
}

interface RustDelta {
  added_nodes?: GraphNode[];
  updated_nodes?: Partial<GraphNode>[];
  removed_nodes?: string[];
  added_edges?: GraphEdge[];
  updated_edges?: Partial<GraphEdge>[];
  removed_edges?: string[];
  metrics?: GraphMetrics;
}

interface GraphMetrics {
  node_count: number;
  edge_count: number;
  density: number;
  avg_degree: number;
  components: number;
  processing_time_ms: number;
}

interface RustWebSocketConfig {
  url?: string;
  reconnectAttempts?: number;
  reconnectDelay?: number;
  heartbeatInterval?: number;
  enableCompression?: boolean;
  batchUpdates?: boolean;
  batchInterval?: number;
}

interface RustWebSocketManagerProps {
  config?: RustWebSocketConfig;
  onDelta?: (delta: RustDelta) => void;
  onSnapshot?: (snapshot: { nodes: GraphNode[]; edges: GraphEdge[] }) => void;
  onMetrics?: (metrics: GraphMetrics) => void;
  onConnectionChange?: (connected: boolean) => void;
  children?: React.ReactNode;
}

interface ConnectionState {
  isConnected: boolean;
  reconnectAttempts: number;
  lastError: Error | null;
  lastMessageTime: number;
  latency: number;
  messageQueue: RustMessage[];
}

/**
 * RustWebSocketManager - Manages WebSocket connection to Rust visualization server
 * Handles real-time updates, reconnection, and message batching
 */
export const RustWebSocketManager: React.FC<RustWebSocketManagerProps> = ({
  config = {},
  onDelta,
  onSnapshot,
  onMetrics,
  onConnectionChange,
  children
}) => {
  const [connectionState, setConnectionState] = useState<ConnectionState>({
    isConnected: false,
    reconnectAttempts: 0,
    lastError: null,
    lastMessageTime: 0,
    latency: 0,
    messageQueue: []
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const heartbeatIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const batchTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const sequenceRef = useRef<number>(0);
  const pendingDeltasRef = useRef<RustDelta[]>([]);
  const lastPingRef = useRef<number>(0);

  // Default configuration
  const fullConfig: Required<RustWebSocketConfig> = {
    url: config.url || `ws://${window.location.hostname}:4543/ws`, // Fixed port to 4543
    reconnectAttempts: config.reconnectAttempts ?? 5,
    reconnectDelay: config.reconnectDelay ?? 1000,
    heartbeatInterval: config.heartbeatInterval ?? 30000,
    enableCompression: config.enableCompression ?? true,
    batchUpdates: config.batchUpdates ?? true,
    batchInterval: config.batchInterval ?? 100
  };

  // Process batched deltas
  const processBatchedDeltas = useCallback(() => {
    if (pendingDeltasRef.current.length === 0) return;

    // Merge all pending deltas
    const mergedDelta: RustDelta = {
      added_nodes: [],
      updated_nodes: [],
      removed_nodes: [],
      added_edges: [],
      updated_edges: [],
      removed_edges: [],
      metrics: undefined
    };

    pendingDeltasRef.current.forEach(delta => {
      if (delta.added_nodes) mergedDelta.added_nodes!.push(...delta.added_nodes);
      if (delta.updated_nodes) mergedDelta.updated_nodes!.push(...delta.updated_nodes);
      if (delta.removed_nodes) mergedDelta.removed_nodes!.push(...delta.removed_nodes);
      if (delta.added_edges) mergedDelta.added_edges!.push(...delta.added_edges);
      if (delta.updated_edges) mergedDelta.updated_edges!.push(...delta.updated_edges);
      if (delta.removed_edges) mergedDelta.removed_edges!.push(...delta.removed_edges);
      if (delta.metrics) mergedDelta.metrics = delta.metrics; // Use latest metrics
    });

    // Clear pending deltas
    pendingDeltasRef.current = [];

    // Send merged delta
    onDelta?.(mergedDelta);
  }, [onDelta]);

  // Handle incoming message
  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const message: RustMessage = JSON.parse(event.data);
      
      setConnectionState(prev => ({
        ...prev,
        lastMessageTime: Date.now()
      }));

      switch (message.type) {
        case 'delta':
          if (fullConfig.batchUpdates) {
            pendingDeltasRef.current.push(message.data as RustDelta);
            
            // Clear existing batch timeout
            if (batchTimeoutRef.current) {
              clearTimeout(batchTimeoutRef.current);
            }
            
            // Set new batch timeout
            batchTimeoutRef.current = setTimeout(() => {
              processBatchedDeltas();
            }, fullConfig.batchInterval);
          } else {
            onDelta?.(message.data as RustDelta);
          }
          break;

        case 'snapshot':
          onSnapshot?.(message.data);
          break;

        case 'metrics':
          onMetrics?.(message.data as GraphMetrics);
          break;

        case 'pong':
          const latency = Date.now() - lastPingRef.current;
          setConnectionState(prev => ({ ...prev, latency }));
          break;

        case 'error':
          console.error('[RustWebSocket] Server error:', message.data);
          setConnectionState(prev => ({
            ...prev,
            lastError: new Error(message.data)
          }));
          break;

        default:
          console.warn('[RustWebSocket] Unknown message type:', message.type);
      }
    } catch (error) {
      console.error('[RustWebSocket] Failed to parse message:', error);
    }
  }, [fullConfig.batchUpdates, fullConfig.batchInterval, processBatchedDeltas, onDelta, onSnapshot, onMetrics]);

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      console.log('[RustWebSocket] Connecting to:', fullConfig.url);
      const ws = new WebSocket(fullConfig.url);
      
      if (fullConfig.enableCompression) {
        // Note: WebSocket compression is handled at the protocol level
        // This is just a placeholder for protocol-specific setup
      }

      ws.onopen = () => {
        console.log('[RustWebSocket] Connected');
        setConnectionState(prev => ({
          ...prev,
          isConnected: true,
          reconnectAttempts: 0,
          lastError: null
        }));
        
        onConnectionChange?.(true);
        
        // Send queued messages
        connectionState.messageQueue.forEach(msg => {
          ws.send(JSON.stringify(msg));
        });
        
        // Clear queue
        setConnectionState(prev => ({
          ...prev,
          messageQueue: []
        }));
        
        // Start heartbeat
        startHeartbeat();
      };

      ws.onmessage = handleMessage;

      ws.onerror = (error) => {
        console.error('[RustWebSocket] Error:', error);
        setConnectionState(prev => ({
          ...prev,
          lastError: new Error('WebSocket error')
        }));
      };

      ws.onclose = () => {
        console.log('[RustWebSocket] Disconnected');
        setConnectionState(prev => ({
          ...prev,
          isConnected: false
        }));
        
        onConnectionChange?.(false);
        stopHeartbeat();
        
        // Attempt reconnection
        if (connectionState.reconnectAttempts < fullConfig.reconnectAttempts) {
          const delay = fullConfig.reconnectDelay * Math.pow(2, connectionState.reconnectAttempts);
          console.log(`[RustWebSocket] Reconnecting in ${delay}ms...`);
          
          reconnectTimeoutRef.current = setTimeout(() => {
            setConnectionState(prev => ({
              ...prev,
              reconnectAttempts: prev.reconnectAttempts + 1
            }));
            connect();
          }, delay);
        }
      };

      wsRef.current = ws;
    } catch (error) {
      console.error('[RustWebSocket] Failed to connect:', error);
      setConnectionState(prev => ({
        ...prev,
        lastError: error as Error
      }));
    }
  }, [fullConfig, connectionState.reconnectAttempts, connectionState.messageQueue, handleMessage, onConnectionChange]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    
    stopHeartbeat();
    
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    
    setConnectionState(prev => ({
      ...prev,
      isConnected: false,
      reconnectAttempts: 0
    }));
  }, []);

  // Send message
  const sendMessage = useCallback((message: Partial<RustMessage>) => {
    const fullMessage: RustMessage = {
      type: message.type || 'delta',
      data: message.data,
      timestamp: Date.now(),
      sequence: sequenceRef.current++,
      version: message.version || '1.0'
    };

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(fullMessage));
    } else {
      // Queue message for later
      setConnectionState(prev => ({
        ...prev,
        messageQueue: [...prev.messageQueue, fullMessage]
      }));
    }
  }, []);

  // Start heartbeat
  const startHeartbeat = useCallback(() => {
    stopHeartbeat();
    
    heartbeatIntervalRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        lastPingRef.current = Date.now();
        sendMessage({ type: 'ping' });
      }
    }, fullConfig.heartbeatInterval);
  }, [fullConfig.heartbeatInterval, sendMessage]);

  // Stop heartbeat
  const stopHeartbeat = useCallback(() => {
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = null;
    }
  }, []);

  // Request snapshot
  const requestSnapshot = useCallback(() => {
    sendMessage({
      type: 'snapshot',
      data: { full: true }
    });
  }, [sendMessage]);

  // Request metrics
  const requestMetrics = useCallback(() => {
    sendMessage({
      type: 'metrics',
      data: { detailed: true }
    });
  }, [sendMessage]);

  // Connect on mount (only if not disabled)
  useEffect(() => {
    // Skip auto-connect if URL contains 'disabled' or port 4543 is not available
    if (!fullConfig.url.includes('disabled')) {
      // Delay connection to avoid initial mount issues
      const timer = setTimeout(() => {
        connect();
      }, 1000);
      
      return () => {
        clearTimeout(timer);
        disconnect();
        
        if (batchTimeoutRef.current) {
          clearTimeout(batchTimeoutRef.current);
        }
      };
    }
    
    return () => {
      if (batchTimeoutRef.current) {
        clearTimeout(batchTimeoutRef.current);
      }
    };
  }, []); // Only run once on mount

  // Context value
  const contextValue = useMemo(() => ({
    ...connectionState,
    connect,
    disconnect,
    sendMessage,
    requestSnapshot,
    requestMetrics
  }), [connectionState, connect, disconnect, sendMessage, requestSnapshot, requestMetrics]);

  return (
    <RustWebSocketContext.Provider value={contextValue}>
      {children}
    </RustWebSocketContext.Provider>
  );
};

// Context
const RustWebSocketContext = React.createContext<{
  isConnected: boolean;
  reconnectAttempts: number;
  lastError: Error | null;
  lastMessageTime: number;
  latency: number;
  messageQueue: RustMessage[];
  connect: () => void;
  disconnect: () => void;
  sendMessage: (message: Partial<RustMessage>) => void;
  requestSnapshot: () => void;
  requestMetrics: () => void;
}>({
  isConnected: false,
  reconnectAttempts: 0,
  lastError: null,
  lastMessageTime: 0,
  latency: 0,
  messageQueue: [],
  connect: () => {},
  disconnect: () => {},
  sendMessage: () => {},
  requestSnapshot: () => {},
  requestMetrics: () => {}
});

export const useRustWebSocket = () => React.useContext(RustWebSocketContext);