import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Search, Settings, BarChart3, Download, Upload, Maximize2, ZoomIn, ZoomOut, Camera, Filter, Layout, Eye, EyeOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { useQuery } from '@tanstack/react-query';
import { CosmographProvider } from '@cosmograph/react';
import { graphClient } from '../api/graphClient';
import { GraphNode } from '../api/types';
import type { GraphData, GraphLink } from '../types/graph';
import { logger } from '../utils/logger';
import GraphErrorBoundary from './GraphErrorBoundary';
import { useGraphDataDiff } from '../hooks/useGraphDataDiff';

// Import the handle interface from GraphCanvas
interface GraphCanvasHandle {
  clearSelection: () => void;
  selectNode: (node: GraphNode) => void;
  selectNodes: (nodes: GraphNode[]) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
  zoomToPoint: (index: number, duration?: number, scale?: number, canZoomOut?: boolean) => void;
  trackPointPositionsByIndices: (indices: number[]) => void;
  getTrackedPointPositionsMap: () => Map<number, [number, number]> | undefined;
  setData: (nodes: GraphNode[], links: GraphLink[], runSimulation?: boolean) => void;
  restart: () => void;
  // Incremental update methods
  addIncrementalData: (newNodes: GraphNode[], newLinks: GraphLink[], runSimulation?: boolean) => void;
  updateNodes: (updatedNodes: GraphNode[]) => void;
  updateLinks: (updatedLinks: GraphLink[]) => void;
  removeNodes: (nodeIds: string[]) => void;
  removeLinks: (linkIds: string[]) => void;
  // Simulation control methods
  startSimulation: (alpha?: number) => void;
  pauseSimulation: () => void;
  resumeSimulation: () => void;
  keepSimulationRunning: (enable: boolean) => void;
  // External incremental flag control
  setIncrementalUpdateFlag: (enabled: boolean) => void;
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
    zoomIn();
  }, [zoomIn]);
  
  const handleZoomOut = useCallback(() => {
    zoomOut();
  }, [zoomOut]);
  
  const handleFitView = useCallback(() => {
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

  // Stable data references to prevent cascade re-renders during incremental updates
  const stableDataRef = useRef<{ nodes: GraphNode[], edges: GraphLink[] } | null>(null);
  const [isIncrementalUpdate, setIsIncrementalUpdate] = useState(false);
  const [isGraphInitialized, setIsGraphInitialized] = useState(false);
  
  // Stable props for GraphCanvas to prevent re-renders during incremental updates
  const stableGraphPropsRef = useRef<{ nodes: GraphNode[], links: GraphLink[] } | null>(null);

  // Fetch graph data from Rust server
  const { data, isLoading, error } = useQuery({
    queryKey: ['graphData', config.queryType, config.nodeLimit],
    queryFn: () => graphClient.getGraphData({ 
      query_type: config.queryType,
      limit: config.nodeLimit 
    }),
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  // Use data diffing to detect changes
  const dataDiff = useGraphDataDiff(data || null);
  
  // Handle initial load separately from incremental updates
  useEffect(() => {
    if (dataDiff.isInitialLoad && !isGraphInitialized) {
      setIsGraphInitialized(true);
      // Store initial stable data reference
      if (data) {
        stableDataRef.current = { nodes: [...data.nodes], edges: [...data.edges] };
      }
    }
  }, [dataDiff.isInitialLoad, isGraphInitialized, data]);

  // Reset incremental update flag when appropriate
  useEffect(() => {
    // Reset incremental update flag when we get a completely new dataset
    if (data && !dataDiff.hasChanges && isIncrementalUpdate) {
      setIsIncrementalUpdate(false);
    }
  }, [data, dataDiff.hasChanges, isIncrementalUpdate]);

  // Handle incremental updates when changes are detected (skip initial loads)
  useEffect(() => {
    // Skip if no changes, no ref available, initial load, or graph not initialized
    if (!dataDiff.hasChanges || !graphCanvasRef.current || dataDiff.isInitialLoad || !isGraphInitialized) {
      if (dataDiff.isInitialLoad) {
      }
      return;
    }

    // Ensure we have stable data from previous state
    if (!stableDataRef.current) {
      return;
    }

    const applyIncrementalUpdates = async () => {
      
      // Set flags BEFORE triggering React re-render to prevent Data Kit processing
      if (graphCanvasRef.current?.setIncrementalUpdateFlag) {
        graphCanvasRef.current.setIncrementalUpdateFlag(true);
      }
      
      setIsIncrementalUpdate(true);

      try {
        // Apply changes in order: removals first, then updates, then additions
        if (dataDiff.removedNodeIds.length > 0) {
          await graphCanvasRef.current!.removeNodes(dataDiff.removedNodeIds);
        }

        if (dataDiff.removedLinkIds.length > 0) {
          await graphCanvasRef.current!.removeLinks(dataDiff.removedLinkIds);
        }

        if (dataDiff.updatedNodes.length > 0) {
          await graphCanvasRef.current!.updateNodes(dataDiff.updatedNodes);
        }

        if (dataDiff.updatedLinks.length > 0) {
          await graphCanvasRef.current!.updateLinks(dataDiff.updatedLinks);
        }

        if (dataDiff.addedNodes.length > 0 || dataDiff.addedLinks.length > 0) {
          // Transform added links to have source/target format
          const transformedAddedLinks = dataDiff.addedLinks.map(link => ({
            ...link,
            source: link.from,
            target: link.to
          }));
          
          await graphCanvasRef.current!.addIncrementalData(
            dataDiff.addedNodes, 
            transformedAddedLinks, 
            false // Don't restart simulation for small additions
          );
          
          // Resume simulation after incremental data changes, with proper timing
          setTimeout(() => {
            if (graphCanvasRef.current?.resumeSimulation) {
              graphCanvasRef.current.resumeSimulation();
            }
          }, 100); // Small delay to ensure component has updated
        }

        // Update stable data reference
        if (data) {
          stableDataRef.current = { nodes: [...data.nodes], edges: [...data.edges] };
        }

      } catch (error) {
        // Fallback to full reload on error
        setIsIncrementalUpdate(false);
      } finally {
        // Flag will be reset when the next real data change occurs
      }
    };

    applyIncrementalUpdates();
  }, [dataDiff.hasChanges, dataDiff.changeCount, dataDiff.isInitialLoad, isGraphInitialized, data]);

  // Enhanced filtering logic with virtualization for large graphs
  // Create stable filter config to prevent unnecessary recalculations
  const filterConfig = React.useMemo(() => ({
    nodeTypeVisibility: config.nodeTypeVisibility,
    filteredNodeTypes: config.filteredNodeTypes,
    minDegree: config.minDegree,
    maxDegree: config.maxDegree,
    minPagerank: config.minPagerank,
    maxPagerank: config.maxPagerank,
    minBetweenness: config.minBetweenness,
    maxBetweenness: config.maxBetweenness,
    minEigenvector: config.minEigenvector,
    maxEigenvector: config.maxEigenvector,
    minConnections: config.minConnections,
    maxConnections: config.maxConnections,
    startDate: config.startDate,
    endDate: config.endDate
  }), [
    config.nodeTypeVisibility,
    config.filteredNodeTypes,
    config.minDegree,
    config.maxDegree,
    config.minPagerank,
    config.maxPagerank,
    config.minBetweenness,
    config.maxBetweenness,
    config.minEigenvector,
    config.maxEigenvector,
    config.minConnections,
    config.maxConnections,
    config.startDate,
    config.endDate
  ]);

  const filteredData = React.useMemo(() => {
    // During incremental updates, use stable data to prevent cascade re-renders
    const sourceData = isIncrementalUpdate ? stableDataRef.current : data;
    
    if (!sourceData) return { nodes: [], edges: [] };
    
    
    const visibleNodes = sourceData.nodes.filter(node => {
      // Basic node type visibility check
      const nodeType = node.node_type as keyof typeof filterConfig.nodeTypeVisibility;
      if (filterConfig.nodeTypeVisibility[nodeType] === false) return false;
      
      // Advanced filter checks from FilterPanel
      
      // Node type filter - only apply if we have filtered types configured
      if (filterConfig.filteredNodeTypes.length > 0 && !filterConfig.filteredNodeTypes.includes(node.node_type)) return false;
      
      // Degree centrality filter
      const degree = node.properties?.degree_centrality || 0;
      const degreePercent = Math.min((degree / 100) * 100, 100); // Normalize to 0-100
      if (degreePercent < filterConfig.minDegree || degreePercent > filterConfig.maxDegree) return false;
      
      // PageRank filter
      const pagerank = node.properties?.pagerank_centrality || node.properties?.pagerank || 0;
      const pagerankPercent = Math.min((pagerank / 0.1) * 100, 100); // Normalize to 0-100
      if (pagerankPercent < filterConfig.minPagerank || pagerankPercent > filterConfig.maxPagerank) return false;
      
      // Betweenness centrality filter
      const betweenness = node.properties?.betweenness_centrality || 0;
      const betweennessPercent = Math.min((betweenness / 1) * 100, 100); // Normalize to 0-100
      if (betweennessPercent < filterConfig.minBetweenness || betweennessPercent > filterConfig.maxBetweenness) return false;
      
      // Eigenvector centrality filter
      const eigenvector = node.properties?.eigenvector_centrality || 0;
      const eigenvectorPercent = Math.min((eigenvector / 1) * 100, 100); // Normalize to 0-100
      if (eigenvectorPercent < filterConfig.minEigenvector || eigenvectorPercent > filterConfig.maxEigenvector) return false;
      
      // Connection count filter
      const connections = node.properties?.degree || node.properties?.connections || 0;
      if (connections < filterConfig.minConnections || connections > filterConfig.maxConnections) return false;
      
      // Date range filter
      if (filterConfig.startDate || filterConfig.endDate) {
        const nodeDate = node.created_at || node.properties?.created || node.properties?.date;
        if (nodeDate) {
          const date = new Date(nodeDate);
          if (filterConfig.startDate && date < new Date(filterConfig.startDate)) return false;
          if (filterConfig.endDate && date > new Date(filterConfig.endDate)) return false;
        }
      }
      
      return true;
    });

    // Virtualization: For very large graphs (>10k nodes), prioritize most important nodes
    let finalNodes = visibleNodes;
    const LARGE_GRAPH_THRESHOLD = 10000;
    const MAX_RENDERED_NODES = 5000;

    if (visibleNodes.length > LARGE_GRAPH_THRESHOLD) {
      
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
        
    }
    
    const visibleNodeIds = new Set(finalNodes.map(n => n.id));
    const filteredEdges = sourceData.edges.filter(edge => 
      visibleNodeIds.has(edge.from) && visibleNodeIds.has(edge.to)
    );
    
    return { nodes: finalNodes, edges: filteredEdges };
  }, [data, isIncrementalUpdate, filterConfig]);

  // Create a stable reference that never changes during incremental updates
  const stableTransformedDataRef = useRef<{ nodes: GraphNode[], links: GraphLink[] } | null>(null);
  
  const transformedData = React.useMemo(() => {
    // During incremental updates, return the exact same object reference
    if (isIncrementalUpdate && stableTransformedDataRef.current) {
      return stableTransformedDataRef.current;
    }
    
    const newTransformedData = {
      nodes: filteredData.nodes,
      links: filteredData.edges.map(edge => ({
        ...edge,
        source: edge.from,
        target: edge.to,
      })),
    };
    
    // Update stable reference when not in incremental mode
    if (!isIncrementalUpdate) {
      stableTransformedDataRef.current = newTransformedData;
    }
    
    return newTransformedData;
  }, [filteredData, isIncrementalUpdate]);

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
      
    } else {
      // No neighbors found
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
      // Screenshot capture failed
    }
  };

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
      stableDataRef.current = null;
      stableGraphPropsRef.current = null;
      stableTransformedDataRef.current = null;
      
      // Clear any pending operations
      if (graphCanvasRef.current) {
        graphCanvasRef.current = null;
      }
    };
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
    <CosmographProvider>
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
            nodes={data?.nodes || []}
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
            {(() => {
              // Use stable props for data during incremental updates, but allow simulation state to update
              const dataToUse = isIncrementalUpdate && stableGraphPropsRef.current 
                ? stableGraphPropsRef.current 
                : transformedData;
              
              // Update stable props when not in incremental update mode
              if (!isIncrementalUpdate) {
                stableGraphPropsRef.current = {
                  nodes: transformedData.nodes,
                  links: transformedData.links
                };
              }
              
              return (
                <GraphCanvas 
                  ref={graphCanvasRef}
                  nodes={dataToUse.nodes}
                  links={dataToUse.links}
                  onNodeClick={handleNodeClick}
                  onNodeSelect={handleNodeSelect}
                  onClearSelection={clearAllSelections}
                  selectedNodes={selectedNodes}
                  highlightedNodes={highlightedNodes}
                  stats={data?.stats}
                  className="h-full w-full"
                />
              );
            })()}
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
    </CosmographProvider>
  );
};

export default GraphViz;