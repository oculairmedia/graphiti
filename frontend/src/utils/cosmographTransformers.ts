/**
 * Cosmograph Data Transformers
 * 
 * Utility functions to transform between our graph data format and Cosmograph's expected format.
 * Used for incremental updates to avoid full graph re-renders.
 */

import type { GraphNode } from '../api/types';
import type { GraphLink } from '../types/graph';

/**
 * Cosmograph point input format for incremental updates
 */
export interface CosmographPointInput {
  id: string;
  idx?: number;
  index?: number;
  label?: string;
  name?: string;
  size?: number;
  cluster?: string;
  [key: string]: any; // Allow additional properties
}

/**
 * Cosmograph link input format for incremental updates
 */
export interface CosmographLinkInput {
  source: string;
  target: string;
  sourceIndex?: number;
  targetIndex?: number;
  weight?: number;
  edge_type?: string;
  [key: string]: any; // Allow additional properties
}

/**
 * Transform a GraphNode to Cosmograph point format
 * @param node - The node to transform
 * @param index - Optional index for the node
 * @returns Transformed node for Cosmograph
 */
export function transformNodeForCosmograph(
  node: GraphNode,
  index?: number
): CosmographPointInput {
  return {
    ...node,
    id: node.id,
    idx: index ?? node.idx,
    index: index ?? node.idx,
    label: node.label || node.name || node.id,
    name: node.name || node.label || node.id,
    size: node.size || 5,
    cluster: node.node_type || 'Unknown',
    // Include all original properties
  };
}

/**
 * Transform a GraphLink to Cosmograph link format
 * @param edge - The edge to transform
 * @param nodeIdToIndex - Optional map of node IDs to indices
 * @returns Transformed edge for Cosmograph
 */
export function transformEdgeForCosmograph(
  edge: GraphLink,
  nodeIdToIndex?: Map<string, number>
): CosmographLinkInput {
  const source = edge.source || edge.from;
  const target = edge.target || edge.to;
  
  return {
    ...edge,
    source: source,
    target: target,
    sourceIndex: nodeIdToIndex?.get(source) ?? -1,
    targetIndex: nodeIdToIndex?.get(target) ?? -1,
    weight: edge.weight || 1,
    edge_type: edge.edge_type || 'default',
  };
}

/**
 * Extract edge pairs from edges for removal operations
 * @param edges - Array of edges or edge identifiers
 * @returns Array of [source, target] pairs
 */
export function extractEdgePairs(
  edges: (GraphLink | string)[]
): [string, string][] {
  return edges.map(edge => {
    if (typeof edge === 'string') {
      // Assume format is "source-target"
      const [source, ...targetParts] = edge.split('-');
      const target = targetParts.join('-'); // Handle IDs with hyphens
      return [source, target] as [string, string];
    } else {
      const source = edge.source || edge.from;
      const target = edge.target || edge.to;
      return [source, target] as [string, string];
    }
  });
}

/**
 * Transform nodes array for batch addition
 * @param nodes - Array of nodes to transform
 * @param startIndex - Optional starting index for new nodes
 * @returns Array of transformed nodes
 */
export function transformNodesForCosmograph(
  nodes: GraphNode[],
  startIndex?: number
): CosmographPointInput[] {
  return nodes.map((node, i) => 
    transformNodeForCosmograph(node, startIndex ? startIndex + i : undefined)
  );
}

/**
 * Transform edges array for batch addition
 * @param edges - Array of edges to transform
 * @param nodeIdToIndex - Optional map of node IDs to indices
 * @returns Array of transformed edges
 */
export function transformEdgesForCosmograph(
  edges: GraphLink[],
  nodeIdToIndex?: Map<string, number>
): CosmographLinkInput[] {
  return edges.map(edge => transformEdgeForCosmograph(edge, nodeIdToIndex));
}

/**
 * Build a node ID to index map from current graph data
 * @param nodes - Current nodes in the graph
 * @returns Map of node ID to index
 */
export function buildNodeIdToIndexMap(nodes: GraphNode[]): Map<string, number> {
  const map = new Map<string, number>();
  nodes.forEach((node, index) => {
    map.set(node.id, index);
  });
  return map;
}

/**
 * Validate that nodes exist for edge endpoints
 * @param edges - Edges to validate
 * @param nodeIds - Set of valid node IDs
 * @returns Filtered array of valid edges
 */
export function filterValidEdges(
  edges: GraphLink[],
  nodeIds: Set<string>
): GraphLink[] {
  return edges.filter(edge => {
    const source = edge.source || edge.from;
    const target = edge.target || edge.to;
    return nodeIds.has(source) && nodeIds.has(target);
  });
}

/**
 * Delta update types
 */
export type DeltaOperation = 'add' | 'update' | 'delete';

export interface DeltaUpdate {
  operation: DeltaOperation;
  nodes?: GraphNode[];
  edges?: GraphLink[];
  nodeIds?: string[];
  edgeIds?: string[];
  timestamp?: number;
}

/**
 * Transform a complete delta update for Cosmograph
 * @param delta - The delta update to transform
 * @param currentNodeCount - Current number of nodes in graph
 * @param nodeIdToIndex - Map of node IDs to indices
 * @returns Transformed delta ready for Cosmograph
 */
export function transformDeltaForCosmograph(
  delta: DeltaUpdate,
  currentNodeCount: number,
  nodeIdToIndex: Map<string, number>
): {
  nodes: CosmographPointInput[];
  edges: CosmographLinkInput[];
  nodeIdsToRemove?: string[];
  edgePairsToRemove?: [string, string][];
} {
  const result: {
    nodes: CosmographPointInput[];
    edges: CosmographLinkInput[];
    nodeIdsToRemove?: string[];
    edgePairsToRemove?: [string, string][];
  } = {
    nodes: [],
    edges: []
  };

  // Handle nodes
  if (delta.nodes && delta.nodes.length > 0) {
    if (delta.operation === 'add') {
      // New nodes get indices starting from current count
      result.nodes = transformNodesForCosmograph(delta.nodes, currentNodeCount);
      // Update the map with new nodes
      delta.nodes.forEach((node, i) => {
        nodeIdToIndex.set(node.id, currentNodeCount + i);
      });
    } else if (delta.operation === 'update') {
      // Updated nodes keep their existing indices
      result.nodes = delta.nodes.map(node => {
        const existingIndex = nodeIdToIndex.get(node.id);
        return transformNodeForCosmograph(node, existingIndex);
      });
    } else if (delta.operation === 'delete') {
      result.nodeIdsToRemove = delta.nodeIds || delta.nodes.map(n => n.id);
    }
  }

  // Handle edges
  if (delta.edges && delta.edges.length > 0) {
    if (delta.operation === 'add' || delta.operation === 'update') {
      result.edges = transformEdgesForCosmograph(delta.edges, nodeIdToIndex);
    } else if (delta.operation === 'delete') {
      result.edgePairsToRemove = extractEdgePairs(delta.edgeIds || delta.edges);
    }
  }

  return result;
}

/**
 * Check if Cosmograph instance has incremental update methods
 * @param cosmographRef - Reference to Cosmograph instance
 * @returns True if incremental updates are supported
 */
export function supportsIncrementalUpdates(cosmographRef: any): boolean {
  return !!(
    cosmographRef?.current?.addPoints &&
    cosmographRef?.current?.addLinks &&
    cosmographRef?.current?.removePointsByIds &&
    cosmographRef?.current?.removeLinksByPointIdPairs
  );
}