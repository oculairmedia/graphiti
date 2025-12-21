/**
 * Cosmograph Data Preparer
 * 
 * Unified data preparation pipeline using Cosmograph's prepareCosmographData function
 * Ensures type consistency between initial load and incremental updates
 */

import { prepareCosmographData } from '@cosmograph/react';
import type { GraphNode, GraphLink } from '../types/graph';
import { generateNodeTypeColor } from './NodeColorManager';

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

// PERFORMANCE: Cache for sanitized nodes to avoid re-processing
const sanitizationCache = new Map<string, any>();
const CACHE_MAX_SIZE = 10000; // Limit cache size to prevent memory issues

/**
 * Generate cache key for a node
 */
function generateNodeCacheKey(
  nodeId: string,
  clusteringMethod?: string,
  isIncremental: boolean = false
): string {
  return `${nodeId}-${clusteringMethod || 'none'}-${isIncremental ? 'inc' : 'full'}`;
}

/**
 * Clear sanitization cache (call when config changes significantly)
 */
export function clearSanitizationCache(): void {
  sanitizationCache.clear();
}

/**
 * Transform and sanitize a node for Cosmograph
 * Exported for use in GraphCanvasV2
 * PERFORMANCE: Now cached to avoid redundant processing
 */
export function sanitizeNode(
  node: GraphNode,
  index: number,
  config: DataPrepConfig = {},
  isIncremental: boolean = false
): any {
  // PERFORMANCE: Check cache first
  const cacheKey = generateNodeCacheKey(node.id, config.clusteringMethod, isIncremental);
  if (sanitizationCache.has(cacheKey)) {
    const cached = sanitizationCache.get(cacheKey)!;
    // PERFORMANCE FIX (GRAPH-62): Return shallow copy with updated index
    // Mutating cached object in place was causing React to detect "changes" 
    // and trigger unnecessary re-renders. Spread operator creates a new reference
    // but reuses all the existing property values (cheap shallow copy).
    return { ...cached, index: Number(index) };
  }
  
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
    ? String(Math.floor(Number(node.properties?.[config.centralityMetric + '_centrality'] || 0) * 10))
    : String(node.node_type || 'Unknown');
  
  // Sanitize all properties
  const sanitizedProperties = sanitizeProperties(node.properties);
  
  // Build sanitized node - ensure consistent field count for DuckDB
  // For incremental updates: exactly 11 non-null fields expected
  // Fields that Cosmograph actually uses (based on debug output)
  const sanitizedNode: any = {};
  
  if (isIncremental) {
    // Incremental updates: MUST provide exactly 16 NON-NULL fields to match cosmograph_points view schema
    // The cosmograph_points view has these 16 fields:
    // index, id, label, node_type, summary, degree_centrality, pagerank_centrality,
    // betweenness_centrality, eigenvector_centrality, x, y, color, size, created_at_timestamp, cluster, clusterStrength
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

    // Add x, y coordinates (required by cosmograph_points view)
    // For incremental updates, these will be null initially and computed by Cosmograph
    sanitizedNode.x = null;
    sanitizedNode.y = null;

    sanitizedNode.color = generateNodeTypeColor(node.node_type || 'Unknown', nodeTypeIndex);
    // Use normalized size based on degree centrality (0-1 range)
    // This provides a consistent base that can be scaled by pointSizeRange
    sanitizedNode.size = degreeValue || 0.1;
    // Note: colorValue is NOT in the cosmograph_points schema, so we don't include it for incremental updates
    sanitizedNode.cluster = String(cluster);
    sanitizedNode.clusterStrength = Number(config.clusterStrength ?? 0.7);
    // CRITICAL: created_at_timestamp MUST be a number (Unix timestamp) for DuckDB
    // DuckDB created this column as DOUBLE type, not string
    // Handle both number and string formats for robustness
    if (node.created_at_timestamp !== undefined && node.created_at_timestamp !== null) {
      // If it's already a number, use it directly
      if (typeof node.created_at_timestamp === 'number') {
        sanitizedNode.created_at_timestamp = isFinite(node.created_at_timestamp) ? node.created_at_timestamp : Date.now();
      } else {
        // Try to parse as date string
        try {
          const timestamp = new Date(String(node.created_at_timestamp)).getTime();
          sanitizedNode.created_at_timestamp = isFinite(timestamp) ? timestamp : Date.now();
        } catch (e) {
          sanitizedNode.created_at_timestamp = Date.now();
        }
      }
    } else if (node.created_at) {
      // Fallback: derive from created_at string
      try {
        const timestamp = new Date(String(node.created_at)).getTime();
        sanitizedNode.created_at_timestamp = isFinite(timestamp) ? timestamp : Date.now();
      } catch (e) {
        sanitizedNode.created_at_timestamp = Date.now();
      }
    } else if ((node.properties as any)?.created_at_timestamp) {
      // Check properties as backup (with type assertion since it's dynamic)
      const propTimestamp = Number((node.properties as any).created_at_timestamp);
      sanitizedNode.created_at_timestamp = isFinite(propTimestamp) ? propTimestamp : Date.now();
    } else {
      // Final fallback to current time
      sanitizedNode.created_at_timestamp = Date.now();
    }
    
    // Verify we have exactly 16 fields to match cosmograph_points view
    // Note: x and y can be null for incremental updates (they'll be computed by Cosmograph)
    const fieldCount = Object.keys(sanitizedNode).length;
    const nullCount = Object.values(sanitizedNode).filter(v => v === null || v === undefined).length;
    const allowedNulls = ['x', 'y']; // These fields can be null for incremental updates
    const actualNulls = Object.entries(sanitizedNode)
      .filter(([k, v]) => v === null || v === undefined)
      .map(([k, v]) => k);
    const unexpectedNulls = actualNulls.filter(field => !allowedNulls.includes(field));

    if (fieldCount !== 16 || unexpectedNulls.length > 0) {
      console.error(`[sanitizeNode] CRITICAL: DuckDB cosmograph_points view requires exactly 16 fields with only x,y allowed to be null. Have ${fieldCount} fields with unexpected nulls in [${unexpectedNulls.join(', ')}]:`,
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
    // Note: colorValue is NOT in the cosmograph_points schema
    // Convert timestamp to number for consistency with DuckDB DOUBLE type
    // Handle both number and string formats for robustness
    if (node.created_at_timestamp !== undefined && node.created_at_timestamp !== null) {
      // If it's already a number, use it directly
      if (typeof node.created_at_timestamp === 'number') {
        sanitizedNode.created_at_timestamp = isFinite(node.created_at_timestamp) ? node.created_at_timestamp : Date.now();
      } else {
        // Try to parse as date string
        try {
          const timestamp = new Date(String(node.created_at_timestamp)).getTime();
          sanitizedNode.created_at_timestamp = isFinite(timestamp) ? timestamp : Date.now();
        } catch (e) {
          sanitizedNode.created_at_timestamp = Date.now();
        }
      }
    } else if (node.created_at) {
      // Fallback: derive from created_at string
      try {
        const timestamp = new Date(String(node.created_at)).getTime();
        sanitizedNode.created_at_timestamp = isFinite(timestamp) ? timestamp : Date.now();
      } catch (e) {
        sanitizedNode.created_at_timestamp = Date.now();
      }
    } else if ((node.properties as any)?.created_at_timestamp) {
      // Check properties as backup (with type assertion since it's dynamic)
      const propTimestamp = Number((node.properties as any).created_at_timestamp);
      sanitizedNode.created_at_timestamp = isFinite(propTimestamp) ? propTimestamp : Date.now();
    } else {
      // Final fallback to current time
      sanitizedNode.created_at_timestamp = Date.now();
    }
    sanitizedNode.cluster = String(cluster);
    sanitizedNode.clusterStrength = Number(config.clusterStrength ?? 0.7);
    
    // Verify we have exactly 16 fields to match cosmograph_points view (for initial load too)
    const fieldCount = Object.keys(sanitizedNode).length;
    const nullCount = Object.values(sanitizedNode).filter(v => v === null || v === undefined).length;
    const allowedNulls = ['x', 'y', 'summary']; // These fields can be null
    const actualNulls = Object.entries(sanitizedNode)
      .filter(([k, v]) => v === null || v === undefined)
      .map(([k, v]) => k);
    const unexpectedNulls = actualNulls.filter(field => !allowedNulls.includes(field));

    if (fieldCount !== 16 || unexpectedNulls.length > 0) {
      console.error(`[sanitizeNode] CRITICAL: DuckDB cosmograph_points view requires exactly 16 fields. Have ${fieldCount} fields with unexpected nulls in [${unexpectedNulls.join(', ')}]:`,
        Object.entries(sanitizedNode).map(([k, v]) => `${k}: ${v === null ? 'NULL' : typeof v}`));
    }
  }
  
  // PERFORMANCE: Store in cache (with size limit to prevent memory issues)
  if (sanitizationCache.size < CACHE_MAX_SIZE) {
    sanitizationCache.set(cacheKey, sanitizedNode);
  } else if (sanitizationCache.size === CACHE_MAX_SIZE) {
    // Clear 20% of cache when limit reached (FIFO)
    const keysToDelete = Array.from(sanitizationCache.keys()).slice(0, Math.floor(CACHE_MAX_SIZE * 0.2));
    keysToDelete.forEach(key => sanitizationCache.delete(key));
    sanitizationCache.set(cacheKey, sanitizedNode);
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

// =============================================================================
// TRANSFORM UTILITIES (consolidated from cosmographTransformers.ts)
// =============================================================================

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
  [key: string]: any;
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
  [key: string]: any;
}

/**
 * Delta update types
 */
export type DeltaOperation = 'add' | 'update' | 'delete';

/**
 * Core delta update payload (flat format)
 */
export interface DeltaUpdate {
  // For flat format
  operation: DeltaOperation;
  nodes?: GraphNode[];
  edges?: GraphLink[];
  nodeIds?: string[];
  edgeIds?: string[];
  timestamp?: number;
  
  // For wrapped format (WebSocket events)
  type?: 'graph:update' | 'graph:delta';
  data?: {
    operation: DeltaOperation;
    nodes?: GraphNode[] | string[];
    edges?: GraphLink[] | string[];
    timestamp?: number;
  };
}

/**
 * Transform a GraphNode to Cosmograph point format (lightweight version)
 */
export function transformNodeForCosmograph(
  node: GraphNode,
  index?: number
): CosmographPointInput {
  return {
    ...node,
    id: node.id,
    idx: index,
    index: index,
    label: node.label || node.name || node.id,
    name: node.name || node.label || node.id,
    size: node.size || 5,
    cluster: node.node_type || 'Unknown',
  };
}

/**
 * Transform a GraphLink to Cosmograph link format
 */
export function transformEdgeForCosmograph(
  edge: GraphLink,
  nodeIdToIndex?: Map<string, number>
): CosmographLinkInput {
  const source = edge.source || (edge as any).from;
  const target = edge.target || (edge as any).to;
  
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
 * Transform nodes array for batch addition
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
 */
export function transformEdgesForCosmograph(
  edges: GraphLink[],
  nodeIdToIndex?: Map<string, number>
): CosmographLinkInput[] {
  return edges.map(edge => transformEdgeForCosmograph(edge, nodeIdToIndex));
}

/**
 * Extract edge pairs from edges for removal operations
 */
export function extractEdgePairs(
  edges: (GraphLink | string)[]
): [string, string][] {
  return edges.map(edge => {
    if (typeof edge === 'string') {
      const [source, ...targetParts] = edge.split('-');
      const target = targetParts.join('-');
      return [source, target] as [string, string];
    } else {
      const source = edge.source || (edge as any).from;
      const target = edge.target || (edge as any).to;
      return [source, target] as [string, string];
    }
  });
}

/**
 * Build a node ID to index map from current graph data
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
 */
export function filterValidEdges(
  edges: GraphLink[],
  nodeIds: Set<string>
): GraphLink[] {
  return edges.filter(edge => {
    const source = edge.source || (edge as any).from;
    const target = edge.target || (edge as any).to;
    return nodeIds.has(source) && nodeIds.has(target);
  });
}

/**
 * Check if Cosmograph instance has incremental update methods
 */
export function supportsIncrementalUpdates(cosmographRef: any): boolean {
  return !!(
    cosmographRef?.current?.addPoints &&
    cosmographRef?.current?.addLinks &&
    cosmographRef?.current?.removePointsByIds &&
    cosmographRef?.current?.removeLinksByPointIdPairs
  );
}

/**
 * Transform a complete delta update for Cosmograph
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

  if (delta.nodes && delta.nodes.length > 0) {
    if (delta.operation === 'add') {
      result.nodes = transformNodesForCosmograph(delta.nodes, currentNodeCount);
      delta.nodes.forEach((node, i) => {
        nodeIdToIndex.set(node.id, currentNodeCount + i);
      });
    } else if (delta.operation === 'update') {
      result.nodes = delta.nodes.map(node => {
        const existingIndex = nodeIdToIndex.get(node.id);
        return transformNodeForCosmograph(node, existingIndex);
      });
    } else if (delta.operation === 'delete') {
      result.nodeIdsToRemove = delta.nodeIds || delta.nodes.map(n => n.id);
    }
  }

  if (delta.edges && delta.edges.length > 0) {
    if (delta.operation === 'add' || delta.operation === 'update') {
      result.edges = transformEdgesForCosmograph(delta.edges, nodeIdToIndex);
    } else if (delta.operation === 'delete') {
      result.edgePairsToRemove = extractEdgePairs(delta.edgeIds || delta.edges);
    }
  }

  return result;
}