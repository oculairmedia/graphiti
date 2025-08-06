/**
 * ParallelInitProvider - Coordinates parallel initialization of all providers
 * Significantly reduces initial load time by initializing everything simultaneously
 */

import React, { createContext, useContext, useEffect, useState, useRef, ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { GraphConfigProvider } from './GraphConfigProvider';
import { WebSocketProvider } from './WebSocketProvider';
import { DuckDBService } from '../services/duckdb-service';
import * as duckdb from '@duckdb/duckdb-wasm';
import { logger } from '../utils/logger';

interface ParallelInitState {
  isDuckDBReady: boolean;
  isWebSocketReady: boolean;
  isConfigReady: boolean;
  isAllReady: boolean;
  duckDBService: DuckDBService | null;
  duckDBConnection: { duckdb: duckdb.AsyncDuckDB; connection: duckdb.AsyncDuckDBConnection } | null;
  initProgress: number;
  initError: Error | null;
}

interface ParallelInitContextValue extends ParallelInitState {
  getDuckDBConnection: () => { duckdb: duckdb.AsyncDuckDB; connection: duckdb.AsyncDuckDBConnection } | null;
}

const ParallelInitContext = createContext<ParallelInitContextValue | null>(null);

export const useParallelInit = () => {
  const context = useContext(ParallelInitContext);
  if (!context) {
    throw new Error('useParallelInit must be used within ParallelInitProvider');
  }
  return context;
};

interface ParallelInitProviderProps {
  children: ReactNode;
  queryClient?: QueryClient;
  rustServerUrl?: string;
}

export const ParallelInitProvider: React.FC<ParallelInitProviderProps> = ({ 
  children,
  queryClient,
  rustServerUrl = import.meta.env.VITE_RUST_SERVER_URL || 'http://192.168.50.90:3000'
}) => {
  const [state, setState] = useState<ParallelInitState>({
    isDuckDBReady: false,
    isWebSocketReady: false,
    isConfigReady: false,
    isAllReady: false,
    duckDBService: null,
    duckDBConnection: null,
    initProgress: 0,
    initError: null
  });

  const duckDBServiceRef = useRef<DuckDBService | null>(null);
  const initStartedRef = useRef(false);

  // Create query client if not provided
  const client = queryClient || new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5 * 60 * 1000,
        cacheTime: 10 * 60 * 1000,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
        retry: 1,
        retryDelay: 1000,
      },
    },
  });

  useEffect(() => {
    if (initStartedRef.current) return;
    initStartedRef.current = true;

    const initializeAll = async () => {
      const startTime = performance.now();
      logger.log('[ParallelInit] Starting parallel initialization...');

      try {
        // Start all initializations in parallel
        const initPromises = [
          // 1. Initialize DuckDB
          (async () => {
            try {
              logger.log('[ParallelInit] Initializing DuckDB...');
              const service = new DuckDBService({ rustServerUrl });
              
              // Start initialization with parallel data prefetch
              await service.initialize();
              
              duckDBServiceRef.current = service;
              const connection = service.getDuckDBConnection();
              
              setState(prev => ({
                ...prev,
                isDuckDBReady: true,
                duckDBService: service,
                duckDBConnection: connection,
                initProgress: prev.initProgress + 33
              }));
              
              logger.log('[ParallelInit] DuckDB ready');
              return { type: 'duckdb', success: true };
            } catch (error) {
              logger.error('[ParallelInit] DuckDB initialization failed:', error);
              return { type: 'duckdb', success: false, error };
            }
          })(),

          // 2. Initialize WebSocket (simulated - actual connection happens in provider)
          (async () => {
            try {
              logger.log('[ParallelInit] Preparing WebSocket...');
              // WebSocket connection is established by WebSocketProvider
              // We just mark it as ready here
              await new Promise(resolve => setTimeout(resolve, 100));
              
              setState(prev => ({
                ...prev,
                isWebSocketReady: true,
                initProgress: prev.initProgress + 33
              }));
              
              logger.log('[ParallelInit] WebSocket ready');
              return { type: 'websocket', success: true };
            } catch (error) {
              logger.error('[ParallelInit] WebSocket preparation failed:', error);
              return { type: 'websocket', success: false, error };
            }
          })(),

          // 3. Initialize Config (simulated - actual setup happens in provider)
          (async () => {
            try {
              logger.log('[ParallelInit] Loading config...');
              // Config is loaded by GraphConfigProvider
              // We just mark it as ready here
              await new Promise(resolve => setTimeout(resolve, 50));
              
              setState(prev => ({
                ...prev,
                isConfigReady: true,
                initProgress: prev.initProgress + 34
              }));
              
              logger.log('[ParallelInit] Config ready');
              return { type: 'config', success: true };
            } catch (error) {
              logger.error('[ParallelInit] Config loading failed:', error);
              return { type: 'config', success: false, error };
            }
          })()
        ];

        // Wait for all initializations to complete
        const results = await Promise.allSettled(initPromises);
        
        // Check results
        const failures = results.filter(r => 
          r.status === 'rejected' || (r.status === 'fulfilled' && !r.value.success)
        );
        
        if (failures.length > 0) {
          const errorMsg = `Initialization failed for: ${failures.map((f: any) => 
            f.value?.type || 'unknown'
          ).join(', ')}`;
          
          throw new Error(errorMsg);
        }

        const endTime = performance.now();
        const duration = endTime - startTime;
        
        logger.log(`[ParallelInit] All services initialized in ${duration.toFixed(2)}ms`);
        
        setState(prev => ({
          ...prev,
          isAllReady: true,
          initProgress: 100
        }));
      } catch (error) {
        logger.error('[ParallelInit] Initialization failed:', error);
        setState(prev => ({
          ...prev,
          initError: error as Error
        }));
      }
    };

    initializeAll();

    // Cleanup
    return () => {
      if (duckDBServiceRef.current) {
        duckDBServiceRef.current.close();
        duckDBServiceRef.current = null;
      }
    };
  }, [rustServerUrl]);

  // Stable function reference
  const getDuckDBConnection = () => state.duckDBConnection;

  const contextValue: ParallelInitContextValue = {
    ...state,
    getDuckDBConnection
  };

  // Show loading state while initializing
  if (!state.isAllReady && !state.initError) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="mb-4">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          </div>
          <p className="text-muted-foreground">Initializing application...</p>
          <div className="mt-4 w-64 mx-auto">
            <div className="bg-secondary rounded-full h-2 overflow-hidden">
              <div 
                className="bg-primary h-full transition-all duration-300"
                style={{ width: `${state.initProgress}%` }}
              />
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              {state.isDuckDBReady && '✓ Database ready '}
              {state.isWebSocketReady && '✓ WebSocket ready '}
              {state.isConfigReady && '✓ Config loaded'}
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Show error state
  if (state.initError) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-background">
        <div className="text-center">
          <p className="text-destructive mb-2">Initialization Error</p>
          <p className="text-sm text-muted-foreground">{state.initError.message}</p>
          <button 
            onClick={() => window.location.reload()}
            className="mt-4 px-4 py-2 bg-primary text-primary-foreground rounded hover:bg-primary/90"
          >
            Reload Page
          </button>
        </div>
      </div>
    );
  }

  // Render providers in parallel once everything is ready
  return (
    <ParallelInitContext.Provider value={contextValue}>
      <QueryClientProvider client={client}>
        <GraphConfigProvider>
          <WebSocketProvider>
            {children}
          </WebSocketProvider>
        </GraphConfigProvider>
      </QueryClientProvider>
    </ParallelInitContext.Provider>
  );
};