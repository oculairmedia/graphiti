import React, { useEffect, useRef, forwardRef, useState, useCallback } from 'react';
import { Cosmograph, prepareCosmographData, CosmographProvider } from '@cosmograph/react';
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
        linkWidthBy: config.linkWidthBy         // Link width by configured column
      }
    }), [config.linkWidthBy]);

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
          const transformedNodes = nodes.map(node => {
            const nodeData = {
              id: String(node.id), // Ensure string type
              label: String(node.label || node.id), // Ensure string type
              node_type: String(node.node_type || 'Unknown'), // Ensure string type
              centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1), // Ensure number type
              // Add other commonly used properties with type safety
              degree_centrality: Number(node.properties?.degree_centrality || 0),
              pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
              betweenness_centrality: Number(node.properties?.betweenness_centrality || 0)
            };
            
            // Validate that all required fields are present and valid
            if (!nodeData.id || nodeData.id === 'undefined') {
              logger.warn('Invalid node ID found:', node);
            }
            
            return nodeData;
          }).filter(node => node.id && node.id !== 'undefined'); // Remove invalid nodes

          const transformedLinks = links.map(link => {
            const linkData = {
              source: String(link.source), // Ensure string type
              target: String(link.target), // Ensure string type
              edge_type: String(link.edge_type || 'default'), // Ensure string type
              weight: Number(link.weight || 1) // Ensure number type
            };
            
            // Validate that source and target exist
            if (!linkData.source || !linkData.target || linkData.source === 'undefined' || linkData.target === 'undefined') {
              logger.warn('Invalid link found:', link);
            }
            
            return linkData;
          }).filter(link => link.source && link.target && link.source !== 'undefined' && link.target !== 'undefined'); // Remove invalid links

          logger.log(`GraphCanvas: Data Kit processing ${transformedNodes.length} nodes, ${transformedLinks.length} links`);
          logger.log('Sample node:', transformedNodes[0]);
          logger.log('Sample link:', transformedLinks[0]);
          logger.log('Data Kit config:', dataKitConfig);
          
          // Log node type distribution for color mapping debugging
          const nodeTypeDistribution = transformedNodes.reduce((acc, node) => {
            acc[node.node_type] = (acc[node.node_type] || 0) + 1;
            return acc;
          }, {} as Record<string, number>);
          logger.log('Node type distribution:', nodeTypeDistribution);
          
          // Validate we have valid data before proceeding
          if (transformedNodes.length === 0) {
            throw new Error('No valid nodes found after transformation');
          }
          
          const result = await prepareCosmographData(
            dataKitConfig,
            transformedNodes,
            transformedLinks
          );
          
          if (!cancelled && result) {
            // Extract the correct structure from Data Kit result
            const { points, links, cosmographConfig } = result;
            logger.log('GraphCanvas: Data Kit result structure:', { 
              pointsType: typeof points, 
              linksType: typeof links, 
              configKeys: Object.keys(cosmographConfig || {}) 
            });
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
            console.log('🟢 GraphCanvas: cosmographRef.current is available');
            console.log('🟢 cosmographRef.current methods:', Object.getOwnPropertyNames(cosmographRef.current));
            console.log('🟢 About to call setCosmographRef...');
            setCosmographRef(cosmographRef);
            console.log('🟢 setCosmographRef called successfully');
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
          // For Cosmograph v2.0 with Data Kit, we need to use point indices
          if (typeof cosmographRef.current.selectPoint === 'function') {
            // Try to find the node index from the transformed data
            const nodeIndex = transformedData.nodes.findIndex(n => n.id === node.id);
            if (nodeIndex >= 0) {
              cosmographRef.current.selectPoint(nodeIndex);
              logger.log('Selected node by index:', nodeIndex, node.id);
            } else {
              logger.warn('Could not find node index for selection:', node.id);
            }
          } else if (typeof cosmographRef.current.selectPoints === 'function') {
            const nodeIndex = transformedData.nodes.findIndex(n => n.id === node.id);
            if (nodeIndex >= 0) {
              cosmographRef.current.selectPoints([nodeIndex]);
              logger.log('Selected node by index array:', nodeIndex, node.id);
            }
          }
        } catch (error) {
          logger.error('Error selecting Cosmograph node:', error);
        }
      }
    }, [transformedData.nodes]);

    // Method to select multiple nodes in Cosmograph
    const selectCosmographNodes = useCallback((nodes: GraphNode[]) => {
      if (cosmographRef.current) {
        try {
          if (typeof cosmographRef.current.selectPoints === 'function') {
            // Convert node IDs to indices
            const nodeIndices = nodes.map(node => {
              return transformedData.nodes.findIndex(n => n.id === node.id);
            }).filter(index => index >= 0); // Remove invalid indices
            
            if (nodeIndices.length > 0) {
              cosmographRef.current.selectPoints(nodeIndices);
              logger.log('Selected Cosmograph nodes by indices:', nodeIndices, nodes.map(n => n.id));
            } else {
              logger.warn('No valid node indices found for selection');
            }
          } else {
            logger.warn('No selectPoints method found on Cosmograph instance');
          }
        } catch (error) {
          logger.error('Error selecting Cosmograph nodes:', error);
        }
      }
    }, [transformedData.nodes]);

    // Method to clear Cosmograph selection and return to default state
    const clearCosmographSelection = useCallback(() => {
      if (cosmographRef.current) {
        try {
          // For Cosmograph v2.0, use the proper methods
          if (typeof cosmographRef.current.unselectAllPoints === 'function') {
            cosmographRef.current.unselectAllPoints();
            logger.log('Cleared Cosmograph selection with unselectAllPoints()');
          } else if (typeof cosmographRef.current.selectPoints === 'function') {
            cosmographRef.current.selectPoints([]);
            logger.log('Cleared Cosmograph selection with selectPoints([])');
          } else {
            logger.warn('No clear selection method found on Cosmograph instance');
            logger.log('Available methods:', Object.getOwnPropertyNames(cosmographRef.current));
          }
          
          // Additional step: clear focused point
          if (typeof cosmographRef.current.setFocusedPoint === 'function') {
            cosmographRef.current.setFocusedPoint();
          }
        } catch (error) {
          logger.error('Error clearing Cosmograph selection:', error);
        }
      }
    }, []);

    const zoomIn = useCallback(() => {
      if (!cosmographRef.current) return;
      
      try {
        // Use the official Cosmograph v2.0 API method with proper error handling
        const currentZoom = cosmographRef.current.getZoomLevel();
        if (currentZoom !== undefined) {
          const newZoom = Math.min(currentZoom * 1.5, 10);
          cosmographRef.current.setZoomLevel(newZoom);
          logger.log(`Zoom in: ${currentZoom.toFixed(2)} → ${newZoom.toFixed(2)}`);
        } else {
          logger.warn('Could not get current zoom level for zoom in');
        }
      } catch (error) {
        logger.warn('Zoom in failed:', error);
      }
    }, []);

    const zoomOut = useCallback(() => {
      if (!cosmographRef.current) return;
      
      try {
        // Use the official Cosmograph v2.0 API method with proper error handling
        const currentZoom = cosmographRef.current.getZoomLevel();
        if (currentZoom !== undefined) {
          const newZoom = Math.max(currentZoom * 0.67, 0.05); // Lower minimum zoom
          cosmographRef.current.setZoomLevel(newZoom);
          logger.log(`Zoom out: ${currentZoom.toFixed(2)} → ${newZoom.toFixed(2)}`);
        } else {
          logger.warn('Could not get current zoom level for zoom out');
        }
      } catch (error) {
        logger.warn('Zoom out failed:', error);
      }
    }, []);

    const fitView = useCallback(() => {
      if (!cosmographRef.current) return;
      
      try {
        // Use the official Cosmograph v2.0 API method with padding
        cosmographRef.current.fitView(500, 0.1); // 500ms duration, 10% padding
        logger.log('Fit view executed with padding');
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
    // Cosmograph v2.0 onClick signature: (index: number | undefined, pointPosition: [number, number] | undefined, event: MouseEvent) => void
    const handleClick = async (index?: number, pointPosition?: [number, number], event?: MouseEvent) => {
      if (typeof index === 'number') {
        logger.log('Point clicked at index:', index, 'position:', pointPosition);
        
        // Get the original node data using the index
        let originalNode: GraphNode | undefined;
        
        // Try to get the node from our transformed data using the index
        if (index >= 0 && index < transformedData.nodes.length) {
          const nodeData = transformedData.nodes[index];
          originalNode = nodeData;
          logger.log('Found original node by index:', originalNode);
        }
        
        // If we can't find the original node by index, try to query it from Cosmograph
        if (!originalNode && cosmographRef.current && typeof cosmographRef.current.getPointsByIndices === 'function') {
          try {
            logger.log('Querying node data from Cosmograph for index:', index);
            const pointData = await cosmographRef.current.getPointsByIndices([index]);
            
            if (pointData && pointData.numRows && pointData.numRows > 0) {
              // Convert the point data to GraphNode format
              const pointArray = cosmographRef.current.convertCosmographDataToObject(pointData);
              if (pointArray && pointArray.length > 0) {
                const point = pointArray[0];
                originalNode = {
                  id: String(point.id || index),
                  label: String(point.label || point.id || index),
                  node_type: String(point.node_type || 'Unknown'),
                  size: Number(point.centrality || 1),
                  properties: {
                    degree_centrality: Number(point.degree_centrality || 0),
                    pagerank_centrality: Number(point.pagerank_centrality || 0),
                    betweenness_centrality: Number(point.betweenness_centrality || 0),
                    centrality: Number(point.centrality || 0),
                    ...point // Include all other properties
                  }
                } as GraphNode;
                logger.log('Created node from Cosmograph data:', originalNode);
              }
            }
          } catch (error) {
            logger.error('Failed to retrieve point data from Cosmograph:', error);
          }
        }
        
        if (originalNode) {
          const currentTime = Date.now();
          const timeDiff = currentTime - lastClickTimeRef.current;
          const isDoubleClick = timeDiff < 300 && lastClickedNodeRef.current?.id === originalNode.id;
          
          // Clear any existing timeout
          if (doubleClickTimeoutRef.current) {
            clearTimeout(doubleClickTimeoutRef.current);
            doubleClickTimeoutRef.current = null;
          }
          
          if (isDoubleClick) {
            // Double-click detected - select node with Cosmograph visual effects
            selectCosmographNode(originalNode);
            onNodeClick(originalNode);
            onNodeSelect(originalNode.id);
          } else {
            // Single click - show modal and maintain visual selection
            doubleClickTimeoutRef.current = setTimeout(() => {
              // Single click confirmed - show modal and keep node visually selected
              logger.log('Single-click detected on node:', originalNode!.id);
              selectCosmographNode(originalNode!); // Keep visual selection circle
              onNodeClick(originalNode!); // Show modal
              onNodeSelect(originalNode!.id); // Update selection state
            }, 300);
          }
          
          // Update click tracking using refs (no re-render)
          lastClickTimeRef.current = currentTime;
          lastClickedNodeRef.current = originalNode;
        } else {
          logger.warn('Could not find or create node data for index:', index);
        }
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
        <CosmographProvider>
          <Cosmograph
            ref={cosmographRef}
            // Use Data Kit prepared data and configuration
            points={cosmographData.points}
            links={cosmographData.links}
            {...cosmographData.cosmographConfig}
            
            // Override with UI-specific configurations
            fitViewOnInit={true}
            fitViewDelay={1500} // Let nodes settle before fitting view
            fitViewDuration={1000} // Smooth animation duration for initial fit
            initialZoomLevel={1.5}
            disableZoom={false}
            backgroundColor={config.backgroundColor}
            
            // Use Cosmograph v2.0 built-in color strategies
            pointColorStrategy={(() => {
              switch (config.colorScheme) {
                case 'by-type': return 'palette';
                case 'by-centrality': 
                case 'by-pagerank': 
                case 'by-degree': return 'interpolatePalette';
                case 'by-community': return 'palette';
                default: return 'palette';
              }
            })()}
            pointColorPalette={(() => {
              switch (config.colorScheme) {
                case 'by-centrality': return ['#1e3a8a', '#3b82f6', '#60a5fa', '#93c5fd', '#dbeafe']; // Blue gradient
                case 'by-pagerank': return ['#7c2d12', '#ea580c', '#f97316', '#fb923c', '#fed7aa']; // Orange gradient  
                case 'by-degree': return ['#166534', '#16a34a', '#22c55e', '#4ade80', '#bbf7d0']; // Green gradient
                case 'by-community': return ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD'];
                default: {
                  // Use dynamic node type colors from the actual data
                  const nodeTypeColors = Object.values(config.nodeTypeColors);
                  if (nodeTypeColors.length > 0) {
                    return nodeTypeColors;
                  }
                  // Fallback colors if no types configured yet
                  return ['#4ECDC4', '#B794F6', '#F6AD55', '#90CDF4', '#FF6B6B', '#4ADE80'];
                }
              }
            })()}
            
            // Use Cosmograph v2.0 built-in size strategies  
            pointSizeStrategy={'auto'}
            pointSizeRange={[config.minNodeSize * config.sizeMultiplier, config.maxNodeSize * config.sizeMultiplier]}
            
            // Highlighted nodes override (still need custom function for this)
            pointColor={(node: any) => {
              const isHighlighted = highlightedNodes.includes(node.id);
              if (isHighlighted) {
                return 'rgba(255, 215, 0, 0.9)'; // Gold highlight
              }
              // Let the strategy handle normal coloring
              return undefined;
            }}
            
            pointSize={(node: any) => {
              const isHighlighted = highlightedNodes.includes(node.id);
              if (isHighlighted) {
                // Make highlighted nodes 20% larger than strategy-calculated size
                return undefined; // Let strategy calculate, then we'll handle in CSS/other way
              }
              return undefined; // Let strategy handle sizing
            }}
            
            // Interaction
            enableDrag={true}
            enableRightClickRepulsion={true}
            onClick={handleClick}
            renderHoveredNodeRing={true}
            hoveredNodeRingColor="#22d3ee"
            focusedNodeRingColor="#fbbf24"
            nodeGreyoutOpacity={selectedNodes.length > 0 || highlightedNodes.length > 0 ? 0.1 : 1}
            
            // Performance
            pixelRatio={2.5}
            showFPSMonitor={false}
            
            // Zoom behavior
            enableSimulationDuringZoom={true}
            
            // Simulation - Cosmograph v2.0 API
            disableSimulation={config.disableSimulation}
            spaceSize={config.spaceSize}
            randomSeed={config.randomSeed}
            simulationRepulsion={config.repulsion}
            simulationRepulsionTheta={config.simulationRepulsionTheta}
            simulationLinkSpring={config.linkSpring}
            simulationLinkDistance={config.linkDistance}
            simulationGravity={config.gravity}
            simulationCenter={config.centerForce}
            simulationFriction={config.friction}
            simulationDecay={config.simulationDecay}
            simulationRepulsionFromMouse={config.mouseRepulsion}
            
            // Link Properties
            linkWidth={config.linkWidth}
            linkWidthBy={config.linkWidthBy}
            
            // Selection
            showLabelsFor={selectedNodes.map(id => ({ id }))}
          />
        </CosmographProvider>
        
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