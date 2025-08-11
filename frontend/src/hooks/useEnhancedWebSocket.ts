import { useEffect, useRef, useState, useCallback } from 'react';

// Connection health monitoring
interface ConnectionHealth {
  isHealthy: boolean;
  latency: number;
  lastPongTime: number;
  reconnectAttempts: number;
  connectionQuality: 'excellent' | 'good' | 'fair' | 'poor' | 'offline';
}

// Enhanced connection options
interface ConnectionOptions {
  heartbeatInterval?: number;
  heartbeatTimeout?: number;
  maxReconnectAttempts?: number;
  reconnectStrategy?: 'exponential' | 'linear' | 'fibonacci';
  connectionPoolSize?: number;
  loadBalancingStrategy?: 'round-robin' | 'least-connections' | 'random';
  enableCompression?: boolean;
  enableBinaryFrames?: boolean;
}

// WebSocket message with metadata
interface EnhancedMessage {
  id: string;
  type: string;
  data: any;
  timestamp: number;
  version?: string;
  compression?: 'gzip' | 'deflate' | 'none';
  priority?: number;
  batch_id?: string;
}

// Connection state machine
enum ConnectionState {
  IDLE = 'idle',
  CONNECTING = 'connecting',
  CONNECTED = 'connected',
  RECONNECTING = 'reconnecting',
  DISCONNECTED = 'disconnected',
  FAILED = 'failed'
}

// Enhanced WebSocket connection class
class EnhancedWebSocketConnection {
  private socket: WebSocket | null = null;
  private heartbeatInterval: number | null = null;
  private healthCheckInterval: number | null = null;
  private lastPongTime = Date.now();
  private connectionId: string;
  private messageQueue: EnhancedMessage[] = [];
  private isProcessingQueue = false;
  
  constructor(
    private url: string,
    private options: ConnectionOptions,
    private onMessage: (message: EnhancedMessage) => void,
    private onStateChange: (state: ConnectionState) => void,
    private onHealthChange: (health: ConnectionHealth) => void
  ) {
    this.connectionId = `conn-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.onStateChange(ConnectionState.CONNECTING);
        this.socket = new WebSocket(this.url);
        
        // Enable binary frames if requested
        if (this.options.enableBinaryFrames) {
          this.socket.binaryType = 'arraybuffer';
        }

        this.socket.onopen = () => {
          console.log(`[${this.connectionId}] WebSocket connected`);
          this.onStateChange(ConnectionState.CONNECTED);
          this.startHeartbeat();
          this.startHealthMonitoring();
          this.processQueuedMessages();
          resolve();
        };

        this.socket.onmessage = async (event) => {
          try {
            let message: EnhancedMessage;
            
            // Handle binary frames
            if (event.data instanceof ArrayBuffer) {
              message = await this.decodeBinaryMessage(event.data);
            } else {
              message = JSON.parse(event.data);
            }

            // Handle heartbeat
            if (message.type === 'pong') {
              this.lastPongTime = Date.now();
              return;
            }

            // Add metadata if not present
            if (!message.id) {
              message.id = `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
            }
            if (!message.timestamp) {
              message.timestamp = Date.now();
            }

            this.onMessage(message);
          } catch (error) {
            console.error(`[${this.connectionId}] Error processing message:`, error);
          }
        };

        this.socket.onerror = (error) => {
          console.error(`[${this.connectionId}] WebSocket error:`, error);
          reject(error);
        };

        this.socket.onclose = () => {
          console.log(`[${this.connectionId}] WebSocket closed`);
          this.stopHeartbeat();
          this.stopHealthMonitoring();
          this.onStateChange(ConnectionState.DISCONNECTED);
        };

      } catch (error) {
        this.onStateChange(ConnectionState.FAILED);
        reject(error);
      }
    });
  }

  private async decodeBinaryMessage(data: ArrayBuffer): Promise<EnhancedMessage> {
    // Simple binary frame decoding (can be enhanced with protobuf/msgpack)
    const decoder = new TextDecoder();
    const text = decoder.decode(data);
    return JSON.parse(text);
  }

  private startHeartbeat(): void {
    const interval = this.options.heartbeatInterval || 30000;
    
    this.heartbeatInterval = window.setInterval(() => {
      if (this.isConnected()) {
        this.send({ type: 'ping', data: null });
        
        // Check for timeout
        setTimeout(() => {
          const timeSinceLastPong = Date.now() - this.lastPongTime;
          if (timeSinceLastPong > (this.options.heartbeatTimeout || 60000)) {
            console.warn(`[${this.connectionId}] Heartbeat timeout`);
            this.socket?.close();
          }
        }, this.options.heartbeatTimeout || 60000);
      }
    }, interval);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  private startHealthMonitoring(): void {
    this.healthCheckInterval = window.setInterval(() => {
      const health = this.getHealth();
      this.onHealthChange(health);
    }, 5000); // Check health every 5 seconds
  }

  private stopHealthMonitoring(): void {
    if (this.healthCheckInterval) {
      clearInterval(this.healthCheckInterval);
      this.healthCheckInterval = null;
    }
  }

  private processQueuedMessages(): void {
    if (this.isProcessingQueue || this.messageQueue.length === 0) return;
    
    this.isProcessingQueue = true;
    
    while (this.messageQueue.length > 0 && this.isConnected()) {
      const message = this.messageQueue.shift();
      if (message) {
        this.sendDirect(message);
      }
    }
    
    this.isProcessingQueue = false;
  }

  send(message: Partial<EnhancedMessage>): void {
    const enhancedMessage: EnhancedMessage = {
      id: message.id || `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      type: message.type || 'data',
      data: message.data,
      timestamp: message.timestamp || Date.now(),
      version: message.version,
      priority: message.priority || 0,
      ...message
    };

    if (this.isConnected()) {
      this.sendDirect(enhancedMessage);
    } else {
      // Queue message for later delivery
      this.messageQueue.push(enhancedMessage);
      console.log(`[${this.connectionId}] Message queued (queue size: ${this.messageQueue.length})`);
    }
  }

  private sendDirect(message: EnhancedMessage): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return;
    
    try {
      if (this.options.enableBinaryFrames && message.data instanceof ArrayBuffer) {
        this.socket.send(message.data);
      } else {
        this.socket.send(JSON.stringify(message));
      }
    } catch (error) {
      console.error(`[${this.connectionId}] Error sending message:`, error);
      // Re-queue the message
      this.messageQueue.unshift(message);
    }
  }

  isConnected(): boolean {
    return this.socket?.readyState === WebSocket.OPEN;
  }

  getHealth(): ConnectionHealth {
    const latency = Date.now() - this.lastPongTime;
    const isHealthy = this.isConnected() && latency < (this.options.heartbeatTimeout || 60000);
    
    let connectionQuality: ConnectionHealth['connectionQuality'];
    if (!this.isConnected()) {
      connectionQuality = 'offline';
    } else if (latency < 50) {
      connectionQuality = 'excellent';
    } else if (latency < 150) {
      connectionQuality = 'good';
    } else if (latency < 300) {
      connectionQuality = 'fair';
    } else {
      connectionQuality = 'poor';
    }

    return {
      isHealthy,
      latency,
      lastPongTime: this.lastPongTime,
      reconnectAttempts: 0, // Will be managed by ConnectionManager
      connectionQuality
    };
  }

  async close(): Promise<void> {
    this.stopHeartbeat();
    this.stopHealthMonitoring();
    
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    
    this.onStateChange(ConnectionState.DISCONNECTED);
  }

  getConnectionId(): string {
    return this.connectionId;
  }

  getQueueSize(): number {
    return this.messageQueue.length;
  }
}

// Connection pool manager
class ConnectionPoolManager {
  private connections = new Map<string, EnhancedWebSocketConnection>();
  private currentIndex = 0;
  
  constructor(
    private urls: string[],
    private poolSize: number,
    private options: ConnectionOptions,
    private onMessage: (message: EnhancedMessage) => void,
    private onHealthChange: (connectionId: string, health: ConnectionHealth) => void
  ) {}

  async initialize(): Promise<void> {
    const connectionPromises: Promise<void>[] = [];
    
    for (let i = 0; i < Math.min(this.poolSize, this.urls.length); i++) {
      const url = this.urls[i % this.urls.length];
      const connection = new EnhancedWebSocketConnection(
        url,
        this.options,
        this.onMessage,
        (state) => this.handleStateChange(connection.getConnectionId(), state),
        (health) => this.onHealthChange(connection.getConnectionId(), health)
      );
      
      this.connections.set(connection.getConnectionId(), connection);
      connectionPromises.push(connection.connect());
    }
    
    await Promise.allSettled(connectionPromises);
  }

  private handleStateChange(connectionId: string, state: ConnectionState): void {
    console.log(`[Pool] Connection ${connectionId} state: ${state}`);
    
    if (state === ConnectionState.FAILED || state === ConnectionState.DISCONNECTED) {
      // Attempt to replace failed connection
      this.replaceConnection(connectionId);
    }
  }

  private async replaceConnection(oldConnectionId: string): Promise<void> {
    const oldConnection = this.connections.get(oldConnectionId);
    if (!oldConnection) return;
    
    this.connections.delete(oldConnectionId);
    
    // Create new connection with same URL
    const url = this.urls[this.connections.size % this.urls.length];
    const newConnection = new EnhancedWebSocketConnection(
      url,
      this.options,
      this.onMessage,
      (state) => this.handleStateChange(newConnection.getConnectionId(), state),
      (health) => this.onHealthChange(newConnection.getConnectionId(), health)
    );
    
    this.connections.set(newConnection.getConnectionId(), newConnection);
    
    try {
      await newConnection.connect();
    } catch (error) {
      console.error('[Pool] Failed to replace connection:', error);
    }
  }

  getConnection(strategy: string = 'round-robin'): EnhancedWebSocketConnection | null {
    const activeConnections = Array.from(this.connections.values()).filter(c => c.isConnected());
    
    if (activeConnections.length === 0) return null;
    
    switch (strategy) {
      case 'round-robin':
        const connection = activeConnections[this.currentIndex % activeConnections.length];
        this.currentIndex++;
        return connection;
        
      case 'least-connections':
        // Sort by queue size (least loaded first)
        return activeConnections.sort((a, b) => a.getQueueSize() - b.getQueueSize())[0];
        
      case 'random':
        return activeConnections[Math.floor(Math.random() * activeConnections.length)];
        
      default:
        return activeConnections[0];
    }
  }

  async closeAll(): Promise<void> {
    const closePromises = Array.from(this.connections.values()).map(c => c.close());
    await Promise.all(closePromises);
    this.connections.clear();
  }

  getHealthStatus(): Map<string, ConnectionHealth> {
    const status = new Map<string, ConnectionHealth>();
    
    for (const [id, connection] of this.connections) {
      status.set(id, connection.getHealth());
    }
    
    return status;
  }
}

// Main hook with enhanced features
export function useEnhancedWebSocket(
  urls: string | string[],
  options: ConnectionOptions = {}
) {
  const [connectionState, setConnectionState] = useState<ConnectionState>(ConnectionState.IDLE);
  const [healthStatus, setHealthStatus] = useState<Map<string, ConnectionHealth>>(new Map());
  const [messageHandlers] = useState(() => new Set<(message: EnhancedMessage) => void>());
  
  const poolManagerRef = useRef<ConnectionPoolManager | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const urlArray = Array.isArray(urls) ? urls : [urls];
  const poolSize = options.connectionPoolSize || 1;

  const handleMessage = useCallback((message: EnhancedMessage) => {
    messageHandlers.forEach(handler => {
      try {
        handler(message);
      } catch (error) {
        console.error('Error in message handler:', error);
      }
    });
  }, [messageHandlers]);

  const handleHealthChange = useCallback((connectionId: string, health: ConnectionHealth) => {
    setHealthStatus(prev => {
      const newStatus = new Map(prev);
      newStatus.set(connectionId, health);
      return newStatus;
    });
  }, []);

  const connect = useCallback(async () => {
    if (poolManagerRef.current) {
      await poolManagerRef.current.closeAll();
    }

    poolManagerRef.current = new ConnectionPoolManager(
      urlArray,
      poolSize,
      options,
      handleMessage,
      handleHealthChange
    );

    setConnectionState(ConnectionState.CONNECTING);
    
    try {
      await poolManagerRef.current.initialize();
      setConnectionState(ConnectionState.CONNECTED);
      reconnectAttemptsRef.current = 0;
    } catch (error) {
      console.error('Failed to connect:', error);
      setConnectionState(ConnectionState.FAILED);
      scheduleReconnect();
    }
  }, [urlArray, poolSize, options, handleMessage, handleHealthChange]);

  const scheduleReconnect = useCallback(() => {
    if (reconnectAttemptsRef.current >= (options.maxReconnectAttempts || 10)) {
      console.error('Max reconnection attempts reached');
      setConnectionState(ConnectionState.FAILED);
      return;
    }

    const strategy = options.reconnectStrategy || 'exponential';
    let delay: number;

    switch (strategy) {
      case 'exponential':
        delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000);
        break;
      case 'linear':
        delay = 1000 * (reconnectAttemptsRef.current + 1);
        break;
      case 'fibonacci':
        const fib = (n: number): number => n <= 1 ? n : fib(n - 1) + fib(n - 2);
        delay = Math.min(1000 * fib(reconnectAttemptsRef.current + 1), 30000);
        break;
      default:
        delay = 3000;
    }

    console.log(`Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current + 1})`);
    setConnectionState(ConnectionState.RECONNECTING);

    reconnectTimeoutRef.current = setTimeout(() => {
      reconnectAttemptsRef.current++;
      connect();
    }, delay);
  }, [options, connect]);

  const disconnect = useCallback(async () => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (poolManagerRef.current) {
      await poolManagerRef.current.closeAll();
      poolManagerRef.current = null;
    }

    setConnectionState(ConnectionState.DISCONNECTED);
    reconnectAttemptsRef.current = 0;
  }, []);

  const send = useCallback((message: Partial<EnhancedMessage>) => {
    if (!poolManagerRef.current) {
      console.warn('No connection pool available');
      return;
    }

    const connection = poolManagerRef.current.getConnection(options.loadBalancingStrategy);
    if (connection) {
      connection.send(message);
    } else {
      console.warn('No active connections available');
    }
  }, [options.loadBalancingStrategy]);

  const subscribe = useCallback((handler: (message: EnhancedMessage) => void) => {
    messageHandlers.add(handler);
    
    return () => {
      messageHandlers.delete(handler);
    };
  }, [messageHandlers]);

  // Auto-connect on mount
  useEffect(() => {
    connect();
    
    return () => {
      disconnect();
    };
  }, []); // Only run once on mount

  // Calculate aggregate health metrics
  const aggregateHealth = Array.from(healthStatus.values()).reduce((acc, health) => {
    return {
      avgLatency: acc.avgLatency + health.latency / healthStatus.size,
      healthyConnections: acc.healthyConnections + (health.isHealthy ? 1 : 0),
      totalConnections: healthStatus.size
    };
  }, { avgLatency: 0, healthyConnections: 0, totalConnections: 0 });

  return {
    connectionState,
    healthStatus,
    aggregateHealth,
    send,
    subscribe,
    reconnect: connect,
    disconnect
  };
}