// Shared component interface types

import type { GraphNode, GraphLink } from './graph';
import type { GraphConfig } from '../contexts/configTypes';
import type { CosmographRef } from '@cosmograph/react';

// Re-export GraphCanvasHandle from the canonical source
export type { GraphCanvasHandle, GraphCanvasRef } from './graphCanvas';

// Configuration update handler type
export type ConfigUpdateHandler = (updates: Partial<GraphConfig>) => void;

// Node type configuration handlers
export type NodeTypeColorChangeHandler = (type: string, color: string) => void;
export type NodeTypeVisibilityChangeHandler = (type: string, visible: boolean) => void;

// Graph stats interface
export interface GraphStats {
  nodeCount: number;
  edgeCount: number;
  nodeTypes: Record<string, number>;
  centralityStats?: {
    min: number;
    max: number;
    avg: number;
  };
}

// Filter configuration interface
export interface FilterConfig {
  nodeTypes?: string[];
  searchTerm?: string;
  dateRange?: {
    start: Date | null;
    end: Date | null;
  };
  centralityRange?: {
    min: number;
    max: number;
  };
}

// Layout options interface
export interface LayoutOptions {
  canvasWidth?: number;
  canvasHeight?: number;
  nodeSpacing?: number;
  levelHeight?: number;
  circleRadius?: number;
  clusterSpacing?: number;
  sortBy?: 'degree' | 'centrality' | 'type' | 'alphabetical';
  clusterBy?: 'type' | 'community' | 'centrality' | 'temporal';
  temporalSpacing?: number;
  physics?: {
    charge?: number;
    linkDistance?: number;
    gravity?: number;
  };
}

// Component prop types
export interface GraphVizProps {
  className?: string;
}

export interface ControlPanelProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  onLayoutChange: (layout: string) => void;
}

export interface NodeDetailsPanelProps {
  node: GraphNode;
  onClose: () => void;
  onShowNeighbors?: (nodeId: string) => void;
}

// Event handler types
export type NodeClickHandler = (node: GraphNode) => void;
export type NodeSelectHandler = (nodeId: string) => void;
export type NodesSelectHandler = (nodes: GraphNode[]) => void;
export type NodeHoverHandler = (node: GraphNode | null) => void;
export type ClearSelectionHandler = () => void;
export type ShowNeighborsHandler = (nodeId: string) => void;

// Cosmograph extended type for internal properties
// Note: CosmographRef is a union type (_Cosmograph | undefined), so we use
// type intersection instead of interface extension
export type CosmographExtended = NonNullable<CosmographRef> & {
  _camera?: {
    pan: (delta: { x: number; y: number }) => void;
  };
  _canvasElement?: HTMLCanvasElement;
};