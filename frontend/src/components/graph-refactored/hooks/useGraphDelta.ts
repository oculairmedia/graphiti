import { useState, useEffect, useCallback, useRef } from 'react';
import { GraphNode } from '../../../api/types';
import { GraphLink } from '../../../types/graph';
import { logger } from '../../../utils/logger';

interface DeltaUpdate {
  id: string;
  timestamp: number;
  type: 'add' | 'update' | 'remove';
  entityType: 'node' | 'link';
  data: any;
}

interface UseGraphDeltaOptions {
  wsUrl?: string;
  autoConnect?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Error) => void;
}

interface UseGraphDeltaReturn {
  isConnected: boolean;
  connect: () => void;
  disconnect: () => void;
  subscribe: (callback: (delta: DeltaUpdate) => void) => () => void;
  send: (message: any) => void;
  stats: {
    messagesReceived: number;
    messagesSent: number;
    lastMessageTime: number | null;
    connectionTime: number | null;
  };
}

/**
 * useGraphDelta - Hook for managing WebSocket delta updates
 * 
 * Features:
 * - WebSocket connection management
 * - Subscription management
 * - Auto-reconnection
 * - Message statistics
 */
export function useGraphDelta(options: UseGraphDeltaOptions = {}): UseGraphDeltaReturn {
  const {
    wsUrl = 'ws://localhost:3000/ws',
    autoConnect = true,
    reconnectInterval = 5000,
    maxReconnectAttempts = 10,
    onConnect,
    onDisconnect,
    onError
  } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [stats, setStats] = useState({
    messagesReceived: 0,
    messagesSent: 0,
    lastMessageTime: null as number | null,
    connectionTime: null as number | null
  });

  // Refs for WebSocket and subscriptions
  const wsRef = useRef<WebSocket | null>(null);
  const subscribersRef = useRef<Set<(delta: DeltaUpdate) => void>>(new Set());
  const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const isMountedRef = useRef(true);

  // Send message via WebSocket
  const send = useCallback((message: any) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      logger.warn('useGraphDelta: Cannot send message, WebSocket not connected');
      return;
    }

    try {
      const messageStr = typeof message === 'string' ? message : JSON.stringify(message);
      wsRef.current.send(messageStr);
      
      setStats(prev => ({
        ...prev,
        messagesSent: prev.messagesSent + 1
      }));

      logger.debug('useGraphDelta: Message sent:', message);
    } catch (error) {
      logger.error('useGraphDelta: Failed to send message:', error);
      onError?.(error instanceof Error ? error : new Error('Failed to send message'));
    }
  }, [onError]);

  // Handle incoming message
  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const delta: DeltaUpdate = JSON.parse(event.data);
      
      // Update stats
      setStats(prev => ({
        ...prev,
        messagesReceived: prev.messagesReceived + 1,
        lastMessageTime: Date.now()
      }));

      // Notify all subscribers
      subscribersRef.current.forEach(callback => {
        try {
          callback(delta);
        } catch (error) {
          logger.error('useGraphDelta: Subscriber error:', error);
        }
      });

      logger.debug('useGraphDelta: Delta received:', delta);
    } catch (error) {
      logger.error('useGraphDelta: Failed to parse message:', error);
    }
  }, []);

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      logger.debug('useGraphDelta: Already connected');
      return;
    }

    if (wsRef.current?.readyState === WebSocket.CONNECTING) {
      logger.debug('useGraphDelta: Connection in progress');
      return;
    }

    try {
      logger.log('useGraphDelta: Connecting to WebSocket...');
      wsRef.current = new WebSocket(wsUrl);

      wsRef.current.onopen = () => {
        if (!isMountedRef.current) return;

        logger.log('useGraphDelta: WebSocket connected');
        setIsConnected(true);
        setStats(prev => ({
          ...prev,
          connectionTime: Date.now()
        }));
        reconnectAttemptsRef.current = 0;
        onConnect?.();
      };

      wsRef.current.onmessage = handleMessage;

      wsRef.current.onclose = (event) => {
        if (!isMountedRef.current) return;

        logger.log('useGraphDelta: WebSocket closed:', event.code, event.reason);
        setIsConnected(false);
        setStats(prev => ({
          ...prev,
          connectionTime: null
        }));
        onDisconnect?.();

        // Auto-reconnect if enabled
        if (autoConnect && reconnectAttemptsRef.current < maxReconnectAttempts) {
          scheduleReconnect();
        }
      };

      wsRef.current.onerror = (error) => {
        logger.error('useGraphDelta: WebSocket error:', error);
        onError?.(new Error('WebSocket connection error'));
      };

    } catch (error) {
      logger.error('useGraphDelta: Failed to connect:', error);
      onError?.(error instanceof Error ? error : new Error('Connection failed'));
      
      if (autoConnect && reconnectAttemptsRef.current < maxReconnectAttempts) {
        scheduleReconnect();
      }
    }
  }, [wsUrl, autoConnect, maxReconnectAttempts, handleMessage, onConnect, onDisconnect, onError]);

  // Schedule reconnection
  const scheduleReconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
    }

    reconnectAttemptsRef.current++;
    const delay = Math.min(reconnectInterval * reconnectAttemptsRef.current, 30000);

    logger.log(`useGraphDelta: Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts})`);

    reconnectTimerRef.current = setTimeout(() => {
      if (isMountedRef.current) {
        connect();
      }
    }, delay);
  }, [reconnectInterval, maxReconnectAttempts, connect]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    logger.log('useGraphDelta: Disconnecting...');

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    if (wsRef.current) {
      // Remove event handlers to prevent reconnection
      wsRef.current.onopen = null;
      wsRef.current.onmessage = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;

      if (wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
      wsRef.current = null;
    }

    setIsConnected(false);
    setStats(prev => ({
      ...prev,
      connectionTime: null
    }));
  }, []);

  // Subscribe to delta updates
  const subscribe = useCallback((callback: (delta: DeltaUpdate) => void): (() => void) => {
    subscribersRef.current.add(callback);
    logger.debug('useGraphDelta: Subscriber added, total:', subscribersRef.current.size);

    // Return unsubscribe function
    return () => {
      subscribersRef.current.delete(callback);
      logger.debug('useGraphDelta: Subscriber removed, total:', subscribersRef.current.size);
    };
  }, []);

  // Auto-connect on mount if enabled
  useEffect(() => {
    if (autoConnect) {
      connect();
    }

    return () => {
      isMountedRef.current = false;
      disconnect();
    };
  }, []); // Only run on mount/unmount

  // Reconnect on URL change
  useEffect(() => {
    if (isConnected) {
      logger.log('useGraphDelta: URL changed, reconnecting...');
      disconnect();
      connect();
    }
  }, [wsUrl]);

  return {
    isConnected,
    connect,
    disconnect,
    subscribe,
    send,
    stats
  };
}

export default useGraphDelta;