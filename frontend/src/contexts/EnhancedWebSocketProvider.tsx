import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import { useEnhancedWebSocket, ConnectionState } from '../hooks/useEnhancedWebSocket';
import { OfflineQueueManager } from '../services/offlineQueueManager';
import { ConflictResolver, GraphDelta, Resolution } from '../services/conflictResolution';
import { UpdateBatcher, DeltaCompressor, BatchingOptions } from '../services/deltaCompression';
import { MessageDeduplicator, OrderedMessage } from '../services/messageDeduplication';

// Context types
interface EnhancedWebSocketContextValue {
  connectionState: ConnectionState;
  connectionHealth: {
    avgLatency: number;
    healthyConnections: number;
    totalConnections: number;
  };
  queueStatus: {
    queueSize: number;
    isSyncing: boolean;
  };
  stats: {
    messagesReceived: number;
    duplicatesDetected: number;
    conflictsResolved: number;
    compressionRatio: number;
  };
  send: (message: any) => void;
  subscribe: (handler: (message: any) => void) => () => void;
  forceSync: () => Promise<void>;
  clearQueue: () => Promise<void>;
  getDetailedStats: () => any;
}

const EnhancedWebSocketContext = createContext<EnhancedWebSocketContextValue | null>(null);

export const useEnhancedWebSocketContext = () => {
  const context = useContext(EnhancedWebSocketContext);
  if (!context) {
    throw new Error('useEnhancedWebSocketContext must be used within EnhancedWebSocketProvider');
  }
  return context;
};

interface EnhancedWebSocketProviderProps {
  children: React.ReactNode;
  urls?: string | string[];
  options?: {
    enableOfflineQueue?: boolean;
    enableConflictResolution?: boolean;
    enableCompression?: boolean;
    enableDeduplication?: boolean;
    batchingOptions?: Partial<BatchingOptions>;
    connectionPoolSize?: number;
  };
}

export const EnhancedWebSocketProvider: React.FC<EnhancedWebSocketProviderProps> = ({
  children,
  urls,
  options = {}
}) => {
  // Configuration
  const {
    enableOfflineQueue = true,
    enableConflictResolution = true,
    enableCompression = true,
    enableDeduplication = true,
    batchingOptions = {},
    connectionPoolSize = 3
  } = options;

  // State
  const [queueStatus, setQueueStatus] = useState({ queueSize: 0, isSyncing: false });
  const [stats, setStats] = useState({
    messagesReceived: 0,
    duplicatesDetected: 0,
    conflictsResolved: 0,
    compressionRatio: 1.0
  });

  // Refs for services
  const offlineQueueRef = useRef<OfflineQueueManager | null>(null);
  const conflictResolverRef = useRef<ConflictResolver | null>(null);
  const updateBatcherRef = useRef<UpdateBatcher | null>(null);
  const deltaCompressorRef = useRef<DeltaCompressor | null>(null);
  const messageDeduplicatorRef = useRef<MessageDeduplicator | null>(null);
  const subscribersRef = useRef<Set<(message: any) => void>>(new Set());

  // Determine WebSocket URLs
  const wsUrls = React.useMemo(() => {
    if (urls) {
      return urls;
    }
    
    const envUrl = import.meta.env.VITE_WEBSOCKET_URL;
    if (envUrl) {
      return envUrl;
    }
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/ws`;
  }, [urls]);

  // Handle ordered messages after deduplication
  const handleOrderedMessage = useCallback((message: OrderedMessage) => {
    setStats(prev => ({
      ...prev,
      messagesReceived: prev.messagesReceived + 1
    }));

    // Notify all subscribers
    subscribersRef.current.forEach(handler => {
      try {
        handler(message.data);
      } catch (error) {
        console.error('[EnhancedWebSocket] Error in message handler:', error);
      }
    });
  }, []);

  // Handle gap detection
  const handleGapDetected = useCallback((sourceId: string, missingSequences: number[]) => {
    console.log(`[EnhancedWebSocket] Gap detected from ${sourceId}:`, missingSequences);
    
    // Could request retransmission here
    // send({ type: 'retransmit', sequences: missingSequences });
  }, []);

  // Handle message acknowledgements
  const handleAcknowledgement = useCallback((messageId: string) => {
    // Send acknowledgement to server
    console.log(`[EnhancedWebSocket] Acknowledging message ${messageId}`);
  }, []);

  // Initialize message deduplicator
  useEffect(() => {
    if (enableDeduplication) {
      messageDeduplicatorRef.current = new MessageDeduplicator(
        handleOrderedMessage,
        handleGapDetected,
        handleAcknowledgement
      );
    }

    return () => {
      messageDeduplicatorRef.current?.clear();
    };
  }, [enableDeduplication]);

  // Handle incoming WebSocket messages
  const handleWebSocketMessage = useCallback((message: any) => {
    // Process through deduplication first
    if (messageDeduplicatorRef.current) {
      const processed = messageDeduplicatorRef.current.processMessage({
        id: message.id,
        sequenceNumber: message.sequence,
        timestamp: message.timestamp || Date.now(),
        type: message.type,
        data: message,
        sourceId: message.sourceId || 'server',
        hash: message.hash
      });

      if (!processed) {
        setStats(prev => ({
          ...prev,
          duplicatesDetected: prev.duplicatesDetected + 1
        }));
        return; // Duplicate detected
      }
    } else {
      // No deduplication, process directly
      handleOrderedMessage({
        id: message.id || `msg-${Date.now()}`,
        sequenceNumber: 0,
        timestamp: Date.now(),
        type: message.type,
        data: message,
        hash: '',
        sourceId: 'server'
      });
    }
  }, [handleOrderedMessage]);

  // Initialize WebSocket connection
  const {
    connectionState,
    aggregateHealth,
    send: wsSend,
    subscribe: wsSubscribe
  } = useEnhancedWebSocket(wsUrls, {
    connectionPoolSize,
    heartbeatInterval: 30000,
    heartbeatTimeout: 60000,
    maxReconnectAttempts: 10,
    reconnectStrategy: 'exponential',
    enableCompression: enableCompression,
    enableBinaryFrames: false
  });

  // Subscribe to WebSocket messages
  useEffect(() => {
    const unsubscribe = wsSubscribe(handleWebSocketMessage);
    return unsubscribe;
  }, [wsSubscribe, handleWebSocketMessage]);

  // Initialize conflict resolver
  useEffect(() => {
    if (enableConflictResolution) {
      conflictResolverRef.current = new ConflictResolver(
        `client-${Date.now()}`,
        'operational-transform'
      );
    }
  }, [enableConflictResolution]);

  // Initialize update batcher
  useEffect(() => {
    if (enableCompression) {
      deltaCompressorRef.current = new DeltaCompressor();
      
      updateBatcherRef.current = new UpdateBatcher(
        {
          maxBatchSize: batchingOptions.maxBatchSize || 50,
          maxBatchTime: batchingOptions.maxBatchTime || 100,
          priorityThreshold: batchingOptions.priorityThreshold || 8,
          compressionThreshold: batchingOptions.compressionThreshold || 1024,
          enableDiffCompression: true,
          ...batchingOptions
        },
        async (batch) => {
          // Send batched updates
          if (batch.compressed) {
            wsSend({
              type: 'batch:compressed',
              data: batch.compressed,
              priority: batch.priority
            });
            
            setStats(prev => ({
              ...prev,
              compressionRatio: batch.compressed.compressedSize / batch.compressed.originalSize
            }));
          } else {
            wsSend({
              type: 'batch:updates',
              data: batch.updates,
              priority: batch.priority
            });
          }
        }
      );
    }

    return () => {
      updateBatcherRef.current?.destroy();
      deltaCompressorRef.current?.destroy();
    };
  }, [enableCompression, batchingOptions, wsSend]);

  // Initialize offline queue
  useEffect(() => {
    if (enableOfflineQueue) {
      offlineQueueRef.current = new OfflineQueueManager(
        async (messages) => {
          // Send queued messages
          for (const message of messages) {
            wsSend(message.data);
          }
        },
        (conflict) => {
          console.log('[EnhancedWebSocket] Offline sync conflict:', conflict);
          setStats(prev => ({
            ...prev,
            conflictsResolved: prev.conflictsResolved + 1
          }));
        }
      );

      offlineQueueRef.current.initialize();

      // Update queue status periodically
      const statusInterval = setInterval(async () => {
        if (offlineQueueRef.current) {
          const status = await offlineQueueRef.current.getQueueStatus();
          setQueueStatus({
            queueSize: status.queueSize,
            isSyncing: status.isSyncing
          });
        }
      }, 1000);

      return () => {
        clearInterval(statusInterval);
        offlineQueueRef.current?.destroy();
      };
    }
  }, [enableOfflineQueue, wsSend]);

  // Enhanced send function
  const send = useCallback((message: any) => {
    // Add to offline queue if enabled and offline
    if (enableOfflineQueue && connectionState !== ConnectionState.CONNECTED) {
      offlineQueueRef.current?.enqueue({
        type: message.type || 'data',
        data: message,
        priority: message.priority || 0
      });
      return;
    }

    // Add to update batcher if enabled
    if (updateBatcherRef.current && message.type === 'delta') {
      const delta: GraphDelta = {
        id: message.id || `delta-${Date.now()}`,
        timestamp: Date.now(),
        operations: message.operations || [],
        version: message.version || '1.0',
        sourceId: `client-${Date.now()}`,
        dependencies: message.dependencies || []
      };

      updateBatcherRef.current.addUpdate(delta, message.priority || 0);
      return;
    }

    // Send directly
    wsSend(message);
  }, [connectionState, enableOfflineQueue, wsSend]);

  // Subscribe function
  const subscribe = useCallback((handler: (message: any) => void) => {
    subscribersRef.current.add(handler);
    
    return () => {
      subscribersRef.current.delete(handler);
    };
  }, []);

  // Force sync function
  const forceSync = useCallback(async () => {
    if (offlineQueueRef.current) {
      await offlineQueueRef.current.sync();
    }
    
    if (updateBatcherRef.current) {
      updateBatcherRef.current.flush();
    }
    
    if (messageDeduplicatorRef.current) {
      messageDeduplicatorRef.current.flush();
    }
  }, []);

  // Clear queue function
  const clearQueue = useCallback(async () => {
    if (offlineQueueRef.current) {
      await offlineQueueRef.current.clearQueue();
    }
    
    if (messageDeduplicatorRef.current) {
      messageDeduplicatorRef.current.clear();
    }
    
    setStats({
      messagesReceived: 0,
      duplicatesDetected: 0,
      conflictsResolved: 0,
      compressionRatio: 1.0
    });
  }, []);

  // Get detailed statistics
  const getDetailedStats = useCallback(() => {
    return {
      connection: {
        state: connectionState,
        health: aggregateHealth
      },
      queue: queueStatus,
      deduplication: messageDeduplicatorRef.current?.getStats(),
      batching: updateBatcherRef.current?.getStats(),
      conflicts: conflictResolverRef.current?.getConflictStats(),
      general: stats
    };
  }, [connectionState, aggregateHealth, queueStatus, stats]);

  const contextValue: EnhancedWebSocketContextValue = {
    connectionState,
    connectionHealth: aggregateHealth,
    queueStatus,
    stats,
    send,
    subscribe,
    forceSync,
    clearQueue,
    getDetailedStats
  };

  return (
    <EnhancedWebSocketContext.Provider value={contextValue}>
      {children}
    </EnhancedWebSocketContext.Provider>
  );
};