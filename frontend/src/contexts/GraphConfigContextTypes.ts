import React from 'react';
import type { GraphNode, GraphEdge } from '../types/graph';
import type { GraphConfig } from './configTypes';

interface CosmographLink {
  source: string;
  target: string;
  weight?: number;
  edge_type?: string;
  properties?: Record<string, unknown>;
  [key: string]: unknown;
}

interface CosmographRefType {
  // Zoom controls
  setZoomLevel: (level: number, duration?: number) => void;
  getZoomLevel: () => number;
  fitView: (duration?: number) => void;
  fitViewByPointIndices: (indices: number[], duration?: number, padding?: number) => void;
  fitViewByIndices: (indices: number[], duration?: number, padding?: number) => void;
  zoomToPoint: (index: number, duration?: number, scale?: number, canZoomOut?: boolean) => void;
  
  // Position tracking
  trackPointPositionsByIndices: (indices: number[]) => void;
  getTrackedPointPositionsMap: () => Map<number, [number, number]> | undefined;
  getTrackedPointPositionsArray: () => Float32Array | undefined;
  
  // Selection methods
  selectNode: (node: unknown) => void;
  selectNodes: (nodes: unknown[]) => void;
  selectPoint?: (index: number, selectAdjacentLinks?: boolean, selectAdjacentNodes?: boolean) => void;
  selectPoints?: (indices: number[], selectAdjacentLinks?: boolean) => void;
  unselectAll: () => void;
  unselectAllPoints?: () => void;
  setFocusedPoint?: (index: number | null) => void;
  unfocusNode: () => void;
  
  // Search/query methods
  getPointIndicesByExactValues?: (keyValues: Record<string, unknown>) => number[] | undefined;
  getConnectedPointIndices?: (index: number) => number[] | undefined;
  
  // Selection tools
  activateRectSelection?: () => void;
  deactivateRectSelection?: () => void;
  activatePolygonalSelection?: () => void;
  deactivatePolygonalSelection?: () => void;
  selectPointsInRect?: (selection: [[number, number], [number, number]] | null, addToSelection?: boolean) => void;
  selectPointsInPolygon?: (polygonPoints: [number, number][], addToSelection?: boolean) => void;
  
  // Simulation control
  restart: () => void;
  start: (alpha?: number) => void;
  pause?: () => void;
  
  // Data methods
  setData?: (nodes: GraphNode[], links: CosmographLink[], runSimulation?: boolean) => void;
  addPoints?: (points: unknown[]) => void;
  removePoints?: (indices: number[]) => void;
  updatePoints?: (updates: Array<{ index: number; data: unknown }>) => void;
  addLinks?: (links: CosmographLink[]) => void;
  removeLinks?: (pairs: [number, number][]) => void;
  
  // Internal
  _canvasElement?: HTMLCanvasElement;
}

export interface GraphConfigContextType {
  config: GraphConfig;
  updateConfig: (updates: Partial<GraphConfig>) => void;
  updateNodeTypeConfigurations: (nodeTypes: string[]) => void;
  cosmographRef: React.RefObject<CosmographRefType> | null;
  setCosmographRef: (ref: React.RefObject<CosmographRefType>) => void;
  // Graph control methods
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
  applyLayout: (layoutType: string, options?: Record<string, unknown>, graphData?: { nodes: GraphNode[], edges: GraphEdge[] }) => void;
  isApplyingLayout: boolean;
}