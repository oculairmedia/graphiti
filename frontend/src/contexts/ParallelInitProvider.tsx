/**
 * ParallelInitProvider - Coordinates parallel initialization of all providers
 * Significantly reduces initial load time by initializing everything simultaneously
 */

import React, { createContext, useContext, useEffect, useState, useRef, ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { GraphConfigProvider } from './GraphConfigProvider';
import { WebSocketProvider } from './WebSocketProvider';
import { LoadingCoordinatorProvider, useLoadingCoordinator } from './LoadingCoordinator';
import { UnifiedLoadingScreen } from '../components/UnifiedLoadingScreen';
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

// Main provider that wraps everything with LoadingCoordinator
export const ParallelInitProvider: React.FC<ParallelInitProviderProps> = ({ 
  children,
  queryClient,
  rustServerUrl = import.meta.env.VITE_RUST_SERVER_URL || 'http://192.168.50.90:3000'
}) => {
  return (
    <LoadingCoordinatorProvider requiredStages={['services', 'data']}>
      <ParallelInitContent 
        queryClient={queryClient}
        rustServerUrl={rustServerUrl}
      >
        {children}
      </ParallelInitContent>
    </LoadingCoordinatorProvider>
  );
};

// Internal component that uses LoadingCoordinator
const ParallelInitContent: React.FC<ParallelInitProviderProps> = ({ 
  children,
  queryClient,
  rustServerUrl = import.meta.env.VITE_RUST_SERVER_URL || 'http://192.168.50.90:3000'
}) => {
  const loadingCoordinator = useLoadingCoordinator();
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
        // Update loading stages
        loadingCoordinator.updateStage('services', { status: 'loading', progress: 0 });
        
        // Start all initializations in parallel
        const initPromises = [
          // 1. Initialize DuckDB with data loading
          (async () => {
            try {
              logger.log('[ParallelInit] Initializing DuckDB...');
              loadingCoordinator.updateStage('services', { status: 'loading', progress: 30 });
              
              const service = new DuckDBService({ rustServerUrl });
              
              // Start initialization with parallel data prefetch
              await service.initialize();
              
              duckDBServiceRef.current = service;
              const connection = service.getDuckDBConnection();
              
              // Get data stats for loading screen
              const stats = await service.getStats();
              loadingCoordinator.updateStage('data', { 
                status: 'loading', 
                progress: 50,
                metadata: { nodeCount: stats?.nodes, edgeCount: stats?.edges }
              });
              
              setState(prev => ({
                ...prev,
                isDuckDBReady: true,
                duckDBService: service,
                duckDBConnection: connection,
                initProgress: prev.initProgress + 33
              }));
              
              // Mark data as complete
              loadingCoordinator.setStageComplete('data', { 
                nodeCount: stats?.nodes, 
                edgeCount: stats?.edges 
              });
              
              logger.log('[ParallelInit] DuckDB ready with data');
              return { type: 'duckdb', success: true };
            } catch (error) {
              loadingCoordinator.setStageError('services', error as Error);
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
        
        // Mark services stage as complete
        loadingCoordinator.setStageComplete('services');
        
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

  // Show unified loading screen until everything is ready
  if (!loadingCoordinator.isFullyLoaded) {
    return (
      <>
        <UnifiedLoadingScreen />
        {/* Keep context provider alive but hide children */}
        <div style={{ display: 'none' }}>
          <ParallelInitContext.Provider value={contextValue}>
            <QueryClientProvider client={client}>
              <GraphConfigProvider>
                <WebSocketProvider>
                  {/* Children hidden until loading complete */}
                </WebSocketProvider>
              </GraphConfigProvider>
            </QueryClientProvider>
          </ParallelInitContext.Provider>
        </div>
      </>
    );
  }

  // Render providers and children once everything is ready
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