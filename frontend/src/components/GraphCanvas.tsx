import React, { useEffect, useRef, forwardRef, useState, useCallback, use } from 'react';
import { Cosmograph, prepareCosmographData } from '@cosmograph/react';
import { GraphNode } from '../api/types';
import type { GraphData } from '../types/graph';
import { useGraphConfig } from '../contexts/GraphConfigProvider';
import { generateNodeTypeColor } from '../utils/nodeTypeColors';
import { logger } from '../utils/logger';
import { hexToRgba, generateHSLColor } from '../utils/colorCache';
import { DataKitCoordinator } from '../utils/DataKitCoordinator';
import { useGraphZoom } from '../hooks/useGraphZoom';
import { useGraphEvents } from '../hooks/useGraphEvents';
import { useSimulation } from '../hooks/useSimulation';
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts';
import { useColorUtils } from '../hooks/useColorUtils';
import { searchIndex } from '../utils/searchIndex';
import { GraphConfigContext } from '../contexts/useGraphConfig';

const dataKitCoordinator = DataKitCoordinator.getInstance();

// Example of React 19's use API for conditional context consumption
// This demonstrates how 'use' can be called conditionally, unlike useContext
function ConditionalConfigConsumer({ shouldUseConfig }: { shouldUseConfig: boolean }) {
  if (!shouldUseConfig) {
    return null; // Early return before using context
  }
  
  // The 'use' API allows conditional consumption after early returns
  const config = use(GraphConfigContext);
  
  if (!config) {
    return <div>Loading config...</div>;
  }
  
  return <div>Config loaded: {config.config.layout}</div>;
}

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
  fitView: (duration?: number, padding?: number) => void;
  fitViewByPointIndices: (indices: number[], duration?: number, padding?: number) => void;
  zoomToPoint: (index: number, duration?: number, scale?: number, canZoomOut?: boolean) => void;
  trackPointPositionsByIndices: (indices: number[]) => void;
  getTrackedPointPositionsMap: () => Map<number, [number, number]> | undefined;
  getTrackedPointPositionsArray: () => Float32Array | undefined;
  // Selection methods
  selectNode: (node: GraphNode, selectAdjacentNodes?: boolean) => void;
  selectNodes: (nodes: GraphNode[]) => void;
  getSelectedNodes: () => GraphNode[];
  unselectNodes: () => void;
  unselectAll: () => void;
  // Focus methods
  focusNode: (node?: GraphNode) => void;
  unfocusNode: () => void;
  // Adjacent nodes
  getAdjacentNodes: (id: string) => GraphNode[] | undefined;
  // Node position methods
  getNodePositions: () => Record<string, { x: number; y: number }>;
  getNodePositionsMap: () => Map<string, [number, number]>;
  restart: () => void;
  start: () => void;
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
  _canvasElement?: HTMLCanvasElement;
}

interface GraphCanvasProps {
  onNodeClick: (node: GraphNode) => void;
  onNodeSelect: (nodeId: string) => void;
  onSelectNodes?: (nodes: GraphNode[]) => void;
  onClearSelection?: () => void;
  onNodeHover?: (node: GraphNode | null) => void;
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
  fitView: (duration?: number, padding?: number) => void;
  fitViewByPointIndices: (indices: number[], duration?: number, padding?: number) => void;
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

interface GraphCanvasComponentProps extends GraphCanvasProps {
  nodes: GraphNode[];
  links: GraphLink[];
}

const GraphCanvasComponent = forwardRef<GraphCanvasHandle, GraphCanvasComponentProps>(
  ({ onNodeClick, onNodeSelect, onSelectNodes, onClearSelection, onNodeHover, selectedNodes, highlightedNodes, className, stats, nodes, links }, ref) => {
    const cosmographRef = useRef<CosmographRef | null>(null);
    const [isReady, setIsReady] = useState(false);
    const [isCanvasReady, setIsCanvasReady] = useState(false);
    const [cosmographData, setCosmographData] = useState<{ nodes: GraphNode[], links: GraphLink[] } | null>(null);
    const [dataKitError, setDataKitError] = useState<string | null>(null);
    const [isDataPreparing, setIsDataPreparing] = useState(false);
    const { config, setCosmographRef } = useGraphConfig();
    
    // Track current data for incremental updates
    const [currentNodes, setCurrentNodes] = useState<GraphNode[]>([]);
    const [currentLinks, setCurrentLinks] = useState<GraphLink[]>([]);
    
    // Simulation control state
    const [keepRunning, setKeepRunning] = useState(false);
    const simulationTimerRef = useRef<NodeJS.Timeout | null>(null);
    
    // Track simulation state for debugging incremental updates
    const [isSimulationActive, setIsSimulationActive] = useState(false);
    const lastResumeTimeRef = useRef<number>(0);
    
    // Flag to prevent Data Kit reprocessing during incremental updates
    const isIncrementalUpdateRef = useRef(false);
    
    // Add component ID for debugging multiple instances
    const componentId = useRef(Math.random().toString(36).substr(2, 9));
    
    // Update current data tracking and search index when props change
    useEffect(() => {
      setCurrentNodes(nodes);
      setCurrentLinks(links);
      
      // Update search index for fast searching
      if (nodes.length > 0) {
        searchIndex.buildIndex(nodes);
        logger.log('Search index updated with', nodes.length, 'nodes');
      }
    }, [nodes, links]);
    
    // Double-click detection using refs to avoid re-renders
    const lastClickTimeRef = useRef<number>(0);
    const lastClickedNodeRef = useRef<GraphNode | null>(null);
    const doubleClickTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    
    // Selection handlers for keyboard shortcuts
    const handleSelectAll = useCallback(() => {
      if (!cosmographRef.current || !currentNodes.length) return;
      
      // Use onSelectNodes if available (for multi-select)
      if (onSelectNodes) {
        onSelectNodes(currentNodes);
      } else {
        // Fallback: Select all visible nodes in Cosmograph
        if (cosmographRef.current.selectNodes) {
          cosmographRef.current.selectNodes(currentNodes);
        }
        
        // For React state, we need to call onNodeSelect for each node
        // since it expects a single node ID
        currentNodes.forEach(node => {
          if (!selectedNodes.includes(node.id)) {
            onNodeSelect?.(node.id);
          }
        });
      }
    }, [currentNodes, onNodeSelect, onSelectNodes, selectedNodes]);
    
    const handleDeselectAll = useCallback(() => {
      onClearSelection?.();
    }, [onClearSelection]);
    
    // Initialize keyboard shortcuts
    useKeyboardShortcuts({
      onSelectAll: handleSelectAll,
      onDeselectAll: handleDeselectAll,
      cosmographRef
    });
    
    // Search functionality using indexed search
    const performSearch = useCallback(() => {
      if (!cosmographRef.current || !config.searchTerm || config.searchTerm.trim() === '') {
        // Clear search highlights if search is empty
        return;
      }
      
      // Use search index for fast search
      const matchingNodes = searchIndex.search(config.searchTerm, {
        limit: 500,
        fuzzy: false
      });
      
      if (matchingNodes.length > 0) {
        // Select matching nodes
        const matchingIds = matchingNodes.map(node => node.id);
        if (onSelectNodes) {
          onSelectNodes(matchingNodes);
        } else {
          // Fallback to individual selection
          matchingIds.forEach(id => onNodeSelect?.(id));
        }
        
        // Focus on the first few matches
        if (cosmographRef.current.fitViewByPointIndices && matchingNodes.length <= 10) {
          const nodeIndices = matchingNodes
            .slice(0, 10)
            .map(node => currentNodes.findIndex(n => n.id === node.id))
            .filter(idx => idx >= 0);
          
          if (nodeIndices.length > 0) {
            cosmographRef.current.fitViewByPointIndices(nodeIndices, 1000, 0.2);
          }
        }
      }
      
      logger.log(`Search found ${matchingNodes.length} nodes for query: ${config.searchTerm}`);
    }, [config.searchTerm, currentNodes, onNodeSelect, onSelectNodes]);
    
    // Trigger search when searchTerm changes
    useEffect(() => {
      if (config.queryType === 'search' && config.searchTerm) {
        performSearch();
      }
    }, [config.searchTerm, config.queryType, performSearch]);
    
    // Memoize color strategy and color by field - moved here before dataKitConfig
    const { pointColorStrategy, pointColorBy } = React.useMemo(() => {
      switch (config.colorScheme) {
        case 'by-type': 
          return { pointColorStrategy: 'map', pointColorBy: 'node_type' };
        case 'by-centrality': 
          return { pointColorStrategy: 'interpolate', pointColorBy: 'degree_centrality' };
        case 'by-pagerank': 
          return { pointColorStrategy: 'interpolate', pointColorBy: 'pagerank_centrality' };
        case 'by-degree': 
          return { pointColorStrategy: 'interpolate', pointColorBy: 'degree_centrality' };
        case 'by-community': 
          return { pointColorStrategy: 'auto', pointColorBy: 'cluster' };
        default: 
          return { pointColorStrategy: 'map', pointColorBy: 'node_type' };
      }
    }, [config.colorScheme]);
    
    // Memoize size by field based on mapping - moved here before dataKitConfig
    const pointSizeBy = React.useMemo(() => {
      switch (config.sizeMapping) {
        case 'uniform': return undefined; // Will use uniform size
        case 'degree': return 'degree_centrality';
        case 'betweenness': return 'betweenness_centrality';
        case 'pagerank': return 'pagerank_centrality';
        case 'importance': return 'eigenvector_centrality';
        case 'connections': return 'degree_centrality'; // Same as degree
        case 'custom': return 'centrality'; // Default centrality field
        default: return 'centrality';
      }
    }, [config.sizeMapping]);

    // Data Kit configuration for Cosmograph v2.0 - stable config to prevent reprocessing
    const dataKitConfig = React.useMemo(() => ({
      points: {
        pointIdBy: 'id',              // Required: unique identifier field
        pointIndexBy: 'index',        // Required: ordinal index field
        pointLabelBy: 'label',        // Node display labels
        pointColorBy: pointColorBy || 'node_type',    // Dynamic color by field based on scheme
        pointSizeBy: pointSizeBy || 'centrality',    // Dynamic size by field based on mapping
        pointIncludeColumns: ['degree_centrality', 'pagerank_centrality', 'betweenness_centrality', 'eigenvector_centrality', 'created_at', 'created_at_timestamp'] // Include additional columns including temporal data
      },
      links: {
        linkSourceBy: 'source',         // Source node ID field
        linkSourceIndexBy: 'sourceIndex', // Required: source node index
        linkTargetBy: 'target',         // Target node ID field (singular for single target)
        linkTargetIndexBy: 'targetIndex', // Required: target node index
        linkColorBy: 'edge_type',      // Link color by type
        linkWidthBy: config.linkWidthBy || 'weight',         // Dynamic width column
        linkIncludeColumns: ['created_at', 'updated_at', 'weight', 'strength', 'confidence'] // Include various link properties
      }
    }), [pointColorBy, pointSizeBy, config.linkWidthBy]);

    // Track previous data to prevent unnecessary reprocessing
    const prevDataRef = useRef<{ nodeCount: number; linkCount: number }>({ nodeCount: 0, linkCount: 0 });
    
    // Data Kit preparation effect
    useEffect(() => {
      // Skip reprocessing if we're in the middle of an incremental update
      if (isIncrementalUpdateRef.current) {
        return;
      }
      
      if (!nodes || !links || nodes.length === 0) {
        setCosmographData(null);
        setDataKitError(null);
        prevDataRef.current = { nodeCount: 0, linkCount: 0 };
        return;
      }
      
      // Skip if data hasn't actually changed (same counts)
      if (prevDataRef.current.nodeCount === nodes.length && 
          prevDataRef.current.linkCount === links.length) {
        return;
      }
      
      prevDataRef.current = { nodeCount: nodes.length, linkCount: links.length };

      let cancelled = false;
      
      const prepareData = async () => {
        await dataKitCoordinator.executeDataKit(async () => {
          try {
            setIsDataPreparing(true);
            setDataKitError(null);
            
          
          // Transform data to match Data Kit expectations with consistent types
          const transformedNodes = nodes.map((node, index) => {
            // Extract created_at from properties if it exists there
            const createdAt = node.properties?.created_at || node.created_at || node.properties?.created || null;
            
            
            const degree = Number(node.properties?.degree_centrality || 0);
            
            const nodeData = {
              id: String(node.id), // Ensure string type
              index: index, // Required for v2.0: ordinal index
              label: String(node.label || node.id), // Ensure string type
              node_type: String(node.node_type || 'Unknown'), // Ensure string type
              centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1), // Ensure number type
              // Add cluster assignment based on node type for more meaningful clustering
              cluster: String(node.node_type || 'Unknown'),
              // Add cluster strength - entities of the same type will be attracted to each other
              clusterStrength: 0.7, // Strong clustering by type (0-1 range)
              // Add other commonly used properties with type safety
              degree_centrality: degree,
              pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
              betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
              eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0),
              // Include temporal data for timeline - keep as string (timeline can parse ISO dates)
              created_at: createdAt,
              // Also include as timestamp for timeline
              created_at_timestamp: createdAt ? new Date(createdAt).getTime() : null
            };
            
            // Validate that all required fields are present and valid
            if (!nodeData.id || nodeData.id === 'undefined') {
              logger.warn('Invalid node ID found:', node);
            }
            
            return nodeData;
          }).filter(node => node.id && node.id !== 'undefined'); // Remove invalid nodes

          // Create a map for quick node index lookup
          const nodeIndexMap = new Map<string, number>();
          transformedNodes.forEach((node, index) => {
            nodeIndexMap.set(node.id, index);
          });

          logger.log('GraphCanvas: Processing links:', links.length, 'nodes in map:', nodeIndexMap.size);
          
          const transformedLinks = links.map(link => {
            const sourceIndex = nodeIndexMap.get(String(link.source));
            const targetIndex = nodeIndexMap.get(String(link.target));
            
            const linkData = {
              source: String(link.source), // Ensure string type
              sourceIndex: sourceIndex !== undefined ? sourceIndex : -1, // Required for v2.0
              target: String(link.target), // Ensure string type
              targetIndex: targetIndex !== undefined ? targetIndex : -1, // Required for v2.0
              edge_type: String(link.edge_type || 'default'), // Ensure string type
              weight: Number(link.weight || 1), // Ensure number type
              // Include temporal data if available
              created_at: link.created_at,
              updated_at: link.updated_at
            };
            
            // Validate that source and target exist and have valid indices
            if (!linkData.source || !linkData.target || linkData.source === 'undefined' || linkData.target === 'undefined' || 
                linkData.sourceIndex === -1 || linkData.targetIndex === -1) {
              logger.warn('Invalid link found:', link, 'indices:', linkData.sourceIndex, linkData.targetIndex);
            }
            
            return linkData;
          }).filter(link => link.source && link.target && link.source !== 'undefined' && link.target !== 'undefined' && 
                           link.sourceIndex !== -1 && link.targetIndex !== -1); // Remove invalid links
          
          logger.log('GraphCanvas: Transformed links:', transformedLinks.length, 'valid links');

          
          // Log node type distribution for color mapping debugging
          const nodeTypeDistribution = transformedNodes.reduce((acc, node) => {
            acc[node.node_type] = (acc[node.node_type] || 0) + 1;
            return acc;
          }, {} as Record<string, number>);
          
          // Validate we have valid data before proceeding
          if (transformedNodes.length === 0) {
            throw new Error('No valid nodes found after transformation');
          }
          
          // BYPASS Data Kit - it's causing issues with links configuration
          // Use direct data instead
          logger.log('GraphCanvas: Bypassing Data Kit, using direct data');
          
          if (!cancelled) {
            setCosmographData({
              points: transformedNodes,
              links: transformedLinks,
              cosmographConfig: dataKitConfig
            });
          }
        } catch (error) {
          if (!cancelled) {
            const errorMessage = error instanceof Error ? error.message : 'Unknown error';
            logger.error('GraphCanvas: Data Kit preparation failed:', errorMessage);
            setDataKitError(errorMessage);
            
            // Fallback to direct data passing
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
        });
      };

      prepareData();
      
      return () => {
        cancelled = true;
      };
    }, [nodes, links, dataKitConfig]);

    // Log when simulation should be ready
    useEffect(() => {
      if (cosmographData && isCanvasReady) {
        logger.log('GraphCanvas: Data loaded and canvas ready, simulation should start automatically');
      }
    }, [cosmographData, isCanvasReady]);

    // Canvas readiness tracking with single polling mechanism and WebGL context loss recovery
    const intervalRef = useRef<NodeJS.Timeout | null>(null);
    const [webglContextLost, setWebglContextLost] = useState(false);
    
    // WebGL context loss recovery
    const setupWebGLContextRecovery = useCallback(() => {
      const canvas = cosmographRef.current?._canvasElement;
      if (!canvas) return;

      const handleContextLost = (event: Event) => {
        event.preventDefault();
        setWebglContextLost(true);
      };

      const handleContextRestored = () => {
        setWebglContextLost(false);
        
        // Trigger re-render by restarting the simulation
        try {
          cosmographRef.current?.restart();
        } catch (error) {
          // WebGL context recovery error
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
            // Set the ref for use in GraphConfigProvider
            console.log('GraphCanvas: Setting cosmographRef');
            setCosmographRef(cosmographRef);
            setIsReady(true);
            
            // Set up WebGL context loss recovery
            webglCleanup = setupWebGLContextRecovery();
            
            // Start canvas polling with optimized intervals
            const pollCanvas = () => {
              const hasCanvas = !!cosmographRef.current?._canvasElement;
              
              setIsCanvasReady(prevReady => {
                if (hasCanvas !== prevReady) {
                  // State change detected, no additional action needed
                }
                return hasCanvas;
              });
              
              // Stop polling once canvas is found or after reasonable attempts
              if (!hasCanvas && checkCount < 20) { // Max 3 seconds of polling  
                checkCount++;
                // Progressive delay: 100ms, 150ms, 200ms, etc.
                const delay = Math.min(100 + (checkCount * 50), 500);
                // Clear any existing timeout before setting new one
                if (intervalRef.current) {
                  clearTimeout(intervalRef.current);
                }
                intervalRef.current = setTimeout(pollCanvas, delay);
              } else if (!hasCanvas) {
                // Canvas not found after polling, log warning
                logger.warn('Canvas element not found after polling');
                setIsCanvasReady(false);
              }
            };
            
            // Start canvas polling immediately
            pollCanvas();
          } catch (error) {
            // Canvas setup error
          }
        } else {
          // Keep polling for cosmographRef with exponential backoff for up to 3 seconds
          if (checkCount < 30) {
            checkCount++;
            // Exponential backoff: 50ms, 100ms, 150ms, 200ms, etc.
            const delay = Math.min(50 + (checkCount * 10), 200);
            // Use intervalRef to track this timeout as well
            if (intervalRef.current) {
              clearTimeout(intervalRef.current);
            }
            intervalRef.current = setTimeout(pollCosmographRef, delay);
          } else {
            // Set a fallback timeout to prevent permanent blocking
            setIsReady(false);
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
    
    // Memoize node types for color generation
    const allNodeTypes = React.useMemo(() => {
      if (!nodes || nodes.length === 0) return [];
      return [...new Set(nodes.map(n => n.node_type).filter(Boolean))].sort();
    }, [nodes]);
    
    
    // Memoize color palette based on scheme
    const pointColorPalette = React.useMemo(() => {
      if (config.colorScheme === 'by-type') {
        return undefined; // Use pointColorByMap for type-based coloring
      }
      
      // For gradient-based schemes, use gradient from low to high color
      if (['by-centrality', 'by-pagerank', 'by-degree'].includes(config.colorScheme)) {
        return [config.gradientLowColor, config.gradientHighColor];
      }
      
      // For community detection, use a diverse palette
      if (config.colorScheme === 'by-community') {
        return ['#ff6b6b', '#4ecdc4', '#45b7d1', '#f39c12', '#e74c3c', '#9b59b6', '#3498db', '#2ecc71'];
      }
      
      return undefined;
    }, [config.colorScheme, config.gradientLowColor, config.gradientHighColor]);
    
    // Memoize color by function
    const pointColorByFn = React.useMemo(() => {
      if (config.colorScheme !== 'by-type') return undefined;
      
      return (nodeType: string) => {
        const typeColor = config.nodeTypeColors[nodeType];
        if (typeColor) {
          return typeColor;
        }
        
        const typeIndex = allNodeTypes.indexOf(nodeType);
        const generatedColor = generateNodeTypeColor(nodeType, typeIndex);
        return generatedColor;
      };
    }, [config.colorScheme, config.nodeTypeColors, allNodeTypes]);
    
    // Memoize link color function based on scheme
    const linkColorFn = React.useMemo(() => {
      if (!config.linkColorScheme || config.linkColorScheme === 'uniform') {
        return undefined; // Use default link color
      }
      
      // Pre-calculate weight ranges for performance
      const weights = currentLinks.map(l => l.weight || 1);
      const maxWeight = Math.max(...weights);
      const minWeight = Math.min(...weights);
      const weightRange = maxWeight - minWeight || 1;
      
      return (link: GraphLink) => {
        switch (config.linkColorScheme) {
          case 'by-weight': {
            // Color by edge weight - interpolate between low and high colors
            const weight = link.weight || 1;
            const normalized = (weight - minWeight) / weightRange;
            // Interpolate between link color and a highlight color
            const r = Math.round(102 + (239 - 102) * normalized); // From #666 to #ef4444
            const g = Math.round(102 + (68 - 102) * normalized);
            const b = Math.round(102 + (68 - 102) * normalized);
            return `rgb(${r}, ${g}, ${b})`;
          }
            
          case 'by-type': {
            // Color by edge type
            const edgeType = link.edge_type || 'default';
            const typeColors: Record<string, string> = {
              'relates_to': '#4ECDC4',
              'causes': '#F6AD55',
              'precedes': '#B794F6',
              'contains': '#90CDF4',
              'default': config.linkColor
            };
            return typeColors[edgeType] || config.linkColor;
          }
            
          case 'by-distance': {
            // Color by link distance/length
            const sourceNode = currentNodes.find(n => n.id === link.source);
            const targetNode = currentNodes.find(n => n.id === link.target);
            if (sourceNode?.x !== undefined && targetNode?.x !== undefined) {
              const distance = Math.sqrt(
                Math.pow(targetNode.x - sourceNode.x, 2) + 
                Math.pow(targetNode.y - sourceNode.y, 2)
              );
              const maxDist = 500; // Approximate max distance
              const normalizedDist = Math.min(distance / maxDist, 1);
              // Fade from bright to dim based on distance
              const opacity = Math.round(255 * (1 - normalizedDist * 0.7));
              return `rgba(102, 102, 102, ${opacity / 255})`;
            }
            return config.linkColor;
          }
            
          case 'node-gradient': {
            // Gradient from source to target node colors
            const sourceNodeColor = config.nodeTypeColors[currentNodes.find(n => n.id === link.source)?.node_type || ''];
            const targetNodeColor = config.nodeTypeColors[currentNodes.find(n => n.id === link.target)?.node_type || ''];
            // For simplicity, use source node color (true gradient would require custom shader)
            return sourceNodeColor || config.linkColor;
          }
            
          case 'by-community': {
            // Color bridges between communities differently
            const sourceCommunity = currentNodes.find(n => n.id === link.source)?.cluster;
            const targetCommunity = currentNodes.find(n => n.id === link.target)?.cluster;
            if (sourceCommunity !== targetCommunity) {
              return '#FF6B6B'; // Highlight inter-community links
            }
            return config.linkColor;
          }
            
          default:
            return config.linkColor;
        }
      };
    }, [config.linkColorScheme, config.linkColor, config.nodeTypeColors, currentLinks, currentNodes]);

    // Memoize point color function
    const pointColorFn = React.useCallback((node: GraphNode) => {
      const isHighlighted = highlightedNodes.includes(node.id);
      if (isHighlighted) {
        return 'rgba(255, 215, 0, 0.9)';
      }
      
      if (config.colorScheme !== 'by-type') {
        return undefined;
      }
      
      return undefined;
    }, [highlightedNodes, config.colorScheme]);
    
    // Memoize point size function
    const pointSizeFn = React.useCallback((node: GraphNode) => {
      // Handle uniform size mapping
      if (config.sizeMapping === 'uniform') {
        return (config.minNodeSize + config.maxNodeSize) / 2 * config.sizeMultiplier;
      }
      const isHighlighted = highlightedNodes.includes(node.id);
      if (isHighlighted) {
        return undefined;
      }
      return undefined;
    }, [highlightedNodes, config.minNodeSize, config.maxNodeSize, config.sizeMapping, config.sizeMultiplier]);
    
    // Improved throttling for mouse move with requestAnimationFrame
    const lastHoverTimeRef = useRef<number>(0);
    const lastHoveredIndexRef = useRef<number | undefined>(undefined);
    const hoverAnimationFrameRef = useRef<number | null>(null);
    const pendingHoverRef = useRef<{ index: number | undefined } | null>(null);
    
    const handleMouseMove = React.useCallback((index: number | undefined) => {
      // Skip if same index
      if (index === lastHoveredIndexRef.current) {
        return;
      }
      
      // Store pending hover
      pendingHoverRef.current = { index };
      
      // Cancel previous animation frame
      if (hoverAnimationFrameRef.current) {
        cancelAnimationFrame(hoverAnimationFrameRef.current);
      }
      
      // Schedule update on next animation frame
      hoverAnimationFrameRef.current = requestAnimationFrame(() => {
        const now = Date.now();
        
        // Throttle to max 30fps (33ms) for better performance
        if (now - lastHoverTimeRef.current < 33) {
          // Reschedule for next frame
          hoverAnimationFrameRef.current = requestAnimationFrame(() => {
            if (pendingHoverRef.current) {
              const { index } = pendingHoverRef.current;
              lastHoverTimeRef.current = now;
              lastHoveredIndexRef.current = index;
              
              if (index !== undefined && index >= 0) {
                const hoveredNode = currentNodes[index];
                if (hoveredNode) {
                  onNodeHover?.(hoveredNode);
                }
              } else {
                onNodeHover?.(null);
              }
              
              pendingHoverRef.current = null;
            }
          });
          return;
        }
        
        if (pendingHoverRef.current) {
          const { index } = pendingHoverRef.current;
          lastHoverTimeRef.current = now;
          lastHoveredIndexRef.current = index;
          
          if (index !== undefined && index >= 0) {
            const hoveredNode = currentNodes[index];
            if (hoveredNode) {
              onNodeHover?.(hoveredNode);
            }
          } else {
            onNodeHover?.(null);
          }
          
          pendingHoverRef.current = null;
        }
      });
    }, [currentNodes, onNodeHover]);

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
            } else {
              logger.warn('Could not find node index for selection:', node.id);
            }
          } else if (typeof cosmographRef.current.selectPoints === 'function') {
            const nodeIndex = transformedData.nodes.findIndex(n => n.id === node.id);
            if (nodeIndex >= 0) {
              cosmographRef.current.selectPoints([nodeIndex]);
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
              
              // For multiple nodes, use fitViewByPointIndices to show all selected nodes
              if (nodeIndices.length > 1) {
                // Call fitViewByPointIndices after this function completes
                setTimeout(() => {
                  if (cosmographRef.current && typeof cosmographRef.current.fitViewByPointIndices === 'function') {
                    cosmographRef.current.fitViewByPointIndices(nodeIndices, config.fitViewDuration, config.fitViewPadding);
                  }
                }, 0);
              }
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
    }, [transformedData.nodes, config.fitViewDuration, config.fitViewPadding]);

    // Method to clear Cosmograph selection and return to default state
    const clearCosmographSelection = useCallback(() => {
      if (cosmographRef.current) {
        try {
          // Use native Cosmograph methods to clear selection
          if (typeof cosmographRef.current.unselectAll === 'function') {
            cosmographRef.current.unselectAll();
          } else if (typeof cosmographRef.current.unselectAllPoints === 'function') {
            cosmographRef.current.unselectAllPoints();
          } else if (typeof cosmographRef.current.selectPoints === 'function') {
            cosmographRef.current.selectPoints([]);
          } else {
            logger.warn('No clear selection method found on Cosmograph instance');
          }
          
          // Clear focused node using native method
          if (typeof cosmographRef.current.unfocusNode === 'function') {
            cosmographRef.current.unfocusNode();
          } else if (typeof cosmographRef.current.setFocusedPoint === 'function') {
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
        // Use the official Cosmograph v2.0 API method with animation duration
        const currentZoom = cosmographRef.current.getZoomLevel();
        if (currentZoom !== undefined) {
          const newZoom = Math.min(currentZoom * 1.5, 10);
          cosmographRef.current.setZoomLevel(newZoom, config.fitViewDuration);
        } else {
          logger.warn('Could not get current zoom level for zoom in');
        }
      } catch (error) {
        logger.warn('Zoom in failed:', error);
      }
    }, [config.fitViewDuration]);

    const zoomOut = useCallback(() => {
      if (!cosmographRef.current) return;
      
      try {
        // Use the official Cosmograph v2.0 API method with animation duration
        const currentZoom = cosmographRef.current.getZoomLevel();
        if (currentZoom !== undefined) {
          const newZoom = Math.max(currentZoom / 1.5, 0.1);
          cosmographRef.current.setZoomLevel(newZoom, config.fitViewDuration);
        } else {
          logger.warn('Could not get current zoom level for zoom out');
        }
      } catch (error) {
        logger.warn('Zoom out failed:', error);
      }
    }, [config.fitViewDuration]);

    const fitView = useCallback(() => {
      if (!cosmographRef.current) return;
      
      // Ensure canvas is ready
      if (!isCanvasReady) {
        logger.warn('GraphCanvas: Cannot fitView - canvas not ready');
        return;
      }
      
      // Ensure we have data (nodes are required, links are optional)
      if (!currentNodes.length) {
        logger.warn('GraphCanvas: Cannot fitView - no nodes');
        return;
      }
      
      try {
        logger.log('GraphCanvas: Calling fitView with duration:', config.fitViewDuration, 'padding:', config.fitViewPadding);
        
        // Call fitView directly without pausing simulation
        // Cosmograph v2.0 handles the animation smoothly without needing to pause
        cosmographRef.current.fitView(config.fitViewDuration, config.fitViewPadding);
        
      } catch (error) {
        logger.warn('Fit view failed:', error);
      }
    }, [config.fitViewDuration, config.fitViewPadding, currentNodes.length, isCanvasReady]);

    const fitViewByPointIndices = useCallback((indices: number[], duration?: number, padding?: number) => {
      if (!cosmographRef.current) return;
      
      try {
        // Use the Cosmograph v2.0 fitViewByPointIndices method with config defaults
        const actualDuration = duration !== undefined ? duration : config.fitViewDuration;
        const actualPadding = padding !== undefined ? padding : config.fitViewPadding;
        cosmographRef.current.fitViewByPointIndices(indices, actualDuration, actualPadding);
      } catch (error) {
        logger.warn('Fit view by indices failed:', error);
      }
    }, [config.fitViewDuration, config.fitViewPadding]);

    const zoomToPoint = useCallback((index: number, duration?: number, scale?: number, canZoomOut?: boolean) => {
      if (!cosmographRef.current) return;
      
      try {
        // Ensure simulation is running for smooth zoom animation
        if (typeof cosmographRef.current.start === 'function') {
          cosmographRef.current.start(0.1); // Start with low energy just for the zoom
        }
        
        // Use the Cosmograph v2.0 zoomToPoint method with config defaults
        const actualDuration = duration !== undefined ? duration : config.fitViewDuration;
        const actualScale = scale !== undefined ? scale : 6.0; // Good zoom scale for detailed focus
        const actualCanZoomOut = canZoomOut !== undefined ? canZoomOut : true;
        cosmographRef.current.zoomToPoint(index, actualDuration, actualScale, actualCanZoomOut);
      } catch (error) {
        logger.warn('Zoom to point failed:', error);
      }
    }, [config.fitViewDuration]);

    const trackPointPositionsByIndices = useCallback((indices: number[]) => {
      if (!cosmographRef.current) return;
      
      try {
        cosmographRef.current.trackPointPositionsByIndices(indices);
      } catch (error) {
        logger.warn('Track point positions failed:', error);
      }
    }, []);

    const getTrackedPointPositionsMap = useCallback(() => {
      if (!cosmographRef.current) return undefined;
      
      try {
        return cosmographRef.current.getTrackedPointPositionsMap();
      } catch (error) {
        logger.warn('Get tracked point positions failed:', error);
        return undefined;
      }
    }, []);

    // Rectangle selection methods
    const activateRectSelection = useCallback(() => {
      if (!cosmographRef.current) return;
      
      try {
        cosmographRef.current.activateRectSelection();
      } catch (error) {
        logger.warn('Activate rect selection failed:', error);
      }
    }, []);

    const deactivateRectSelection = useCallback(() => {
      if (!cosmographRef.current) return;
      
      try {
        cosmographRef.current.deactivateRectSelection();
      } catch (error) {
        logger.warn('Deactivate rect selection failed:', error);
      }
    }, []);

    const selectPointsInRect = useCallback((selection: [[number, number], [number, number]] | null, addToSelection = false) => {
      if (!cosmographRef.current) return;
      
      try {
        cosmographRef.current.selectPointsInRect(selection, addToSelection);
      } catch (error) {
        logger.warn('Select points in rect failed:', error);
      }
    }, []);

    // Polygonal selection methods
    const activatePolygonalSelection = useCallback(() => {
      if (!cosmographRef.current) return;
      
      try {
        cosmographRef.current.activatePolygonalSelection();
      } catch (error) {
        logger.warn('Activate polygonal selection failed:', error);
      }
    }, []);

    const deactivatePolygonalSelection = useCallback(() => {
      if (!cosmographRef.current) return;
      
      try {
        cosmographRef.current.deactivatePolygonalSelection();
      } catch (error) {
        logger.warn('Deactivate polygonal selection failed:', error);
      }
    }, []);

    const selectPointsInPolygon = useCallback((polygonPoints: [number, number][], addToSelection = false) => {
      if (!cosmographRef.current) return;
      
      try {
        cosmographRef.current.selectPointsInPolygon(polygonPoints, addToSelection);
      } catch (error) {
        logger.warn('Select points in polygon failed:', error);
      }
    }, []);

    // Get connected nodes
    const getConnectedPointIndices = useCallback((index: number): number[] | undefined => {
      if (!cosmographRef.current) return undefined;
      
      try {
        return cosmographRef.current.getConnectedPointIndices(index);
      } catch (error) {
        logger.warn('Get connected point indices failed:', error);
        return undefined;
      }
    }, []);

    // Search for nodes by exact property values
    const getPointIndicesByExactValues = useCallback((keyValues: Record<string, unknown>): number[] | undefined => {
      if (!cosmographRef.current) return undefined;
      
      try {
        return cosmographRef.current.getPointIndicesByExactValues(keyValues);
      } catch (error) {
        logger.warn('Get point indices by exact values failed:', error);
        return undefined;
      }
    }, []);

    // Incremental update methods
    const addIncrementalData = useCallback(async (newNodes: GraphNode[], newLinks: GraphLink[], runSimulation = false) => {
      if (!cosmographRef.current) return;
      
      try {
        // Set flag to prevent main Data Kit effect from running
        isIncrementalUpdateRef.current = true;
        
        // Merge new data with existing data
        const updatedNodes = [...currentNodes, ...newNodes];
        const updatedLinks = [...currentLinks, ...newLinks];
        
        // Update internal state
        setCurrentNodes(updatedNodes);
        setCurrentLinks(updatedLinks);
        
        // Transform and use Cosmograph's setData directly for efficiency
        if (cosmographRef.current.setData && updatedNodes.length > 0) {
          const transformedNodes = updatedNodes.map(node => ({
            id: String(node.id),
            label: String(node.label || node.id),
            node_type: String(node.node_type || 'Unknown'),
            centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
            cluster: String(node.node_type || 'Unknown'),
            clusterStrength: 0.7,
            degree_centrality: Number(node.properties?.degree_centrality || 0),
            pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
            betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
            eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0),
            // Include temporal data for timeline
            created_at: node.properties?.created_at || node.created_at || node.properties?.created || null,
            created_at_timestamp: (node.properties?.created_at || node.created_at || node.properties?.created) ? new Date(node.properties?.created_at || node.created_at || node.properties?.created).getTime() : null
          }));
          
          const transformedLinks = updatedLinks.map(link => ({
            source: String(link.source),
            target: String(link.target),
            edge_type: String(link.edge_type || 'default'),
            weight: Number(link.weight || 1)
          }));
          
          // Use direct setData without Data Kit reprocessing for better performance
          cosmographRef.current.setData(transformedNodes, transformedLinks, runSimulation);
        }
      } catch (error) {
        logger.error('Incremental data update failed:', error);
      } finally {
        // Reset flag after a brief delay
        setTimeout(() => {
          isIncrementalUpdateRef.current = false;
        }, 100);
      }
    }, [currentNodes, currentLinks]);
    
    const updateNodes = useCallback(async (updatedNodes: GraphNode[]) => {
      if (!cosmographRef.current?.setData) return;
      
      try {
        isIncrementalUpdateRef.current = true;
        
        // Create a map for quick lookup
        const updateMap = new Map(updatedNodes.map(node => [node.id, node]));
        
        // Update existing nodes
        const newCurrentNodes = currentNodes.map(node => 
          updateMap.has(node.id) ? updateMap.get(node.id)! : node
        );
        
        setCurrentNodes(newCurrentNodes);
        
        // Transform and update directly
        const transformedNodes = newCurrentNodes.map(node => ({
          id: String(node.id),
          label: String(node.label || node.id),
          node_type: String(node.node_type || 'Unknown'),
          centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
          degree_centrality: Number(node.properties?.degree_centrality || 0),
          pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
          betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
          eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0),
          // Include temporal data for timeline
          created_at: node.properties?.created_at || node.created_at || node.properties?.created || null,
          created_at_timestamp: (node.properties?.created_at || node.created_at || node.properties?.created) ? new Date(node.properties?.created_at || node.created_at || node.properties?.created).getTime() : null,
          // Cluster by node type for proper grouping
          cluster: String(node.node_type || 'Unknown'),
          clusterStrength: 0.7 // Strong clustering by type (0-1 range)
        }));
        
        const transformedLinks = currentLinks.map(link => ({
          source: String(link.source),
          target: String(link.target),
          edge_type: String(link.edge_type || 'default'),
          weight: Number(link.weight || 1)
        }));
        
        cosmographRef.current.setData(transformedNodes, transformedLinks, false);
      } catch (error) {
        logger.error('Node update failed:', error);
      } finally {
        setTimeout(() => {
          isIncrementalUpdateRef.current = false;
        }, 100);
      }
    }, [currentNodes, currentLinks]);
    
    const updateLinks = useCallback(async (updatedLinks: GraphLink[]) => {
      if (!cosmographRef.current?.setData) return;
      
      try {
        isIncrementalUpdateRef.current = true;
        
        // Create a map for quick lookup by source-target pair
        const updateMap = new Map(updatedLinks.map(link => [`${link.source}-${link.target}`, link]));
        
        // Update existing links
        const newCurrentLinks = currentLinks.map(link => {
          const key = `${link.source}-${link.target}`;
          return updateMap.has(key) ? updateMap.get(key)! : link;
        });
        
        setCurrentLinks(newCurrentLinks);
        
        // Transform and update directly
        const transformedNodes = currentNodes.map(node => ({
          id: String(node.id),
          label: String(node.label || node.id),
          node_type: String(node.node_type || 'Unknown'),
          centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
          degree_centrality: Number(node.properties?.degree_centrality || 0),
          pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
          betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
          eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0),
          // Include temporal data for timeline
          created_at: node.properties?.created_at || node.created_at || node.properties?.created || null,
          created_at_timestamp: (node.properties?.created_at || node.created_at || node.properties?.created) ? new Date(node.properties?.created_at || node.created_at || node.properties?.created).getTime() : null,
          // Cluster by node type for proper grouping
          cluster: String(node.node_type || 'Unknown'),
          clusterStrength: 0.7 // Strong clustering by type (0-1 range)
        }));
        
        const transformedLinks = newCurrentLinks.map(link => ({
          source: String(link.source),
          target: String(link.target),
          edge_type: String(link.edge_type || 'default'),
          weight: Number(link.weight || 1)
        }));
        
        cosmographRef.current.setData(transformedNodes, transformedLinks, false);
      } catch (error) {
        logger.error('Link update failed:', error);
      } finally {
        setTimeout(() => {
          isIncrementalUpdateRef.current = false;
        }, 100);
      }
    }, [currentLinks, currentNodes]);
    
    const removeNodes = useCallback(async (nodeIds: string[]) => {
      if (!cosmographRef.current?.setData) return;
      
      try {
        isIncrementalUpdateRef.current = true;
        
        const nodeIdSet = new Set(nodeIds);
        
        // Remove nodes
        const filteredNodes = currentNodes.filter(node => !nodeIdSet.has(node.id));
        
        // Remove links connected to removed nodes
        const filteredLinks = currentLinks.filter(link => 
          !nodeIdSet.has(link.source) && !nodeIdSet.has(link.target)
        );
        
        setCurrentNodes(filteredNodes);
        setCurrentLinks(filteredLinks);
        
        // Transform and update directly
        const transformedNodes = filteredNodes.map(node => ({
          id: String(node.id),
          label: String(node.label || node.id),
          node_type: String(node.node_type || 'Unknown'),
          centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
          degree_centrality: Number(node.properties?.degree_centrality || 0),
          pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
          betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
          eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0),
          // Include temporal data for timeline
          created_at: node.properties?.created_at || node.created_at || node.properties?.created || null,
          created_at_timestamp: (node.properties?.created_at || node.created_at || node.properties?.created) ? new Date(node.properties?.created_at || node.created_at || node.properties?.created).getTime() : null,
          // Cluster by node type for proper grouping
          cluster: String(node.node_type || 'Unknown'),
          clusterStrength: 0.7 // Strong clustering by type (0-1 range)
        }));
        
        const transformedLinks = filteredLinks.map(link => ({
          source: String(link.source),
          target: String(link.target),
          edge_type: String(link.edge_type || 'default'),
          weight: Number(link.weight || 1)
        }));
        
        cosmographRef.current.setData(transformedNodes, transformedLinks, false);
      } catch (error) {
        logger.error('Node removal failed:', error);
      } finally {
        setTimeout(() => {
          isIncrementalUpdateRef.current = false;
        }, 100);
      }
    }, [currentNodes, currentLinks]);
    
    const removeLinks = useCallback(async (linkIds: string[]) => {
      if (!cosmographRef.current?.setData) return;
      
      try {
        isIncrementalUpdateRef.current = true;
        
        const linkIdSet = new Set(linkIds);
        
        // Remove links (assuming linkIds are in "source-target" format)
        const filteredLinks = currentLinks.filter(link => {
          const linkId = `${link.source}-${link.target}`;
          return !linkIdSet.has(linkId);
        });
        
        setCurrentLinks(filteredLinks);
        
        // Transform and update directly
        const transformedNodes = currentNodes.map(node => ({
          id: String(node.id),
          label: String(node.label || node.id),
          node_type: String(node.node_type || 'Unknown'),
          centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
          degree_centrality: Number(node.properties?.degree_centrality || 0),
          pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
          betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
          eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0),
          // Include temporal data for timeline
          created_at: node.properties?.created_at || node.created_at || node.properties?.created || null,
          created_at_timestamp: (node.properties?.created_at || node.created_at || node.properties?.created) ? new Date(node.properties?.created_at || node.created_at || node.properties?.created).getTime() : null,
          // Cluster by node type for proper grouping
          cluster: String(node.node_type || 'Unknown'),
          clusterStrength: 0.7 // Strong clustering by type (0-1 range)
        }));
        
        const transformedLinks = filteredLinks.map(link => ({
          source: String(link.source),
          target: String(link.target),
          edge_type: String(link.edge_type || 'default'),
          weight: Number(link.weight || 1)
        }));
        
        cosmographRef.current.setData(transformedNodes, transformedLinks, false);
      } catch (error) {
        logger.error('Link removal failed:', error);
      } finally {
        setTimeout(() => {
          isIncrementalUpdateRef.current = false;
        }, 100);
      }
    }, [currentLinks, currentNodes]);

    // Simulation control methods
    const startSimulation = useCallback((alpha = 1.0) => {
      if (cosmographRef.current && typeof cosmographRef.current.start === 'function') {
        cosmographRef.current.start(alpha);
      }
    }, []);
    
    const pauseSimulation = useCallback(() => {
      if (cosmographRef.current && typeof cosmographRef.current.pause === 'function') {
        cosmographRef.current.pause();
      }
      
      // Clear the keep-running timer
      if (simulationTimerRef.current) {
        clearInterval(simulationTimerRef.current);
        simulationTimerRef.current = null;
      }
    }, []);
    
    const resumeSimulation = useCallback(() => {
      if (cosmographRef.current && typeof cosmographRef.current.start === 'function') {
        const currentTime = Date.now();
        lastResumeTimeRef.current = currentTime;
        
        cosmographRef.current.start(0.3); // Resume with moderate energy
        setIsSimulationActive(true);
        
        
        // Use requestAnimationFrame to ensure the simulation state is properly propagated
        requestAnimationFrame(() => {
        });
      }
    }, []);
    
    const keepSimulationRunning = useCallback((enable: boolean) => {
      setKeepRunning(enable);
      
      // Don't interfere with Cosmograph's built-in simulation control
      // The simulation will run naturally based on the simulationDecay setting
      
      if (simulationTimerRef.current) {
        clearInterval(simulationTimerRef.current);
        simulationTimerRef.current = null;
      }
    }, []);

    
    // Handle tab visibility changes to restart simulation with debouncing
    useEffect(() => {
      let visibilityTimeoutId: NodeJS.Timeout | null = null;
      let focusTimeoutId: NodeJS.Timeout | null = null;
      
      const handleVisibilityChange = () => {
        // Clear any existing timeout
        if (visibilityTimeoutId) {
          clearTimeout(visibilityTimeoutId);
        }
        
        // Debounce visibility change handling
        visibilityTimeoutId = setTimeout(() => {
          if (!document.hidden && cosmographRef.current && !config.disableSimulation) {
            // Tab is now visible, restart simulation with low energy
            if (typeof cosmographRef.current.start === 'function') {
              cosmographRef.current.start(0.1);
            }
          }
        }, 300); // 300ms debounce
      };

      // Also handle window focus for better reliability
      const handleFocus = () => {
        // Clear any existing timeout
        if (focusTimeoutId) {
          clearTimeout(focusTimeoutId);
        }
        
        // Debounce focus handling
        focusTimeoutId = setTimeout(() => {
          if (cosmographRef.current && !config.disableSimulation) {
            // Window regained focus, ensure simulation is running
            if (typeof cosmographRef.current.start === 'function') {
              cosmographRef.current.start(0.05); // Even lower energy for focus events
            }
          }
        }, 500); // 500ms debounce for focus
      };

      document.addEventListener('visibilitychange', handleVisibilityChange);
      window.addEventListener('focus', handleFocus);
      
      return () => {
        document.removeEventListener('visibilitychange', handleVisibilityChange);
        window.removeEventListener('focus', handleFocus);
        
        // Clean up timeouts
        if (visibilityTimeoutId) {
          clearTimeout(visibilityTimeoutId);
        }
        if (focusTimeoutId) {
          clearTimeout(focusTimeoutId);
        }
      };
    }, [config.disableSimulation, setupWebGLContextRecovery]);
    
    // Cleanup all timers and refs on unmount
    useEffect(() => {
      return () => {
        // Clear simulation timer
        if (simulationTimerRef.current) {
          clearInterval(simulationTimerRef.current);
          simulationTimerRef.current = null;
        }
        // Clear double-click timeout
        if (doubleClickTimeoutRef.current) {
          clearTimeout(doubleClickTimeoutRef.current);
          doubleClickTimeoutRef.current = null;
        }
        // Clear canvas polling interval
        if (intervalRef.current) {
          clearTimeout(intervalRef.current);
          intervalRef.current = null;
        }
        // Clear hover animation frame
        if (hoverAnimationFrameRef.current) {
          cancelAnimationFrame(hoverAnimationFrameRef.current);
          hoverAnimationFrameRef.current = null;
        }
        // Clear refs to prevent memory leaks
        cosmographRef.current = null;
        lastClickedNodeRef.current = null;
        isIncrementalUpdateRef.current = false;
        lastResumeTimeRef.current = 0;
        pendingHoverRef.current = null;
      };
    }, []);

    // Create stable method refs
    const methodsRef = useRef({
      clearSelection: clearCosmographSelection,
      selectNode: selectCosmographNode,
      selectNodes: selectCosmographNodes,
      zoomIn,
      zoomOut,
      fitView,
      fitViewByPointIndices,
      zoomToPoint,
      trackPointPositionsByIndices,
      getTrackedPointPositionsMap,
      activateRectSelection,
      deactivateRectSelection,
      activatePolygonalSelection,
      deactivatePolygonalSelection,
      selectPointsInRect,
      selectPointsInPolygon,
      getConnectedPointIndices,
      getPointIndicesByExactValues,
      addIncrementalData,
      updateNodes,
      updateLinks,
      removeNodes,
      removeLinks,
      startSimulation,
      pauseSimulation,
      resumeSimulation,
      keepSimulationRunning
    });
    
    // Update methods ref when dependencies change
    useEffect(() => {
      methodsRef.current = {
        clearSelection: clearCosmographSelection,
        selectNode: selectCosmographNode,
        selectNodes: selectCosmographNodes,
        zoomIn,
        zoomOut,
        fitView,
        fitViewByPointIndices,
        zoomToPoint,
        trackPointPositionsByIndices,
        getTrackedPointPositionsMap,
        activateRectSelection,
        deactivateRectSelection,
        activatePolygonalSelection,
        deactivatePolygonalSelection,
        selectPointsInRect,
        selectPointsInPolygon,
        getConnectedPointIndices,
        getPointIndicesByExactValues,
        addIncrementalData,
        updateNodes,
        updateLinks,
        removeNodes,
        removeLinks,
        startSimulation,
        pauseSimulation,
        resumeSimulation,
        keepSimulationRunning
      };
    });
    
    // Expose methods to parent via ref with minimal dependencies
    React.useImperativeHandle(ref, () => ({
      ...methodsRef.current,
      setData: (nodes: GraphNode[], links: GraphLink[], runSimulation = true) => {
        if (cosmographRef.current && typeof cosmographRef.current.setData === 'function') {
          cosmographRef.current.setData(nodes, links, runSimulation);
        }
      },
      restart: () => {
        if (cosmographRef.current && typeof cosmographRef.current.restart === 'function') {
          cosmographRef.current.restart();
        }
      },
      setIncrementalUpdateFlag: (enabled: boolean) => {
        isIncrementalUpdateRef.current = enabled;
      }
    }), []);

    // Handle Cosmograph events with native selection methods and multi-selection
    // Cosmograph v2.0 onClick signature: (index: number | undefined, pointPosition: [number, number] | undefined, event: MouseEvent) => void
    const handleClick = async (index?: number, pointPosition?: [number, number], event?: MouseEvent) => {
      
      if (typeof index === 'number' && cosmographRef.current) {
        
        // Get the original node data using the index
        let originalNode: GraphNode | undefined;
        
        // Try to get the node from our transformed data using the index
        if (index >= 0 && index < transformedData.nodes.length) {
          const nodeData = transformedData.nodes[index];
          originalNode = nodeData;
        }
        
        // If we can't find the original node by index, try to query it from Cosmograph
        if (!originalNode && typeof cosmographRef.current.getPointsByIndices === 'function') {
          try {
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
                    eigenvector_centrality: Number(point.eigenvector_centrality || 0),
                    centrality: Number(point.centrality || 0),
                    ...point // Include all other properties
                  }
                } as GraphNode;
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
          
          // Use native Cosmograph selection methods
          if (event?.shiftKey || event?.ctrlKey || event?.metaKey) {
            // Multi-selection with shift/ctrl
            if (typeof cosmographRef.current.selectPoints === 'function') {
              // Get currently selected point indices
              const currentlySelectedIndices: number[] = [];
              if (typeof cosmographRef.current.getSelectedPointIndices === 'function') {
                const selected = cosmographRef.current.getSelectedPointIndices();
                if (selected) currentlySelectedIndices.push(...selected);
              }
              
              const isAlreadySelected = currentlySelectedIndices.includes(index);
              
              if (isAlreadySelected) {
                // Deselect the node - remove from selection
                const newSelection = currentlySelectedIndices.filter(i => i !== index);
                cosmographRef.current.selectPoints(newSelection);
              } else {
                // Add to selection
                cosmographRef.current.selectPoints([...currentlySelectedIndices, index]);
              }
            }
            
            // Highlight adjacent nodes if shift is held
            if (event?.shiftKey && typeof cosmographRef.current.getAdjacentNodes === 'function') {
              const adjacentNodes = cosmographRef.current.getAdjacentNodes(originalNode.id);
              if (adjacentNodes && adjacentNodes.length > 0) {
                logger.log(`Node ${originalNode.label} has ${adjacentNodes.length} adjacent nodes`);
              }
            }
            
            // Always call onNodeClick to show the info panel even with modifiers
            onNodeClick(originalNode);
            onNodeSelect(originalNode.id);
          } else {
            // Handle single click or double click
            if (isDoubleClick) {
              // Double-click - select, focus, and zoom
              
              // Select the node
              if (typeof cosmographRef.current.selectPoint === 'function') {
                cosmographRef.current.selectPoint(index);
              } else if (typeof cosmographRef.current.selectPoints === 'function') {
                cosmographRef.current.selectPoints([index]);
              }
              
              // Focus the node (draws a ring around it)
              if (typeof cosmographRef.current.setFocusedPoint === 'function') {
                cosmographRef.current.setFocusedPoint(index);
              }
              
              // Center and zoom to the selected node
              zoomToPoint(index);
              
              // Track the selected node position
              trackPointPositionsByIndices([index]);
              
              // Log tracking info - position will be tracked
              logger.log(`Tracking node ${originalNode.label} (index: ${index})`);
              
              // Show the info panel
              onNodeClick(originalNode);
              onNodeSelect(originalNode.id);
            } else {
              // Single click - wait to see if it's a double click
              doubleClickTimeoutRef.current = setTimeout(() => {
                // Single click confirmed - select and show info panel
                
                // Select the node
                if (typeof cosmographRef.current.selectPoint === 'function') {
                  cosmographRef.current.selectPoint(index);
                } else if (typeof cosmographRef.current.selectPoints === 'function') {
                  cosmographRef.current.selectPoints([index]);
                }
                
                // Focus the node (draws a ring around it)
                if (typeof cosmographRef.current.setFocusedPoint === 'function') {
                  cosmographRef.current.setFocusedPoint(index);
                }
                
                // Track the selected node position
                trackPointPositionsByIndices([index]);
                
                // Removed automatic zoom on node selection for now
                
                // Show the info panel
                onNodeClick(originalNode);
                onNodeSelect(originalNode.id);
              }, 300);
            }
          }
          
          // Update click tracking using refs (no re-render)
          lastClickTimeRef.current = currentTime;
          lastClickedNodeRef.current = originalNode;
        } else {
          logger.warn('Could not find or create node data for index:', index);
        }
      } else {
        // Empty space was clicked - clear all selections and return to default state
        if (cosmographRef.current) {
          // Clear selection using native methods
          if (typeof cosmographRef.current.unselectAll === 'function') {
            cosmographRef.current.unselectAll();
          } else if (typeof cosmographRef.current.unselectAllPoints === 'function') {
            cosmographRef.current.unselectAllPoints();
          } else if (typeof cosmographRef.current.selectPoints === 'function') {
            cosmographRef.current.selectPoints([]);
          }
          
          // Clear focused node using native method
          if (typeof cosmographRef.current.unfocusNode === 'function') {
            cosmographRef.current.unfocusNode();
          } else if (typeof cosmographRef.current.setFocusedPoint === 'function') {
            cosmographRef.current.setFocusedPoint();
          }
          
          // Removed automatic fitView on empty space for now
        }
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
            // Use prepared data directly
            points={cosmographData.points}
            links={cosmographData.links}
            // Point configuration
            pointIdBy="id"
            pointIndexBy="index"
            pointLabelBy="label"
            pointColorBy={pointColorBy}
            pointSizeBy={pointSizeBy}
            pointClusterBy={config.clusteringEnabled ? config.pointClusterBy : undefined}  // Group nodes by their cluster assignment
            pointClusterStrengthBy={config.clusteringEnabled ? config.pointClusterStrengthBy : undefined}  // Control clustering attraction strength
            // Link configuration
            linkSourceBy="source"
            linkSourceIndexBy="sourceIndex"
            linkTargetBy="target"
            linkTargetIndexBy="targetIndex"
            // linkColorBy="edge_type"  // Disabled to let config color take over
            linkWidthBy={config.linkWidthBy || "weight"}
            
            // Override with UI-specific configurations
            fitViewOnInit={false} // Disable automatic fitView to prevent simulation interruption
            // fitViewDelay={1500} // Not needed when fitViewOnInit is false
            fitViewDuration={config.fitViewDuration}
            fitViewPadding={config.fitViewPadding}
            // initialZoomLevel={1.5} // Commented out - causing infinite zoom loop
            disableZoom={false}
            backgroundColor={config.backgroundColor}
            
            // Use Cosmograph v2.0 built-in color strategies
            pointColorStrategy={pointColorStrategy}
            pointColorPalette={pointColorPalette}
            pointColorByMap={config.nodeTypeColors}
            
            // Use Cosmograph v2.0 built-in size strategies  
            pointSizeStrategy={'auto'}
            pointSizeRange={[config.minNodeSize * config.sizeMultiplier, config.maxNodeSize * config.sizeMultiplier]}
            
            
            // Use pointColor only for highlighting
            pointColor={pointColorFn}
            
            pointSize={pointSizeFn}
            
            // Interaction
            enableDrag={true}
            enableRightClickRepulsion={true}
            onClick={handleClick}
            onMouseMove={handleMouseMove}
            
            // Hover and focus styling from config
            hoveredPointCursor={config.hoveredPointCursor}
            renderHoveredPointRing={config.renderHoveredPointRing}
            hoveredPointRingColor={config.hoveredPointRingColor}
            focusedPointRingColor={config.focusedPointRingColor}
            focusedPointIndex={config.focusedPointIndex}
            renderLinks={config.renderLinks}
            
            // Zoom event handlers (debugging disabled for now)
            // onZoomStart={(e, userDriven) => {
            //   console.log('Zoom started', { userDriven, transform: e.transform });
            // }}
            // onZoom={(e, userDriven) => {
            //   console.log('Zooming', { userDriven, k: e.transform.k });
            // }}
            // onZoomEnd={(e, userDriven) => {
            //   console.log('Zoom ended', { userDriven, transform: e.transform });
            // }}
            
            nodeGreyoutOpacity={selectedNodes.length > 0 || highlightedNodes.length > 0 ? 0.1 : 1}
            
            // Performance
            pixelRatio={config.performanceMode ? 1.0 : (currentNodes.length > 10000 ? 1.5 : 2.5)}
            showFPSMonitor={config.showFPS}
            renderUnselectedNodesTransparency={config.pixelationThreshold > 0 ? Math.max(0.1, 1 - config.pixelationThreshold / 20) : 1}
            
            // Zoom behavior
            enableSimulationDuringZoom={true}
            
            // Simulation - Cosmograph v2.0 API
            enableSimulation={true} // Explicitly enable simulation
            spaceSize={config.spaceSize}
            randomSeed={config.randomSeed}
            simulationRepulsion={config.repulsion}
            simulationRepulsionTheta={config.simulationRepulsionTheta}
            simulationCluster={config.simulationCluster}
            simulationClusterStrength={config.simulationClusterStrength}
            simulationImpulse={config.simulationImpulse}
            simulationLinkSpring={config.linkSpring}
            simulationLinkDistance={config.linkDistance}
            simulationLinkDistRandomVariationRange={config.linkDistRandomVariationRange}
            simulationGravity={config.gravity}
            simulationCenter={config.centerForce}
            simulationFriction={config.friction}
            simulationDecay={config.simulationDecay}
            simulationRepulsionFromMouse={config.mouseRepulsion}
            
            // Link Properties
            linkColor={linkColorFn || config.linkColor}
            linkOpacity={config.linkOpacity}
            linkGreyoutOpacity={config.linkGreyoutOpacity}
            linkWidth={1}
            // linkWidthBy is already set above to 'weight'
            // linkWidthBy={config.linkWidthBy}
            linkWidthScale={config.linkWidth}
            linkWidthRange={[0.5, 5]} // Set link width range for auto scaling
            scaleLinksOnZoom={config.scaleLinksOnZoom}
            linkArrows={config.edgeArrows || config.linkArrows}
            linkArrowsSizeScale={config.edgeArrowScale || config.linkArrowsSizeScale}
            curvedLinks={config.performanceMode ? false : config.curvedLinks}
            curvedLinkSegments={config.performanceMode ? 10 : config.curvedLinkSegments}
            curvedLinkWeight={config.curvedLinkWeight}
            curvedLinkControlPointDistance={config.curvedLinkControlPointDistance}
            linkVisibilityDistanceRange={config.linkVisibilityDistance}
            linkVisibilityMinTransparency={config.linkVisibilityMinTransparency}
            useClassicQuadtree={config.useClassicQuadtree}
            
            // Selection
            showLabelsFor={config.renderLabels ? undefined : selectedNodes.map(id => ({ id }))}
            
            // Label rendering
            showLabels={config.performanceMode ? false : config.renderLabels}
            labelVisibility={config.performanceMode ? 0 : (config.renderLabels ? 1.0 : 0)}
            labelStyle={{
              fontSize: config.labelSize,
              fontWeight: config.labelFontWeight,
              color: config.labelColor,
              backgroundColor: config.labelBackgroundColor,
              padding: '2px 4px',
              borderRadius: '2px'
            }}
            hoveredLabelStyle={{
              fontSize: config.hoveredLabelSize,
              fontWeight: config.hoveredLabelFontWeight,
              color: config.hoveredLabelColor,
              backgroundColor: config.hoveredLabelBackgroundColor,
              padding: '3px 6px',
              borderRadius: '3px'
            }}
          />
        
        {/* Performance Overlay */}
        {(config.showNodeCount || config.showDebugInfo) && stats && (
          <div className="absolute top-4 left-4 glass text-xs text-muted-foreground p-2 rounded space-y-1">
            {config.showNodeCount && (
              <>
                <div>Nodes: {stats.total_nodes.toLocaleString()}</div>
                <div>Edges: {stats.total_edges.toLocaleString()}</div>
              </>
            )}
            {config.showDebugInfo && (
              <>
                {stats.density !== undefined && (
                  <div>Density: {stats.density.toFixed(4)}</div>
                )}
                <div>Selected: {selectedNodes.length}</div>
                <div>Highlighted: {highlightedNodes.length}</div>
                <div>View: {config.queryType}</div>
                <div>Color: {config.colorScheme}</div>
                <div>Labels: {config.renderLabels ? 'On' : 'Off'}</div>
                <div>Physics: {config.disableSimulation ? 'Off' : 'On'}</div>
              </>
            )}
          </div>
        )}
      </div>
    );
  }
);

// Export with React.memo to prevent unnecessary re-renders
export const GraphCanvas = React.memo(GraphCanvasComponent, (prevProps, nextProps) => {
  // Optimized comparison - only re-render for essential changes
  
  // Most important: check if data references changed (should be stable during incremental updates)
  const dataChanged = prevProps.nodes !== nextProps.nodes || prevProps.links !== nextProps.links;
  
  // Check callback functions by reference (they should be stable with useCallback)
  const callbacksChanged = prevProps.onNodeClick !== nextProps.onNodeClick ||
                           prevProps.onNodeSelect !== nextProps.onNodeSelect ||
                           prevProps.onClearSelection !== nextProps.onClearSelection ||
                           prevProps.onNodeHover !== nextProps.onNodeHover;
  
  // Simple reference comparison for selection arrays (should be stable)
  const selectedNodesChanged = prevProps.selectedNodes !== nextProps.selectedNodes;
  const highlightedNodesChanged = prevProps.highlightedNodes !== nextProps.highlightedNodes;
  
  // Stats and className changes
  const statsChanged = prevProps.stats !== nextProps.stats;
  const classNameChanged = prevProps.className !== nextProps.className;
  
  const shouldRerender = dataChanged || callbacksChanged || selectedNodesChanged || 
                        highlightedNodesChanged || statsChanged || classNameChanged;
  
  // Return true to skip re-render, false to re-render
  return !shouldRerender;
});

GraphCanvas.displayName = 'GraphCanvas';