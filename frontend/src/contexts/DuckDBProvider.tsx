import React, { createContext, useContext, ReactNode } from 'react';
import { useDuckDBService } from '../hooks/useDuckDBService';
import { DuckDBService } from '../services/duckdb-service';
import * as duckdb from '@duckdb/duckdb-wasm';

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
  const duckdbService = useDuckDBService({
    rustServerUrl,
    autoInitialize: true
  });

  return (
    <DuckDBContext.Provider value={duckdbService}>
      {children}
    </DuckDBContext.Provider>
  );
};