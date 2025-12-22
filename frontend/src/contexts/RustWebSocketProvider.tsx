import React, { createContext, useContext, useCallback, useRef, useEffect, useState } from 'react';

// Production-safe logging - only log in development mode
const isDev = import.meta.env.DEV;
const log = isDev ? console.log.bind(console) : () => {};
const logWarn = isDev ? console.warn.bind(console) : () => {};
const logError = console.error.bind(console); // Always log errors

// Import shared types
import { GraphNode, GraphLink } from '../types/graph';

// DeltaUpdate uses the common GraphNode and GraphLink types
// to ensure compatibility with consumers
interface DeltaUpdate {
  type: 'graph:delta' | 'graph:update';
  data: {
    operation: 'add' | 'update' | 'delete';
    nodes?: GraphNode[];
    edges?: GraphLink[];
    timestamp: number;
  };
}

// WebSocket message payload
interface WebSocketMessage {
  type: string;
  [key: string]: unknown;
}

// Raw message types from Rust server
interface RawGraphDeltaMessage {
  type: 'graph:delta';
  data: {
    nodes_added?: GraphNode[];
    edges_added?: GraphLink[];
    nodes_removed?: GraphNode[];
    edges_removed?: GraphLink[];
    timestamp?: number;
  };
}

interface RawGraphUpdateMessage {
  type: 'graph:update';
  data: {
    nodes?: GraphNode[];
    edges?: GraphLink[];
    timestamp?: number;
  };
}

type RawServerMessage = RawGraphDeltaMessage | RawGraphUpdateMessage | { type: string; [key: string]: unknown };

// Debug info stored on window
interface RustWebSocketDebug {
  isConnected: boolean;
  url?: string;
  readyState?: number;
  reconnectCount?: number;
  lastError?: { error: unknown; timestamp: string; url: string };
  lastClose?: { code: number; reason: string; wasClean: boolean; timestamp: string };
}

declare global {
  interface Window {
    rustWebSocket?: RustWebSocketDebug;
  }
}

interface RustWebSocketContextType {
  isConnected: boolean;
  subscribe: (callback: (update: DeltaUpdate) => void) => () => void;
  sendMessage: (message: WebSocketMessage) => void;
}

const RustWebSocketContext = createContext<RustWebSocketContextType | null>(null);

export function RustWebSocketProvider({ children }: { children: React.ReactNode }) {
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const subscribersRef = useRef<Set<(update: DeltaUpdate) => void>>(new Set());
  const reconnectCountRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const isConnectingRef = useRef(false);
  const pingIntervalRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const connectionIdRef = useRef(0);
  
  const reconnectAttempts = 5;
  const reconnectDelay = 1000;
  const isIntentionalCloseRef = useRef(false);
  const PING_INTERVAL = 30000; // Send ping every 30 seconds

  const connect = useCallback(() => {
    // Prevent duplicate connections
    if (isConnectingRef.current || wsRef.current?.readyState === WebSocket.CONNECTING || wsRef.current?.readyState === WebSocket.OPEN) {
      log('[RustWebSocketProvider] Already connected or connecting, skipping. readyState:', wsRef.current?.readyState);
      return;
    }
    
    const connId = ++connectionIdRef.current;
    log(`[RustWebSocketProvider] Starting new connection attempt #${connId}`);
    isConnectingRef.current = true;
    isIntentionalCloseRef.current = false; // Reset the intentional close flag
    
    // Use environment variable for Rust WebSocket URL, with fallbacks
    let rustWsUrl: string;
    
    // Check for environment variable first and replace localhost with current hostname if needed
    if (import.meta.env.VITE_RUST_WS_URL) {
      rustWsUrl = import.meta.env.VITE_RUST_WS_URL;
      // If we're not on localhost but the URL points to localhost, update it
      if (typeof window !== 'undefined') {
        const currentHost = window.location.hostname;
        if (currentHost !== 'localhost' && currentHost !== '127.0.0.1' && rustWsUrl.includes('localhost')) {
          rustWsUrl = rustWsUrl.replace('localhost', currentHost);
        }
      }
    }
    // If we're accessing from a browser in production, use the nginx proxy path
    else if (typeof window !== 'undefined' && import.meta.env.PROD) {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host; // includes port
      rustWsUrl = `${protocol}//${host}/rust-ws`;
    }
    // For development, connect directly to Rust server (default port 3000)
    else if (typeof window !== 'undefined') {
      const currentHost = window.location.hostname;
      const defaultPort = import.meta.env.VITE_RUST_WS_PORT || '3000';
      // If accessing from network IP, update the WebSocket URL
      if (currentHost !== 'localhost' && currentHost !== '127.0.0.1') {
        rustWsUrl = `ws://${currentHost}:${defaultPort}/ws`;
      } else {
        rustWsUrl = `ws://localhost:${defaultPort}/ws`;
      }
    } else {
      // Fallback
      rustWsUrl = 'ws://localhost:3000/ws';
    }
    
    log(`[RustWebSocketProvider #${connId}] Connecting to Rust server:`, rustWsUrl);
    
    try {
      const ws = new WebSocket(rustWsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        log(`[RustWebSocketProvider #${connId}] Connected to Rust server at ${rustWsUrl}`);
        log(`[RustWebSocketProvider #${connId}] Connection stats: attempts=${reconnectCountRef.current + 1}, readyState=${ws.readyState}`);
        isConnectingRef.current = false;
        setIsConnected(true);
        reconnectCountRef.current = 0;
        
        // Make connection status available globally for debugging
        if (typeof window !== 'undefined') {
          window.rustWebSocket = {
            isConnected: true,
            url: rustWsUrl,
            readyState: ws.readyState,
            reconnectCount: reconnectCountRef.current
          };
        }
        
        // Subscribe to delta updates for real-time incremental changes
        try {
          const subscribeMessage = JSON.stringify({
            type: 'subscribe:deltas'
          });
          ws.send(subscribeMessage);
          log('[RustWebSocketProvider] Sent subscribe:deltas message');
        } catch (error) {
          logError('[RustWebSocketProvider] Failed to send subscribe message:', error);
        }
        
        // Start heartbeat to keep connection alive
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
        }
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            try {
              ws.send(JSON.stringify({ type: 'ping' }));
              log('[RustWebSocketProvider] Sent ping');
            } catch (error) {
              logError('[RustWebSocketProvider] Failed to send ping:', error);
            }
          }
        }, PING_INTERVAL);
        
        log('[RustWebSocketProvider] Connected, subscribed to delta updates, heartbeat started');
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as RawServerMessage;
          // Handle subscription confirmation
          if (message.type === 'subscribed:deltas') {
            log('[RustWebSocketProvider] Delta subscription confirmed');
          }
          
          // Handle pong response - no logging needed for pong
          else if (message.type === 'pong') {
            // Silent pong handling
          }
          
          // Handle both graph:delta and graph:update message types
          else if (message.type === 'graph:delta' || message.type === 'graph:update') {
            // Handle GraphDelta format from Rust server
            if (message.type === 'graph:delta') {
              const deltaMsg = message as RawGraphDeltaMessage;
              const data = deltaMsg.data;
              
              // Send added nodes/edges - THIS IS THE IMPORTANT ONE FOR REAL-TIME
              if ((data.nodes_added?.length ?? 0) > 0 || (data.edges_added?.length ?? 0) > 0) {
                const addMessage: DeltaUpdate = {
                  type: 'graph:delta' as const,
                  data: {
                    operation: 'add' as const,
                    nodes: data.nodes_added || [],
                    edges: data.edges_added || [],
                    timestamp: data.timestamp || Date.now()
                  }
                };
                subscribersRef.current.forEach(callback => callback(addMessage));
              }
              
              // Skip node/edge updates - not needed for real-time sync
              // We only care about new nodes/edges being added
              
              // Send removed nodes/edges
              if ((data.nodes_removed?.length ?? 0) > 0 || (data.edges_removed?.length ?? 0) > 0) {
                const deleteMessage: DeltaUpdate = {
                  type: 'graph:delta' as const,
                  data: {
                    operation: 'delete' as const,
                    nodes: data.nodes_removed || [],
                    edges: data.edges_removed || [],
                    timestamp: data.timestamp || Date.now()
                  }
                };
                subscribersRef.current.forEach(callback => callback(deleteMessage));
              }
            }
            // Handle GraphUpdate format (fallback)
            else if (message.type === 'graph:update') {
              const updateMsg = message as RawGraphUpdateMessage;
              const deltaMessage: DeltaUpdate = {
                type: 'graph:delta' as const,
                data: {
                  operation: 'update' as const,
                  nodes: updateMsg.data.nodes || [],
                  edges: updateMsg.data.edges || [],
                  timestamp: updateMsg.data.timestamp || Date.now()
                }
              };
              subscribersRef.current.forEach(callback => callback(deltaMessage));
            }
          }
        } catch (error) {
          logError('[RustWebSocketProvider] Error parsing message:', error);
        }
      };

      ws.onerror = (error) => {
        logError(`[RustWebSocketProvider #${connId}] WebSocket error:`, error);
        isConnectingRef.current = false;
        
        // Update global debug info
        if (typeof window !== 'undefined') {
          window.rustWebSocket = {
            ...(window.rustWebSocket || { isConnected: false }),
            lastError: { error, timestamp: new Date().toISOString(), url: rustWsUrl },
            isConnected: false
          };
        }
      };

      ws.onclose = (event) => {
        log(`[RustWebSocketProvider #${connId}] Connection closed: code=${event.code}`);
        wsRef.current = null;
        isConnectingRef.current = false;
        setIsConnected(false);
        
        // Update global debug info
        if (typeof window !== 'undefined') {
          window.rustWebSocket = {
            ...(window.rustWebSocket || { isConnected: false }),
            isConnected: false,
            lastClose: { 
              code: event.code, 
              reason: event.reason, 
              wasClean: event.wasClean,
              timestamp: new Date().toISOString()
            }
          };
        }
        
        // Clear ping interval
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
          pingIntervalRef.current = undefined;
        }
        
        // Only attempt reconnection if this wasn't an intentional close
        if (!isIntentionalCloseRef.current && reconnectCountRef.current < reconnectAttempts) {
          reconnectCountRef.current++;
          log(`[RustWebSocketProvider] Reconnecting... (${reconnectCountRef.current}/${reconnectAttempts})`);
          
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, reconnectDelay * Math.pow(2, reconnectCountRef.current - 1)); // Exponential backoff
        }
      };
    } catch (error) {
      logError('[RustWebSocketProvider] Failed to create WebSocket:', error);
      isConnectingRef.current = false;
    }
  }, []);

  useEffect(() => {
    // Connect to Rust WebSocket server
    connect();

    return () => {
      // Mark this as an intentional close to prevent reconnection
      isIntentionalCloseRef.current = true;
      
      // Clean up all subscriptions
      subscribersRef.current.clear();
      
      // Clear reconnect timeout
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      
      // Clear ping interval
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = undefined;
      }
      
      // Close WebSocket connection
      if (wsRef.current) {
        // Disable auto-reconnect by clearing onclose handler before closing
        wsRef.current.onclose = null;
        wsRef.current.onopen = null;
        wsRef.current.onmessage = null;
        wsRef.current.onerror = null;
        if (wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.close();
        }
        wsRef.current = null;
      }
      
      // Reset connection state
      isConnectingRef.current = false;
      setIsConnected(false);
    };
  }, []); // Remove connect dependency to prevent re-renders

  const subscribe = useCallback((callback: (update: DeltaUpdate) => void) => {
    subscribersRef.current.add(callback);
    return () => {
      subscribersRef.current.delete(callback);
    };
  }, []);

  const sendMessage = useCallback((message: WebSocketMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    } else {
      logWarn('[RustWebSocketProvider] WebSocket not connected');
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