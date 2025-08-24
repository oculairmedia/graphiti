import React, { createContext, useContext, useMemo, ReactNode } from 'react';
import { GraphNode } from '../api/types';

interface CentralityStats {
  degree: { min: number; max: number; mean: number; scalingMax: number };
  betweenness: { min: number; max: number; mean: number; scalingMax: number };
  pagerank: { min: number; max: number; mean: number; scalingMax: number };
  eigenvector: { min: number; max: number; mean: number; scalingMax: number };
}

const CentralityStatsContext = createContext<CentralityStats | null>(null);

interface CentralityStatsProviderProps {
  children: ReactNode;
  nodes: GraphNode[];
}

/**
 * Calculate centrality statistics for all metrics
 */
function calculateCentralityStats(nodes: GraphNode[]): CentralityStats {
  const metrics = {
    degree: 'degree_centrality',
    betweenness: 'betweenness_centrality', 
    pagerank: 'pagerank_centrality',
    eigenvector: 'eigenvector_centrality'
  } as const;

  const stats = {} as CentralityStats;

  Object.entries(metrics).forEach(([key, propName]) => {
    const values: number[] = [];
    
    // Extract values from nodes, checking both root level and properties
    nodes.forEach(node => {
      const value = (node as any)[propName] || node.properties?.[propName];
      if (typeof value === 'number' && !isNaN(value)) {
        values.push(value);
      }
    });

    if (values.length === 0) {
      stats[key as keyof CentralityStats] = { min: 0, max: 0, mean: 0, scalingMax: 0 };
      return;
    }

    values.sort((a, b) => a - b);
    const min = values[0];
    const max = values[values.length - 1];
    const mean = values.reduce((sum, val) => sum + val, 0) / values.length;

    // Calculate moving average of top 10% of values for smoother scaling
    const topPercentileCount = Math.max(1, Math.ceil(values.length * 0.1));
    const topValues = values.slice(-topPercentileCount);
    const scalingMax = topValues.reduce((sum, val) => sum + val, 0) / topValues.length;

    stats[key as keyof CentralityStats] = { min, max, mean, scalingMax };
  });

  return stats;
}

export const CentralityStatsProvider: React.FC<CentralityStatsProviderProps> = ({ 
  children, 
  nodes 
}) => {
  const stats = useMemo(() => {
    if (!nodes || nodes.length === 0) {
      return {
        degree: { min: 0, max: 1, mean: 0.5, scalingMax: 1 },
        betweenness: { min: 0, max: 1, mean: 0.5, scalingMax: 1 },
        pagerank: { min: 0, max: 1, mean: 0.5, scalingMax: 1 },
        eigenvector: { min: 0, max: 1, mean: 0.5, scalingMax: 1 }
      };
    }
    return calculateCentralityStats(nodes);
  }, [nodes]);

  return (
    <CentralityStatsContext.Provider value={stats}>
      {children}
    </CentralityStatsContext.Provider>
  );
};

export const useCentralityStats = (): CentralityStats | null => {
  return useContext(CentralityStatsContext);
};

export { CentralityStatsContext };