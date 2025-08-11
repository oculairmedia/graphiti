import React, { forwardRef, useRef, useImperativeHandle, useCallback, useEffect, useState, useMemo } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import { LazyGraphCanvas } from './LazyGraphCanvas';
import type { GraphCanvasRef as GraphCanvasHandle } from './GraphCanvas';
import { NodeDetailsPanel } from './NodeDetailsPanel';
import { GraphOverlays } from './GraphOverlays';
import GraphErrorBoundary from './GraphErrorBoundary';

// Import feature components
import { KeyboardShortcuts } from './graph-refactored/features/KeyboardShortcuts';
import { SearchManager } from './graph-refactored/features/SearchManager';
import { VisualizationStrategies } from './graph-refactored/features/VisualizationStrategies';
import { SelectionTools } from './graph-refactored/features/SelectionTools';

interface GraphViewportEnhancedFixedProps {
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
 * CRITICAL: Isolate Cosmograph component to prevent re-initialization
 * This component should NEVER re-render unless absolutely necessary
 */
const IsolatedCosmographCanvas = React.memo(forwardRef<GraphCanvasHandle, any>((props, ref) => {
  return <LazyGraphCanvas ref={ref} {...props} />;
}), (prevProps, nextProps) => {
  // Only re-render if nodes/links data actually changes (by reference)
  // This prevents wrapper re-renders from affecting Cosmograph
  return (
    prevProps.nodes === nextProps.nodes &&
    prevProps.links === nextProps.links &&
    // Allow these UI props to update without re-rendering Cosmograph
    prevProps.selectedNodes === nextProps.selectedNodes &&
    prevProps.highlightedNodes === nextProps.highlightedNodes &&
    prevProps.hoveredNode === nextProps.hoveredNode &&
    prevProps.hoveredConnectedNodes === nextProps.hoveredConnectedNodes &&
    prevProps.selectedNode === nextProps.selectedNode
  );
});

IsolatedCosmographCanvas.displayName = 'IsolatedCosmographCanvas';

/**
 * Fixed Enhanced Viewport that properly isolates Cosmograph from wrapper re-renders
 */
const GraphViewportEnhancedFixed = forwardRef<GraphCanvasHandle, GraphViewportEnhancedFixedProps>((props, ref) => {
  const {
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
  } = props;

  // State
  const [fps, setFps] = useState<number>(60);
  const [showNodeDetails, setShowNodeDetails] = useState(false);
  
  // Internal ref for the actual GraphCanvas
  const graphCanvasRef = useRef<GraphCanvasHandle>(null);
  
  // Expose all methods via ref - including the missing ones
  useImperativeHandle(ref, () => ({
    // Core viewport controls
    zoomIn: () => graphCanvasRef.current?.zoomIn(),
    zoomOut: () => graphCanvasRef.current?.zoomOut(),
    fitView: () => graphCanvasRef.current?.fitView(),
    pauseSimulation: () => graphCanvasRef.current?.pauseSimulation(),
    resumeSimulation: () => graphCanvasRef.current?.resumeSimulation(),
    screenshot: () => graphCanvasRef.current?.screenshot(),
    recenter: () => graphCanvasRef.current?.recenter(),
    getNodeScreenPosition: (nodeId: string) => graphCanvasRef.current?.getNodeScreenPosition(nodeId),
    
    // Selection methods
    clearSelection: () => graphCanvasRef.current?.clearSelection(),
    selectNode: (node: GraphNode) => graphCanvasRef.current?.selectNode(node),
    selectNodes: (nodes: GraphNode[]) => graphCanvasRef.current?.selectNodes(nodes),
    focusOnNodes: (nodeIds: string[], duration?: number, padding?: number) => 
      graphCanvasRef.current?.focusOnNodes(nodeIds, duration, padding),
    
    // Data methods - CRITICAL for useNodeSelection hook
    getConnectedPointIndices: (index: number) => graphCanvasRef.current?.getConnectedPointIndices(index),
    getPointIndicesByExactValues: (keyValues: Record<string, unknown>) => 
      graphCanvasRef.current?.getPointIndicesByExactValues(keyValues),
    
    // Additional viewport methods
    fitViewByPointIndices: (indices: number[], duration?: number, padding?: number) => 
      graphCanvasRef.current?.fitViewByPointIndices(indices, duration, padding),
    zoomToPoint: (index: number, duration?: number, scale?: number, canZoomOut?: boolean) => 
      graphCanvasRef.current?.zoomToPoint(index, duration, scale, canZoomOut),
    trackPointPositionsByIndices: (indices: number[]) => 
      graphCanvasRef.current?.trackPointPositionsByIndices(indices),
    getTrackedPointPositionsMap: () => graphCanvasRef.current?.getTrackedPointPositionsMap(),
    
    // Data management
    setData: (nodes: GraphNode[], links: any[], runSimulation?: boolean) => 
      graphCanvasRef.current?.setData(nodes, links, runSimulation),
    restart: () => graphCanvasRef.current?.restart(),
    getLiveStats: () => graphCanvasRef.current?.getLiveStats(),
    
    // Selection tools
    activateRectSelection: () => graphCanvasRef.current?.activateRectSelection(),
    deactivateRectSelection: () => graphCanvasRef.current?.deactivateRectSelection(),
    activatePolygonalSelection: () => graphCanvasRef.current?.activatePolygonalSelection(),
    deactivatePolygonalSelection: () => graphCanvasRef.current?.deactivatePolygonalSelection(),
    selectPointsInRect: (selection: [[number, number], [number, number]] | null, addToSelection?: boolean) => 
      graphCanvasRef.current?.selectPointsInRect(selection, addToSelection),
    selectPointsInPolygon: (polygonPoints: [number, number][], addToSelection?: boolean) => 
      graphCanvasRef.current?.selectPointsInPolygon(polygonPoints, addToSelection),
  }), []);

  // Handle node details
  useEffect(() => {
    setShowNodeDetails(!!selectedNode);
  }, [selectedNode]);

  // Memoize keyboard shortcuts to prevent re-renders
  const keyboardShortcuts = useMemo(() => [
    {
      id: 'zoom-in-enhanced',
      key: '=',
      modifiers: ['ctrl'],
      description: 'Zoom in',
      category: 'Navigation',
      action: onZoomIn,
      enabled: true,
      preventDefault: true
    },
    {
      id: 'zoom-out-enhanced',
      key: '-',
      modifiers: ['ctrl'],
      description: 'Zoom out',
      category: 'Navigation',
      action: onZoomOut,
      enabled: true,
      preventDefault: true
    },
    {
      id: 'fit-view-enhanced',
      key: 'f',
      description: 'Fit view',
      category: 'Navigation',
      action: onFitView,
      enabled: true
    },
    {
      id: 'clear-selection-enhanced',
      key: 'Escape',
      description: 'Clear selection',
      category: 'Selection',
      action: onClearSelection,
      enabled: true
    }
  ], [onZoomIn, onZoomOut, onFitView, onClearSelection]);

  // Memoize callbacks to prevent re-renders
  const handleSearchResults = useCallback((results: any[]) => {
    if (results.length > 0 && onSelectNodes) {
      onSelectNodes(results.map(r => r.node));
    }
  }, [onSelectNodes]);

  const handleSelectionChange = useCallback((selectedNodes: GraphNode[]) => {
    if (onSelectNodes) {
      onSelectNodes(selectedNodes);
    }
  }, [onSelectNodes]);

  // Memoize visualization config
  const vizConfig = useMemo(() => ({
    color: { scheme: 'type' as const },
    size: { strategy: 'degree' as const },
    shape: { strategy: 'circle' as const }
  }), []);

  // Memoize selection config
  const selectionConfig = useMemo(() => ({
    multiSelect: true,
    boxSelect: true,
    lassoSelect: false
  }), []);

  return (
    <GraphErrorBoundary>
      <div className="relative h-full w-full overflow-hidden bg-gray-950">
        {/* Wrappers are outside of the isolated Cosmograph to prevent affecting it */}
        <KeyboardShortcuts
          shortcuts={keyboardShortcuts}
          onShortcutTriggered={useCallback((shortcut) => console.log('[Shortcut]', shortcut.id), [])}
        >
          <SearchManager
            nodes={nodes}
            onSearchResults={handleSearchResults}
          >
            <VisualizationStrategies
              nodes={nodes}
              edges={links}
              config={vizConfig}
            >
              <SelectionTools
                nodes={nodes}
                edges={links}
                config={selectionConfig}
                onSelectionChange={handleSelectionChange}
              >
                {/* CRITICAL: IsolatedCosmographCanvas prevents re-initialization */}
                <IsolatedCosmographCanvas
                  ref={graphCanvasRef}
                  nodes={nodes}
                  links={links}
                  selectedNodes={selectedNodes}
                  highlightedNodes={highlightedNodes}
                  hoveredNode={hoveredNode}
                  hoveredConnectedNodes={hoveredConnectedNodes}
                  selectedNode={selectedNode}
                  stats={stats}
                  onNodeClick={onNodeClick}
                  onNodeSelect={onNodeSelect}
                  onSelectNodes={onSelectNodes}
                  onNodeHover={onNodeHover}
                  onClearSelection={onClearSelection}
                  onStatsUpdate={onStatsUpdate}
                />
              </SelectionTools>
            </VisualizationStrategies>
          </SearchManager>
        </KeyboardShortcuts>
        
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
          onClearSelection={onClearSelection}
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

GraphViewportEnhancedFixed.displayName = 'GraphViewportEnhancedFixed';

export { GraphViewportEnhancedFixed };