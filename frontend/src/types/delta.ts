/**
 * Delta update types for incremental graph updates
 */

import type { GraphNode, GraphEdge } from './graph';

export type DeltaType = 'incremental' | 'full' | 'snapshot';

export interface GraphDelta {
  sequence: number;
  timestamp: number;
  type: DeltaType;
  added_nodes?: GraphNode[];
  added_edges?: GraphEdge[];
  updated_nodes?: Partial<GraphNode>[];
  updated_edges?: Partial<GraphEdge>[];
  removed_nodes?: string[];
  removed_edges?: string[];
}

export interface DeltaOperation {
  type: 'add' | 'update' | 'remove';
  entity: 'node' | 'edge';
  data: GraphNode | GraphEdge | Partial<GraphNode> | Partial<GraphEdge> | string;
}
