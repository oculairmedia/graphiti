// Graph data types for Graphiti frontend

import type { NodeProperties, EdgeProperties } from './properties';

// Re-export NodeProperties for backward compatibility
export type GraphNodeProperties = NodeProperties;

export interface GraphNode {
  id: string;
  label?: string;
  name?: string; // Alias for label
  node_type: 'Entity' | 'Episodic' | 'Agent' | 'Community' | string;
  summary?: string;
  description?: string;
  created_at?: string;
  created_at_timestamp?: number;
  updated_at?: string;
  x?: number;
  y?: number;
  properties?: NodeProperties;
}

// Re-export EdgeProperties for backward compatibility
export type GraphEdgeProperties = EdgeProperties;

export interface GraphEdge {
  id: string;
  from: string;
  to: string;
  source?: string; // Alias for from
  target?: string; // Alias for to
  label?: string;
  weight?: number;
  edge_type?: string;
  properties?: EdgeProperties;
}

// GraphLink is an alias for edges with source/target naming
export interface GraphLink {
  source: string;
  target: string;
  edge_type?: string;
  weight?: number;
  name?: string;
  properties?: EdgeProperties;
  [key: string]: any;
}

export interface GraphDataStats {
  query_time?: number;
  render_time?: number;
  memory_usage?: number;
  [key: string]: unknown;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats?: GraphDataStats;
}

export interface NodeTypeStats {
  id: string;
  label: string;
  color: string;
  count: number;
}

export interface CentralityMetrics {
  degree: number;
  betweenness: number;
  pagerank: number;
  eigenvector: number;
}

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