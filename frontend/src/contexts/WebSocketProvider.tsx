import React, { createContext, useContext, useCallback, useEffect, useState, useRef } from 'react';
import { useWebSocket, NodeAccessEvent, GraphUpdateEvent, WebSocketEvent } from '../hooks/useWebSocket';

interface WebSocketContextValue {
  isConnected: boolean;
  subscribe: (handler: (event: WebSocketEvent) => void) => () => void;
  subscribeToNodeAccess: (handler: (event: NodeAccessEvent) => void) => () => void;
  subscribeToGraphUpdate: (handler: (event: GraphUpdateEvent) => void) => () => void;
  lastNodeAccessEvent: NodeAccessEvent | null;
  lastGraphUpdateEvent: GraphUpdateEvent | null;
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
  url 
}) => {
  // Handle relative URLs and construct full WebSocket URL
  const wsUrl = React.useMemo(() => {
    const envUrl = import.meta.env.VITE_WEBSOCKET_URL;
    
    // If url prop is provided, use it
    if (url) {
      return url;
    }
    
    // If environment URL is provided
    if (envUrl) {
      // If it's a relative URL, construct the full URL
      if (envUrl.startsWith('/')) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${window.location.host}${envUrl}`;
      }
      // If it's already a full URL, use it as is
      return envUrl;
    }
    
    // Default fallback
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/ws`;
  }, [url]);
  
  const [handlers, setHandlers] = useState<Set<(event: WebSocketEvent) => void>>(new Set());
  const [nodeAccessHandlers, setNodeAccessHandlers] = useState<Set<(event: NodeAccessEvent) => void>>(new Set());
  const [graphUpdateHandlers, setGraphUpdateHandlers] = useState<Set<(event: GraphUpdateEvent) => void>>(new Set());
  const [lastNodeAccessEvent, setLastNodeAccessEvent] = useState<NodeAccessEvent | null>(null);
  const [lastGraphUpdateEvent, setLastGraphUpdateEvent] = useState<GraphUpdateEvent | null>(null);

  const handlersRef = useRef<Set<(event: WebSocketEvent) => void>>(new Set());
  const nodeAccessHandlersRef = useRef<Set<(event: NodeAccessEvent) => void>>(new Set());
  const graphUpdateHandlersRef = useRef<Set<(event: GraphUpdateEvent) => void>>(new Set());
  
  // Log WebSocket URL only once on mount
  useEffect(() => {
    console.log('WebSocketProvider - Environment URL:', import.meta.env.VITE_WEBSOCKET_URL);
    console.log('WebSocketProvider - Using URL:', wsUrl);
  }, []); // Empty deps - log only once
  
  useEffect(() => {
    handlersRef.current = handlers;
    nodeAccessHandlersRef.current = nodeAccessHandlers;
    graphUpdateHandlersRef.current = graphUpdateHandlers;
  }, [handlers, nodeAccessHandlers, graphUpdateHandlers]);
  
  const handleMessage = useCallback((event: WebSocketEvent) => {
    // Handle specific event types
    if (event.type === 'node_access') {
      setLastNodeAccessEvent(event as NodeAccessEvent);
      nodeAccessHandlersRef.current.forEach(handler => {
        try {
          handler(event as NodeAccessEvent);
        } catch (error) {
          console.error('Error in NodeAccess event handler:', error);
        }
      });
    } else if (event.type === 'graph:update') {
      setLastGraphUpdateEvent(event as GraphUpdateEvent);
      graphUpdateHandlersRef.current.forEach(handler => {
        try {
          handler(event as GraphUpdateEvent);
        } catch (error) {
          console.error('Error in GraphUpdate event handler:', error);
        }
      });
    }
    
    // Call generic handlers
    handlersRef.current.forEach(handler => {
      try {
        handler(event);
      } catch (error) {
        console.error('Error in WebSocket event handler:', error);
      }
    });
  }, []);

  const { isConnected } = useWebSocket({
    url: wsUrl,
    onMessage: handleMessage,
    onConnect: () => console.log('WebSocket provider connected'),
    onDisconnect: () => console.log('WebSocket provider disconnected'),
    onError: (error) => console.error('WebSocket provider error:', error)
  });

  const subscribe = useCallback((handler: (event: WebSocketEvent) => void) => {
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

  const subscribeToNodeAccess = useCallback((handler: (event: NodeAccessEvent) => void) => {
    setNodeAccessHandlers(prev => new Set(prev).add(handler));
    
    // Return unsubscribe function
    return () => {
      setNodeAccessHandlers(prev => {
        const next = new Set(prev);
        next.delete(handler);
        return next;
      });
    };
  }, []);

  const subscribeToGraphUpdate = useCallback((handler: (event: GraphUpdateEvent) => void) => {
    setGraphUpdateHandlers(prev => new Set(prev).add(handler));
    
    // Return unsubscribe function
    return () => {
      setGraphUpdateHandlers(prev => {
        const next = new Set(prev);
        next.delete(handler);
        return next;
      });
    };
  }, []);

  const value: WebSocketContextValue = {
    isConnected,
    subscribe,
    subscribeToNodeAccess,
    subscribeToGraphUpdate,
    lastNodeAccessEvent,
    lastGraphUpdateEvent
  };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
};