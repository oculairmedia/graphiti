import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { useStableCallback } from '../hooks/useStableCallback';
import { CosmographProvider } from '@cosmograph/react';
import { useGraphConfig } from '../contexts/GraphConfigProvider';
import { ControlPanel } from './ControlPanel';
import { LazyGraphCanvas } from './LazyGraphCanvas';

// Lazy load modal panels
const FilterPanel = React.lazy(() => import('./FilterPanel').then(m => ({ default: m.FilterPanel })));
const StatsPanel = React.lazy(() => import('./StatsPanel').then(m => ({ default: m.StatsPanel })));
const NodeDetailsPanel = React.lazy(() => import('./NodeDetailsPanel').then(m => ({ default: m.NodeDetailsPanel })));
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
import { calculateNodeDegrees } from '../utils/graphNodeOperations';

export const GraphViz: React.FC<GraphVizProps> = ({ className }) => {
  // Component rendering
  
  const { applyLayout, zoomIn, zoomOut, fitView } = useGraphConfig();
  
  // UI State
  const [leftPanelCollapsed, setLeftPanelCollapsed] = useState(false);
  // Right panel removed - no longer needed
  // const [rightPanelCollapsed, setRightPanelCollapsed] = useState(false);
  const [showFilterPanel, setShowFilterPanel] = useState(false);
  const [showStatsPanel, setShowStatsPanel] = useState(false);
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
  
  // Track if Cosmograph context is ready for timeline
  const [isContextReady, setIsContextReady] = useState(false);

  // Handle context ready state from GraphCanvas
  const handleContextReady = useCallback((ready: boolean) => {
    setIsContextReady(ready);
  }, []);

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
    pendingUpdate,
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
  
  // Hover state is managed by useNodeSelection hook

  // Calculate actual node degrees from edges for accurate connection counts
  const nodeDegreeMap = useMemo(() => {
    if (!transformedData?.nodes || !transformedData?.links) {
      return new Map<string, number>();
    }
    return calculateNodeDegrees(transformedData.nodes, transformedData.links);
  }, [transformedData?.nodes, transformedData?.links]);

  // Get actual connection count for selected node
  const selectedNodeConnections = selectedNode ? (nodeDegreeMap.get(selectedNode.id) || 0) : 0;

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

          {/* Main Graph Viewport - Using refactored components */}
          <div className="flex-1 relative">
            {/* Real-time update indicator */}
            {pendingUpdate && (
              <div className="absolute top-4 left-1/2 transform -translate-x-1/2 z-40">
                <div className="bg-primary/90 text-primary-foreground px-4 py-2 rounded-lg shadow-lg flex items-center space-x-2">
                  <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                  <span className="text-sm font-medium">Updating graph...</span>
                </div>
              </div>
            )}
            
            <LazyGraphCanvas
              ref={graphCanvasRef}
              nodes={dataToUse.nodes}
              links={dataToUse.links}
            selectedNodes={selectedNodes}
            highlightedNodes={highlightedNodes}
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
              onContextReady={handleContextReady}
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
        
        {/* Timeline at the bottom - Only render when context is ready */}
        {data && data.nodes && data.nodes.length > 0 && isContextReady && (
          <div className={`fixed bottom-0 z-50 transition-all duration-300`}
            style={{
              left: leftPanelCollapsed ? '48px' : '320px',
              right: '48px' // Fixed right margin after removing right panel
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
                }}
                className=""
              />
            </React.Suspense>
          </div>
        )}
        
        {/* Show loading indicator when timeline should be visible but context not ready */}
        {data && data.nodes && data.nodes.length > 0 && !isContextReady && isTimelineVisible && (
          <div className={`fixed bottom-0 z-50 transition-all duration-300`}
            style={{
              left: leftPanelCollapsed ? '48px' : '320px',
              right: '48px', // Fixed right margin after removing right panel
              height: '180px'
            }}
          >
            <div className="h-full bg-background/80 backdrop-blur-sm border-t border-border flex items-center justify-center">
              <div className="text-muted-foreground">Initializing timeline...</div>
            </div>
          </div>
        )}
        
        {/* Node Details Panel - Show when a node is selected (rendered last to be on top) */}
        {selectedNode && (
          <div 
            className="absolute z-[55]" 
            style={{ 
              top: '80px', // Below the nav bar
              right: '60px', // Fixed right margin after removing right panel
              maxHeight: 'calc(100vh - 280px)', // Leave space for nav and timeline
              pointerEvents: 'auto',
              transition: 'right 0.3s ease-in-out'
            }}
          >
            <React.Suspense fallback={<div className="w-96 h-96 bg-background/80 backdrop-blur-sm rounded-lg animate-pulse" />}>
              <NodeDetailsPanel
                node={selectedNode}
                connections={selectedNodeConnections}
                onClose={() => clearAllSelections()}
                onShowNeighbors={handleShowNeighbors}
              />
            </React.Suspense>
          </div>
        )}
      </div>
    </CosmographProvider>
  );
};

export default GraphViz;