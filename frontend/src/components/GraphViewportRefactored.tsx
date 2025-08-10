import React, { forwardRef, useRef, useImperativeHandle, useCallback, useEffect, useState } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import { GraphContainer } from './graph/GraphContainer';
import { GraphCanvasRenderer, type GraphViewportHandle } from './graph/GraphCanvasRenderer';
import { useGraphData } from '../hooks/graph/useGraphData';
import { NodeDetailsPanel } from './NodeDetailsPanel';
import { GraphOverlays } from './GraphOverlays';
import GraphErrorBoundary from './GraphErrorBoundary';

interface GraphViewportRefactoredProps {
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

// Create a handle interface that matches the old GraphCanvasHandle
export interface GraphCanvasRefactoredHandle {
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

const GraphViewportRefactored = forwardRef<GraphCanvasRefactoredHandle, GraphViewportRefactoredProps>(({
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
  const [isIncrementalUpdate, setIsIncrementalUpdate] = useState(false);
  
  // Refs
  const viewportRef = useRef<GraphViewportHandle>(null);
  const nodeIndexMapRef = useRef<Map<string, number>>(new Map());
  const trackedPositionsRef = useRef<Map<number, [number, number]>>(new Map());
  const isSimulationRunningRef = useRef(true);
  
  // Convert selected/highlighted arrays to Sets
  const selectedNodeSet = new Set(selectedNodes);
  const highlightedNodeSet = new Set(highlightedNodes);
  
  // Update node index map
  useEffect(() => {
    const indexMap = new Map<string, number>();
    nodes.forEach((node, index) => {
      indexMap.set(node.id, index);
    });
    nodeIndexMapRef.current = indexMap;
  }, [nodes]);
  
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
  
  // Handle node click with all the selection logic
  const handleNodeClick = useCallback((node: GraphNode) => {
    onNodeClick(node);
    onNodeSelect(node.id);
    setShowNodeDetails(true);
  }, [onNodeClick, onNodeSelect]);
  
  // Handle node double click for neighbors
  const handleNodeDoubleClick = useCallback((node: GraphNode) => {
    onShowNeighbors(node.id);
  }, [onShowNeighbors]);
  
  // Imperative handle for external control
  useImperativeHandle(ref, () => ({
    // Selection methods
    clearSelection: () => {
      onClearSelection();
      setShowNodeDetails(false);
    },
    selectNode: (node: GraphNode) => {
      onNodeSelect(node.id);
      // Don't call onSelectNodes here to avoid recursion
    },
    selectNodes: (nodesToSelect: GraphNode[]) => {
      // Don't call onSelectNodes here to avoid recursion
      // This is called by the parent component
      console.log('[GraphViewportRefactored] selectNodes called with', nodesToSelect.length, 'nodes');
    },
    
    // Viewport controls
    zoomIn: () => {
      viewportRef.current?.zoomTo(2);
      onZoomIn();
    },
    zoomOut: () => {
      viewportRef.current?.zoomTo(0.5);
      onZoomOut();
    },
    fitView: (duration = 300, padding = 50) => {
      viewportRef.current?.fitToNodes(undefined, padding);
      onFitView();
    },
    fitViewByPointIndices: (indices: number[], duration = 300, padding = 50) => {
      const nodeIds = indices
        .map(i => nodes[i]?.id)
        .filter(Boolean) as string[];
      viewportRef.current?.fitToNodes(nodeIds, padding);
    },
    zoomToPoint: (index: number, duration = 300, scale = 2) => {
      const node = nodes[index];
      if (node) {
        // This would need position data from layout
        // For now, just fit to that node
        viewportRef.current?.fitToNodes([node.id], 100);
      }
    },
    
    // Position tracking
    trackPointPositionsByIndices: (indices: number[]) => {
      // Store indices for tracking
      indices.forEach(i => {
        trackedPositionsRef.current.set(i, [0, 0]);
      });
    },
    getTrackedPointPositionsMap: () => trackedPositionsRef.current,
    
    // Data management
    setData: (newNodes: GraphNode[], newLinks: GraphLink[], runSimulation = true) => {
      // This would update the parent component's state
      // For now, we'll handle this through props
      console.log('[GraphViewportRefactored] setData called with', newNodes.length, 'nodes');
    },
    restart: () => {
      viewportRef.current?.resetViewport();
    },
    
    // Selection tools
    activateRectSelection: () => {
      console.log('[GraphViewportRefactored] Rectangle selection activated');
    },
    deactivateRectSelection: () => {
      console.log('[GraphViewportRefactored] Rectangle selection deactivated');
    },
    activatePolygonalSelection: () => {
      console.log('[GraphViewportRefactored] Polygonal selection activated');
    },
    deactivatePolygonalSelection: () => {
      console.log('[GraphViewportRefactored] Polygonal selection deactivated');
    },
    selectPointsInRect: (selection, addToSelection = false) => {
      console.log('[GraphViewportRefactored] Select points in rect');
    },
    selectPointsInPolygon: (polygonPoints, addToSelection = false) => {
      console.log('[GraphViewportRefactored] Select points in polygon');
    },
    
    // Data queries
    getConnectedPointIndices: (index: number) => {
      const node = nodes[index];
      if (!node) return undefined;
      
      const connected = new Set<number>();
      links.forEach(link => {
        if (link.source === node.id) {
          const targetIndex = nodeIndexMapRef.current.get(link.target);
          if (targetIndex !== undefined) connected.add(targetIndex);
        } else if (link.target === node.id) {
          const sourceIndex = nodeIndexMapRef.current.get(link.source);
          if (sourceIndex !== undefined) connected.add(sourceIndex);
        }
      });
      
      return Array.from(connected);
    },
    getPointIndicesByExactValues: (keyValues: Record<string, unknown>) => {
      const indices: number[] = [];
      nodes.forEach((node, index) => {
        const matches = Object.entries(keyValues).every(([key, value]) => {
          return (node as any)[key] === value;
        });
        if (matches) indices.push(index);
      });
      return indices;
    },
    
    // Incremental updates - these are called by useIncrementalUpdates hook
    addIncrementalData: async (newNodes: GraphNode[], newLinks: GraphLink[], runSimulation = true) => {
      console.log('[GraphViewportRefactored] Adding incremental data:', newNodes.length, 'nodes');
      setIsIncrementalUpdate(true);
      // The parent component will update the nodes/links props
      // which will trigger a re-render with the new data
      return Promise.resolve();
    },
    updateNodes: async (updatedNodes: GraphNode[]) => {
      console.log('[GraphViewportRefactored] Updating nodes:', updatedNodes.length);
      // The parent component handles the actual update
      return Promise.resolve();
    },
    updateLinks: async (updatedLinks: GraphLink[]) => {
      console.log('[GraphViewportRefactored] Updating links:', updatedLinks.length);
      // The parent component handles the actual update
      return Promise.resolve();
    },
    removeNodes: async (nodeIds: string[]) => {
      console.log('[GraphViewportRefactored] Removing nodes:', nodeIds.length);
      // The parent component handles the actual removal
      return Promise.resolve();
    },
    removeLinks: async (linkIds: string[]) => {
      console.log('[GraphViewportRefactored] Removing links:', linkIds.length);
      // The parent component handles the actual removal
      return Promise.resolve();
    },
    
    // Simulation controls
    startSimulation: (alpha = 1) => {
      isSimulationRunningRef.current = true;
      viewportRef.current?.resumeRendering();
    },
    pauseSimulation: () => {
      isSimulationRunningRef.current = false;
      viewportRef.current?.pauseRendering();
    },
    resumeSimulation: () => {
      isSimulationRunningRef.current = true;
      viewportRef.current?.resumeRendering();
    },
    keepSimulationRunning: (enable: boolean) => {
      isSimulationRunningRef.current = enable;
    },
    setIncrementalUpdateFlag: (enabled: boolean) => {
      setIsIncrementalUpdate(enabled);
    },
  }), [nodes, links, onNodeSelect, onSelectNodes, onClearSelection, onZoomIn, onZoomOut, onFitView]);
  
  return (
    <GraphErrorBoundary>
      <div className="relative flex-1 bg-background">
        {/* Main Graph Container */}
        <GraphContainer
          initialNodes={nodes}
          initialLinks={links}
          width={window.innerWidth - 640} // Account for side panels
          height={window.innerHeight - 120} // Account for nav and timeline
          theme="dark"
          enableRealTimeUpdates={false}
          enableDeltaProcessing={isIncrementalUpdate}
          onNodeClick={handleNodeClick}
          onNodeDoubleClick={handleNodeDoubleClick}
          onSelectionChange={(selected) => {
            onSelectNodes?.(selected);
          }}
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
          <NodeDetailsPanel
            node={selectedNode}
            onClose={() => setShowNodeDetails(false)}
            onShowNeighbors={onShowNeighbors}
          />
        )}
      </div>
    </GraphErrorBoundary>
  );
});

GraphViewportRefactored.displayName = 'GraphViewportRefactored';

export { GraphViewportRefactored };
export default GraphViewportRefactored;