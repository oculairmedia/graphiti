import React, { useEffect, useRef, forwardRef, useState, useCallback } from 'react';
import { Cosmograph, prepareCosmographData } from '@cosmograph/react';
import { GraphNode } from '../api/types';
import type { GraphData } from '../types/graph';
import { useGraphConfig } from '../contexts/GraphConfigContext';
import { logger } from '../utils/logger';
import { hexToRgba, generateHSLColor } from '../utils/colorCache';

interface GraphLink {
  source: string;
  target: string;
  from: string;
  to: string;
  weight?: number;
  edge_type?: string;
  [key: string]: unknown;
}

interface GraphNodeWithPosition extends GraphNode {
  x?: number;
  y?: number;
}

interface GraphStats {
  total_nodes: number;
  total_edges: number;
  density?: number;
  [key: string]: unknown;
}

interface CosmographRef {
  setZoomLevel: (level: number, duration?: number) => void;
  getZoomLevel: () => number;
  fitView: (duration?: number) => void;
  selectNode: (node: GraphNode) => void;
  selectNodes: (nodes: GraphNode[]) => void;
  unselectAll: () => void;
  unfocusNode: () => void;
  restart: () => void;
  start: () => void;
  _canvasElement?: HTMLCanvasElement;
}

interface GraphCanvasProps {
  onNodeClick: (node: GraphNode) => void;
  onNodeSelect: (nodeId: string) => void;
  onClearSelection?: () => void;
  selectedNodes: string[];
  highlightedNodes: string[];
  className?: string;
  stats?: GraphStats;
}

interface GraphCanvasHandle {
  clearSelection: () => void;
  selectNode: (node: GraphNode) => void;
  selectNodes: (nodes: GraphNode[]) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
  setData: (nodes: GraphNode[], links: GraphLink[], runSimulation?: boolean) => void;
  restart: () => void;
}

interface GraphCanvasComponentProps extends GraphCanvasProps {
  nodes: GraphNode[];
  links: GraphLink[];
}

const GraphCanvasComponent = forwardRef<GraphCanvasHandle, GraphCanvasComponentProps>(
  ({ onNodeClick, onNodeSelect, onClearSelection, selectedNodes, highlightedNodes, className, stats, nodes, links }, ref) => {
    const cosmographRef = useRef<CosmographRef | null>(null);
    const [isReady, setIsReady] = useState(false);
    const [isCanvasReady, setIsCanvasReady] = useState(false);
    const [cosmographData, setCosmographData] = useState<any>(null);
    const [dataKitError, setDataKitError] = useState<string | null>(null);
    const [isDataPreparing, setIsDataPreparing] = useState(false);
    const { config, setCosmographRef } = useGraphConfig();
    // Double-click detection using refs to avoid re-renders
    const lastClickTimeRef = useRef<number>(0);
    const lastClickedNodeRef = useRef<GraphNode | null>(null);
    const doubleClickTimeoutRef = useRef<NodeJS.Timeout | null>(null);


    // Data Kit configuration for Cosmograph v2.0
    const dataKitConfig = React.useMemo(() => ({
      points: {
        pointIdBy: 'id',              // Required: unique identifier field
        pointLabelBy: 'label',        // Node display labels
        pointColorBy: 'node_type',    // Color by entity type
        pointSizeBy: 'centrality',    // Size by centrality metrics
        pointIncludeColumns: ['degree_centrality', 'pagerank_centrality', 'betweenness_centrality'] // Include additional columns
      },
      links: {
        linkSourceBy: 'source',       // Source node ID field
        linkTargetsBy: ['target'],    // Target node ID field (note: array format as per docs)
        linkColorBy: 'edge_type',     // Link color by type
        linkWidthBy: 'weight'         // Link width by weight
      }
    }), []);

    // Data Kit preparation effect
    useEffect(() => {
      if (!nodes || !links || nodes.length === 0) {
        setCosmographData(null);
        setDataKitError(null);
        return;
      }

      let cancelled = false;
      
      const prepareData = async () => {
        try {
          setIsDataPreparing(true);
          setDataKitError(null);
          
          logger.log('GraphCanvas: Preparing data with Cosmograph Data Kit...');
          
          // Transform data to match Data Kit expectations with consistent types
          const transformedNodes = nodes.map(node => ({
            id: String(node.id), // Ensure string type
            label: String(node.label || node.id), // Ensure string type
            node_type: String(node.node_type || 'Unknown'), // Ensure string type
            centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1), // Ensure number type
            // Add other commonly used properties with type safety
            degree_centrality: Number(node.properties?.degree_centrality || 0),
            pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
            betweenness_centrality: Number(node.properties?.betweenness_centrality || 0)
          }));

          const transformedLinks = links.map(link => ({
            source: String(link.source), // Ensure string type
            target: String(link.target), // Ensure string type
            edge_type: String(link.edge_type || 'default'), // Ensure string type
            weight: Number(link.weight || 1) // Ensure number type
          }));

          logger.log(`GraphCanvas: Data Kit processing ${transformedNodes.length} nodes, ${transformedLinks.length} links`);
          logger.log('Sample node:', transformedNodes[0]);
          logger.log('Sample link:', transformedLinks[0]);
          logger.log('Data Kit config:', dataKitConfig);
          
          const result = await prepareCosmographData(
            dataKitConfig,
            transformedNodes,
            transformedLinks
          );
          
          if (!cancelled && result) {
            // Extract the correct structure from Data Kit result
            const { points, links, cosmographConfig } = result;
            setCosmographData({
              points,
              links,
              cosmographConfig
            });
            logger.log('GraphCanvas: Data Kit preparation completed successfully');
          }
        } catch (error) {
          if (!cancelled) {
            const errorMessage = error instanceof Error ? error.message : 'Unknown error';
            logger.error('GraphCanvas: Data Kit preparation failed:', errorMessage);
            setDataKitError(errorMessage);
            
            // Fallback to direct data passing
            logger.log('GraphCanvas: Falling back to direct data passing');
            setCosmographData({
              points: transformedNodes,
              links: transformedLinks,
              cosmographConfig: {}
            });
          }
        } finally {
          if (!cancelled) {
            setIsDataPreparing(false);
          }
        }
      };

      prepareData();
      
      return () => {
        cancelled = true;
      };
    }, [nodes, links, dataKitConfig]);

    // Canvas readiness tracking with single polling mechanism and WebGL context loss recovery
    const intervalRef = useRef<NodeJS.Timeout | null>(null);
    const [webglContextLost, setWebglContextLost] = useState(false);
    
    // WebGL context loss recovery
    const setupWebGLContextRecovery = useCallback(() => {
      const canvas = cosmographRef.current?._canvasElement;
      if (!canvas) return;

      const handleContextLost = (event: Event) => {
        event.preventDefault();
        console.warn('GraphCanvas: WebGL context lost, attempting recovery...');
        setWebglContextLost(true);
      };

      const handleContextRestored = () => {
        console.log('GraphCanvas: WebGL context restored');
        setWebglContextLost(false);
        
        // Trigger re-render by restarting the simulation
        try {
          cosmographRef.current?.restart();
        } catch (error) {
          console.error('GraphCanvas: Error restarting after context restore:', error);
        }
      };

      canvas.addEventListener('webglcontextlost', handleContextLost);
      canvas.addEventListener('webglcontextrestored', handleContextRestored);

      return () => {
        canvas.removeEventListener('webglcontextlost', handleContextLost);
        canvas.removeEventListener('webglcontextrestored', handleContextRestored);
      };
    }, []);
    
    useEffect(() => {
      // Set up continuous polling to check for cosmographRef availability
      let checkCount = 0;
      let webglCleanup: (() => void) | undefined;
      
      const pollCosmographRef = () => {
        if (cosmographRef.current) {
          try {
            console.log('GraphCanvas: Setting cosmographRef in context');
            setCosmographRef(cosmographRef);
            setIsReady(true);
            
            // Set up WebGL context loss recovery
            webglCleanup = setupWebGLContextRecovery();
            
            // Start canvas polling
            const pollCanvas = () => {
              const hasCanvas = !!cosmographRef.current?._canvasElement;
              
              setIsCanvasReady(prevReady => {
                if (hasCanvas !== prevReady) {
                  console.log('GraphCanvas: Canvas ready state changed to', hasCanvas);
                }
                return hasCanvas;
              });
              
              if (!hasCanvas && checkCount < 100) { // Max 5 seconds of polling
                checkCount++;
                // Aggressive polling for first 2 seconds, then slower
                const delay = checkCount < 40 ? 50 : 200;
                intervalRef.current = setTimeout(pollCanvas, delay);
              }
            };
            
            // Start canvas polling immediately
            pollCanvas();
          } catch (error) {
            console.error('GraphCanvas: Error setting up cosmographRef:', error);
          }
        } else {
          // Keep polling for cosmographRef every 100ms for up to 10 seconds
          if (checkCount < 100) {
            checkCount++;
            setTimeout(pollCosmographRef, 100);
          } else {
            console.warn('GraphCanvas: cosmographRef never became available after 10 seconds');
          }
        }
      };
      
      // Start polling immediately
      pollCosmographRef();
      
      return () => {
        if (intervalRef.current) {
          clearTimeout(intervalRef.current);
          intervalRef.current = null;
        }
        if (webglCleanup) {
          webglCleanup();
        }
      };
    }, [setCosmographRef, setupWebGLContextRecovery]);


    // Simplified data transformation for legacy compatibility
    const transformedData = React.useMemo(() => {
      return { nodes, links };
    }, [nodes, links]);

    // Method to select a single node in Cosmograph
    const selectCosmographNode = useCallback((node: GraphNode) => {
      if (cosmographRef.current) {
        try {
          if (typeof cosmographRef.current.selectNode === 'function') {
            cosmographRef.current.selectNode(node);
          } else if (typeof cosmographRef.current.selectNodes === 'function') {
            cosmographRef.current.selectNodes([node]);
          }
        } catch (error) {
          logger.error('Error selecting Cosmograph node:', error);
        }
      }
    }, []);

    // Method to select multiple nodes in Cosmograph
    const selectCosmographNodes = useCallback((nodes: GraphNode[]) => {
      if (cosmographRef.current) {
        try {
          if (typeof cosmographRef.current.selectNodes === 'function') {
            cosmographRef.current.selectNodes(nodes);
            logger.log('Selected Cosmograph nodes:', nodes.map(n => n.id));
          } else {
            logger.warn('No selectNodes method found on Cosmograph instance');
          }
        } catch (error) {
          logger.error('Error selecting Cosmograph nodes:', error);
        }
      }
    }, []);

    // Method to clear Cosmograph selection and return to default state
    const clearCosmographSelection = useCallback(() => {
      if (cosmographRef.current) {
        try {
          // Try multiple approaches to clear selection and return to default state
          if (typeof cosmographRef.current.unselectAll === 'function') {
            cosmographRef.current.unselectAll();
            logger.log('Cleared Cosmograph selection with unselectAll()');
          } else if (typeof cosmographRef.current.selectNodes === 'function') {
            cosmographRef.current.selectNodes([]);
            logger.log('Cleared Cosmograph selection with selectNodes([])');
          } else if (typeof cosmographRef.current.setSelectedNodes === 'function') {
            cosmographRef.current.setSelectedNodes([]);
            logger.log('Cleared Cosmograph selection with setSelectedNodes([])');
          } else {
            logger.warn('No clear selection method found on Cosmograph instance');
            logger.log('Available methods:', Object.getOwnPropertyNames(cosmographRef.current));
          }
          
          // Additional step: ensure we're in default state by calling unfocusNode if available
          if (typeof cosmographRef.current.unfocusNode === 'function') {
            cosmographRef.current.unfocusNode();
          }
        } catch (error) {
          logger.error('Error clearing Cosmograph selection:', error);
        }
      }
    }, []);

    const zoomIn = useCallback(() => {
      if (!cosmographRef.current?.setZoomLevel) return;
      
      try {
        const currentZoom = cosmographRef.current.getZoomLevel();
        const newZoom = Math.min(currentZoom * 1.5, 10);
        cosmographRef.current.setZoomLevel(newZoom, 300);
      } catch (error) {
        logger.warn('Zoom in failed:', error);
      }
    }, []);

    const zoomOut = useCallback(() => {
      if (!cosmographRef.current?.setZoomLevel) return;
      
      try {
        const currentZoom = cosmographRef.current.getZoomLevel();
        const newZoom = Math.max(currentZoom * 0.67, 0.1);
        cosmographRef.current.setZoomLevel(newZoom, 300);
      } catch (error) {
        logger.warn('Zoom out failed:', error);
      }
    }, []);

    const fitView = useCallback(() => {
      if (!cosmographRef.current?.fitView) return;
      
      try {
        cosmographRef.current.fitView(500);
      } catch (error) {
        logger.warn('Fit view failed:', error);
      }
    }, []);

    // Expose methods to parent via ref
    React.useImperativeHandle(ref, () => ({
      clearSelection: clearCosmographSelection,
      selectNode: selectCosmographNode,
      selectNodes: selectCosmographNodes,
      zoomIn,
      zoomOut,
      fitView,
      setData: (nodes: GraphNode[], links: GraphLink[], runSimulation = true) => {
        if (cosmographRef.current && typeof cosmographRef.current.setData === 'function') {
          cosmographRef.current.setData(nodes, links, runSimulation);
        }
      },
      restart: () => {
        if (cosmographRef.current && typeof cosmographRef.current.restart === 'function') {
          cosmographRef.current.restart();
        }
      }
    }), [clearCosmographSelection, selectCosmographNode, selectCosmographNodes, zoomIn, zoomOut, fitView]);

    // Handle Cosmograph events with double-click detection
    const handleClick = (node?: GraphNode) => {
      if (node) {
        const currentTime = Date.now();
        const timeDiff = currentTime - lastClickTimeRef.current;
        const isDoubleClick = timeDiff < 300 && lastClickedNodeRef.current?.id === node.id;
        
        // Clear any existing timeout
        if (doubleClickTimeoutRef.current) {
          clearTimeout(doubleClickTimeoutRef.current);
          doubleClickTimeoutRef.current = null;
        }
        
        if (isDoubleClick) {
          // Double-click detected - select node with Cosmograph visual effects
          selectCosmographNode(node);
          onNodeClick(node);
          onNodeSelect(node.id);
        } else {
          // Single click - show modal and maintain visual selection
          doubleClickTimeoutRef.current = setTimeout(() => {
            // Single click confirmed - show modal and keep node visually selected
            logger.log('Single-click detected on node:', node.id);
            selectCosmographNode(node); // Keep visual selection circle
            onNodeClick(node); // Show modal
            onNodeSelect(node.id); // Update selection state
          }, 300);
        }
        
        // Update click tracking using refs (no re-render)
        lastClickTimeRef.current = currentTime;
        lastClickedNodeRef.current = node;
      } else {
        // Empty space was clicked - clear all selections and return to default state
        clearCosmographSelection();
        onClearSelection?.();
      }
    };

    // Show loading state while data is being prepared
    if (isDataPreparing) {
      return (
        <div className={`relative overflow-hidden ${className} flex items-center justify-center`}>
          <div className="text-muted-foreground text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mb-2 mx-auto"></div>
            <p className="text-sm">Preparing graph data...</p>
          </div>
        </div>
      );
    }

    // Show error state if Data Kit failed (with fallback)
    if (dataKitError && !cosmographData) {
      return (
        <div className={`relative overflow-hidden ${className} flex items-center justify-center`}>
          <div className="text-destructive text-center">
            <p className="text-sm">Data preparation failed: {dataKitError}</p>
            <p className="text-xs text-muted-foreground mt-1">Using fallback rendering</p>
          </div>
        </div>
      );
    }

    // Don't render if no data is available
    if (!cosmographData) {
      return (
        <div className={`relative overflow-hidden ${className} flex items-center justify-center`}>
          <div className="text-muted-foreground text-center">
            <p className="text-sm">No graph data available</p>
          </div>
        </div>
      );
    }

    return (
      <div 
        className={`relative overflow-hidden ${className}`}
      >
          <Cosmograph
            ref={cosmographRef}
            // Use Data Kit prepared data and configuration
            points={cosmographData.points}
            links={cosmographData.links}
            {...cosmographData.cosmographConfig}
            // Override with UI-specific configurations
            fitViewOnInit={true}
            initialZoomLevel={1.5}
            disableZoom={false}
            backgroundColor={config.backgroundColor}
            
            // Highlighted nodes styling
            nodeColor={(node: any) => {
              const isHighlighted = highlightedNodes.includes(node.id);
              if (isHighlighted) {
                return 'rgba(255, 215, 0, 0.9)'; // Gold highlight
              }
              
              // Fallback to Data Kit color or type-based color
              if (cosmographData.cosmographConfig.nodeColor) {
                return typeof cosmographData.cosmographConfig.nodeColor === 'function' 
                  ? cosmographData.cosmographConfig.nodeColor(node)
                  : cosmographData.cosmographConfig.nodeColor;
              }
              
              // Type-based fallback
              const nodeType = node.node_type as keyof typeof config.nodeTypeColors;
              const typeColor = config.nodeTypeColors[nodeType] || '#b3b3b3';
              return hexToRgba(typeColor, config.nodeOpacity / 100);
            }}
            
            nodeSize={(node: any) => {
              // Data Kit should handle sizing, but add highlight effect
              let baseSize = 1;
              if (cosmographData.cosmographConfig.nodeSize) {
                baseSize = typeof cosmographData.cosmographConfig.nodeSize === 'function'
                  ? cosmographData.cosmographConfig.nodeSize(node)
                  : cosmographData.cosmographConfig.nodeSize;
              }
              
              // Make highlighted nodes 20% larger
              const isHighlighted = highlightedNodes.includes(node.id);
              return isHighlighted ? baseSize * 1.2 : baseSize;
            }}
            
            // Interaction
            onClick={handleClick}
            renderHoveredNodeRing={true}
            hoveredNodeRingColor="#22d3ee"
            focusedNodeRingColor="#fbbf24"
            nodeGreyoutOpacity={selectedNodes.length > 0 || highlightedNodes.length > 0 ? 0.1 : 1}
            
            // Performance
            pixelRatio={2.5}
            showFPSMonitor={false}
            
            // Selection
            showLabelsFor={selectedNodes.map(id => ({ id }))}
          />
        
        {/* Performance Overlay */}
        {stats && (
          <div className="absolute top-4 left-4 glass text-xs text-muted-foreground p-2 rounded">
            <div>Nodes: {stats.total_nodes.toLocaleString()}</div>
            <div>Edges: {stats.total_edges.toLocaleString()}</div>
            {stats.density !== undefined && (
              <div>Density: {stats.density.toFixed(4)}</div>
            )}
          </div>
        )}
      </div>
    );
  }
);

// Export with React.memo to prevent unnecessary re-renders
export const GraphCanvas = React.memo(GraphCanvasComponent, (prevProps, nextProps) => {
  // Ultra-restrictive comparison - only re-render for essential changes
  
  // Check callback functions by reference (they should be stable with useCallback)
  const callbacksChanged = prevProps.onNodeClick !== nextProps.onNodeClick ||
                           prevProps.onNodeSelect !== nextProps.onNodeSelect ||
                           prevProps.onClearSelection !== nextProps.onClearSelection;
  
  // Proper deep comparison for selection arrays
  const selectedNodesChanged = prevProps.selectedNodes !== nextProps.selectedNodes ||
                              prevProps.selectedNodes.length !== nextProps.selectedNodes.length ||
                              !prevProps.selectedNodes.every((id, index) => id === nextProps.selectedNodes[index]);
                               
  const highlightedNodesChanged = prevProps.highlightedNodes !== nextProps.highlightedNodes ||
                                 prevProps.highlightedNodes.length !== nextProps.highlightedNodes.length ||
                                 !prevProps.highlightedNodes.every((id, index) => id === nextProps.highlightedNodes[index]);
  
  // Only re-render if stats actually changed
  const statsChanged = prevProps.stats !== nextProps.stats;
  
  // ClassName changes
  const classNameChanged = prevProps.className !== nextProps.className;
  
  const shouldRerender = callbacksChanged || selectedNodesChanged || highlightedNodesChanged || statsChanged || classNameChanged;
  
  // Return true to skip re-render, false to re-render
  return !shouldRerender;
});

GraphCanvas.displayName = 'GraphCanvas';