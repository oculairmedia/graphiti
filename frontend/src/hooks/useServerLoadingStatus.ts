/**
 * useServerLoadingStatus - Polls server loading status during backend startup
 * Shows progress bar when the Rust visualizer is still loading graph data
 */

import { useState, useEffect, useCallback } from 'react';

export interface ServerLoadingStatus {
  state: 'initializing' | 'loading_nodes' | 'loading_edges' | 'indexing' | 'ready' | 'error';
  progress_percent: number;
  current_phase: string;
  nodes_loaded: number;
  nodes_total: number;
  edges_loaded: number;
  edges_total: number;
  elapsed_seconds: number;
  estimated_remaining_seconds: number | null;
  ready: boolean;
}

interface UseServerLoadingStatusOptions {
  pollInterval?: number;
  onReady?: () => void;
  onError?: (error: Error) => void;
}

export function useServerLoadingStatus(options: UseServerLoadingStatusOptions = {}) {
  const { pollInterval = 1000, onReady, onError } = options;
  
  const [status, setStatus] = useState<ServerLoadingStatus | null>(null);
  const [isPolling, setIsPolling] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [consecutiveErrors, setConsecutiveErrors] = useState(0);

  const fetchStatus = useCallback(async () => {
    try {
      const baseUrl = import.meta.env.VITE_RUST_SERVER_URL || 'http://192.168.50.90:3000';
      const response = await fetch(`${baseUrl}/api/loading-status`, {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
        signal: AbortSignal.timeout(5000), // 5 second timeout
      });

      if (!response.ok) {
        throw new Error(`Server returned ${response.status}`);
      }

      const data: ServerLoadingStatus = await response.json();
      setStatus(data);
      setConsecutiveErrors(0);
      setError(null);

      // If server is ready, stop polling
      if (data.ready) {
        setIsPolling(false);
        onReady?.();
      }
    } catch (err) {
      const newError = err instanceof Error ? err : new Error('Failed to fetch loading status');
      setConsecutiveErrors(prev => prev + 1);
      
      // Only set error state after 3 consecutive failures
      if (consecutiveErrors >= 2) {
        setError(newError);
        onError?.(newError);
      }
      
      // Keep polling even on error - server might not be up yet
      console.log('[useServerLoadingStatus] Fetch error (attempt', consecutiveErrors + 1, '):', newError.message);
    }
  }, [consecutiveErrors, onReady, onError]);

  useEffect(() => {
    if (!isPolling) return;

    // Initial fetch
    fetchStatus();

    // Set up polling interval
    const intervalId = setInterval(fetchStatus, pollInterval);

    return () => {
      clearInterval(intervalId);
    };
  }, [isPolling, pollInterval, fetchStatus]);

  // Format remaining time as human-readable
  const formatTimeRemaining = (seconds: number | null): string => {
    if (seconds === null || seconds <= 0) return '';
    if (seconds < 60) return `~${Math.ceil(seconds)}s remaining`;
    const minutes = Math.floor(seconds / 60);
    const secs = Math.ceil(seconds % 60);
    return `~${minutes}m ${secs}s remaining`;
  };

  return {
    status,
    isLoading: status ? !status.ready : true,
    isReady: status?.ready ?? false,
    error,
    progressPercent: status?.progress_percent ?? 0,
    currentPhase: status?.current_phase ?? 'connecting',
    nodesProgress: status ? `${status.nodes_loaded.toLocaleString()}/${status.nodes_total.toLocaleString()}` : '',
    edgesProgress: status ? `${status.edges_loaded.toLocaleString()}/${status.edges_total.toLocaleString()}` : '',
    timeRemaining: formatTimeRemaining(status?.estimated_remaining_seconds ?? null),
    elapsedSeconds: status?.elapsed_seconds ?? 0,
    // Allow retrying if there were errors
    retry: () => {
      setConsecutiveErrors(0);
      setError(null);
      setIsPolling(true);
    }
  };
}
