import React, { useRef, useCallback, useEffect, useMemo, useState } from 'react';
import { GraphViewport, GraphViewportHandle } from './GraphViewport';
import { useGraphData, GraphDelta, createGraphDelta } from '../../hooks/graph/useGraphData';
import { useWebSocketManager } from '../../hooks/graph/useWebSocketManager';
import { GraphNode } from '../../api/types';
import { ErrorBoundary } from './ErrorBoundary';
import { GraphLoadingState } from './GraphLoadingState';

export interface GraphContainerProps {
  // Data source
  initialNodes?: GraphNode[];
  initialLinks?: any[];
  dataUrl?: string;
  webSocketUrl?: string;
  
  // Visual config
  width?: number;
  height?: number;
  className?: string;
  theme?: 'dark' | 'light';
  
  // Features
  enableRealTimeUpdates?: boolean;
  enableVirtualization?: boolean;
  enableDeltaProcessing?: boolean;
  
  // Callbacks
  onNodeClick?: (node: GraphNode) => void;
  onNodeDoubleClick?: (node: GraphNode) => void;
  onSelectionChange?: (selectedNodes: GraphNode[]) => void;
  onError?: (error: Error) => void;
}

/**
 * Container component that orchestrates graph data management,
 * real-time updates, and rendering
 */
export const GraphContainer: React.FC<GraphContainerProps> = ({
  initialNodes = [],
  initialLinks = [],
  dataUrl,
  webSocketUrl,
  width = 800,
  height = 600,
  className = '',
  theme = 'dark',
  enableRealTimeUpdates = true,
  enableVirtualization = true,
  enableDeltaProcessing = true,
  onNodeClick,
  onNodeDoubleClick,
  onSelectionChange,
  onError
}) => {
  // Refs
  const viewportRef = useRef<GraphViewportHandle>(null);
  const lastDataRef = useRef<{ nodes: GraphNode[]; links: any[] }>({ nodes: [], links: [] });
  
  // State
  const [selectedNodes, setSelectedNodes] = useState<Set<string>>(new Set());
  const [highlightedNodes, setHighlightedNodes] = useState<Set<string>>(new Set());
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);
  
  // Custom hooks for data management
  const [graphData, graphActions] = useGraphData({
    initialNodes,
    initialLinks,
    enableDeltaProcessing,
    maxHistorySize: 20
  });
  
  // WebSocket management for real-time updates
  const [wsState, wsActions] = useWebSocketManager(
    {
      url: webSocketUrl || 'ws://localhost:8000/ws',
      reconnectAttempts: 5,
      reconnectDelay: 1000,
      heartbeatInterval: 30000,
      enableCompression: true,
      batchUpdates: true,
      batchInterval: 16 // ~60fps
    },
    // Handle WebSocket messages
    useCallback((message) => {
      console.log('[GraphContainer] Received WebSocket message:', message.type);
      
      if (message.type === 'delta' && message.delta) {
        graphActions.applyDelta(message.delta);
      } else if (message.type === 'full' && message.data) {
        graphActions.setNodes(message.data.nodes || []);
        graphActions.setLinks(message.data.links || []);
      }
    }, [graphActions]),
    // Handle delta updates
    useCallback((delta: GraphDelta) => {
      console.log('[GraphContainer] Applying delta update:', {
        addedNodes: delta.addedNodes?.length || 0,
        updatedNodes: delta.updatedNodes?.size || 0,
        removedNodes: delta.removedNodeIds?.length || 0
      });
      graphActions.applyDelta(delta);
    }, [graphActions])
  );
  
  // Load initial data if URL provided
  useEffect(() => {
    if (!dataUrl || isInitialized) return;
    
    const loadData = async () => {
      try {
        graphActions.setLoading(true);
        const response = await fetch(dataUrl);
        
        if (!response.ok) {
          throw new Error(`Failed to load data: ${response.statusText}`);
        }
        
        const data = await response.json();
        graphActions.setNodes(data.nodes || []);
        graphActions.setLinks(data.links || data.edges || []);
        setIsInitialized(true);
      } catch (error) {
        console.error('[GraphContainer] Failed to load data:', error);
        graphActions.setError(error instanceof Error ? error.message : 'Failed to load data');
        onError?.(error instanceof Error ? error : new Error('Failed to load data'));
      } finally {
        graphActions.setLoading(false);
      }
    };
    
    loadData();
  }, [dataUrl, isInitialized, graphActions, onError]);
  
  // Connect WebSocket if enabled
  useEffect(() => {
    if (enableRealTimeUpdates && webSocketUrl && !wsState.isConnected) {
      wsActions.connect();
    }
    
    return () => {
      if (wsState.isConnected) {
        wsActions.disconnect();
      }
    };
  }, [enableRealTimeUpdates, webSocketUrl, wsState.isConnected, wsActions]);
  
  // Calculate delta when data changes (for debugging/monitoring)
  useEffect(() => {
    if (enableDeltaProcessing && lastDataRef.current.nodes.length > 0) {
      const delta = createGraphDelta(
        lastDataRef.current,
        { nodes: graphData.nodes, links: graphData.links }
      );
      
      if (Object.keys(delta).length > 1) { // Has changes beyond timestamp
        console.log('[GraphContainer] Data changed, delta:', delta);
      }
    }
    
    lastDataRef.current = {
      nodes: [...graphData.nodes],
      links: [...graphData.links]
    };
  }, [graphData.nodes, graphData.links, enableDeltaProcessing]);
  
  // Handle node click
  const handleNodeClick = useCallback((node: GraphNode, event: React.MouseEvent) => {
    if (event.shiftKey || event.ctrlKey || event.metaKey) {
      // Multi-select
      setSelectedNodes(prev => {
        const newSet = new Set(prev);
        if (newSet.has(node.id)) {
          newSet.delete(node.id);
        } else {
          newSet.add(node.id);
        }
        return newSet;
      });
    } else {
      // Single select
      setSelectedNodes(new Set([node.id]));
    }
    
    onNodeClick?.(node);
  }, [onNodeClick]);
  
  // Handle node double click
  const handleNodeDoubleClick = useCallback((node: GraphNode, event: React.MouseEvent) => {
    // Highlight connected nodes
    const connectedNodeIds = new Set<string>();
    
    graphData.links.forEach(link => {
      if (link.source === node.id) {
        connectedNodeIds.add(link.target);
      } else if (link.target === node.id) {
        connectedNodeIds.add(link.source);
      }
    });
    
    setHighlightedNodes(connectedNodeIds);
    onNodeDoubleClick?.(node);
  }, [graphData.links, onNodeDoubleClick]);
  
  // Handle background click
  const handleBackgroundClick = useCallback(() => {
    setSelectedNodes(new Set());
    setHighlightedNodes(new Set());
  }, []);
  
  // Handle hover
  const handleNodeHover = useCallback((node: GraphNode | null) => {
    setHoveredNode(node);
  }, []);
  
  // Notify selection changes
  useEffect(() => {
    if (onSelectionChange) {
      const selected = graphData.nodes.filter(n => selectedNodes.has(n.id));
      onSelectionChange(selected);
    }
  }, [selectedNodes, graphData.nodes, onSelectionChange]);
  
  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl/Cmd + A: Select all
      if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
        e.preventDefault();
        setSelectedNodes(new Set(graphData.nodes.map(n => n.id)));
      }
      // Escape: Clear selection
      else if (e.key === 'Escape') {
        setSelectedNodes(new Set());
        setHighlightedNodes(new Set());
      }
      // Delete: Remove selected nodes (if removal is enabled)
      else if (e.key === 'Delete' && selectedNodes.size > 0) {
        // This would trigger node removal if enabled
        console.log('[GraphContainer] Delete pressed on', selectedNodes.size, 'nodes');
      }
      // F: Fit view
      else if (e.key === 'f' && !e.ctrlKey && !e.metaKey) {
        viewportRef.current?.fitToNodes();
      }
      // R: Reset viewport
      else if (e.key === 'r' && !e.ctrlKey && !e.metaKey) {
        viewportRef.current?.resetViewport();
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedNodes, graphData.nodes]);
  
  // Memoize visual configuration
  const visualConfig = useMemo(() => ({
    backgroundColor: theme === 'dark' ? '#0a0a0a' : '#f5f5f5',
    nodeColor: (node: GraphNode) => {
      if (selectedNodes.has(node.id)) return '#FFD700';
      if (highlightedNodes.has(node.id)) return '#FF6B6B';
      if (node.node_type === 'Entity') return '#4FC3F7';
      if (node.node_type === 'Episodic') return '#66BB6A';
      return '#4A90E2';
    },
    linkColor: theme === 'dark' ? '#333333' : '#cccccc',
    nodeSize: 5,
    linkWidth: 1
  }), [theme, selectedNodes, highlightedNodes]);
  
  // Loading state
  if (graphData.loading && !isInitialized) {
    return <GraphLoadingState message="Loading graph data..." />;
  }
  
  // Error state
  if (graphData.error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-red-500 text-center">
          <p className="text-xl mb-2">Error Loading Graph</p>
          <p className="text-sm">{graphData.error}</p>
          <button
            onClick={() => {
              graphActions.setError(null);
              if (dataUrl) {
                setIsInitialized(false);
              }
            }}
            className="mt-4 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }
  
  return (
    <ErrorBoundary
      onError={onError}
      fallback={
        <div className="flex items-center justify-center h-full">
          <div className="text-red-500 text-center">
            <p className="text-xl mb-2">Something went wrong</p>
            <p className="text-sm">The graph visualization encountered an error</p>
          </div>
        </div>
      }
    >
      <div className={`relative ${className}`}>
        {/* Main viewport */}
        <GraphViewport
          ref={viewportRef}
          nodes={graphData.nodes}
          links={graphData.links}
          width={width}
          height={height}
          selectedNodes={selectedNodes}
          highlightedNodes={highlightedNodes}
          hoveredNode={hoveredNode}
          backgroundColor={visualConfig.backgroundColor}
          nodeColor={visualConfig.nodeColor}
          linkColor={visualConfig.linkColor}
          nodeSize={visualConfig.nodeSize}
          linkWidth={visualConfig.linkWidth}
          onNodeClick={handleNodeClick}
          onNodeDoubleClick={handleNodeDoubleClick}
          onNodeHover={handleNodeHover}
          onBackgroundClick={handleBackgroundClick}
          enablePanning={true}
          enableZooming={true}
          showLabels={true}
          labelVisibilityZoom={0.5}
        />
        
        {/* Status overlay */}
        <div className="absolute top-2 left-2 text-xs space-y-1">
          <div className={`px-2 py-1 rounded ${theme === 'dark' ? 'bg-gray-800 text-gray-300' : 'bg-white text-gray-700'}`}>
            Nodes: {graphData.stats.totalNodes}
          </div>
          <div className={`px-2 py-1 rounded ${theme === 'dark' ? 'bg-gray-800 text-gray-300' : 'bg-white text-gray-700'}`}>
            Edges: {graphData.stats.totalEdges}
          </div>
          {selectedNodes.size > 0 && (
            <div className={`px-2 py-1 rounded ${theme === 'dark' ? 'bg-blue-800 text-blue-300' : 'bg-blue-100 text-blue-700'}`}>
              Selected: {selectedNodes.size}
            </div>
          )}
        </div>
        
        {/* WebSocket status */}
        {enableRealTimeUpdates && (
          <div className="absolute top-2 right-2">
            <div className={`px-2 py-1 rounded text-xs ${
              wsState.isConnected ? 'bg-green-500' : 
              wsState.isReconnecting ? 'bg-yellow-500' : 
              'bg-red-500'
            } text-white`}>
              {wsState.isConnected ? 'Connected' :
               wsState.isReconnecting ? 'Reconnecting...' :
               'Disconnected'}
            </div>
            {wsState.connectionQuality !== 'offline' && (
              <div className={`mt-1 px-2 py-1 rounded text-xs ${
                wsState.connectionQuality === 'excellent' ? 'bg-green-500' :
                wsState.connectionQuality === 'good' ? 'bg-yellow-500' :
                'bg-orange-500'
              } text-white`}>
                {wsState.connectionQuality} ({wsState.lastPing}ms)
              </div>
            )}
          </div>
        )}
        
        {/* Controls */}
        <div className="absolute bottom-2 right-2 space-x-2">
          <button
            onClick={() => viewportRef.current?.fitToNodes()}
            className="px-3 py-1 bg-blue-500 text-white rounded text-sm hover:bg-blue-600"
          >
            Fit
          </button>
          <button
            onClick={() => viewportRef.current?.resetViewport()}
            className="px-3 py-1 bg-gray-500 text-white rounded text-sm hover:bg-gray-600"
          >
            Reset
          </button>
          <button
            onClick={async () => {
              const blob = await viewportRef.current?.exportImage('png');
              if (blob) {
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `graph-${Date.now()}.png`;
                a.click();
                URL.revokeObjectURL(url);
              }
            }}
            className="px-3 py-1 bg-green-500 text-white rounded text-sm hover:bg-green-600"
          >
            Export
          </button>
        </div>
      </div>
    </ErrorBoundary>
  );
};