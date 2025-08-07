import React, { createContext, useContext, useCallback, useEffect, useState, useRef, useReducer, useMemo } from 'react';
import { useWebSocket, NodeAccessEvent, GraphUpdateEvent, DeltaUpdateEvent, CacheInvalidateEvent, WebSocketEvent } from '../hooks/useWebSocket';

interface WebSocketContextValue {
  isConnected: boolean;
  connectionQuality: 'excellent' | 'good' | 'poor';
  latency: number;
  subscribe: (handler: (event: WebSocketEvent) => void) => () => void;
  subscribeToNodeAccess: (handler: (event: NodeAccessEvent) => void) => () => void;
  subscribeToGraphUpdate: (handler: (event: GraphUpdateEvent) => void) => () => void;
  subscribeToDeltaUpdate: (handler: (event: DeltaUpdateEvent) => void) => () => void;
  subscribeToCacheInvalidate: (handler: (event: CacheInvalidateEvent) => void) => () => void;
  lastNodeAccessEvent: NodeAccessEvent | null;
  lastGraphUpdateEvent: GraphUpdateEvent | null;
  lastDeltaUpdateEvent: DeltaUpdateEvent | null;
  updateStats: UpdateStats;
}

interface UpdateStats {
  totalUpdates: number;
  deltaUpdates: number;
  cacheInvalidations: number;
  lastUpdateTime: number | null;
}

type StatsAction = 
  | { type: 'INCREMENT_DELTA' }
  | { type: 'INCREMENT_CACHE' }
  | { type: 'INCREMENT_TOTAL' }
  | { type: 'UPDATE_TIME' };

function statsReducer(state: UpdateStats, action: StatsAction): UpdateStats {
  switch (action.type) {
    case 'INCREMENT_DELTA':
      return { ...state, deltaUpdates: state.deltaUpdates + 1, totalUpdates: state.totalUpdates + 1, lastUpdateTime: Date.now() };
    case 'INCREMENT_CACHE':
      return { ...state, cacheInvalidations: state.cacheInvalidations + 1, lastUpdateTime: Date.now() };
    case 'INCREMENT_TOTAL':
      return { ...state, totalUpdates: state.totalUpdates + 1, lastUpdateTime: Date.now() };
    case 'UPDATE_TIME':
      return { ...state, lastUpdateTime: Date.now() };
    default:
      return state;
  }
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
  
  // State for last events only (for UI display)
  const [lastNodeAccessEvent, setLastNodeAccessEvent] = useState<NodeAccessEvent | null>(null);
  const [lastGraphUpdateEvent, setLastGraphUpdateEvent] = useState<GraphUpdateEvent | null>(null);
  const [lastDeltaUpdateEvent, setLastDeltaUpdateEvent] = useState<DeltaUpdateEvent | null>(null);
  
  const [updateStats, dispatchStats] = useReducer(statsReducer, {
    totalUpdates: 0,
    deltaUpdates: 0,
    cacheInvalidations: 0,
    lastUpdateTime: null
  });

  // Use refs for handlers to avoid re-renders on subscription changes
  const handlersRef = useRef<Set<(event: WebSocketEvent) => void>>(new Set());
  const nodeAccessHandlersRef = useRef<Set<(event: NodeAccessEvent) => void>>(new Set());
  const graphUpdateHandlersRef = useRef<Set<(event: GraphUpdateEvent) => void>>(new Set());
  const deltaUpdateHandlersRef = useRef<Set<(event: DeltaUpdateEvent) => void>>(new Set());
  const cacheInvalidateHandlersRef = useRef<Set<(event: CacheInvalidateEvent) => void>>(new Set());
  
  // Log WebSocket URL only once on mount
  useEffect(() => {
    console.log('WebSocketProvider - Environment URL:', import.meta.env.VITE_WEBSOCKET_URL);
    console.log('WebSocketProvider - Using URL:', wsUrl);
  }, []); // Empty deps - log only once
  
  const handleMessage = useCallback((event: WebSocketEvent) => {
    // Handle specific event types
    if (event.type === 'node_access') {
      setLastNodeAccessEvent(event as NodeAccessEvent);
      dispatchStats({ type: 'INCREMENT_TOTAL' });
      nodeAccessHandlersRef.current.forEach(handler => {
        try {
          handler(event as NodeAccessEvent);
        } catch (error) {
          console.error('Error in NodeAccess event handler:', error);
        }
      });
    } else if (event.type === 'graph:update') {
      setLastGraphUpdateEvent(event as GraphUpdateEvent);
      dispatchStats({ type: 'INCREMENT_TOTAL' });
      graphUpdateHandlersRef.current.forEach(handler => {
        try {
          handler(event as GraphUpdateEvent);
        } catch (error) {
          console.error('Error in GraphUpdate event handler:', error);
        }
      });
    } else if (event.type === 'graph:delta') {
      setLastDeltaUpdateEvent(event as DeltaUpdateEvent);
      dispatchStats({ type: 'INCREMENT_DELTA' });
      deltaUpdateHandlersRef.current.forEach(handler => {
        try {
          handler(event as DeltaUpdateEvent);
        } catch (error) {
          console.error('Error in DeltaUpdate event handler:', error);
        }
      });
    } else if (event.type === 'cache:invalidate') {
      dispatchStats({ type: 'INCREMENT_CACHE' });
      cacheInvalidateHandlersRef.current.forEach(handler => {
        try {
          handler(event as CacheInvalidateEvent);
        } catch (error) {
          console.error('Error in CacheInvalidate event handler:', error);
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

  const { isConnected, connectionQuality, latency } = useWebSocket({
    url: wsUrl,
    onMessage: handleMessage,
    onConnect: () => console.log('WebSocket provider connected'),
    onDisconnect: () => console.log('WebSocket provider disconnected'),
    onError: (error) => console.error('WebSocket provider error:', error),
    batchInterval: 100,
    maxBatchSize: 50
  });

  const subscribe = useCallback((handler: (event: WebSocketEvent) => void) => {
    handlersRef.current.add(handler);
    
    // Return unsubscribe function
    return () => {
      handlersRef.current.delete(handler);
    };
  }, []);

  const subscribeToNodeAccess = useCallback((handler: (event: NodeAccessEvent) => void) => {
    nodeAccessHandlersRef.current.add(handler);
    
    // Return unsubscribe function
    return () => {
      nodeAccessHandlersRef.current.delete(handler);
    };
  }, []);

  const subscribeToGraphUpdate = useCallback((handler: (event: GraphUpdateEvent) => void) => {
    graphUpdateHandlersRef.current.add(handler);
    
    // Return unsubscribe function
    return () => {
      graphUpdateHandlersRef.current.delete(handler);
    };
  }, []);
  
  const subscribeToDeltaUpdate = useCallback((handler: (event: DeltaUpdateEvent) => void) => {
    deltaUpdateHandlersRef.current.add(handler);
    
    // Return unsubscribe function
    return () => {
      deltaUpdateHandlersRef.current.delete(handler);
    };
  }, []);
  
  const subscribeToCacheInvalidate = useCallback((handler: (event: CacheInvalidateEvent) => void) => {
    cacheInvalidateHandlersRef.current.add(handler);
    
    // Return unsubscribe function
    return () => {
      cacheInvalidateHandlersRef.current.delete(handler);
    };
  }, []);

  const value: WebSocketContextValue = useMemo(() => ({
    isConnected,
    connectionQuality,
    latency,
    subscribe,
    subscribeToNodeAccess,
    subscribeToGraphUpdate,
    subscribeToDeltaUpdate,
    subscribeToCacheInvalidate,
    lastNodeAccessEvent,
    lastGraphUpdateEvent,
    lastDeltaUpdateEvent,
    updateStats
  }), [
    isConnected,
    connectionQuality,
    latency,
    subscribe,
    subscribeToNodeAccess,
    subscribeToGraphUpdate,
    subscribeToDeltaUpdate,
    subscribeToCacheInvalidate,
    lastNodeAccessEvent,
    lastGraphUpdateEvent,
    lastDeltaUpdateEvent,
    updateStats
  ]);

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
};