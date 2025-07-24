import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Search, Settings, BarChart3, Download, Upload, Maximize2, ZoomIn, ZoomOut, Camera, Filter, Layout, Eye, EyeOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { CosmographProvider } from '@cosmograph/react';
import { useQuery } from '@tanstack/react-query';
import { graphClient } from '../api/graphClient';
import { useGraphConfig } from '../contexts/GraphConfigContext';
import { ControlPanel } from './ControlPanel';
import { SearchBar } from './SearchBar';
import { GraphSearch } from './GraphSearch';
import { GraphCanvas } from './GraphCanvas';
import { NodeDetailsPanel } from './NodeDetailsPanel';
import { LayoutPanel } from './LayoutPanel';
import { FilterPanel } from './FilterPanel';
import { StatsPanel } from './StatsPanel';
import { QuickActions } from './QuickActions';

interface GraphVizProps {
  className?: string;
}

export const GraphViz: React.FC<GraphVizProps> = ({ className }) => {
  const { config } = useGraphConfig();
  const [leftPanelCollapsed, setLeftPanelCollapsed] = useState(false);
  const [rightPanelCollapsed, setRightPanelCollapsed] = useState(false);
  const [selectedNodes, setSelectedNodes] = useState<string[]>([]);
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [highlightedNodes, setHighlightedNodes] = useState<string[]>([]);
  const [showFilterPanel, setShowFilterPanel] = useState(false);
  const [showStatsPanel, setShowStatsPanel] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [isFullscreen, setIsFullscreen] = useState(false);

  const graphCanvasRef = useRef<HTMLDivElement>(null);

  // Fetch graph data from Rust server
  const { data, isLoading, error } = useQuery({
    queryKey: ['graphData', config.queryType, config.nodeLimit],
    queryFn: () => graphClient.getGraphData({ 
      query_type: config.queryType,
      limit: config.nodeLimit 
    }),
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  // Separate filtering and transformation to prevent infinite re-renders (Issue #006)
  const filteredData = React.useMemo(() => {
    if (!data) return { nodes: [], edges: [] };
    
    const visibleNodes = data.nodes.filter(node => {
      const nodeType = node.node_type as keyof typeof config.nodeTypeVisibility;
      return config.nodeTypeVisibility[nodeType] !== false;
    });
    
    const visibleNodeIds = new Set(visibleNodes.map(n => n.id));
    const filteredEdges = data.edges.filter(edge => 
      visibleNodeIds.has(edge.from) && visibleNodeIds.has(edge.to)
    );
    
    return { nodes: visibleNodes, edges: filteredEdges };
  }, [data, config.nodeTypeVisibility]);

  const transformedData = React.useMemo(() => {
    return {
      nodes: filteredData.nodes, // No unnecessary transformation
      links: filteredData.edges.map(edge => ({
        ...edge,
        source: edge.from,
        target: edge.to,
      })),
    };
  }, [filteredData]);

  const handleNodeSelect = (nodeId: string) => {
    if (selectedNodes.includes(nodeId)) {
      setSelectedNodes(selectedNodes.filter(id => id !== nodeId));
    } else {
      setSelectedNodes([...selectedNodes, nodeId]);
    }
  };

  const handleNodeClick = (node: any) => {
    setSelectedNode(node);
  };

  const handleNodeSelectWithCosmograph = (node: any) => {
    // Set React state
    setSelectedNode(node);
    handleNodeSelect(node.id);
    
    // Also select in Cosmograph for visual effects
    if (graphCanvasRef.current && typeof graphCanvasRef.current.selectNode === 'function') {
      graphCanvasRef.current.selectNode(node);
    }
  };

  const handleHighlightNodes = (nodes: any[]) => {
    const nodeIds = nodes.map(node => node.id);
    setHighlightedNodes(nodeIds);
  };

  const handleSelectNodes = (nodes: any[]) => {
    // Select multiple nodes with Cosmograph visual effects
    if (graphCanvasRef.current && typeof graphCanvasRef.current.selectNodes === 'function') {
      graphCanvasRef.current.selectNodes(nodes);
    }
    
    // Update React state - for multiple selection, we'll select the first node for the modal
    // and add all to the selectedNodes array
    if (nodes.length > 0) {
      setSelectedNode(nodes[0]); // Show modal for first node
      const nodeIds = nodes.map(node => node.id);
      setSelectedNodes(nodeIds);
    }
  };

  // Centralized navigation handler to eliminate imperative ref abuse
  const navigationActions = useCallback({
    zoomIn: () => {
      if (graphCanvasRef.current && typeof graphCanvasRef.current.zoomIn === 'function') {
        graphCanvasRef.current.zoomIn();
      }
    },
    zoomOut: () => {
      if (graphCanvasRef.current && typeof graphCanvasRef.current.zoomOut === 'function') {
        graphCanvasRef.current.zoomOut();
      }
    },
    fitView: () => {
      if (graphCanvasRef.current && typeof graphCanvasRef.current.fitView === 'function') {
        graphCanvasRef.current.fitView();
      }
    },
    clearSelection: () => {
      if (graphCanvasRef.current && typeof graphCanvasRef.current.clearSelection === 'function') {
        graphCanvasRef.current.clearSelection();
      }
    }
  }, []);

  // Unified function to clear all selection states and return to default
  const clearAllSelections = useCallback(() => {
    // Only update state if there's actually something to clear
    const hasSelections = selectedNodes.length > 0 || selectedNode !== null || highlightedNodes.length > 0;
    
    if (hasSelections) {
      // Batch state updates to prevent multiple re-renders
      React.startTransition(() => {
        setSelectedNodes([]); // Clear multi-selection
        setSelectedNode(null); // Clear single selection and close modal
        setHighlightedNodes([]); // Clear search highlights
      });
    }
    
    // Use centralized navigation handler
    navigationActions.clearSelection();
  }, [selectedNodes.length, selectedNode?.id, highlightedNodes.length, navigationActions]);

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

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
    <CosmographProvider
      nodes={transformedData.nodes}
      links={transformedData.links}
    >
      <div className={`h-screen w-full flex flex-col bg-background overflow-hidden ${className}`}>
      {/* Top Navigation Bar */}
      <div className="h-16 glass-panel border-b border-border/20 flex items-center justify-between px-6 z-50">
        <div className="flex items-center space-x-4">
          <div className="text-xl font-bold bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
            Graphiti
          </div>
          <Badge variant="secondary" className="text-xs">
            Knowledge Graph
          </Badge>
        </div>

        <div className="flex-1 max-w-2xl mx-8">
          <GraphSearch 
            onNodeSelect={handleNodeSelectWithCosmograph}
            onHighlightNodes={handleHighlightNodes}
            onSelectNodes={handleSelectNodes}
            onClearSelection={clearAllSelections}
            onFilterClick={() => setShowFilterPanel(true)}
            className="w-full"
          />
        </div>

        <div className="flex items-center space-x-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {/* TODO: Implement download */}}
            className="hover:bg-primary/10"
            title="Download Graph"
          >
            <Download className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {/* TODO: Implement upload */}}
            className="hover:bg-primary/10"
            title="Upload Graph"
          >
            <Upload className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {/* TODO: Implement camera */}}
            className="hover:bg-primary/10"
            title="Take Screenshot"
          >
            <Camera className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={navigationActions.zoomOut}
            className="hover:bg-primary/10"
            title="Zoom Out"
          >
            <ZoomOut className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={navigationActions.zoomIn}
            className="hover:bg-primary/10"
            title="Zoom In"
          >
            <ZoomIn className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {/* TODO: Implement layout */}}
            className="hover:bg-primary/10"
            title="Change Layout"
          >
            <Layout className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setLeftPanelCollapsed(!leftPanelCollapsed)}
            className="hover:bg-primary/10"
            title="Settings"
          >
            <Settings className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowStatsPanel(true)}
            className="hover:bg-primary/10"
            title="Statistics"
          >
            <BarChart3 className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleFullscreen}
            className="hover:bg-primary/10"
            title="Fullscreen"
          >
            <Maximize2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Control Panel */}
        <div className={`${leftPanelCollapsed ? 'w-12' : 'w-80'} transition-all duration-300 flex-shrink-0`}>
          <ControlPanel 
            collapsed={leftPanelCollapsed}
            onToggleCollapse={() => setLeftPanelCollapsed(!leftPanelCollapsed)}
          />
        </div>

        {/* Main Graph Viewport */}
        <div className="flex-1 relative">
          <GraphCanvas 
            ref={graphCanvasRef}
            onNodeClick={handleNodeClick}
            onNodeSelect={handleNodeSelect}
            onClearSelection={clearAllSelections}
            selectedNodes={selectedNodes}
            highlightedNodes={highlightedNodes}
            stats={data?.stats}
            className="h-full w-full"
          />
          
          {/* Node Details Panel Overlay */}
          {selectedNode && (
            <div className="absolute top-4 right-4 w-96 animate-slide-in-right">
              <NodeDetailsPanel 
                node={selectedNode}
                onClose={clearAllSelections}
              />
            </div>
          )}

          {/* Quick Actions Toolbar */}
          <div className="absolute bottom-6 left-1/2 transform -translate-x-1/2">
            <QuickActions 
              selectedCount={selectedNodes.length}
              onClearSelection={clearAllSelections}
              onFitToScreen={navigationActions.fitView}
              onZoomIn={navigationActions.zoomIn}
              onZoomOut={navigationActions.zoomOut}
              onScreenshot={() => {
                // TODO: Implement screenshot functionality
              }}
            />
          </div>
        </div>

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
        />
      )}

      {showStatsPanel && (
        <StatsPanel 
          isOpen={showStatsPanel}
          onClose={() => setShowStatsPanel(false)}
        />
      )}
      </div>
    </CosmographProvider>
  );
};

export default GraphViz;