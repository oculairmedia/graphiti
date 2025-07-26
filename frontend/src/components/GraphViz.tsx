import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Search, Settings, BarChart3, Download, Upload, Maximize2, ZoomIn, ZoomOut, Camera, Filter, Layout, Eye, EyeOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { useQuery } from '@tanstack/react-query';
import { graphClient } from '../api/graphClient';
import { GraphNode } from '../api/types';
import type { GraphData } from '../types/graph';
import { logger } from '../utils/logger';
import GraphErrorBoundary from './GraphErrorBoundary';

// Import the handle interface from GraphCanvas
interface GraphCanvasHandle {
  clearSelection: () => void;
  selectNode: (node: GraphNode) => void;
  selectNodes: (nodes: GraphNode[]) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
}
import { useGraphConfig } from '../contexts/GraphConfigContext';
import { ControlPanel } from './ControlPanel';
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
  const { config, applyLayout, zoomIn, zoomOut, fitView, updateNodeTypeConfigurations } = useGraphConfig();
  
  // Add debug logging for button clicks
  const handleZoomIn = useCallback(() => {
    console.log('🔵 GraphViz: Zoom In button clicked');
    console.log('🔵 zoomIn function exists:', typeof zoomIn === 'function');
    zoomIn();
  }, [zoomIn]);
  
  const handleZoomOut = useCallback(() => {
    console.log('🔵 GraphViz: Zoom Out button clicked');
    console.log('🔵 zoomOut function exists:', typeof zoomOut === 'function');
    zoomOut();
  }, [zoomOut]);
  
  const handleFitView = useCallback(() => {
    console.log('🔵 GraphViz: Fit View button clicked');
    console.log('🔵 fitView function exists:', typeof fitView === 'function');
    fitView();
  }, [fitView]);
  const [leftPanelCollapsed, setLeftPanelCollapsed] = useState(false);
  const [rightPanelCollapsed, setRightPanelCollapsed] = useState(false);
  const [selectedNodes, setSelectedNodes] = useState<string[]>([]);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [highlightedNodes, setHighlightedNodes] = useState<string[]>([]);
  const [showFilterPanel, setShowFilterPanel] = useState(false);
  const [showStatsPanel, setShowStatsPanel] = useState(false);
  const [showLayoutPanel, setShowLayoutPanel] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [isFullscreen, setIsFullscreen] = useState(false);

  const graphCanvasRef = useRef<GraphCanvasHandle>(null);

  // Fetch graph data from Rust server
  const { data, isLoading, error } = useQuery({
    queryKey: ['graphData', config.queryType, config.nodeLimit],
    queryFn: () => graphClient.getGraphData({ 
      query_type: config.queryType,
      limit: config.nodeLimit 
    }),
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  // Enhanced filtering logic with virtualization for large graphs
  const filteredData = React.useMemo(() => {
    if (!data) return { nodes: [], edges: [] };
    
    const visibleNodes = data.nodes.filter(node => {
      // Basic node type visibility check
      const nodeType = node.node_type as keyof typeof config.nodeTypeVisibility;
      if (config.nodeTypeVisibility[nodeType] === false) return false;
      
      // Advanced filter checks from FilterPanel
      
      // Node type filter
      if (!config.filteredNodeTypes.includes(node.node_type)) return false;
      
      // Degree centrality filter
      const degree = node.properties?.degree_centrality || 0;
      const degreePercent = Math.min((degree / 100) * 100, 100); // Normalize to 0-100
      if (degreePercent < config.minDegree || degreePercent > config.maxDegree) return false;
      
      // PageRank filter
      const pagerank = node.properties?.pagerank_centrality || node.properties?.pagerank || 0;
      const pagerankPercent = Math.min((pagerank / 0.1) * 100, 100); // Normalize to 0-100
      if (pagerankPercent < config.minPagerank || pagerankPercent > config.maxPagerank) return false;
      
      // Connection count filter
      const connections = node.properties?.degree || node.properties?.connections || 0;
      if (connections < config.minConnections || connections > config.maxConnections) return false;
      
      // Date range filter
      if (config.startDate || config.endDate) {
        const nodeDate = node.created_at || node.properties?.created || node.properties?.date;
        if (nodeDate) {
          const date = new Date(nodeDate);
          if (config.startDate && date < new Date(config.startDate)) return false;
          if (config.endDate && date > new Date(config.endDate)) return false;
        }
      }
      
      return true;
    });

    // Virtualization: For very large graphs (>10k nodes), prioritize most important nodes
    let finalNodes = visibleNodes;
    const LARGE_GRAPH_THRESHOLD = 10000;
    const MAX_RENDERED_NODES = 5000;

    if (visibleNodes.length > LARGE_GRAPH_THRESHOLD) {
      logger.log(`Large graph detected: ${visibleNodes.length} nodes. Applying virtualization.`);
      
      // Calculate importance score for each node
      const nodesWithScore = visibleNodes.map(node => {
        const degree = node.properties?.degree_centrality || 0;
        const pagerank = node.properties?.pagerank_centrality || node.properties?.pagerank || 0;
        const betweenness = node.properties?.betweenness_centrality || 0;
        
        // Composite importance score (weighted combination)
        const importanceScore = (degree * 0.4) + (pagerank * 1000 * 0.4) + (betweenness * 0.2);
        
        return { node, importanceScore };
      });

      // Sort by importance and take top N nodes
      nodesWithScore.sort((a, b) => b.importanceScore - a.importanceScore);
      finalNodes = nodesWithScore
        .slice(0, MAX_RENDERED_NODES)
        .map(item => item.node);
        
      logger.log(`Virtualization applied: reduced from ${visibleNodes.length} to ${finalNodes.length} nodes`);
    }
    
    const visibleNodeIds = new Set(finalNodes.map(n => n.id));
    const filteredEdges = data.edges.filter(edge => 
      visibleNodeIds.has(edge.from) && visibleNodeIds.has(edge.to)
    );
    
    return { nodes: finalNodes, edges: filteredEdges };
  }, [
    data, 
    config.nodeTypeVisibility, 
    config.filteredNodeTypes,
    config.minDegree,
    config.maxDegree,
    config.minPagerank,
    config.maxPagerank,
    config.minConnections,
    config.maxConnections,
    config.startDate,
    config.endDate
  ]);

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

  // Update node type configurations when data changes
  React.useEffect(() => {
    if (data?.nodes && data.nodes.length > 0) {
      const nodeTypes = [...new Set(data.nodes.map(node => node.node_type).filter(Boolean))];
      if (nodeTypes.length > 0) {
        updateNodeTypeConfigurations(nodeTypes);
      }
    }
  }, [data, updateNodeTypeConfigurations]);

  const handleNodeSelect = (nodeId: string) => {
    if (selectedNodes.includes(nodeId)) {
      setSelectedNodes(selectedNodes.filter(id => id !== nodeId));
    } else {
      setSelectedNodes([...selectedNodes, nodeId]);
    }
  };

  const handleNodeClick = (node: GraphNode) => {
    setSelectedNode(node);
  };

  const handleNodeSelectWithCosmograph = (node: GraphNode) => {
    // Set React state
    setSelectedNode(node);
    handleNodeSelect(node.id);
    
    // Also select in Cosmograph for visual effects
    if (graphCanvasRef.current && typeof graphCanvasRef.current.selectNode === 'function') {
      graphCanvasRef.current.selectNode(node);
    }
  };

  const handleHighlightNodes = (nodes: GraphNode[]) => {
    const nodeIds = nodes.map(node => node.id);
    setHighlightedNodes(nodeIds);
  };

  const handleSelectNodes = (nodes: GraphNode[]) => {
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

  const handleShowNeighbors = (nodeId: string) => {
    // Start with nodes to explore - if we have highlighted nodes, use all of them
    // Otherwise, just use the clicked node
    const nodesToExplore = highlightedNodes.length > 0 ? highlightedNodes : [nodeId];
    const newNeighborIds = new Set<string>();
    
    // Find neighbors for all nodes we're exploring
    nodesToExplore.forEach(currentNodeId => {
      transformedData.links.forEach(edge => {
        if (edge.source === currentNodeId) {
          newNeighborIds.add(edge.target);
        } else if (edge.target === currentNodeId) {
          newNeighborIds.add(edge.source);
        }
      });
    });
    
    // Remove nodes we're already exploring to get only NEW neighbors
    nodesToExplore.forEach(id => newNeighborIds.delete(id));
    
    // Find the actual neighbor nodes from our data
    const newNeighborNodes = transformedData.nodes.filter(node => 
      newNeighborIds.has(node.id)
    );
    
    if (newNeighborNodes.length > 0) {
      // Combine existing highlighted nodes with new neighbors
      const allHighlightedIds = [...new Set([...nodesToExplore, ...Array.from(newNeighborIds)])];
      setHighlightedNodes(allHighlightedIds);
      
      // Select all highlighted nodes with visual effects
      const allHighlightedNodes = transformedData.nodes.filter(node => 
        allHighlightedIds.includes(node.id)
      );
      
      if (graphCanvasRef.current && typeof graphCanvasRef.current.selectNodes === 'function') {
        graphCanvasRef.current.selectNodes(allHighlightedNodes);
      }
      
      const isExpanding = highlightedNodes.length > 0;
      logger.log(
        isExpanding 
          ? `Expanded network: found ${newNeighborNodes.length} new neighbors. Total nodes: ${allHighlightedIds.length}`
          : `Found ${newNeighborNodes.length} neighbors for node ${nodeId}:`, 
        newNeighborNodes.map(n => n.label || n.id)
      );
    } else {
      const isExpanding = highlightedNodes.length > 0;
      logger.log(
        isExpanding 
          ? `No new neighbors found. Network expansion complete with ${nodesToExplore.length} nodes.`
          : `No neighbors found for node ${nodeId}`
      );
    }
  };

  // Navigation actions now use GraphConfigContext directly (no ref chains)

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
    
    // Clear GraphCanvas selection using direct ref (only for clearing)
    if (graphCanvasRef.current && typeof graphCanvasRef.current.clearSelection === 'function') {
      graphCanvasRef.current.clearSelection();
    }
  }, [selectedNodes.length, selectedNode?.id, highlightedNodes.length]);

  const handleLayoutChange = useCallback((layoutType: string) => {
    if (filteredData && filteredData.nodes.length > 0) {
      applyLayout(layoutType, {}, { nodes: filteredData.nodes, edges: filteredData.edges });
    }
  }, [applyLayout, filteredData]);

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  const handleDownloadGraph = () => {
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
  };

  const handleCaptureScreenshot = async () => {
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
      logger.warn('Screenshot capture failed:', error);
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
          {data && data.nodes.length > 10000 && (
            <Badge variant="outline" className="text-xs border-warning text-warning">
              Virtualized ({filteredData.nodes.length.toLocaleString()}/{data.nodes.length.toLocaleString()})
            </Badge>
          )}
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
            onClick={handleDownloadGraph}
            className="hover:bg-primary/10"
            title="Download Graph"
          >
            <Download className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {/* Upload functionality would require file input */}}
            disabled
            className="hover:bg-primary/10"
            title="Upload Graph"
          >
            <Upload className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleCaptureScreenshot}
            className="hover:bg-primary/10"
            title="Take Screenshot"
          >
            <Camera className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleZoomOut}
            className="hover:bg-primary/10"
            title="Zoom Out"
          >
            <ZoomOut className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleZoomIn}
            className="hover:bg-primary/10"
            title="Zoom In"
          >
            <ZoomIn className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowLayoutPanel(true)}
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
            onLayoutChange={handleLayoutChange}
          />
        </div>

        {/* Main Graph Viewport */}
        <div className="flex-1 relative">
          <GraphErrorBoundary>
            <GraphCanvas 
              ref={graphCanvasRef}
              nodes={transformedData.nodes}
              links={transformedData.links}
              onNodeClick={handleNodeClick}
              onNodeSelect={handleNodeSelect}
              onClearSelection={clearAllSelections}
              selectedNodes={selectedNodes}
              highlightedNodes={highlightedNodes}
              stats={data?.stats}
              className="h-full w-full"
            />
          </GraphErrorBoundary>
          
          {/* Node Details Panel Overlay */}
          {selectedNode && (
            <div className="absolute top-4 right-4 w-96 animate-slide-in-right">
              <NodeDetailsPanel 
                node={selectedNode}
                onClose={clearAllSelections}
                onShowNeighbors={handleShowNeighbors}
              />
            </div>
          )}

          {/* Quick Actions Toolbar */}
          <div className="absolute bottom-6 left-1/2 transform -translate-x-1/2">
            <QuickActions 
              selectedCount={selectedNodes.length}
              onClearSelection={clearAllSelections}
              onFitToScreen={handleFitView}
              onZoomIn={handleZoomIn}
              onZoomOut={handleZoomOut}
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
      </div>
  );
};

export default GraphViz;