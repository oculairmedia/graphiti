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

  const graphClient = new GraphClient();

  const fetchQueueStatus = async () => {
    if (!enabled || inFlightRef.current) return;
    
    inFlightRef.current = true;
    const isInitial = queueStatus === null;
    
    try {
      if (isInitial) {
        setIsLoading(true);
      } else {
        setIsRefreshing(true);
      }
      setError(null);
      
      const status = await graphClient.getQueueStatus();
      
      // Only update if data actually changed to prevent unnecessary re-renders
      setQueueStatus(prev => {
        if (JSON.stringify(prev) === JSON.stringify(status)) {
          return prev;
        }
        return status;
      });
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

    // Initial fetch
    fetchQueueStatus();

    // Set up interval for automatic refresh
    const interval = setInterval(fetchQueueStatus, refreshInterval);

    return () => clearInterval(interval);
  }, [refreshInterval, enabled]);

  return {
    queueStatus,
    isLoading,
    isRefreshing,
    error,
    refresh,
  };
};