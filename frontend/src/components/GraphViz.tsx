import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { useStableCallback } from '../hooks/useStableCallback';
import { CosmographProvider } from '@cosmograph/react';
import { useGraphConfig } from '../contexts/GraphConfigProvider';
import { ControlPanel } from './ControlPanel';
import { GraphViewport } from './GraphViewport';
import { LayoutPanel } from './LayoutPanel';
import { FilterPanel } from './FilterPanel';
import { StatsPanel } from './StatsPanel';
import { GraphTimeline, GraphTimelineHandle } from './GraphTimeline';
import { GraphNavBar } from './GraphNavBar';
import { useGraphDataQuery } from '../hooks/useGraphDataQuery';
import { useNodeSelection } from '../hooks/useNodeSelection';
import { useIncrementalUpdates } from '../hooks/useIncrementalUpdates';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import type { GraphCanvasHandle, GraphVizProps } from '../types/components';
import { getErrorMessage } from '../types/errors';

export const GraphViz: React.FC<GraphVizProps> = ({ className }) => {
  const { applyLayout, zoomIn, zoomOut, fitView } = useGraphConfig();
  
  // UI State
  const [leftPanelCollapsed, setLeftPanelCollapsed] = useState(false);
  const [rightPanelCollapsed, setRightPanelCollapsed] = useState(false);
  const [showFilterPanel, setShowFilterPanel] = useState(false);
  const [showStatsPanel, setShowStatsPanel] = useState(false);
  const [showLayoutPanel, setShowLayoutPanel] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isSimulationRunning, setIsSimulationRunning] = useState(true);

  // Refs
  const graphCanvasRef = useRef<GraphCanvasHandle>(null);
  const timelineRef = useRef<GraphTimelineHandle>(null);
  const stableGraphPropsRef = useRef<{ nodes: GraphNode[], links: GraphLink[] } | null>(null);

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

  // Handle loading state
  if (isLoading) {
    return (
      <div className={`h-screen w-full flex items-center justify-center bg-background ${className}`}>
        <div className="text-muted-foreground text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mb-4 mx-auto"></div>
          <p>Loading graph data...</p>
        </div>
      </div>
    );
  }

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

  return (
    <CosmographProvider>
      <div className={`h-screen w-full flex flex-col bg-background overflow-hidden ${className}`}>
        {/* Top Navigation Bar */}
        <GraphNavBar
          totalNodes={data?.nodes.length || 0}
          visibleNodes={transformedData.nodes.length}
          isVirtualized={data && data.nodes.length > 10000}
          isSimulationRunning={isSimulationRunning}
          selectedNodes={data?.nodes || []}
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
            />
          </div>

          {/* Main Graph Viewport */}
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
          />

          {/* Right Layout Panel */}
          <div className={`${rightPanelCollapsed ? 'w-12' : 'w-80'} transition-all duration-300 flex-shrink-0`}>
            <LayoutPanel 
              collapsed={rightPanelCollapsed}
              onToggleCollapse={() => setRightPanelCollapsed(!rightPanelCollapsed)}
            />
          </div>
        </div>

        {/* Modal Panels */}
        {showFilterPanel && (
          <FilterPanel 
            isOpen={showFilterPanel}
            onClose={() => setShowFilterPanel(false)}
            data={data}
          />
        )}

        {showStatsPanel && (
          <StatsPanel 
            isOpen={showStatsPanel}
            onClose={() => setShowStatsPanel(false)}
            data={data}
          />
        )}
        
        {/* Timeline at the bottom */}
        {data && (
          <div className={`fixed bottom-0 z-50 transition-all duration-300`}
            style={{
              left: leftPanelCollapsed ? '48px' : '320px',
              right: rightPanelCollapsed ? '48px' : '320px'
            }}
          >
            <GraphTimeline 
              ref={timelineRef}
              onTimeRangeChange={(range) => {
                // Handle timeline range changes
              }}
              className=""
            />
          </div>
        )}
      </div>
    </CosmographProvider>
  );
};

export default GraphViz;