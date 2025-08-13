/**
 * Graph Statistics Hook
 * Manages live statistics tracking for graph data
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import { calculateNodeStats, calculateNodeDegrees } from '../utils/graphNodeOperations';
import { calculateLinkStats } from '../utils/graphLinkOperations';
import { calculateGraphMetrics } from '../utils/graphMetrics';

/**
 * Core statistics interface
 */
export interface GraphStatistics {
  // Basic counts
  nodeCount: number;
  edgeCount: number;
  
  // Timestamps
  lastUpdated: number;
  lastDataChange: number;
  
  // Node statistics
  nodesByType: Map<string, number>;
  avgNodeDegree: number;
  maxNodeDegree: number;
  minNodeDegree: number;
  isolatedNodes: number;
  
  // Link statistics
  linksByType: Map<string, number>;
  avgLinkWeight: number;
  selfLoops: number;
  
  // Graph metrics
  density: number;
  
  // Centrality stats
  avgCentrality: number;
  maxCentrality: number;
  minCentrality: number;
  
  // Performance metrics
  updateCount: number;
  averageUpdateTime: number;
}

/**
 * Statistics update event
 */
export interface StatsUpdateEvent {
  type: 'full' | 'incremental' | 'removal';
  nodesDelta?: number;
  edgesDelta?: number;
  timestamp: number;
}

/**
 * Hook configuration
 */
export interface UseGraphStatisticsConfig {
  // Enable detailed statistics (may impact performance)
  detailed?: boolean;
  
  // Update throttle in milliseconds
  updateThrottle?: number;
  
  // Enable performance tracking
  trackPerformance?: boolean;
  
  // Callback for stats updates
  onStatsUpdate?: (stats: GraphStatistics) => void;
  
  // Callback for significant changes
  onSignificantChange?: (event: StatsUpdateEvent) => void;
}

/**
 * Graph Statistics Hook
 */
export function useGraphStatistics(
  nodes: GraphNode[],
  links: GraphLink[],
  config: UseGraphStatisticsConfig = {}
) {
  const {
    detailed = false,
    updateThrottle = 100,
    trackPerformance = false,
    onStatsUpdate,
    onSignificantChange
  } = config;

  // Core statistics state
  const [statistics, setStatistics] = useState<GraphStatistics>(() => ({
    nodeCount: 0,
    edgeCount: 0,
    lastUpdated: Date.now(),
    lastDataChange: Date.now(),
    nodesByType: new Map(),
    avgNodeDegree: 0,
    maxNodeDegree: 0,
    minNodeDegree: 0,
    isolatedNodes: 0,
    linksByType: new Map(),
    avgLinkWeight: 0,
    selfLoops: 0,
    density: 0,
    avgCentrality: 0,
    maxCentrality: 0,
    minCentrality: 0,
    updateCount: 0,
    averageUpdateTime: 0
  }));

  // Performance tracking
  const performanceRef = useRef({
    updateTimes: [] as number[],
    maxSamples: 100
  });

  // Update throttling
  const updateTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const pendingUpdateRef = useRef<(() => void) | null>(null);

  /**
   * Calculate detailed statistics
   */
  const calculateDetailedStats = useCallback((
    nodes: GraphNode[],
    links: GraphLink[]
  ): Partial<GraphStatistics> => {
    const startTime = performance.now();

    // Calculate node statistics
    const nodeStats = calculateNodeStats(nodes);
    
    // Calculate link statistics
    const linkStats = calculateLinkStats(links);
    
    // Calculate graph metrics
    const graphMetrics = calculateGraphMetrics(nodes, links);
    
    // Calculate node degrees
    const degrees = calculateNodeDegrees(nodes, links);
    const degreeValues = Array.from(degrees.values());
    
    // Calculate isolated nodes
    const isolatedNodes = degreeValues.filter(d => d === 0).length;
    
    // Performance tracking
    const updateTime = performance.now() - startTime;
    if (trackPerformance) {
      performanceRef.current.updateTimes.push(updateTime);
      if (performanceRef.current.updateTimes.length > performanceRef.current.maxSamples) {
        performanceRef.current.updateTimes.shift();
      }
    }

    return {
      nodesByType: nodeStats.byType,
      avgNodeDegree: graphMetrics.avgDegree,
      maxNodeDegree: graphMetrics.maxDegree,
      minNodeDegree: graphMetrics.minDegree,
      isolatedNodes,
      linksByType: linkStats.byType,
      avgLinkWeight: linkStats.avgWeight,
      selfLoops: linkStats.selfLoops,
      density: graphMetrics.density,
      avgCentrality: nodeStats.avgCentrality,
      maxCentrality: nodeStats.maxCentrality,
      minCentrality: nodeStats.minCentrality
    };
  }, [trackPerformance]);

  /**
   * Update statistics
   */
  const updateStatistics = useCallback((
    nodes: GraphNode[],
    links: GraphLink[],
    updateType: 'full' | 'incremental' | 'removal' = 'full'
  ) => {
    const update = () => {
      const startTime = performance.now();

      setStatistics(prev => {
        const baseStats: GraphStatistics = {
          ...prev,
          nodeCount: nodes.length,
          edgeCount: links.length,
          lastUpdated: Date.now(),
          lastDataChange: Date.now(),
          updateCount: prev.updateCount + 1
        };

        // Calculate detailed stats if enabled
        if (detailed) {
          const detailedStats = calculateDetailedStats(nodes, links);
          Object.assign(baseStats, detailedStats);
        }

        // Update average update time
        if (trackPerformance && performanceRef.current.updateTimes.length > 0) {
          const sum = performanceRef.current.updateTimes.reduce((a, b) => a + b, 0);
          baseStats.averageUpdateTime = sum / performanceRef.current.updateTimes.length;
        }

        return baseStats;
      });

      // Trigger update event
      const event: StatsUpdateEvent = {
        type: updateType,
        timestamp: Date.now()
      };

      if (updateType === 'incremental') {
        event.nodesDelta = nodes.length - statistics.nodeCount;
        event.edgesDelta = links.length - statistics.edgeCount;
      }

      // Check for significant changes
      const isSignificant = 
        Math.abs(nodes.length - statistics.nodeCount) > nodes.length * 0.1 ||
        Math.abs(links.length - statistics.edgeCount) > links.length * 0.1;

      if (isSignificant && onSignificantChange) {
        onSignificantChange(event);
      }

      const updateTime = performance.now() - startTime;
      console.debug(`[useGraphStatistics] Update completed in ${updateTime.toFixed(2)}ms`);
    };

    // Throttle updates
    if (updateThrottle > 0) {
      pendingUpdateRef.current = update;
      
      if (updateTimeoutRef.current) {
        clearTimeout(updateTimeoutRef.current);
      }
      
      updateTimeoutRef.current = setTimeout(() => {
        if (pendingUpdateRef.current) {
          pendingUpdateRef.current();
          pendingUpdateRef.current = null;
        }
        updateTimeoutRef.current = null;
      }, updateThrottle);
    } else {
      update();
    }
  }, [statistics.nodeCount, statistics.edgeCount, detailed, calculateDetailedStats, 
      trackPerformance, updateThrottle, onSignificantChange]);

  /**
   * Force immediate update
   */
  const forceUpdate = useCallback(() => {
    if (updateTimeoutRef.current) {
      clearTimeout(updateTimeoutRef.current);
      updateTimeoutRef.current = null;
    }
    
    if (pendingUpdateRef.current) {
      pendingUpdateRef.current();
      pendingUpdateRef.current = null;
    } else {
      updateStatistics(nodes, links, 'full');
    }
  }, [nodes, links, updateStatistics]);

  /**
   * Get specific statistics
   */
  const getNodeCountByType = useCallback((type: string): number => {
    return statistics.nodesByType.get(type) || 0;
  }, [statistics.nodesByType]);

  const getLinkCountByType = useCallback((type: string): number => {
    return statistics.linksByType.get(type) || 0;
  }, [statistics.linksByType]);

  /**
   * Get basic stats (lightweight)
   */
  const getBasicStats = useCallback(() => ({
    nodeCount: statistics.nodeCount,
    edgeCount: statistics.edgeCount,
    lastUpdated: statistics.lastUpdated
  }), [statistics.nodeCount, statistics.edgeCount, statistics.lastUpdated]);

  /**
   * Check if graph is empty
   */
  const isEmpty = useMemo(() => 
    statistics.nodeCount === 0 && statistics.edgeCount === 0,
    [statistics.nodeCount, statistics.edgeCount]
  );

  /**
   * Check if graph is dense
   */
  const isDense = useMemo(() => 
    statistics.density > 0.5,
    [statistics.density]
  );

  /**
   * Check if graph is sparse
   */
  const isSparse = useMemo(() => 
    statistics.density < 0.1,
    [statistics.density]
  );

  /**
   * Get performance metrics
   */
  const getPerformanceMetrics = useCallback(() => {
    if (!trackPerformance) {
      return null;
    }

    const times = performanceRef.current.updateTimes;
    if (times.length === 0) {
      return null;
    }

    return {
      averageUpdateTime: statistics.averageUpdateTime,
      minUpdateTime: Math.min(...times),
      maxUpdateTime: Math.max(...times),
      updateCount: statistics.updateCount,
      samples: times.length
    };
  }, [trackPerformance, statistics.averageUpdateTime, statistics.updateCount]);

  // Update statistics when data changes
  useEffect(() => {
    updateStatistics(nodes, links, 'full');
  }, [nodes, links]); // Intentionally omit updateStatistics to prevent loops

  // Trigger callback when stats update
  useEffect(() => {
    if (onStatsUpdate) {
      onStatsUpdate(statistics);
    }
  }, [statistics, onStatsUpdate]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (updateTimeoutRef.current) {
        clearTimeout(updateTimeoutRef.current);
      }
    };
  }, []);

  return {
    // Core statistics
    statistics,
    
    // Basic stats getter (for performance)
    getBasicStats,
    
    // Type-specific getters
    getNodeCountByType,
    getLinkCountByType,
    
    // State checks
    isEmpty,
    isDense,
    isSparse,
    
    // Actions
    forceUpdate,
    
    // Performance metrics
    getPerformanceMetrics,
    
    // Update function (for manual updates)
    updateStatistics
  };
}

/**
 * Simple statistics hook for basic counting
 * Lighter weight alternative when detailed stats aren't needed
 */
export function useSimpleGraphStatistics(
  nodes: GraphNode[],
  links: GraphLink[],
  onUpdate?: (stats: { nodeCount: number; edgeCount: number; lastUpdated: number }) => void
) {
  const [stats, setStats] = useState({
    nodeCount: nodes.length,
    edgeCount: links.length,
    lastUpdated: Date.now()
  });

  useEffect(() => {
    const newStats = {
      nodeCount: nodes.length,
      edgeCount: links.length,
      lastUpdated: Date.now()
    };
    
    setStats(newStats);
    
    if (onUpdate) {
      onUpdate(newStats);
    }
  }, [nodes.length, links.length, onUpdate]);

  return stats;
}