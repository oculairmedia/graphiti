import React, { createContext, useContext, useState, useCallback, useRef, ReactNode, useMemo, useEffect } from 'react';
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
  // Physics - Optimized simulation parameters based on Cosmograph v2.0 docs
  gravity: 0.25,  // Increased from 0.05 - better clustering
  repulsion: 1.0,  // Reduced from 3.0 - less spread, tighter layout
  centerForce: 0.10,
  friction: 0.85,  // Reduced from 0.86 - slightly smoother movement
  linkSpring: 0.15,  // Slightly increased for stronger connections
  linkDistance: 10,  // Increased from 3.1 - better spacing (Cosmograph default)
  linkDistRandomVariationRange: [1, 1.2],
  mouseRepulsion: 2.0,  // Reduced from 10.0 - more subtle interaction
  simulationDecay: 5000, // Reduced from 10000 - faster convergence (5 seconds)
  simulationRepulsionTheta: 1.15,  // Reduced from 1.70 - more accurate (Cosmograph default)
  simulationCluster: 0.1, // Default cluster coefficient
  simulationClusterStrength: 0.5,  // Not using - kills performance
  simulationImpulse: 0.01,
  spaceSize: 4096,  // Keep at 4096, increase to 8192 only for very large graphs
  
  // Quadtree optimization
  useQuadtree: true,
  useClassicQuadtree: false,
  quadtreeLevels: 12,
  
  // Static appearance
  linkWidth: 2,
  linkWidthBy: 'weight',
  linkWidthScheme: 'uniform',  // New: scheme for link width
  linkWidthScale: 0.5,
  linkWidthMin: 0.1,  // Minimum link width for non-uniform schemes
  linkWidthMax: 5,    // Maximum link width for non-uniform schemes
  linkOpacity: 0.85,
  linkOpacityScheme: 'uniform',  // New: scheme for link opacity
  linkOpacityMin: 0.1,  // Minimum link opacity for non-uniform schemes
  linkOpacityMax: 1,    // Maximum link opacity for non-uniform schemes
  linkGreyoutOpacity: 0.1,
  linkColor: '#9CA3AF',
  linkColorScheme: 'uniform',
  scaleLinksOnZoom: true,
  backgroundColor: '#000000',
  
  // Link Visibility
  linkVisibilityDistance: [50, 200],
  linkVisibilityMinTransparency: 0.05,
  linkArrows: true,
  linkArrowsSizeScale: 1,
  
  // Curved Links
  curvedLinks: false,
  curvedLinkSegments: 10,
  curvedLinkWeight: 0.5,
  curvedLinkControlPointDistance: 0.5,
  
  // Link Strength
  linkStrengthEnabled: true,
  entityEntityStrength: 1.5,
  episodicStrength: 0.5,
  defaultLinkStrength: 1.0,
  
  // Link Animation
  linkAnimationEnabled: false,
  linkAnimationAmplitude: 0.15,  // ±15% variation
  linkAnimationFrequency: 0.5,    // Slower, organic movement
  
  // Node sizing
  minNodeSize: 4,
  maxNodeSize: 30,
  sizeMultiplier: 1,
  nodeOpacity: 0.9,
  borderWidth: 2,
  
  // Labels
  labelBy: 'label',  // Default field for label text
  labelColor: '#FFFFFF',
  hoveredLabelColor: '#FFFFFF',
  labelSize: 12,
  labelOpacity: 0.8,
  labelVisibilityThreshold: 0.5,
  labelFontWeight: 400,
  labelBackgroundColor: 'rgba(0,0,0,0.7)',
  hoveredLabelSize: 14,
  hoveredLabelFontWeight: 600,
  hoveredLabelBackgroundColor: 'rgba(0,0,0,0.9)',
  
  // Visual defaults
  colorScheme: 'by-type',
  gradientHighColor: '#FF0000',
  gradientLowColor: '#0000FF',
  
  // Hover and focus
  hoveredPointCursor: 'pointer',
  renderHoveredPointRing: false, // Disabled for performance
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
  showLabels: true,
  showHoveredNodeLabel: false, // Disabled for performance
  
  // Label optimization settings
  showDynamicLabels: true,
  showTopLabels: true,
  showTopLabelsLimit: 100,
  
  // Dynamic node configuration
  nodeTypeColors: {},
  nodeTypeVisibility: {},
  nodeAccessHighlightColor: '#FFD700',
  sizeMapping: 'degree',
  
  // Clustering configuration
  clusteringEnabled: true,
  pointClusterBy: 'node_type',
  pointClusterStrengthBy: 'clusterStrength',
  clusteringMethod: 'none',
  centralityMetric: 'pagerank',
  clusterStrength: 0.5,
  clusterPositions: undefined,
  clusterMapping: undefined,
  
  // Query
  queryType: 'entire_graph',
  nodeLimit: 100000,
  searchTerm: '',
  
  // Layout
  layout: 'force',
  hierarchyDirection: 'TB',
  radialCenter: 'most_connected',
  circularOrdering: 'degree',
  clusterBy: 'community',
  
  // Fit View configuration
  fitViewOnInit: true,  // Auto-fit graph on initialization (manually triggered after delay)
  fitViewDelay: 1500,   // Delay before fitting (ms) - allows simulation to settle
  fitViewPadding: 0.2,  // Padding around bounding box (0-1, where 0.2 = 20% padding)
  fitViewDuration: 1000, // Animation duration (ms)
  
  // Advanced rendering options
  renderLabels: true,
  edgeArrows: false,
  edgeArrowScale: 1,
  pointsOnEdge: false,
  advancedOptionsEnabled: false,
  pixelationThreshold: 100000,
  renderSelectedNodesOnTop: true,
  performanceMode: false,
  
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
  followSelectedNode: false,
  
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
  // Combine default configs for persistence - memoize to prevent infinite loops
  const defaultCombinedConfig = useMemo<GraphConfig>(() => ({ 
    ...defaultStableConfig, 
    ...defaultDynamicConfig 
  }), []);
  
  // Load persisted config with proper parameters
  const [persistedConfig, setPersistedConfig, isPersistedLoaded] = usePersistedGraphConfig<GraphConfig>(defaultCombinedConfig);
  
  // Split default configs for initial state
  const { stable: defaultStable, dynamic: defaultDynamic } = splitConfig(defaultCombinedConfig);
  
  // State - initialize with defaults
  const [stableConfig, setStableConfig] = useState<StableConfig>(defaultStable);
  const [dynamicConfig, setDynamicConfig] = useState<DynamicConfig>(defaultDynamic);
  const [cosmographRef, setCosmographRef] = useState<React.RefObject<CosmographRefType> | null>(null);
  const [isApplyingLayout, setIsApplyingLayout] = useState(false);
  const [isLoadingPersistedConfig, setIsLoadingPersistedConfig] = useState(true);
  
  // Refs to hold latest config values for persistence
  const stableConfigRef = useRef<StableConfig>(stableConfig);
  const dynamicConfigRef = useRef<DynamicConfig>(dynamicConfig);
  const hasLoadedPersistedRef = useRef(false);
  
  // Update refs when state changes
  useEffect(() => {
    stableConfigRef.current = stableConfig;
  }, [stableConfig]);
  
  useEffect(() => {
    dynamicConfigRef.current = dynamicConfig;
  }, [dynamicConfig]);
  
  // Update states when persisted config loads - only once
  useEffect(() => {
    if (!isPersistedLoaded || hasLoadedPersistedRef.current) return;
    
    hasLoadedPersistedRef.current = true;
    
    if (persistedConfig && Object.keys(persistedConfig).length > 0) {
      console.log('GraphConfigProvider: Loading persisted config', {
        hasNodeTypeColors: !!persistedConfig.nodeTypeColors,
        nodeTypeColorsCount: Object.keys(persistedConfig.nodeTypeColors || {}).length,
        nodeTypeColors: persistedConfig.nodeTypeColors,
        filteredNodeTypes: persistedConfig.filteredNodeTypes
      });
      
      const { stable: loadedStable, dynamic: loadedDynamic } = splitConfig(persistedConfig);
      
      // Only update if there are actual differences
      if (Object.keys(loadedStable).length > 0) {
        setStableConfig(prev => ({ ...prev, ...loadedStable }));
      }
      if (Object.keys(loadedDynamic).length > 0) {
        // Always use 'entire_graph' for initial load regardless of persisted value
        const { queryType, filteredNodeTypes, ...otherDynamicConfig } = loadedDynamic;
        
        // Fix legacy persisted state that only has 'Entity' in filteredNodeTypes
        // This happens when Episodic nodes were added after the config was saved
        let correctedFilteredNodeTypes = filteredNodeTypes;
        if (filteredNodeTypes && filteredNodeTypes.length === 1 && filteredNodeTypes[0] === 'Entity') {
          console.log('GraphConfigProvider: Fixing legacy filteredNodeTypes - clearing filter to show all nodes');
          correctedFilteredNodeTypes = []; // Clear filter to show all node types
        }
        
        // Ensure node type configurations are preserved
        setDynamicConfig(prev => {
          const configToApply = { 
            ...prev, 
            ...otherDynamicConfig,
            queryType: 'entire_graph', // Always start with entire graph
            filteredNodeTypes: correctedFilteredNodeTypes || [], // Use corrected filter
            // Explicitly preserve node type configs
            nodeTypeColors: { ...prev.nodeTypeColors, ...(otherDynamicConfig.nodeTypeColors || {}) },
            nodeTypeVisibility: { ...prev.nodeTypeVisibility, ...(otherDynamicConfig.nodeTypeVisibility || {}) }
          };
          
          console.log('GraphConfigProvider: Applied persisted dynamic config', {
            nodeTypeColors: configToApply.nodeTypeColors,
            nodeTypeVisibility: configToApply.nodeTypeVisibility,
            filteredNodeTypes: configToApply.filteredNodeTypes
          });
          
          return configToApply;
        });
      }
    } else {
      console.log('GraphConfigProvider: No persisted config found, using defaults');
    }
    
    setIsLoadingPersistedConfig(false);
  }, [isPersistedLoaded, persistedConfig]);
  
  // Batch update queue
  const batchUpdateTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const pendingUpdatesRef = useRef<Partial<DynamicConfig>>({});
  
  // Update stable config
  const updateStableConfig = useCallback((updates: Partial<StableConfig>) => {
    // Don't allow updates while loading persisted config
    if (isLoadingPersistedConfig) {
      console.log('GraphConfigProvider: Ignoring stable config update during load', updates);
      return;
    }
    
    setStableConfig(prev => {
      const newConfig = { ...prev, ...updates };
      
      // Persist immediately within setState to ensure we capture the right values
      setTimeout(() => {
        const fullConfig = { ...newConfig, ...dynamicConfigRef.current };
        console.log('GraphConfigProvider: Persisting stable config', {
          updateKeys: Object.keys(updates),
          example: updates[Object.keys(updates)[0]]
        });
        setPersistedConfig(fullConfig);
      }, 0);
      
      return newConfig;
    });
  }, [setPersistedConfig, isLoadingPersistedConfig]);
  
  // Update dynamic config immediately
  const updateDynamicConfig = useCallback((updates: Partial<DynamicConfig>) => {
    // Don't allow updates while loading persisted config
    if (isLoadingPersistedConfig) {
      console.log('GraphConfigProvider: Ignoring dynamic config update during load', updates);
      return;
    }
    
    setDynamicConfig(prev => {
      const newConfig = { ...prev, ...updates };
      
      // Special handling for nodeTypeColors and nodeTypeVisibility - merge instead of replace
      if (updates.nodeTypeColors) {
        newConfig.nodeTypeColors = { ...prev.nodeTypeColors, ...updates.nodeTypeColors };
      }
      if (updates.nodeTypeVisibility) {
        newConfig.nodeTypeVisibility = { ...prev.nodeTypeVisibility, ...updates.nodeTypeVisibility };
      }
      
      // Persist immediately within setState to ensure we capture the right values
      setTimeout(() => {
        const fullConfig = { ...stableConfigRef.current, ...newConfig };
        console.log('GraphConfigProvider: Persisting dynamic config', {
          updateKeys: Object.keys(updates),
          nodeTypeColors: newConfig.nodeTypeColors,
          nodeTypeVisibility: newConfig.nodeTypeVisibility
        });
        setPersistedConfig(fullConfig);
      }, 0);
      
      return newConfig;
    });
  }, [setPersistedConfig, isLoadingPersistedConfig]);
  
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
    
    // Don't allow updates while loading persisted config
    if (isLoadingPersistedConfig) {
      console.log('GraphConfigProvider: Ignoring node type config update during load');
      return;
    }
    
    setDynamicConfig(prev => {
      const newColors = { ...prev.nodeTypeColors };
      const newVisibility = { ...prev.nodeTypeVisibility };
      
      // Ensure ALL node types have both color and visibility entries
      nodeTypes.forEach((type, index) => {
        // Add color if missing
        if (!newColors[type]) {
          newColors[type] = generateNodeTypeColor(type, index);
        }
        // Always ensure visibility is set (default to true if not explicitly set)
        if (newVisibility[type] === undefined) {
          newVisibility[type] = true;
        }
      });
      
      const newConfig = {
        ...prev,
        nodeTypeColors: newColors,
        nodeTypeVisibility: newVisibility
      };
      
      return newConfig;
    });
    
    // Persist after state update using refs
    setTimeout(() => {
      const fullConfig = { ...stableConfigRef.current, ...dynamicConfigRef.current };
      setPersistedConfig(fullConfig);
    }, 0);
  }, [setPersistedConfig, isLoadingPersistedConfig]);
  
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