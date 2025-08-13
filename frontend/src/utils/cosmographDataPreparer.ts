/**
 * Cosmograph Data Preparer
 * 
 * Unified data preparation pipeline using Cosmograph's prepareCosmographData function
 * Ensures type consistency between initial load and incremental updates
 */

import { prepareCosmographData } from '@cosmograph/react';
import type { GraphNode, GraphLink } from '../types/graph';
import { generateNodeTypeColor } from './nodeTypeColors';

/**
 * Configuration for data preparation
 */
export interface DataPrepConfig {
  clusteringMethod?: string;
  centralityMetric?: string;
  clusterStrength?: number;
  nodeTypeIndexMap?: Map<string, number>;
}

/**
 * Sanitize a value to ensure it's a primitive type
 */
function sanitizeValue(value: any): any {
  // Handle null/undefined
  if (value === null || value === undefined) {
    return null;
  }
  
  // Handle arrays - convert to count or comma-separated string
  if (Array.isArray(value)) {
    // For numeric arrays, return count
    if (value.length > 0 && typeof value[0] === 'number') {
      return value.length;
    }
    // For string arrays, join them
    if (value.length > 0 && typeof value[0] === 'string') {
      return value.slice(0, 5).join(', '); // Limit to first 5 items
    }
    // For other arrays, just return count
    return value.length;
  }
  
  // Handle objects - convert to string representation
  if (typeof value === 'object') {
    // Try to extract a meaningful value
    if (value.id) return String(value.id);
    if (value.name) return String(value.name);
    if (value.label) return String(value.label);
    // Otherwise return type name
    return Object.prototype.toString.call(value);
  }
  
  // Ensure numbers are actually numbers
  if (typeof value === 'string' && !isNaN(Number(value))) {
    const num = Number(value);
    if (isFinite(num)) return num;
  }
  
  // Return primitive values as-is
  return value;
}

/**
 * Sanitize properties object to remove nested structures
 */
function sanitizeProperties(properties: any): Record<string, any> {
  if (!properties || typeof properties !== 'object') {
    return {};
  }
  
  const sanitized: Record<string, any> = {};
  
  for (const [key, value] of Object.entries(properties)) {
    const sanitizedValue = sanitizeValue(value);
    // Only include if it's a primitive type
    if (
      typeof sanitizedValue === 'string' ||
      typeof sanitizedValue === 'number' ||
      typeof sanitizedValue === 'boolean' ||
      sanitizedValue === null
    ) {
      sanitized[key] = sanitizedValue;
    }
  }
  
  return sanitized;
}

/**
 * Transform and sanitize a node for Cosmograph
 * Exported for use in GraphCanvasV2
 */
export function sanitizeNode(
  node: GraphNode,
  index: number,
  config: DataPrepConfig = {}
): any {
  // Get or assign node type index for color generation
  let nodeTypeIndex = 0;
  if (config.nodeTypeIndexMap) {
    const nodeType = node.node_type || 'Unknown';
    if (!config.nodeTypeIndexMap.has(nodeType)) {
      config.nodeTypeIndexMap.set(nodeType, config.nodeTypeIndexMap.size);
    }
    nodeTypeIndex = config.nodeTypeIndexMap.get(nodeType) || 0;
  }
  
  // Calculate cluster value
  const cluster = config.clusteringMethod === 'nodeType' 
    ? String(node.node_type || 'Unknown')
    : config.clusteringMethod === 'centrality'
    ? String(Math.floor((node.properties?.[config.centralityMetric + '_centrality'] || 0) * 10))
    : String(node.node_type || 'Unknown');
  
  // Sanitize all properties
  const sanitizedProperties = sanitizeProperties(node.properties);
  
  // Build sanitized node with only primitive values
  const sanitizedNode: any = {
    // Core fields - always present (matches cosmograph_points schema)
    index: Number(index),  // cosmograph_points expects 'index' first
    id: String(node.id),
    label: String(node.label || node.name || node.id),
    node_type: String(node.node_type || 'Unknown'),
    summary: node.summary ? String(node.summary) : null,
    
    // Centrality metrics (from cosmograph_points schema)
    degree_centrality: Number(sanitizedProperties.degree_centrality || 0),
    pagerank_centrality: Number(sanitizedProperties.pagerank_centrality || 0),
    betweenness_centrality: Number(sanitizedProperties.betweenness_centrality || 0),
    eigenvector_centrality: Number(sanitizedProperties.eigenvector_centrality || 0),
    
    // Position (may be null initially)
    x: node.x ?? null,
    y: node.y ?? null,
    
    // Visual properties
    color: generateNodeTypeColor(node.node_type || 'Unknown', nodeTypeIndex),
    size: Number(node.size || 5),
    
    // Timestamp
    created_at_timestamp: node.created_at_timestamp ?? null,
    
    // Clustering (required by cosmograph_points)
    cluster: String(cluster),
    clusterStrength: Number(config.clusterStrength ?? 0.7),
    
    // Additional fields for compatibility
    idx: Number(index),  // Duplicate of index for compatibility
    name: String(node.name || node.label || ''),
    
    // Properties object for additional data
    properties: sanitizedProperties,
    
    // Original created_at string
    created_at: node.created_at ? String(node.created_at) : ''
  };
  
  return sanitizedNode;
}

/**
 * Transform and sanitize a link for Cosmograph
 * Exported for use in GraphCanvasV2
 */
export function sanitizeLink(
  link: GraphLink,
  nodeIdToIndex: Map<string, number>
): any | null {
  const sourceId = String(link.source || link.from);
  const targetId = String(link.target || link.to);
  
  const sourceIndex = nodeIdToIndex.get(sourceId);
  const targetIndex = nodeIdToIndex.get(targetId);
  
  // Skip invalid links
  if (sourceIndex === undefined || targetIndex === undefined) {
    return null;
  }
  
  return {
    // Required fields
    source: sourceId,
    target: targetId,
    sourceIndex: Number(sourceIndex),
    targetIndex: Number(targetIndex),
    sourceidx: Number(sourceIndex), // DuckDB compatibility
    targetidx: Number(targetIndex), // DuckDB compatibility
    
    // Link properties
    weight: Number(link.weight || 1),
    edge_type: String(link.edge_type || 'default'),
    
    // Optional fields
    created_at: link.created_at ? String(link.created_at) : ''
  };
}

/**
 * Unified data preparer class
 */
export class CosmographDataPreparer {
  private config: DataPrepConfig;
  private nodeIdToIndex: Map<string, number> = new Map();
  private nodeTypeIndexMap: Map<string, number> = new Map();
  private preparedConfig: any = null;
  
  constructor(config: DataPrepConfig = {}) {
    this.config = { ...config, nodeTypeIndexMap: this.nodeTypeIndexMap };
  }
  
  /**
   * Prepare initial data for Cosmograph
   */
  async prepareInitialData(
    nodes: GraphNode[],
    links: GraphLink[]
  ): Promise<{ data: any; config: any }> {
    // Clear maps
    this.nodeIdToIndex.clear();
    this.nodeTypeIndexMap.clear();
    
    // Sanitize all nodes
    const sanitizedNodes = nodes.map((node, index) => {
      this.nodeIdToIndex.set(node.id, index);
      return sanitizeNode(node, index, this.config);
    });
    
    // Sanitize all links
    const sanitizedLinks = links
      .map(link => sanitizeLink(link, this.nodeIdToIndex))
      .filter(link => link !== null);
    
    // Don't use prepareCosmographData for now - it has issues
    // Just return the sanitized data directly
    // The Cosmograph component will handle the conversion to Arrow format
    
    return {
      data: {
        nodes: sanitizedNodes,
        links: sanitizedLinks
      },
      config: {
        // Return empty config since we're not using prepareCosmographData
        nodeIdBy: 'id',
        nodeIndexBy: 'index',
        linkSourceBy: 'source',
        linkTargetBy: 'target'
      }
    };
  }
  
  /**
   * Prepare incremental data for Cosmograph
   */
  async prepareIncrementalData(
    nodes: GraphNode[],
    links: GraphLink[]
  ): Promise<{ nodes: any[]; links: any[] }> {
    // Sanitize new nodes
    const sanitizedNodes: any[] = [];
    for (const node of nodes) {
      // Skip if already exists
      if (this.nodeIdToIndex.has(node.id)) {
        continue;
      }
      
      const index = this.nodeIdToIndex.size;
      this.nodeIdToIndex.set(node.id, index);
      sanitizedNodes.push(sanitizeNode(node, index, this.config));
    }
    
    // Sanitize new links
    const sanitizedLinks = links
      .map(link => sanitizeLink(link, this.nodeIdToIndex))
      .filter(link => link !== null);
    
    return {
      nodes: sanitizedNodes,
      links: sanitizedLinks
    };
  }
  
  /**
   * Get the stored preparation config
   */
  getConfig(): any {
    return this.preparedConfig;
  }
  
  /**
   * Update configuration
   */
  updateConfig(config: Partial<DataPrepConfig>) {
    this.config = { ...this.config, ...config, nodeTypeIndexMap: this.nodeTypeIndexMap };
  }
  
  /**
   * Get node count
   */
  getNodeCount(): number {
    return this.nodeIdToIndex.size;
  }
  
  /**
   * Check if node exists
   */
  hasNode(nodeId: string): boolean {
    return this.nodeIdToIndex.has(nodeId);
  }
  
  /**
   * Reset the preparer
   */
  reset() {
    this.nodeIdToIndex.clear();
    this.nodeTypeIndexMap.clear();
    this.preparedConfig = null;
  }
}

// Global instance
let globalPreparer: CosmographDataPreparer | null = null;

export function getGlobalDataPreparer(config?: DataPrepConfig): CosmographDataPreparer {
  if (!globalPreparer) {
    globalPreparer = new CosmographDataPreparer(config);
  } else if (config) {
    globalPreparer.updateConfig(config);
  }
  return globalPreparer;
}

export function resetGlobalDataPreparer(): void {
  if (globalPreparer) {
    globalPreparer.reset();
  }
  globalPreparer = null;
}