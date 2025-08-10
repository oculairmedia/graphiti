import { useState, useEffect, useCallback, useRef } from 'react';
import { graphClient } from '../api/graphClient';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import { logger } from '../utils/logger';

interface ProgressiveGraphDataOptions {
  initialLimit?: number;
  batchSize?: number;
  loadingStrategy?: 'centrality' | 'temporal' | 'degree';
  minCentrality?: number;
  onProgress?: (loaded: number, total: number) => void;
}

interface ProgressiveGraphData {
  nodes: GraphNode[];
  links: GraphLink[];
  isLoading: boolean;
  isInitialLoadComplete: boolean;
  totalNodes: number;
  loadedNodes: number;
  loadMore: () => Promise<void>;
  loadAll: () => Promise<void>;
}

export function useProgressiveGraphData(options: ProgressiveGraphDataOptions = {}): ProgressiveGraphData {
  const {
    initialLimit = 500,  // Start with just 500 most important nodes
    batchSize = 250,     // Load 250 nodes at a time
    loadingStrategy = 'centrality',
    minCentrality = 0.01,
    onProgress
  } = options;

  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [links, setLinks] = useState<GraphLink[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isInitialLoadComplete, setIsInitialLoadComplete] = useState(false);
  const [totalNodes, setTotalNodes] = useState(0);
  const [loadedNodes, setLoadedNodes] = useState(0);
  
  const offsetRef = useRef(0);
  const loadedNodeIdsRef = useRef(new Set<string>());
  const isLoadingMoreRef = useRef(false);

  // Initial load - get the most important nodes first
  useEffect(() => {
    let cancelled = false;

    const loadInitialData = async () => {
      try {
        setIsLoading(true);
        logger.log('[Progressive] Loading initial batch:', initialLimit);

        // Get stats first to know total count
        const stats = await graphClient.getStats();
        if (cancelled) return;
        
        setTotalNodes(stats.nodes);
        
        // Load initial batch with centrality-based sorting
        const queryParams = {
          query_type: loadingStrategy === 'centrality' ? 'high_centrality' : 'entire_graph',
          limit: initialLimit,
          offset: 0
        };

        const result = await graphClient.getGraphData(queryParams);
        if (cancelled) return;

        // Track loaded node IDs
        result.nodes.forEach(node => loadedNodeIdsRef.current.add(node.id));
        
        // Filter edges to only include those between loaded nodes
        const filteredEdges = result.edges.filter(edge => 
          loadedNodeIdsRef.current.has(edge.source) && 
          loadedNodeIdsRef.current.has(edge.target)
        );

        setNodes(result.nodes);
        setLinks(filteredEdges);
        setLoadedNodes(result.nodes.length);
        offsetRef.current = result.nodes.length;
        setIsInitialLoadComplete(true);
        
        logger.log('[Progressive] Initial load complete:', {
          nodes: result.nodes.length,
          edges: filteredEdges.length,
          total: stats.nodes
        });

        if (onProgress) {
          onProgress(result.nodes.length, stats.nodes);
        }
      } catch (error) {
        logger.error('[Progressive] Initial load failed:', error);
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    loadInitialData();

    return () => {
      cancelled = true;
    };
  }, [initialLimit, loadingStrategy, onProgress]);

  // Load more nodes incrementally
  const loadMore = useCallback(async () => {
    if (isLoadingMoreRef.current || loadedNodes >= totalNodes) {
      return;
    }

    isLoadingMoreRef.current = true;
    setIsLoading(true);

    try {
      logger.log('[Progressive] Loading more nodes, offset:', offsetRef.current);

      const queryParams = {
        query_type: 'entire_graph',
        limit: batchSize,
        offset: offsetRef.current
      };

      const result = await graphClient.getGraphData(queryParams);

      // Filter out already loaded nodes (in case of duplicates)
      const newNodes = result.nodes.filter(node => !loadedNodeIdsRef.current.has(node.id));
      newNodes.forEach(node => loadedNodeIdsRef.current.add(node.id));

      // Get edges for the new batch
      const newEdges = result.edges.filter(edge => {
        const isNew = !links.some(
          existingEdge => 
            existingEdge.source === edge.source && 
            existingEdge.target === edge.target
        );
        return isNew && 
               loadedNodeIdsRef.current.has(edge.source) && 
               loadedNodeIdsRef.current.has(edge.target);
      });

      setNodes(prev => [...prev, ...newNodes]);
      setLinks(prev => [...prev, ...newEdges]);
      setLoadedNodes(prev => prev + newNodes.length);
      offsetRef.current += newNodes.length;

      logger.log('[Progressive] Loaded batch:', {
        newNodes: newNodes.length,
        newEdges: newEdges.length,
        totalLoaded: loadedNodes + newNodes.length
      });

      if (onProgress) {
        onProgress(loadedNodes + newNodes.length, totalNodes);
      }
    } catch (error) {
      logger.error('[Progressive] Load more failed:', error);
    } finally {
      setIsLoading(false);
      isLoadingMoreRef.current = false;
    }
  }, [loadedNodes, totalNodes, batchSize, links, onProgress]);

  // Load all remaining nodes
  const loadAll = useCallback(async () => {
    if (loadedNodes >= totalNodes) {
      return;
    }

    const remainingNodes = totalNodes - loadedNodes;
    const batches = Math.ceil(remainingNodes / batchSize);

    logger.log('[Progressive] Loading all remaining nodes in', batches, 'batches');

    for (let i = 0; i < batches; i++) {
      await loadMore();
      // Small delay between batches to prevent overwhelming the UI
      if (i < batches - 1) {
        await new Promise(resolve => setTimeout(resolve, 100));
      }
    }
  }, [loadedNodes, totalNodes, batchSize, loadMore]);

  return {
    nodes,
    links,
    isLoading,
    isInitialLoadComplete,
    totalNodes,
    loadedNodes,
    loadMore,
    loadAll
  };
}