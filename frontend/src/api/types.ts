/**
 * API Types - Re-exports from canonical source
 * 
 * GRAPH-82: This file now re-exports types from @/types/graph.ts
 * for backwards compatibility. New code should import directly from @/types/graph.
 * 
 * @deprecated Import from '@/types/graph' instead
 */

// Re-export all types from the canonical source
export {
  // Node types
  type GraphNode,
  type IndexedGraphNode,
  type TransformedGraphNode,
  type NodeProperties,
  type GraphNodeProperties,
  
  // Edge types
  type GraphEdge,
  type GraphLink,
  type TransformedGraphLink,
  type EdgeProperties,
  type GraphEdgeProperties,
  
  // Data containers
  type GraphData,
  type GraphLinkData,
  type GraphDataStats,
  
  // Statistics
  type NodeTypeStats,
  type CentralityMetrics,
  type CentralityStats,
  type BulkCentralityResponse,
  type GraphStats,
  type ApiGraphStats,
  
  // API types
  type QueryResponse,
  type QueryParams,
  type SearchRequest,
  type SearchResponse,
  type NodeDetails,
  type ErrorResponse,
  
  // Graphiti types
  type NodeResult,
  type QueueStatus,
  
  // Utility functions
  edgeToLink,
  linkToEdge,
  hasNodeCentrality,
  getNodeLabel,
} from '../types/graph';

// Legacy type alias for NodeProperties with API-specific extensions
// This was previously defined here with additional fields
export interface ExtendedNodeProperties {
  // Centrality metrics
  pagerank?: number;
  degree?: number;
  connections?: number;
  importance_centrality?: number;
  importance?: number;
  custom_score?: number;
  date?: string;
  
  // Standard centrality (from base)
  degree_centrality?: number;
  betweenness_centrality?: number;
  closeness_centrality?: number;
  eigenvector_centrality?: number;
  pagerank_centrality?: number;
  
  // Temporal
  created_at?: string;
  updated_at?: string;
  
  // Metadata
  source?: string;
  confidence?: number;
  tags?: string[];
  
  // Index for type compatibility
  [key: string]: unknown;
}
