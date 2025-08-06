import React, { forwardRef, useMemo, useState, useEffect } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import { GraphCanvas, type GraphCanvasRef as GraphCanvasHandle } from './GraphCanvas';
import { NodeDetailsPanel } from './NodeDetailsPanel';
import { QuickActions } from './QuickActions';
import { GraphOverlays } from './GraphOverlays';
import GraphErrorBoundary from './GraphErrorBoundary';
import { useStableCallback } from '../hooks/useStableCallback';
import type { GraphStats } from '../types/components';


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
  // FPS tracking
  const [fps, setFps] = useState<number>(60);
  
  useEffect(() => {
    let frameCount = 0;
    let lastTime = performance.now();
    let rafId: number;
    
    const measureFPS = () => {
      frameCount++;
      const currentTime = performance.now();
      
      // Update FPS every second
      if (currentTime >= lastTime + 1000) {
        setFps(Math.round((frameCount * 1000) / (currentTime - lastTime)));
        frameCount = 0;
        lastTime = currentTime;
      }
      
      rafId = requestAnimationFrame(measureFPS);
    };
    
    rafId = requestAnimationFrame(measureFPS);
    
    return () => {
      if (rafId) {
        cancelAnimationFrame(rafId);
      }
    };
  }, []);
  
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

  // Calculate connected nodes count for selected node
  const selectedNodeConnections = useMemo(() => {
    if (!selectedNode) return 0;
    
    let connectionCount = 0;
    links.forEach(link => {
      if (link.source === selectedNode.id || link.target === selectedNode.id) {
        connectionCount++;
      }
    });
    
    return connectionCount;
  }, [selectedNode, links]);

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
      
      {/* Graph Overlays - Node count, FPS, Debug info */}
      <GraphOverlays
        nodeCount={nodes.length}
        edgeCount={links.length}
        visibleNodes={nodes.length} // All nodes are visible in current implementation
        selectedNodes={selectedNodes.length}
        fps={fps}
      />
      
      {/* Node Details Panel Overlay */}
      {selectedNode && (
        <div className="absolute top-4 right-4 w-96 animate-slide-in-right">
          <NodeDetailsPanel 
            node={selectedNode}
            connections={selectedNodeConnections}
            onClose={stableOnClearSelection}
            onShowNeighbors={stableOnShowNeighbors}
          />
        </div>
      )}

      {/* Hover Tooltip - Positioned above viewport controls */}
      {hoveredNode && (
        <div className="absolute bottom-48 left-1/2 transform -translate-x-1/2 glass-panel px-4 py-2 rounded-lg text-sm font-medium text-foreground opacity-0 animate-[opacity_200ms_ease-in_forwards] pointer-events-none shadow-lg backdrop-blur-md bg-background/90 border border-border z-[60]">
          <div className="text-center">
            <div className="text-base font-semibold">{hoveredNode.label || hoveredNode.name}</div>
            {hoveredConnectedNodes.length > 0 && (
              <div className="text-xs text-muted-foreground mt-1">
                {hoveredConnectedNodes.length} connected node{hoveredConnectedNodes.length !== 1 ? 's' : ''}
              </div>
            )}
          </div>
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