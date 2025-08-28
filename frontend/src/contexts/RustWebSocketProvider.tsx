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
  const pingIntervalRef = useRef<NodeJS.Timeout>();
  const connectionIdRef = useRef(0);
  
  const reconnectAttempts = 5;
  const reconnectDelay = 1000;
  const isIntentionalCloseRef = useRef(false);
  const PING_INTERVAL = 30000; // Send ping every 30 seconds

  const connect = useCallback(() => {
    // Prevent duplicate connections
    if (isConnectingRef.current || wsRef.current?.readyState === WebSocket.CONNECTING || wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[RustWebSocketProvider] Already connected or connecting, skipping. readyState:', wsRef.current?.readyState);
      return;
    }
    
    const connId = ++connectionIdRef.current;
    console.log(`[RustWebSocketProvider] Starting new connection attempt #${connId}`);
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
    
    console.log(`[RustWebSocketProvider #${connId}] Connecting to Rust server:`, rustWsUrl);
    
    try {
      const ws = new WebSocket(rustWsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log(`[RustWebSocketProvider #${connId}] ✅ Connected to Rust server at ${rustWsUrl}`);
        console.log(`[RustWebSocketProvider #${connId}] Connection stats: attempts=${reconnectCountRef.current + 1}, readyState=${ws.readyState}`);
        isConnectingRef.current = false;
        setIsConnected(true);
        reconnectCountRef.current = 0;
        
        // Make connection status available globally for debugging
        if (typeof window !== 'undefined') {
          (window as any).rustWebSocket = {
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
          console.log('[RustWebSocketProvider] Sent subscribe:deltas message');
        } catch (error) {
          console.error('[RustWebSocketProvider] Failed to send subscribe message:', error);
        }
        
        // Start heartbeat to keep connection alive
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
        }
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            try {
              ws.send(JSON.stringify({ type: 'ping' }));
              console.log('[RustWebSocketProvider] Sent ping');
            } catch (error) {
              console.error('[RustWebSocketProvider] Failed to send ping:', error);
            }
          }
        }, PING_INTERVAL);
        
        console.log('[RustWebSocketProvider] Connected, subscribed to delta updates, heartbeat started');
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          console.log(`[RustWebSocketProvider #${connId}] Message received:`, message.type, message);
          
          // Handle subscription confirmation
          if (message.type === 'subscribed:deltas') {
            console.log('[RustWebSocketProvider] Delta subscription confirmed');
          }
          
          // Handle pong response
          else if (message.type === 'pong') {
            console.log('[RustWebSocketProvider] Pong received');
          }
          
          // Handle both graph:delta and graph:update message types
          else if (message.type === 'graph:delta' || message.type === 'graph:update') {
            console.log('[RustWebSocketProvider] Delta/Update data:', message);
            
            // Handle GraphDelta format from Rust server
            if (message.type === 'graph:delta' && message.data) {
              const data = message.data;
              
              console.log('[RustWebSocketProvider] Processing delta:', {
                nodes_added: data.nodes_added?.length || 0,
                nodes_updated: data.nodes_updated?.length || 0,
                nodes_removed: data.nodes_removed?.length || 0,
                edges_added: data.edges_added?.length || 0,
                edges_updated: data.edges_updated?.length || 0,
                edges_removed: data.edges_removed?.length || 0
              });
              
              // Send added nodes/edges - THIS IS THE IMPORTANT ONE FOR REAL-TIME
              if ((data.nodes_added?.length > 0) || (data.edges_added?.length > 0)) {
                const addMessage = {
                  type: 'graph:delta',
                  data: {
                    operation: 'add' as const,
                    nodes: data.nodes_added || [],
                    edges: data.edges_added || [],
                    timestamp: data.timestamp || Date.now()
                  }
                };
                console.log('[RustWebSocketProvider] Sending ADD message:', {
                  nodes: addMessage.data.nodes.length,
                  edges: addMessage.data.edges.length
                });
                subscribersRef.current.forEach(callback => callback(addMessage));
              }
              
              // Skip node updates - not needed for real-time sync
              // We only care about new nodes/edges being added
              if (data.nodes_updated?.length > 0) {
                console.log('[RustWebSocketProvider] Skipping node updates:', data.nodes_updated.length);
              }
              
              // Skip edge updates too - they're causing issues
              if (data.edges_updated?.length > 0) {
                console.log('[RustWebSocketProvider] Skipping edge updates:', data.edges_updated.length);
              }
              
              // Send removed nodes/edges
              if ((data.nodes_removed?.length > 0) || (data.edges_removed?.length > 0)) {
                const deleteMessage = {
                  type: 'graph:delta',
                  data: {
                    operation: 'delete' as const,
                    nodes: data.nodes_removed || [],
                    edges: data.edges_removed || [],
                    timestamp: data.timestamp || Date.now()
                  }
                };
                console.log('[RustWebSocketProvider] Sending DELETE message:', {
                  nodes: deleteMessage.data.nodes.length,
                  edges: deleteMessage.data.edges.length
                });
                subscribersRef.current.forEach(callback => callback(deleteMessage));
              }
            }
            // Handle GraphUpdate format (fallback)
            else if (message.type === 'graph:update' && message.data) {
              const deltaMessage = {
                type: 'graph:delta' as const,
                data: {
                  operation: 'update' as const,
                  nodes: message.data.nodes || [],
                  edges: message.data.edges || [],
                  timestamp: message.data.timestamp || Date.now()
                }
              };
              subscribersRef.current.forEach(callback => callback(deltaMessage));
            }
          }
        } catch (error) {
          console.error('[RustWebSocketProvider] Error parsing message:', error);
        }
      };

      ws.onerror = (error) => {
        console.error(`[RustWebSocketProvider #${connId}] ❌ WebSocket error:`, {
          error,
          url: rustWsUrl,
          readyState: ws.readyState,
          reconnectCount: reconnectCountRef.current
        });
        isConnectingRef.current = false;
        
        // Update global debug info
        if (typeof window !== 'undefined') {
          (window as any).rustWebSocket = {
            ...((window as any).rustWebSocket || {}),
            lastError: { error, timestamp: new Date().toISOString(), url: rustWsUrl },
            isConnected: false
          };
        }
      };

      ws.onclose = (event) => {
        console.log(`[RustWebSocketProvider #${connId}] ⚪ Connection closed:`, {
          code: event.code,
          reason: event.reason || 'No reason provided',
          wasClean: event.wasClean,
          intentional: isIntentionalCloseRef.current,
          url: rustWsUrl,
          reconnectCount: reconnectCountRef.current
        });
        wsRef.current = null;
        isConnectingRef.current = false;
        setIsConnected(false);
        
        // Update global debug info
        if (typeof window !== 'undefined') {
          (window as any).rustWebSocket = {
            ...((window as any).rustWebSocket || {}),
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