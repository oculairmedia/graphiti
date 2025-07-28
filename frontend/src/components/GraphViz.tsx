import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Search, Settings, BarChart3, Download, Upload, Maximize2, ZoomIn, ZoomOut, Camera, Filter, Layout, Eye, EyeOff, Play, Pause } from 'lucide-react';
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
  fitViewByIndices: (indices: number[], duration?: number, padding?: number) => void;
  zoomToPoint: (index: number, duration?: number, scale?: number, canZoomOut?: boolean) => void;
  trackPointPositionsByIndices: (indices: number[]) => void;
  getTrackedPointPositionsMap: () => Map<number, [number, number]> | undefined;
  setData: (nodes: GraphNode[], links: GraphLink[], runSimulation?: boolean) => void;
  restart: () => void;
  // Selection tools
  activateRectSelection: () => void;
  deactivateRectSelection: () => void;
  activatePolygonalSelection: () => void;
  deactivatePolygonalSelection: () => void;
  selectPointsInRect: (selection: [[number, number], [number, number]] | null, addToSelection?: boolean) => void;
  selectPointsInPolygon: (polygonPoints: [number, number][], addToSelection?: boolean) => void;
  getConnectedPointIndices: (index: number) => number[] | undefined;
  // Search methods
  getPointIndicesByExactValues: (keyValues: Record<string, unknown>) => number[] | undefined;
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
import { useGraphConfig } from '../contexts/GraphConfigProvider';
import { ControlPanel } from './ControlPanel';
import { GraphSearch } from './GraphSearch';
import { GraphCanvas } from './GraphCanvas';
import { NodeDetailsPanel } from './NodeDetailsPanel';
import { LayoutPanel } from './LayoutPanel';
import { FilterPanel } from './FilterPanel';
import { StatsPanel } from './StatsPanel';
import { QuickActions } from './QuickActions';
import { GraphTimeline, GraphTimelineHandle } from './GraphTimeline';

interface GraphVizProps {
  className?: string;
}

export const GraphViz: React.FC<GraphVizProps> = ({ className }) => {
  const { config, applyLayout, zoomIn, zoomOut, fitView, updateNodeTypeConfigurations } = useGraphConfig();
  
  // Add debug logging for button clicks
  const handleZoomIn = useCallback(() => {
    console.log('GraphViz: handleZoomIn called');
    zoomIn();
  }, [zoomIn]);
  
  const handleZoomOut = useCallback(() => {
    console.log('GraphViz: handleZoomOut called');
    zoomOut();
  }, [zoomOut]);
  
  const handleFitView = useCallback(() => {
    console.log('GraphViz: handleFitView called');
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
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [hoveredConnectedNodes, setHoveredConnectedNodes] = useState<string[]>([]);
  const [isSimulationRunning, setIsSimulationRunning] = useState(true);

  const graphCanvasRef = useRef<GraphCanvasHandle>(null);
  const timelineRef = useRef<GraphTimelineHandle>(null);

  // Stable data references to prevent cascade re-renders during incremental updates
  const stableDataRef = useRef<{ nodes: GraphNode[], edges: GraphLink[] } | null>(null);
  const [isIncrementalUpdate, setIsIncrementalUpdate] = useState(false);
  const [isGraphInitialized, setIsGraphInitialized] = useState(false);
  
  // Stable props for GraphCanvas to prevent re-renders during incremental updates
  const stableGraphPropsRef = useRef<{ nodes: GraphNode[], links: GraphLink[] } | null>(null);

  // Fetch graph data from Rust server
  const { data, isLoading, error } = useQuery({
    queryKey: ['graphData', config.queryType, config.nodeLimit],
    queryFn: async () => {
      const result = await graphClient.getGraphData({ 
        query_type: config.queryType,
        limit: config.nodeLimit 
      });
      // Debug: log a sample of the data structure
      if (result && result.nodes && result.nodes.length > 0) {
        logger.log('Sample node data:', result.nodes[0]);
        logger.log('Node properties:', result.nodes[0].properties);
        // Find nodes with temporal data
        const nodesWithDates = result.nodes.filter((n: any) => 
          n.created_at || n.properties?.created_at || n.properties?.created || 
          n.properties?.date || n.properties?.timestamp
        );
        logger.log(`Nodes with temporal data: ${nodesWithDates.length}/${result.nodes.length}`);
        if (nodesWithDates.length > 0) {
          logger.log('Sample node with date:', nodesWithDates[0]);
        }
        logger.log('Sample edge data:', result.edges && result.edges[0]);
      }
      return result;
    },
    // Disabled auto-refetch to improve performance
    // refetchInterval: 30000, // Refresh every 30 seconds
  });

  // Use data diffing to detect changes
  const dataDiff = useGraphDataDiff(data || null);
  
  // Debug logging
  useEffect(() => {
    logger.log('GraphViz: Query state', { isLoading, hasData: !!data, error: error?.message });
    if (data) {
      logger.log('GraphViz: Data loaded', { nodes: data.nodes?.length, edges: data.edges?.length });
    }
  }, [isLoading, data, error]);
  
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

  // Memoize filter function to prevent recreation
  const nodePassesFilters = React.useCallback((node: GraphNode, filterConfig: any) => {
    // Basic node type visibility check
    const nodeType = node.node_type as keyof typeof filterConfig.nodeTypeVisibility;
    if (filterConfig.nodeTypeVisibility[nodeType] === false) return false;
    
    // Node type filter - only apply if we have filtered types configured
    if (filterConfig.filteredNodeTypes.length > 0 && !filterConfig.filteredNodeTypes.includes(node.node_type)) return false;
    
    // Skip metric filters if all at default values
    const hasMetricFilters = filterConfig.minDegree > 0 || filterConfig.maxDegree < 100 ||
                           filterConfig.minPagerank > 0 || filterConfig.maxPagerank < 100 ||
                           filterConfig.minBetweenness > 0 || filterConfig.maxBetweenness < 100 ||
                           filterConfig.minEigenvector > 0 || filterConfig.maxEigenvector < 100;
    
    if (hasMetricFilters) {
      // Degree centrality filter
      const degree = node.properties?.degree_centrality || 0;
      const degreePercent = Math.min((degree / 100) * 100, 100);
      if (degreePercent < filterConfig.minDegree || degreePercent > filterConfig.maxDegree) return false;
      
      // PageRank filter
      const pagerank = node.properties?.pagerank_centrality || node.properties?.pagerank || 0;
      const pagerankPercent = Math.min((pagerank / 0.1) * 100, 100);
      if (pagerankPercent < filterConfig.minPagerank || pagerankPercent > filterConfig.maxPagerank) return false;
      
      // Betweenness centrality filter
      const betweenness = node.properties?.betweenness_centrality || 0;
      const betweennessPercent = Math.min((betweenness / 1) * 100, 100);
      if (betweennessPercent < filterConfig.minBetweenness || betweennessPercent > filterConfig.maxBetweenness) return false;
      
      // Eigenvector centrality filter
      const eigenvector = node.properties?.eigenvector_centrality || 0;
      const eigenvectorPercent = Math.min((eigenvector / 1) * 100, 100);
      if (eigenvectorPercent < filterConfig.minEigenvector || eigenvectorPercent > filterConfig.maxEigenvector) return false;
    }
    
    // Connection count filter
    if (filterConfig.minConnections > 0 || filterConfig.maxConnections < 1000) {
      const connections = node.properties?.degree || node.properties?.connections || 0;
      if (connections < filterConfig.minConnections || connections > filterConfig.maxConnections) return false;
    }
    
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
  }, []);

  // Create a stable reference that never changes during incremental updates
  const stableTransformedDataRef = useRef<{ nodes: GraphNode[], links: GraphLink[] } | null>(null);
  
  const transformedData = React.useMemo(() => {
    // During incremental updates, return the exact same object reference
    if (isIncrementalUpdate && stableTransformedDataRef.current) {
      return stableTransformedDataRef.current;
    }
    
    // During incremental updates, use stable data to prevent cascade re-renders
    const sourceData = isIncrementalUpdate ? stableDataRef.current : data;
    
    if (!sourceData) {
      logger.warn('GraphViz: No source data available', { isIncrementalUpdate, hasData: !!data });
      return { nodes: [], links: [] };
    }
    
    const visibleNodes = sourceData.nodes.filter(node => nodePassesFilters(node, filterConfig));

    // Virtualization: For very large graphs (>10k nodes), prioritize most important nodes
    let finalNodes = visibleNodes;
    const LARGE_GRAPH_THRESHOLD = 10000;
    const MAX_RENDERED_NODES = 5000;

    if (visibleNodes.length > LARGE_GRAPH_THRESHOLD) {
      // Pre-calculate importance scores
      const nodesWithScore = visibleNodes.map(node => ({
        node,
        importanceScore: (node.properties?.degree_centrality || 0) * 0.4 + 
                        (node.properties?.pagerank_centrality || node.properties?.pagerank || 0) * 1000 * 0.4 + 
                        (node.properties?.betweenness_centrality || 0) * 0.2
      }));

      // Sort by importance and take top N nodes
      nodesWithScore.sort((a, b) => b.importanceScore - a.importanceScore);
      finalNodes = nodesWithScore
        .slice(0, MAX_RENDERED_NODES)
        .map(item => item.node);
    }
    
    const visibleNodeIds = new Set(finalNodes.map(n => n.id));
    const filteredLinks = sourceData.edges
      .filter(edge => visibleNodeIds.has(edge.from) && visibleNodeIds.has(edge.to))
      .map(edge => ({
        ...edge,
        source: edge.from,
        target: edge.to,
      }));
    
    const newTransformedData = {
      nodes: finalNodes,
      links: filteredLinks,
    };
    
    // Update stable reference when not in incremental mode
    if (!isIncrementalUpdate) {
      stableTransformedDataRef.current = newTransformedData;
    }
    
    return newTransformedData;
  }, [data, isIncrementalUpdate, filterConfig, nodePassesFilters]);

  // Update node type configurations when data changes
  React.useEffect(() => {
    if (data?.nodes && data.nodes.length > 0) {
      const nodeTypes = [...new Set(data.nodes.map(node => node.node_type).filter(Boolean))].sort();
      if (nodeTypes.length > 0) {
        updateNodeTypeConfigurations(nodeTypes);
      }
    }
  }, [data?.nodes?.length, updateNodeTypeConfigurations]);

  const handleNodeSelect = (nodeId: string) => {
    if (selectedNodes.includes(nodeId)) {
      setSelectedNodes(selectedNodes.filter(id => id !== nodeId));
    } else {
      setSelectedNodes([...selectedNodes, nodeId]);
    }
  };

  const handleNodeClick = (node: GraphNode) => {
    // Normal click behavior
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
      
      // Removed automatic zoom to subnetwork for now
      
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
    
    // Removed automatic fitView on clear selection for now
  }, [selectedNodes.length, selectedNode?.id, highlightedNodes.length]);

  const handleLayoutChange = useCallback((layoutType: string) => {
    if (transformedData && transformedData.nodes.length > 0) {
      applyLayout(layoutType, {}, { nodes: transformedData.nodes, edges: transformedData.links.map(link => ({ from: link.source, to: link.target, ...link })) });
    }
  }, [applyLayout, transformedData]);

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


  const handleNodeHover = useCallback((node: GraphNode | null) => {
    setHoveredNode(node);
    
    if (node && graphCanvasRef.current) {
      // Find connected nodes
      const nodeIndex = transformedData.nodes.findIndex(n => n.id === node.id);
      if (nodeIndex !== -1) {
        const connectedIndices = graphCanvasRef.current.getConnectedPointIndices(nodeIndex);
        if (connectedIndices && connectedIndices.length > 0) {
          const connectedNodeIds = connectedIndices
            .map(idx => transformedData.nodes[idx]?.id)
            .filter(Boolean);
          setHoveredConnectedNodes(connectedNodeIds);
        } else {
          setHoveredConnectedNodes([]);
        }
      }
    } else {
      setHoveredConnectedNodes([]);
    }
  }, [transformedData.nodes]);

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
              Virtualized ({transformedData.nodes.length.toLocaleString()}/{data.nodes.length.toLocaleString()})
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
            onClick={toggleSimulation}
            className="hover:bg-primary/10"
            title={isSimulationRunning ? "Pause Simulation" : "Play Simulation"}
          >
            {isSimulationRunning ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
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
                  onNodeHover={handleNodeHover}
                  selectedNodes={selectedNodes}
                  highlightedNodes={[...highlightedNodes, ...hoveredConnectedNodes]}
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

          {/* Hover Tooltip */}
          {hoveredNode && hoveredConnectedNodes.length > 0 && (
            <div className="absolute bottom-20 left-1/2 transform -translate-x-1/2 glass-panel px-3 py-1 rounded-full text-xs text-muted-foreground animate-fade-in pointer-events-none">
              {hoveredNode.label} • {hoveredConnectedNodes.length} connected nodes
            </div>
          )}

          {/* Quick Actions Toolbar - Positioned above timeline */}
          <div className="absolute bottom-32 left-1/2 transform -translate-x-1/2 flex flex-col items-center space-y-2 z-50">
            
            {/* Quick Actions */}
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
              logger.log('Timeline range changed:', range);
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