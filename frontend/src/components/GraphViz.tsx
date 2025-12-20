import React, { useRef, useEffect, useCallback, useMemo } from 'react';
import { useStableCallback } from '../hooks/useStableCallback';
import { CosmographProvider } from '@cosmograph/react';
import { useGraphConfig } from '../contexts/GraphConfigProvider';
import { ControlPanel } from './ControlPanel';
import { LazyGraphCanvas } from './LazyGraphCanvas';

// Zustand stores - GRAPH-93: Migrated from useState to Zustand
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
// GRAPH-86: Migrated from useNodeSelection to useGraphSelection
import { useGraphSelection } from '../hooks/useGraphSelection';
// GRAPH-87: Migrated from useIncrementalUpdates to useCosmographIncrementalUpdates
import { useCosmographIncrementalUpdates } from '../hooks/useCosmographIncrementalUpdates';
import { GraphNode } from '../api/types';
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
    data: graphData, 
    isLoading, 
    error,
    refetch,
    isRefetching
  } = useGraphDataQuery();
  
  // GRAPH-86: Migrated to consolidated useGraphSelection hook
  const {
    selectedNode,
    setSelectedNode,
    hoveredNode,
    setHoveredNode,
    highlightedNodes,
    clearSelection
  } = useGraphSelection();
  
  // Calculate node degrees for sizing
  const nodesWithDegrees = useMemo(() => {
    if (!graphData?.nodes) return [];
    return calculateNodeDegrees(graphData.nodes, graphData.links || []);
  }, [graphData?.nodes, graphData?.links]);

  // Use stable callback to avoid re-renders
  const handleNodeClick = useStableCallback((node: GraphNode | null) => {
    setSelectedNode(node);
  });

  const handleNodeHover = useStableCallback((node: GraphNode | null) => {
    setHoveredNode(node);
  });
  
  // GRAPH-87: Migrated to consolidated useCosmographIncrementalUpdates hook
  const { 
    cosmographNodes, 
    cosmographLinks,
    resetData
  } = useCosmographIncrementalUpdates({
    initialNodes: nodesWithDegrees,
    initialLinks: graphData?.links || [],
    selectedNodeId: selectedNode?.id || null,
    hoveredNodeId: hoveredNode?.id || null,
    highlightedNodeIds: highlightedNodes,
    onNodesChange: () => {
      // Update timeline when data changes
      lastDataUpdateTime.current = Date.now();
      // Use instant mode for real-time updates to prevent animation lag
      setTimelineUpdateMode('instant');
    }
  });

  // Track data updates for timeline animation mode
  useEffect(() => {
    if (graphData) {
      const now = Date.now();
      const timeSinceLastUpdate = now - lastDataUpdateTime.current;
      
      // If we haven't had an update in 2 seconds, switch back to animated mode
      if (timeSinceLastUpdate > 2000) {
        setTimelineUpdateMode('animated');
      }
      
      lastDataUpdateTime.current = now;
    }
  }, [graphData, setTimelineUpdateMode]);

  // Sync cosmograph data when graphData changes
  useEffect(() => {
    if (nodesWithDegrees.length > 0 || graphData?.links?.length) {
      resetData(nodesWithDegrees, graphData?.links || [], 'graphData');
    }
  }, [nodesWithDegrees, graphData?.links, resetData]);

  // Handle live stats updates from GraphCanvas
  const handleLiveStatsUpdate = useCallback((stats: { nodeCount: number; edgeCount: number }) => {
    setLiveStats({ ...stats, lastUpdated: Date.now() });
  }, [setLiveStats]);

  // Handle closing the details panel
  const handleCloseDetails = useCallback(() => {
    setSelectedNode(null);
  }, [setSelectedNode]);

  // Handle timeline node selection
  const handleTimelineNodeSelect = useCallback((nodeId: string | null) => {
    if (!nodeId) {
      setSelectedNode(null);
      return;
    }
    
    // Find the node in our data
    const node = cosmographNodes.find(n => n.id === nodeId);
    if (node) {
      setSelectedNode(node);
      // Focus on the node in the graph
      graphCanvasRef.current?.focusNode(nodeId);
    }
  }, [cosmographNodes, setSelectedNode]);

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
            onClick={() => refetch()}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <CosmographProvider nodes={cosmographNodes} links={cosmographLinks}>
      <CentralityStatsProvider>
        <div className={`relative h-full w-full overflow-hidden ${isFullscreen ? 'fixed inset-0 z-50' : ''} ${className || ''}`}>
          {/* Navigation Bar - GRAPH-93: Now reads most state from Zustand stores */}
          <GraphNavBar
            nodes={cosmographNodes}
            links={cosmographLinks}
            onZoomIn={zoomIn}
            onZoomOut={zoomOut}
            onFitView={fitView}
            onRefresh={() => refetch()}
            isRefreshing={isRefetching}
          />

          {/* Main Content Area */}
          <div className="flex h-[calc(100%-48px)] mt-12">
            {/* Left Control Panel */}
            <div className={`transition-all duration-300 ${leftPanelCollapsed ? 'w-0' : 'w-64'} overflow-hidden`}>
              <ControlPanel
                collapsed={leftPanelCollapsed}
                onToggleCollapse={() => setLeftPanelCollapsed(!leftPanelCollapsed)}
                onApplyLayout={applyLayout}
              />
            </div>

            {/* Graph Canvas */}
            <div className="flex-1 relative">
              <LazyGraphCanvas
                ref={graphCanvasRef}
                nodes={cosmographNodes}
                links={cosmographLinks}
                selectedNode={selectedNode}
                hoveredNode={hoveredNode}
                onNodeClick={handleNodeClick}
                onNodeHover={handleNodeHover}
                isSimulationRunning={isSimulationRunning}
                onLiveStatsUpdate={handleLiveStatsUpdate}
                onContextReady={handleContextReady}
                config={config}
              />

              {/* Timeline */}
              {isTimelineVisible && isContextReady && (
                <React.Suspense fallback={<div className="absolute bottom-0 left-0 right-0 h-32 bg-background/50 animate-pulse" />}>
                  <GraphTimeline
                    ref={timelineRef}
                    nodes={cosmographNodes}
                    links={cosmographLinks}
                    onNodeSelect={handleTimelineNodeSelect}
                    selectedNodeId={selectedNode?.id || null}
                    updateMode={timelineUpdateMode}
                  />
                </React.Suspense>
              )}
            </div>

            {/* Right Panel - Node Details */}
            {selectedNode && (
              <div className="w-80 border-l border-border overflow-auto">
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
