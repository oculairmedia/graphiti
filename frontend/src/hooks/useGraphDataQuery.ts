import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import { graphClient } from '../api/graphClient';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import { useGraphDataDiff } from './useGraphDataDiff';
import { useGraphConfig } from '../contexts/GraphConfigProvider';
import { logger } from '../utils/logger';

interface FilterConfig {
  nodeTypeVisibility: Record<string, boolean>;
  filteredNodeTypes: string[];
  minDegree: number;
  maxDegree: number;
  minPagerank: number;
  maxPagerank: number;
  minBetweenness: number;
  maxBetweenness: number;
  minEigenvector: number;
  maxEigenvector: number;
  minConnections: number;
  maxConnections: number;
  startDate?: Date;
  endDate?: Date;
}

interface TransformedData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export function useGraphDataQuery() {
  const { config, updateNodeTypeConfigurations } = useGraphConfig();
  
  // Fetch graph data from Rust server
  const { data, isLoading, error } = useQuery({
    queryKey: ['graphData', config.queryType, config.nodeLimit],
    queryFn: async () => {
      const result = await graphClient.getGraphData({ 
        query_type: config.queryType,
        limit: config.nodeLimit 
      });
      return result;
    },
  });

  // Use data diffing to detect changes
  const dataDiff = useGraphDataDiff(data || null);
  
  // State for incremental updates
  const [isIncrementalUpdate, setIsIncrementalUpdate] = useState(false);
  const [isGraphInitialized, setIsGraphInitialized] = useState(false);
  
  // Stable data references to prevent cascade re-renders during incremental updates
  const stableDataRef = useRef<{ nodes: GraphNode[], edges: GraphLink[] } | null>(null);
  const stableTransformedDataRef = useRef<TransformedData | null>(null);
  
  // Handle initial load separately from incremental updates
  useEffect(() => {
    if (dataDiff.isInitialLoad && !isGraphInitialized) {
      setIsGraphInitialized(true);
      // Store initial stable data reference
      if (data) {
        stableDataRef.current = { nodes: [...data.nodes], edges: [...data.edges] };
      }
    }
  }, [dataDiff.isInitialLoad, isGraphInitialized, data]);

  // Reset incremental update flag when appropriate
  useEffect(() => {
    // Reset incremental update flag when we get a completely new dataset
    if (data && !dataDiff.hasChanges && isIncrementalUpdate) {
      setIsIncrementalUpdate(false);
      // Clear filter cache on data reset
      filterCacheRef.current.clear();
    }
  }, [data, dataDiff.hasChanges, isIncrementalUpdate]);

  // Memoize node types to avoid recalculation
  const nodeTypes = useMemo(() => {
    if (!data?.nodes || data.nodes.length === 0) return [];
    return [...new Set(data.nodes.map(node => node.node_type).filter(Boolean))].sort();
  }, [data?.nodes]);
  
  // Update node type configurations when node types change
  useEffect(() => {
    if (nodeTypes.length > 0) {
      updateNodeTypeConfigurations(nodeTypes);
    }
  }, [nodeTypes, updateNodeTypeConfigurations]);

  // Create stable filter config to prevent unnecessary recalculations
  const filterConfig = useMemo<FilterConfig>(() => ({
    nodeTypeVisibility: config.nodeTypeVisibility,
    filteredNodeTypes: config.filteredNodeTypes,
    minDegree: config.minDegree,
    maxDegree: config.maxDegree,
    minPagerank: config.minPagerank,
    maxPagerank: config.maxPagerank,
    minBetweenness: config.minBetweenness,
    maxBetweenness: config.maxBetweenness,
    minEigenvector: config.minEigenvector,
    maxEigenvector: config.maxEigenvector,
    minConnections: config.minConnections,
    maxConnections: config.maxConnections,
    startDate: config.startDate,
    endDate: config.endDate
  }), [
    config.nodeTypeVisibility,
    config.filteredNodeTypes,
    config.minDegree,
    config.maxDegree,
    config.minPagerank,
    config.maxPagerank,
    config.minBetweenness,
    config.maxBetweenness,
    config.minEigenvector,
    config.maxEigenvector,
    config.minConnections,
    config.maxConnections,
    config.startDate,
    config.endDate
  ]);

  // Cache for filter results to avoid recalculating for the same nodes
  const filterCacheRef = useRef(new Map<string, boolean>());
  
  // Memoize filter function to prevent recreation
  const nodePassesFilters = useCallback((node: GraphNode, filterConfig: FilterConfig) => {
    // Create cache key from node ID and filter config hash
    const cacheKey = `${node.id}:${JSON.stringify(filterConfig)}`;
    
    // Check cache first
    const cached = filterCacheRef.current.get(cacheKey);
    if (cached !== undefined) {
      return cached;
    }
    // Basic node type visibility check
    const nodeType = node.node_type as keyof typeof filterConfig.nodeTypeVisibility;
    if (filterConfig.nodeTypeVisibility[nodeType] === false) {
      filterCacheRef.current.set(cacheKey, false);
      return false;
    }
    
    // Node type filter - only apply if we have filtered types configured
    if (filterConfig.filteredNodeTypes.length > 0 && !filterConfig.filteredNodeTypes.includes(node.node_type)) {
      filterCacheRef.current.set(cacheKey, false);
      return false;
    }
    
    // Skip metric filters if all at default values
    const hasMetricFilters = filterConfig.minDegree > 0 || filterConfig.maxDegree < 100 ||
                           filterConfig.minPagerank > 0 || filterConfig.maxPagerank < 1 ||
                           filterConfig.minBetweenness > 0 || filterConfig.maxBetweenness < 1 ||
                           filterConfig.minEigenvector > 0 || filterConfig.maxEigenvector < 1;
    
    if (hasMetricFilters) {
      // Degree centrality filter
      const degree = node.properties?.degree_centrality || 0;
      const degreePercent = Math.min((degree / 100) * 100, 100);
      if (degreePercent < filterConfig.minDegree || degreePercent > filterConfig.maxDegree) {
        filterCacheRef.current.set(cacheKey, false);
        return false;
      }
      
      // PageRank filter
      const pagerank = node.properties?.pagerank_centrality || node.properties?.pagerank || 0;
      const pagerankPercent = Math.min((pagerank / 0.1) * 100, 100);
      if (pagerankPercent < filterConfig.minPagerank || pagerankPercent > filterConfig.maxPagerank) {
        filterCacheRef.current.set(cacheKey, false);
        return false;
      }
      
      // Betweenness centrality filter
      const betweenness = node.properties?.betweenness_centrality || 0;
      const betweennessPercent = Math.min((betweenness / 1) * 100, 100);
      if (betweennessPercent < filterConfig.minBetweenness || betweennessPercent > filterConfig.maxBetweenness) {
        filterCacheRef.current.set(cacheKey, false);
        return false;
      }
      
      // Eigenvector centrality filter
      const eigenvector = node.properties?.eigenvector_centrality || 0;
      const eigenvectorPercent = Math.min((eigenvector / 1) * 100, 100);
      if (eigenvectorPercent < filterConfig.minEigenvector || eigenvectorPercent > filterConfig.maxEigenvector) {
        filterCacheRef.current.set(cacheKey, false);
        return false;
      }
    }
    
    // Connection count filter
    if (filterConfig.minConnections > 0 || filterConfig.maxConnections < 1000) {
      const connections = node.properties?.degree || node.properties?.connections || 0;
      if (connections < filterConfig.minConnections || connections > filterConfig.maxConnections) {
        filterCacheRef.current.set(cacheKey, false);
        return false;
      }
    }
    
    // Date range filter
    if (filterConfig.startDate || filterConfig.endDate) {
      const nodeDate = node.created_at || node.properties?.created || node.properties?.date;
      if (nodeDate) {
        const date = new Date(nodeDate);
        if (filterConfig.startDate && date < new Date(filterConfig.startDate)) {
          filterCacheRef.current.set(cacheKey, false);
          return false;
        }
        if (filterConfig.endDate && date > new Date(filterConfig.endDate)) {
          filterCacheRef.current.set(cacheKey, false);
          return false;
        }
      }
    }
    
    // Cache the result
    filterCacheRef.current.set(cacheKey, true);
    
    // Clear cache if it gets too large
    if (filterCacheRef.current.size > 10000) {
      filterCacheRef.current.clear();
    }
    
    return true;
  }, []);

  const transformedData = useMemo<TransformedData>(() => {
    // During incremental updates, return the exact same object reference
    if (isIncrementalUpdate && stableTransformedDataRef.current) {
      return stableTransformedDataRef.current;
    }
    
    // During incremental updates, use stable data to prevent cascade re-renders
    const sourceData = isIncrementalUpdate ? stableDataRef.current : data;
    
    if (!sourceData) {
      logger.warn('GraphViz: No source data available', { isIncrementalUpdate, hasData: !!data });
      return { nodes: [], links: [] };
    }
    
    const visibleNodes = sourceData.nodes.filter(node => nodePassesFilters(node, filterConfig));

    // Virtualization: For very large graphs (>10k nodes), prioritize most important nodes
    let finalNodes = visibleNodes;
    const LARGE_GRAPH_THRESHOLD = 10000;
    const MAX_RENDERED_NODES = 5000;

    if (visibleNodes.length > LARGE_GRAPH_THRESHOLD) {
      // Pre-calculate importance scores
      const nodesWithScore = visibleNodes.map(node => ({
        node,
        importanceScore: (node.properties?.degree_centrality || 0) * 0.4 + 
                        (node.properties?.pagerank_centrality || node.properties?.pagerank || 0) * 1000 * 0.4 + 
                        (node.properties?.betweenness_centrality || 0) * 0.2
      }));

      // Sort by importance and take top N nodes
      nodesWithScore.sort((a, b) => b.importanceScore - a.importanceScore);
      finalNodes = nodesWithScore
        .slice(0, MAX_RENDERED_NODES)
        .map(item => item.node);
    }
    
    const visibleNodeIds = new Set(finalNodes.map(n => n.id));
    
    const filteredLinks = sourceData.edges
      .filter(edge => visibleNodeIds.has(edge.from) && visibleNodeIds.has(edge.to))
      .map(edge => ({
        ...edge,
        source: edge.from,
        target: edge.to,
      }));
    
    const newTransformedData = {
      nodes: finalNodes,
      links: filteredLinks,
    };
    
    // Update stable reference when not in incremental mode
    if (!isIncrementalUpdate) {
      stableTransformedDataRef.current = newTransformedData;
    }
    
    return newTransformedData;
  }, [data, isIncrementalUpdate, filterConfig, nodePassesFilters]);

  return {
    data,
    transformedData,
    isLoading,
    error,
    dataDiff,
    isIncrementalUpdate,
    setIsIncrementalUpdate,
    isGraphInitialized,
    stableDataRef,
  };
}