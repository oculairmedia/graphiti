import React, { forwardRef, useImperativeHandle, useRef, useEffect, useCallback } from 'react';
import { GraphContainer } from './GraphContainer';
import { GraphCanvasRenderer, type GraphViewportHandle } from './GraphCanvasRenderer';
import { useGraphData } from '../../hooks/graph/useGraphData';
import { GraphNode } from '../../api/types';
import { GraphLink } from '../../types/graph';

/**
 * Integration component that bridges the old GraphCanvas API with the new refactored components
 * This allows gradual migration from the monolithic GraphCanvas to the modular architecture
 */

export interface GraphCanvasIntegrationProps {
  // Data
  nodes: GraphNode[];
  links: GraphLink[];
  
  // Visual config (matching old GraphCanvas props)
  width?: number;
  height?: number;
  className?: string;
  
  // Selection state (matching old API)
  selectedNodes?: GraphNode[];
  highlightedNodes?: GraphNode[];
  hoveredNode?: GraphNode | null;
  
  // Callbacks (matching old API)
  onNodeClick?: (node: GraphNode) => void;
  onNodeSelect?: (nodeId: string) => void;
  onSelectNodes?: (nodes: GraphNode[]) => void;
  onNodeHover?: (node: GraphNode | null) => void;
  onClearSelection?: () => void;
  onShowNeighbors?: (nodeId: string) => void;
  
  // Stats callback
  onStatsUpdate?: (stats: { nodeCount: number; edgeCount: number; lastUpdated: number }) => void;
  
  // Feature flags for migration
  useRefactoredComponents?: boolean;
  enablePerformanceMonitoring?: boolean;
  enableDeltaProcessing?: boolean;
}

export interface GraphCanvasIntegrationHandle {
  // Match the old GraphCanvas ref API
  getCanvas: () => HTMLCanvasElement | null;
  getNodes: () => GraphNode[];
  getLinks: () => GraphLink[];
  
  // Viewport controls
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: (duration?: number, padding?: number) => void;
  fitViewByPointIndices: (indices: number[], duration?: number, padding?: number) => void;
  zoomToPoint: (index: number, duration?: number, scale?: number, canZoomOut?: boolean) => void;
  resetViewport: () => void;
  panTo: (x: number, y: number) => void;
  
  // Simulation controls
  pauseSimulation: () => void;
  resumeSimulation: () => void;
  startSimulation: (alpha?: number) => void;
  keepSimulationRunning: (enable: boolean) => void;
  
  // Export
  exportImage: (format?: string) => Promise<Blob>;
  
  // Selection
  selectNode: (node: GraphNode) => void;
  selectNodes: (nodes: GraphNode[]) => void;
  clearSelection: () => void;
  activateRectSelection: () => void;
  deactivateRectSelection: () => void;
  activatePolygonalSelection: () => void;
  deactivatePolygonalSelection: () => void;
  selectPointsInRect: (selection: [[number, number], [number, number]] | null, addToSelection?: boolean) => void;
  selectPointsInPolygon: (polygonPoints: [number, number][], addToSelection?: boolean) => void;
  
  // Data management
  setData: (nodes: GraphNode[], links: GraphLink[], runSimulation?: boolean) => void;
  addIncrementalData: (newNodes: GraphNode[], newLinks: GraphLink[], runSimulation?: boolean) => void;
  updateNodes: (updatedNodes: GraphNode[]) => void;
  updateLinks: (updatedLinks: GraphLink[]) => void;
  removeNodes: (nodeIds: string[]) => void;
  removeLinks: (linkIds: string[]) => void;
  setIncrementalUpdateFlag: (enabled: boolean) => void;
  
  // Data queries
  trackPointPositionsByIndices: (indices: number[]) => void;
  getTrackedPointPositionsMap: () => Map<number, [number, number]> | undefined;
  getConnectedPointIndices: (index: number) => number[] | undefined;
  getPointIndicesByExactValues: (keyValues: Record<string, unknown>) => number[] | undefined;
  
  // Other
  restart: () => void;
}

/**
 * Integration wrapper that provides backward compatibility
 * while using the new refactored components internally
 */
export const GraphCanvasIntegration = forwardRef<GraphCanvasIntegrationHandle, GraphCanvasIntegrationProps>((
  props,
  ref
) => {
  const {
    nodes,
    links,
    width = 800,
    height = 600,
    className = '',
    selectedNodes = [],
    highlightedNodes = [],
    hoveredNode = null,
    onNodeClick,
    onNodeSelect,
    onSelectNodes,
    onNodeHover,
    onClearSelection,
    onShowNeighbors,
    onStatsUpdate,
    useRefactoredComponents = true,
    enablePerformanceMonitoring = false,
    enableDeltaProcessing = true
  } = props;

  // Refs
  const containerRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<GraphViewportHandle>(null);
  const isSimulationRunningRef = useRef(true);

  // Convert old selectedNodes array to Set for new components
  const selectedNodeIds = new Set(selectedNodes.map(n => n.id));
  const highlightedNodeIds = new Set(highlightedNodes.map(n => n.id));

  // Stats reporting
  useEffect(() => {
    if (onStatsUpdate) {
      const stats = {
        nodeCount: nodes.length,
        edgeCount: links.length,
        lastUpdated: Date.now()
      };
      onStatsUpdate(stats);
    }
  }, [nodes.length, links.length, onStatsUpdate]);

  // Handle node click with backward compatibility
  const handleNodeClick = useCallback((node: GraphNode) => {
    console.log('[GraphCanvasIntegration] Node clicked:', node.id);
    
    // Call old API callbacks
    onNodeClick?.(node);
    onNodeSelect?.(node.id);
    
    // Update selection
    if (onSelectNodes) {
      const isSelected = selectedNodeIds.has(node.id);
      if (isSelected) {
        const newSelection = selectedNodes.filter(n => n.id !== node.id);
        onSelectNodes(newSelection);
      } else {
        onSelectNodes([...selectedNodes, node]);
      }
    }
  }, [onNodeClick, onNodeSelect, onSelectNodes, selectedNodes, selectedNodeIds]);

  // Handle selection change
  const handleSelectionChange = useCallback((nodes: GraphNode[]) => {
    console.log('[GraphCanvasIntegration] Selection changed:', nodes.length, 'nodes');
    onSelectNodes?.(nodes);
  }, [onSelectNodes]);

  // Handle double click for neighbors
  const handleNodeDoubleClick = useCallback((node: GraphNode) => {
    console.log('[GraphCanvasIntegration] Node double-clicked:', node.id);
    onShowNeighbors?.(node.id);
  }, [onShowNeighbors]);

  // Imperative handle to match old GraphCanvas API
  useImperativeHandle(ref, () => ({
    // Data access
    getCanvas: () => viewportRef.current?.getCanvas() || null,
    getNodes: () => nodes,
    getLinks: () => links,
    
    // Viewport controls
    zoomIn: () => {
      viewportRef.current?.zoomTo(2);
    },
    zoomOut: () => {
      viewportRef.current?.zoomTo(0.5);
    },
    fitView: () => {
      viewportRef.current?.fitToNodes();
    },
    resetViewport: () => {
      viewportRef.current?.resetViewport();
    },
    panTo: (x: number, y: number) => {
      viewportRef.current?.panTo(x, y);
    },
    
    // Simulation controls
    pauseSimulation: () => {
      isSimulationRunningRef.current = false;
      viewportRef.current?.pauseRendering();
    },
    resumeSimulation: () => {
      isSimulationRunningRef.current = true;
      viewportRef.current?.resumeRendering();
    },
    
    // Export
    exportImage: async (format = 'png') => {
      return viewportRef.current?.exportImage(format as 'png' | 'jpeg') || 
             new Blob();
    },
    
    // Selection
    selectNodes: (nodeIds: string[]) => {
      const nodesToSelect = nodes.filter(n => nodeIds.includes(n.id));
      onSelectNodes?.(nodesToSelect);
    },
    clearSelection: () => {
      onClearSelection?.();
      onSelectNodes?.([]);
    }
  }), [nodes, links, onSelectNodes, onClearSelection]);

  // Render using new refactored components
  if (useRefactoredComponents) {
    return (
      <div ref={containerRef} className={className}>
        <GraphContainer
          initialNodes={nodes}
          initialLinks={links}
          width={width}
          height={height}
          theme="dark"
          enableRealTimeUpdates={false} // Controlled by parent
          enableDeltaProcessing={enableDeltaProcessing}
          onNodeClick={handleNodeClick}
          onNodeDoubleClick={handleNodeDoubleClick}
          onSelectionChange={handleSelectionChange}
        />
      </div>
    );
  }

  // Fallback to direct canvas renderer for testing
  return (
    <div ref={containerRef} className={className}>
      <GraphCanvasRenderer
        ref={viewportRef}
        nodes={nodes}
        links={links}
        width={width}
        height={height}
        selectedNodes={selectedNodeIds}
        highlightedNodes={highlightedNodeIds}
        hoveredNode={hoveredNode}
        onNodeClick={handleNodeClick}
        onNodeDoubleClick={handleNodeDoubleClick}
        onNodeHover={onNodeHover}
        onBackgroundClick={onClearSelection}
        enablePanning={true}
        enableZooming={true}
        showLabels={true}
      />
    </div>
  );
});

GraphCanvasIntegration.displayName = 'GraphCanvasIntegration';