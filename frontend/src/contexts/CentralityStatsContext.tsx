import React, { createContext, useContext, useMemo, ReactNode } from 'react';
import { GraphNode } from '../api/types';

export type ScalingMethod = 'moving-average' | 'iqr' | 'winsorized' | 'mad' | 'raw' | 'log-sensitivity';

interface CentralityStats {
  degree: { 
    min: number; 
    max: number; 
    mean: number; 
    median: number;
    q1: number;
    q3: number;
    iqr: number;
    mad: number;
    scalingMax: number;
    scalingMethod: ScalingMethod;
  };
  betweenness: { 
    min: number; 
    max: number; 
    mean: number; 
    median: number;
    q1: number;
    q3: number;
    iqr: number;
    mad: number;
    scalingMax: number;
    scalingMethod: ScalingMethod;
  };
  pagerank: { 
    min: number; 
    max: number; 
    mean: number; 
    median: number;
    q1: number;
    q3: number;
    iqr: number;
    mad: number;
    scalingMax: number;
    scalingMethod: ScalingMethod;
  };
  eigenvector: { 
    min: number; 
    max: number; 
    mean: number; 
    median: number;
    q1: number;
    q3: number;
    iqr: number;
    mad: number;
    scalingMax: number;
    scalingMethod: ScalingMethod;
  };
}

const CentralityStatsContext = createContext<CentralityStats | null>(null);

interface CentralityStatsProviderProps {
  children: ReactNode;
  nodes: GraphNode[];
  scalingMethod?: ScalingMethod;
}

/**
 * Calculate percentile from sorted array
 */
function getPercentile(sortedValues: number[], percentile: number): number {
  const index = percentile * (sortedValues.length - 1);
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  const weight = index % 1;
  
  if (upper >= sortedValues.length) return sortedValues[sortedValues.length - 1];
  if (lower < 0) return sortedValues[0];
  
  return sortedValues[lower] * (1 - weight) + sortedValues[upper] * weight;
}

/**
 * Calculate Median Absolute Deviation
 */
function calculateMAD(values: number[], median: number): number {
  const deviations = values.map(val => Math.abs(val - median));
  deviations.sort((a, b) => a - b);
  const mad = getPercentile(deviations, 0.5);
  return mad;
}

/**
 * Apply betweenness centrality gating to cap outlier influence
 */
function applyBetweennessGating(values: number[], mean: number): number[] {
  // Gate at mean + 2 standard deviations for betweenness centrality
  const variance = values.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / values.length;
  const stdDev = Math.sqrt(variance);
  const gateThreshold = mean + 2 * stdDev;
  
  return values.map(val => Math.min(val, gateThreshold));
}

/**
 * Calculate robust scaling maximum based on method
 */
function calculateScalingMax(values: number[], method: ScalingMethod, stats: any, metricType?: string): number {
  // Apply betweenness gating if this is betweenness centrality
  let processedValues = values;
  if (metricType === 'betweenness') {
    processedValues = applyBetweennessGating(values, stats.mean);
    // Recalculate max after gating
    const gatedMax = Math.max(...processedValues);
    stats = { ...stats, max: gatedMax };
  }
  
  switch (method) {
    case 'iqr':
      // Use Q3 + 1.5 * IQR as scaling maximum (outlier fence)
      return stats.q3 + 1.5 * stats.iqr;
    
    case 'winsorized':
      // Use 95th percentile for winsorization
      return getPercentile(processedValues, 0.95);
    
    case 'mad':
      // Use median + 3 * 1.4826 * MAD (equivalent to 3 sigma for normal distribution)
      return stats.median + 3 * 1.4826 * stats.mad;
    
    case 'raw':
      // Use absolute maximum (after gating for betweenness)
      return stats.max;
    
    case 'log-sensitivity':
      // Use logarithmic scaling for better sensitivity to small differences
      const epsilon = Math.max(stats.min * 0.001, 0.0000001); // Small offset to avoid log(0)
      const logMin = Math.log10(Math.max(stats.min, epsilon));
      const logMax = Math.log10(Math.max(stats.max, epsilon));
      
      // Return the scaling maximum in log space, then convert back
      const logScalingMax = logMin + (logMax - logMin) * 0.95; // Use 95% of log range
      return Math.pow(10, logScalingMax);
    
    case 'moving-average':
    default:
      // Use moving average of top 10% (existing behavior)
      const topPercentileCount = Math.max(1, Math.ceil(processedValues.length * 0.1));
      const topValues = processedValues.slice(-topPercentileCount);
      return topValues.reduce((sum, val) => sum + val, 0) / topValues.length;
  }
}

/**
 * Apply log sensitivity transformation to values for better visual distribution
 */
function applyLogSensitivity(values: number[], scalingMethod: ScalingMethod): number[] {
  if (scalingMethod !== 'log-sensitivity') {
    return values;
  }
  
  const epsilon = Math.max(Math.min(...values) * 0.001, 0.0000001);
  return values.map(val => {
    const adjustedVal = Math.max(val, epsilon);
    return Math.log10(adjustedVal);
  });
}

/**
 * Calculate centrality statistics for all metrics with robust scaling
 */
function calculateCentralityStats(nodes: GraphNode[], scalingMethod: ScalingMethod = 'iqr'): CentralityStats {
  const metrics = {
    degree: 'degree_centrality',
    betweenness: 'betweenness_centrality', 
    pagerank: 'pagerank_centrality',
    eigenvector: 'eigenvector_centrality'
  } as const;

  const stats = {} as CentralityStats;

  Object.entries(metrics).forEach(([key, propName]) => {
    const rawValues: number[] = [];
    
    // Extract values from nodes, checking both root level and properties
    nodes.forEach(node => {
      const value = (node as any)[propName] || node.properties?.[propName];
      if (typeof value === 'number' && !isNaN(value)) {
        rawValues.push(value);
      }
    });

    if (rawValues.length === 0) {
      stats[key as keyof CentralityStats] = { 
        min: 0, max: 0, mean: 0, median: 0, q1: 0, q3: 0, iqr: 0, mad: 0, 
        scalingMax: 0, scalingMethod 
      };
      return;
    }

    // Apply log sensitivity transformation if selected
    const values = applyLogSensitivity(rawValues, scalingMethod);
    values.sort((a, b) => a - b);
    
    // Basic statistics
    const min = values[0];
    const max = values[values.length - 1];
    const mean = values.reduce((sum, val) => sum + val, 0) / values.length;
    const median = getPercentile(values, 0.5);
    
    // Quartiles and IQR
    const q1 = getPercentile(values, 0.25);
    const q3 = getPercentile(values, 0.75);
    const iqr = q3 - q1;
    
    // MAD calculation
    const mad = calculateMAD(values, median);
    
    // Robust statistics object
    const robustStats = { min, max, mean, median, q1, q3, iqr, mad };
    
    // Calculate scaling maximum based on method, passing metric type for betweenness gating
    const scalingMax = Math.max(calculateScalingMax(values, scalingMethod, robustStats, key), min + 0.000001);

    stats[key as keyof CentralityStats] = { 
      ...robustStats, 
      scalingMax, 
      scalingMethod 
    };
  });

  return stats;
}

export const CentralityStatsProvider: React.FC<CentralityStatsProviderProps> = ({ 
  children, 
  nodes,
  scalingMethod = 'iqr'
}) => {
  const stats = useMemo(() => {
    if (!nodes || nodes.length === 0) {
      const defaultStats = {
        min: 0, max: 1, mean: 0.5, median: 0.5, q1: 0.25, q3: 0.75, 
        iqr: 0.5, mad: 0.25, scalingMax: 1, scalingMethod
      };
      return {
        degree: defaultStats,
        betweenness: defaultStats,
        pagerank: defaultStats,
        eigenvector: defaultStats
      };
    }
    return calculateCentralityStats(nodes, scalingMethod);
  }, [nodes, scalingMethod]);

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