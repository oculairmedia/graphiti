// Graph data types for Graphiti frontend

import type { NodeProperties, EdgeProperties } from './properties';

// Re-export NodeProperties for backward compatibility
export type GraphNodeProperties = NodeProperties;

export interface GraphNode {
  id: string;
  label?: string;
  node_type: 'Entity' | 'Episodic' | 'Agent' | 'Community' | string;
  summary?: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
  properties?: NodeProperties;
}

// Re-export EdgeProperties for backward compatibility
export type GraphEdgeProperties = EdgeProperties;

export interface GraphEdge {
  id: string;
  from: string;
  to: string;
  label?: string;
  weight?: number;
  edge_type?: string;
  properties?: EdgeProperties;
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