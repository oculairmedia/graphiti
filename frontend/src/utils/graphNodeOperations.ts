/**
 * Graph Node Operations Utility Module
 * Pure functions for node manipulation and transformation
 */

import { GraphNode } from '../api/types';

/**
 * Transform raw nodes into Cosmograph-compatible format
 */
export function transformNodeForCosmograph(node: GraphNode, arrayIndex: number) {
  return {
    id: String(node.id),
    index: arrayIndex,
    label: String(node.label || node.name || node.id),
    node_type: String(node.node_type || 'Unknown'),
    centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
    cluster: String(node.node_type || 'Unknown'),
    clusterStrength: 0.7,
    degree_centrality: Number(node.properties?.degree_centrality || 0),
    pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
    betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
    eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0),
    created_at: node.properties?.created_at || node.created_at || null,
    created_at_timestamp: node.created_at_timestamp || node.properties?.created_at_timestamp || 
      (node.properties?.created_at ? new Date(node.properties.created_at).getTime() : null)
  };
}

/**
 * Batch transform nodes for Cosmograph
 */
export function transformNodesForCosmograph(nodes: GraphNode[]): any[] {
  if (!nodes || nodes.length === 0) return [];
  
  return nodes.map((node, index) => transformNodeForCosmograph(node, index));
}

/**
 * Filter out invalid nodes
 */
export function filterValidNodes(nodes: any[]): any[] {
  return nodes.filter(node => node.id && node.id !== 'undefined');
}

/**
 * Create node index map for quick lookup
 */
export function createNodeIndexMap(nodes: any[]): Map<string, number> {
  const map = new Map<string, number>();
  nodes.forEach((node, index) => {
    map.set(String(node.id), index);
  });
  return map;
}

/**
 * Get node by ID from array
 */
export function getNodeById(nodes: GraphNode[], nodeId: string): GraphNode | undefined {
  return nodes.find(node => node.id === nodeId);
}

/**
 * Get multiple nodes by IDs
 */
export function getNodesByIds(nodes: GraphNode[], nodeIds: string[]): GraphNode[] {
  const idSet = new Set(nodeIds);
  return nodes.filter(node => idSet.has(node.id));
}

/**
 * Get nodes by type
 */
export function getNodesByType(nodes: GraphNode[], type: string): GraphNode[] {
  return nodes.filter(node => node.node_type === type);
}

/**
 * Update node in array (immutable)
 */
export function updateNodeInArray(nodes: GraphNode[], updatedNode: GraphNode): GraphNode[] {
  return nodes.map(node => 
    node.id === updatedNode.id ? { ...node, ...updatedNode } : node
  );
}

/**
 * Update multiple nodes in array (immutable)
 */
export function updateNodesInArray(nodes: GraphNode[], updatedNodes: GraphNode[]): GraphNode[] {
  const updateMap = new Map(updatedNodes.map(n => [n.id, n]));
  return nodes.map(node => {
    const update = updateMap.get(node.id);
    return update ? { ...node, ...update } : node;
  });
}

/**
 * Remove nodes from array (immutable)
 */
export function removeNodesFromArray(nodes: GraphNode[], nodeIdsToRemove: string[]): GraphNode[] {
  const removeSet = new Set(nodeIdsToRemove);
  return nodes.filter(node => !removeSet.has(node.id));
}

/**
 * Add nodes to array (immutable, with deduplication)
 */
export function addNodesToArray(nodes: GraphNode[], newNodes: GraphNode[]): GraphNode[] {
  const existingIds = new Set(nodes.map(n => n.id));
  const nodesToAdd = newNodes.filter(n => !existingIds.has(n.id));
  return [...nodes, ...nodesToAdd];
}

/**
 * Merge node arrays with deduplication (newer nodes override older)
 */
export function mergeNodeArrays(existingNodes: GraphNode[], newNodes: GraphNode[]): GraphNode[] {
  const nodeMap = new Map<string, GraphNode>();
  
  // Add existing nodes first
  existingNodes.forEach(node => nodeMap.set(node.id, node));
  
  // Override with new nodes
  newNodes.forEach(node => nodeMap.set(node.id, node));
  
  return Array.from(nodeMap.values());
}

/**
 * Calculate node statistics
 */
export function calculateNodeStats(nodes: GraphNode[]) {
  const stats = {
    total: nodes.length,
    byType: new Map<string, number>(),
    avgCentrality: 0,
    maxCentrality: 0,
    minCentrality: Infinity,
    withTimestamps: 0,
    uniqueTypes: 0
  };
  
  let totalCentrality = 0;
  
  nodes.forEach(node => {
    // Count by type
    const type = node.node_type || 'Unknown';
    stats.byType.set(type, (stats.byType.get(type) || 0) + 1);
    
    // Calculate centrality stats
    const centrality = Number(node.properties?.degree_centrality || 0);
    totalCentrality += centrality;
    stats.maxCentrality = Math.max(stats.maxCentrality, centrality);
    stats.minCentrality = Math.min(stats.minCentrality, centrality);
    
    // Count nodes with timestamps
    if (node.created_at || node.created_at_timestamp) {
      stats.withTimestamps++;
    }
  });
  
  stats.avgCentrality = nodes.length > 0 ? totalCentrality / nodes.length : 0;
  stats.uniqueTypes = stats.byType.size;
  
  if (nodes.length === 0) {
    stats.minCentrality = 0;
  }
  
  return stats;
}

/**
 * Sort nodes by centrality
 */
export function sortNodesByCentrality(nodes: GraphNode[], metric: string = 'degree'): GraphNode[] {
  return [...nodes].sort((a, b) => {
    const aValue = Number(a.properties?.[`${metric}_centrality`] || 0);
    const bValue = Number(b.properties?.[`${metric}_centrality`] || 0);
    return bValue - aValue; // Descending order
  });
}

/**
 * Get top N nodes by centrality
 */
export function getTopNodesByCentrality(nodes: GraphNode[], n: number, metric: string = 'degree'): GraphNode[] {
  return sortNodesByCentrality(nodes, metric).slice(0, n);
}

/**
 * Find nodes within time range
 */
export function findNodesInTimeRange(nodes: GraphNode[], startTime: number, endTime: number): GraphNode[] {
  return nodes.filter(node => {
    const timestamp = node.created_at_timestamp || 
      (node.created_at ? new Date(node.created_at).getTime() : null);
    
    if (!timestamp) return false;
    return timestamp >= startTime && timestamp <= endTime;
  });
}

/**
 * Group nodes by property
 */
export function groupNodesByProperty(nodes: GraphNode[], property: string): Map<any, GraphNode[]> {
  const groups = new Map<any, GraphNode[]>();
  
  nodes.forEach(node => {
    const value = (node as any)[property] || node.properties?.[property] || 'Unknown';
    if (!groups.has(value)) {
      groups.set(value, []);
    }
    groups.get(value)!.push(node);
  });
  
  return groups;
}

/**
 * Calculate node degree (number of connections)
 * Note: This requires link information, so it's a utility that needs both nodes and links
 */
export function calculateNodeDegrees(nodes: GraphNode[], links: any[]): Map<string, number> {
  const degrees = new Map<string, number>();
  
  // Initialize all nodes with 0 degree
  nodes.forEach(node => degrees.set(node.id, 0));
  
  // Count connections
  links.forEach(link => {
    const source = String(link.source || link.from);
    const target = String(link.target || link.to);
    
    degrees.set(source, (degrees.get(source) || 0) + 1);
    degrees.set(target, (degrees.get(target) || 0) + 1);
  });
  
  return degrees;
}

/**
 * Find isolated nodes (nodes with no connections)
 */
export function findIsolatedNodes(nodes: GraphNode[], links: any[]): GraphNode[] {
  const connectedNodes = new Set<string>();
  
  links.forEach(link => {
    connectedNodes.add(String(link.source || link.from));
    connectedNodes.add(String(link.target || link.to));
  });
  
  return nodes.filter(node => !connectedNodes.has(node.id));
}

/**
 * Validate node data
 */
export function validateNode(node: any): boolean {
  return !!(
    node &&
    node.id &&
    node.id !== 'undefined' &&
    node.id !== 'null' &&
    typeof node.id === 'string'
  );
}

/**
 * Batch validate nodes
 */
export function validateNodes(nodes: any[]): { valid: any[], invalid: any[] } {
  const valid: any[] = [];
  const invalid: any[] = [];
  
  nodes.forEach(node => {
    if (validateNode(node)) {
      valid.push(node);
    } else {
      invalid.push(node);
    }
  });
  
  return { valid, invalid };
}