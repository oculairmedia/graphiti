import React, { createContext, useContext, useState, ReactNode } from 'react';
import { calculateLayoutPositions, type LayoutOptions } from '../utils/layoutAlgorithms';
import type { GraphNode, GraphEdge } from '../types/graph';

// Generate default colors for dynamic node types
const generateNodeTypeColor = (nodeType: string, index: number): string => {
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
    'Entity': '#4ECDC4',
    'Episodic': '#B794F6',
    'Agent': '#F6AD55', 
    'Community': '#90CDF4',
    'Unknown': '#9CA3AF'
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
  disableSimulation: boolean | null;
  spaceSize: number;
  randomSeed?: number | string;
  
  // Quadtree optimization
  useQuadtree: boolean;
  quadtreeLevels: number;
  
  // Appearance
  linkWidth: number;
  linkOpacity: number;
  linkColor: string;
  linkColorScheme: string;
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
  minConnections: number;
  maxConnections: number;
  startDate: string;
  endDate: string;
}

interface CosmographRefType {
  setZoomLevel: (level: number, duration?: number) => void;
  getZoomLevel: () => number;
  fitView: (duration?: number) => void;
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
  repulsion: 0.1,
  centerForce: 0.1,
  friction: 0.85,
  linkSpring: 1.0,
  linkDistance: 2,
  mouseRepulsion: 2.0,
  simulationDecay: 1000,
  
  // New Cosmograph v2.0 simulation properties
  simulationRepulsionTheta: 1.7,
  disableSimulation: null, // Auto-detect based on links
  spaceSize: 4096,
  randomSeed: undefined,
  
  // Quadtree optimization
  useQuadtree: false,
  quadtreeLevels: 12,
  
  // Appearance
  linkWidth: 1,
  linkOpacity: 0.8,
  linkColor: '#666666',
  linkColorScheme: 'uniform',
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
  minConnections: 0,
  maxConnections: 1000,
  startDate: '',
  endDate: '',
};

const GraphConfigContext = createContext<GraphConfigContextType | undefined>(undefined);

export const GraphConfigProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [config, setConfig] = useState<GraphConfig>(defaultConfig);
  const [cosmographRef, setCosmographRef] = useState<React.MutableRefObject<CosmographRefType> | null>(null);
  const [isApplyingLayout, setIsApplyingLayout] = useState(false);

  // Function to update node type configurations based on actual graph data
  const updateNodeTypeConfigurations = (nodeTypes: string[]) => {
    if (nodeTypes.length === 0) return;
    
    // Only update if the node types have actually changed
    const currentTypes = Object.keys(config.nodeTypeColors);
    const typesChanged = nodeTypes.length !== currentTypes.length || 
                        !nodeTypes.every(type => currentTypes.includes(type));
    
    if (!typesChanged) return;
    
    console.log('GraphConfigContext: Updating node type configurations for types:', nodeTypes);
    
    // Generate colors and visibility for the actual node types
    const newNodeTypeColors: Record<string, string> = {};
    const newNodeTypeVisibility: Record<string, boolean> = {};
    
    nodeTypes.forEach((nodeType, index) => {
      // Preserve existing color if already configured, otherwise generate new
      newNodeTypeColors[nodeType] = config.nodeTypeColors[nodeType] || generateNodeTypeColor(nodeType, index);
      // Preserve existing visibility if already configured, otherwise default to true
      newNodeTypeVisibility[nodeType] = config.nodeTypeVisibility[nodeType] !== undefined 
        ? config.nodeTypeVisibility[nodeType] 
        : true;
    });
    
    // Update filtered node types to include all visible types
    const newFilteredNodeTypes = nodeTypes.filter(type => newNodeTypeVisibility[type]);
    
    setConfig(prev => ({
      ...prev,
      nodeTypeColors: newNodeTypeColors,
      nodeTypeVisibility: newNodeTypeVisibility,
      filteredNodeTypes: newFilteredNodeTypes
    }));
  };

  const updateConfig = (updates: Partial<GraphConfig>) => {
    setConfig(prev => {
      const newConfig = { ...prev, ...updates };
      // Note: Updates will be applied through React props in GraphCanvas
      // Cosmograph React component handles updates automatically through props
      return newConfig;
    });
  };

  const zoomIn = () => {
    console.log('🔍 GraphConfigContext: zoomIn() called');
    console.log('🔍 cosmographRef exists:', !!cosmographRef);
    console.log('🔍 cosmographRef.current exists:', !!cosmographRef?.current);
    
    if (cosmographRef?.current) {
      console.log('🔍 Available methods on cosmographRef.current:', Object.getOwnPropertyNames(cosmographRef.current));
      console.log('🔍 setZoomLevel method exists:', typeof cosmographRef.current.setZoomLevel === 'function');
      console.log('🔍 getZoomLevel method exists:', typeof cosmographRef.current.getZoomLevel === 'function');
    }
    
    if (!cosmographRef?.current) {
      console.warn('❌ GraphConfigContext: Zoom in failed - cosmographRef not available');
      console.log('🔍 cosmographRef state:', cosmographRef);
      return;
    }

    try {
      console.log('🔍 Attempting to get current zoom level...');
      const beforeZoom = cosmographRef.current.getZoomLevel();
      console.log('🔍 Current zoom level:', beforeZoom);
      
      if (beforeZoom !== undefined) {
        const newZoom = Math.min(beforeZoom * 1.5, 10); // Cap at 10x zoom
        console.log('🔍 Attempting to set zoom level to:', newZoom);
        cosmographRef.current.setZoomLevel(newZoom, 300);
        console.log(`✅ GraphConfigContext: Zoom in from ${beforeZoom.toFixed(2)} to ${newZoom.toFixed(2)}`);
      } else {
        console.warn('❌ GraphConfigContext: Could not get current zoom level - returned undefined');
      }
    } catch (error) {
      console.error('❌ GraphConfigContext: Zoom in failed with error:', error);
      console.log('🔍 Error details:', {
        name: error.name,
        message: error.message,
        stack: error.stack
      });
    }
  };

  const zoomOut = () => {
    console.log('🔍 GraphConfigContext: zoomOut() called');
    console.log('🔍 cosmographRef exists:', !!cosmographRef);
    console.log('🔍 cosmographRef.current exists:', !!cosmographRef?.current);
    
    if (!cosmographRef?.current) {
      console.warn('❌ GraphConfigContext: Zoom out failed - cosmographRef not available');
      console.log('🔍 cosmographRef state:', cosmographRef);
      return;
    }

    try {
      console.log('🔍 Attempting to get current zoom level for zoom out...');
      const beforeZoom = cosmographRef.current.getZoomLevel();
      console.log('🔍 Current zoom level:', beforeZoom);
      
      if (beforeZoom !== undefined) {
        const newZoom = Math.max(beforeZoom * 0.67, 0.05); // Lower minimum zoom like GraphCanvas
        console.log('🔍 Attempting to set zoom level to:', newZoom);
        cosmographRef.current.setZoomLevel(newZoom, 300);
        console.log(`✅ GraphConfigContext: Zoom out from ${beforeZoom.toFixed(2)} to ${newZoom.toFixed(2)}`);
      } else {
        console.warn('❌ GraphConfigContext: Could not get current zoom level - returned undefined');
      }
    } catch (error) {
      console.error('❌ GraphConfigContext: Zoom out failed with error:', error);
      console.log('🔍 Error details:', {
        name: error.name,
        message: error.message,
        stack: error.stack
      });
    }
  };

  const fitView = () => {
    console.log('🔍 GraphConfigContext: fitView() called');
    console.log('🔍 cosmographRef exists:', !!cosmographRef);
    console.log('🔍 cosmographRef.current exists:', !!cosmographRef?.current);
    
    if (cosmographRef?.current) {
      console.log('🔍 fitView method exists:', typeof cosmographRef.current.fitView === 'function');
    }
    
    if (!cosmographRef?.current) {
      console.warn('❌ GraphConfigContext: Fit view failed - cosmographRef not available');
      console.log('🔍 cosmographRef state:', cosmographRef);
      return;
    }

    try {
      console.log('🔍 Attempting to call fitView with duration 500ms and padding 0.1...');
      cosmographRef.current.fitView(500, 0.1); // Duration and padding like GraphCanvas
      console.log('✅ GraphConfigContext: Fit view executed with padding');
    } catch (error) {
      console.error('❌ GraphConfigContext: Fit view failed with error:', error);
      console.log('🔍 Error details:', {
        name: error.name,
        message: error.message,
        stack: error.stack
      });
    }
  };

  const applyLayout = async (layoutType: string, options?: Record<string, unknown>, graphData?: { nodes: GraphNode[], edges: GraphEdge[] }) => {
    console.log('GraphConfigContext: applyLayout called', { layoutType, hasGraphData: !!graphData, nodeCount: graphData?.nodes?.length, edgeCount: graphData?.edges?.length, hasCosmographRef: !!cosmographRef?.current });
    
    if (!cosmographRef?.current) {
      console.error('GraphConfigContext: No cosmographRef available');
      return;
    }
    
    if (!graphData || !graphData.nodes?.length) {
      console.error('GraphConfigContext: No graph data provided', graphData);
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
        canvasWidth: 1200, // TODO: Get from actual canvas dimensions
        canvasHeight: 800,
        ...options
      };
      
      console.log('GraphConfigContext: Layout options', layoutOptions);

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
        console.log('GraphConfigContext: Calculating positions for', layoutType);
        const positions = calculateLayoutPositions(layoutType, graphData.nodes, graphData.edges, layoutOptions);
        console.log('GraphConfigContext: Calculated', positions.length, 'positions');
        
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

        console.log('GraphConfigContext: Prepared', positionedNodes.length, 'positioned nodes and', transformedEdges.length, 'edges');

        // Apply positions to Cosmograph - disable simulation for fixed layouts
        if (cosmographRef.current.setData) {
          const shouldRunSimulation = layoutType === 'force-directed';
          console.log('GraphConfigContext: Calling setData with runSimulation =', shouldRunSimulation);
          cosmographRef.current.setData(positionedNodes, transformedEdges, shouldRunSimulation);
        } else {
          console.error('GraphConfigContext: setData method not available on cosmographRef');
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
      console.error('GraphConfigContext: Layout application failed:', error);
    } finally {
      setIsApplyingLayout(false);
    }
  };

  const setCosmographRefCallback = (ref: React.MutableRefObject<CosmographRefType>) => {
    console.log('📍 GraphConfigContext: setCosmographRef called');
    console.log('📍 Received ref object:', !!ref);
    console.log('📍 Ref.current exists:', !!ref?.current);
    
    if (ref?.current) {
      console.log('📍 Available methods on ref.current:', Object.getOwnPropertyNames(ref.current));
      console.log('📍 getZoomLevel available:', typeof ref.current.getZoomLevel === 'function');
      console.log('📍 setZoomLevel available:', typeof ref.current.setZoomLevel === 'function');
      console.log('📍 fitView available:', typeof ref.current.fitView === 'function');
    }
    
    setCosmographRef(ref);
    console.log('📍 cosmographRef state updated in context');
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