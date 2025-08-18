/**
 * GraphCanvas type definitions
 * Extracted from the original GraphCanvas.tsx component
 */

/**
 * Interface defining all methods available on the GraphCanvas component
 */
export interface GraphCanvasHandle {
  clearSelection: () => void;
  selectNode: (nodeId: string) => void;
  selectNodes: (nodeIds: string[]) => void;
  focusOnNodes: (nodeIds: string[], duration?: number) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
  getSelectedNodes: () => string[];
  highlightNodes: (nodeIds: string[]) => void;
  clearHighlights: () => void;
  togglePhysics: () => void;
  setPhysicsEnabled: (enabled: boolean) => void;
  getCameraState: () => { x: number; y: number; zoom: number } | null;
  setCameraState: (state: { x: number; y: number; zoom: number }) => void;
  centerCamera: () => void;
  getNodePositions: () => Map<string, { x: number; y: number }>;
  setNodePositions: (positions: Map<string, { x: number; y: number }>) => void;
  pauseSimulation: () => void;
  resumeSimulation: () => void;
  restartSimulation: () => void;
  exportImage: (format?: 'png' | 'jpeg') => Promise<string | null>;
  getGraphData: () => { nodes: any[]; links: any[] };
  updateGraphData: (data: { nodes?: any[]; links?: any[] }) => void;
  findShortestPath: (sourceId: string, targetId: string) => string[] | null;
  getNeighbors: (nodeId: string, depth?: number) => Set<string>;
  applyLayout: (layout: string, options?: any) => void;
  getGraphStats: () => { nodeCount: number; edgeCount: number; components: number };
}

/**
 * Type for the GraphCanvas ref
 */
export type GraphCanvasRef = GraphCanvasHandle;