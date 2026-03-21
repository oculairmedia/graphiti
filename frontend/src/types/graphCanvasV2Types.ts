import type { GraphNode, GraphLink } from './graph';

export interface GraphStats {
  total_nodes: number;
  total_edges: number;
  density?: number;
  [key: string]: unknown;
}

export interface GraphCanvasProps {
  onNodeClick: (node: GraphNode) => void;
  onNodeSelect: (nodeId: string) => void;
  onSelectNodes?: (nodes: GraphNode[]) => void;
  onClearSelection?: () => void;
  onNodeHover?: (node: GraphNode | null) => void;
  onStatsUpdate?: (stats: { nodeCount: number; edgeCount: number; lastUpdated: number }) => void;
  onContextReady?: (isReady: boolean) => void;
  selectedNodes: string[];
  highlightedNodes: string[];
  className?: string;
  stats?: GraphStats;
}

export interface GraphCanvasComponentProps extends GraphCanvasProps {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface WebSocketEvent {
  type: string;
  node_ids?: string[];
  nodes?: GraphNode[];
  edges?: GraphLink[];
  operation?: 'add' | 'update' | 'delete';
}

export interface DeltaUpdateEvent extends WebSocketEvent {
  operation: 'add' | 'update' | 'delete';
}

export interface StatsUpdatePayload {
  nodeCount: number;
  edgeCount: number;
  lastUpdated: number;
}
