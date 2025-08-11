import React, { forwardRef, useRef, useImperativeHandle, useCallback, useEffect, useState } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import { LazyGraphCanvas } from './LazyGraphCanvas';
import type { GraphCanvasRef as GraphCanvasHandle } from './GraphCanvas';
import { NodeDetailsPanel } from './NodeDetailsPanel';
import { GraphOverlays } from './GraphOverlays';
import GraphErrorBoundary from './GraphErrorBoundary';

interface GraphViewportSimplifiedProps {
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

/**
 * Simplified version that reuses the existing GraphCanvas with Cosmograph
 * but with a cleaner interface
 */
const GraphViewportSimplified = forwardRef<GraphCanvasHandle, GraphViewportSimplifiedProps>(({
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
  // State
  const [fps, setFps] = useState<number>(60);
  const [showNodeDetails, setShowNodeDetails] = useState(false);
  
  // Internal ref for the actual GraphCanvas
  const graphCanvasRef = useRef<GraphCanvasHandle>(null);
  
  // FPS tracking
  useEffect(() => {
    let frameCount = 0;
    let lastTime = performance.now();
    let rafId: number;
    
    const measureFPS = () => {
      frameCount++;
      const currentTime = performance.now();
      
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
  
  // Stats update
  useEffect(() => {
    if (onStatsUpdate) {
      onStatsUpdate({
        nodeCount: nodes.length,
        edgeCount: links.length,
        lastUpdated: Date.now()
      });
    }
  }, [nodes.length, links.length, onStatsUpdate]);
  
  // Handle node click
  const handleNodeClick = useCallback((node: GraphNode) => {
    console.log('[GraphViewportSimplified] Node clicked:', node.id);
    onNodeClick(node);
    setShowNodeDetails(true);
  }, [onNodeClick]);
  
  // Forward ref methods to the internal GraphCanvas
  useImperativeHandle(ref, () => {
    const canvas = graphCanvasRef.current;
    if (!canvas) {
      // Return a stub implementation if canvas isn't ready
      return {
        clearSelection: () => {},
        selectNode: () => {},
        selectNodes: () => {},
        zoomIn: () => {},
        zoomOut: () => {},
        fitView: () => {},
        fitViewByPointIndices: () => {},
        zoomToPoint: () => {},
        trackPointPositionsByIndices: () => {},
        getTrackedPointPositionsMap: () => undefined,
        setData: () => {},
        restart: () => {},
        activateRectSelection: () => {},
        deactivateRectSelection: () => {},
        activatePolygonalSelection: () => {},
        deactivatePolygonalSelection: () => {},
        selectPointsInRect: () => {},
        selectPointsInPolygon: () => {},
        getConnectedPointIndices: () => undefined,
        getPointIndicesByExactValues: () => undefined,
        addIncrementalData: () => {},
        updateNodes: () => {},
        updateLinks: () => {},
        removeNodes: () => {},
        removeLinks: () => {},
        startSimulation: () => {},
        pauseSimulation: () => {},
        resumeSimulation: () => {},
        keepSimulationRunning: () => {},
        setIncrementalUpdateFlag: () => {},
      } as GraphCanvasHandle;
    }
    return canvas;
  }, []);
  
  return (
    <GraphErrorBoundary>
      <div className="relative flex-1 bg-background overflow-hidden">
        {/* Use the existing GraphCanvas component which has Cosmograph */}
        <LazyGraphCanvas
          ref={graphCanvasRef}
          nodes={nodes}
          links={links}
          selectedNodes={selectedNodes}
          highlightedNodes={highlightedNodes}
          hoveredNode={hoveredNode}
          hoveredConnectedNodes={hoveredConnectedNodes}
          selectedNode={selectedNode}
          stats={stats}
          onNodeClick={handleNodeClick}
          onNodeSelect={onNodeSelect}
          onSelectNodes={onSelectNodes}
          onNodeHover={onNodeHover}
          onClearSelection={onClearSelection}
          onShowNeighbors={onShowNeighbors}
          onStatsUpdate={onStatsUpdate}
        />
        
        {/* Overlays */}
        <GraphOverlays
          fps={fps}
          nodeCount={nodes.length}
          edgeCount={links.length}
          selectedCount={selectedNodes.length}
          onZoomIn={onZoomIn}
          onZoomOut={onZoomOut}
          onFitView={onFitView}
          onScreenshot={onScreenshot}
          onToggleTimeline={onToggleTimeline}
          isTimelineVisible={isTimelineVisible}
        />
        
        {/* Node Details Panel */}
        {showNodeDetails && selectedNode && (
          <div className="absolute top-4 right-4 w-96 animate-slide-in-right z-20">
            <NodeDetailsPanel
              node={selectedNode}
              onClose={() => setShowNodeDetails(false)}
              onShowNeighbors={onShowNeighbors}
            />
          </div>
        )}
      </div>
    </GraphErrorBoundary>
  );
});

GraphViewportSimplified.displayName = 'GraphViewportSimplified';

export { GraphViewportSimplified };
export default GraphViewportSimplified;