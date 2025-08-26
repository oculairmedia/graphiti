import { useState, useEffect } from 'react';
import { QueueStatus } from '@/api/types';
import { GraphClient } from '@/api/graphClient';

interface UseQueueStatusOptions {
  refreshInterval?: number; // in milliseconds
  enabled?: boolean;
}

interface UseQueueStatusResult {
  queueStatus: QueueStatus | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => void;
}

export const useQueueStatus = ({ 
  refreshInterval = 5000, // 5 seconds default
  enabled = true 
}: UseQueueStatusOptions = {}): UseQueueStatusResult => {
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const graphClient = new GraphClient();

  const fetchQueueStatus = async () => {
    if (!enabled) return;
    
    try {
      setIsLoading(true);
      setError(null);
      const status = await graphClient.getQueueStatus();
      setQueueStatus(status);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch queue status';
      setError(errorMessage);
      console.error('Queue status fetch error:', err);
    } finally {
      setIsLoading(false);
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
    error,
    refresh,
  };
};