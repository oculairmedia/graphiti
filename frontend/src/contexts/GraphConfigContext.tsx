import React, { useState, ReactNode, useCallback } from 'react';
import { calculateLayoutPositions, type LayoutOptions } from '../utils/layoutAlgorithms';
import type { GraphNode, GraphEdge } from '../types/graph';
import { usePersistedGraphConfig, usePersistedNodeTypes } from '@/hooks/usePersistedConfig';
import type { GraphConfig } from './configTypes';
import { generateNodeTypeColor } from '../utils/nodeTypeColors';
import type { GraphConfigContextType } from './GraphConfigContextTypes';
import { GraphConfigContext } from './useGraphConfig';

// Re-export types needed internally
type CosmographLink = {
  source: string;
  target: string;
  weight?: number;
  edge_type?: string;
  properties?: Record<string, unknown>;
  [key: string]: unknown;
}

type CosmographRefType = {
  setZoomLevel: (level: number, duration?: number) => void;
  getZoomLevel: () => number;
  fitView: (duration?: number) => void;
  fitViewByPointIndices: (indices: number[], duration?: number, padding?: number) => void;
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

const defaultConfig: GraphConfig = {
  // Physics - Cosmograph v2.0 simulation defaults
  gravity: 0.05,
  repulsion: 3.0,
  centerForce: 0.10,
  friction: 0.86,
  linkSpring: 0.12,
  linkDistance: 3.1,
  linkDistRandomVariationRange: [1, 1.2],
  mouseRepulsion: 10.0,
  simulationDecay: 10000, // 10 seconds for longer natural simulation
  
  // New Cosmograph v2.0 simulation properties
  simulationRepulsionTheta: 1.70,
  simulationCluster: 0.1, // Default cluster coefficient
  simulationClusterStrength: undefined, // No clustering force by default
  simulationImpulse: undefined, // No impulse by default
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
  edgeArrows: false,
  edgeArrowScale: 1.0,
  pointsOnEdge: false,
  
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
  renderLabels: true,
  showLabels: true,
  showHoveredNodeLabel: true,
  labelColor: '#ffffff',
  hoveredLabelColor: '#ffffff',
  labelSize: 12,
  labelOpacity: 80, // Using percentage (0-100)
  labelVisibilityThreshold: 0.5,
  labelFontWeight: 'normal',
  labelBackgroundColor: 'rgba(0, 0, 0, 0.7)',
  hoveredLabelSize: 14,
  hoveredLabelFontWeight: 'bold',
  hoveredLabelBackgroundColor: 'rgba(0, 0, 0, 0.9)',
  
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
  searchTerm: '',
  
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
  
  // Advanced rendering options
  advancedOptionsEnabled: false,
  pixelationThreshold: 1,
  renderSelectedNodesOnTop: false,
  
  // Display settings
  showFPS: false,
  showNodeCount: true,
  showDebugInfo: false,
  
  // Interaction settings
  enableHoverEffects: true,
  enablePanOnDrag: true,
  enableZoomOnScroll: true,
  enableClickSelection: true,
  enableDoubleClickFocus: true,
  enableKeyboardShortcuts: true,
  
  // Performance
  performanceMode: false,
  
  // Clustering
  clusteringEnabled: true,
  pointClusterBy: 'cluster',
  pointClusterStrengthBy: 'clusterStrength'
};


export const GraphConfigProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [config, setConfig, isConfigLoaded] = usePersistedGraphConfig(defaultConfig);
  const [cosmographRef, setCosmographRef] = useState<React.RefObject<CosmographRefType> | null>(null);
  const [isApplyingLayout, setIsApplyingLayout] = useState(false);
  const { mergeWithPersisted: mergeNodeTypes, isLoaded: isNodeTypesLoaded } = usePersistedNodeTypes(
    config.nodeTypeColors,
    config.nodeTypeVisibility
  );

  // Note: Initialization is handled by usePersistedGraphConfig hook automatically

  // Function to update node type configurations based on actual graph data
  const updateNodeTypeConfigurations = useCallback((nodeTypes: string[]) => {
    if (nodeTypes.length === 0) return;
    
    setConfig(prev => {
      // Start with current config to preserve any recent user changes
      const newNodeTypeColors: Record<string, string> = { ...prev.nodeTypeColors };
      const newNodeTypeVisibility: Record<string, boolean> = { ...prev.nodeTypeVisibility };
      
      let hasChanges = false;
      
      // Process each node type
      nodeTypes.forEach((nodeType, index) => {
        // For colors: only add if not already in config
        if (!newNodeTypeColors[nodeType]) {
          // Get the exact index this type would have in the sorted list
          const sortedTypes = [...nodeTypes].sort();
          const typeIndex = sortedTypes.indexOf(nodeType);
          newNodeTypeColors[nodeType] = generateNodeTypeColor(nodeType, typeIndex);
          hasChanges = true;
        }
        
        // For visibility: only add if not already in config
        if (newNodeTypeVisibility[nodeType] === undefined) {
          newNodeTypeVisibility[nodeType] = true;
          hasChanges = true;
        }
      });
      
      // Only update if there are actually changes
      if (!hasChanges) {
        return prev;
      }
      
      // Update filtered node types to include all visible types
      const newFilteredNodeTypes = nodeTypes.filter(type => newNodeTypeVisibility[type]);
      
      return {
        ...prev,
        nodeTypeColors: newNodeTypeColors,
        nodeTypeVisibility: newNodeTypeVisibility,
        filteredNodeTypes: newFilteredNodeTypes
      };
    });
  }, [setConfig]);

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
      console.warn('GraphConfigContext: cosmographRef is not available for zoomIn');
      return;
    }

    try {
      const beforeZoom = cosmographRef.current.getZoomLevel();
      console.log('GraphConfigContext: Current zoom level:', beforeZoom);
      
      if (beforeZoom !== undefined && !isNaN(beforeZoom)) {
        const newZoom = Math.min(beforeZoom * 1.5, 10);
        console.log('GraphConfigContext: Setting new zoom level:', newZoom);
        cosmographRef.current.setZoomLevel(newZoom);
      } else {
        console.warn('GraphConfigContext: Invalid zoom level:', beforeZoom);
      }
    } catch (error) {
      console.error('GraphConfigContext: Zoom in failed:', error);
    }
  };

  const zoomOut = () => {
    if (!cosmographRef?.current) {
      console.warn('GraphConfigContext: cosmographRef is not available for zoomOut');
      return;
    }

    try {
      const beforeZoom = cosmographRef.current.getZoomLevel();
      console.log('GraphConfigContext: Current zoom level:', beforeZoom);
      
      if (beforeZoom !== undefined && !isNaN(beforeZoom)) {
        const newZoom = Math.max(beforeZoom / 1.5, 0.1);
        console.log('GraphConfigContext: Setting new zoom level:', newZoom);
        cosmographRef.current.setZoomLevel(newZoom);
      } else {
        console.warn('GraphConfigContext: Invalid zoom level:', beforeZoom);
      }
    } catch (error) {
      console.error('GraphConfigContext: Zoom out failed:', error);
    }
  };

  const fitView = () => {
    if (!cosmographRef?.current) {
      console.warn('GraphConfigContext: cosmographRef is not available for fitView');
      return;
    }

    try {
      console.log('GraphConfigContext: Calling fitView through ref');
      // Call the GraphCanvas fitView which handles timing properly
      if (typeof cosmographRef.current.fitView === 'function') {
        cosmographRef.current.fitView();
      }
    } catch (error) {
      console.error('GraphConfigContext: Fit view failed:', error);
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

  const setCosmographRefCallback = (ref: React.RefObject<CosmographRefType>) => {
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

