/**
 * Cosmograph Schema Validator
 * 
 * Ensures data consistency for incremental updates by validating and transforming
 * nodes and links to match the exact schema used during initial Cosmograph setup.
 * 
 * Issue: GRAPH-277 - Implement proper data schema validation for Cosmograph updates
 */

import { GraphNode, GraphLink } from '../types/graph';

// Schema definitions based on GraphCanvasV2.tsx initialization
export interface CosmographNode {
  // Required fields from initial setup
  id: string;
  index: number;
  idx: number; // Duplicate for compatibility
  
  // Standard node fields
  node_type?: string;
  label?: string;
  name?: string;
  size?: number;
  
  // Clustering fields
  cluster?: string;
  clusterStrength?: number;
  
  // Properties object containing centrality metrics
  properties?: {
    degree_centrality?: number;
    pagerank_centrality?: number;
    betweenness_centrality?: number;
    closeness_centrality?: number;
    [key: string]: any;
  };
  
  // Additional fields from backend
  created_at?: string;
  [key: string]: any; // Allow additional fields
}

export interface CosmographLink {
  // Required fields
  source: string;
  target: string;
  sourceIndex: number;
  targetIndex: number;
  
  // DuckDB compatibility fields
  sourceidx: number;
  targetidx: number;
  
  // Link properties
  weight?: number;
  edge_type?: string;
  
  // Centrality values for link styling
  source_centrality?: number;
  source_pagerank?: number;
  source_betweenness?: number;
  
  // Additional fields from backend
  from?: string;
  to?: string;
  [key: string]: any; // Allow additional fields
}

export class CosmographSchemaValidator {
  private nodeIdToIndex: Map<string, number> = new Map();
  private nodes: CosmographNode[] = [];
  private config: {
    clusteringMethod?: string;
    centralityMetric?: string;
    clusterStrength?: number;
  };

  constructor(config?: any) {
    this.config = config || {};
  }

  /**
   * Initialize validator with existing graph data
   */
  initialize(nodes: GraphNode[], links: GraphLink[]) {
    this.nodeIdToIndex.clear();
    this.nodes = [];
    
    // Build node index map from existing data
    nodes.forEach((node, index) => {
      this.nodeIdToIndex.set(node.id, index);
      this.nodes.push(this.transformNode(node, index));
    });
  }

  /**
   * Transform a node to match Cosmograph schema
   */
  transformNode(node: GraphNode, index?: number): CosmographNode {
    // Use provided index or look it up
    const nodeIndex = index !== undefined ? index : this.nodeIdToIndex.get(node.id);
    
    // If node doesn't exist yet, assign next available index
    const finalIndex = nodeIndex !== undefined ? nodeIndex : this.nodes.length;
    
    // Calculate cluster based on configuration
    const cluster = this.calculateCluster(node);
    
    // Ensure numeric fields are properly typed
    const size = this.ensureNumeric(node.size, 5);
    const clusterStrength = this.ensureNumeric(this.config.clusterStrength, 0.7);
    
    // Clean properties - remove undefined/null values and ensure numeric centrality
    const cleanProperties: any = {};
    if (node.properties) {
      Object.keys(node.properties).forEach(key => {
        const value = node.properties![key];
        if (value !== undefined && value !== null) {
          // Ensure centrality metrics are numeric
          if (key.endsWith('_centrality')) {
            cleanProperties[key] = this.ensureNumeric(value, 0);
          } else {
            cleanProperties[key] = value;
          }
        }
      });
    }
    
    // Ensure all centrality metrics exist as numbers
    cleanProperties.degree_centrality = this.ensureNumeric(cleanProperties.degree_centrality, 0);
    cleanProperties.pagerank_centrality = this.ensureNumeric(cleanProperties.pagerank_centrality, 0);
    cleanProperties.betweenness_centrality = this.ensureNumeric(cleanProperties.betweenness_centrality, 0);
    cleanProperties.closeness_centrality = this.ensureNumeric(cleanProperties.closeness_centrality, 0);
    
    // Build clean result object - only include defined values
    const result: CosmographNode = {
      // Required fields - always defined
      id: String(node.id),
      index: Number(finalIndex),
      idx: Number(finalIndex),
      
      // Standard fields - always defined with defaults
      node_type: String(node.node_type || 'Unknown'),
      label: String(node.label || node.name || node.id),
      name: String(node.name || node.label || ''),
      size: Number(size),
      cluster: String(cluster),
      clusterStrength: Number(clusterStrength),
      
      // Clean properties
      properties: cleanProperties
    };
    
    // Add other fields from node, but filter out undefined/null values
    Object.keys(node).forEach(key => {
      if (!result.hasOwnProperty(key)) {
        const value = (node as any)[key];
        if (value !== undefined && value !== null) {
          (result as any)[key] = value;
        }
      }
    });
    
    return result;
  }

  /**
   * Transform a link to match Cosmograph schema
   */
  transformLink(link: GraphLink): CosmographLink | null {
    // Get source and target IDs
    const sourceId = String(link.source || link.from);
    const targetId = String(link.target || link.to);
    
    if (!sourceId || !targetId) {
      console.warn('[SchemaValidator] Link missing source or target:', link);
      return null;
    }
    
    // Look up indices
    const sourceIndex = this.nodeIdToIndex.get(sourceId);
    const targetIndex = this.nodeIdToIndex.get(targetId);
    
    // Skip invalid links
    if (sourceIndex === undefined || targetIndex === undefined) {
      console.warn('[SchemaValidator] Link references unknown nodes:', {
        sourceId,
        targetId,
        hasSource: sourceIndex !== undefined,
        hasTarget: targetIndex !== undefined
      });
      return null;
    }
    
    // Get source node for centrality values
    const sourceNode = this.nodes[sourceIndex];
    
    // Ensure numeric values
    const weight = this.ensureNumeric(link.weight, 1);
    const source_centrality = this.ensureNumeric(sourceNode?.properties?.degree_centrality, 0);
    const source_pagerank = this.ensureNumeric(sourceNode?.properties?.pagerank_centrality, 0);
    const source_betweenness = this.ensureNumeric(sourceNode?.properties?.betweenness_centrality, 0);
    
    // Build clean result object - only include defined values
    const result: CosmographLink = {
      // Required fields - always defined
      source: String(sourceId),
      target: String(targetId),
      sourceIndex: Number(sourceIndex),
      targetIndex: Number(targetIndex),
      sourceidx: Number(sourceIndex),
      targetidx: Number(targetIndex),
      
      // Link properties - always defined with defaults
      weight: Number(weight),
      edge_type: String(link.edge_type || 'default'),
      
      // Centrality values - always defined as numbers
      source_centrality: Number(source_centrality),
      source_pagerank: Number(source_pagerank),
      source_betweenness: Number(source_betweenness)
    };
    
    // Add other fields from link, but filter out undefined/null values
    Object.keys(link).forEach(key => {
      if (!result.hasOwnProperty(key)) {
        const value = (link as any)[key];
        if (value !== undefined && value !== null) {
          (result as any)[key] = value;
        }
      }
    });
    
    return result;
  }

  /**
   * Validate and transform nodes for incremental update
   */
  validateNodes(nodes: GraphNode[]): CosmographNode[] {
    const validated: CosmographNode[] = [];
    
    for (const node of nodes) {
      // Check if node already exists
      let index = this.nodeIdToIndex.get(node.id);
      
      // If new node, assign next index based on current maximum
      if (index === undefined) {
        // Use the actual next available index
        index = this.getMaxIndex() + validated.length;
        this.nodeIdToIndex.set(node.id, index);
      }
      
      const transformedNode = this.transformNode(node, index);
      validated.push(transformedNode);
    }
    
    console.log('[SchemaValidator] Validated nodes sample:', validated[0]);
    
    return validated;
  }

  /**
   * Validate and transform links for incremental update
   */
  validateLinks(links: GraphLink[]): CosmographLink[] {
    const validated: CosmographLink[] = [];
    
    for (const link of links) {
      const transformedLink = this.transformLink(link);
      if (transformedLink) {
        validated.push(transformedLink);
      }
    }
    
    return validated;
  }

  /**
   * Update internal state after successful incremental update
   */
  updateState(addedNodes?: CosmographNode[], removedNodeIds?: string[]) {
    // Add new nodes to internal list
    if (addedNodes) {
      for (const node of addedNodes) {
        this.nodes[node.index] = node;
        this.nodeIdToIndex.set(node.id, node.index);
      }
    }
    
    // Remove deleted nodes
    if (removedNodeIds) {
      for (const nodeId of removedNodeIds) {
        const index = this.nodeIdToIndex.get(nodeId);
        if (index !== undefined) {
          // Don't actually remove from array to preserve indices
          // Just mark as deleted or set to null
          delete this.nodes[index];
          this.nodeIdToIndex.delete(nodeId);
        }
      }
    }
  }

  /**
   * Get current node count
   */
  getNodeCount(): number {
    return this.nodeIdToIndex.size;
  }

  /**
   * Get current maximum index
   */
  getMaxIndex(): number {
    // Return the highest index in use, not just array length
    let maxIndex = 0;
    this.nodeIdToIndex.forEach(index => {
      if (index > maxIndex) maxIndex = index;
    });
    return maxIndex;
  }

  /**
   * Check if a node exists
   */
  hasNode(nodeId: string): boolean {
    return this.nodeIdToIndex.has(nodeId);
  }

  /**
   * Get node index
   */
  getNodeIndex(nodeId: string): number | undefined {
    return this.nodeIdToIndex.get(nodeId);
  }

  private calculateCluster(node: GraphNode): string {
    const { clusteringMethod, centralityMetric } = this.config;
    
    if (clusteringMethod === 'nodeType') {
      return String(node.node_type || 'Unknown');
    } else if (clusteringMethod === 'centrality') {
      const metricValue = this.ensureNumeric(node.properties?.[`${centralityMetric}_centrality`], 0);
      return String(Math.floor(metricValue * 10));
    }
    
    return String(node.node_type || 'Unknown');
  }
  
  /**
   * Ensure a value is numeric, with fallback
   */
  private ensureNumeric(value: any, fallback: number): number {
    if (typeof value === 'number' && !isNaN(value)) {
      return value;
    }
    const parsed = parseFloat(value);
    return isNaN(parsed) ? fallback : parsed;
  }
}

// Singleton instance for global schema validation
let globalValidator: CosmographSchemaValidator | null = null;

export function getGlobalSchemaValidator(config?: any): CosmographSchemaValidator {
  if (!globalValidator) {
    globalValidator = new CosmographSchemaValidator(config);
  }
  return globalValidator;
}

export function resetGlobalSchemaValidator(): void {
  globalValidator = null;
}