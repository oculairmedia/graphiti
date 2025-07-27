import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { graphClient } from '../api/graphClient';
import { CentralityMetrics, BulkCentralityResponse, CentralityStats } from '../api/types';

// Hook to fetch centrality for a single node
export function useNodeCentrality(nodeId: string | null, enabled = true) {
  return useQuery({
    queryKey: ['centrality', nodeId],
    queryFn: () => graphClient.getNodeCentrality(nodeId!),
    enabled: enabled && !!nodeId,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// Hook to fetch centrality for multiple nodes
export function useBulkCentrality(nodeIds: string[], enabled = true) {
  return useQuery({
    queryKey: ['centrality', 'bulk', nodeIds],
    queryFn: () => graphClient.getBulkCentrality(nodeIds),
    enabled: enabled && nodeIds.length > 0,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// Hook to fetch centrality statistics
export function useCentralityStats() {
  return useQuery({
    queryKey: ['centrality', 'stats'],
    queryFn: () => graphClient.getCentralityStats(),
    staleTime: 10 * 60 * 1000, // 10 minutes
  });
}

// Mutation to prefetch centrality data
export function usePrefetchCentrality() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (nodeIds: string[]) => {
      return graphClient.getBulkCentrality(nodeIds);
    },
    onSuccess: (data: BulkCentralityResponse) => {
      // Cache individual node centrality data
      Object.entries(data).forEach(([nodeId, metrics]) => {
        queryClient.setQueryData(['centrality', nodeId], metrics);
      });
    },
  });
}

// Hook to get centrality with fallback to node properties
export function useNodeCentralityWithFallback(nodeId: string | null, nodeProperties?: Record<string, unknown>) {
  // Disable API calls for now since the endpoints aren't implemented yet
  // Just use the fallback to node properties
  const { data: centralityData, isLoading, error } = useNodeCentrality(nodeId, false);
  
  // Always use properties for now
  if (nodeProperties) {
    const fallbackCentrality: CentralityMetrics = {
      degree: Number(nodeProperties.degree_centrality || 0),
      betweenness: Number(nodeProperties.betweenness_centrality || 0),
      pagerank: Number(nodeProperties.pagerank_centrality || nodeProperties.pagerank || 0),
      eigenvector: Number(nodeProperties.eigenvector_centrality || 0),
    };
    
    return {
      centrality: fallbackCentrality,
      isLoading: false,
      source: 'properties' as const,
    };
  }
  
  // No data available
  return {
    centrality: null,
    isLoading: false,
    source: 'none' as const,
  };
}