import { useEffect, useRef, useState } from 'react';
import { DuckDBService } from '../services/duckdb-service';
import { useWebSocketContext } from '../contexts/WebSocketProvider';
import { logger } from '../utils/logger';

interface UseDuckDBServiceOptions {
  rustServerUrl?: string;
  autoInitialize?: boolean;
}

export function useDuckDBService(options: UseDuckDBServiceOptions = {}) {
  const {
    rustServerUrl = import.meta.env.VITE_RUST_SERVER_URL || import.meta.env.VITE_API_URL || 'http://192.168.50.90:3000',
    autoInitialize = true
  } = options;

  const [isInitialized, setIsInitialized] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [stats, setStats] = useState<{ nodes: number; edges: number } | null>(null);
  
  const serviceRef = useRef<DuckDBService | null>(null);
  const { subscribeToGraphUpdate } = useWebSocketContext();

  // Initialize DuckDB service
  useEffect(() => {
    if (!autoInitialize) return;

    const initializeDuckDB = async () => {
      if (serviceRef.current?.initialized) return;
      
      setIsLoading(true);
      setError(null);

      try {
        logger.log('[DuckDB] Initializing service with server:', rustServerUrl);
        
        const service = new DuckDBService({ rustServerUrl });
        await service.initialize();
        
        serviceRef.current = service;
        
        // Get initial stats
        const initialStats = await service.getStats();
        setStats(initialStats);
        
        setIsInitialized(true);
        logger.log('[DuckDB] Service initialized successfully with', initialStats);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Failed to initialize DuckDB';
        logger.error('[DuckDB] Initialization failed:', err);
        setError(new Error(errorMessage));
      } finally {
        setIsLoading(false);
      }
    };

    initializeDuckDB();

    return () => {
      if (serviceRef.current) {
        logger.log('[DuckDB] Closing service');
        serviceRef.current.close();
        serviceRef.current = null;
      }
    };
  }, [rustServerUrl, autoInitialize]);

  // Subscribe to WebSocket graph updates
  useEffect(() => {
    if (!isInitialized || !serviceRef.current) return;

    const unsubscribe = subscribeToGraphUpdate(async (event) => {
      if (!serviceRef.current) return;
      
      logger.log('[DuckDB] Received graph update:', event.data);
      
      try {
        // Apply the update to DuckDB
        await serviceRef.current.applyUpdate(event.data);
        
        // Update stats
        const newStats = await serviceRef.current.getStats();
        setStats(newStats);
        
        logger.log('[DuckDB] Update applied successfully, new stats:', newStats);
      } catch (err) {
        logger.error('[DuckDB] Failed to apply update:', err);
      }
    });

    return unsubscribe;
  }, [isInitialized, subscribeToGraphUpdate]);

  return {
    service: serviceRef.current,
    isInitialized,
    isLoading,
    error,
    stats,
    getDuckDBConnection: () => serviceRef.current?.getDuckDBConnection() || null,
  };
}