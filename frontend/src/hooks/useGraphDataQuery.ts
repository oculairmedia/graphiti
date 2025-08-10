import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import { graphClient } from '../api/graphClient';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import { useGraphDataDiff } from './useGraphDataDiff';
import { useGraphConfig } from '../contexts/GraphConfigProvider';
import { useDuckDB } from '../contexts/DuckDBProvider';
import { useRustWebSocket } from '../contexts/RustWebSocketProvider';
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
  const { getDuckDBConnection } = useDuckDB();
  const { subscribe } = useRustWebSocket();
  
  // State for DuckDB-sourced UI data
  const [duckDBData, setDuckDBData] = useState<{ nodes: GraphNode[], edges: GraphLink[] } | null>(null);
  const [isDuckDBLoading, setIsDuckDBLoading] = useState(true); // Start with loading true
  const [hasInitialData, setHasInitialData] = useState(false); // Track if we've ever loaded data
  
  // Flag to prevent re-fetching after initial load
  const hasFetchedDuckDBRef = useRef(false);
  const lastFetchTimeRef = useRef(0);
  
  // Skip JSON fetch if using DuckDB (Arrow format is faster)
  const skipJsonFetch = false; // Use JSON fetch as fallback when Arrow data is not available
  
  // Use progressive loading for large graphs
  const INITIAL_LOAD_LIMIT = 1000; // Start with 1000 most important nodes
  const USE_PROGRESSIVE_LOADING = true; // Enable progressive loading
  
  // Fetch graph data from Rust server (disabled when using Arrow)
  const { data: jsonData, isLoading: isJsonLoading, error } = useQuery({
    queryKey: ['graphData'], // Remove config dependencies to prevent refetches on config changes
    queryFn: async () => {
      if (skipJsonFetch) {
        // Return empty data - we'll use Arrow format from DuckDB instead
        return { nodes: [], edges: [] };
      }
      
      // Use progressive loading for better initial performance
      const limit = USE_PROGRESSIVE_LOADING ? INITIAL_LOAD_LIMIT : 100000;
      
      // Always fetch entire graph to maintain stability (or initial batch for progressive)
      const result = await graphClient.getGraphData({ 
        query_type: 'entire_graph',
        limit: limit
      });
      return result;
    },
    enabled: !skipJsonFetch, // Disable JSON fetch when using Arrow
    staleTime: 5 * 60 * 1000, // Consider data fresh for 5 minutes
    cacheTime: 10 * 60 * 1000, // Keep in cache for 10 minutes
  });
  
  // Define fetchDuckDBData as a stable callback so it can be called from multiple places
  const fetchDuckDBData = useCallback(async (forceRefresh = false) => {
    // Skip if already fetched (unless forcing refresh)
    if (hasFetchedDuckDBRef.current && !forceRefresh) {
      return;
    }
    
    // Throttle fetches to prevent rapid re-fetching (minimum 1 second between fetches)
    const now = Date.now();
    if (now - lastFetchTimeRef.current < 1000) {
      return;
    }
    
    const connection = getDuckDBConnection();
    if (!connection?.connection) {
      // If no connection yet, don't mark as fetched so we can retry
      // Keep loading state true until we can actually fetch
      return;
    }
    
    // Mark as fetching to prevent concurrent fetches
    hasFetchedDuckDBRef.current = true;
    lastFetchTimeRef.current = now;
    setIsDuckDBLoading(true);
    
    try {
      // Query nodes and edges from DuckDB - MUST ORDER BY idx to match Cosmograph indices
      const [nodesResult, edgesResult] = await Promise.all([
        connection.connection.query('SELECT * FROM nodes ORDER BY idx'),
        connection.connection.query('SELECT * FROM edges ORDER BY sourceidx, targetidx')
      ]);
      
      if (nodesResult && edgesResult) {
        // Convert Arrow tables to JavaScript arrays
        const nodesArray = nodesResult.toArray();
        const edgesArray = edgesResult.toArray();
        
        // Transform to GraphNode format - PRESERVE idx field for proper indexing
        const nodes: GraphNode[] = nodesArray.map((n: any, arrayIndex) => ({
            id: n.id,
            idx: n.idx !== undefined ? n.idx : arrayIndex,  // Preserve DuckDB idx or use array index
            label: n.label || n.id,
            name: n.properties?.name || n.name || n.label || n.id,  // Use name from properties or direct field
            node_type: n.node_type || 'Unknown',
            summary: n.summary || null,
            size: n.degree_centrality || 1,
            created_at: n.created_at,
            properties: {
              idx: n.idx !== undefined ? n.idx : arrayIndex,  // Also store in properties for access
              degree_centrality: n.degree_centrality || 0,
              pagerank_centrality: n.pagerank_centrality || n.pagerank || 0,
              betweenness_centrality: n.betweenness_centrality || 0,
              eigenvector_centrality: n.eigenvector_centrality || 0,
              degree: n.degree || 0,
              connections: n.connections || n.degree || 0,
              created: n.created_at,
              date: n.created_at,
              ...n // Include all other properties
            }
        }));
        
        // Create node index map for edge indices
        const nodeIndexMap = new Map<string, number>();
        nodes.forEach((node, idx) => {
          nodeIndexMap.set(String(node.id), idx);
        });
        
        // Transform to GraphLink format with indices
        const edges: GraphLink[] = edgesArray.map((e: any) => ({
            id: `${e.source}-${e.target}`,
            source: e.source,
            target: e.target || e.targetidx,
            from: e.source,
            to: e.target || e.targetidx,
            sourceIndex: nodeIndexMap.get(String(e.source)) ?? -1,
            targetIndex: nodeIndexMap.get(String(e.target || e.targetidx)) ?? -1,
            edge_type: e.edge_type || '',
            weight: e.weight || 1,
            created_at: e.created_at,
            updated_at: e.updated_at
        }));
        
        // Only update if data has actually changed
        setDuckDBData(prevData => {
            // Check if data is the same
            if (prevData && 
                prevData.nodes.length === nodes.length && 
                prevData.edges.length === edges.length) {
              // Do a quick check on first few items to see if it's the same data
              const sameNodes = prevData.nodes[0]?.id === nodes[0]?.id && 
                               prevData.nodes[1]?.id === nodes[1]?.id;
              const sameEdges = prevData.edges[0]?.id === edges[0]?.id && 
                               prevData.edges[1]?.id === edges[1]?.id;
              
              if (sameNodes && sameEdges) {
                // Data hasn't changed, return previous reference
                return prevData;
              }
            }
            
            // Data has changed, update it
            logger.log('Loaded UI data from DuckDB:', nodes.length, 'nodes,', edges.length, 'edges');
            console.log('[useGraphDataQuery] DuckDB data loaded:', { 
              nodeCount: nodes.length, 
              edgeCount: edges.length,
              firstNode: nodes[0],
              firstEdge: edges[0]
            });
            
            return { nodes, edges };
        });
        
        setHasInitialData(true); // Mark that we have loaded data at least once
      }
    } catch (error) {
      logger.error('Failed to query DuckDB for UI data:', error);
    } finally {
      setIsDuckDBLoading(false);
    }
  }, [getDuckDBConnection]);

  // Refresh function that forces re-fetch
  const refreshDuckDBData = useCallback(() => {
    console.log('[useGraphDataQuery] Refreshing DuckDB data after WebSocket update');
    hasFetchedDuckDBRef.current = false;
    fetchDuckDBData(true);
  }, [fetchDuckDBData]);

  // Subscribe to WebSocket updates and refresh data
  useEffect(() => {
    const unsubscribe = subscribe((update) => {
      if (update.type === 'graph:delta' && update.data) {
        // Delay refresh slightly to ensure DuckDB has been updated
        console.log('[useGraphDataQuery] Received delta update, scheduling refresh');
        setTimeout(refreshDuckDBData, 100);
      }
    });
    
    return unsubscribe;
  }, [subscribe, refreshDuckDBData]);

  // Initial fetch and retry logic
  useEffect(() => {
    // Initial fetch attempt
    fetchDuckDBData();
    
    // Only set up retry interval if we haven't fetched yet
    let intervalId: NodeJS.Timeout | null = null;
    if (!hasFetchedDuckDBRef.current) {
      intervalId = setInterval(() => {
        if (!hasFetchedDuckDBRef.current) {
          fetchDuckDBData();
        } else if (intervalId) {
          clearInterval(intervalId);
          intervalId = null;
        }
      }, 500); // Reduced frequency from 100ms to 500ms
    }
    
    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [fetchDuckDBData]);
  
  // Use DuckDB data if available, otherwise fall back to JSON data
  // Memoize the data to prevent unnecessary recalculations
  const data = useMemo(() => {
    return duckDBData || jsonData || { nodes: [], edges: [] };
  }, [duckDBData, jsonData]);
  
  // Consider loading if we're fetching data OR haven't loaded initial data yet
  const isLoading = (isDuckDBLoading || isJsonLoading) || (!hasInitialData && !duckDBData && !jsonData);
  
  // Debug logging only when data actually changes
  useEffect(() => {
    if (data && (data.nodes.length > 0 || data.edges.length > 0)) {
      console.log('[useGraphDataQuery] Data updated:', {
        hasDuckDBData: !!duckDBData,
        hasJsonData: !!jsonData,
        nodeCount: data?.nodes?.length || 0,
        edgeCount: data?.edges?.length || 0,
        isDuckDBLoading,
        isJsonLoading
      });
    }
  }, [data?.nodes?.length, data?.edges?.length]); // Only log when counts change

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
    // Skip filter if it only contains "Entity" (likely bad persisted state)
    const shouldApplyTypeFilter = filterConfig.filteredNodeTypes.length > 0 && 
      !(filterConfig.filteredNodeTypes.length === 1 && filterConfig.filteredNodeTypes[0] === 'Entity');
    
    if (shouldApplyTypeFilter && !filterConfig.filteredNodeTypes.includes(node.node_type)) {
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
      const topNodes = nodesWithScore.slice(0, MAX_RENDERED_NODES).map(item => item.node);
      
      // CRITICAL: Sort back by original idx to preserve index mapping for Cosmograph
      finalNodes = topNodes.sort((a, b) => {
        const aIdx = a.idx !== undefined ? a.idx : (a.properties?.idx ?? 0);
        const bIdx = b.idx !== undefined ? b.idx : (b.properties?.idx ?? 0);
        return aIdx - bIdx;
      });
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
    refreshDuckDBData,
  };
}