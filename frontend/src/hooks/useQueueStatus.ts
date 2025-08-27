import { useState, useEffect, useRef } from 'react';
import { QueueStatus } from '@/api/types';
import { GraphClient } from '@/api/graphClient';

interface UseQueueStatusOptions {
  refreshInterval?: number; // in milliseconds
  enabled?: boolean;
}

interface UseQueueStatusResult {
  queueStatus: QueueStatus | null;
  isLoading: boolean;      // initial-only
  isRefreshing: boolean;   // background refetches
  error: string | null;
  isStale: boolean;        // data is older than 60s
  lastUpdatedAgo: number | null; // seconds since last successful update
  refresh: () => void;
}

export const useQueueStatus = ({ 
  refreshInterval = 5000, // 5 seconds default
  enabled = true 
}: UseQueueStatusOptions = {}): UseQueueStatusResult => {
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlightRef = useRef(false);
  const mountedRef = useRef(true);
  const requestIdRef = useRef(0);
  const [lastSuccessAt, setLastSuccessAt] = useState<number | null>(null);
  const [currentTime, setCurrentTime] = useState(Date.now());

  const graphClient = new GraphClient();

  const fetchQueueStatus = async () => {
    if (!enabled || inFlightRef.current || !mountedRef.current) return;
    
    inFlightRef.current = true;
    const currentRequestId = ++requestIdRef.current;
    const isInitial = queueStatus === null;
    
    try {
      if (isInitial) {
        setIsLoading(true);
      } else {
        setIsRefreshing(true);
      }
      setError(null);
      
      const status = await graphClient.getQueueStatus();
      
      // Only apply result if this is the latest request and component is still mounted
      if (currentRequestId !== requestIdRef.current || !mountedRef.current) {
        return; // Stale request, ignore result
      }
      
      // Field-wise comparison to prevent unnecessary re-renders
      setQueueStatus(prev => {
        if (!prev) return status;
        
        // Check if any rendered fields actually changed
        const fieldsEqual = 
          prev.status === status.status &&
          prev.visible_messages === status.visible_messages &&
          prev.invisible_messages === status.invisible_messages &&
          prev.total_processed === status.total_processed &&
          prev.total_failed === status.total_failed &&
          prev.success_rate === status.success_rate &&
          prev.last_updated === status.last_updated;
        
        if (fieldsEqual) {
          return prev; // Prevent re-render if nothing actually changed
        }
        
        return status;
      });
      
      // Track successful update timestamp
      setLastSuccessAt(Date.now());
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch queue status';
      setError(errorMessage);
      console.error('Queue status fetch error:', err);
      // Keep showing last good data on error
    } finally {
      if (isInitial) {
        setIsLoading(false);
      }
      setIsRefreshing(false);
      inFlightRef.current = false;
    }
  };

  const refresh = () => {
    fetchQueueStatus();
  };

  useEffect(() => {
    if (!enabled) return;

    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    let isActive = true;

    const scheduleNext = () => {
      if (!isActive) return;
      
      // Add ±10% jitter to prevent synchronized requests across instances
      const base = Math.max(1500, refreshInterval); // Enforce minimum 1.5s interval
      const jitter = base * (Math.random() * 0.2 - 0.1); // ±10%
      const nextInterval = Math.floor(base + jitter);
      
      timeoutId = setTimeout(() => {
        if (isActive) {
          fetchQueueStatus().finally(() => {
            if (isActive) scheduleNext();
          });
        }
      }, nextInterval);
    };

    // Initial fetch, then start adaptive polling
    fetchQueueStatus().finally(() => {
      if (isActive) scheduleNext();
    });

    return () => {
      isActive = false;
      mountedRef.current = false;
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [refreshInterval, enabled]);

  // Update current time every second for staleness calculation
  useEffect(() => {
    const timeInterval = setInterval(() => {
      setCurrentTime(Date.now());
    }, 1000);

    return () => clearInterval(timeInterval);
  }, []);

  // Calculate staleness
  const lastUpdatedAgo = lastSuccessAt ? Math.floor((currentTime - lastSuccessAt) / 1000) : null;
  const isStale = lastUpdatedAgo !== null && lastUpdatedAgo > 60;

  return {
    queueStatus,
    isLoading,
    isRefreshing,
    error,
    isStale,
    lastUpdatedAgo,
    refresh,
  };
};