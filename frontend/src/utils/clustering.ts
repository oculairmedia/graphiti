/**
 * Clustering utilities for graph visualization
 * Provides functions to compute cluster assignments based on various methods
 */

import { GraphNode } from '../api/types';

export type ClusteringMethod = 'nodeType' | 'centrality' | 'custom' | 'none';
export type CentralityMetric = 'degree' | 'pagerank' | 'betweenness' | 'eigenvector';

export interface ClusteringConfig {
  method: ClusteringMethod;
  centralityMetric?: CentralityMetric;
  clusterStrength: number;
  customClusterFn?: (node: GraphNode, index: number) => string | number;
}

/**
 * Generate cluster assignments for nodes based on the specified method
 */
export function generateClusterAssignments(
  nodes: GraphNode[],
  config: ClusteringConfig
): { 
  clusterBy: string | undefined;
  clusterAssignments: (string | number)[];
  clusterStrengths: number[];
  clusterMapping: Map<unknown, number>;
} {
  if (config.method === 'none' || !nodes.length) {
    return {
      clusterBy: undefined,
      clusterAssignments: [],
      clusterStrengths: [],
      clusterMapping: new Map()
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

  return {
    clusterBy,
    clusterAssignments,
    clusterStrengths,
    clusterMapping
  };
}

/**
 * Get centrality value for a node based on the specified metric
 */
function getCentralityValue(node: GraphNode, metric: CentralityMetric): number {
  switch (metric) {
    case 'degree':
      return node.degree_centrality || 0;
    case 'pagerank':
      return node.pagerank || 0;
    case 'betweenness':
      return node.betweenness_centrality || 0;
    case 'eigenvector':
      return node.eigenvector_centrality || 0;
    default:
      return 0;
  }
}

/**
 * Determine cluster assignment based on centrality value
 * Creates 5 clusters: very low, low, medium, high, very high
 */
function getCentralityCluster(centrality: number): string {
  if (centrality < 0.2) return 'very_low';
  if (centrality < 0.4) return 'low';
  if (centrality < 0.6) return 'medium';
  if (centrality < 0.8) return 'high';
  return 'very_high';
}

/**
 * Generate cluster positions for force-directed layout
 * Arranges clusters in a circle around the center
 */
export function generateClusterPositions(
  clusterMapping: Map<unknown, number>,
  centerX: number = 0,
  centerY: number = 0,
  radius: number = 500
): Record<string, { x: number; y: number }> {
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
}

/**
 * Apply clustering to graph data for Cosmograph
 * Returns the data with cluster assignments added
 */
export function applyClusteringToGraphData(
  nodes: GraphNode[],
  config: ClusteringConfig
): {
  nodes: (GraphNode & { cluster?: string | number; clusterStrength?: number })[];
  clusterMapping: Map<unknown, number>;
  clusterPositions: Record<string, { x: number; y: number }>;
} {
  const { clusterAssignments, clusterStrengths, clusterMapping } = generateClusterAssignments(nodes, config);
  
  const clusteredNodes = nodes.map((node, index) => ({
    ...node,
    cluster: clusterAssignments[index],
    clusterStrength: clusterStrengths[index]
  }));
  
  const clusterPositions = generateClusterPositions(clusterMapping);
  
  return {
    nodes: clusteredNodes,
    clusterMapping,
    clusterPositions
  };
}