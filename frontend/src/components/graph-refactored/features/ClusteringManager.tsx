import React, { useCallback, useMemo, useState, useEffect } from 'react';
import { GraphNode } from '../../../api/types';

export type ClusteringMethod = 'nodeType' | 'centrality' | 'community' | 'temporal' | 'custom' | 'none';
export type CentralityMetric = 'degree' | 'pagerank' | 'betweenness' | 'eigenvector';

export interface ClusteringConfig {
  method: ClusteringMethod;
  centralityMetric?: CentralityMetric;
  clusterStrength: number;
  customClusterFn?: (node: GraphNode, index: number) => string | number;
  temporalWindow?: number; // For temporal clustering
  communityAlgorithm?: 'louvain' | 'modularity'; // For community detection
}

interface ClusteringResult {
  clusterBy: string | undefined;
  clusterAssignments: (string | number)[];
  clusterStrengths: number[];
  clusterMapping: Map<unknown, number>;
  clusterPositions: Record<string, { x: number; y: number }>;
}

interface ClusteringManagerProps {
  nodes: GraphNode[];
  config: ClusteringConfig;
  onClusteringUpdate?: (result: ClusteringResult) => void;
  children?: React.ReactNode;
}

/**
 * ClusteringManager - Advanced clustering system for graph visualization
 * Supports multiple clustering methods including temporal and community detection
 */
export const ClusteringManager: React.FC<ClusteringManagerProps> = ({
  nodes,
  config,
  onClusteringUpdate,
  children
}) => {
  const [clusteringResult, setClusteringResult] = useState<ClusteringResult | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  // Generate cluster assignments based on method
  const generateClusterAssignments = useCallback((
    nodes: GraphNode[],
    config: ClusteringConfig
  ): ClusteringResult => {
    if (config.method === 'none' || !nodes.length) {
      return {
        clusterBy: undefined,
        clusterAssignments: [],
        clusterStrengths: [],
        clusterMapping: new Map(),
        clusterPositions: {}
      };
    }

    let clusterBy: string | undefined;
    const clusterAssignments: (string | number)[] = [];
    const clusterStrengths: number[] = [];
    const clusterMapping = new Map<unknown, number>();
    let clusterIndex = 0;

    switch (config.method) {
      case 'nodeType':
        clusterBy = 'node_type';
        nodes.forEach((node) => {
          const cluster = node.node_type || 'unknown';
          if (!clusterMapping.has(cluster)) {
            clusterMapping.set(cluster, clusterIndex++);
          }
          clusterAssignments.push(cluster);
          clusterStrengths.push(config.clusterStrength);
        });
        break;

      case 'centrality':
        clusterBy = config.centralityMetric || 'pagerank';
        nodes.forEach((node) => {
          const centrality = getCentralityValue(node, config.centralityMetric || 'pagerank');
          const cluster = getCentralityCluster(centrality);
          if (!clusterMapping.has(cluster)) {
            clusterMapping.set(cluster, clusterIndex++);
          }
          clusterAssignments.push(cluster);
          // Higher centrality nodes have stronger clustering
          clusterStrengths.push(config.clusterStrength * (0.5 + centrality * 0.5));
        });
        break;

      case 'temporal':
        clusterBy = 'temporal';
        const windowSize = config.temporalWindow || 86400000; // 24 hours default
        nodes.forEach((node) => {
          const timestamp = node.created_at ? new Date(node.created_at).getTime() : Date.now();
          const cluster = Math.floor(timestamp / windowSize);
          if (!clusterMapping.has(cluster)) {
            clusterMapping.set(cluster, clusterIndex++);
          }
          clusterAssignments.push(cluster);
          clusterStrengths.push(config.clusterStrength);
        });
        break;

      case 'community':
        // Simplified community detection (would use actual algorithm in production)
        clusterBy = 'community';
        const communities = detectCommunities(nodes, config.communityAlgorithm);
        communities.forEach((community, index) => {
          if (!clusterMapping.has(community)) {
            clusterMapping.set(community, clusterIndex++);
          }
          clusterAssignments.push(community);
          clusterStrengths.push(config.clusterStrength);
        });
        break;

      case 'custom':
        if (config.customClusterFn) {
          clusterBy = 'custom';
          nodes.forEach((node, index) => {
            const cluster = config.customClusterFn!(node, index);
            if (!clusterMapping.has(cluster)) {
              clusterMapping.set(cluster, clusterIndex++);
            }
            clusterAssignments.push(cluster);
            clusterStrengths.push(config.clusterStrength);
          });
        }
        break;
    }

    // Generate cluster positions
    const clusterPositions = generateClusterPositions(clusterMapping);

    return {
      clusterBy,
      clusterAssignments,
      clusterStrengths,
      clusterMapping,
      clusterPositions
    };
  }, []);

  // Get centrality value for a node
  const getCentralityValue = (node: GraphNode, metric: CentralityMetric): number => {
    const props = node.properties || {};
    switch (metric) {
      case 'degree':
        return props.degree_centrality || node.degree_centrality || 0;
      case 'pagerank':
        return props.pagerank_centrality || node.pagerank || 0;
      case 'betweenness':
        return props.betweenness_centrality || node.betweenness_centrality || 0;
      case 'eigenvector':
        return props.eigenvector_centrality || node.eigenvector_centrality || 0;
      default:
        return 0;
    }
  };

  // Determine cluster based on centrality value
  const getCentralityCluster = (centrality: number): string => {
    if (centrality < 0.2) return 'very_low';
    if (centrality < 0.4) return 'low';
    if (centrality < 0.6) return 'medium';
    if (centrality < 0.8) return 'high';
    return 'very_high';
  };

  // Simple community detection (placeholder for real algorithm)
  const detectCommunities = (
    nodes: GraphNode[], 
    algorithm?: 'louvain' | 'modularity'
  ): number[] => {
    // This is a simplified version - real implementation would use actual algorithms
    // For now, group by node type as a proxy for communities
    const communities: number[] = [];
    const typeMap = new Map<string, number>();
    let communityId = 0;

    nodes.forEach(node => {
      const type = node.node_type || 'default';
      if (!typeMap.has(type)) {
        typeMap.set(type, communityId++);
      }
      communities.push(typeMap.get(type)!);
    });

    return communities;
  };

  // Generate cluster positions in circular layout
  const generateClusterPositions = (
    clusterMapping: Map<unknown, number>,
    centerX: number = 0,
    centerY: number = 0,
    radius: number = 500
  ): Record<string, { x: number; y: number }> => {
    const positions: Record<string, { x: number; y: number }> = {};
    const numClusters = clusterMapping.size;
    
    if (numClusters === 0) return positions;
    
    const angleStep = (2 * Math.PI) / numClusters;
    
    clusterMapping.forEach((index, cluster) => {
      const angle = index * angleStep;
      positions[String(cluster)] = {
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle)
      };
    });
    
    return positions;
  };

  // Process clustering when nodes or config changes
  useEffect(() => {
    // Only process if we have nodes and not already processing
    if (nodes.length === 0 || isProcessing) return;
    
    setIsProcessing(true);
    
    // Use requestAnimationFrame for smooth updates
    const frame = requestAnimationFrame(() => {
      const result = generateClusterAssignments(nodes, config);
      setClusteringResult(result);
      onClusteringUpdate?.(result);
      setIsProcessing(false);
    });

    return () => {
      cancelAnimationFrame(frame);
    };
  }, [nodes.length, config.method, config.clusterStrength]); // Only depend on specific values, not entire objects

  // Apply clustering to nodes
  const clusteredNodes = useMemo(() => {
    if (!clusteringResult) return nodes;

    return nodes.map((node, index) => ({
      ...node,
      cluster: clusteringResult.clusterAssignments[index],
      clusterStrength: clusteringResult.clusterStrengths[index]
    }));
  }, [nodes, clusteringResult]);

  // Context value for child components
  const contextValue = useMemo(() => ({
    clusteringResult,
    clusteredNodes,
    isProcessing,
    applyCustomClustering: (fn: (node: GraphNode, index: number) => string | number) => {
      const newConfig: ClusteringConfig = {
        ...config,
        method: 'custom',
        customClusterFn: fn
      };
      const result = generateClusterAssignments(nodes, newConfig);
      setClusteringResult(result);
      onClusteringUpdate?.(result);
    }
  }), [clusteringResult, clusteredNodes, isProcessing, config, nodes, generateClusterAssignments, onClusteringUpdate]);

  return (
    <ClusteringContext.Provider value={contextValue}>
      {children}
    </ClusteringContext.Provider>
  );
};

// Context for clustering state
const ClusteringContext = React.createContext<{
  clusteringResult: ClusteringResult | null;
  clusteredNodes: GraphNode[];
  isProcessing: boolean;
  applyCustomClustering: (fn: (node: GraphNode, index: number) => string | number) => void;
}>({
  clusteringResult: null,
  clusteredNodes: [],
  isProcessing: false,
  applyCustomClustering: () => {}
});

export const useClustering = () => React.useContext(ClusteringContext);

// Hook for applying clustering to graph data
export const useClusteringEffect = (
  nodes: GraphNode[],
  config: ClusteringConfig
): {
  clusteredNodes: GraphNode[];
  clusterMapping: Map<unknown, number>;
  clusterPositions: Record<string, { x: number; y: number }>;
  isProcessing: boolean;
} => {
  const [state, setState] = useState({
    clusteredNodes: nodes,
    clusterMapping: new Map<unknown, number>(),
    clusterPositions: {} as Record<string, { x: number; y: number }>,
    isProcessing: false
  });

  useEffect(() => {
    setState(prev => ({ ...prev, isProcessing: true }));

    const processAsync = async () => {
      // Simulate async processing for large datasets
      await new Promise(resolve => setTimeout(resolve, 0));
      
      const manager = new ClusteringManager({
        nodes,
        config,
        onClusteringUpdate: (result) => {
          setState({
            clusteredNodes: nodes.map((node, index) => ({
              ...node,
              cluster: result.clusterAssignments[index],
              clusterStrength: result.clusterStrengths[index]
            })),
            clusterMapping: result.clusterMapping,
            clusterPositions: result.clusterPositions,
            isProcessing: false
          });
        }
      });
    };

    processAsync();
  }, [nodes, config]);

  return state;
};