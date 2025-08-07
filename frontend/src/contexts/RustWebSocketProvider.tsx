import React, { createContext, useContext, useCallback, useRef, useEffect, useState } from 'react';

interface DeltaUpdate {
  type: 'graph:delta' | 'graph:update';
  data: {
    operation: 'add' | 'update' | 'delete';
    nodes?: any[];
    edges?: any[];
    timestamp: number;
  };
}

interface RustWebSocketContextType {
  isConnected: boolean;
  subscribe: (callback: (update: DeltaUpdate) => void) => () => void;
  sendMessage: (message: any) => void;
}

const RustWebSocketContext = createContext<RustWebSocketContextType | null>(null);

export function RustWebSocketProvider({ children }: { children: React.ReactNode }) {
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const subscribersRef = useRef<Set<(update: DeltaUpdate) => void>>(new Set());
  const reconnectCountRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
  const isConnectingRef = useRef(false);
  
  const reconnectAttempts = 5;
  const reconnectDelay = 1000;

  const connect = useCallback(() => {
    // Prevent duplicate connections
    if (isConnectingRef.current || wsRef.current?.readyState === WebSocket.CONNECTING || wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[RustWebSocketProvider] Already connected or connecting, skipping');
      return;
    }
    
    isConnectingRef.current = true;
    
    // Use VITE_WS_URL for Rust server (port 3000)
    let rustWsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:3000/ws';
    
    // If we're accessing from a browser and the URL has localhost, replace with actual host
    if (typeof window !== 'undefined' && rustWsUrl.includes('localhost')) {
      const currentHost = window.location.hostname;
      if (currentHost !== 'localhost' && currentHost !== '127.0.0.1') {
        rustWsUrl = rustWsUrl.replace('localhost', currentHost);
      }
    }
    
    console.log('[RustWebSocketProvider] Connecting to Rust server:', rustWsUrl);
    
    try {
      const ws = new WebSocket(rustWsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[RustWebSocketProvider] Connected to Rust server');
        isConnectingRef.current = false;
        setIsConnected(true);
        reconnectCountRef.current = 0;
        
        // Don't subscribe to deltas - Rust server only sends to update_tx, not delta_tx
        // By not subscribing to deltas, we'll receive full updates instead
        console.log('[RustWebSocketProvider] Connected, ready to receive updates');
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          console.log('[RustWebSocketProvider] Message received:', message.type, message);
          
          // Handle subscription confirmation
          if (message.type === 'subscribed:deltas') {
            console.log('[RustWebSocketProvider] Delta subscription confirmed');
          }
          
          // Handle both graph:delta and graph:update message types
          else if (message.type === 'graph:delta' || message.type === 'graph:update') {
            console.log('[RustWebSocketProvider] Delta/Update data:', message);
            
            // Transform graph:update to delta format if needed
            let deltaMessage = message;
            if (message.type === 'graph:update' && message.data) {
              // Assume it's an add operation for new data
              deltaMessage = {
                type: 'graph:delta',
                data: {
                  operation: 'add',
                  nodes: message.data.nodes || [],
                  edges: message.data.edges || [],
                  timestamp: message.data.timestamp || Date.now()
                }
              };
            }
            
            // Notify all subscribers
            console.log('[RustWebSocketProvider] Notifying subscribers, count:', subscribersRef.current.size);
            subscribersRef.current.forEach(callback => {
              console.log('[RustWebSocketProvider] Calling subscriber callback');
              callback(deltaMessage);
            });
          }
        } catch (error) {
          console.error('[RustWebSocketProvider] Error parsing message:', error);
        }
      };

      ws.onerror = (error) => {
        console.error('[RustWebSocketProvider] WebSocket error:', error);
        isConnectingRef.current = false;
      };

      ws.onclose = () => {
        console.log('[RustWebSocketProvider] Connection closed');
        wsRef.current = null;
        isConnectingRef.current = false;
        setIsConnected(false);
        
        // Attempt reconnection
        if (reconnectCountRef.current < reconnectAttempts) {
          reconnectCountRef.current++;
          console.log(`[RustWebSocketProvider] Reconnecting... (${reconnectCountRef.current}/${reconnectAttempts})`);
          
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, reconnectDelay * Math.pow(2, reconnectCountRef.current - 1)); // Exponential backoff
        }
      };
    } catch (error) {
      console.error('[RustWebSocketProvider] Failed to create WebSocket:', error);
      isConnectingRef.current = false;
    }
  }, []);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  const subscribe = useCallback((callback: (update: DeltaUpdate) => void) => {
    console.log('[RustWebSocketProvider] Adding subscriber, current count:', subscribersRef.current.size);
    subscribersRef.current.add(callback);
    console.log('[RustWebSocketProvider] After adding, subscriber count:', subscribersRef.current.size);
    
    return () => {
      console.log('[RustWebSocketProvider] Removing subscriber');
      subscribersRef.current.delete(callback);
      console.log('[RustWebSocketProvider] After removing, subscriber count:', subscribersRef.current.size);
    };
  }, []);

  const sendMessage = useCallback((message: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    } else {
      console.warn('[RustWebSocketProvider] WebSocket not connected');
    }
  }, []);

  return (
    <RustWebSocketContext.Provider value={{ isConnected, subscribe, sendMessage }}>
      {children}
    </RustWebSocketContext.Provider>
  );
}

export function useRustWebSocket() {
  const context = useContext(RustWebSocketContext);
  if (!context) {
    throw new Error('useRustWebSocket must be used within RustWebSocketProvider');
  }
  return context;
}