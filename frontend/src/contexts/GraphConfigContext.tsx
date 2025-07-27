import React, { createContext, useContext, useState, ReactNode, useCallback } from 'react';
import { calculateLayoutPositions, type LayoutOptions } from '../utils/layoutAlgorithms';
import type { GraphNode, GraphEdge } from '../types/graph';
import { usePersistedGraphConfig, usePersistedNodeTypes } from '@/hooks/usePersistedConfig';

// Generate default colors for dynamic node types
export const generateNodeTypeColor = (nodeType: string, index: number): string => {
  // Predefined color palette for common node types
  const colorPalette = [
    '#4ECDC4', // Teal
    '#B794F6', // Purple  
    '#F6AD55', // Orange
    '#90CDF4', // Blue
    '#FF6B6B', // Red
    '#4ADE80', // Green
    '#FBBF24', // Yellow
    '#EC4899', // Pink
    '#8B5CF6', // Violet
    '#06B6D4', // Cyan
    '#F59E0B', // Amber
    '#EF4444'  // Red variant
  ];
  
  // Use specific colors for known node types
  const knownTypeColors: Record<string, string> = {
    'Entity': '#B794F6',    // Purple
    'Episodic': '#4ECDC4',  // Teal
    'Agent': '#F6AD55',     // Orange
    'Community': '#90CDF4', // Blue
    'Unknown': '#9CA3AF'    // Gray
  };
  
  if (knownTypeColors[nodeType]) {
    return knownTypeColors[nodeType];
  }
  
  // For unknown types, use the color palette cyclically
  return colorPalette[index % colorPalette.length];
};

interface CosmographLink {
  source: string;
  target: string;
  weight?: number;
  edge_type?: string;
  properties?: Record<string, unknown>;
  [key: string]: unknown;
}

interface GraphConfig {
  // Physics - Updated for Cosmograph v2.0 simulation API
  gravity: number;
  repulsion: number;
  centerForce: number;
  friction: number;
  linkSpring: number;
  linkDistance: number;
  mouseRepulsion: number;
  simulationDecay: number;
  
  // New Cosmograph v2.0 simulation properties
  simulationRepulsionTheta: number;
  simulationCluster: number;
  disableSimulation: boolean | null;
  spaceSize: number;
  randomSeed?: number | string;
  
  // Quadtree optimization
  useQuadtree: boolean;
  useClassicQuadtree: boolean;
  quadtreeLevels: number;
  
  // Appearance
  linkWidth: number;
  linkWidthBy: string;
  linkWidthScale: number;
  linkOpacity: number;
  linkGreyoutOpacity: number;
  linkColor: string;
  linkColorScheme: string;
  scaleLinksOnZoom: boolean;
  backgroundColor: string;
  
  // Link Visibility
  linkVisibilityDistance: [number, number]; // [min, max] in pixels
  linkVisibilityMinTransparency: number; // 0-1
  linkArrows: boolean;
  linkArrowsSizeScale: number;
  
  // Curved Links
  curvedLinks: boolean;
  curvedLinkSegments: number;
  curvedLinkWeight: number;
  curvedLinkControlPointDistance: number;
  
  // Node sizing
  minNodeSize: number;
  maxNodeSize: number;
  sizeMultiplier: number;
  nodeOpacity: number;
  sizeMapping: string;
  borderWidth: number;
  
  // Node colors by type - now dynamic
  nodeTypeColors: Record<string, string>;
  nodeTypeVisibility: Record<string, boolean>;
  
  // Labels
  showLabels: boolean;
  showHoveredNodeLabel: boolean;
  labelColor: string;
  hoveredLabelColor: string;
  labelSize: number;
  labelOpacity: number;
  
  // Visual preferences
  colorScheme: string;
  gradientHighColor: string;
  gradientLowColor: string;
  
  // Hover and focus styling
  hoveredPointCursor: string;
  renderHoveredPointRing: boolean;
  hoveredPointRingColor: string;
  focusedPointRingColor: string;
  focusedPointIndex?: number;
  renderLinks: boolean;
  
  // Fit view configuration
  fitViewDuration: number;
  fitViewPadding: number;
  
  // Query
  queryType: string;
  nodeLimit: number;
  
  // Layout
  layout: string;
  hierarchyDirection: string;
  radialCenter: string;
  circularOrdering: string;
  clusterBy: string;
  
  // Filters
  filteredNodeTypes: string[];
  minDegree: number;
  maxDegree: number;
  minPagerank: number;
  maxPagerank: number;
  minBetweenness: number;
  maxBetweenness: number;
  minEigenvector: number;
  maxEigenvector: number;
  minConnections: number;
  maxConnections: number;
  startDate: string;
  endDate: string;
}

interface CosmographRefType {
  setZoomLevel: (level: number, duration?: number) => void;
  getZoomLevel: () => number;
  fitView: (duration?: number) => void;
  fitViewByIndices: (indices: number[], duration?: number, padding?: number) => void;
  zoomToPoint: (index: number, duration?: number, scale?: number, canZoomOut?: boolean) => void;
  trackPointPositionsByIndices: (indices: number[]) => void;
  getTrackedPointPositionsMap: () => Map<number, [number, number]> | undefined;
  getTrackedPointPositionsArray: () => Float32Array | undefined;
  selectNode: (node: unknown) => void;
  selectNodes: (nodes: unknown[]) => void;
  unselectAll: () => void;
  unfocusNode: () => void;
  restart: () => void;
  start: () => void;
  setData?: (nodes: GraphNode[], links: CosmographLink[], runSimulation?: boolean) => void;
  _canvasElement?: HTMLCanvasElement;
}

interface GraphConfigContextType {
  config: GraphConfig;
  updateConfig: (updates: Partial<GraphConfig>) => void;
  updateNodeTypeConfigurations: (nodeTypes: string[]) => void;
  cosmographRef: React.MutableRefObject<CosmographRefType> | null;
  setCosmographRef: (ref: React.MutableRefObject<CosmographRefType>) => void;
  // Graph control methods
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
  applyLayout: (layoutType: string, options?: Record<string, unknown>, graphData?: { nodes: GraphNode[], edges: GraphEdge[] }) => void;
  isApplyingLayout: boolean;
}

const defaultConfig: GraphConfig = {
  // Physics - Cosmograph v2.0 simulation defaults
  gravity: 0.05,
  repulsion: 3.0,
  centerForce: 0.10,
  friction: 0.86,
  linkSpring: 0.12,
  linkDistance: 3.1,
  mouseRepulsion: 10.0,
  simulationDecay: 10000, // 10 seconds for longer natural simulation
  
  // New Cosmograph v2.0 simulation properties
  simulationRepulsionTheta: 1.70,
  simulationCluster: 0.1, // Default cluster coefficient
  disableSimulation: false, // Force simulation always on by default
  spaceSize: 4096,
  randomSeed: undefined,
  
  // Quadtree optimization
  useQuadtree: false,
  useClassicQuadtree: false,
  quadtreeLevels: 12,
  
  // Appearance
  linkWidth: 1,
  linkWidthBy: 'weight',
  linkWidthScale: 1,
  linkOpacity: 0.8,
  linkGreyoutOpacity: 0.1,
  linkColor: '#666666',
  linkColorScheme: 'uniform',
  scaleLinksOnZoom: false,
  backgroundColor: '#0a0a0a',
  
  // Link Visibility
  linkVisibilityDistance: [50, 150],
  linkVisibilityMinTransparency: 0.25,
  linkArrows: true,
  linkArrowsSizeScale: 1.0,
  
  // Curved Links
  curvedLinks: true,
  curvedLinkSegments: 19,
  curvedLinkWeight: 0.8,
  curvedLinkControlPointDistance: 0.5,
  
  // Node sizing
  minNodeSize: 3,
  maxNodeSize: 12,
  sizeMultiplier: 1.0,
  nodeOpacity: 90, // Using percentage (0-100)
  sizeMapping: 'degree',
  borderWidth: 0,
  
  // Node colors by type - now dynamic, empty by default
  nodeTypeColors: {},
  nodeTypeVisibility: {},
  
  // Labels
  showLabels: true,
  showHoveredNodeLabel: true,
  labelColor: '#ffffff',
  hoveredLabelColor: '#ffffff',
  labelSize: 12,
  labelOpacity: 80, // Using percentage (0-100)
  
  // Visual preferences
  colorScheme: 'by-type',
  gradientHighColor: '#FF6B6B',
  gradientLowColor: '#4ECDC4',
  
  // Hover and focus styling
  hoveredPointCursor: 'pointer',
  renderHoveredPointRing: true,
  hoveredPointRingColor: '#22d3ee', // Cyan
  focusedPointRingColor: '#ef4444', // Bright Red  
  focusedPointIndex: undefined,
  renderLinks: true,
  
  // Fit view configuration
  fitViewDuration: 250, // Default from Cosmograph interface
  fitViewPadding: 0.1, // Default from Cosmograph interface
  
  // Query
  queryType: 'entire_graph',
  nodeLimit: 100000,
  
  // Layout
  layout: 'force-directed',
  hierarchyDirection: 'top-down',
  radialCenter: '',
  circularOrdering: 'degree',
  clusterBy: 'type',
  
  // Filters - now dynamic, empty by default
  filteredNodeTypes: [],
  minDegree: 0,
  maxDegree: 100,
  minPagerank: 0,
  maxPagerank: 100,
  minBetweenness: 0,
  maxBetweenness: 100,
  minEigenvector: 0,
  maxEigenvector: 100,
  minConnections: 0,
  maxConnections: 1000,
  startDate: '',
  endDate: '',
};

const GraphConfigContext = createContext<GraphConfigContextType | undefined>(undefined);

export const GraphConfigProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [config, setConfig, isConfigLoaded] = usePersistedGraphConfig(defaultConfig);
  const [cosmographRef, setCosmographRef] = useState<React.MutableRefObject<CosmographRefType> | null>(null);
  const [isApplyingLayout, setIsApplyingLayout] = useState(false);
  const { mergeWithPersisted: mergeNodeTypes, isLoaded: isNodeTypesLoaded } = usePersistedNodeTypes(
    config.nodeTypeColors,
    config.nodeTypeVisibility
  );

  // Note: Initialization is handled by usePersistedGraphConfig hook automatically

  // Function to update node type configurations based on actual graph data
  const updateNodeTypeConfigurations = useCallback((nodeTypes: string[]) => {
    if (nodeTypes.length === 0) return;
    
    // Start with current config to preserve any recent user changes
    const newNodeTypeColors: Record<string, string> = { ...config.nodeTypeColors };
    const newNodeTypeVisibility: Record<string, boolean> = { ...config.nodeTypeVisibility };
    
    
    // Process each node type
    nodeTypes.forEach((nodeType, index) => {
      // For colors: only add if not already in config
      if (!newNodeTypeColors[nodeType]) {
        // Get the exact index this type would have in the sorted list
        const sortedTypes = [...nodeTypes].sort();
        const typeIndex = sortedTypes.indexOf(nodeType);
        newNodeTypeColors[nodeType] = generateNodeTypeColor(nodeType, typeIndex);
      }
      
      // For visibility: only add if not already in config
      if (newNodeTypeVisibility[nodeType] === undefined) {
        newNodeTypeVisibility[nodeType] = true;
      }
    });
    
    // Update filtered node types to include all visible types
    const newFilteredNodeTypes = nodeTypes.filter(type => newNodeTypeVisibility[type]);
    
    // Only update if there are actually changes to avoid unnecessary re-renders
    const hasColorChanges = JSON.stringify(config.nodeTypeColors) !== JSON.stringify(newNodeTypeColors);
    const hasVisibilityChanges = JSON.stringify(config.nodeTypeVisibility) !== JSON.stringify(newNodeTypeVisibility);
    
    if (hasColorChanges || hasVisibilityChanges) {
      setConfig(prev => ({
        ...prev,
        nodeTypeColors: newNodeTypeColors,
        nodeTypeVisibility: newNodeTypeVisibility,
        filteredNodeTypes: newFilteredNodeTypes
      }));
    }
  }, [config.nodeTypeColors, config.nodeTypeVisibility, setConfig]);

  const updateConfig = useCallback((updates: Partial<GraphConfig>) => {
    setConfig(prev => {
      const newConfig = { ...prev, ...updates };
      // Note: Updates will be applied through React props in GraphCanvas
      // Cosmograph React component handles updates automatically through props
      return newConfig;
    });
  }, [setConfig]);

  const zoomIn = () => {
    if (!cosmographRef?.current) {
      return;
    }

    try {
      const beforeZoom = cosmographRef.current.getZoomLevel();
      
      if (beforeZoom !== undefined) {
        const newZoom = Math.min(beforeZoom * 1.5, 10);
        cosmographRef.current.setZoomLevel(newZoom, config.fitViewDuration);
      }
    } catch (error) {
      // Zoom operation failed
    }
  };

  const zoomOut = () => {
    if (!cosmographRef?.current) {
      return;
    }

    try {
      const beforeZoom = cosmographRef.current.getZoomLevel();
      
      if (beforeZoom !== undefined) {
        const newZoom = Math.max(beforeZoom / 1.5, 0.1);
        cosmographRef.current.setZoomLevel(newZoom, config.fitViewDuration);
      }
    } catch (error) {
      // Zoom operation failed
    }
  };

  const fitView = () => {
    if (!cosmographRef?.current) {
      return;
    }

    try {
      // fitView method only accepts duration parameter, padding is set during initialization
      cosmographRef.current.fitView(config.fitViewDuration);
    } catch (error) {
    }
  };

  const applyLayout = async (layoutType: string, options?: Record<string, unknown>, graphData?: { nodes: GraphNode[], edges: GraphEdge[] }) => {
    if (!cosmographRef?.current) {
      return;
    }
    
    if (!graphData || !graphData.nodes?.length) {
      return;
    }

    setIsApplyingLayout(true);
    
    try {
      // Use current config merged with new options for layout calculation
      const currentConfig = { ...config, layout: layoutType, ...options };
      
      // Update config after we have the merged values
      updateConfig({ layout: layoutType, ...options });
      
      // Prepare layout options
      const layoutOptions: LayoutOptions = {
        hierarchyDirection: currentConfig.hierarchyDirection as 'top-down' | 'bottom-up' | 'left-right' | 'right-left',
        radialCenter: currentConfig.radialCenter,
        circularOrdering: currentConfig.circularOrdering as 'degree' | 'centrality' | 'type' | 'alphabetical',
        clusterBy: currentConfig.clusterBy as 'type' | 'community' | 'centrality' | 'temporal',
        canvasHeight: 800,
        ...options
      };
      

      if (layoutType === 'force-directed') {
        // For force-directed, just restart simulation with updated physics
        updateConfig({
          gravity: 0.05,
          repulsion: 0.1,
          centerForce: 0.1,
          friction: 0.85,
          linkSpring: 1.0,
          linkDistance: 2
        });
        
        if (cosmographRef.current.restart) {
          cosmographRef.current.restart();
        }
      } else {
        // Calculate actual positions using layout algorithms
        const positions = calculateLayoutPositions(layoutType, graphData.nodes, graphData.edges, layoutOptions);
        
        // Create nodes with calculated positions
        const positionedNodes = graphData.nodes.map((node, index) => ({
          ...node,
          x: positions[index]?.x || 0,
          y: positions[index]?.y || 0
        }));

        // Transform edges for Cosmograph format
        const transformedEdges = graphData.edges.map(edge => ({
          ...edge,
          source: edge.from,
          target: edge.to
        }));


        // Apply positions to Cosmograph - disable simulation for fixed layouts
        if (cosmographRef.current.setData) {
          const shouldRunSimulation = layoutType === 'force-directed';
          cosmographRef.current.setData(positionedNodes, transformedEdges, shouldRunSimulation);
        }

        // Update physics parameters for the layout type
        switch (layoutType) {
          case 'hierarchical':
            updateConfig({
              gravity: 0.02,
              repulsion: 0.05,
              centerForce: 0.1,
              friction: 0.95
            });
            break;
          case 'radial':
            updateConfig({
              gravity: 0.03,
              repulsion: 0.08,
              centerForce: 0.6,
              friction: 0.9
            });
            break;
          case 'circular':
            updateConfig({
              gravity: 0.01,
              repulsion: 0.03,
              centerForce: 0.3,
              friction: 0.98
            });
            break;
          case 'cluster':
            updateConfig({
              gravity: 0.05,
              repulsion: 0.1,
              centerForce: 0.05,
              friction: 0.85
            });
            break;
          case 'temporal':
            updateConfig({
              gravity: 0.03,
              repulsion: 0.06,
              centerForce: 0.02,
              friction: 0.92
            });
            break;
        }
      }
      
    } catch (error) {
      // Layout application failed
    } finally {
      setIsApplyingLayout(false);
    }
  };

  const setCosmographRefCallback = (ref: React.MutableRefObject<CosmographRefType>) => {
    setCosmographRef(ref);
  };

  return (
    <GraphConfigContext.Provider value={{ 
      config, 
      updateConfig,
      updateNodeTypeConfigurations,
      cosmographRef, 
      setCosmographRef: setCosmographRefCallback,
      zoomIn,
      zoomOut,
      fitView,
      applyLayout,
      isApplyingLayout
    }}>
      {children}
    </GraphConfigContext.Provider>
  );
};

export const useGraphConfig = () => {
  const context = useContext(GraphConfigContext);
  if (!context) {
    throw new Error('useGraphConfig must be used within a GraphConfigProvider');
  }
  return context;
};