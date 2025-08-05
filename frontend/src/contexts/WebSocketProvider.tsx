import React, { createContext, useContext, useCallback, useEffect, useState, useRef } from 'react';
import { useWebSocket, NodeAccessEvent } from '../hooks/useWebSocket';

interface WebSocketContextValue {
  isConnected: boolean;
  subscribe: (handler: (event: NodeAccessEvent) => void) => () => void;
  lastNodeAccessEvent: NodeAccessEvent | null;
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

export const useWebSocketContext = () => {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocketContext must be used within WebSocketProvider');
  }
  return context;
};

interface WebSocketProviderProps {
  children: React.ReactNode;
  url?: string;
}

export const WebSocketProvider: React.FC<WebSocketProviderProps> = ({ 
  children, 
  url = import.meta.env.VITE_WEBSOCKET_URL || 
    (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + 
    window.location.host + '/graphiti/ws' 
}) => {
  const [handlers, setHandlers] = useState<Set<(event: NodeAccessEvent) => void>>(new Set());
  const [lastNodeAccessEvent, setLastNodeAccessEvent] = useState<NodeAccessEvent | null>(null);

  const handlersRef = useRef<Set<(event: NodeAccessEvent) => void>>(new Set());
  
  useEffect(() => {
    handlersRef.current = handlers;
  }, [handlers]);
  
  const handleMessage = useCallback((event: NodeAccessEvent) => {
    setLastNodeAccessEvent(event);
    handlersRef.current.forEach(handler => {
      try {
        handler(event);
      } catch (error) {
        console.error('Error in WebSocket event handler:', error);
      }
    });
  }, []);

  const { isConnected } = useWebSocket({
    url,
    onMessage: handleMessage,
    onConnect: () => console.log('WebSocket provider connected'),
    onDisconnect: () => console.log('WebSocket provider disconnected'),
    onError: (error) => console.error('WebSocket provider error:', error)
  });

  const subscribe = useCallback((handler: (event: NodeAccessEvent) => void) => {
    setHandlers(prev => new Set(prev).add(handler));
    
    // Return unsubscribe function
    return () => {
      setHandlers(prev => {
        const next = new Set(prev);
        next.delete(handler);
        return next;
      });
    };
  }, []);

  const value: WebSocketContextValue = {
    isConnected,
    subscribe,
    lastNodeAccessEvent
  };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
};