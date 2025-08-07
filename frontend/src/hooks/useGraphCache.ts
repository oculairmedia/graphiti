import { useEffect, useRef, useState, useCallback } from 'react';
import { GraphCacheService } from '../services/graph-cache-service';
import { useWebSocketContext } from '../contexts/WebSocketProvider';
import { useDuckDBService } from './useDuckDBService';
import { logger } from '../utils/logger';

interface UseGraphCacheOptions {
  ttl?: number;
  maxSize?: number;
  enableVersioning?: boolean;
  autoConnect?: boolean;
}

export function useGraphCache(options: UseGraphCacheOptions = {}) {
  const {
    ttl = 5 * 60 * 1000,
    maxSize = 1000,
    enableVersioning = true,
    autoConnect = true
  } = options;

  const [isInitialized, setIsInitialized] = useState(false);
  const [cacheStats, setCacheStats] = useState<ReturnType<GraphCacheService['getStats']> | null>(null);
  
  const cacheServiceRef = useRef<GraphCacheService | null>(null);
  const { subscribeToDeltaUpdate, subscribeToCacheInvalidate, updateStats } = useWebSocketContext();
  const { service: duckDBService, isInitialized: isDuckDBReady } = useDuckDBService();

  // Initialize cache service
  useEffect(() => {
    if (!autoConnect) return;

    logger.log('[GraphCache] Initializing cache service');
    
    const cache = new GraphCacheService({
      ttl,
      maxSize,
      enableVersioning
    });
    
    cacheServiceRef.current = cache;
    setIsInitialized(true);
    
    // Update stats periodically
    const statsInterval = setInterval(() => {
      if (cacheServiceRef.current) {
        setCacheStats(cacheServiceRef.current.getStats());
      }
    }, 5000);
    
    return () => {
      clearInterval(statsInterval);
      if (cacheServiceRef.current) {
        cacheServiceRef.current.clear();
        cacheServiceRef.current = null;
      }
    };
  }, [ttl, maxSize, enableVersioning, autoConnect]);

  // Connect DuckDB service when ready
  useEffect(() => {
    if (!isInitialized || !isDuckDBReady || !duckDBService || !cacheServiceRef.current) return;
    
    logger.log('[GraphCache] Connecting DuckDB service');
    cacheServiceRef.current.setDuckDBService(duckDBService);
  }, [isInitialized, isDuckDBReady, duckDBService]);

  // Subscribe to WebSocket delta updates
  useEffect(() => {
    if (!isInitialized || !cacheServiceRef.current) return;

    const unsubscribeDelta = subscribeToDeltaUpdate(async (event) => {
      logger.log('[GraphCache] Received delta update:', event.data);
      
      try {
        await cacheServiceRef.current?.applyDeltaUpdate(event.data);
        setCacheStats(cacheServiceRef.current?.getStats() || null);
      } catch (error) {
        logger.error('[GraphCache] Failed to apply delta update:', error);
      }
    });

    const unsubscribeInvalidate = subscribeToCacheInvalidate((event) => {
      logger.log('[GraphCache] Received cache invalidation:', event.data);
      
      cacheServiceRef.current?.invalidate(event.data.keys);
      setCacheStats(cacheServiceRef.current?.getStats() || null);
    });

    return () => {
      unsubscribeDelta();
      unsubscribeInvalidate();
    };
  }, [isInitialized, subscribeToDeltaUpdate, subscribeToCacheInvalidate]);

  // Cached data fetching
  const getCached = useCallback(async <T,>(
    key: string,
    fetcher?: () => Promise<T>
  ): Promise<T | null> => {
    if (!cacheServiceRef.current) {
      logger.warn('[GraphCache] Cache not initialized, fetching directly');
      return fetcher ? await fetcher() : null;
    }
    
    return cacheServiceRef.current.get(key, fetcher);
  }, []);

  // Manual cache operations
  const setCached = useCallback(<T,>(key: string, data: T, version?: string) => {
    if (!cacheServiceRef.current) {
      logger.warn('[GraphCache] Cache not initialized');
      return;
    }
    
    cacheServiceRef.current.set(key, data, version);
    setCacheStats(cacheServiceRef.current.getStats());
  }, []);

  const invalidate = useCallback((keys: string | string[]) => {
    if (!cacheServiceRef.current) {
      logger.warn('[GraphCache] Cache not initialized');
      return;
    }
    
    cacheServiceRef.current.invalidate(keys);
    setCacheStats(cacheServiceRef.current.getStats());
  }, []);

  const clearCache = useCallback(() => {
    if (!cacheServiceRef.current) {
      logger.warn('[GraphCache] Cache not initialized');
      return;
    }
    
    cacheServiceRef.current.clear();
    setCacheStats(cacheServiceRef.current.getStats());
  }, []);

  // Prefetch common data patterns
  const prefetch = useCallback(async (patterns: string[]) => {
    if (!cacheServiceRef.current || !duckDBService) {
      logger.warn('[GraphCache] Cannot prefetch, services not ready');
      return;
    }
    
    logger.log('[GraphCache] Prefetching patterns:', patterns);
    
    const prefetchPromises = patterns.map(async (pattern) => {
      if (pattern === 'graph:full') {
        // Prefetch full graph data
        return getCached('graph:full', async () => {
          const nodes = await duckDBService.query('SELECT * FROM nodes');
          const edges = await duckDBService.query('SELECT * FROM edges');
          return { nodes, edges };
        });
      } else if (pattern.startsWith('nodes:')) {
        // Prefetch specific node types
        const nodeType = pattern.split(':')[1];
        return getCached(pattern, async () => {
          return duckDBService.query(`SELECT * FROM nodes WHERE type = '${nodeType}'`);
        });
      }
      // Add more patterns as needed
    });
    
    await Promise.allSettled(prefetchPromises);
    logger.log('[GraphCache] Prefetch complete');
  }, [getCached, duckDBService]);

  return {
    isInitialized,
    cacheStats,
    updateStats,
    getCached,
    setCached,
    invalidate,
    clearCache,
    prefetch
  };
}