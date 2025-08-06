import React, { memo, useCallback, useMemo, useRef, useEffect, useState } from 'react';
import { Cosmograph } from '@cosmograph/react';
import { GraphNode } from '../api/types';
import { debounce, throttle, RequestQueue, FrameThrottler } from '../utils/performance';
import { lazyLoader } from '../services/lazy-loader';
import { useGraphConfig } from '../contexts/GraphConfigProvider';
import { useDuckDB } from '../contexts/DuckDBProvider';

// Memoized node component
const GraphNodeRenderer = memo<{ node: GraphNode; isSelected: boolean }>(
  ({ node, isSelected }) => {
    return null; // Cosmograph handles rendering
  },
  (prevProps, nextProps) => {
    // Only re-render if selection state or key properties change
    return (
      prevProps.isSelected === nextProps.isSelected &&
      prevProps.node.id === nextProps.node.id &&
      prevProps.node.label === nextProps.node.label
    );
  }
);

// Memoized edge renderer
const GraphEdgeRenderer = memo<{ edge: any }>(
  ({ edge }) => {
    return null; // Cosmograph handles rendering
  },
  (prevProps, nextProps) => {
    return (
      prevProps.edge.source === nextProps.edge.source &&
      prevProps.edge.target === nextProps.edge.target
    );
  }
);

interface OptimizedGraphCanvasProps {
  onNodeClick: (node: GraphNode) => void;
  selectedNodeIds: Set<string>;
}

export const OptimizedGraphCanvas = memo<OptimizedGraphCanvasProps>(
  ({ onNodeClick, selectedNodeIds }) => {
    const cosmographRef = useRef<any>(null);
    const workerRef = useRef<Worker | null>(null);
    const requestQueue = useRef(new RequestQueue(2));
    const frameThrottler = useRef(new FrameThrottler(30));
    
    const { config } = useGraphConfig();
    const { duckDBService, isInitialized } = useDuckDB();
    
    const [graphData, setGraphData] = useState<any>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [loadProgress, setLoadProgress] = useState(0);
    const [viewport, setViewport] = useState({ x: 0, y: 0, width: 1000, height: 1000, zoom: 1 });
    
    // Initialize WebWorker
    useEffect(() => {
      workerRef.current = new Worker(
        new URL('../workers/graph-processor.worker.ts', import.meta.url),
        { type: 'module' }
      );
      
      workerRef.current.onmessage = (event) => {
        const { type, data } = event.data;
        
        switch (type) {
          case 'LAYOUT_COMPLETE':
            applyLayout(data.positions);
            break;
          case 'LAYOUT_PROGRESS':
            setLoadProgress(data.progress);
            break;
          case 'FILTER_COMPLETE':
            updateFilteredNodes(data.nodes);
            break;
        }
      };
      
      return () => {
        workerRef.current?.terminate();
      };
    }, []);
    
    // Memoized data transformation
    const transformedData = useMemo(() => {
      if (!graphData) return null;
      
      // Heavy transformation moved to WebWorker
      return {
        nodes: graphData.nodes,
        edges: graphData.edges,
        stats: {
          nodeCount: graphData.nodes.length,
          edgeCount: graphData.edges.length
        }
      };
    }, [graphData]);
    
    // Debounced search handler
    const handleSearch = useMemo(
      () => debounce((searchTerm: string) => {
        if (!workerRef.current || !graphData) return;
        
        workerRef.current.postMessage({
          type: 'FILTER_NODES',
          data: {
            nodes: graphData.nodes,
            filters: { searchTerm }
          }
        });
      }, 300),
      [graphData]
    );
    
    // Throttled viewport update
    const handleViewportChange = useMemo(
      () => throttle((newViewport: any) => {
        setViewport(newViewport);
        
        // Trigger lazy loading for new viewport
        if (duckDBService && isInitialized) {
          requestQueue.current.add(
            `viewport-${newViewport.x}-${newViewport.y}`,
            () => lazyLoader.loadChunkByViewport(
              newViewport,
              config.rustServerUrl || 'http://localhost:3000',
              duckDBService.getDuckDBConnection()?.connection
            ),
            1 // Low priority
          );
        }
      }, 100),
      [duckDBService, isInitialized, config.rustServerUrl]
    );
    
    // Optimized node click handler
    const handleNodeClick = useCallback((node: GraphNode) => {
      // Use requestAnimationFrame for smooth updates
      requestAnimationFrame(() => {
        onNodeClick(node);
      });
    }, [onNodeClick]);
    
    // Progressive loading
    useEffect(() => {
      if (!duckDBService || !isInitialized) return;
      
      const loadData = async () => {
        setIsLoading(true);
        setLoadProgress(0);
        
        try {
          // Load initial chunk
          const stats = await lazyLoader.loadInitialChunk(
            config.rustServerUrl || 'http://localhost:3000',
            duckDBService.getDuckDBConnection()?.connection
          );
          
          setLoadProgress(0.5);
          
          // Get data from DuckDB
          const nodesTable = await duckDBService.getNodesTable();
          const edgesTable = await duckDBService.getEdgesTable();
          
          if (nodesTable && edgesTable) {
            // Convert to arrays for initial render
            const nodes: any[] = [];
            const edges: any[] = [];
            
            // Process nodes
            for (const batch of nodesTable.batches) {
              for (let i = 0; i < batch.numRows; i++) {
                nodes.push({
                  id: batch.getChild('id')?.get(i),
                  idx: batch.getChild('idx')?.get(i),
                  label: batch.getChild('label')?.get(i),
                  node_type: batch.getChild('node_type')?.get(i),
                  degree_centrality: batch.getChild('degree_centrality')?.get(i)
                });
              }
            }
            
            // Process edges
            for (const batch of edgesTable.batches) {
              for (let i = 0; i < batch.numRows; i++) {
                edges.push({
                  source: batch.getChild('source')?.get(i),
                  target: batch.getChild('target')?.get(i),
                  sourceidx: batch.getChild('sourceidx')?.get(i),
                  targetidx: batch.getChild('targetidx')?.get(i),
                  edge_type: batch.getChild('edge_type')?.get(i)
                });
              }
            }
            
            setGraphData({ nodes, edges });
            setLoadProgress(1);
            
            // Start layout calculation in WebWorker
            if (workerRef.current && nodes.length < 1000) {
              workerRef.current.postMessage({
                type: 'PROCESS_LAYOUT',
                data: { nodes, edges, iterations: 50 }
              });
            }
          }
        } catch (error) {
          console.error('Failed to load graph data:', error);
        } finally {
          setIsLoading(false);
        }
      };
      
      loadData();
    }, [duckDBService, isInitialized, config.rustServerUrl]);
    
    // Apply layout from WebWorker
    const applyLayout = useCallback((positions: Float32Array) => {
      if (!cosmographRef.current) return;
      
      // Apply positions smoothly
      frameThrottler.current.start((deltaTime) => {
        // Interpolate positions for smooth animation
        // This would update Cosmograph's node positions
        console.log('Applying layout positions smoothly');
      });
      
      setTimeout(() => {
        frameThrottler.current.stop();
      }, 1000);
    }, []);
    
    // Update filtered nodes
    const updateFilteredNodes = useCallback((filteredNodes: any[]) => {
      setGraphData(prev => ({
        ...prev,
        nodes: filteredNodes
      }));
    }, []);
    
    // Memoized Cosmograph config
    const cosmographConfig = useMemo(() => ({
      nodeSize: 5,
      nodeColor: (node: any) => {
        if (selectedNodeIds.has(node.id)) {
          return '#6366f1'; // Indigo for selected
        }
        return config.nodeTypeColors[node.node_type] || '#94a3b8';
      },
      linkWidth: 1,
      linkColor: '#64748b',
      backgroundColor: '#0f172a',
      showFPSCounter: false,
      disableSimulation: graphData?.nodes?.length > 2000, // Disable for large graphs
      useQuadtree: true, // Enable spatial indexing
      pixelRatio: Math.min(window.devicePixelRatio, 2), // Cap pixel ratio for performance
    }), [selectedNodeIds, config.nodeTypeColors, graphData]);
    
    if (!transformedData) {
      return (
        <div className="flex items-center justify-center h-full">
          <div className="text-center">
            <div className="text-lg mb-2">Loading Graph...</div>
            <div className="w-64 h-2 bg-gray-700 rounded">
              <div 
                className="h-full bg-indigo-500 rounded transition-all duration-300"
                style={{ width: `${loadProgress * 100}%` }}
              />
            </div>
            {lazyLoader.isLoading() && (
              <div className="text-sm mt-2 text-gray-400">
                Loading additional data...
              </div>
            )}
          </div>
        </div>
      );
    }
    
    return (
      <div className="relative w-full h-full">
        <Cosmograph
          ref={cosmographRef}
          nodes={transformedData.nodes}
          links={transformedData.edges}
          {...cosmographConfig}
          onClick={handleNodeClick}
          onViewportChange={handleViewportChange}
        />
        
        {/* Performance stats overlay */}
        <div className="absolute top-4 right-4 bg-black/50 text-white p-2 rounded text-xs">
          <div>Nodes: {transformedData.stats.nodeCount}</div>
          <div>Edges: {transformedData.stats.edgeCount}</div>
          <div>Loaded: {lazyLoader.getLoadedNodeCount()}</div>
        </div>
      </div>
    );
  },
  (prevProps, nextProps) => {
    // Only re-render if selected nodes change
    if (prevProps.selectedNodeIds.size !== nextProps.selectedNodeIds.size) {
      return false;
    }
    
    for (const id of prevProps.selectedNodeIds) {
      if (!nextProps.selectedNodeIds.has(id)) {
        return false;
      }
    }
    
    return true;
  }
);

OptimizedGraphCanvas.displayName = 'OptimizedGraphCanvas';