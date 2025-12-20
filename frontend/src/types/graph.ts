/**
 * Unified Graph Type Definitions
 * 
 * GRAPH-82: This is the canonical source for all graph-related types.
 * All other files should import from here.
 * 
 * Type Hierarchy:
 * - GraphNode: Core node type with all properties
 * - GraphEdge: Edge with from/to naming (database style)
 * - GraphLink: Edge with source/target naming (D3/Cosmograph style)
 * - GraphData: Container for nodes + edges
 */

import type { NodeProperties, EdgeProperties, NodeCentralityMetrics } from './properties';

// Re-export property types for convenience
export type { NodeProperties, EdgeProperties, NodeCentralityMetrics };
export type GraphNodeProperties = NodeProperties;
export type GraphEdgeProperties = EdgeProperties;

// =============================================================================
// CORE NODE TYPE
// =============================================================================

/**
 * Canonical GraphNode type - unified from api/types.ts and types/graph.ts
 * 
 * Usage:
 * - Import from '@/types/graph' or '../types/graph'
 * - Use for all node representations in the frontend
 */
export interface GraphNode {
  // Required fields
  id: string;
  
  // Display fields
  label?: string;
  name?: string;  // Alias for label (some APIs use this)
  
  // Type classification
  node_type: 'Entity' | 'Episodic' | 'Agent' | 'Community' | string;
  
  // Content fields
  summary?: string;
  description?: string;
  
  // Visual properties (set by frontend)
  size?: number;
  color?: string;
  x?: number;
  y?: number;
  
  // Temporal fields
  created_at?: string;
  created_at_timestamp?: number;  // Unix timestamp in milliseconds
  updated_at?: string;
  
  // Extended properties (centrality, metadata, custom)
  properties?: NodeProperties;
}

/**
 * Extended node with index for Cosmograph rendering
 */
export interface IndexedGraphNode extends GraphNode {
  index: number;
}

/**
 * Transformed node with computed centrality values hoisted to top level
 * Used after data transformation for efficient access
 */
export interface TransformedGraphNode extends IndexedGraphNode {
  centrality: number;
  cluster: string;
  clusterStrength: number;
  degree_centrality: number;
  pagerank_centrality: number;
  betweenness_centrality: number;
  eigenvector_centrality: number;
}

// =============================================================================
// EDGE TYPES
// =============================================================================

/**
 * GraphEdge - uses from/to naming convention (database style)
 * 
 * Use this type when working with data from the database/API
 */
export interface GraphEdge {
  id?: string;
  from: string;
  to: string;
  source?: string;  // Alias for from
  target?: string;  // Alias for to
  label?: string;
  edge_type?: string;
  weight?: number;
  properties?: EdgeProperties;
}

/**
 * GraphLink - uses source/target naming convention (D3/Cosmograph style)
 * 
 * Use this type when working with visualization libraries
 */
export interface GraphLink {
  source: string;
  target: string;
  edge_type?: string;
  weight?: number;
  name?: string;
  created_at?: string;
  updated_at?: string;
  properties?: EdgeProperties;
  [key: string]: unknown;  // Allow additional properties
}

/**
 * Transformed link with indices for Cosmograph rendering
 */
export interface TransformedGraphLink {
  source: string;
  sourceIndex: number;
  target: string;
  targetIndex: number;
  edge_type: string;
  weight: number;
  created_at?: string;
  updated_at?: string;
}

// =============================================================================
// GRAPH DATA CONTAINERS
// =============================================================================

/**
 * Statistics about graph data query/render performance
 */
export interface GraphDataStats {
  query_time?: number;
  render_time?: number;
  memory_usage?: number;
  [key: string]: unknown;
}

/**
 * Core graph data structure with nodes and edges
 */
export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats?: GraphDataStats;
}

/**
 * Graph data using link terminology (for D3/Cosmograph)
 */
export interface GraphLinkData {
  nodes: GraphNode[];
  links: GraphLink[];
  stats?: GraphDataStats;
}

// =============================================================================
// STATISTICS & METRICS
// =============================================================================

/**
 * Node type distribution statistics
 */
export interface NodeTypeStats {
  id: string;
  label: string;
  color: string;
  count: number;
}

/**
 * Centrality metrics for a single node
 */
export interface CentralityMetrics {
  degree: number;
  betweenness: number;
  pagerank: number;
  eigenvector: number;
}

/**
 * Aggregate centrality statistics across all nodes
 */
export interface CentralityStats {
  min_degree: number;
  max_degree: number;
  avg_degree: number;
  min_betweenness: number;
  max_betweenness: number;
  avg_betweenness: number;
  min_pagerank: number;
  max_pagerank: number;
  avg_pagerank: number;
  min_eigenvector: number;
  max_eigenvector: number;
  avg_eigenvector: number;
}

/**
 * Bulk centrality response (node ID -> metrics)
 */
export interface BulkCentralityResponse {
  [nodeId: string]: CentralityMetrics;
}

/**
 * Complete graph statistics for dashboard display
 */
export interface GraphStats {
  overview: {
    totalNodes: number;
    totalEdges: number;
    avgDegree: number;
    density: number;
  };
  nodeTypes: NodeTypeStats[];
  topNodes: Array<{
    name: string;
    degree: number;
    type: string;
  }>;
  performance: {
    queryTime: number;
    renderTime: number;
    fps: number;
    memory: number;
  };
}

/**
 * API-style graph statistics (snake_case)
 */
export interface ApiGraphStats {
  total_nodes: number;
  total_edges: number;
  node_types: Record<string, number>;
  edge_types?: Record<string, number>;
  avg_degree: number;
  density?: number;
  max_degree?: number;
}

// =============================================================================
// API RESPONSE TYPES
// =============================================================================

/**
 * Query response from the Rust API
 */
export interface QueryResponse {
  data: {
    nodes: GraphNode[];
    edges: GraphEdge[];
    stats: ApiGraphStats;
  };
  has_more: boolean;
  execution_time_ms: number;
}

/**
 * Query parameters for API requests
 */
export interface QueryParams {
  query_type?: string;
  limit?: number;
  offset?: number;
  search?: string;
}

/**
 * Search request parameters
 */
export interface SearchRequest {
  query: string;
  node_types?: string[];
  limit?: number;
}

/**
 * Search response
 */
export interface SearchResponse {
  nodes: GraphNode[];
  total: number;
}

/**
 * Extended node details with connections
 */
export interface NodeDetails extends GraphNode {
  centrality?: CentralityMetrics;
  connections: {
    incoming: GraphEdge[];
    outgoing: GraphEdge[];
  };
}

/**
 * API error response
 */
export interface ErrorResponse {
  error: string;
  details?: string;
}

// =============================================================================
// GRAPHITI-SPECIFIC TYPES (Python API)
// =============================================================================

/**
 * Node result from Graphiti Python API
 */
export interface NodeResult {
  uuid: string;
  name: string;
  summary: string;
  labels: string[];
  group_id: string;
  created_at: string;
  attributes: {
    labels?: string[];
    betweenness_centrality?: number;
    pagerank_centrality?: number;
    degree_centrality?: number;
    eigenvector_centrality?: number;
    [key: string]: unknown;
  };
}

/**
 * Queue status for background processing
 */
export interface QueueStatus {
  status: string;
  visible_messages: number;
  invisible_messages: number;
  total_processed: number;
  total_failed: number;
  success_rate: number;
  last_updated: string;
}

// =============================================================================
// TYPE UTILITIES
// =============================================================================

/**
 * Convert GraphEdge (from/to) to GraphLink (source/target)
 */
export function edgeToLink(edge: GraphEdge): GraphLink {
  return {
    source: edge.from || edge.source || '',
    target: edge.to || edge.target || '',
    edge_type: edge.edge_type,
    weight: edge.weight,
    properties: edge.properties,
  };
}

/**
 * Convert GraphLink (source/target) to GraphEdge (from/to)
 */
export function linkToEdge(link: GraphLink): GraphEdge {
  return {
    from: link.source,
    to: link.target,
    source: link.source,
    target: link.target,
    edge_type: link.edge_type,
    weight: link.weight,
    properties: link.properties,
  };
}

/**
 * Type guard to check if a node has centrality metrics
 */
export function hasNodeCentrality(node: GraphNode): boolean {
  return !!(
    node.properties?.degree_centrality ||
    node.properties?.pagerank_centrality ||
    node.properties?.betweenness_centrality ||
    node.properties?.eigenvector_centrality
  );
}

/**
 * Extract display label from a node
 */
export function getNodeLabel(node: GraphNode): string {
  return node.label || node.name || node.id;
}
