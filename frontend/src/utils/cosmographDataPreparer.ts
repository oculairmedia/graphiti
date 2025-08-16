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
  sizeMapping?: string;  // Add sizeMapping to config
}

// Compute node size based on the selected sizing strategy (copied from useGraphDataQuery)
export function computeSizeFromStrategy(node: any, config: DataPrepConfig): number {
  // Return normalized value (0-1 range) - renderer will handle scaling
  switch (config.sizeMapping) {
    case 'degree':
      return node.properties?.degree_centrality || node.degree_centrality || 0.1;
    case 'betweenness':
      return node.properties?.betweenness_centrality || node.betweenness_centrality || 0.1;
    case 'pagerank':
      return node.properties?.pagerank_centrality || node.properties?.pagerank || node.pagerank_centrality || node.pagerank || 0.1;
    case 'importance':
      return node.properties?.eigenvector_centrality || node.eigenvector_centrality || 0.1;
    case 'connections':
      // Same as degree but could use raw count if available
      return node.properties?.degree_centrality || node.degree_centrality || 0.1;
    case 'uniform':
      return 0.5; // Middle value for uniform sizing
    case 'custom':
      // Use eigenvector as default for custom
      return node.properties?.eigenvector_centrality || node.properties?.pagerank_centrality || node.properties?.degree_centrality || node.eigenvector_centrality || node.pagerank_centrality || node.degree_centrality || 0.1;
    default:
      // Safe fallback using best available metric
      return node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.degree_centrality || node.pagerank_centrality || 0.1;
  }
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
  config: DataPrepConfig = {},
  isIncremental: boolean = false
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
  
  // Build sanitized node - ensure consistent field count for DuckDB
  // For incremental updates: exactly 11 non-null fields expected
  // Fields that Cosmograph actually uses (based on debug output)
  const sanitizedNode: any = {};
  
  if (isIncremental) {
    // Incremental updates: MUST provide exactly 14 NON-NULL fields to match DuckDB table schema
    // DuckDB counts null fields differently in incremental vs initial load
    // The table was created with 14 columns, so we must provide all 14 with non-null values
    sanitizedNode.index = Number(index);
    sanitizedNode.id = String(node.id);
    sanitizedNode.label = String(node.label || node.name || node.id);
    sanitizedNode.node_type = String(node.node_type || 'Unknown');
    sanitizedNode.summary = String(node.summary || ''); // Always provide a string, not null
    // Add small variance to prevent STDDEV_SAMP errors
    // Keep raw values for the columns (they should already be 0-1 normalized from backend)
    const epsilon = 0.000001;
    const degreeValue = Number(sanitizedProperties.degree_centrality || 0);
    const pagerankValue = Number(sanitizedProperties.pagerank_centrality || 0);
    const betweennessValue = Number(sanitizedProperties.betweenness_centrality || 0);
    const eigenvectorValue = Number(sanitizedProperties.eigenvector_centrality || 0);
    
    // Add tiny random noise to prevent STDDEV_SAMP errors
    sanitizedNode.degree_centrality = degreeValue + (Math.random() * epsilon);
    sanitizedNode.pagerank_centrality = pagerankValue + (Math.random() * epsilon);
    sanitizedNode.betweenness_centrality = betweennessValue + (Math.random() * epsilon);
    sanitizedNode.eigenvector_centrality = eigenvectorValue + (Math.random() * epsilon);
    
    sanitizedNode.color = generateNodeTypeColor(node.node_type || 'Unknown', nodeTypeIndex);
    // Use normalized size based on degree centrality (0-1 range)
    // This provides a consistent base that can be scaled by pointSizeRange
    sanitizedNode.size = degreeValue || 0.1;
    // Add color value that can be used by color schemes (same as degree by default)
    sanitizedNode.colorValue = degreeValue || 0.1;
    sanitizedNode.cluster = String(cluster);
    sanitizedNode.clusterStrength = Number(config.clusterStrength ?? 0.7);
    // CRITICAL: created_at_timestamp MUST be a number (Unix timestamp) for DuckDB
    // DuckDB created this column as DOUBLE type, not string
    // Handle both number and string formats for robustness
    if (node.created_at_timestamp !== undefined && node.created_at_timestamp !== null) {
      // If it's already a number, use it directly
      if (typeof node.created_at_timestamp === 'number') {
        sanitizedNode.created_at_timestamp = node.created_at_timestamp;
      } else {
        // Try to parse as date string
        const timestamp = new Date(node.created_at_timestamp).getTime();
        sanitizedNode.created_at_timestamp = isNaN(timestamp) ? Date.now() : timestamp;
      }
    } else if (node.created_at) {
      // Fallback: derive from created_at string
      const timestamp = new Date(node.created_at).getTime();
      sanitizedNode.created_at_timestamp = isNaN(timestamp) ? Date.now() : timestamp;
    } else if (node.properties?.created_at_timestamp) {
      // Check properties as backup
      const propTimestamp = Number(node.properties.created_at_timestamp);
      sanitizedNode.created_at_timestamp = isNaN(propTimestamp) ? Date.now() : propTimestamp;
    } else {
      // Final fallback to current time
      sanitizedNode.created_at_timestamp = Date.now();
    }
    
    // Verify we have exactly 14 fields with no nulls
    const fieldCount = Object.keys(sanitizedNode).length;
    const nullCount = Object.values(sanitizedNode).filter(v => v === null || v === undefined).length;
    if (fieldCount !== 14 || nullCount > 0) {
      console.error(`[sanitizeNode] CRITICAL: DuckDB requires exactly 14 non-null fields. Have ${fieldCount} fields with ${nullCount} nulls:`, 
        Object.entries(sanitizedNode).map(([k, v]) => `${k}: ${v === null ? 'NULL' : typeof v}`));
    }
  } else {
    // Initial load: include all fields
    sanitizedNode.index = Number(index);
    sanitizedNode.id = String(node.id);
    sanitizedNode.label = String(node.label || node.name || node.id);
    sanitizedNode.node_type = String(node.node_type || 'Unknown');
    sanitizedNode.summary = node.summary ? String(node.summary) : null;
    // Add small variance to prevent STDDEV_SAMP errors
    // Keep raw values for the columns (they should already be 0-1 normalized from backend)
    const epsilon = 0.000001;
    const degreeValue = Number(sanitizedProperties.degree_centrality || 0);
    const pagerankValue = Number(sanitizedProperties.pagerank_centrality || 0);
    const betweennessValue = Number(sanitizedProperties.betweenness_centrality || 0);
    const eigenvectorValue = Number(sanitizedProperties.eigenvector_centrality || 0);
    
    // Add tiny random noise to centrality values to ensure variance
    sanitizedNode.degree_centrality = degreeValue + (Math.random() * epsilon);
    sanitizedNode.pagerank_centrality = pagerankValue + (Math.random() * epsilon);
    sanitizedNode.betweenness_centrality = betweennessValue + (Math.random() * epsilon);
    sanitizedNode.eigenvector_centrality = eigenvectorValue + (Math.random() * epsilon);
    
    sanitizedNode.x = node.x ?? null;
    sanitizedNode.y = node.y ?? null;
    sanitizedNode.color = generateNodeTypeColor(node.node_type || 'Unknown', nodeTypeIndex);
    // Use normalized size based on degree centrality (0-1 range)
    // This provides a consistent base that can be scaled by pointSizeRange
    sanitizedNode.size = degreeValue || 0.1;
    // Add color value that can be used by color schemes (same as degree by default)
    sanitizedNode.colorValue = degreeValue || 0.1;
    // Convert timestamp to number for consistency with DuckDB DOUBLE type
    // Handle both number and string formats for robustness
    if (node.created_at_timestamp !== undefined && node.created_at_timestamp !== null) {
      // If it's already a number, use it directly
      if (typeof node.created_at_timestamp === 'number') {
        sanitizedNode.created_at_timestamp = node.created_at_timestamp;
      } else {
        // Try to parse as date string
        const timestamp = new Date(node.created_at_timestamp).getTime();
        sanitizedNode.created_at_timestamp = isNaN(timestamp) ? Date.now() : timestamp;
      }
    } else if (node.created_at) {
      // Fallback: derive from created_at string
      const timestamp = new Date(node.created_at).getTime();
      sanitizedNode.created_at_timestamp = isNaN(timestamp) ? Date.now() : timestamp;
    } else if (node.properties?.created_at_timestamp) {
      // Check properties as backup
      const propTimestamp = Number(node.properties.created_at_timestamp);
      sanitizedNode.created_at_timestamp = isNaN(propTimestamp) ? Date.now() : propTimestamp;
    } else {
      // Final fallback to current time
      sanitizedNode.created_at_timestamp = Date.now();
    }
    sanitizedNode.cluster = String(cluster);
    sanitizedNode.clusterStrength = Number(config.clusterStrength ?? 0.7);
  }
  
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
  
  // Cosmograph's addLinks only passes these 5 fields to DuckDB:
  // source, target, sourceIndex, targetIndex, edge_type
  // Any other fields are filtered out internally
  
  const sanitizedLink: any = {};
  
  // Provide ONLY the 5 fields that Cosmograph will pass to DuckDB
  sanitizedLink.source = String(sourceId);
  sanitizedLink.target = String(targetId);
  sanitizedLink.sourceIndex = Number(sourceIndex);
  sanitizedLink.targetIndex = Number(targetIndex);
  sanitizedLink.edge_type = String(link.edge_type || 'default');
  
  // Note: The "9 columns but 5 values" error occurs because:
  // 1. DuckDB table was created with 9 columns from a previous version
  // 2. Cosmograph now only sends 5 values for incremental updates
  // 3. Solution: Run resetDuckDBStorage() in console and refresh page
  
  return sanitizedLink;
}

/**
 * Unified data preparer class
 */
export class CosmographDataPreparer {
  private config: DataPrepConfig;
  private nodeIdToIndex: Map<string, number> = new Map();
  private indexToNodeData: Map<number, any> = new Map();  // Store minimal node data
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
    this.indexToNodeData.clear();
    this.nodeTypeIndexMap.clear();
    
    // Sanitize all nodes
    const sanitizedNodes = nodes.map((node, index) => {
      this.nodeIdToIndex.set(node.id, index);
      // Store minimal node data for click handling
      this.indexToNodeData.set(index, {
        id: node.id,
        label: node.label || node.name || node.id,
        node_type: node.node_type,
        summary: node.summary
      });
      // Pass isIncremental=false for initial load
      return sanitizeNode(node, index, this.config, false);
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
      // Store minimal node data for click handling
      this.indexToNodeData.set(index, {
        id: node.id,
        label: node.label || node.name || node.id,
        node_type: node.node_type,
        summary: node.summary
      });
      // Pass isIncremental=true for incremental updates
      sanitizedNodes.push(sanitizeNode(node, index, this.config, true));
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
   * Get node data by index
   */
  getNodeByIndex(index: number): any | undefined {
    return this.indexToNodeData.get(index);
  }
  
  /**
   * Get node ID by index
   */
  getNodeIdByIndex(index: number): string | undefined {
    const nodeData = this.indexToNodeData.get(index);
    return nodeData?.id;
  }
  
  /**
   * Reset the preparer
   */
  reset() {
    this.nodeIdToIndex.clear();
    this.indexToNodeData.clear();
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