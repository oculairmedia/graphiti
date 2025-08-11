import React, { useEffect, useRef, useCallback, useState } from 'react';
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

interface DeltaProcessorProps {
  wsUrl?: string;
  onDeltaReceived?: (delta: DeltaUpdate) => void;
  onNodesAdded?: (nodes: GraphNode[]) => void;
  onNodesUpdated?: (nodes: GraphNode[]) => void;
  onNodesRemoved?: (nodeIds: string[]) => void;
  onLinksAdded?: (links: GraphLink[]) => void;
  onLinksUpdated?: (links: GraphLink[]) => void;
  onLinksRemoved?: (linkIds: string[]) => void;
  batchSize?: number;
  batchDelay?: number;
  maxQueueSize?: number;
  enableAutoReconnect?: boolean;
}

interface DeltaProcessorState {
  isConnected: boolean;
  queueSize: number;
  lastProcessed: number;
  error: Error | null;
}

/**
 * DeltaProcessor - Handles WebSocket delta updates for real-time graph changes
 * 
 * Features:
 * - WebSocket connection management
 * - Delta queue with batching
 * - Automatic reconnection
 * - Conflict resolution
 * - Memory-efficient processing
 */
export const DeltaProcessor: React.FC<DeltaProcessorProps> = ({
  wsUrl = 'ws://localhost:3000/ws',
  onDeltaReceived,
  onNodesAdded,
  onNodesUpdated,
  onNodesRemoved,
  onLinksAdded,
  onLinksUpdated,
  onLinksRemoved,
  batchSize = 100,
  batchDelay = 50,
  maxQueueSize = 1000,
  enableAutoReconnect = true
}) => {
  const [state, setState] = useState<DeltaProcessorState>({
    isConnected: false,
    queueSize: 0,
    lastProcessed: Date.now(),
    error: null
  });

  // Refs for WebSocket and processing
  const wsRef = useRef<WebSocket | null>(null);
  const deltaQueueRef = useRef<DeltaUpdate[]>([]);
  const processingTimerRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const isProcessingRef = useRef(false);
  const reconnectAttemptsRef = useRef(0);

  // Process batch of deltas
  const processDeltaBatch = useCallback(() => {
    if (isProcessingRef.current || deltaQueueRef.current.length === 0) {
      return;
    }

    isProcessingRef.current = true;

    try {
      // Extract batch
      const batch = deltaQueueRef.current.splice(0, batchSize);
      
      // Group by operation type
      const nodesAdded: GraphNode[] = [];
      const nodesUpdated: GraphNode[] = [];
      const nodesRemoved: string[] = [];
      const linksAdded: GraphLink[] = [];
      const linksUpdated: GraphLink[] = [];
      const linksRemoved: string[] = [];

      batch.forEach(delta => {
        onDeltaReceived?.(delta);

        if (delta.entityType === 'node') {
          switch (delta.type) {
            case 'add':
              nodesAdded.push(delta.data);
              break;
            case 'update':
              nodesUpdated.push(delta.data);
              break;
            case 'remove':
              nodesRemoved.push(delta.data.id);
              break;
          }
        } else if (delta.entityType === 'link') {
          switch (delta.type) {
            case 'add':
              linksAdded.push(delta.data);
              break;
            case 'update':
              linksUpdated.push(delta.data);
              break;
            case 'remove':
              linksRemoved.push(delta.data.id);
              break;
          }
        }
      });

      // Trigger callbacks
      if (nodesAdded.length > 0) onNodesAdded?.(nodesAdded);
      if (nodesUpdated.length > 0) onNodesUpdated?.(nodesUpdated);
      if (nodesRemoved.length > 0) onNodesRemoved?.(nodesRemoved);
      if (linksAdded.length > 0) onLinksAdded?.(linksAdded);
      if (linksUpdated.length > 0) onLinksUpdated?.(linksUpdated);
      if (linksRemoved.length > 0) onLinksRemoved?.(linksRemoved);

      // Update state
      setState(prev => ({
        ...prev,
        queueSize: deltaQueueRef.current.length,
        lastProcessed: Date.now()
      }));

      logger.log('DeltaProcessor: Processed batch', {
        batchSize: batch.length,
        remainingQueue: deltaQueueRef.current.length
      });

    } catch (error) {
      logger.error('DeltaProcessor: Error processing batch:', error);
      setState(prev => ({
        ...prev,
        error: error instanceof Error ? error : new Error('Processing error')
      }));
    } finally {
      isProcessingRef.current = false;

      // Schedule next batch if queue not empty
      if (deltaQueueRef.current.length > 0) {
        scheduleBatchProcessing();
      }
    }
  }, [
    batchSize,
    onDeltaReceived,
    onNodesAdded,
    onNodesUpdated,
    onNodesRemoved,
    onLinksAdded,
    onLinksUpdated,
    onLinksRemoved
  ]);

  // Schedule batch processing
  const scheduleBatchProcessing = useCallback(() => {
    if (processingTimerRef.current) {
      clearTimeout(processingTimerRef.current);
    }

    processingTimerRef.current = setTimeout(() => {
      processDeltaBatch();
    }, batchDelay);
  }, [batchDelay, processDeltaBatch]);

  // Handle incoming WebSocket message
  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const delta: DeltaUpdate = JSON.parse(event.data);
      
      // Validate delta
      if (!delta.id || !delta.type || !delta.entityType) {
        logger.warn('DeltaProcessor: Invalid delta received:', delta);
        return;
      }

      // Check queue size
      if (deltaQueueRef.current.length >= maxQueueSize) {
        logger.warn('DeltaProcessor: Queue full, dropping oldest deltas');
        deltaQueueRef.current.splice(0, deltaQueueRef.current.length - maxQueueSize + 1);
      }

      // Add to queue
      deltaQueueRef.current.push({
        ...delta,
        timestamp: delta.timestamp || Date.now()
      });

      // Schedule processing
      scheduleBatchProcessing();

    } catch (error) {
      logger.error('DeltaProcessor: Error parsing message:', error);
    }
  }, [maxQueueSize, scheduleBatchProcessing]);

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      wsRef.current = new WebSocket(wsUrl);

      wsRef.current.onopen = () => {
        logger.log('DeltaProcessor: WebSocket connected');
        setState(prev => ({
          ...prev,
          isConnected: true,
          error: null
        }));
        reconnectAttemptsRef.current = 0;
      };

      wsRef.current.onmessage = handleMessage;

      wsRef.current.onclose = () => {
        logger.log('DeltaProcessor: WebSocket disconnected');
        setState(prev => ({
          ...prev,
          isConnected: false
        }));

        if (enableAutoReconnect) {
          scheduleReconnect();
        }
      };

      wsRef.current.onerror = (error) => {
        logger.error('DeltaProcessor: WebSocket error:', error);
        setState(prev => ({
          ...prev,
          error: new Error('WebSocket connection failed')
        }));
      };

    } catch (error) {
      logger.error('DeltaProcessor: Failed to create WebSocket:', error);
      setState(prev => ({
        ...prev,
        error: error instanceof Error ? error : new Error('Connection failed')
      }));

      if (enableAutoReconnect) {
        scheduleReconnect();
      }
    }
  }, [wsUrl, handleMessage, enableAutoReconnect]);

  // Schedule reconnection with exponential backoff
  const scheduleReconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
    }

    const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000);
    reconnectAttemptsRef.current++;

    logger.log(`DeltaProcessor: Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current})`);

    reconnectTimerRef.current = setTimeout(() => {
      connect();
    }, delay);
  }, [connect]);

  // Disconnect WebSocket
  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    if (processingTimerRef.current) {
      clearTimeout(processingTimerRef.current);
      processingTimerRef.current = null;
    }

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    deltaQueueRef.current = [];
    setState(prev => ({
      ...prev,
      isConnected: false,
      queueSize: 0
    }));
  }, []);

  // Connect on mount
  useEffect(() => {
    connect();

    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  // Export state for monitoring
  useEffect(() => {
    const stateExport = {
      isConnected: state.isConnected,
      queueSize: state.queueSize,
      lastProcessed: state.lastProcessed,
      error: state.error?.message
    };

    // Could emit this to a monitoring service
    logger.debug('DeltaProcessor state:', stateExport);
  }, [state]);

  return null; // This is a non-visual component
};

export default DeltaProcessor;