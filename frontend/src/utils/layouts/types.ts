import type { GraphNode, GraphEdge } from '../../types/graph';

export interface LayoutPosition {
  x: number;
  y: number;
}

export interface LayoutOptions {
  hierarchyDirection?: 'top-down' | 'bottom-up' | 'left-right' | 'right-left';
  radialCenter?: string;
  circularOrdering?: 'degree' | 'centrality' | 'type' | 'alphabetical';
  clusterBy?: 'type' | 'community' | 'centrality' | 'temporal';
  canvasWidth?: number;
  canvasHeight?: number;
}

export interface LayoutAlgorithm {
  name: string;
  calculate: (nodes: GraphNode[], edges: GraphEdge[], options?: LayoutOptions) => LayoutPosition[];
}

// Default canvas dimensions for layout calculations
export const DEFAULT_CANVAS_WIDTH = 1200;
export const DEFAULT_CANVAS_HEIGHT = 800;