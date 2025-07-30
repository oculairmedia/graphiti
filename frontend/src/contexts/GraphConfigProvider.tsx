import React, { createContext, useContext, useState, useCallback, useRef, ReactNode } from 'react';
import { calculateLayoutPositions, type LayoutOptions } from '../utils/layoutAlgorithms';
import type { GraphNode, GraphEdge } from '../types/graph';
import { usePersistedGraphConfig, usePersistedNodeTypes } from '@/hooks/usePersistedConfig';
import type { GraphConfig, StableConfig, DynamicConfig } from './configTypes';
import { isStableConfigKey, splitConfig } from './configTypes';
import { generateNodeTypeColor } from '../utils/nodeTypeColors';
export { useGraphConfig, useStableConfig, useDynamicConfig, useGraphControl } from '../hooks/useGraphConfigHooks';

// Cosmograph types
interface CosmographLink {
  source: string;
  target: string;
  weight?: number;
  edge_type?: string;
  properties?: Record<string, unknown>;
  [key: string]: unknown;
}

interface CosmographRefType {
  setZoomLevel: (level: number, duration?: number) => void;
  getZoomLevel: () => number;
  fitView: (duration?: number, padding?: number) => void;
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

// Context interfaces
interface StableConfigContextType {
  config: StableConfig;
  updateConfig: (updates: Partial<StableConfig>) => void;
}

interface DynamicConfigContextType {
  config: DynamicConfig;
  updateConfig: (updates: Partial<DynamicConfig>) => void;
  batchUpdate: (updater: (draft: DynamicConfig) => void) => void;
}

interface GraphControlContextType {
  cosmographRef: React.RefObject<CosmographRefType> | null;
  setCosmographRef: (ref: React.RefObject<CosmographRefType>) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
  applyLayout: (layoutType: string, options?: Record<string, unknown>, graphData?: { nodes: GraphNode[], edges: GraphEdge[] }) => void;
  isApplyingLayout: boolean;
  updateNodeTypeConfigurations: (nodeTypes: string[]) => void;
}

// Create separate contexts - exported for hooks
export const StableConfigContext = createContext<StableConfigContextType | undefined>(undefined);
export const DynamicConfigContext = createContext<DynamicConfigContextType | undefined>(undefined);
export const GraphControlContext = createContext<GraphControlContextType | undefined>(undefined);

// Default configurations
const defaultStableConfig: StableConfig = {
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
  simulationRepulsionTheta: 1.70,
  simulationCluster: 0.1, // Default cluster coefficient
  simulationClusterStrength: 0.5,
  simulationImpulse: 0.01,
  spaceSize: 4096,
  
  // Quadtree optimization
  useQuadtree: true,
  useClassicQuadtree: false,
  quadtreeLevels: 12,
  
  // Static appearance
  linkWidth: 1,
  linkWidthBy: 'weight',
  linkWidthScale: 0.5,
  linkOpacity: 0.3,
  linkGreyoutOpacity: 0.1,
  linkColor: '#E5E7EB',
  linkColorScheme: 'uniform',
  scaleLinksOnZoom: true,
  backgroundColor: '#000000',
  
  // Link Visibility
  linkVisibilityDistance: [50, 200],
  linkVisibilityMinTransparency: 0.05,
  linkArrows: false,
  linkArrowsSizeScale: 1,
  
  // Curved Links
  curvedLinks: false,
  curvedLinkSegments: 10,
  curvedLinkWeight: 0.5,
  curvedLinkControlPointDistance: 0.5,
  
  // Node sizing
  minNodeSize: 4,
  maxNodeSize: 30,
  sizeMultiplier: 1,
  nodeOpacity: 0.9,
  borderWidth: 2,
  
  // Labels
  labelColor: '#FFFFFF',
  hoveredLabelColor: '#FFFFFF',
  labelSize: 12,
  labelOpacity: 0.8,
  
  // Visual defaults
  colorScheme: 'nodetype',
  gradientHighColor: '#FF0000',
  gradientLowColor: '#0000FF',
  
  // Hover and focus
  hoveredPointCursor: 'pointer',
  renderHoveredPointRing: true,
  hoveredPointRingColor: '#FFD700',
  focusedPointRingColor: '#FF6B6B',
  
  // Fit view
  fitViewDuration: 1000,
  fitViewPadding: 0.1, // 10% padding around the graph
};

const defaultDynamicConfig: DynamicConfig = {
  // Frequently toggled
  disableSimulation: false,
  renderLinks: true,
  showLabels: false,
  showHoveredNodeLabel: true,
  
  // Dynamic node configuration
  nodeTypeColors: {},
  nodeTypeVisibility: {},
  sizeMapping: 'degree',
  
  // Query
  queryType: 'entire_graph',
  nodeLimit: 100000,
  
  // Layout
  layout: 'force',
  hierarchyDirection: 'TB',
  radialCenter: 'most_connected',
  circularOrdering: 'degree',
  clusterBy: 'community',
  
  // Filters
  filteredNodeTypes: [],
  minDegree: 0,
  maxDegree: 100,
  minPagerank: 0,
  maxPagerank: 1,
  minBetweenness: 0,
  maxBetweenness: 1,
  minEigenvector: 0,
  maxEigenvector: 1,
  minConnections: 0,
  maxConnections: 1000,
  startDate: '',
  endDate: '',
};

// Provider component
export function GraphConfigProvider({ children }: { children: ReactNode }) {
  // Load persisted config
  const [persistedConfig, setPersistedConfig] = usePersistedGraphConfig();
  
  // Split persisted config if it exists
  const initialConfig = persistedConfig ? 
    { ...defaultStableConfig, ...defaultDynamicConfig, ...persistedConfig } :
    { ...defaultStableConfig, ...defaultDynamicConfig };
    
  const { stable: initialStable, dynamic: initialDynamic } = splitConfig(initialConfig);
  
  // State
  const [stableConfig, setStableConfig] = useState<StableConfig>(initialStable);
  const [dynamicConfig, setDynamicConfig] = useState<DynamicConfig>(initialDynamic);
  const [cosmographRef, setCosmographRef] = useState<React.RefObject<CosmographRefType> | null>(null);
  const [isApplyingLayout, setIsApplyingLayout] = useState(false);
  
  // Batch update queue
  const batchUpdateTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const pendingUpdatesRef = useRef<Partial<DynamicConfig>>({});
  
  // Update stable config
  const updateStableConfig = useCallback((updates: Partial<StableConfig>) => {
    setStableConfig(prev => {
      const newConfig = { ...prev, ...updates };
      // Persist the full config
      const fullConfig = { ...newConfig, ...dynamicConfig };
      setPersistedConfig(fullConfig);
      return newConfig;
    });
  }, [dynamicConfig, setPersistedConfig]);
  
  // Update dynamic config immediately
  const updateDynamicConfig = useCallback((updates: Partial<DynamicConfig>) => {
    setDynamicConfig(prev => {
      const newConfig = { ...prev, ...updates };
      // Persist the full config
      const fullConfig = { ...stableConfig, ...newConfig };
      setPersistedConfig(fullConfig);
      return newConfig;
    });
  }, [stableConfig, setPersistedConfig]);
  
  // Batch update dynamic config
  const batchUpdateDynamicConfig = useCallback((updater: (draft: DynamicConfig) => void) => {
    // Clear existing timeout
    if (batchUpdateTimeoutRef.current) {
      clearTimeout(batchUpdateTimeoutRef.current);
    }
    
    // Apply updates to pending queue
    const draft = { ...dynamicConfig, ...pendingUpdatesRef.current };
    updater(draft);
    pendingUpdatesRef.current = { ...pendingUpdatesRef.current, ...draft };
    
    // Schedule batch update
    batchUpdateTimeoutRef.current = setTimeout(() => {
      if (Object.keys(pendingUpdatesRef.current).length > 0) {
        updateDynamicConfig(pendingUpdatesRef.current);
        pendingUpdatesRef.current = {};
      }
    }, 16); // ~60fps
  }, [dynamicConfig, updateDynamicConfig]);
  
  // Update node type configurations
  const updateNodeTypeConfigurations = useCallback((nodeTypes: string[]) => {
    if (nodeTypes.length === 0) return;
    
    setDynamicConfig(prev => {
      const existingTypes = Object.keys(prev.nodeTypeColors);
      const newTypes = nodeTypes.filter(type => !existingTypes.includes(type));
      
      if (newTypes.length === 0) {
        return prev;
      }
      
      const newColors = { ...prev.nodeTypeColors };
      const newVisibility = { ...prev.nodeTypeVisibility };
      
      newTypes.forEach((type, index) => {
        newColors[type] = generateNodeTypeColor(type, existingTypes.length + index);
        newVisibility[type] = true;
      });
      
      const newConfig = {
        ...prev,
        nodeTypeColors: newColors,
        nodeTypeVisibility: newVisibility
      };
      
      // Persist
      const fullConfig = { ...stableConfig, ...newConfig };
      setPersistedConfig(fullConfig);
      
      return newConfig;
    });
  }, [stableConfig, setPersistedConfig]);
  
  // Graph control methods
  const zoomIn = useCallback(() => {
    if (!cosmographRef?.current) return;
    const currentZoom = cosmographRef.current.getZoomLevel();
    cosmographRef.current.setZoomLevel(currentZoom * 1.5);
  }, [cosmographRef]);
  
  const zoomOut = useCallback(() => {
    if (!cosmographRef?.current) return;
    const currentZoom = cosmographRef.current.getZoomLevel();
    cosmographRef.current.setZoomLevel(currentZoom / 1.5);
  }, [cosmographRef]);
  
  const fitView = useCallback(() => {
    console.log('GraphConfigProvider: fitView called - using fallback zoom approach');
    
    if (!cosmographRef?.current) {
      console.warn('GraphConfigProvider: No cosmographRef available');
      return;
    }
    
    try {
      // Since the React wrapper doesn't expose fitView methods, 
      // we'll implement a simple zoom reset as a workaround
      if (typeof cosmographRef.current.setZoomLevel === 'function') {
        // Reset to a reasonable zoom level that shows most of the graph
        // This is a workaround since we can't access the actual fitView method
        const defaultZoom = 1.0;
        cosmographRef.current.setZoomLevel(defaultZoom, stableConfig.fitViewDuration);
        console.log('GraphConfigProvider: Reset zoom to', defaultZoom);
      } else {
        console.error('GraphConfigProvider: setZoomLevel not available');
        console.log('Available on ref:', Object.keys(cosmographRef.current));
      }
    } catch (error) {
      console.error('fitView error:', error);
    }
  }, [cosmographRef, stableConfig.fitViewDuration]);
  
  const applyLayout = useCallback(async (
    layoutType: string,
    options?: Record<string, unknown>,
    graphData?: { nodes: GraphNode[], edges: GraphEdge[] }
  ) => {
    if (!cosmographRef?.current || !graphData) return;
    
    setIsApplyingLayout(true);
    
    try {
      const layoutOptions: LayoutOptions = {
        type: layoutType,
        ...options
      };
      
      const positions = await calculateLayoutPositions(
        graphData.nodes,
        graphData.edges,
        layoutOptions
      );
      
      if (cosmographRef.current.setData) {
        const nodesWithPositions = graphData.nodes.map((node, index) => ({
          ...node,
          x: positions[index].x,
          y: positions[index].y
        }));
        
        const links: CosmographLink[] = graphData.edges.map(edge => ({
          source: edge.source,
          target: edge.target,
          weight: edge.weight,
          edge_type: edge.edge_type,
          properties: edge.properties
        }));
        
        cosmographRef.current.setData(nodesWithPositions, links, false);
        
        setTimeout(() => {
          cosmographRef.current?.fitView(stableConfig.fitViewDuration, stableConfig.fitViewPadding);
        }, 100);
      }
    } finally {
      setIsApplyingLayout(false);
    }
  }, [cosmographRef, stableConfig.fitViewDuration, stableConfig.fitViewPadding]);
  
  return (
    <StableConfigContext.Provider value={{ config: stableConfig, updateConfig: updateStableConfig }}>
      <DynamicConfigContext.Provider value={{ 
        config: dynamicConfig, 
        updateConfig: updateDynamicConfig,
        batchUpdate: batchUpdateDynamicConfig
      }}>
        <GraphControlContext.Provider value={{
          cosmographRef,
          setCosmographRef,
          zoomIn,
          zoomOut,
          fitView,
          applyLayout,
          isApplyingLayout,
          updateNodeTypeConfigurations
        }}>
          {children}
        </GraphControlContext.Provider>
      </DynamicConfigContext.Provider>
    </StableConfigContext.Provider>
  );
}