import { useEffect, useRef, useCallback, useState } from 'react';
import { useRustWebSocket } from '../contexts/RustWebSocketProvider';
import { logger } from '../utils/logger';

interface RealtimeDataSyncOptions {
  enabled?: boolean;
  debounceMs?: number;
  onDataUpdate?: () => void;
  onNotification?: (notification: any) => void;
}

/**
 * Hook that connects WebSocket notifications to data refresh
 * This enables real-time updates without disrupting the visualization
 */
export function useRealtimeDataSync({
  enabled = true,
  debounceMs = 500, // Debounce rapid updates
  onDataUpdate,
  onNotification,
}: RealtimeDataSyncOptions = {}) {
  const { isConnected, subscribe } = useRustWebSocket();
  const [lastUpdateTime, setLastUpdateTime] = useState<number>(0);
  const [pendingUpdate, setPendingUpdate] = useState(false);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const updateCountRef = useRef(0);
  const lastUpdateTimeRef = useRef(0);

  // Store callbacks in refs to avoid recreating them
  const onDataUpdateRef = useRef(onDataUpdate);
  const onNotificationRef = useRef(onNotification);
  
  // Update refs when callbacks change
  useEffect(() => {
    onDataUpdateRef.current = onDataUpdate;
    onNotificationRef.current = onNotification;
  }, [onDataUpdate, onNotification]);

  // Debounced update handler to prevent too frequent refreshes
  const handleDataUpdate = useCallback(() => {
    // Clear any existing timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    // Set pending update flag
    setPendingUpdate(true);

    // Debounce the actual update
    debounceTimerRef.current = setTimeout(() => {
      const now = Date.now();
      updateCountRef.current++;
      
      logger.log('[useRealtimeDataSync] Triggering data refresh', {
        updateCount: updateCountRef.current,
        timeSinceLastUpdate: now - (lastUpdateTimeRef.current || 0),
        hasCallback: !!onDataUpdateRef.current
      });

      lastUpdateTimeRef.current = now;
      setLastUpdateTime(now);
      setPendingUpdate(false);
      
      // Trigger the data update callback using ref with error handling
      try {
        onDataUpdateRef.current?.();
        logger.log('[useRealtimeDataSync] Data refresh callback executed successfully');
      } catch (error) {
        logger.error('[useRealtimeDataSync] Error in data refresh callback:', error);
      }
    }, debounceMs);
  }, [debounceMs]); // Only depend on debounceMs

  // Subscribe to WebSocket notifications
  useEffect(() => {
    if (!enabled || !isConnected) return;

    logger.log('[useRealtimeDataSync] Setting up WebSocket subscription');

    const unsubscribe = subscribe((update) => {
      logger.log('[useRealtimeDataSync] Received WebSocket update:', {
        type: update.type,
        hasData: !!(update.data?.nodes || update.data?.edges),
        nodeCount: update.data?.nodes?.length || 0,
        edgeCount: update.data?.edges?.length || 0
      });

      try {
        // Handle different update types
        if (update.type === 'graph:update' || update.type === 'graph:delta') {
          // Call the notification callback if provided
          onNotificationRef.current?.(update);

          // Check if this is a notification (no data payload) or actual data
          const hasDataPayload = update.data?.nodes || update.data?.edges;
          
          if (!hasDataPayload) {
            // This is a notification - trigger data refresh
            logger.log('[useRealtimeDataSync] Notification received, triggering refresh');
            handleDataUpdate();
          } else {
            // This is actual data - let the data layer handle it
            logger.log('[useRealtimeDataSync] Data payload received, skipping refresh');
          }
        } else {
          logger.log('[useRealtimeDataSync] Unknown update type received:', update.type);
        }
      } catch (error) {
        logger.error('[useRealtimeDataSync] Error handling WebSocket update:', error);
      }
    });

    return () => {
      logger.log('[useRealtimeDataSync] Cleaning up WebSocket subscription');
      unsubscribe();
      
      // Clear any pending timers
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [enabled, isConnected, subscribe, handleDataUpdate]); // Stable dependencies

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  return {
    isConnected,
    lastUpdateTime,
    pendingUpdate,
    updateCount: updateCountRef.current,
  };
}