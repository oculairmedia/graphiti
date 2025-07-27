// Types matching the Rust server API responses

// Graph node property types
export interface NodeProperties {
  degree_centrality?: number;
  betweenness_centrality?: number;
  pagerank_centrality?: number;
  eigenvector_centrality?: number;
  pagerank?: number;
  degree?: number;
  connections?: number;
  importance_centrality?: number;
  importance?: number;
  custom_score?: number;
  created?: string;
  date?: string;
  // Allow for additional dynamic properties
  [key: string]: unknown;
}

export interface GraphNode {
  id: string;
  label: string;
  node_type: string;
  summary?: string;  // Add summary field for node description/content
  size: number;
  color: string;
  properties: NodeProperties;
  created_at?: string;
  updated_at?: string;
}

export interface GraphEdge {
  from: string;
  to: string;
  edge_type: string;
  weight: number;
}

export interface GraphStats {
  total_nodes: number;
  total_edges: number;
  node_types: Record<string, number>;
  edge_types?: Record<string, number>;
  avg_degree: number;
  density?: number;
  max_degree?: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: GraphStats;
}

export interface QueryResponse {
  data: GraphData;
  has_more: boolean;
  execution_time_ms: number;
}

export interface QueryParams {
  query_type?: string;
  limit?: number;
  offset?: number;
  search?: string;
}

export interface SearchRequest {
  query: string;
  node_types?: string[];
  limit?: number;
}

export interface SearchResponse {
  nodes: GraphNode[];
  total: number;
}

export interface NodeDetails extends GraphNode {
  created_at?: string;
  updated_at?: string;
  centrality?: CentralityMetrics;
  connections: {
    incoming: GraphEdge[];
    outgoing: GraphEdge[];
  };
}

export interface ErrorResponse {
  error: string;
  details?: string;
}

// Centrality types
export interface CentralityMetrics {
  degree: number;
  betweenness: number;
  pagerank: number;
  eigenvector: number;
}

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

export interface BulkCentralityResponse {
  [nodeId: string]: CentralityMetrics;
}