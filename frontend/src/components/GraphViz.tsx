import React, { useRef, useEffect, useCallback, useMemo } from 'react';
import { useStableCallback } from '../hooks/useStableCallback';
import { CosmographProvider } from '@cosmograph/react';
import { useGraphConfig } from '../contexts/GraphConfigProvider';
import { ControlPanel } from './ControlPanel';
import { LazyGraphCanvas } from './LazyGraphCanvas';

// GRAPH-93: Zustand stores for global state management
import { useUIStore, useGraphStore, useSelectionStore } from '../stores';

// Lazy load modal panels - PERFORMANCE FIX (GRAPH-42): Lazy load all conditional panels
const FilterPanel = React.lazy(() => import('./FilterPanel').then(m => ({ default: m.FilterPanel })));
const StatsPanel = React.lazy(() => import('./StatsPanel').then(m => ({ default: m.StatsPanel })));
const MonitoringDashboard = React.lazy(() => import('./MonitoringDashboard').then(m => ({ default: m.MonitoringDashboard })));
const NodeDetailsPanel = React.lazy(() => import('./NodeDetailsPanel').then(m => ({ default: m.NodeDetailsPanel })));
import { GraphNavBar } from './GraphNavBar';
import { CentralityStatsProvider } from '../contexts/CentralityStatsContext';

// Lazy load heavy components
const GraphTimeline = React.lazy(() => import('./GraphTimeline').then(m => ({ default: m.GraphTimeline })));
type GraphTimelineHandle = any; // Type will be resolved at runtime
import { useGraphDataQuery } from '../hooks/useGraphDataQuery';
import { GraphNode } from '../types/graph';
import { GraphLink } from '../types/graph';
import type { GraphCanvasHandle, GraphVizProps } from '../types/components';
import { getErrorMessage } from '../types/errors';
import { calculateNodeDegrees } from '../utils/graphNodeOperations';

export const GraphViz: React.FC<GraphVizProps> = ({ className }) => {
  const { applyLayout, zoomIn, zoomOut, fitView } = useGraphConfig();
  const { config } = useGraphConfig();

  // GRAPH-93: UI State from Zustand store
  const {
    leftPanelCollapsed,
    setLeftPanelCollapsed,
    showFilterPanel,
    setShowFilterPanel,
    showStatsPanel,
    showMonitoringPanel,
    isFullscreen,
    isTimelineVisible,
    timelineUpdateMode,
    setTimelineUpdateMode,
  } = useUIStore();

  // GRAPH-93: Graph state from Zustand store
  const {
    isSimulationRunning,
    isContextReady,
    setContextReady,
    setLiveStats,
  } = useGraphStore();

  // GRAPH-93: Selection state from Zustand store (replaces useGraphSelection hook)
  const {
    selectedNode,
    hoveredNode,
    highlightedNodes,
    selectNode,
    hoverNodeById: setHoveredNode,
    clearAll: clearSelection,
  } = useSelectionStore();

  // Refs
  const graphCanvasRef = useRef<GraphCanvasHandle>(null);
  const timelineRef = useRef<GraphTimelineHandle>(null);
  const stableGraphPropsRef = useRef<{ nodes: GraphNode[], links: GraphLink[] } | null>(null);

  // Track recent data updates to optimize timeline animation mode
  const lastDataUpdateTime = useRef<number>(0);

  // Handle context ready state from GraphCanvas
  const handleContextReady = useCallback((ready: boolean) => {
    setContextReady(ready);
  }, [setContextReady]);

  // Fetch graph data using React Query
  const {
    transformedData,
    isLoading,
    error,
    refreshDuckDBData
  } = useGraphDataQuery();

  // Use stable callback to avoid re-renders
  const handleNodeClick = useStableCallback((node: GraphNode | null) => {
    selectNode(node);
  });

  const handleNodeHover = useStableCallback((node: GraphNode | null) => {
    if (setHoveredNode) {
      setHoveredNode(node?.id || null);
    }
  });

  // Use transformedData directly - it already has correct structure and centrality calculations
  // IMPORTANT: Only use data when we actually have it to prevent Cosmograph errors
  const hasValidData = !isLoading && transformedData?.nodes?.length > 0;
  const cosmographNodes = useMemo(() => hasValidData ? transformedData?.nodes : [], [transformedData, hasValidData]);
  const cosmographLinks = useMemo(() => hasValidData ? transformedData?.links : [], [transformedData, hasValidData]);

  // DEBUG: Log what transformedData contains (only when state changes significantly)
  useEffect(() => {
    if (hasValidData) {
      console.log('[GraphViz] Data ready:', {
        nodesCount: cosmographNodes.length,
        linksCount: cosmographLinks.length
      });
    }
  }, [hasValidData, cosmographNodes.length, cosmographLinks.length]);

  // Track data updates for timeline animation mode
  useEffect(() => {
    if (transformedData) {
      const now = Date.now();
      const timeSinceLastUpdate = now - lastDataUpdateTime.current;

      // If we haven't had an update in 2 seconds, switch back to animated mode
      if (timeSinceLastUpdate > 2000) {
        setTimelineUpdateMode('animated');
      }

      lastDataUpdateTime.current = now;
    }
  }, [transformedData, setTimelineUpdateMode]);

  // Handle live stats updates from GraphCanvas
  const handleLiveStatsUpdate = useCallback((stats: { nodeCount: number; edgeCount: number }) => {
    setLiveStats({ ...stats, lastUpdated: Date.now() });
  }, [setLiveStats]);

  // Handle closing the details panel
  const handleCloseDetails = useCallback(() => {
    selectNode(null);
  }, [selectNode]);

  // Handle timeline node selection
  const handleTimelineNodeSelect = useCallback((nodeId: string | null) => {
    if (!nodeId) {
      selectNode(null);
      return;
    }

    // Find the node in our data
    const node = cosmographNodes.find(n => n.id === nodeId);
    if (node) {
      selectNode(node);
      // Focus on the node in the graph
      graphCanvasRef.current?.focusNode(nodeId);
    }
  }, [cosmographNodes, selectNode]);

  // Stable graph props for child components
  const stableGraphProps = useMemo(() => {
    const props = {
      nodes: cosmographNodes,
      links: cosmographLinks,
    };
    stableGraphPropsRef.current = props;
    return props;
  }, [cosmographNodes, cosmographLinks]);

  // Error state
  if (error) {
    return (
      <div className="flex items-center justify-center h-full bg-background">
        <div className="text-center p-8">
          <h2 className="text-xl font-semibold text-destructive mb-2">Error Loading Graph</h2>
          <p className="text-muted-foreground mb-4">{getErrorMessage(error)}</p>
          <button
            onClick={() => refreshDuckDBData()}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <CosmographProvider>
      <CentralityStatsProvider nodes={cosmographNodes}>
        <div className={`relative h-full w-full overflow-hidden ${isFullscreen ? 'fixed inset-0 z-50' : ''} ${className || ''}`}>
          {/* Navigation Bar - GRAPH-93: Now reads most state from Zustand stores */}
          <GraphNavBar
            nodes={cosmographNodes}
            links={cosmographLinks}
            onZoomIn={zoomIn}
            onZoomOut={zoomOut}
            onFitView={fitView}
            onRefresh={() => refreshDuckDBData()}
            isRefreshing={isLoading}
          />

          {/* Main Content Area - Flex container for left panel, graph, and right panel */}
          <div className="flex h-[calc(100%-48px)] mt-12">
            {/* Left Control Panel */}
            <div className={`transition-all duration-300 ${leftPanelCollapsed ? 'w-12' : 'w-80'} flex-shrink-0 overflow-hidden z-20`}>
              <ControlPanel
                collapsed={leftPanelCollapsed}
                onToggleCollapse={() => setLeftPanelCollapsed(!leftPanelCollapsed)}
              />
            </div>

            {/* Graph Canvas */}
            <div className="flex-1 relative overflow-hidden bg-background/5">
              <LazyGraphCanvas
                ref={graphCanvasRef}
                nodes={cosmographNodes}
                links={cosmographLinks}
                selectedNodes={selectedNode ? [selectedNode.id] : []}
                highlightedNodes={highlightedNodes || []}
                onNodeClick={handleNodeClick}
                onNodeSelect={(nodeId: string) => {
                  const node = cosmographNodes.find(n => n.id === nodeId);
                  if (node) selectNode(node);
                }}
                onSelectNodes={(nodes: GraphNode[]) => {
                  if (nodes.length > 0) selectNode(nodes[0]);
                }}
                onClearSelection={clearSelection}
                onNodeHover={handleNodeHover}
                onStatsUpdate={handleLiveStatsUpdate}
                onContextReady={handleContextReady}
              />

              {/* Timeline - Positioned absolutely at bottom */}
              {isTimelineVisible && isContextReady && (
                <React.Suspense fallback={<div className="absolute bottom-0 left-0 right-0 h-20 bg-background/50 animate-pulse z-10" />}>
                  <div className="absolute bottom-0 left-0 right-0 z-10">
                    <GraphTimeline
                      ref={timelineRef}
                      nodes={cosmographNodes}
                      links={cosmographLinks}
                      onNodeSelect={handleTimelineNodeSelect}
                      selectedNodeId={selectedNode?.id || null}
                      updateMode={timelineUpdateMode}
                    />
                  </div>
                </React.Suspense>
              )}
            </div>

            {/* Right Panel - Node Details */}
            {selectedNode && (
              <div className="w-96 flex-shrink-0 border-l border-border bg-card/95 backdrop-blur-sm shadow-xl z-20 overflow-y-auto">
                <React.Suspense fallback={<div className="p-4 animate-pulse">Loading details...</div>}>
                  <NodeDetailsPanel
                    node={selectedNode}
                    onClose={handleCloseDetails}
                  />
                </React.Suspense>
              </div>
            )}
          </div>

          {/* Modal Panels */}
          {showFilterPanel && (
            <React.Suspense fallback={<div className="fixed inset-0 bg-background/50 animate-pulse" />}>
              <FilterPanel
                isOpen={showFilterPanel}
                onClose={() => setShowFilterPanel(false)}
              />
            </React.Suspense>
          )}

          {showStatsPanel && (
            <React.Suspense fallback={<div className="fixed inset-0 bg-background/50 animate-pulse" />}>
              <StatsPanel
                isOpen={showStatsPanel}
                onClose={() => useUIStore.getState().setShowStatsPanel(false)}
                nodes={cosmographNodes}
                links={cosmographLinks}
              />
            </React.Suspense>
          )}

          {showMonitoringPanel && (
            <React.Suspense fallback={<div className="fixed inset-0 bg-background/50 animate-pulse" />}>
              <MonitoringDashboard
                isOpen={showMonitoringPanel}
                onClose={() => useUIStore.getState().setShowMonitoringPanel(false)}
              />
            </React.Suspense>
          )}

          {/* Loading Overlay */}
          {isLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-40">
              <div className="flex flex-col items-center gap-4">
                <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin" />
                <p className="text-muted-foreground">Loading graph data...</p>
              </div>
            </div>
          )}
        </div>
      </CentralityStatsProvider>
    </CosmographProvider>
  );
};

export default GraphViz;
