import React, { forwardRef, useRef, useImperativeHandle, useCallback, useEffect, useState, useMemo } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import { LazyGraphCanvas } from './LazyGraphCanvas';
import type { GraphCanvasRef as GraphCanvasHandle } from './GraphCanvas';
import { NodeDetailsPanel } from './NodeDetailsPanel';
import { GraphOverlays } from './GraphOverlays';
import GraphErrorBoundary from './GraphErrorBoundary';
import { CosmographGuard, useStableCallback } from './StableCosmographWrapper';

// Import all our new feature components
import { ClusteringManager } from './graph-refactored/features/ClusteringManager';
import { ProgressiveLoader } from './graph-refactored/features/ProgressiveLoader';
import { SearchManager } from './graph-refactored/features/SearchManager';
import { RustWebSocketManager } from './graph-refactored/features/RustWebSocketManager';
import { DataKitCoordinator } from './graph-refactored/features/DataKitCoordinator';
import { TemporalManager } from './graph-refactored/features/TemporalManager';
import { VisualizationStrategies } from './graph-refactored/features/VisualizationStrategies';
import { SelectionTools } from './graph-refactored/features/SelectionTools';
import { KeyboardShortcuts } from './graph-refactored/features/KeyboardShortcuts';
import { PerformanceMonitor } from './graph-refactored/features/PerformanceMonitor';
import { GraphLayoutAlgorithms } from './graph-refactored/features/GraphLayoutAlgorithms';

interface GraphViewportEnhancedProps {
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
 * Enhanced version that integrates all the new modular features
 */
const GraphViewportEnhanced = forwardRef<GraphCanvasHandle, GraphViewportEnhancedProps>(({
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
  const [processedNodes, setProcessedNodes] = useState<GraphNode[]>(nodes);
  const [processedLinks, setProcessedLinks] = useState<GraphLink[]>(links);
  const [activeFeatures, setActiveFeatures] = useState(() => {
    // Load feature preferences from localStorage
    const saved = localStorage.getItem('graphiti.features');
    return saved ? JSON.parse(saved) : {
      clustering: false, // DISABLED - May interfere with data structure
      progressiveLoading: false, // DISABLED - Conflicts with data loading
      search: true, // ENABLED - Search functionality
      rustWebSocket: false, // DISABLED - WebSocket server not running
      dataKit: false, // DISABLED - Conflicts with DuckDB table initialization
      temporal: false, // DISABLED - May filter out needed data
      visualization: true, // ENABLED - Advanced visualization strategies
      selection: true, // ENABLED - Selection tools
      keyboard: true, // ENABLED - Keyboard shortcuts
      performance: false, // DISABLED - FPS tracking causing issues
      layout: false // DISABLED - May interfere with positioning
    };
  });
  
  // Internal ref for the actual GraphCanvas - stable across re-renders
  const graphCanvasRef = useRef<GraphCanvasHandle>(null);
  
  // Create a data version that changes only when nodes/links change
  const dataVersion = useMemo(() => {
    return `${nodes.length}-${links.length}-${Date.now()}`;
  }, [nodes, links]);
  
  // FPS tracking - only when performance monitoring is enabled
  useEffect(() => {
    if (!activeFeatures.performance) return;
    
    let frameCount = 0;
    let lastTime = performance.now();
    let rafId: number;
    let isActive = true;
    
    const measureFPS = () => {
      if (!isActive) return;
      
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
      isActive = false;
      if (rafId) {
        cancelAnimationFrame(rafId);
      }
    };
  }, [activeFeatures.performance]);
  
  // Expose methods via ref
  useImperativeHandle(ref, () => ({
    // Viewport controls
    zoomIn: () => graphCanvasRef.current?.zoomIn(),
    zoomOut: () => graphCanvasRef.current?.zoomOut(),
    fitView: () => graphCanvasRef.current?.fitView(),
    pauseSimulation: () => graphCanvasRef.current?.pauseSimulation(),
    resumeSimulation: () => graphCanvasRef.current?.resumeSimulation(),
    screenshot: () => graphCanvasRef.current?.screenshot(),
    recenter: () => graphCanvasRef.current?.recenter(),
    getNodeScreenPosition: (nodeId: string) => graphCanvasRef.current?.getNodeScreenPosition(nodeId),

    // Selection methods - forward to underlying GraphCanvas
    clearSelection: () => graphCanvasRef.current?.clearSelection(),
    selectNode: (node: GraphNode) => graphCanvasRef.current?.selectNode(node),
    selectNodes: (nodes: GraphNode[]) => graphCanvasRef.current?.selectNodes(nodes),

    // Data query methods - required by useNodeSelection hook
    getConnectedPointIndices: (index: number) => graphCanvasRef.current?.getConnectedPointIndices(index),
    getPointIndicesByExactValues: (keyValues: Record<string, unknown>) => graphCanvasRef.current?.getPointIndicesByExactValues(keyValues),

    // Additional methods that might be needed
    fitViewByPointIndices: (indices: number[], duration?: number, padding?: number) => graphCanvasRef.current?.fitViewByPointIndices(indices, duration, padding),
    zoomToPoint: (index: number, duration?: number, scale?: number, canZoomOut?: boolean) => graphCanvasRef.current?.zoomToPoint(index, duration, scale, canZoomOut),
    trackPointPositionsByIndices: (indices: number[]) => graphCanvasRef.current?.trackPointPositionsByIndices(indices),
    getTrackedPointPositionsMap: () => graphCanvasRef.current?.getTrackedPointPositionsMap()
  }), []);

  // Handle node details
  useEffect(() => {
    setShowNodeDetails(!!selectedNode);
  }, [selectedNode]);

  // Update processed nodes/links when props change
  useEffect(() => {
    // Update nodes when they change (unless dataKit is handling them)
    if (!activeFeatures.dataKit) {
      setProcessedNodes(nodes);
    }
  }, [nodes, activeFeatures.dataKit]);
  
  useEffect(() => {
    // Update links when they change (unless dataKit is handling them)
    if (!activeFeatures.dataKit) {
      setProcessedLinks(links);
    }
  }, [links, activeFeatures.dataKit]);

  // Handle data transformation from DataKit
  const handleDataTransformed = useCallback((data: any) => {
    setProcessedNodes(data.nodes);
    setProcessedLinks(data.edges);
  }, []);

  // Handle clustering updates
  const handleClusteringUpdate = useCallback((result: any) => {
    console.log('[Enhanced] Clustering updated:', result);
  }, []);

  // Handle layout changes
  const handleLayoutComplete = useCallback((result: any) => {
    if (result.nodes && graphCanvasRef.current) {
      // Apply new positions to nodes
      const positionMap = new Map(result.nodes.map((n: any) => [n.id, { x: n.x, y: n.y }]));
      setProcessedNodes(prevNodes => prevNodes.map(node => ({
        ...node,
        ...positionMap.get(node.id)
      })));
    }
  }, []);

  // Handle performance warnings
  const handlePerformanceWarning = useCallback((warning: any) => {
    console.warn('[Performance]', warning.message);
  }, []);

  // Use stable callbacks to prevent re-renders
  const handleSearchResults = useStableCallback((results: any[]) => {
    if (results.length > 0 && onSelectNodes) {
      onSelectNodes(results.map(r => r.node));
    }
  }, [onSelectNodes]);

  const handleSelectionChange = useStableCallback((selectedNodes: GraphNode[]) => {
    if (onSelectNodes) {
      onSelectNodes(selectedNodes);
    }
  }, [onSelectNodes]);

  // Handle temporal filtering
  const handleTemporalFilter = useCallback((filteredNodes: GraphNode[], filteredEdges: any[]) => {
    setProcessedNodes(filteredNodes);
    setProcessedLinks(filteredEdges);
  }, []);

  // Handle WebSocket deltas
  const handleRustDelta = useCallback((delta: any) => {
    // Apply incremental updates from Rust server
    if (delta.added_nodes || delta.removed_nodes || delta.updated_nodes) {
      setProcessedNodes(prev => {
        let updated = [...prev];
        
        // Remove nodes
        if (delta.removed_nodes) {
          const removeSet = new Set(delta.removed_nodes);
          updated = updated.filter(n => !removeSet.has(n.id));
        }
        
        // Add nodes
        if (delta.added_nodes) {
          updated.push(...delta.added_nodes);
        }
        
        // Update nodes
        if (delta.updated_nodes) {
          const updateMap = new Map(delta.updated_nodes.map((n: any) => [n.id, n]));
          updated = updated.map(n => updateMap.has(n.id) ? { ...n, ...updateMap.get(n.id) } : n);
        }
        
        return updated;
      });
    }
  }, []);

  
  // Handle keyboard shortcuts - memoized to prevent re-renders
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

  // Save feature preferences - debounced to prevent excessive writes
  useEffect(() => {
    const timer = setTimeout(() => {
      localStorage.setItem('graphiti.features', JSON.stringify(activeFeatures));
    }, 500);
    return () => clearTimeout(timer);
  }, [activeFeatures]);

  // Toggle feature
  const toggleFeature = useCallback((feature: string) => {
    setActiveFeatures(prev => ({
      ...prev,
      [feature]: !prev[feature]
    }));
  }, []);

  return (
    <GraphErrorBoundary>
      <div className="relative h-full w-full overflow-hidden bg-gray-950">
        {/* Wrappers with stable props to prevent Cosmograph re-initialization */}
        <KeyboardShortcuts
          shortcuts={keyboardShortcuts}
          onShortcutTriggered={useStableCallback((shortcut) => console.log('[Shortcut]', shortcut.id), [])}
        >
          <SearchManager
            nodes={nodes}
            onSearchResults={handleSearchResults}
          >
            <VisualizationStrategies
              nodes={nodes}
              edges={links}
              config={useMemo(() => ({
                color: { scheme: 'type' },
                size: { strategy: 'degree' },
                shape: { strategy: 'circle' }
              }), [])}
            >
              <SelectionTools
                nodes={nodes}
                edges={links}
                config={useMemo(() => ({
                  multiSelect: true,
                  boxSelect: true,
                  lassoSelect: false
                }), [])}
                onSelectionChange={handleSelectionChange}
              >
                {/* CosmographGuard prevents re-renders unless data actually changes */}
                <CosmographGuard dataVersion={dataVersion}>
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
                    onNodeClick={onNodeClick}
                    onNodeSelect={onNodeSelect}
                    onSelectNodes={onSelectNodes}
                    onNodeHover={onNodeHover}
                    onClearSelection={onClearSelection}
                    onStatsUpdate={onStatsUpdate}
                  />
                </CosmographGuard>
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

GraphViewportEnhanced.displayName = 'GraphViewportEnhanced';

// Helper component for conditional wrapping - memoized to prevent re-renders
const ConditionalWrapper: React.FC<{
  condition: boolean;
  wrapper: (children: React.ReactNode) => React.ReactNode;
  children: React.ReactNode;
}> = React.memo(({ condition, wrapper, children }) => {
  return condition ? <>{wrapper(children)}</> : <>{children}</>;
}, (prevProps, nextProps) => {
  // Only re-render if condition changes
  return prevProps.condition === nextProps.condition && 
         prevProps.children === nextProps.children;
});

export { GraphViewportEnhanced };