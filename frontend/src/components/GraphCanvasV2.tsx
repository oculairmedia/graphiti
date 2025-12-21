/**
 * GraphCanvasV2 Component
 * Refactored version of GraphCanvas using modular hooks
 */

import React, { 
  useEffect, 
  useRef, 
  forwardRef, 
  useState, 
  useCallback, 
  useMemo,
  useImperativeHandle 
} from 'react';
import { Cosmograph } from '@cosmograph/react';
import '../styles/cosmograph.css';
import { GraphNode } from '../types/graph';
import type { GraphLink } from '../types/graph';
import { useGraphConfig } from '../hooks/useGraphConfigHooks';
import { hexToRgba, interpolateColor } from '../utils/NodeColorManager';
import { generateNodeTypeColor } from '../utils/NodeColorManager';
import { NodeColorManager, getGlobalColorManager } from '../utils/NodeColorManager';

// Import our new hooks
import { useGraphStatistics } from '../hooks/useGraphStatistics';
import { useGraphDataManagement } from '../hooks/useGraphDataManagement';
import { useGraphSelection } from '../hooks/useGraphSelection';
import { useGraphWebSocket } from '../hooks/useGraphWebSocket';
import { useGraphCamera } from '../hooks/useGraphCamera';
import { useGraphInteractions } from '../hooks/useGraphInteractions';
import { useGraphSimulation } from '../hooks/useGraphSimulation';
import { useGraphVisualEffects } from '../hooks/useGraphVisualEffects';
import { useCosmographIncrementalUpdates } from '../hooks/useCosmographIncrementalUpdates';
import { useCosmographDataTransform } from '../hooks/useCosmographDataTransform';
import { useGraphCanvasEvents } from '../hooks/useGraphCanvasEvents';
import { useCosmographVisualization } from '../hooks/useCosmographVisualization';
import { GraphCanvasRenderer } from './GraphCanvasRenderer';

// PERFORMANCE FIX (GRAPH-35): Extracted hooks for better separation of concerns
import { useGraphGlowEffects } from '../hooks/useGraphGlowEffects';
import { useGraphFPS } from '../hooks/useGraphFPS';
import { useGraphNodeIndex } from '../hooks/useGraphNodeIndex';
import { useGraphLiveCounts } from '../hooks/useGraphLiveCounts';
import { useGraphNodeAccessEvents } from '../hooks/useGraphNodeAccessEvents';

// Additional imports
import { useLoadingCoordinator } from '../contexts/LoadingCoordinator';
import { ProgressiveLoadingOverlay } from './ProgressiveLoadingOverlay';
import { useWebSocketContext } from '../contexts/WebSocketProvider';
import { GraphOverlays } from './GraphOverlays';
// CosmographDataPreparer now handled by useCosmographDataTransform hook
import { inspectCosmographSchema, attachSchemaDebugger, isSchemaDebuggingEnabled } from '../utils/debugCosmographSchema';
import { inspectDuckDBSchema } from '../utils/inspectDuckDBSchema';
import { resetDuckDBStorage } from '../utils/resetDuckDB';

// GraphLink is now imported from '../types/graph'

interface GraphStats {
  total_nodes: number;
  total_edges: number;
  density?: number;
  [key: string]: unknown;
}

interface GraphCanvasProps {
  onNodeClick: (node: GraphNode) => void;
  onNodeSelect: (nodeId: string) => void;
  onSelectNodes?: (nodes: GraphNode[]) => void;
  onClearSelection?: () => void;
  onNodeHover?: (node: GraphNode | null) => void;
  onStatsUpdate?: (stats: { nodeCount: number; edgeCount: number; lastUpdated: number }) => void;
  onContextReady?: (isReady: boolean) => void;
  selectedNodes: string[];
  highlightedNodes: string[];
  className?: string;
  stats?: GraphStats;
}

interface GraphCanvasHandle {
  clearSelection: () => void;
  selectNode: (node: GraphNode) => void;
  selectNodes: (nodes: GraphNode[]) => void;
  focusOnNodes: (nodeIds: string[], duration?: number, padding?: number) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: (duration?: number, padding?: number) => void;
  fitViewByPointIndices: (indices: number[], duration?: number, padding?: number) => void;
  zoomToPoint: (index: number, duration?: number, scale?: number, canZoomOut?: boolean) => void;
  trackPointPositionsByIndices: (indices: number[]) => void;
  getTrackedPointPositionsMap: () => Map<number, [number, number]> | undefined;
  setData: (nodes: GraphNode[], links: GraphLink[], runSimulation?: boolean) => void;
  restart: () => void;
  getLiveStats: () => { nodeCount: number; edgeCount: number; lastUpdated: number };
  // Selection tools
  activateRectSelection: () => void;
  deactivateRectSelection: () => void;
  activatePolygonalSelection: () => void;
  deactivatePolygonalSelection: () => void;
  selectPointsInRect: (selection: [[number, number], [number, number]] | null, addToSelection?: boolean) => void;
  selectPointsInPolygon: (polygonPoints: [number, number][], addToSelection?: boolean) => void;
  getConnectedPointIndices: (index: number) => number[] | undefined;
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
  setIncrementalUpdateFlag: (enabled: boolean) => void;
  // Get the Cosmograph instance ref
  getCosmographRef: () => React.RefObject<any>;
}

interface GraphCanvasComponentProps extends GraphCanvasProps {
  nodes: GraphNode[];
  links: GraphLink[];
}

const GraphCanvasV2 = forwardRef<GraphCanvasHandle, GraphCanvasComponentProps>(
  ({ 
    onNodeClick, 
    onNodeSelect, 
    onSelectNodes, 
    onClearSelection, 
    onStatsUpdate, 
    onContextReady,
    selectedNodes = [], 
    highlightedNodes = [], 
    className, 
    stats, 
    nodes: initialNodes = [], 
    links: initialLinks = [] 
  }, ref) => {
    
    // Component state
    const cosmographRef = useRef<any>(null);
    const [isReady, setIsReady] = useState(false);
    const [isCanvasReady, setIsCanvasReady] = useState(false);
    const [loadingPhase, setLoadingPhase] = useState<string>('');
    const [loadingProgress, setLoadingProgress] = useState<{ loaded: number; total: number }>({ loaded: 0, total: 0 });
    
    // PERFORMANCE FIX: Refs for logging counts without causing callback recreation
    const nodesLengthRef = useRef<number>(0);
    const linksLengthRef = useRef<number>(0);
    
    // Attach debugger on mount (only if debugging is enabled)
    useEffect(() => {
      if (isSchemaDebuggingEnabled()) {
        attachSchemaDebugger();
        // Debug schema after cosmograph is ready
        if (cosmographRef.current && isCanvasReady) {
          console.log('[GraphCanvasV2] Inspecting Cosmograph schema...');
          inspectCosmographSchema(cosmographRef);
        }
      }
    }, [isCanvasReady]);
    
    // PERFORMANCE FIX (GRAPH-35): Use extracted hook for glow effects
    const {
      glowingNodes,
      setGlowingNodes,
      addGlowingNodes,
      clearGlowingNodes,
      glowTimeoutRef
    } = useGraphGlowEffects({ fadeDuration: 2000, cleanupDelay: 100 });
    
    // Context hooks
    const { config, setCosmographRef } = useGraphConfig();
    const loadingCoordinator = useLoadingCoordinator();
    
    // PERFORMANCE FIX (GRAPH-35): Use extracted hook for live counts (WebSocket delta tracking)
    const {
      liveNodeCount,
      liveEdgeCount,
      resetCounts
    } = useGraphLiveCounts({ debug: false });
    
    // === 1. HOOKS ===
    
    // Memoize the stats update callback to prevent infinite loops
    const handleStatsUpdate = useCallback((stats: any) => {
      if (onStatsUpdate) {
        onStatsUpdate({
          nodeCount: stats.nodeCount,
          edgeCount: stats.edgeCount,
          lastUpdated: stats.lastUpdated
        });
      }
    }, [onStatsUpdate]);
    
    // Statistics tracking
    const {
      statistics,
      updateStatistics,
      getBasicStats,
      getPerformanceMetrics
    } = useGraphStatistics(initialNodes, initialLinks as any, {
      detailed: true,
      updateThrottle: 1000,
      trackPerformance: true,
      onStatsUpdate: handleStatsUpdate
    });
    
    // Memoize initial data to prevent re-initialization
    const memoizedInitialData = useMemo(
      () => ({ nodes: initialNodes, links: initialLinks }),
      [initialNodes?.length, initialLinks?.length] // Only re-create if lengths change
    );
    
    // Data management
    const {
      nodes,
      links,
      loading,
      error,
      resetData: setData,
      addNodes,
      addLinks,
      updateNodes,
      updateLinks,
      removeNodes,
      removeLinks,
      refresh: refreshData
    } = useGraphDataManagement({
      initialNodes: memoizedInitialData.nodes,
      initialLinks: memoizedInitialData.links as any,
      dataSource: {
        enableCache: true,
        cacheDuration: 5 * 60 * 1000,
        maxCacheSize: 100
      },
      optimisticUpdates: true,
      autoDedup: true,
      onDataUpdate: (event) => {
        // Don't log here to avoid noise
      },
      debug: false
    });
    
    // PERFORMANCE FIX: Keep refs updated for logging without causing callback recreation
    useEffect(() => {
      nodesLengthRef.current = nodes?.length || 0;
      linksLengthRef.current = links?.length || 0;
    }, [nodes?.length, links?.length]);
    
    // PERFORMANCE FIX (GRAPH-36): Use extracted hook for O(1) node lookups
    // IMPORTANT: Must be defined before useGraphSelection which uses nodeIndexMap
    const { nodeIndexMap, getNodeIndex, getNodeIndices } = useGraphNodeIndex(nodes);
    
    // PERFORMANCE: Hover is now handled by Cosmograph's built-in system
    // No custom hover state management needed
    
    // Selection management
    const {
      selectedNodeIds,
      selectedLinkIds,
      selectNode: selectSingleNode,
      selectNodes: selectMultipleNodes,
      deselectNode,
      clearSelection: clearAllSelection,
      toggleNodeSelection,
      selectAll,
      invertSelection,
      selectConnectedNodes,
      isNodeSelected,
      getSelectedNodes: getSelectedNodesList
    } = useGraphSelection(nodes, links as any, {
      multiSelect: true,
      // PERFORMANCE FIX: Use nodeIndexMap for O(1) lookups instead of O(n*m) filter
      // DISABLED: onSelectionChange was causing panel updates on hover
      // The click handler in useGraphCanvasEvents already handles selection
      onSelectionChange: undefined
    });
    
    // WebSocket callbacks
    const handleNodeAccess = useCallback((event: any) => {
      // Handle node access events when needed
    }, []);
    
    // Incremental updates hook - must be defined before using its values
    const {
      applyDelta,
      replaceDataWithConfig,
      metrics: incrementalMetrics,
      isReady: incrementalUpdatesReady
    } = useCosmographIncrementalUpdates(
      cosmographRef,
      nodes,
      links as GraphLink[],
      {
        debug: true,
        config: {
          clusteringMethod: config.clusteringMethod,
          centralityMetric: config.centralityMetric,
          clusterStrength: config.clusterStrength,
          sizeMapping: config.sizeMapping
        },
        onError: (error) => {
          // Only log errors in development
          if (process.env.NODE_ENV === 'development') {
            console.error('[GraphCanvasV2] Incremental update error:', error);
          }
        },
        onSuccess: (_operation, _count) => {
          // Success logging removed for performance
        },
        fallbackToFullUpdate: (fallbackNodes, fallbackEdges) => {
          // Fall back to traditional state update
          setData(fallbackNodes, fallbackEdges as any);
        }
      }
    );
    
    const handleGraphUpdate = useCallback(async (event: any) => {
      if (event.nodes && event.edges) {
        // Try to use setConfig for seamless data replacement
        if (incrementalUpdatesReady && replaceDataWithConfig) {
          const success = await replaceDataWithConfig(event.nodes, event.edges);
          if (success) {
            return; // Data replaced using setConfig (no hard reload)
          }
        }
        // Fall back to traditional state update
        setData(event.nodes, event.edges as any);
      }
    }, [setData, incrementalUpdatesReady, replaceDataWithConfig]);
    
    // PERFORMANCE FIX: Use refs for logging to avoid callback recreation on data changes
    const handleDeltaUpdate = useCallback(async (event: any) => {
      // Try incremental update first if Cosmograph is ready
      if (incrementalUpdatesReady && cosmographRef.current) {
        const success = await applyDelta(event);
        if (success) {
          return; // Exit early - incremental update succeeded
        }
      }
      
      // Fall back to traditional state-based updates
      // Handle node updates
      if (event.nodes && event.nodes.length > 0) {
        if (event.operation === 'add') {
          addNodes(event.nodes);
        } else if (event.operation === 'update') {
          updateNodes(event.nodes);
        } else if (event.operation === 'delete') {
          const nodeIds = typeof event.nodes[0] === 'string' 
            ? event.nodes 
            : event.nodes.map((n: any) => n.id);
          removeNodes(nodeIds);
        }
      }
      
      // Handle edge updates
      if (event.edges && event.edges.length > 0) {
        if (event.operation === 'add') {
          addLinks(event.edges);
        } else if (event.operation === 'update') {
          addLinks(event.edges);
        } else if (event.operation === 'delete') {
          const edgeIds = typeof event.edges[0] === 'string'
            ? event.edges
            : event.edges.map((e: any) => `${e.from || e.source}-${e.to || e.target}`);
          removeLinks(edgeIds);
        }
      }
    }, [incrementalUpdatesReady, applyDelta, addNodes, updateNodes, removeNodes, addLinks, removeLinks]);
    
    // WebSocket updates
    const {
      connectionStatus,
      isConnected,
      statistics: wsStats,
      triggerNodeAccess,
      triggerGraphUpdate,
      triggerDeltaUpdate,
      getRecentEvents
    } = useGraphWebSocket({
      enablePython: false,  // Python WebSocket disabled
      enableRust: true,     // Enable Rust WebSocket for real-time updates
      batchInterval: 100,
      onNodeAccess: handleNodeAccess,
      onGraphUpdate: handleGraphUpdate,
      onDeltaUpdate: handleDeltaUpdate,
      debug: false  // PERFORMANCE: Disabled in production
    });
    
    // Camera controls
    const {
      cameraState,
      controls: cameraControls,
      zoomIn,
      zoomOut,
      zoomTo,
      pan,
      panTo,
      reset: resetCamera,
      fitToView,
      fitToNodes,
      centerOnNode,
      centerOnNodes,
      isAnimating: isCameraAnimating
    } = useGraphCamera(nodes, {
      initialZoom: 1,
      minZoom: 0.1,
      maxZoom: 10,
      enableKeyboardControls: true
    });
    
    // Interactions
    const {
      dragState,
      hoveredNode,
      handleNodeClick: handleInteractionNodeClick,
      handleNodeHover: handleInteractionNodeHover,
      startNodeDrag,
      updateNodeDrag,
      endNodeDrag,
      isInteracting
    } = useGraphInteractions(nodes, links as any, {
      enableClick: true,
      enableDrag: true,
      enableHover: true,
      onNodeClick: (nodeId, event) => {
        // Click is now handled directly in Cosmograph's onClick
      },
      onNodeHover: (nodeId) => {
        // Hover is now handled by Cosmograph's built-in onPointMouseOver/Out
      }
    });
    
    // Simulation
    const {
      simulationState,
      isRunning: isSimulationRunning,
      start: startSim,
      stop: stopSim,
      restart: restartSim,
      reheat,
      applyLayout
    } = useGraphSimulation(nodes, links as any, {
      autoStart: false,
      forces: [
        { type: 'charge', strength: -300, enabled: true },
        { type: 'link', strength: 1, enabled: true },
        { type: 'center', strength: 0.1, enabled: true }
      ]
    });
    
    // Visual effects
    const {
      activeEffects,
      highlightNodes: highlightNodeVisuals,
      highlightLinks: highlightLinkVisuals,
      pulseNodes,
      createRipple,
      visualStyle,
      updateStyle,
      isNodeHighlighted,
      isAnimating: isEffectsAnimating
    } = useGraphVisualEffects(nodes, links as any, {
      enabled: true,
      defaultNodeStyle: {
        fill: (node: GraphNode) => generateNodeTypeColor(node.node_type),
        strokeWidth: 2,
        opacity: 0.9
      },
      defaultLinkStyle: {
        stroke: '#999',
        strokeWidth: 1,
        opacity: 0.6
      }
    });
    
    // === 2. DATA PREPARATION ===
    
    // Note: nodeIndexMap, getNodeIndex, getNodeIndices are defined earlier (before useGraphSelection)
    
    // Transform nodes and links for Cosmograph using extracted hook
    const cosmographData = useCosmographDataTransform(
      nodes || [],
      links || [],
      {
        clusteringMethod: config.clusteringMethod,
        centralityMetric: config.centralityMetric,
        clusterStrength: config.clusterStrength
      }
    );
    
    // === 3. EVENT HANDLERS ===
    
    // Extract event handling logic into dedicated hook
    const { handleClick, handleMouseOver, handleMouseOut } = useGraphCanvasEvents({
      nodes: nodes || [],
      cosmographRef,
      onNodeClick,
      onNodeSelect,
      onClearSelection
    });
    
    // PERFORMANCE FIX: Memoize eventHandlers object to prevent re-renders
    const eventHandlers = useMemo(() => ({
      handleClick,
      handleMouseOver,
      handleMouseOut
    }), [handleClick, handleMouseOver, handleMouseOut]);
    
    
    // === VISUALIZATION CONFIGURATION (using extracted hook) ===
    const visualConfig = useCosmographVisualization({
      config,
      cosmographData,
      glowingNodes,
      highlightedNodes
    });
    
    
    // CSS variables for styling
    const containerStyle: React.CSSProperties = {
      ['--cosmograph-label-size' as any]: `${config.labelSize}px`,
      ['--cosmograph-border-width' as any]: '0px',
      ['--cosmograph-border-color' as any]: 'rgba(0,0,0,0.5)',
      width: '100%',
      height: '100%',
      position: 'relative' as const,  // Changed from absolute to relative
      // Removed inset: 0 which was making it cover everything
    };
    
    // === 3. IMPERATIVE HANDLE ===
    
    // PERFORMANCE FIX (P3-2): Store dependencies in refs to avoid handle recreation
    // These refs are updated by effects and read by the imperative handle
    const nodeIndexMapRef = useRef(nodeIndexMap);
    const statisticsRef = useRef(statistics);
    const clearAllSelectionRef = useRef(clearAllSelection);
    const selectSingleNodeRef = useRef(selectSingleNode);
    const selectMultipleNodesRef = useRef(selectMultipleNodes);
    const setDataRef = useRef(setData);
    const addNodesRef = useRef(addNodes);
    const addLinksRef = useRef(addLinks);
    const updateNodesRef = useRef(updateNodes);
    const updateLinksRef = useRef(updateLinks);
    const removeNodesRef = useRef(removeNodes);
    const removeLinksRef = useRef(removeLinks);
    const reheatRef = useRef(reheat);
    const configRef = useRef(config);
    
    // Keep refs in sync with latest values
    useEffect(() => {
      nodeIndexMapRef.current = nodeIndexMap;
      statisticsRef.current = statistics;
      clearAllSelectionRef.current = clearAllSelection;
      selectSingleNodeRef.current = selectSingleNode;
      selectMultipleNodesRef.current = selectMultipleNodes;
      setDataRef.current = setData;
      addNodesRef.current = addNodes;
      addLinksRef.current = addLinks;
      updateNodesRef.current = updateNodes;
      updateLinksRef.current = updateLinks;
      removeNodesRef.current = removeNodes;
      removeLinksRef.current = removeLinks;
      reheatRef.current = reheat;
      configRef.current = config;
    });
    
    // Now useImperativeHandle has NO dependencies - methods read from refs
    useImperativeHandle(ref, () => ({
      // Selection methods
      clearSelection: () => {
        clearAllSelectionRef.current();
        setGlowingNodes(new Map());
        if (cosmographRef.current?.unselectAllPoints) {
          cosmographRef.current.unselectAllPoints();
        }
      },
      selectNode: (node: GraphNode) => {
        selectSingleNodeRef.current(node.id);
        setGlowingNodes(new Map([[node.id, Date.now()]]));
        const index = nodeIndexMapRef.current.get(node.id);
        if (index !== undefined && cosmographRef.current?.selectPoint) {
          cosmographRef.current.selectPoint(index, false, false);
        }
      },
      selectNodes: (nodeList: GraphNode[]) => {
        selectMultipleNodesRef.current(nodeList.map(n => n.id));
        const newGlowing = new Map<string, number>();
        const now = Date.now();
        nodeList.forEach(node => newGlowing.set(node.id, now));
        setGlowingNodes(newGlowing);
        const indices: number[] = [];
        nodeList.forEach(node => {
          const index = nodeIndexMapRef.current.get(node.id);
          if (index !== undefined) indices.push(index);
        });
        if (indices.length > 0 && cosmographRef.current?.selectPoints) {
          cosmographRef.current.selectPoints(indices, false);
        }
      },
      
      // Camera methods - read nodeIndexMap from ref
      focusOnNodes: (nodeIds: string[], duration?: number, padding?: number) => {
        const indices: number[] = [];
        nodeIds.forEach(id => {
          const index = nodeIndexMapRef.current.get(id);
          if (index !== undefined) indices.push(index);
        });
        if (indices.length > 0 && cosmographRef.current?.fitViewByIndices) {
          cosmographRef.current.fitViewByIndices(indices, duration, padding);
        }
      },
      
      // These methods just forward to cosmographRef - no deps needed
      zoomIn: () => {
        if (cosmographRef.current?.getZoomLevel && cosmographRef.current?.setZoomLevel) {
          const currentZoom = cosmographRef.current.getZoomLevel();
          cosmographRef.current.setZoomLevel(currentZoom * 1.5, 250);
        }
      },
      zoomOut: () => {
        if (cosmographRef.current?.getZoomLevel && cosmographRef.current?.setZoomLevel) {
          const currentZoom = cosmographRef.current.getZoomLevel();
          cosmographRef.current.setZoomLevel(currentZoom / 1.5, 250);
        }
      },
      fitView: (duration?: number, padding?: number) => {
        cosmographRef.current?.fitView?.(duration, padding);
      },
      fitViewByPointIndices: (indices: number[], duration?: number, padding?: number) => {
        cosmographRef.current?.fitViewByIndices?.(indices, duration, padding);
      },
      zoomToPoint: (index: number, duration?: number, scale?: number, canZoomOut?: boolean) => {
        cosmographRef.current?.zoomToPoint?.(index, duration, scale, canZoomOut);
      },
      trackPointPositionsByIndices: (indices: number[]) => {
        cosmographRef.current?.trackPointPositionsByIndices?.(indices);
      },
      getTrackedPointPositionsMap: () => {
        return cosmographRef.current?.getTrackedPointPositionsMap?.();
      },
      
      // Data methods - read from refs
      setData: (newNodes: GraphNode[], newLinks: GraphLink[], runSimulation = true) => {
        setDataRef.current(newNodes, newLinks as any);
        if (runSimulation && configRef.current.simulationEnabled) {
          cosmographRef.current?.restart?.();
        }
      },
      restart: () => {
        cosmographRef.current?.restart?.();
      },
      getLiveStats: () => ({
        nodeCount: statisticsRef.current.nodeCount,
        edgeCount: statisticsRef.current.edgeCount,
        lastUpdated: statisticsRef.current.lastUpdated
      }),
      
      // Selection tools - just forward to cosmographRef
      activateRectSelection: () => {
        cosmographRef.current?.activateRectSelection?.();
      },
      deactivateRectSelection: () => {
        cosmographRef.current?.deactivateRectSelection?.();
      },
      activatePolygonalSelection: () => {
        cosmographRef.current?.activatePolygonalSelection?.();
      },
      deactivatePolygonalSelection: () => {
        cosmographRef.current?.deactivatePolygonalSelection?.();
      },
      selectPointsInRect: (selection, addToSelection) => {
        cosmographRef.current?.selectPointsInRect?.(selection, addToSelection);
      },
      selectPointsInPolygon: (polygonPoints, addToSelection) => {
        cosmographRef.current?.selectPointsInPolygon?.(polygonPoints, addToSelection);
      },
      getConnectedPointIndices: (index: number) => {
        return cosmographRef.current?.getConnectedPointIndices?.(index);
      },
      getPointIndicesByExactValues: (keyValues) => {
        return cosmographRef.current?.getPointIndicesByExactValues?.(keyValues);
      },
      
      // Incremental update methods - read from refs
      addIncrementalData: (newNodes: GraphNode[], newLinks: GraphLink[]) => {
        addNodesRef.current(newNodes);
        addLinksRef.current(newLinks as any);
        if (configRef.current.simulationEnabled) {
          reheatRef.current(0.3);
        }
      },
      updateNodes: (updatedNodes: GraphNode[]) => {
        updateNodesRef.current(updatedNodes);
      },
      updateLinks: (updatedLinks: GraphLink[]) => {
        updateLinksRef.current(updatedLinks);
      },
      removeNodes: (nodeIds: string[]) => {
        removeNodesRef.current(nodeIds);
      },
      removeLinks: (linkIds: string[]) => {
        removeLinksRef.current(linkIds);
      },
      
      // Simulation control - just forward to cosmographRef
      startSimulation: (alpha?: number) => {
        cosmographRef.current?.start?.(alpha);
      },
      pauseSimulation: () => {
        cosmographRef.current?.pause?.();
      },
      resumeSimulation: () => {
        cosmographRef.current?.start?.(0.3);
      },
      keepSimulationRunning: (_enable: boolean) => {
        // Currently handled via config settings
      },
      setIncrementalUpdateFlag: (_enabled: boolean) => {
        // Flag for incremental updates - managed internally
      },
      getCosmographRef: () => cosmographRef
    }), [setGlowingNodes]); // Only setGlowingNodes is needed - it's stable from useState
    
    // === 4. EFFECTS ===
    
    // PERFORMANCE FIX (GRAPH-35): Use extracted hook for FPS tracking
    const { fps } = useGraphFPS({
      enabled: config.showFPS,
      hasData: (cosmographData?.nodes?.length || 0) > 0,
      stateUpdateInterval: 2000
    });
    
    // Subscribe to WebSocket events for node access highlighting
    // NOTE: Kept inline instead of using useGraphNodeAccessEvents hook due to
    // stale closure issues with getNodeIndices when nodes change
    const { subscribe: subscribeToWebSocket } = useWebSocketContext();
    useEffect(() => {
      const unsubscribe = subscribeToWebSocket((event: any) => {
        if (event.type === 'node_access' && event.node_ids) {
          // Cancel any existing glow timeout
          if (glowTimeoutRef.current) {
            clearTimeout(glowTimeoutRef.current);
          }
          
          // Update glowing nodes
          addGlowingNodes(event.node_ids);
          
          // Highlight nodes in Cosmograph using O(1) lookups
          if (cosmographRef.current && nodes) {
            const indices = getNodeIndices(event.node_ids);
            
            if (indices.length > 0) {
              // Select all nodes for visual effect
              if (cosmographRef.current.selectPoints) {
                cosmographRef.current.selectPoints(indices, false);
              }
              // Focus on the first node to show the ring
              if (cosmographRef.current.setFocusedPoint) {
                cosmographRef.current.setFocusedPoint(indices[0]);
              }
            }
          }
          
          // Remove glow after 2 seconds
          glowTimeoutRef.current = setTimeout(() => {
            clearGlowingNodes();
            // Clear focus and selection in Cosmograph
            if (cosmographRef.current) {
              if (cosmographRef.current.setFocusedPoint) {
                cosmographRef.current.setFocusedPoint(undefined);
              }
              if (cosmographRef.current.unselectAllPoints) {
                cosmographRef.current.unselectAllPoints();
              }
            }
          }, 2000);
        }
      });
      
      return () => {
        unsubscribe();
        if (glowTimeoutRef.current) {
          clearTimeout(glowTimeoutRef.current);
        }
      };
    }, [subscribeToWebSocket, nodes, getNodeIndices, addGlowingNodes, clearGlowingNodes, glowTimeoutRef]);
    
    // Expose DuckDB utilities for debugging
    useEffect(() => {
      if (typeof window !== 'undefined') {
        (window as any).inspectDuckDBSchema = inspectDuckDBSchema;
        (window as any).resetDuckDBStorage = resetDuckDBStorage;
        (window as any).cosmographRef = cosmographRef;
      }
    }, []);
    
    // Cleanup on unmount - PERFORMANCE FIX (GRAPH-37): Proper WebGL cleanup
    useEffect(() => {
      return () => {
        // Clean up WebGL resources to prevent memory leaks
        if (cosmographRef.current) {
          // Dispose of Cosmograph instance if it has a dispose method
          if (typeof cosmographRef.current.dispose === 'function') {
            cosmographRef.current.dispose();
          }
          // Clear any tracked points
          if (typeof cosmographRef.current.trackPointPositionsByIndices === 'function') {
            cosmographRef.current.trackPointPositionsByIndices([]);
          }
          // Stop any running simulation
          if (typeof cosmographRef.current.pause === 'function') {
            cosmographRef.current.pause();
          }
        }
        
        // Clear any pending timeouts
        if (glowTimeoutRef.current) {
          clearTimeout(glowTimeoutRef.current);
        }
        
        // Notify parent that context is no longer ready
        if (onContextReady) {
          onContextReady(false);
        }
      };
    }, [onContextReady, glowTimeoutRef]);
    
    // Update Cosmograph ref in context - use a flag to prevent loops
    const hasSetRef = useRef(false);
    useEffect(() => {
      if (cosmographRef.current && !hasSetRef.current) {
        setCosmographRef(cosmographRef);
        hasSetRef.current = true;
      }
    }, [cosmographRef.current]); // eslint-disable-line react-hooks/exhaustive-deps
    
    // Handle highlighted nodes - visual selection for Show Neighbors
    // PERFORMANCE FIX (GRAPH-36): O(1) lookup per node instead of O(n) findIndex
    useEffect(() => {
      if (highlightedNodes && highlightedNodes.length > 0 && cosmographRef.current && nodes) {
        // Find indices of highlighted nodes using O(1) Map lookup
        const indices: number[] = [];
        highlightedNodes.forEach(nodeId => {
          const index = nodeIndexMap.get(nodeId);
          if (index !== undefined) indices.push(index);
        });
        
        // Select nodes visually in Cosmograph
        if (indices.length > 0) {
          if (cosmographRef.current.selectPoints) {
            cosmographRef.current.selectPoints(indices, false);
          }
          
          // Fit view to show all selected nodes with smooth animation
          // Use small padding (0.1 = 10% extra space) to avoid zooming out too far
          if (cosmographRef.current.fitViewByIndices) {
            cosmographRef.current.fitViewByIndices(indices, 500, 0.1); // 500ms duration, 10% padding
          }
        }
        
        // Also apply visual effects
        highlightNodeVisuals(highlightedNodes, 2000);
      } else if (highlightedNodes && highlightedNodes.length === 0 && cosmographRef.current) {
        // Clear selection when no nodes are highlighted
        if (cosmographRef.current.unselectAllPoints) {
          cosmographRef.current.unselectAllPoints();
        }
      }
    }, [highlightedNodes, highlightNodeVisuals, nodes, nodeIndexMap]);
    
    // Handle selected nodes - simplified to just update internal state
    // PERFORMANCE FIX: Use Set operations instead of Array.includes (O(1) vs O(n))
    useEffect(() => {
      if (selectedNodes && Array.isArray(selectedNodes) && selectedNodeIds) {
        const selectedSet = new Set(selectedNodes);
        
        // Find nodes to select (in selectedNodes but not in selectedNodeIds)
        for (const id of selectedNodes) {
          if (!selectedNodeIds.has(id)) {
            selectSingleNode(id);
          }
        }
        
        // Find nodes to deselect (in selectedNodeIds but not in selectedNodes)
        for (const id of selectedNodeIds) {
          if (!selectedSet.has(id)) {
            deselectNode(id);
          }
        }
      }
    }, [selectedNodes, selectedNodeIds, selectSingleNode, deselectNode]);
    
    // Update statistics when nodes or links change
    useEffect(() => {
      updateStatistics(nodes, links, 'full');
    }, [nodes, links]); // eslint-disable-line react-hooks/exhaustive-deps
    
    // Re-apply simulation settings when config changes
    useEffect(() => {
      if (cosmographRef.current && !config.disableSimulation) {
        // Restart simulation with new settings
        cosmographRef.current.restart?.();
      }
    }, [
      config.repulsion,
      config.linkSpring,
      config.linkDistance,
      config.gravity,
      config.centerForce,
      config.friction,
      config.simulationDecay,
      config.simulationCluster,
      config.mouseRepulsion,
      config.simulationRepulsionTheta,
      config.clusteringEnabled,
      config.clusterStrength
    ]);
    
    // Notify when context is ready - check if Cosmograph ref exists and data is available
    useEffect(() => {
      // Set a small delay to ensure Cosmograph is fully initialized
      const timer = setTimeout(() => {
        if (onContextReady && cosmographRef.current && cosmographData?.nodes?.length > 0) {
          onContextReady(true);
          setIsReady(true);
          setIsCanvasReady(true);
        }
      }, 500); // 500ms delay to ensure Cosmograph initialization
      
      return () => clearTimeout(timer);
    }, [cosmographData?.nodes?.length]); // Only depend on data availability
    
    // Manually trigger fitView after simulation settles (like old implementation)
    useEffect(() => {
      if (cosmographRef.current && cosmographData?.nodes?.length > 0 && config.fitViewOnInit !== false) {
        // Wait for simulation to settle before fitting view
        // Use simulationDecay time plus a buffer
        const fitDelay = (config.fitViewDelay || 1500); // Default 1.5s to let simulation settle
        
        const fitTimer = setTimeout(() => {
          if (cosmographRef.current?.fitView) {
            cosmographRef.current.fitView(
              config.fitViewDuration || 1000,
              config.fitViewPadding !== undefined ? config.fitViewPadding : 0.2
            );
          }
        }, fitDelay);
        
        return () => clearTimeout(fitTimer);
      }
    }, [cosmographData?.nodes?.length, config.fitViewOnInit, config.fitViewDelay, config.fitViewDuration, config.fitViewPadding]);
    
    // Mark dataPreparation and canvas stages complete when cosmograph data is ready
    useEffect(() => {
      if (cosmographData) {
        // Initialize live counts from initial data (even if empty)
        // PERFORMANCE FIX (GRAPH-35): Use hook's resetCounts function
        resetCounts(cosmographData.nodes?.length || 0, cosmographData.links?.length || 0);

        // Only mark complete if not already complete
        if (loadingCoordinator.getStageStatus('dataPreparation') !== 'complete') {
          loadingCoordinator.setStageComplete('dataPreparation', {
            nodesCount: cosmographData.nodes?.length || 0,
            linksCount: cosmographData.links?.length || 0
          });
        }

        // Only mark canvas complete if not already complete
        // Mark complete even with empty data so loading screen doesn't hang
        if (loadingCoordinator.getStageStatus('canvas') !== 'complete') {
          loadingCoordinator.setStageComplete('canvas', {
            canvasReady: true,
            hasData: (cosmographData.nodes?.length || 0) > 0
          });
        }
      }
    }, [cosmographData?.nodes?.length, cosmographData?.links?.length, resetCounts]); // Use stable dependencies
    
    // === 5. RENDER ===
    
    if (loading || !cosmographData) {
      return (
        <div className="flex items-center justify-center h-full">
          <div className="text-gray-500">Loading graph data...</div>
        </div>
      );
    }
    
    if (error) {
      return (
        <div className="flex items-center justify-center h-full">
          <div className="text-red-500">Error loading graph: {error}</div>
        </div>
      );
    }
    
    return (
      <div className={className} style={containerStyle}>
        {loadingPhase && (
          <ProgressiveLoadingOverlay
            phase={loadingPhase}
            progress={loadingProgress}
          />
        )}
        
        {/* Graph Overlays for stats display */}
        <GraphOverlays
          nodeCount={statistics.nodeCount}
          edgeCount={statistics.edgeCount}
          liveNodeCount={liveNodeCount}
          liveEdgeCount={liveEdgeCount}
          fps={fps}
          visibleNodes={cosmographData?.nodes?.length}
          selectedNodes={selectedNodes?.length ?? 0}
        />
        
        
        <GraphCanvasRenderer
          cosmographRef={cosmographRef}
          cosmographData={cosmographData}
          config={config}
          visualConfig={visualConfig}
          eventHandlers={eventHandlers}
          hasGlowingNodes={glowingNodes.size > 0}
          onReady={() => {
            setIsReady(true);
            setIsCanvasReady(true);
            
            // Check if we have data and notify parent that everything is ready
            if (cosmographRef.current && cosmographData && cosmographData.nodes.length > 0) {
              onContextReady?.(true);
            }
          }}
        />
      </div>
    );
  }
);

GraphCanvasV2.displayName = 'GraphCanvasV2';

export default GraphCanvasV2;