import { useState, useCallback, useEffect } from 'react';
import { useMutation } from '@tanstack/react-query';
import { graphitiClient, type GraphitiNodeSearchQuery } from '@/api/graphitiClient';
import type { NodeResult } from '@/api/types';
import type { GraphCanvasRef } from '@/components/GraphCanvas';
import { useDebounce } from './useDebounce';

export interface UseGraphitiSearchOptions {
  graphCanvasRef?: React.RefObject<GraphCanvasRef>;
  onNodeSelect?: (node: NodeResult) => void;
  defaultMaxNodes?: number;
}

export function useGraphitiSearch(options: UseGraphitiSearchOptions = {}) {
  const { graphCanvasRef, onNodeSelect, defaultMaxNodes = 20 } = options;
  
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [highlightedNodeIds, setHighlightedNodeIds] = useState<Set<string>>(new Set());
  
  // Debounce the search query
  const debouncedQuery = useDebounce(searchQuery, 300);

  // Search mutation
  const searchMutation = useMutation({
    mutationFn: (params: GraphitiNodeSearchQuery) => graphitiClient.searchNodes(params),
    onSuccess: (data) => {
      // Highlight all search results in the graph
      const nodeIds = new Set(data.nodes.map(node => node.uuid));
      setHighlightedNodeIds(nodeIds);
    },
  });

  // Perform search
  const search = useCallback((query: string, additionalParams?: Partial<GraphitiNodeSearchQuery>) => {
    if (!query.trim()) {
      searchMutation.reset();
      setHighlightedNodeIds(new Set());
      return;
    }

    searchMutation.mutate({
      query,
      max_nodes: defaultMaxNodes,
      ...additionalParams,
    });
  }, [searchMutation, defaultMaxNodes]);

  // Auto-search when debounced query changes
  useEffect(() => {
    if (debouncedQuery) {
      search(debouncedQuery);
    } else {
      searchMutation.reset();
      setHighlightedNodeIds(new Set());
    }
  }, [debouncedQuery, search, searchMutation]);

  // Focus on a specific node
  const focusNode = useCallback((nodeId: string) => {
    if (graphCanvasRef?.current) {
      // First, select the node
      graphCanvasRef.current.selectNodes([nodeId]);
      
      // Then focus on it
      setTimeout(() => {
        graphCanvasRef.current?.focusOnNodes([nodeId]);
      }, 100);
    }
    
    setSelectedNodeId(nodeId);
  }, [graphCanvasRef]);

  // Handle node selection from search results
  const selectNode = useCallback((node: NodeResult) => {
    focusNode(node.uuid);
    onNodeSelect?.(node);
  }, [focusNode, onNodeSelect]);

  // Clear highlights
  const clearHighlights = useCallback(() => {
    setHighlightedNodeIds(new Set());
    setSelectedNodeId(null);
    if (graphCanvasRef?.current) {
      graphCanvasRef.current.selectNodes([]);
    }
  }, [graphCanvasRef]);

  // Get edges for a node
  const getNodeEdgesMutation = useMutation({
    mutationFn: (nodeUuid: string) => graphitiClient.getEdgesByNode(nodeUuid),
  });

  return {
    // State
    searchQuery,
    setSearchQuery,
    searchResults: searchMutation.data?.nodes || [],
    isSearching: searchMutation.isPending,
    searchError: searchMutation.error,
    selectedNodeId,
    highlightedNodeIds,
    
    // Actions
    search,
    selectNode,
    focusNode,
    clearHighlights,
    
    // Edge queries
    getNodeEdges: getNodeEdgesMutation.mutate,
    nodeEdges: getNodeEdgesMutation.data,
    isLoadingEdges: getNodeEdgesMutation.isPending,
  };
}