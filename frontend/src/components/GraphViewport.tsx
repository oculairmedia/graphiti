import React, { forwardRef } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import { GraphCanvas } from './GraphCanvas';
import { NodeDetailsPanel } from './NodeDetailsPanel';
import { QuickActions } from './QuickActions';
import GraphErrorBoundary from './GraphErrorBoundary';

interface GraphCanvasHandle {
  clearSelection: () => void;
  selectNode: (node: GraphNode) => void;
  selectNodes: (nodes: GraphNode[]) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
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

interface GraphViewportProps {
  nodes: GraphNode[];
  links: GraphLink[];
  selectedNodes: string[];
  highlightedNodes: string[];
  hoveredNode: GraphNode | null;
  hoveredConnectedNodes: string[];
  selectedNode: GraphNode | null;
  stats?: any;
  onNodeClick: (node: GraphNode) => void;
  onNodeSelect: (nodeId: string) => void;
  onSelectNodes?: (nodes: GraphNode[]) => void;
  onNodeHover: (node: GraphNode | null) => void;
  onClearSelection: () => void;
  onShowNeighbors: (nodeId: string) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitView: () => void;
  onScreenshot: () => void;
}

export const GraphViewport = forwardRef<GraphCanvasHandle, GraphViewportProps>(({
  nodes,
  links,
  selectedNodes,
  highlightedNodes,
  hoveredNode,
  hoveredConnectedNodes,
  selectedNode,
  stats,
  onNodeClick,
  onNodeSelect,
  onSelectNodes,
  onNodeHover,
  onClearSelection,
  onShowNeighbors,
  onZoomIn,
  onZoomOut,
  onFitView,
  onScreenshot,
}, ref) => {
  return (
    <div className="flex-1 relative">
      <GraphErrorBoundary>
        <GraphCanvas 
          ref={ref}
          nodes={nodes}
          links={links}
          onNodeClick={onNodeClick}
          onNodeSelect={onNodeSelect}
          onSelectNodes={onSelectNodes}
          onClearSelection={onClearSelection}
          onNodeHover={onNodeHover}
          selectedNodes={selectedNodes}
          highlightedNodes={[...highlightedNodes, ...hoveredConnectedNodes]}
          stats={stats}
          className="h-full w-full"
        />
      </GraphErrorBoundary>
      
      {/* Node Details Panel Overlay */}
      {selectedNode && (
        <div className="absolute top-4 right-4 w-96 animate-slide-in-right">
          <NodeDetailsPanel 
            node={selectedNode}
            onClose={onClearSelection}
            onShowNeighbors={onShowNeighbors}
          />
        </div>
      )}

      {/* Hover Tooltip */}
      {hoveredNode && hoveredConnectedNodes.length > 0 && (
        <div className="absolute bottom-20 left-1/2 transform -translate-x-1/2 glass-panel px-3 py-1 rounded-full text-xs text-muted-foreground animate-fade-in pointer-events-none">
          {hoveredNode.label} • {hoveredConnectedNodes.length} connected nodes
        </div>
      )}

      {/* Quick Actions Toolbar - Positioned above timeline */}
      <div className="absolute bottom-32 left-1/2 transform -translate-x-1/2 flex flex-col items-center space-y-2 z-50">
        <QuickActions 
          selectedCount={selectedNodes.length}
          onClearSelection={onClearSelection}
          onFitToScreen={onFitView}
          onZoomIn={onZoomIn}
          onZoomOut={onZoomOut}
          onScreenshot={onScreenshot}
        />
      </div>
    </div>
  );
});

GraphViewport.displayName = 'GraphViewport';