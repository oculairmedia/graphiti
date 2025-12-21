/**
 * GraphCanvas type definitions
 * Canonical interface for GraphCanvas component handle
 * 
 * IMPORTANT: This should match the useImperativeHandle in GraphCanvasV2.tsx
 */

import type { GraphNode, GraphLink } from './graph';
import type { CosmographRef } from '@cosmograph/react';

/**
 * Interface defining all methods available on the GraphCanvas component
 */
export interface GraphCanvasHandle {
  // Selection methods
  clearSelection: () => void;
  selectNode: (node: GraphNode) => void;
  selectNodes: (nodes: GraphNode[]) => void;
  
  // Camera/view methods
  focusNode?: (nodeId: string, duration?: number, scale?: number) => void;
  focusOnNodes: (nodeIds: string[], duration?: number, padding?: number) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: (duration?: number, padding?: number) => void;
  fitViewByPointIndices: (indices: number[], duration?: number, padding?: number) => void;
  zoomToPoint: (index: number, duration?: number, scale?: number, canZoomOut?: boolean) => void;
  trackPointPositionsByIndices: (indices: number[]) => void;
  getTrackedPointPositionsMap: () => Map<number, [number, number]> | undefined;
  
  // Data methods
  setData: (nodes: GraphNode[], links: GraphLink[], runSimulation?: boolean) => void;
  restart: () => void;
  getLiveStats?: () => { nodeCount: number; edgeCount: number; lastUpdated: number };
  
  // Selection tools
  activateRectSelection: () => void;
  deactivateRectSelection: () => void;
  activatePolygonalSelection: () => void;
  deactivatePolygonalSelection: () => void;
  selectPointsInRect: (selection: [[number, number], [number, number]] | null, addToSelection?: boolean) => void;
  selectPointsInPolygon: (polygonPoints: [number, number][], addToSelection?: boolean) => void;
  getConnectedPointIndices: (index: number) => number[] | undefined;
  getPointIndicesByExactValues: (keyValues: Record<string, unknown>) => number[] | undefined;
  
  // Incremental update methods
  addIncrementalData: (newNodes: GraphNode[], newLinks: GraphLink[], runSimulation?: boolean) => void;
  updateNodes: (updatedNodes: GraphNode[]) => void;
  updateLinks: (updatedLinks: GraphLink[]) => void;
  removeNodes: (nodeIds: string[]) => void;
  removeLinks: (linkIds: string[]) => void;
  
  // Simulation control
  startSimulation: (alpha?: number) => void;
  pauseSimulation: () => void;
  resumeSimulation: () => void;
  keepSimulationRunning: (enable: boolean) => void;
  setIncrementalUpdateFlag: (enabled: boolean) => void;
  
  // Legacy methods for backwards compatibility (from old interface)
  getSelectedNodes?: () => string[];
  highlightNodes?: (nodeIds: string[]) => void;
  clearHighlights?: () => void;
  togglePhysics?: () => void;
  setPhysicsEnabled?: (enabled: boolean) => void;
  getCameraState?: () => { x: number; y: number; zoom: number } | null;
  setCameraState?: (state: { x: number; y: number; zoom: number }) => void;
  centerCamera?: () => void;
  getNodePositions?: () => Map<string, { x: number; y: number }>;
  setNodePositions?: (positions: Map<string, { x: number; y: number }>) => void;
  restartSimulation?: () => void;
  exportImage?: (format?: 'png' | 'jpeg') => Promise<string | null>;
  getGraphData?: () => { nodes: GraphNode[]; links: GraphLink[] };
  updateGraphData?: (data: { nodes?: GraphNode[]; links?: GraphLink[] }) => void;
  findShortestPath?: (sourceId: string, targetId: string) => string[] | null;
  getNeighbors?: (nodeId: string, depth?: number) => Set<string>;
  applyLayout?: (layout: string, options?: unknown) => void;
  getGraphStats?: () => { nodeCount: number; edgeCount: number; components: number };
  
  // Internal reference access
  getCosmographRef?: () => React.RefObject<CosmographRef>;
}

/**
 * Type for the GraphCanvas ref
 */
export type GraphCanvasRef = GraphCanvasHandle;
