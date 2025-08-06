import { useEffect, useRef, useState, useCallback } from 'react';

export interface NodeAccessEvent {
  type: 'node_access';
  node_ids: string[];
  timestamp: string;
  access_type?: string;
  query?: string;
}

export interface GraphUpdateEvent {
  type: 'graph:update';
  data: {
    operation: 'add_nodes' | 'add_edges' | 'update_nodes' | 'delete_nodes' | 'delete_edges';
    nodes?: any[];
    edges?: any[];
    timestamp: number;
  };
}

export interface WebSocketMessage {
  type: string;
  data?: any;
  [key: string]: any;
}

export type WebSocketEvent = NodeAccessEvent | GraphUpdateEvent;

interface UseWebSocketOptions {
  url: string;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  onMessage?: (event: WebSocketEvent) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
}

export const useWebSocket = ({
  url,
  reconnectInterval = 3000,
  maxReconnectAttempts = 10,
  onMessage,
  onConnect,
  onDisconnect,
  onError
}: UseWebSocketOptions) => {
  const [isConnected, setIsConnected] = useState(false);
  const reconnectAttemptRef = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const clientIdRef = useRef<string>(`client-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`);

  // Store callbacks in refs to avoid recreating connect function
  const onMessageRef = useRef(onMessage);
  const onConnectRef = useRef(onConnect);
  const onDisconnectRef = useRef(onDisconnect);
  const onErrorRef = useRef(onError);
  
  useEffect(() => {
    onMessageRef.current = onMessage;
    onConnectRef.current = onConnect;
    onDisconnectRef.current = onDisconnect;
    onErrorRef.current = onError;
  }, [onMessage, onConnect, onDisconnect, onError]);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN || 
        wsRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    try {
      console.log('Attempting WebSocket connection to:', url);
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('WebSocket connected successfully!');
        setIsConnected(true);
        reconnectAttemptRef.current = 0;
        
        // Send subscription message
        const subscribeMsg = {
          type: 'subscribe',
          client_id: clientIdRef.current
        };
        console.log('Sending subscription:', subscribeMsg);
        ws.send(JSON.stringify(subscribeMsg));
        
        onConnectRef.current?.();
      };

      ws.onmessage = (event) => {
        console.log('WebSocket message received:', event.data);
        try {
          const data = JSON.parse(event.data) as WebSocketMessage;
          console.log('Parsed message:', data);
          
          if (data.type === 'node_access' && onMessageRef.current) {
            console.log('Node access event:', data);
            onMessageRef.current(data as NodeAccessEvent);
          } else if (data.type === 'graph:update' && onMessageRef.current) {
            console.log('Graph update event:', data);
            onMessageRef.current(data as GraphUpdateEvent);
          } else if (data.type === 'subscription_confirmed') {
            console.log('WebSocket subscription confirmed');
          } else if (data.type === 'pong') {
            console.log('Pong received');
          } else if (data.type === 'connected') {
            console.log('WebSocket connected confirmation');
          } else {
            console.log('Unknown message type:', data.type);
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
          console.error('Raw message:', event.data);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        console.error('WebSocket readyState:', ws.readyState);
        console.error('WebSocket url:', ws.url);
        onErrorRef.current?.(error);
      };

      ws.onclose = () => {
        console.log('WebSocket disconnected');
        setIsConnected(false);
        onDisconnectRef.current?.();
        
        // Attempt to reconnect
        if (reconnectAttemptRef.current < maxReconnectAttempts) {
          const timeout = Math.min(reconnectInterval * Math.pow(1.5, reconnectAttemptRef.current), 30000);
          console.log(`Reconnecting in ${timeout}ms (attempt ${reconnectAttemptRef.current + 1}/${maxReconnectAttempts})`);
          
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttemptRef.current += 1;
            connect();
          }, timeout);
        }
      };
    } catch (error) {
      console.error('Error creating WebSocket:', error);
      setIsConnected(false);
    }
  }, [url, reconnectInterval, maxReconnectAttempts]);

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
    reconnectAttemptRef.current = 0;
  }, []);

  const sendMessage = useCallback((message: WebSocketMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket is not connected');
    }
  }, []);

  const sendPing = useCallback(() => {
    sendMessage({ type: 'ping' });
  }, [sendMessage]);

  useEffect(() => {
    // Prevent multiple connections
    if (wsRef.current?.readyState === WebSocket.CONNECTING || 
        wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }
    
    connect();
    
    return () => {
      // Ensure we clean up on unmount
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      
      setIsConnected(false);
      reconnectAttemptRef.current = 0;
    };
  }, []); // Empty dependency array to run only once
  
  // Separate effect for ping interval to avoid dependency issues
  useEffect(() => {
    if (!isConnected) return;
    
    const pingInterval = setInterval(() => {
      sendPing();
    }, 30000); // Ping every 30 seconds
    
    return () => {
      clearInterval(pingInterval);
    };
  }, [isConnected, sendPing]);

  return {
    isConnected,
    sendMessage,
    disconnect,
    reconnect: connect
  };
};