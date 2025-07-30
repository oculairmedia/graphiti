import React, { forwardRef } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import { GraphCanvas } from './GraphCanvas';
import { NodeDetailsPanel } from './NodeDetailsPanel';
import { QuickActions } from './QuickActions';
import GraphErrorBoundary from './GraphErrorBoundary';
import { useStableCallback } from '../hooks/useStableCallback';
import type { GraphCanvasHandle, GraphStats } from '../types/components';


interface GraphViewportProps {
  nodes: GraphNode[];
  links: GraphLink[];
  selectedNodes: string[];
  highlightedNodes: string[];
  hoveredNode: GraphNode | null;
  hoveredConnectedNodes: string[];
  selectedNode: GraphNode | null;
  stats?: {
    nodeCount: number;
    edgeCount: number;
    nodeTypes: Record<string, number>;
    centralityStats?: {
      min: number;
      max: number;
      avg: number;
    };
  };
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

const GraphViewportComponent = forwardRef<GraphCanvasHandle, GraphViewportProps>(({
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
  // Use stable callbacks to prevent child re-renders
  const stableOnNodeClick = useStableCallback(onNodeClick);
  const stableOnNodeSelect = useStableCallback(onNodeSelect);
  const stableOnSelectNodes = useStableCallback(onSelectNodes || (() => {}));
  const stableOnNodeHover = useStableCallback(onNodeHover || (() => {}));
  const stableOnClearSelection = useStableCallback(onClearSelection);
  const stableOnShowNeighbors = useStableCallback(onShowNeighbors);
  const stableOnZoomIn = useStableCallback(onZoomIn);
  const stableOnZoomOut = useStableCallback(onZoomOut);
  const stableOnFitView = useStableCallback(onFitView);
  const stableOnScreenshot = useStableCallback(onScreenshot);
  return (
    <div className="flex-1 relative">
      <GraphErrorBoundary>
        <GraphCanvas 
          ref={ref}
          nodes={nodes}
          links={links}
          onNodeClick={stableOnNodeClick}
          onNodeSelect={stableOnNodeSelect}
          onSelectNodes={stableOnSelectNodes}
          onClearSelection={stableOnClearSelection}
          onNodeHover={stableOnNodeHover}
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
            onClose={stableOnClearSelection}
            onShowNeighbors={stableOnShowNeighbors}
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
          onClearSelection={stableOnClearSelection}
          onFitToScreen={stableOnFitView}
          onZoomIn={stableOnZoomIn}
          onZoomOut={stableOnZoomOut}
          onScreenshot={stableOnScreenshot}
        />
      </div>
    </div>
  );
});

GraphViewportComponent.displayName = 'GraphViewportComponent';

// Export memoized component to prevent unnecessary re-renders
export const GraphViewport = React.memo(GraphViewportComponent, (prevProps, nextProps) => {
  // Deep compare arrays by checking if they're the same reference or have same contents
  const arraysEqual = (a: string[], b: string[]) => {
    if (a === b) return true;
    if (a.length !== b.length) return false;
    return a.every((val, idx) => val === b[idx]);
  };
  
  // Check if any props changed
  return prevProps.nodes === nextProps.nodes &&
         prevProps.links === nextProps.links &&
         arraysEqual(prevProps.selectedNodes, nextProps.selectedNodes) &&
         arraysEqual(prevProps.highlightedNodes, nextProps.highlightedNodes) &&
         prevProps.hoveredNode === nextProps.hoveredNode &&
         arraysEqual(prevProps.hoveredConnectedNodes, nextProps.hoveredConnectedNodes) &&
         prevProps.selectedNode === nextProps.selectedNode &&
         prevProps.stats === nextProps.stats;
});