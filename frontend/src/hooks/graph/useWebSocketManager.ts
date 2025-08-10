import { useEffect, useRef, useCallback, useState } from 'react';
import { GraphDelta } from './useGraphData';

export interface WebSocketConfig {
  url: string;
  reconnectAttempts?: number;
  reconnectDelay?: number;
  heartbeatInterval?: number;
  enableCompression?: boolean;
  batchUpdates?: boolean;
  batchInterval?: number;
}

export interface WebSocketMessage {
  type: 'delta' | 'full' | 'ping' | 'pong' | 'error' | 'info';
  data?: any;
  delta?: GraphDelta;
  timestamp: number;
  sequence?: number;
}

export interface WebSocketState {
  isConnected: boolean;
  isReconnecting: boolean;
  connectionQuality: 'excellent' | 'good' | 'poor' | 'offline';
  lastPing: number;
  messageQueueSize: number;
  error: string | null;
}

export interface WebSocketActions {
  connect: () => void;
  disconnect: () => void;
  send: (message: any) => void;
  reconnect: () => void;
  clearQueue: () => void;
}

interface UpdateBatch {
  deltas: GraphDelta[];
  timestamp: number;
}

/**
 * Custom hook for managing WebSocket connections with automatic reconnection,
 * heartbeat monitoring, and message batching
 */
export function useWebSocketManager(
  config: WebSocketConfig,
  onMessage?: (message: WebSocketMessage) => void,
  onDelta?: (delta: GraphDelta) => void
): [WebSocketState, WebSocketActions] {
  const {
    url,
    reconnectAttempts = 5,
    reconnectDelay = 1000,
    heartbeatInterval = 30000,
    enableCompression = true,
    batchUpdates = true,
    batchInterval = 16 // ~60fps
  } = config;

  // State
  const [isConnected, setIsConnected] = useState(false);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [connectionQuality, setConnectionQuality] = useState<WebSocketState['connectionQuality']>('offline');
  const [lastPing, setLastPing] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // Refs
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const heartbeatIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const messageQueueRef = useRef<WebSocketMessage[]>([]);
  const sequenceRef = useRef(0);
  const lastSequenceRef = useRef(0);
  const updateBatchRef = useRef<UpdateBatch | null>(null);
  const batchTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Calculate connection quality based on ping
  const updateConnectionQuality = useCallback((ping: number) => {
    if (ping === 0) {
      setConnectionQuality('offline');
    } else if (ping < 50) {
      setConnectionQuality('excellent');
    } else if (ping < 150) {
      setConnectionQuality('good');
    } else {
      setConnectionQuality('poor');
    }
  }, []);

  // Process batched updates
  const processBatchedUpdates = useCallback(() => {
    if (!updateBatchRef.current || updateBatchRef.current.deltas.length === 0) {
      return;
    }

    const batch = updateBatchRef.current;
    updateBatchRef.current = null;

    // Merge deltas into a single delta
    const mergedDelta: GraphDelta = {
      timestamp: batch.timestamp,
      addedNodes: [],
      updatedNodes: new Map(),
      removedNodeIds: [],
      addedLinks: [],
      removedLinkIds: []
    };

    // Merge all deltas
    batch.deltas.forEach(delta => {
      if (delta.addedNodes) {
        mergedDelta.addedNodes!.push(...delta.addedNodes);
      }
      if (delta.updatedNodes) {
        delta.updatedNodes.forEach((updates, nodeId) => {
          const existing = mergedDelta.updatedNodes!.get(nodeId) || {};
          mergedDelta.updatedNodes!.set(nodeId, { ...existing, ...updates });
        });
      }
      if (delta.removedNodeIds) {
        mergedDelta.removedNodeIds!.push(...delta.removedNodeIds);
      }
      if (delta.addedLinks) {
        mergedDelta.addedLinks!.push(...delta.addedLinks);
      }
      if (delta.removedLinkIds) {
        mergedDelta.removedLinkIds!.push(...delta.removedLinkIds);
      }
    });

    // Send merged delta
    if (onDelta) {
      onDelta(mergedDelta);
    }
  }, [onDelta]);

  // Add delta to batch
  const addDeltaToBatch = useCallback((delta: GraphDelta) => {
    if (!batchUpdates) {
      if (onDelta) {
        onDelta(delta);
      }
      return;
    }

    if (!updateBatchRef.current) {
      updateBatchRef.current = {
        deltas: [],
        timestamp: Date.now()
      };
    }

    updateBatchRef.current.deltas.push(delta);

    // Clear existing timeout
    if (batchTimeoutRef.current) {
      clearTimeout(batchTimeoutRef.current);
    }

    // Set new timeout to process batch
    batchTimeoutRef.current = setTimeout(() => {
      processBatchedUpdates();
    }, batchInterval);
  }, [batchUpdates, batchInterval, onDelta, processBatchedUpdates]);

  // Handle incoming messages
  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const message: WebSocketMessage = JSON.parse(event.data);
      
      // Check sequence for missed messages
      if (message.sequence !== undefined) {
        if (message.sequence !== lastSequenceRef.current + 1) {
          console.warn(`Missed messages: expected ${lastSequenceRef.current + 1}, got ${message.sequence}`);
        }
        lastSequenceRef.current = message.sequence;
      }

      // Handle different message types
      switch (message.type) {
        case 'delta':
          if (message.delta) {
            addDeltaToBatch(message.delta);
          }
          break;
          
        case 'full':
          // Full update - clear batch and process immediately
          if (batchTimeoutRef.current) {
            clearTimeout(batchTimeoutRef.current);
          }
          updateBatchRef.current = null;
          break;
          
        case 'pong':
          const ping = Date.now() - message.timestamp;
          setLastPing(ping);
          updateConnectionQuality(ping);
          break;
          
        case 'error':
          setError(message.data?.message || 'Unknown WebSocket error');
          break;
      }

      // Forward message to handler
      if (onMessage) {
        onMessage(message);
      }
    } catch (err) {
      console.error('Failed to parse WebSocket message:', err);
      setError('Failed to parse message');
    }
  }, [addDeltaToBatch, onMessage, updateConnectionQuality]);

  // Send heartbeat
  const sendHeartbeat = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const pingMessage: WebSocketMessage = {
        type: 'ping',
        timestamp: Date.now()
      };
      wsRef.current.send(JSON.stringify(pingMessage));
    }
  }, []);

  // Setup heartbeat monitoring
  const setupHeartbeat = useCallback(() => {
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
    }

    heartbeatIntervalRef.current = setInterval(() => {
      sendHeartbeat();
    }, heartbeatInterval);

    // Send initial heartbeat
    sendHeartbeat();
  }, [heartbeatInterval, sendHeartbeat]);

  // Cleanup heartbeat
  const cleanupHeartbeat = useCallback(() => {
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = null;
    }
  }, []);

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      // Clean up existing connection
      if (wsRef.current) {
        wsRef.current.close();
      }

      // Create new WebSocket connection
      const protocols = enableCompression ? ['graphiti-ws', 'permessage-deflate'] : ['graphiti-ws'];
      wsRef.current = new WebSocket(url, protocols);

      wsRef.current.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
        setIsReconnecting(false);
        setError(null);
        reconnectCountRef.current = 0;
        
        // Setup heartbeat
        setupHeartbeat();
        
        // Process queued messages
        while (messageQueueRef.current.length > 0) {
          const queuedMessage = messageQueueRef.current.shift();
          if (queuedMessage && wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(queuedMessage));
          }
        }
      };

      wsRef.current.onmessage = handleMessage;

      wsRef.current.onerror = (event) => {
        console.error('WebSocket error:', event);
        setError('WebSocket connection error');
      };

      wsRef.current.onclose = (event) => {
        console.log('WebSocket closed:', event.code, event.reason);
        setIsConnected(false);
        setConnectionQuality('offline');
        cleanupHeartbeat();

        // Attempt reconnection if not manual disconnect
        if (event.code !== 1000 && reconnectCountRef.current < reconnectAttempts) {
          setIsReconnecting(true);
          reconnectCountRef.current++;
          
          const delay = reconnectDelay * Math.pow(2, reconnectCountRef.current - 1); // Exponential backoff
          console.log(`Reconnecting in ${delay}ms (attempt ${reconnectCountRef.current}/${reconnectAttempts})`);
          
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, delay);
        } else if (reconnectCountRef.current >= reconnectAttempts) {
          setError(`Failed to reconnect after ${reconnectAttempts} attempts`);
        }
      };
    } catch (err) {
      console.error('Failed to create WebSocket:', err);
      setError('Failed to create WebSocket connection');
    }
  }, [url, enableCompression, reconnectAttempts, reconnectDelay, handleMessage, setupHeartbeat, cleanupHeartbeat]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    cleanupHeartbeat();

    if (wsRef.current) {
      wsRef.current.close(1000, 'Manual disconnect');
      wsRef.current = null;
    }

    setIsConnected(false);
    setIsReconnecting(false);
    setConnectionQuality('offline');
  }, [cleanupHeartbeat]);

  // Send message
  const send = useCallback((message: any) => {
    const wsMessage: WebSocketMessage = {
      type: 'info',
      data: message,
      timestamp: Date.now(),
      sequence: ++sequenceRef.current
    };

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(wsMessage));
    } else {
      // Queue message for later
      messageQueueRef.current.push(wsMessage);
      
      // Limit queue size
      if (messageQueueRef.current.length > 100) {
        messageQueueRef.current.shift();
      }
    }
  }, []);

  // Manual reconnect
  const reconnect = useCallback(() => {
    disconnect();
    reconnectCountRef.current = 0;
    connect();
  }, [connect, disconnect]);

  // Clear message queue
  const clearQueue = useCallback(() => {
    messageQueueRef.current = [];
  }, []);

  // Auto-connect on mount
  useEffect(() => {
    connect();
    
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  // Process final batch on unmount
  useEffect(() => {
    return () => {
      if (batchTimeoutRef.current) {
        clearTimeout(batchTimeoutRef.current);
      }
      processBatchedUpdates();
    };
  }, [processBatchedUpdates]);

  // Create state object
  const state: WebSocketState = {
    isConnected,
    isReconnecting,
    connectionQuality,
    lastPing,
    messageQueueSize: messageQueueRef.current.length,
    error
  };

  // Create actions object
  const actions: WebSocketActions = {
    connect,
    disconnect,
    send,
    reconnect,
    clearQueue
  };

  return [state, actions];
}