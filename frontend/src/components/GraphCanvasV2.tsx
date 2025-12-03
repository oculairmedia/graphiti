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
import { GraphNode } from '../api/types';
import type { GraphLink } from '../types/graph';
import { useGraphConfig } from '../contexts/GraphConfigProvider';
import { hexToRgba, interpolateColor } from '../utils/colorCache';
import { generateNodeTypeColor } from '../utils/nodeTypeColors';
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
    selectedNodes, 
    highlightedNodes, 
    className, 
    stats, 
    nodes: initialNodes, 
    links: initialLinks 
  }, ref) => {
    
    // Component state
    const cosmographRef = useRef<any>(null);
    const [isReady, setIsReady] = useState(false);
    const [isCanvasReady, setIsCanvasReady] = useState(false);
    const [loadingPhase, setLoadingPhase] = useState<string>('');
    const [loadingProgress, setLoadingProgress] = useState<{ loaded: number; total: number }>({ loaded: 0, total: 0 });
    
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
    
    // Glowing nodes state for real-time access highlighting
    const [glowingNodes, setGlowingNodes] = useState<Map<string, number>>(new Map());
    const glowTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    
    // Live stats state for overlays
    const [liveNodeCount, setLiveNodeCount] = useState<number>(0);
    const [liveEdgeCount, setLiveEdgeCount] = useState<number>(0);
    const [fps, setFps] = useState<number>(60);
    const fpsIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const lastFrameTimeRef = useRef<number>(performance.now());
    const frameCountRef = useRef<number>(0);
    
    // Context hooks
    const { config, setCosmographRef } = useGraphConfig();
    const loadingCoordinator = useLoadingCoordinator();
    const { subscribe: subscribeToWebSocket } = useWebSocketContext();
    
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
      onSelectionChange: useCallback((event) => {
        // Only handle node selection events
        if (onSelectNodes && event.target === 'node' && event.ids) {
          const selectedNodeObjects = nodes.filter(n => event.ids.includes(n.id));
          onSelectNodes(selectedNodeObjects);
        }
      }, [onSelectNodes, nodes])
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
          console.error('[GraphCanvasV2] Incremental update error:', error);
        },
        onSuccess: (operation, count) => {
          console.log(`[GraphCanvasV2] Incremental ${operation}: ${count} items`);
        },
        fallbackToFullUpdate: (fallbackNodes, fallbackEdges) => {
          console.log('[GraphCanvasV2] Falling back to full update');
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
            console.log('[GraphCanvasV2] Replaced data using setConfig (no hard reload)');
            return;
          }
        }
        // Fall back to traditional state update
        setData(event.nodes, event.edges as any);
      }
    }, [setData, incrementalUpdatesReady, replaceDataWithConfig]);
    
    const handleDeltaUpdate = useCallback(async (event: any) => {
      console.log('[GraphCanvasV2] Received delta update:', event);
      console.log(`[GraphCanvasV2] Current graph size: ${nodes.length} nodes, ${links.length} edges`);
      
      // Try incremental update first if Cosmograph is ready
      if (incrementalUpdatesReady && cosmographRef.current) {
        const success = await applyDelta(event);
        if (success) {
          console.log('[GraphCanvasV2] Applied incremental update successfully');
          
          // DON'T update React state for incremental updates
          // This would trigger a re-render and cause a hard reload
          // The graph is already updated via Cosmograph's incremental API
          // React state will be out of sync but that's acceptable for performance
          
          console.log(`[GraphCanvasV2] After incremental update: ${nodes.length} nodes, ${links.length} edges`);
          return; // Exit early - incremental update succeeded
        }
      }
      
      // Fall back to traditional state-based updates
      console.log('[GraphCanvasV2] Using traditional state update');
      
      // Handle node updates
      if (event.nodes && event.nodes.length > 0) {
        if (event.operation === 'add') {
          console.log('[GraphCanvasV2] Adding nodes:', event.nodes.length);
          addNodes(event.nodes);
        } else if (event.operation === 'update') {
          console.log('[GraphCanvasV2] Updating nodes:', event.nodes.length);
          updateNodes(event.nodes);
        } else if (event.operation === 'delete') {
          console.log('[GraphCanvasV2] Removing nodes:', event.nodes.length);
          const nodeIds = typeof event.nodes[0] === 'string' 
            ? event.nodes 
            : event.nodes.map(n => n.id);
          removeNodes(nodeIds);
        }
      }
      
      // Handle edge updates
      if (event.edges && event.edges.length > 0) {
        if (event.operation === 'add') {
          console.log('[GraphCanvasV2] Adding edges:', event.edges.length);
          addLinks(event.edges);
        } else if (event.operation === 'update') {
          console.log('[GraphCanvasV2] Updating/adding edges:', event.edges.length);
          addLinks(event.edges);
        } else if (event.operation === 'delete') {
          console.log('[GraphCanvasV2] Removing edges:', event.edges.length);
          const edgeIds = typeof event.edges[0] === 'string'
            ? event.edges
            : event.edges.map(e => `${e.from || e.source}-${e.to || e.target}`);
          removeLinks(edgeIds);
        }
      }
      
      // Log final count after traditional update
      console.log(`[GraphCanvasV2] After traditional update: ${nodes.length} nodes, ${links.length} edges`);
    }, [incrementalUpdatesReady, applyDelta, addNodes, updateNodes, removeNodes, addLinks, removeLinks, nodes.length, links.length]);
    
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
      debug: true  // Enable debug logging to monitor updates
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
    
    
    // === VISUALIZATION CONFIGURATION (using extracted hook) ===
    const visualConfig = useCosmographVisualization({
      config,
      cosmographData,
      glowingNodes
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
    
    useImperativeHandle(ref, () => ({
      // Selection methods
      clearSelection: () => {
        clearAllSelection();
        setGlowingNodes(new Map()); // Clear glowing nodes
        if (cosmographRef.current?.unselectAllPoints) {
          cosmographRef.current.unselectAllPoints();
        }
      },
      selectNode: (node: GraphNode) => {
        selectSingleNode(node.id);
        // Add to glowing nodes for highlight color
        setGlowingNodes(new Map([[node.id, Date.now()]]));
        // Also select in Cosmograph
        const index = nodes.findIndex(n => n.id === node.id);
        if (index >= 0 && cosmographRef.current?.selectPoint) {
          cosmographRef.current.selectPoint(index, false, false);
        }
      },
      selectNodes: (nodeList: GraphNode[]) => {
        selectMultipleNodes(nodeList.map(n => n.id));
        // Add all to glowing nodes for highlight color
        const newGlowing = new Map();
        const now = Date.now();
        nodeList.forEach(node => {
          newGlowing.set(node.id, now);
        });
        setGlowingNodes(newGlowing);
        // Also select in Cosmograph
        const indices = nodeList.map(node => nodes.findIndex(n => n.id === node.id)).filter(i => i >= 0);
        if (indices.length > 0 && cosmographRef.current?.selectPoints) {
          cosmographRef.current.selectPoints(indices, false);
        }
      },
      
      // Camera methods
      focusOnNodes: (nodeIds: string[], duration?: number, padding?: number) => {
        // Get indices for the node IDs
        const indices: number[] = [];
        nodeIds.forEach(id => {
          const index = nodes.findIndex(n => n.id === id);
          if (index >= 0) indices.push(index);
        });
        if (indices.length > 0 && cosmographRef.current?.fitViewByIndices) {
          cosmographRef.current.fitViewByIndices(indices, duration, padding);
        }
      },
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
        if (cosmographRef.current?.fitView) {
          cosmographRef.current.fitView(duration, padding);
        }
      },
      fitViewByPointIndices: (indices: number[], duration?: number, padding?: number) => {
        if (cosmographRef.current?.fitViewByIndices) {
          cosmographRef.current.fitViewByIndices(indices, duration, padding);
        }
      },
      zoomToPoint: (index: number, duration?: number, scale?: number, canZoomOut?: boolean) => {
        if (cosmographRef.current?.zoomToPoint) {
          cosmographRef.current.zoomToPoint(index, duration, scale, canZoomOut);
        }
      },
      trackPointPositionsByIndices: (indices: number[]) => {
        if (cosmographRef.current?.trackPointPositionsByIndices) {
          cosmographRef.current.trackPointPositionsByIndices(indices);
        }
      },
      getTrackedPointPositionsMap: () => {
        if (cosmographRef.current?.getTrackedPointPositionsMap) {
          return cosmographRef.current.getTrackedPointPositionsMap();
        }
        return undefined;
      },
      
      // Data methods
      setData: (newNodes: GraphNode[], newLinks: GraphLink[], runSimulation = true) => {
        setData(newNodes, newLinks as any);
        if (runSimulation && config.simulationEnabled && cosmographRef.current?.restart) {
          cosmographRef.current.restart();
        }
      },
      restart: () => {
        if (cosmographRef.current?.restart) {
          cosmographRef.current.restart();
        }
      },
      getLiveStats: () => ({
        nodeCount: statistics.nodeCount,
        edgeCount: statistics.edgeCount,
        lastUpdated: statistics.lastUpdated
      }),
      
      // Selection tools (need Cosmograph integration)
      activateRectSelection: () => {
        if (cosmographRef.current?.activateRectSelection) {
          cosmographRef.current.activateRectSelection();
        }
      },
      deactivateRectSelection: () => {
        if (cosmographRef.current?.deactivateRectSelection) {
          cosmographRef.current.deactivateRectSelection();
        }
      },
      activatePolygonalSelection: () => {
        if (cosmographRef.current?.activatePolygonalSelection) {
          cosmographRef.current.activatePolygonalSelection();
        }
      },
      deactivatePolygonalSelection: () => {
        if (cosmographRef.current?.deactivatePolygonalSelection) {
          cosmographRef.current.deactivatePolygonalSelection();
        }
      },
      selectPointsInRect: (selection, addToSelection) => {
        if (cosmographRef.current?.selectPointsInRect) {
          cosmographRef.current.selectPointsInRect(selection, addToSelection);
        }
      },
      selectPointsInPolygon: (polygonPoints, addToSelection) => {
        if (cosmographRef.current?.selectPointsInPolygon) {
          cosmographRef.current.selectPointsInPolygon(polygonPoints, addToSelection);
        }
      },
      getConnectedPointIndices: (index: number) => {
        if (cosmographRef.current?.getConnectedPointIndices) {
          return cosmographRef.current.getConnectedPointIndices(index);
        }
        return undefined;
      },
      getPointIndicesByExactValues: (keyValues) => {
        if (cosmographRef.current?.getPointIndicesByExactValues) {
          return cosmographRef.current.getPointIndicesByExactValues(keyValues);
        }
        return undefined;
      },
      
      // Incremental update methods
      addIncrementalData: (newNodes: GraphNode[], newLinks: GraphLink[]) => {
        addNodes(newNodes);
        addLinks(newLinks as any);
        if (config.simulationEnabled) {
          reheat(0.3);
        }
      },
      updateNodes: (updatedNodes: GraphNode[]) => {
        updateNodes(updatedNodes);
      },
      updateLinks: (updatedLinks: GraphLink[]) => {
        updateLinks(updatedLinks);
      },
      removeNodes: (nodeIds: string[]) => {
        removeNodes(nodeIds);
      },
      removeLinks: (linkIds: string[]) => {
        removeLinks(linkIds);
      },
      
      // Simulation control
      startSimulation: (alpha?: number) => {
        if (cosmographRef.current?.start) {
          cosmographRef.current.start(alpha);
        }
      },
      pauseSimulation: () => {
        if (cosmographRef.current?.pause) {
          cosmographRef.current.pause();
        }
      },
      resumeSimulation: () => {
        if (cosmographRef.current?.start) {
          cosmographRef.current.start(0.3); // Resume with moderate energy
        }
      },
      keepSimulationRunning: (enable: boolean) => {
        // This would control whether simulation auto-restarts
        // Currently handled via config settings
      },
      setIncrementalUpdateFlag: (enabled: boolean) => {
        // Flag for incremental updates - managed internally
      },
      // Expose the cosmograph ref
      getCosmographRef: () => cosmographRef
    }), [
      nodes,
      statistics,
      clearAllSelection,
      selectSingleNode,
      selectMultipleNodes,
      setData,
      addNodes,
      addLinks,
      updateNodes,
      updateLinks,
      removeNodes,
      removeLinks,
      config.simulationEnabled
    ]);
    
    // === 4. EFFECTS ===
    
    // Clean up old glowing nodes after fade duration
    useEffect(() => {
      if (glowingNodes.size === 0) return;
      
      const timeout = setTimeout(() => {
        const now = Date.now();
        const updatedGlowingNodes = new Map(glowingNodes);
        let hasChanges = false;
        
        // Remove nodes that have finished glowing
        glowingNodes.forEach((startTime, nodeId) => {
          if (now - startTime >= 2000) { // 2 second fade duration
            updatedGlowingNodes.delete(nodeId);
            hasChanges = true;
          }
        });
        
        if (hasChanges) {
          setGlowingNodes(updatedGlowingNodes);
        }
      }, 2100); // Check slightly after fade duration
      
      return () => clearTimeout(timeout);
    }, [glowingNodes]);
    
    // Expose DuckDB utilities for debugging
    useEffect(() => {
      if (typeof window !== 'undefined') {
        (window as any).inspectDuckDBSchema = inspectDuckDBSchema;
        (window as any).resetDuckDBStorage = resetDuckDBStorage;
        (window as any).cosmographRef = cosmographRef;
      }
    }, []);
    
    // Subscribe to WebSocket events for node access highlighting and live counts
    useEffect(() => {
      const unsubscribe = subscribeToWebSocket((event: any) => {
        // Handle delta updates for live counts
        if (event.type === 'delta' && event.data) {
          const deltaData = event.data;
          if (deltaData.added_nodes?.length > 0 || deltaData.removed_nodes?.length > 0) {
            // Update live node count
            setLiveNodeCount(prev => {
              const newCount = prev + (deltaData.added_nodes?.length || 0) - (deltaData.removed_nodes?.length || 0);
              console.log('[GraphCanvasV2] Live node count updated:', newCount);
              return newCount;
            });
          }
          if (deltaData.added_edges?.length > 0 || deltaData.removed_edges?.length > 0) {
            // Update live edge count
            setLiveEdgeCount(prev => {
              const newCount = prev + (deltaData.added_edges?.length || 0) - (deltaData.removed_edges?.length || 0);
              console.log('[GraphCanvasV2] Live edge count updated:', newCount);
              return newCount;
            });
          }
        }
        
        if (event.type === 'node_access' && event.node_ids) {
          console.log('[GraphCanvasV2] Node access event received:', {
            nodeIds: event.node_ids,
            nodeCount: event.node_ids.length
          });
          
          // Cancel any existing glow timeout
          if (glowTimeoutRef.current) {
            clearTimeout(glowTimeoutRef.current);
          }
          
          const now = Date.now();
          
          // Update glowing nodes map
          setGlowingNodes(() => {
            const updated = new Map<string, number>();
            event.node_ids.forEach((nodeId: string) => {
              updated.set(nodeId, now);
            });
            return updated;
          });
          
          // Highlight nodes in Cosmograph using focus (shows the gold ring)
          if (cosmographRef.current && nodes) {
            const indices: number[] = [];
            event.node_ids.forEach((nodeId: string) => {
              const index = nodes.findIndex(n => n.id === nodeId);
              if (index >= 0) indices.push(index);
            });
            
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
            setGlowingNodes(new Map());
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
    }, [subscribeToWebSocket, nodes]);
    
    // FPS calculation effect
    useEffect(() => {
      let animationFrameId: number;
      let lastTime = performance.now();
      let frameCount = 0;
      
      const calculateFPS = () => {
        const now = performance.now();
        const delta = now - lastTime;
        frameCount++;
        
        // Update FPS every second
        if (delta >= 1000) {
          const currentFps = Math.round((frameCount * 1000) / delta);
          setFps(currentFps);
          frameCount = 0;
          lastTime = now;
        }
        
        animationFrameId = requestAnimationFrame(calculateFPS);
      };
      
      // Start FPS calculation
      if (config.showFPS && cosmographData?.nodes?.length > 0) {
        animationFrameId = requestAnimationFrame(calculateFPS);
      }
      
      return () => {
        if (animationFrameId) {
          cancelAnimationFrame(animationFrameId);
        }
      };
    }, [config.showFPS, cosmographData?.nodes?.length]);
    
    // Cleanup on unmount
    useEffect(() => {
      return () => {
        if (onContextReady) {
          onContextReady(false);
        }
      };
    }, [onContextReady]);
    
    // Update Cosmograph ref in context - use a flag to prevent loops
    const hasSetRef = useRef(false);
    useEffect(() => {
      if (cosmographRef.current && !hasSetRef.current) {
        setCosmographRef(cosmographRef);
        hasSetRef.current = true;
      }
    }, [cosmographRef.current]); // eslint-disable-line react-hooks/exhaustive-deps
    
    // Handle highlighted nodes - visual selection for Show Neighbors
    useEffect(() => {
      if (highlightedNodes && highlightedNodes.length > 0 && cosmographRef.current && nodes) {
        // Find indices of highlighted nodes
        const indices: number[] = [];
        highlightedNodes.forEach(nodeId => {
          const index = nodes.findIndex(n => n.id === nodeId);
          if (index >= 0) indices.push(index);
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
    }, [highlightedNodes, highlightNodeVisuals, nodes]);
    
    // Handle selected nodes - simplified to just update internal state
    useEffect(() => {
      // Ensure selectedNodes is defined and is an array
      if (selectedNodes && Array.isArray(selectedNodes) && selectedNodeIds) {
        const currentSelection = Array.from(selectedNodeIds);
        const toSelect = selectedNodes.filter(id => !currentSelection.includes(id));
        const toDeselect = currentSelection.filter(id => !selectedNodes.includes(id));
        
        // Update selection state
        toSelect.forEach(id => selectSingleNode(id));
        toDeselect.forEach(id => deselectNode(id));
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
        setLiveNodeCount(cosmographData.nodes?.length || 0);
        setLiveEdgeCount(cosmographData.links?.length || 0);

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
    }, [cosmographData?.nodes?.length, cosmographData?.links?.length]); // Use stable dependencies
    
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
          selectedNodes={selectedNodes.length}
        />
        
        
        <GraphCanvasRenderer
          cosmographRef={cosmographRef}
          cosmographData={cosmographData}
          config={config}
          visualConfig={visualConfig}
          eventHandlers={{ handleClick, handleMouseOver, handleMouseOut }}
          glowingNodes={glowingNodes}
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