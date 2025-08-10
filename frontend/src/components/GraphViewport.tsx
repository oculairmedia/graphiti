import React, { forwardRef, useMemo, useState, useEffect } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import { LazyGraphCanvas } from './LazyGraphCanvas';
import type { GraphCanvasRef as GraphCanvasHandle } from './GraphCanvas';
import { NodeDetailsPanel } from './NodeDetailsPanel';
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
  onToggleTimeline?: () => void;
  isTimelineVisible?: boolean;
  onStatsUpdate?: (stats: { nodeCount: number; edgeCount: number; lastUpdated: number }) => void;
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
  onToggleTimeline,
  isTimelineVisible,
  onStatsUpdate,
}, ref) => {
  // FPS tracking
  const [fps, setFps] = useState<number>(60);
  
  // Live stats from GraphCanvas
  const [liveStats, setLiveStats] = useState<{ nodeCount: number; edgeCount: number } | null>(null);
  
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
  
  // Handle stats updates from GraphCanvas
  const handleStatsUpdate = useStableCallback((stats: { nodeCount: number; edgeCount: number; lastUpdated: number }) => {
    setLiveStats(stats);
    if (onStatsUpdate) {
      onStatsUpdate(stats);
    }
  });
  
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
        <LazyGraphCanvas 
          ref={ref}
          nodes={nodes}
          links={links}
          onNodeClick={stableOnNodeClick}
          onNodeSelect={stableOnNodeSelect}
          onSelectNodes={stableOnSelectNodes}
          onClearSelection={stableOnClearSelection}
          onNodeHover={stableOnNodeHover}
          onStatsUpdate={handleStatsUpdate}
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
        liveNodeCount={liveStats?.nodeCount}
        liveEdgeCount={liveStats?.edgeCount}
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

      {/* Hover Tooltip removed - was showing incorrect information */}

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