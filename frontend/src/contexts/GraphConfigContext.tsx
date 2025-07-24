import React, { createContext, useContext, useState, ReactNode } from 'react';
import { calculateLayoutPositions, type LayoutOptions } from '../utils/layoutAlgorithms';
import type { GraphNode, GraphEdge } from '../types/graph';

interface CosmographLink {
  source: string;
  target: string;
  weight?: number;
  edge_type?: string;
  properties?: Record<string, unknown>;
  [key: string]: unknown;
}

interface GraphConfig {
  // Physics
  gravity: number;
  repulsion: number;
  centerForce: number;
  friction: number;
  linkSpring: number;
  linkDistance: number;
  mouseRepulsion: number;
  simulationDecay: number;
  
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
  
  // Node colors by type
  nodeTypeColors: {
    Entity: string;
    Episodic: string;
    Agent: string;
    Community: string;
  };
  nodeTypeVisibility: {
    Entity: boolean;
    Episodic: boolean;
    Agent: boolean;
    Community: boolean;
  };
  
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
  // Physics
  gravity: 0.05,
  repulsion: 0.1,
  centerForce: 0.1,
  friction: 0.85,
  linkSpring: 1.0,
  linkDistance: 2,
  mouseRepulsion: 2.0,
  simulationDecay: 1000,
  
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
  
  // Node colors by type
  nodeTypeColors: {
    Entity: '#4ECDC4',
    Episodic: '#B794F6', 
    Agent: '#F6AD55',
    Community: '#90CDF4'
  },
  nodeTypeVisibility: {
    Entity: true,
    Episodic: true,
    Agent: true,
    Community: true
  },
  
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
  
  // Filters
  filteredNodeTypes: ['Entity', 'Episodic', 'Agent', 'Community'],
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

  const updateConfig = (updates: Partial<GraphConfig>) => {
    setConfig(prev => {
      const newConfig = { ...prev, ...updates };
      // Note: Updates will be applied through React props in GraphCanvas
      // Cosmograph React component handles updates automatically through props
      return newConfig;
    });
  };

  const zoomIn = () => {
    if (cosmographRef?.current) {
      const currentZoom = cosmographRef.current.getZoomLevel();
      cosmographRef.current.setZoomLevel(currentZoom * 1.5, 250);
    }
  };

  const zoomOut = () => {
    if (cosmographRef?.current) {
      const currentZoom = cosmographRef.current.getZoomLevel();
      cosmographRef.current.setZoomLevel(currentZoom * 0.7, 250);
    }
  };

  const fitView = () => {
    if (cosmographRef?.current) {
      cosmographRef.current.fitView();
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
    console.log('GraphConfigContext: Received cosmographRef', !!ref?.current);
    setCosmographRef(ref);
  };

  return (
    <GraphConfigContext.Provider value={{ 
      config, 
      updateConfig, 
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