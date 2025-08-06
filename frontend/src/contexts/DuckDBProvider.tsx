import React, { createContext, useContext, ReactNode, useMemo } from 'react';
import { useDuckDBService } from '../hooks/useDuckDBService';
import { DuckDBService } from '../services/duckdb-service';
import * as duckdb from '@duckdb/duckdb-wasm';
import { useParallelInit } from './ParallelInitProvider';

interface DuckDBContextValue {
  service: DuckDBService | null;
  isInitialized: boolean;
  isLoading: boolean;
  error: Error | null;
  stats: { nodes: number; edges: number } | null;
  getDuckDBConnection: () => { duckdb: duckdb.AsyncDuckDB; connection: duckdb.AsyncDuckDBConnection } | null;
}

const DuckDBContext = createContext<DuckDBContextValue | null>(null);

export const useDuckDB = () => {
  const context = useContext(DuckDBContext);
  if (!context) {
    throw new Error('useDuckDB must be used within DuckDBProvider');
  }
  return context;
};

interface DuckDBProviderProps {
  children: ReactNode;
  rustServerUrl?: string;
}

export const DuckDBProvider: React.FC<DuckDBProviderProps> = ({ 
  children, 
  rustServerUrl 
}) => {
  // Try to get DuckDB from ParallelInitProvider first
  let parallelInit: ReturnType<typeof useParallelInit> | null = null;
  try {
    parallelInit = useParallelInit();
  } catch (e) {
    // Not inside ParallelInitProvider, use standalone mode
  }

  // Use parallel init if available, otherwise use standalone service
  const standaloneService = useDuckDBService({
    rustServerUrl,
    autoInitialize: !parallelInit // Only auto-initialize if not using parallel init
  });

  // Combine the context values
  const contextValue = useMemo<DuckDBContextValue>(() => {
    if (parallelInit?.isDuckDBReady && parallelInit.duckDBService) {
      // Use the parallel initialized service
      return {
        service: parallelInit.duckDBService,
        isInitialized: true,
        isLoading: false,
        error: parallelInit.initError,
        stats: null, // TODO: Get stats from service
        getDuckDBConnection: parallelInit.getDuckDBConnection
      };
    } else {
      // Use standalone service
      return standaloneService;
    }
  }, [parallelInit, standaloneService]);

  return (
    <DuckDBContext.Provider value={contextValue}>
      {children}
    </DuckDBContext.Provider>
  );
};