import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import { graphClient } from '../api/graphClient';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import { useGraphDataDiff } from './useGraphDataDiff';
import { useGraphConfig } from '../hooks/useGraphConfigHooks';
import { useDuckDB } from '../contexts/DuckDBProvider';
import { useRustWebSocket } from '../contexts/RustWebSocketProvider';
import { useRealtimeDataSync } from './useRealtimeDataSync';
import { useGraphWebSocket } from './useGraphWebSocket';
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

// Compute node size based on the selected sizing strategy
function computeSizeFromStrategy(node: any, config: any): number {
  // Return normalized value (0-1 range) - renderer will handle scaling
  switch (config.sizeMapping) {
    case 'degree':
      return node.degree_centrality || 0.1;
    case 'betweenness':
      return node.betweenness_centrality || 0.1;
    case 'pagerank':
      return node.pagerank_centrality || node.pagerank || 0.1;
    case 'importance':
      return node.eigenvector_centrality || 0.1;
    case 'connections':
      // Same as degree but could use raw count if available
      return node.degree_centrality || 0.1;
    case 'uniform':
      return 0.5; // Middle value for uniform sizing
    case 'custom':
      // Use eigenvector as default for custom
      return node.eigenvector_centrality || node.pagerank_centrality || node.degree_centrality || 0.1;
    default:
      // Safe fallback using best available metric
      return node.degree_centrality || node.pagerank_centrality || 0.1;
  }
}

export function useGraphDataQuery() {
  const { config, updateNodeTypeConfigurations } = useGraphConfig();
  const { getDuckDBConnection, isInitialized: isDuckDBInitialized } = useDuckDB();
  const queryClient = useQueryClient();
  
  // State for DuckDB-sourced UI data
  const [duckDBData, setDuckDBData] = useState<{ nodes: GraphNode[], edges: GraphLink[] } | null>(null);
  const [isDuckDBLoading, setIsDuckDBLoading] = useState(true); // Start with loading true
  const [hasInitialData, setHasInitialData] = useState(false); // Track if we've ever loaded data
  
  // Flag to prevent re-fetching after initial load
  const hasFetchedDuckDBRef = useRef(false);
  const lastFetchTimeRef = useRef(0);
  
  // Skip JSON fetch if using DuckDB (Arrow format is faster)
  // TEMPORARY: Disable JSON/WebSocket fetch to use DuckDB data only
  const skipJsonFetch = true; // Disable WebSocket override issue
  
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
      // Optimize: Only fetch essential fields to reduce data transfer and parsing time
      const essentialNodeFields = 'id, idx, label, node_type, summary, size, color, ' +
        'degree_centrality, pagerank_centrality, betweenness_centrality, eigenvector_centrality, ' +
        'created_at, created_at_timestamp, x, y';
      const essentialEdgeFields = 'source, target, sourceidx, targetidx, edge_type, weight, strength';

      const [nodesResult, edgesResult] = await Promise.all([
        connection.connection.query(`SELECT ${essentialNodeFields} FROM nodes ORDER BY idx`),
        connection.connection.query(`SELECT ${essentialEdgeFields} FROM edges`)
      ]);
      
      if (nodesResult && edgesResult) {
        // Convert Arrow tables to JavaScript arrays
        const nodesArray = nodesResult.toArray();
        const edgesArray = edgesResult.toArray();
        
        // Transform to GraphNode format - PRESERVE idx field for proper indexing
        // Optimized: Direct property access (DuckDB WASM returns proper objects)
        const nodes: GraphNode[] = nodesArray.map((n: any, arrayIndex) => {
            // Normalize temporal fields - ensure both exist
            let created_at = n.created_at;
            let created_at_timestamp = n.created_at_timestamp;

            if (!created_at && created_at_timestamp) {
              const ts = Number(created_at_timestamp);
              if (!Number.isNaN(ts)) {
                created_at = new Date(ts).toISOString();
              }
            } else if (created_at && !created_at_timestamp) {
              created_at_timestamp = new Date(created_at).getTime();
            }

            // Fallback to synthetic values if both missing
            if (!created_at && !created_at_timestamp) {
              created_at_timestamp = Date.now();
              created_at = new Date(created_at_timestamp).toISOString();
            }

            return {
              id: n.id,
              idx: n.idx !== undefined ? n.idx : arrayIndex,  // Preserve DuckDB idx or use array index
              label: n.label || n.id,
              name: n.label || n.id,  // Use label as name
              node_type: n.node_type || 'Unknown',
              summary: n.summary || null,
              size: computeSizeFromStrategy(n, config),
              created_at,
              created_at_timestamp: created_at_timestamp || null,  // Add timestamp for timeline
              // Store centrality at the root level for direct access
              degree_centrality: n.degree_centrality || 0,
              pagerank_centrality: n.pagerank_centrality || 0,
              betweenness_centrality: n.betweenness_centrality || 0,
              eigenvector_centrality: n.eigenvector_centrality || 0,
              properties: {
                idx: n.idx !== undefined ? n.idx : arrayIndex,  // Also store in properties for access
                degree_centrality: n.degree_centrality || 0,
                pagerank_centrality: n.pagerank_centrality || 0,
                betweenness_centrality: n.betweenness_centrality || 0,
                eigenvector_centrality: n.eigenvector_centrality || 0,
                // Note: Removed misleading degree/connections properties that were incorrectly
                // derived from centrality * 100. Actual edge counts are now computed in GraphViz
                // using calculateNodeDegrees() for accurate connection counts.
                created: created_at,  // Now guaranteed to exist
                date: created_at,      // Now guaranteed to exist
                created_at: created_at,  // Now guaranteed to exist
                created_at_timestamp: created_at_timestamp  // Now guaranteed to exist
              }
            };
        });
        
        // Create node index map for edge indices
        const nodeIndexMap = new Map<string, number>();
        nodes.forEach((node, idx) => {
          nodeIndexMap.set(String(node.id), idx);
        });
        
        // Transform to GraphLink format with indices
        const edges: GraphLink[] = edgesArray.map((e: any) => {
            const edgeType = e.edge_type || '';
            
            // Calculate link strength based on edge type and config
            // Use dynamic values from UI config if link strength is enabled
            let strength = config.defaultLinkStrength || 1.0;
            if (config.linkStrengthEnabled) {
              if (edgeType === 'entity_entity' || edgeType === 'relates_to') {
                strength = config.entityEntityStrength || 1.5;  // Stronger Entity-Entity connections
              } else if (edgeType === 'episodic' || edgeType === 'temporal' || edgeType === 'mentioned_in') {
                strength = config.episodicStrength || 0.5;  // Weaker Episodic connections
              }
            }
            
            return {
                id: `${e.source}-${e.target}`,
                source: e.source,
                target: e.target,  // Always use UUID, no fallback to idx
                from: e.source,
                to: e.target,  // Always use UUID, no fallback to idx
                sourceIndex: nodeIndexMap.get(String(e.source)) ?? -1,
                targetIndex: nodeIndexMap.get(String(e.target)) ?? -1,  // Use actual target UUID
                edge_type: edgeType,
                weight: e.weight || 1,
                strength: strength,  // Add strength for link force variation
                created_at: e.created_at,
                updated_at: e.updated_at
            };
        });
        
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
            // Debug: Log node type distribution from DuckDB
            const duckDBNodeTypes = nodes.reduce((acc, node) => {
              acc[node.node_type] = (acc[node.node_type] || 0) + 1;
              return acc;
            }, {} as Record<string, number>);
            
            logger.log('Loaded UI data from DuckDB:', nodes.length, 'nodes,', edges.length, 'edges');
            console.log('[useGraphDataQuery] DuckDB data loaded:', { 
              nodeCount: nodes.length, 
              edgeCount: edges.length,
              nodeTypes: duckDBNodeTypes,
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
  
  // Set up WebSocket to listen for cache invalidation events
  useGraphWebSocket({
    enablePython: true,
    enableRust: false,
    onCacheInvalidate: (event) => {
      logger.log('[useGraphDataQuery] Cache invalidated, refetching data...');
      // Clear DuckDB cache and refetch
      refreshDuckDBData();
      // Also invalidate React Query cache if using JSON fetch
      if (!skipJsonFetch) {
        queryClient.invalidateQueries({ queryKey: ['graphData'] });
      }
    },
    onGraphUpdate: (event) => {
      logger.log('[useGraphDataQuery] Graph update received, refetching data...');
      // Clear cache and refetch on graph updates
      refreshDuckDBData();
    },
    debug: true
  });

  // Stable callbacks for real-time sync
  const handleRealtimeDataUpdate = useCallback(() => {
    logger.log('[useGraphDataQuery] Real-time update triggered, refreshing data');
    
    // Invalidate React Query cache to ensure fresh data
    queryClient.invalidateQueries({ queryKey: ['graphData'] });
    
    // Refresh DuckDB data
    refreshDuckDBData();
  }, [refreshDuckDBData, queryClient]);

  const handleRealtimeNotification = useCallback((notification: any) => {
    logger.log('[useGraphDataQuery] Received notification:', notification);
  }, []);

  // Integrate real-time data sync with WebSocket notifications
  const { pendingUpdate } = useRealtimeDataSync({
    enabled: true, // Re-enabled after fixing subscription issue
    debounceMs: 500, // Debounce rapid updates
    onDataUpdate: handleRealtimeDataUpdate,
    onNotification: handleRealtimeNotification,
  });

  // Initial fetch and retry logic
  useEffect(() => {
    // Always try to fetch on mount if DuckDB is ready
    if (isDuckDBInitialized && !hasFetchedDuckDBRef.current) {
      console.log('[useGraphDataQuery] DuckDB initialized, fetching data');
      fetchDuckDBData(true); // Fetch when DuckDB is ready
    }
    
    // Set up retry interval if we don't have data yet
    let intervalId: NodeJS.Timeout | null = null;
    if (isDuckDBInitialized && !hasFetchedDuckDBRef.current) {
      intervalId = setInterval(() => {
        if (!hasFetchedDuckDBRef.current && isDuckDBInitialized) {
          console.log('[useGraphDataQuery] Retrying DuckDB data fetch');
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDuckDBInitialized]); // Only depend on isDuckDBInitialized, not fetchDuckDBData
  
  // Use DuckDB data if available, otherwise fall back to JSON data
  // Memoize the data to prevent unnecessary recalculations
  const data = useMemo(() => {
    // Temporarily prioritize DuckDB data over WebSocket data
    // TODO: Fix WebSocket to send notifications instead of replacement data
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

  // PERFORMANCE FIX (GRAPH-39): LRU cache for filter results with max 1000 entries
  // Previous implementation grew to 10K entries before clearing entirely
  const filterCacheRef = useRef<Map<string, boolean>>(new Map());
  const LRU_CACHE_MAX_SIZE = 1000;

  // Precomputed filter config hash to avoid repeated JSON.stringify
  const filterConfigHashRef = useRef<string>('');

  // Compute lightweight filter hash (only when filterConfig changes)
  useEffect(() => {
    // Create hash from only the values that matter for filtering
    filterConfigHashRef.current = `${filterConfig.minDegree}_${filterConfig.maxDegree}_` +
      `${filterConfig.minPagerank}_${filterConfig.maxPagerank}_` +
      `${filterConfig.minBetweenness}_${filterConfig.maxBetweenness}_` +
      `${filterConfig.minEigenvector}_${filterConfig.maxEigenvector}_` +
      `${filterConfig.minConnections}_${filterConfig.maxConnections}_` +
      `${filterConfig.filteredNodeTypes.join(',')}_` +
      `${filterConfig.startDate || ''}_${filterConfig.endDate || ''}`;
  }, [filterConfig]);

  // Memoize filter function to prevent recreation
  const nodePassesFilters = useCallback((node: GraphNode, filterConfig: FilterConfig) => {
    // Create cache key using precomputed hash (60-80% faster than JSON.stringify)
    const cacheKey = `${node.id}:${filterConfigHashRef.current}`;

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
    // Skip filter if:
    // 1. Empty array (no filtering)
    // 2. Only contains "Entity" (likely bad persisted state from before Episodic was added)
    // 3. Contains both Entity and Episodic (showing all main types)
    const hasEntityAndEpisodic = filterConfig.filteredNodeTypes.includes('Entity') && 
                                 filterConfig.filteredNodeTypes.includes('Episodic');
    const shouldApplyTypeFilter = filterConfig.filteredNodeTypes.length > 0 && 
      !(filterConfig.filteredNodeTypes.length === 1 && filterConfig.filteredNodeTypes[0] === 'Entity') &&
      !hasEntityAndEpisodic;
    
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
    
    // Cache the result - PERFORMANCE FIX (GRAPH-39): LRU eviction instead of full clear
    filterCacheRef.current.set(cacheKey, true);
    
    // LRU eviction: remove oldest entries when cache exceeds max size
    if (filterCacheRef.current.size > LRU_CACHE_MAX_SIZE) {
      // Map maintains insertion order, so first entries are oldest
      const keysToDelete = Array.from(filterCacheRef.current.keys()).slice(0, 100);
      keysToDelete.forEach(key => filterCacheRef.current.delete(key));
    }
    
    return true;
  }, []);

  // CRITICAL: Keep transformedData stable to prevent hover lag
  // Only recreate if the actual data content has changed
  const previousTransformedDataRef = useRef<TransformedData | null>(null);
  const previousFilterConfigRef = useRef<FilterConfig | null>(null);
  const previousDataRef = useRef<{ nodes: GraphNode[], edges: GraphLink[] } | null>(null);
  
  const transformedData = useMemo<TransformedData>(() => {
    // During incremental updates, return the exact same object reference
    if (isIncrementalUpdate && stableTransformedDataRef.current) {
      return stableTransformedDataRef.current;
    }

    // Optimized: Use reference equality instead of JSON.stringify
    const filterConfigChanged = filterConfig !== previousFilterConfigRef.current;
    const dataChanged = data !== previousDataRef.current;

    if (!filterConfigChanged && !dataChanged && previousTransformedDataRef.current) {
      // Nothing changed, return the exact same reference
      return previousTransformedDataRef.current;
    }

    // Update refs for next comparison
    previousFilterConfigRef.current = filterConfig;
    previousDataRef.current = data;
    
    // During incremental updates, use stable data to prevent cascade re-renders
    const sourceData = isIncrementalUpdate ? stableDataRef.current : data;
    
    if (!sourceData) {
      logger.warn('GraphViz: No source data available', { isIncrementalUpdate, hasData: !!data });
      // Return previous data if available to maintain stability
      return previousTransformedDataRef.current || { nodes: [], links: [] };
    }
    
    // Optimized: No filtering - use nodes directly (already sorted by idx from DuckDB)
    // Filtering is disabled to show full graph - future optimization can add back selective filtering
    const finalNodes = sourceData.nodes;
    
    // Optimized: Use edges directly - no filtering or mapping needed
    // Edges already have correct structure from DuckDB query
    const filteredLinks = sourceData.edges || [];
    
    const newTransformedData = {
      nodes: finalNodes,
      links: filteredLinks,
    };
    
    // Check if data actually changed by comparing node/link counts and first few items
    const hasDataChanged = !previousTransformedDataRef.current ||
      previousTransformedDataRef.current.nodes.length !== newTransformedData.nodes.length ||
      previousTransformedDataRef.current.links.length !== newTransformedData.links.length ||
      (newTransformedData.nodes[0]?.id !== previousTransformedDataRef.current.nodes[0]?.id);
    
    if (!hasDataChanged) {
      // Return the previous reference to maintain stability
      return previousTransformedDataRef.current;
    }
    
    // Update stable reference when not in incremental mode
    if (!isIncrementalUpdate) {
      stableTransformedDataRef.current = newTransformedData;
    }
    
    // Store for next comparison
    previousTransformedDataRef.current = newTransformedData;
    
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
    pendingUpdate, // Indicates if a real-time update is pending
  };
}