// Shared component interface types

import type { GraphNode, GraphLink } from './graph';
import type { GraphConfig } from '../contexts/configTypes';
import type { CosmographRef } from '@cosmograph/react';

// GraphCanvas component handle interface
export interface GraphCanvasHandle {
  clearSelection: () => void;
  selectNode: (node: GraphNode) => void;
  selectNodes: (nodes: GraphNode[]) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: (duration?: number, padding?: number) => void;
  fitViewByPointIndices: (indices: number[], duration?: number, padding?: number) => void;
  zoomToPoint: (index: number, duration?: number, scale?: number, canZoomOut?: boolean) => void;
  trackPointPositionsByIndices: (indices: number[]) => void;
  getTrackedPointPositionsMap: () => Map<number, [number, number]> | undefined;
  setData: (nodes: GraphNode[], links: GraphLink[], runSimulation?: boolean) => void;
  restart: () => void;
  activateRectSelection: () => void;
  deactivateRectSelection: () => void;
  activatePolygonalSelection: () => void;
  deactivatePolygonalSelection: () => void;
  selectPointsInRect: (selection: [[number, number], [number, number]] | null, addToSelection?: boolean) => void;
  selectPointsInPolygon: (polygonPoints: [number, number][], addToSelection?: boolean) => void;
  getConnectedPointIndices: (index: number) => number[] | undefined;
  getPointIndicesByExactValues: (keyValues: Record<string, unknown>) => number[] | undefined;
  addIncrementalData: (newNodes: GraphNode[], newLinks: GraphLink[], runSimulation?: boolean) => void;
  updateNodes: (updatedNodes: GraphNode[]) => void;
  updateLinks: (updatedLinks: GraphLink[]) => void;
  removeNodes: (nodeIds: string[]) => void;
  removeLinks: (linkIds: string[]) => void;
  startSimulation: (alpha?: number) => void;
  pauseSimulation: () => void;
  resumeSimulation: () => void;
  keepSimulationRunning: (enable: boolean) => void;
  setIncrementalUpdateFlag: (enabled: boolean) => void;
}

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

// Cosmograph extended interface for internal properties
export interface CosmographExtended extends CosmographRef {
  _camera?: {
    pan: (delta: { x: number; y: number }) => void;
  };
  _canvasElement?: HTMLCanvasElement;
}