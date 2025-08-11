import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { GraphNode } from '../../../api/types';
import { GraphLink } from '../../../types/graph';
import { logger } from '../../../utils/logger';
import { useDuckDB } from '../../../contexts/DuckDBProvider';

interface GraphStats {
  total_nodes: number;
  total_edges: number;
  density?: number;
  node_types?: Record<string, number>;
  centrality_stats?: {
    min: number;
    max: number;
    avg: number;
  };
}

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
  stats?: GraphStats;
}

interface GraphDataManagerProps {
  children: (data: GraphDataState) => React.ReactNode;
  onDataUpdate?: (data: GraphData) => void;
  enableDuckDB?: boolean;
}

interface GraphDataState {
  data: GraphData | null;
  isLoading: boolean;
  error: Error | null;
  updateData: (newData: Partial<GraphData>) => void;
  refreshData: () => Promise<void>;
  clearData: () => void;
}

/**
 * GraphDataManager - Manages graph data state and transformations
 * 
 * Responsibilities:
 * - Data state management (nodes, links, stats)
 * - Data validation and normalization
 * - DuckDB integration for analytics
 * - Memory-efficient data updates
 */
export const GraphDataManager: React.FC<GraphDataManagerProps> = ({
  children,
  onDataUpdate,
  enableDuckDB = true
}) => {
  const [data, setData] = useState<GraphData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  
  // Use refs to prevent memory leaks
  const dataRef = useRef<GraphData | null>(null);
  const updateCallbackRef = useRef(onDataUpdate);
  
  // DuckDB integration
  const { connection: duckDBConnection, isReady: isDuckDBReady } = useDuckDB();
  
  // Update callback ref
  useEffect(() => {
    updateCallbackRef.current = onDataUpdate;
  }, [onDataUpdate]);
  
  // Validate and normalize node data
  const normalizeNode = useCallback((node: any): GraphNode => {
    return {
      id: String(node.id),
      label: node.label || node.id,
      node_type: node.node_type || 'Unknown',
      created_at: node.created_at || new Date().toISOString(),
      updated_at: node.updated_at || new Date().toISOString(),
      properties: node.properties || {},
      summary: node.summary || '',
      name: node.name || node.label || node.id
    };
  }, []);
  
  // Validate and normalize link data
  const normalizeLink = useCallback((link: any): GraphLink => {
    return {
      source: String(link.source || link.from),
      target: String(link.target || link.to),
      from: String(link.from || link.source),
      to: String(link.to || link.target),
      weight: link.weight || 1,
      edge_type: link.edge_type || 'RELATED_TO'
    };
  }, []);
  
  // Memory-efficient data update
  const updateData = useCallback((newData: Partial<GraphData>) => {
    setData(prevData => {
      if (!prevData) {
        const normalizedData: GraphData = {
          nodes: newData.nodes?.map(normalizeNode) || [],
          links: newData.links?.map(normalizeLink) || [],
          stats: newData.stats
        };
        dataRef.current = normalizedData;
        updateCallbackRef.current?.(normalizedData);
        return normalizedData;
      }
      
      // Merge data efficiently
      const updatedData: GraphData = {
        nodes: newData.nodes ? newData.nodes.map(normalizeNode) : prevData.nodes,
        links: newData.links ? newData.links.map(normalizeLink) : prevData.links,
        stats: newData.stats || prevData.stats
      };
      
      // Update ref
      dataRef.current = updatedData;
      
      // Notify update
      updateCallbackRef.current?.(updatedData);
      
      return updatedData;
    });
  }, [normalizeNode, normalizeLink]);
  
  // Load initial data
  const refreshData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      // Fetch from API
      const response = await fetch('/api/graph/data');
      if (!response.ok) {
        throw new Error(`Failed to fetch graph data: ${response.statusText}`);
      }
      
      const rawData = await response.json();
      
      // Validate and normalize
      const normalizedData: GraphData = {
        nodes: rawData.nodes?.map(normalizeNode) || [],
        links: rawData.edges?.map(normalizeLink) || [],
        stats: rawData.stats
      };
      
      // Store in DuckDB if enabled
      if (enableDuckDB && isDuckDBReady && duckDBConnection) {
        try {
          // Create tables and insert data
          await duckDBConnection.query(`
            CREATE TABLE IF NOT EXISTS nodes AS 
            SELECT * FROM read_json_auto('${JSON.stringify(normalizedData.nodes)}')
          `);
          
          await duckDBConnection.query(`
            CREATE TABLE IF NOT EXISTS edges AS 
            SELECT * FROM read_json_auto('${JSON.stringify(normalizedData.links)}')
          `);
          
          logger.log('GraphDataManager: Data loaded into DuckDB');
        } catch (duckError) {
          logger.warn('GraphDataManager: Failed to load data into DuckDB:', duckError);
        }
      }
      
      updateData(normalizedData);
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Unknown error');
      setError(error);
      logger.error('GraphDataManager: Failed to load data:', error);
    } finally {
      setIsLoading(false);
    }
  }, [enableDuckDB, isDuckDBReady, duckDBConnection, normalizeNode, normalizeLink, updateData]);
  
  // Clear data and free memory
  const clearData = useCallback(() => {
    setData(null);
    dataRef.current = null;
    setError(null);
    logger.log('GraphDataManager: Data cleared');
  }, []);
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      dataRef.current = null;
      logger.log('GraphDataManager: Cleanup on unmount');
    };
  }, []);
  
  // Memoize state object to prevent unnecessary re-renders
  const state = useMemo<GraphDataState>(() => ({
    data,
    isLoading,
    error,
    updateData,
    refreshData,
    clearData
  }), [data, isLoading, error, updateData, refreshData, clearData]);
  
  return <>{children(state)}</>;
};

export default GraphDataManager;