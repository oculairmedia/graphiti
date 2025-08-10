import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { useStableCallback } from '../hooks/useStableCallback';
import { CosmographProvider } from '@cosmograph/react';
import { useGraphConfig } from '../contexts/GraphConfigProvider';
import { ControlPanel } from './ControlPanel';
import { GraphViewport } from './GraphViewport';
import { GraphViewportSimplified } from './GraphViewportSimplified';
import { LayoutPanel } from './LayoutPanel';
import { logger } from '../utils/logger';

// Lazy load modal panels
const FilterPanel = React.lazy(() => import('./FilterPanel').then(m => ({ default: m.FilterPanel })));
const StatsPanel = React.lazy(() => import('./StatsPanel').then(m => ({ default: m.StatsPanel })));
import { GraphNavBar } from './GraphNavBar';

// Lazy load heavy components
const GraphTimeline = React.lazy(() => import('./GraphTimeline').then(m => ({ default: m.GraphTimeline })));
type GraphTimelineHandle = any; // Type will be resolved at runtime
import { useGraphDataQuery } from '../hooks/useGraphDataQuery';
import { useNodeSelection } from '../hooks/useNodeSelection';
import { useIncrementalUpdates } from '../hooks/useIncrementalUpdates';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import type { GraphCanvasHandle, GraphVizProps } from '../types/components';
import { getErrorMessage } from '../types/errors';

export const GraphViz: React.FC<GraphVizProps> = ({ className }) => {
  // Feature flag for using refactored components
  const USE_REFACTORED_COMPONENTS = localStorage.getItem('graphiti.useRefactoredComponents') === 'true';
  
  // Debug component lifecycle
  useEffect(() => {
    console.log('[GraphViz] Component mounted, using refactored:', USE_REFACTORED_COMPONENTS);
    return () => {
      console.log('[GraphViz] Component unmounting');
    };
  }, []);
  
  const { applyLayout, zoomIn, zoomOut, fitView } = useGraphConfig();
  
  // UI State
  const [leftPanelCollapsed, setLeftPanelCollapsed] = useState(false);
  const [rightPanelCollapsed, setRightPanelCollapsed] = useState(false);
  const [showFilterPanel, setShowFilterPanel] = useState(false);
  const [showStatsPanel, setShowStatsPanel] = useState(false);
  const [showLayoutPanel, setShowLayoutPanel] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isSimulationRunning, setIsSimulationRunning] = useState(true);
  
  // Live stats from GraphCanvas for real-time updates
  const [liveStats, setLiveStats] = useState<{ nodeCount: number; edgeCount: number; lastUpdated: number } | null>(null);
  

  // Refs
  const graphCanvasRef = useRef<GraphCanvasHandle>(null);
  const timelineRef = useRef<GraphTimelineHandle>(null);
  const stableGraphPropsRef = useRef<{ nodes: GraphNode[], links: GraphLink[] } | null>(null);
  
  // Timeline visibility state
  const [isTimelineVisible, setIsTimelineVisible] = useState(() => {
    // Load from localStorage
    const saved = localStorage.getItem('graphiti.timeline.visible');
    return saved !== null ? saved === 'true' : true;
  });

  // Handle timeline visibility change
  const handleTimelineVisibilityChange = useCallback((visible: boolean) => {
    setIsTimelineVisible(visible);
    localStorage.setItem('graphiti.timeline.visible', String(visible));
  }, []);

  // Toggle timeline visibility
  const toggleTimeline = useCallback(() => {
    const newVisibility = !isTimelineVisible;
    setIsTimelineVisible(newVisibility);
    localStorage.setItem('graphiti.timeline.visible', String(newVisibility));
  }, [isTimelineVisible]);

  // Handle stats updates from GraphCanvas
  const handleStatsUpdate = useCallback((stats: { nodeCount: number; edgeCount: number; lastUpdated: number }) => {
    setLiveStats(stats);
  }, []);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl/Cmd + T to toggle timeline
      if ((e.ctrlKey || e.metaKey) && e.key === 't') {
        e.preventDefault();
        toggleTimeline();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [toggleTimeline]);

  // Custom hooks
  const {
    data,
    transformedData,
    isLoading,
    error,
    dataDiff,
    isIncrementalUpdate,
    setIsIncrementalUpdate,
    isGraphInitialized,
    stableDataRef,
  } = useGraphDataQuery();
  
  const {
    selectedNodes,
    selectedNode,
    highlightedNodes,
    hoveredNode,
    hoveredConnectedNodes,
    handleNodeSelect,
    handleNodeClick,
    handleNodeSelectWithCosmograph,
    handleHighlightNodes,
    handleSelectNodes,
    handleShowNeighbors,
    handleNodeHover,
    clearAllSelections,
  } = useNodeSelection(transformedData, graphCanvasRef);

  // Apply incremental updates
  useIncrementalUpdates(
    graphCanvasRef,
    dataDiff,
    isGraphInitialized,
    isIncrementalUpdate,
    setIsIncrementalUpdate,
    data,
    stableDataRef
  );
  
  // Preload resources for better performance
  useEffect(() => {
    // Note: Shader preloading removed - shader files not present in public directory
    // Cosmograph handles its own WebGL shader loading internally
    
    // Graph data endpoints are loaded on demand by the query hooks
  }, []);

  // Use stable callbacks for navigation handlers
  const handleZoomIn = useStableCallback(zoomIn);
  const handleZoomOut = useStableCallback(zoomOut);
  const handleFitView = useStableCallback(fitView);

  const handleLayoutChange = useCallback((layoutType: string) => {
    if (transformedData && transformedData.nodes.length > 0) {
      applyLayout(layoutType, {}, { 
        nodes: transformedData.nodes, 
        edges: transformedData.links.map(link => ({ 
          from: link.source, 
          to: link.target, 
          ...link 
        })) 
      });
    }
  }, [applyLayout, transformedData]);

  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  }, []);

  const handleDownloadGraph = useCallback(() => {
    if (!data) return;
    
    const graphData = {
      nodes: data.nodes,
      edges: data.edges,
      metadata: {
        exportedAt: new Date().toISOString(),
        totalNodes: data.nodes.length,
        totalEdges: data.edges.length
      }
    };
    
    const blob = new Blob([JSON.stringify(graphData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `graphiti-export-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [data]);

  const handleCaptureScreenshot = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
      const video = document.createElement('video');
      video.srcObject = stream;
      video.play();
      
      video.addEventListener('loadedmetadata', () => {
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');
        ctx?.drawImage(video, 0, 0);
        
        canvas.toBlob((blob) => {
          if (blob) {
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `graphiti-screenshot-${new Date().toISOString().split('T')[0]}.png`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
          }
        }, 'image/png');
        
        stream.getTracks().forEach(track => track.stop());
      });
    } catch (error) {
      // Screenshot capture failed - user cancelled or not supported
      console.info('Screenshot capture cancelled or not supported');
    }
  }, []);

  const toggleSimulation = useCallback(() => {
    if (!graphCanvasRef.current) return;
    
    if (isSimulationRunning) {
      graphCanvasRef.current.pauseSimulation();
      setIsSimulationRunning(false);
    } else {
      graphCanvasRef.current.resumeSimulation();
      setIsSimulationRunning(true);
    }
  }, [isSimulationRunning]);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  // Cleanup refs on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      // Clear data refs
      stableGraphPropsRef.current = null;
      
      // Clear any pending operations
      if (graphCanvasRef.current) {
        graphCanvasRef.current = null;
      }
    };
  }, []);

  // Memoize data for rendering to prevent unnecessary re-renders
  const dataToUse = useMemo(() => {
    if (isIncrementalUpdate && stableGraphPropsRef.current) {
      return stableGraphPropsRef.current;
    }
    
    // Update stable props when not in incremental update mode
    if (!isIncrementalUpdate && transformedData) {
      stableGraphPropsRef.current = {
        nodes: transformedData.nodes,
        links: transformedData.links
      };
    }
    
    return transformedData || { nodes: [], links: [] };
  }, [isIncrementalUpdate, transformedData]);

  // Note: Loading is now handled by UnifiedLoadingScreen in ParallelInitProvider
  // This is only for edge cases where data might be loading after initial load

  // Handle error state
  if (error) {
    return (
      <div className={`h-screen w-full flex items-center justify-center bg-background ${className}`}>
        <div className="text-destructive text-center">
          <p>Error loading graph: {(error as Error).message}</p>
          <p className="text-sm text-muted-foreground mt-2">
            Make sure the Rust server is running at localhost:3000
          </p>
        </div>
      </div>
    );
  }
  
  // Handle empty data state after loading
  if (!data?.nodes?.length) {
    return (
      <div className={`h-screen w-full flex items-center justify-center bg-background ${className}`}>
        <div className="text-muted-foreground text-center">
          <p>No graph data available</p>
        </div>
      </div>
    );
  }

  return (
    <CosmographProvider>
      <div className={`h-screen w-full flex flex-col bg-background overflow-hidden ${className}`}>
        {/* Top Navigation Bar */}
        <GraphNavBar
          totalNodes={data?.nodes.length || 0}
          visibleNodes={transformedData.nodes.length}
          isVirtualized={data && data.nodes.length > 10000}
          isSimulationRunning={isSimulationRunning}
          selectedNodes={selectedNodes}
          allNodes={transformedData.nodes}
          onNodeSelect={handleNodeSelectWithCosmograph}
          onHighlightNodes={handleHighlightNodes}
          onSelectNodes={handleSelectNodes}
          onClearSelection={clearAllSelections}
          onFilterClick={() => setShowFilterPanel(true)}
          onDownload={handleDownloadGraph}
          onUpload={() => {/* Upload functionality would require file input */}}
          onScreenshot={handleCaptureScreenshot}
          onToggleSimulation={toggleSimulation}
          onLayoutClick={() => setShowLayoutPanel(true)}
          onSettingsClick={() => setLeftPanelCollapsed(!leftPanelCollapsed)}
          onStatsClick={() => setShowStatsPanel(true)}
          onFullscreenClick={toggleFullscreen}
        />

        {/* Main Content Area */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left Control Panel */}
          <div className={`${leftPanelCollapsed ? 'w-12' : 'w-80'} transition-all duration-300 flex-shrink-0`}>
            <ControlPanel 
              collapsed={leftPanelCollapsed}
              onToggleCollapse={() => setLeftPanelCollapsed(!leftPanelCollapsed)}
              onLayoutChange={handleLayoutChange}
              graphCanvasRef={graphCanvasRef}
              nodes={transformedData.nodes}
              onNodeSelect={handleNodeClick}
            />
          </div>

          {/* Main Graph Viewport - Conditionally use simplified components */}
          {USE_REFACTORED_COMPONENTS ? (
            <GraphViewportSimplified
              ref={graphCanvasRef}
              nodes={dataToUse.nodes}
              links={dataToUse.links}
              selectedNodes={selectedNodes}
              highlightedNodes={highlightedNodes}
              hoveredNode={hoveredNode}
              hoveredConnectedNodes={hoveredConnectedNodes}
              selectedNode={selectedNode}
              stats={data?.stats}
              onNodeClick={handleNodeClick}
              onNodeSelect={handleNodeSelect}
              onSelectNodes={handleSelectNodes}
              onNodeHover={handleNodeHover}
              onClearSelection={clearAllSelections}
              onShowNeighbors={handleShowNeighbors}
              onZoomIn={handleZoomIn}
              onZoomOut={handleZoomOut}
              onFitView={handleFitView}
              onScreenshot={handleCaptureScreenshot}
              onToggleTimeline={toggleTimeline}
              isTimelineVisible={isTimelineVisible}
              onStatsUpdate={handleStatsUpdate}
            />
          ) : (
            <GraphViewport
              ref={graphCanvasRef}
              nodes={dataToUse.nodes}
              links={dataToUse.links}
              selectedNodes={selectedNodes}
              highlightedNodes={highlightedNodes}
              hoveredNode={hoveredNode}
              hoveredConnectedNodes={hoveredConnectedNodes}
              selectedNode={selectedNode}
              stats={data?.stats}
              onNodeClick={handleNodeClick}
              onNodeSelect={handleNodeSelect}
              onSelectNodes={handleSelectNodes}
              onNodeHover={handleNodeHover}
              onClearSelection={clearAllSelections}
              onShowNeighbors={handleShowNeighbors}
              onZoomIn={handleZoomIn}
              onZoomOut={handleZoomOut}
              onFitView={handleFitView}
              onScreenshot={handleCaptureScreenshot}
              onToggleTimeline={toggleTimeline}
              isTimelineVisible={isTimelineVisible}
              onStatsUpdate={handleStatsUpdate}
            />
          )}

          {/* Right Layout Panel */}
          <div className={`${rightPanelCollapsed ? 'w-12' : 'w-80'} transition-all duration-300 flex-shrink-0`}>
            <LayoutPanel 
              collapsed={rightPanelCollapsed}
              onToggleCollapse={() => setRightPanelCollapsed(!rightPanelCollapsed)}
              graphData={transformedData}
            />
          </div>
        </div>

        {/* Modal Panels */}
        {showFilterPanel && (
          <React.Suspense fallback={<div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" /></div>}>
            <FilterPanel 
              isOpen={showFilterPanel}
              onClose={() => setShowFilterPanel(false)}
              data={data}
            />
          </React.Suspense>
        )}

        {showStatsPanel && (
          <React.Suspense fallback={<div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" /></div>}>
            <StatsPanel 
              isOpen={showStatsPanel}
              onClose={() => setShowStatsPanel(false)}
              data={transformedData.nodes.length > 0 ? {
                nodes: transformedData.nodes,
                edges: transformedData.links?.map(link => ({
                  source: link.source,
                  target: link.target,
                  edge_type: link.edge_type || '',
                  weight: link.weight || 1
                })) || [],
                stats: data?.stats || {}
              } : undefined}
              liveStats={liveStats}
            />
          </React.Suspense>
        )}
        
        {/* Timeline at the bottom */}
        {data && data.nodes && data.nodes.length > 0 && (
          <div className={`fixed bottom-0 z-50 transition-all duration-300`}
            style={{
              left: leftPanelCollapsed ? '48px' : '320px',
              right: rightPanelCollapsed ? '48px' : '320px'
            }}
          >
            <React.Suspense fallback={<div className="h-20 bg-background/80 backdrop-blur-sm" />}>
              <GraphTimeline 
                ref={timelineRef}
                isVisible={isTimelineVisible}
                onVisibilityChange={handleTimelineVisibilityChange}
                cosmographRef={graphCanvasRef}
                selectedCount={selectedNodes.length}
                onClearSelection={clearAllSelections}
                onScreenshot={handleCaptureScreenshot}
                onTimeRangeChange={(range) => {
                  // Handle timeline range changes
                  logger.log('Timeline range changed:', range);
                }}
                className=""
              />
            </React.Suspense>
          </div>
        )}
      </div>
    </CosmographProvider>
  );
};

export default GraphViz;