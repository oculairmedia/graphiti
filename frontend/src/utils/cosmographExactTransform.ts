/**
 * Exact Cosmograph Transform
 * 
 * This module replicates the EXACT transformation used in GraphCanvasV2
 * to ensure incremental updates match the initial data schema perfectly.
 */

import { GraphNode, GraphLink } from '../types/graph';
import { generateNodeTypeColor } from './nodeTypeColors';

export interface TransformConfig {
  clusteringMethod?: string;
  centralityMetric?: string;
  clusterStrength?: number;
}

/**
 * Transform a node using the EXACT same logic as initial load
 */
export function transformNodeExact(
  node: GraphNode,
  index: number,
  config: TransformConfig = {},
  nodeTypeIndex: number = 0
): any {
  const cluster = config.clusteringMethod === 'nodeType' 
    ? String(node.node_type || 'Unknown')
    : config.clusteringMethod === 'centrality'
    ? String(Math.floor((node.properties?.[config.centralityMetric + '_centrality'] || 0) * 10))
    : String(node.node_type || 'Unknown');
  
  // Generate color for the node type
  const color = generateNodeTypeColor(node.node_type || 'Unknown', nodeTypeIndex);
  
  // Clean properties - remove arrays and complex objects
  const cleanProperties: any = {};
  if (node.properties) {
    Object.keys(node.properties).forEach(key => {
      const value = node.properties![key];
      // Only include primitive types (strings, numbers, booleans)
      if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
        cleanProperties[key] = value;
      }
    });
  }
  
  // Return EXACT same structure as initial load but with cleaned data
  return {
    ...node,  // Spread all original fields first
    index,
    idx: index,
    size: node.size || 5,
    label: node.label || node.name || node.id,
    cluster,
    clusterStrength: config.clusterStrength ?? 0.7,
    color,  // Add the color field
    // Override properties with cleaned version
    properties: cleanProperties
  };
}

/**
 * Transform a link using the EXACT same logic as initial load
 */
export function transformLinkExact(
  link: GraphLink,
  nodeIdToIndex: Map<string, number>,
  transformedNodes: any[]
): any | null {
  const sourceIndex = nodeIdToIndex.get(link.source || link.from);
  const targetIndex = nodeIdToIndex.get(link.target || link.to);
  
  // Skip invalid links just like initial load
  if (sourceIndex === undefined || targetIndex === undefined || sourceIndex < 0 || targetIndex < 0) {
    return null;
  }
  
  const sourceNode = transformedNodes[sourceIndex];
  
  // Return EXACT same structure as initial load
  return {
    ...link,  // Spread all original fields first
    source: link.source || link.from,
    target: link.target || link.to,
    sourceIndex: sourceIndex,
    targetIndex: targetIndex,
    sourceidx: sourceIndex,
    targetidx: targetIndex,
    weight: link.weight || 1,
    edge_type: link.edge_type || 'default',
    source_centrality: sourceNode?.properties?.degree_centrality || 0,
    source_pagerank: sourceNode?.properties?.pagerank_centrality || 0,
    source_betweenness: sourceNode?.properties?.betweenness_centrality || 0
  };
}

/**
 * Manager class to maintain state for incremental updates
 */
export class ExactTransformManager {
  private nodeIdToIndex: Map<string, number> = new Map();
  private transformedNodes: any[] = [];
  private config: TransformConfig;
  private nextIndex: number = 0;
  private nodeTypeIndexMap: Map<string, number> = new Map();

  constructor(config: TransformConfig = {}) {
    this.config = config;
  }

  /**
   * Initialize with existing graph data
   */
  initialize(nodes: GraphNode[], links: GraphLink[]) {
    this.nodeIdToIndex.clear();
    this.transformedNodes = [];
    this.nodeTypeIndexMap.clear();
    this.nextIndex = 0;
    
    // Build node type index map
    const nodeTypes = new Set<string>();
    nodes.forEach(node => {
      const nodeType = node.node_type || 'Unknown';
      nodeTypes.add(nodeType);
    });
    
    Array.from(nodeTypes).forEach((type, index) => {
      this.nodeTypeIndexMap.set(type, index);
    });
    
    // Transform all nodes
    nodes.forEach((node, index) => {
      const nodeType = node.node_type || 'Unknown';
      const typeIndex = this.nodeTypeIndexMap.get(nodeType) || 0;
      const transformed = transformNodeExact(node, index, this.config, typeIndex);
      this.nodeIdToIndex.set(node.id, index);
      this.transformedNodes[index] = transformed;
      this.nextIndex = index + 1;
    });
  }

  /**
   * Add new nodes for incremental update
   */
  addNodes(nodes: GraphNode[]): any[] {
    const result: any[] = [];
    
    for (const node of nodes) {
      // Skip if already exists
      if (this.nodeIdToIndex.has(node.id)) {
        console.warn('[ExactTransform] Node already exists:', node.id);
        continue;
      }
      
      const nodeType = node.node_type || 'Unknown';
      
      // Get or create type index
      let typeIndex = this.nodeTypeIndexMap.get(nodeType);
      if (typeIndex === undefined) {
        typeIndex = this.nodeTypeIndexMap.size;
        this.nodeTypeIndexMap.set(nodeType, typeIndex);
      }
      
      const index = this.nextIndex++;
      const transformed = transformNodeExact(node, index, this.config, typeIndex);
      
      this.nodeIdToIndex.set(node.id, index);
      this.transformedNodes[index] = transformed;
      result.push(transformed);
    }
    
    return result;
  }

  /**
   * Add new links for incremental update
   */
  addLinks(links: GraphLink[]): any[] {
    const result: any[] = [];
    
    for (const link of links) {
      const transformed = transformLinkExact(link, this.nodeIdToIndex, this.transformedNodes);
      if (transformed) {
        result.push(transformed);
      }
    }
    
    return result;
  }

  /**
   * Get node index
   */
  getNodeIndex(nodeId: string): number | undefined {
    return this.nodeIdToIndex.get(nodeId);
  }

  /**
   * Get current node count
   */
  getNodeCount(): number {
    return this.nodeIdToIndex.size;
  }

  /**
   * Update config
   */
  updateConfig(config: TransformConfig) {
    this.config = { ...this.config, ...config };
  }
}

// Global instance
let globalManager: ExactTransformManager | null = null;

export function getExactTransformManager(config?: TransformConfig): ExactTransformManager {
  if (!globalManager) {
    globalManager = new ExactTransformManager(config);
  } else if (config) {
    globalManager.updateConfig(config);
  }
  return globalManager;
}

export function resetExactTransformManager(): void {
  globalManager = null;
}