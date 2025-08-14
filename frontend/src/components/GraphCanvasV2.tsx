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
import { Cosmograph, prepareCosmographData } from '@cosmograph/react';
import '../styles/cosmograph.css';
import { GraphNode } from '../api/types';
import type { GraphData, GraphLink } from '../types/graph';
import { useGraphConfig } from '../contexts/GraphConfigProvider';
import { hexToRgba, generateHSLColor } from '../utils/colorCache';

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

// Additional imports
import { useLoadingCoordinator } from '../contexts/LoadingCoordinator';
import { ProgressiveLoadingOverlay } from './ProgressiveLoadingOverlay';
import { useWebSocketContext } from '../contexts/WebSocketProvider';
import { GraphOverlays } from './GraphOverlays';
import { 
  CosmographDataPreparer, 
  getGlobalDataPreparer,
  sanitizeNode,
  sanitizeLink
} from '../utils/cosmographDataPreparer';
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
    onNodeHover, 
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
          clusterStrength: config.clusterStrength
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
        const node = nodeId ? nodes.find(n => n.id === nodeId) : null;
        if (onNodeHover) {
          onNodeHover(node || null);
        }
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
    
    // Get global data preparer instance
    const dataPreparerRef = useRef<CosmographDataPreparer>(getGlobalDataPreparer({
      clusteringMethod: config.clusteringMethod,
      centralityMetric: config.centralityMetric,
      clusterStrength: config.clusterStrength
    }));
    
    // Update preparer config when it changes
    useEffect(() => {
      dataPreparerRef.current.updateConfig({
        clusteringMethod: config.clusteringMethod,
        centralityMetric: config.centralityMetric,
        clusterStrength: config.clusterStrength
      });
    }, [config.clusteringMethod, config.centralityMetric, config.clusterStrength]);
    
    // Prepare data for Cosmograph using unified preparer
    const cosmographData = useMemo(() => {
      if (!nodes || !links) {
        return { nodes: [], links: [] };
      }
      
      // Use the data preparer for consistent transformation
      // This ensures both initial load and incremental updates use the same pipeline
      const preparer = dataPreparerRef.current;
      
      // Prepare initial data synchronously (since we're in a useMemo)
      // The prepareInitialData is async but we can use the synchronous sanitization
      preparer.reset(); // Clear any previous state
      
      // Build node index map and sanitize nodes
      const nodeIdToIndex = new Map<string, number>();
      const nodeTypeIndexMap = new Map<string, number>();
      
      const transformedNodes = nodes.map((node, index) => {
        nodeIdToIndex.set(node.id, index);
        
        // Get or assign node type index for color generation
        const nodeType = node.node_type || 'Unknown';
        if (!nodeTypeIndexMap.has(nodeType)) {
          nodeTypeIndexMap.set(nodeType, nodeTypeIndexMap.size);
        }
        
        // Use the sanitizeNode function from cosmographDataPreparer
        return sanitizeNode(node, index, {
          clusteringMethod: config.clusteringMethod,
          centralityMetric: config.centralityMetric,
          clusterStrength: config.clusterStrength,
          nodeTypeIndexMap
        });
      });
      
      // Transform links using sanitization
      const transformedLinks = links
        .map(link => sanitizeLink(link, nodeIdToIndex))
        .filter(link => link !== null);
      
      return {
        nodes: transformedNodes,
        links: transformedLinks
      };
    }, [nodes, links, config.clusteringMethod, config.centralityMetric, config.clusterStrength]);
    
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
        if (cosmographRef.current?.unselectAllPoints) {
          cosmographRef.current.unselectAllPoints();
        }
      },
      selectNode: (node: GraphNode) => {
        selectSingleNode(node.id);
        // Also select in Cosmograph
        const index = nodes.findIndex(n => n.id === node.id);
        if (index >= 0 && cosmographRef.current?.selectPoint) {
          cosmographRef.current.selectPoint(index, false, false);
        }
      },
      selectNodes: (nodeList: GraphNode[]) => {
        selectMultipleNodes(nodeList.map(n => n.id));
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
          
          // Highlight nodes in Cosmograph by selecting them
          if (cosmographRef.current && nodes) {
            const indices: number[] = [];
            event.node_ids.forEach((nodeId: string) => {
              const index = nodes.findIndex(n => n.id === nodeId);
              if (index >= 0) indices.push(index);
            });
            
            if (indices.length > 0 && cosmographRef.current.selectPoints) {
              cosmographRef.current.selectPoints(indices, false);
            }
          }
          
          // Remove glow after 2 seconds
          glowTimeoutRef.current = setTimeout(() => {
            setGlowingNodes(new Map());
            // Clear selection in Cosmograph
            if (cosmographRef.current?.unselectAllPoints) {
              cosmographRef.current.unselectAllPoints();
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
      if (cosmographData && cosmographData.nodes?.length > 0) {
        // Initialize live counts from initial data
        setLiveNodeCount(cosmographData.nodes.length);
        setLiveEdgeCount(cosmographData.links?.length || 0);
        
        // Only mark complete if not already complete
        if (loadingCoordinator.getStageStatus('dataPreparation') !== 'complete') {
          loadingCoordinator.setStageComplete('dataPreparation', {
            nodesCount: cosmographData.nodes?.length || 0,
            linksCount: cosmographData.links?.length || 0
          });
        }
        
        // Only mark canvas complete if not already complete
        if (loadingCoordinator.getStageStatus('canvas') !== 'complete') {
          loadingCoordinator.setStageComplete('canvas', {
            canvasReady: true,
            hasData: true
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
        
        <Cosmograph
          ref={cosmographRef}
          // Use points/links instead of nodes/links
          points={cosmographData.nodes}
          links={cosmographData.links}
          // Point configuration - tell Cosmograph how to interpret the data
          pointIdBy="id"
          pointIndexBy="index"
          pointLabelBy={config.labelBy || "label"}
          pointColorBy="node_type"
          pointSizeBy="size"
          pointClusterBy={config.clusteringEnabled ? "cluster" : undefined}
          pointClusterStrengthBy={config.clusteringEnabled ? "clusterStrength" : undefined}
          // Label configuration - using Cosmograph's actual API
          showLabels={config.renderLabels || false}
          pointLabelFontSize={config.labelSize || 12}
          pointLabelColor={config.labelColor || "#ffffff"}
          showDynamicLabels={config.showDynamicLabels || false}
          showTopLabels={config.showTopLabels || false}
          showTopLabelsLimit={config.showTopLabelsLimit || 100}
          showHoveredPointLabel={config.showHoveredNodeLabel !== false}
          // Use className for background and font weight styling
          pointLabelClassName={() => 
            `background: ${config.labelBackgroundColor || 'rgba(0,0,0,0.7)'}; ` +
            `font-weight: ${config.labelFontWeight || 400}; ` +
            `padding: 4px 6px; border-radius: 3px;`
          }
          hoveredPointLabelClassName={() => 
            `background: ${config.hoveredLabelBackgroundColor || 'rgba(0,0,0,0.9)'}; ` +
            `font-weight: ${config.hoveredLabelFontWeight || 600}; ` +
            `font-size: ${config.hoveredLabelSize || 14}px; ` +
            `color: ${config.hoveredLabelColor || '#ffffff'}; ` +
            `padding: 5px 8px; border-radius: 4px;`
          }
          // Link configuration - use indices for performance
          linkSourceBy="source"
          linkSourceIndexBy="sourceIndex"
          linkTargetBy="target"
          linkTargetIndexBy="targetIndex"
          // Always use edge_type as the base field for linkColorBy
          linkColorBy="edge_type"
          // Link color function based on scheme
          linkColorByFn={
            config.linkColorScheme === 'uniform' ? 
              undefined :  // Let Cosmograph use default linkColor
            config.linkColorScheme === 'by-type' ? 
              (edgeType: any, linkIndex: number) => {
                // Color by edge type
                const typeColors: Record<string, string> = {
                  'relates_to': '#4ECDC4',
                  'causes': '#F6AD55',
                  'precedes': '#B794F6',
                  'contains': '#90CDF4',
                  'default': config.linkColor
                };
                return typeColors[edgeType] || config.linkColor;
              } :
            config.linkColorScheme === 'by-weight' ?
              (edgeType: any, linkIndex: number) => {
                // Get the link data to access weight
                const link = cosmographData.links[linkIndex];
                if (!link) return config.linkColor;
                const weight = link.weight || 0;
                // Interpolate between low and high colors based on weight
                const maxWeight = Math.max(...cosmographData.links.map(l => l.weight || 0));
                const ratio = maxWeight > 0 ? weight / maxWeight : 0;
                // Simple interpolation between blue and red
                const r = Math.round(ratio * 255);
                const b = Math.round((1 - ratio) * 255);
                return `rgb(${r}, 0, ${b})`;
              } :
            config.linkColorScheme === 'by-source-node' ?
              (edgeType: any, linkIndex: number) => {
                // Use source node color - get from config.nodeTypeColors
                const link = cosmographData.links[linkIndex];
                if (!link) return config.linkColor;
                const sourceIndex = link.sourceIndex;
                const sourceNode = cosmographData.nodes[sourceIndex];
                if (!sourceNode) return config.linkColor;
                // Use the color from config.nodeTypeColors or fallback to generated color
                const nodeType = sourceNode.node_type;
                const baseColor = config.nodeTypeColors?.[nodeType] || generateNodeTypeColor(nodeType);
                // Make the color more visible by ensuring good opacity
                return hexToRgba(baseColor, 0.8); // Use 80% opacity for better visibility
              } :
            config.linkColorScheme === 'gradient' ? 
              (edgeType: any, linkIndex: number) => {
                // Use source node color for gradient
                const link = cosmographData.links[linkIndex];
                if (!link) return config.linkColor;
                const sourceIndex = link.sourceIndex;
                const sourceNode = cosmographData.nodes[sourceIndex];
                if (!sourceNode) return config.linkColor;
                // Use the color from config.nodeTypeColors or fallback to generated color
                const nodeType = sourceNode.node_type;
                const baseColor = config.nodeTypeColors?.[nodeType] || generateNodeTypeColor(nodeType);
                // Make the color more visible by ensuring good opacity
                return hexToRgba(baseColor, 0.8); // Use 80% opacity for better visibility
              } :
            config.linkColorScheme === 'by-community' ?
              (edgeType: any, linkIndex: number) => {
                // Color by whether link bridges communities
                const link = cosmographData.links[linkIndex];
                if (!link) return config.linkColor;
                const sourceNode = cosmographData.nodes[link.sourceIndex];
                const targetNode = cosmographData.nodes[link.targetIndex];
                return sourceNode?.cluster === targetNode?.cluster ? 
                  config.linkColor : '#ff6b6b';
              } :
            config.linkColorScheme === 'by-distance' ?
              (edgeType: any, linkIndex: number) => {
                // Color by distance/weight with opacity
                const link = cosmographData.links[linkIndex];
                if (!link) return config.linkColor;
                const weight = link.weight || 1;
                const opacity = Math.max(0.2, Math.min(1, 1 / weight));
                return hexToRgba(config.linkColor, opacity);
              } :
            undefined  // Fallback to default
          }
          linkWidthBy={
            // Only use columns that actually exist in the links data
            // Links only have: source, target, sourceIndex, targetIndex, edge_type
            config.linkWidthScheme === 'by-weight' && cosmographData.links[0]?.weight ? 'weight' : 
            undefined  // Don't use non-existent columns
          }
          // Link visual properties - increased visibility
          linkWidth={config.linkWidth || 2}
          linkOpacity={config.linkOpacity || 0.85}
          linkColor={config.linkColor || '#9CA3AF'}
          linkArrows={config.edgeArrows || false}
          linkArrowSize={config.edgeArrowScale || 1}
          linkCurvature={config.curvedLinks ? (config.curvedLinkWeight || 0.5) : 0}
          // Visual configuration
          backgroundColor={config.backgroundColor}
          pointSizeStrategy="auto"
          pointSizeRange={[config.minNodeSize || 2, config.maxNodeSize || 8]}
          // Color configuration
          pointColorPalette={[
            '#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
            '#1abc9c', '#34495e', '#e67e22', '#95a5a6', '#d35400'
          ]}
          pointColorByMap={config.nodeTypeColors || {}}
          // Interaction
          enableDrag={true}
          enableRightClickRepulsion={true}
          renderLinks={config.renderLinks !== false}
          hoveredPointCursor={config.hoveredPointCursor || "pointer"}
          renderHoveredPointRing={config.renderHoveredPointRing !== false}
          hoveredPointRingColor={config.hoveredPointRingColor || "#ff0000"}
          renderFocusedPointRing={true}
          focusedPointRingColor={glowingNodes.size > 0 ? (config.nodeAccessHighlightColor || "#FFD700") : (config.focusedPointRingColor || "#0066cc")}
          renderSelectedPointRing={true}
          selectedPointRingColor={glowingNodes.size > 0 ? (config.nodeAccessHighlightColor || "#FFD700") : (config.focusedPointRingColor || "#0066cc")}
          // Advanced rendering options
          pixelationThreshold={config.pixelationThreshold || 0}
          renderSelectedNodesOnTop={config.renderSelectedNodesOnTop || false}
          pointsOnEdge={config.pointsOnEdge || false}
          // Layout and simulation - fitView configuration
          fitViewOnInit={false}  // Disable automatic fitView to prevent simulation interruption (like old implementation)
          // fitViewDelay={config.fitViewDelay || 500}  // Not needed when fitViewOnInit is false
          fitViewPadding={config.fitViewPadding !== undefined ? config.fitViewPadding : 0.2}  // Default: 0.2 (20% padding) - normalized value 0-1
          fitViewDuration={config.fitViewDuration || 1000}  // Default: 1000ms - animation duration
          simulationEnabled={!config.disableSimulation && config.simulationEnabled !== false}
          simulationGravity={config.gravity ?? config.simulationGravity ?? 0.1}
          simulationCenter={config.centerForce ?? config.simulationCenter ?? 0.0}
          simulationRepulsion={config.repulsion ?? config.simulationRepulsion ?? 0.5}
          simulationRepulsionTheta={config.simulationRepulsionTheta ?? 1.7}
          simulationLinkDistance={config.linkDistance ?? config.simulationLinkDistance ?? 2}
          simulationLinkSpring={config.linkSpring ?? config.simulationLinkSpring ?? 1}
          simulationLinkDistRandomVariationRange={config.linkDistRandomVariationRange ?? [1, 1.2]}
          simulationFriction={config.friction ?? config.simulationFriction ?? 0.85}
          simulationDecay={config.simulationDecay ?? 1000}
          simulationCluster={config.simulationCluster ?? 0.1}
          simulationClusterStrength={config.clusterStrength ?? config.simulationClusterStrength}
          simulationRepulsionFromMouse={config.mouseRepulsion ?? 2.0}
          // Events
          onReady={() => {
            setIsReady(true);
            setIsCanvasReady(true);
            
            // Check if we have data and notify parent that everything is ready
            if (cosmographRef.current && cosmographData && cosmographData.nodes.length > 0) {
              onContextReady?.(true);
            }
          }}
          onClick={async (index?: number, pointPosition?: [number, number], event?: MouseEvent) => {
            if (typeof index === 'number' && index >= 0) {
              // Visual selection first for immediate feedback
              requestAnimationFrame(() => {
                if (cosmographRef.current?.selectPoint) {
                  cosmographRef.current.selectPoint(index);
                } else if (cosmographRef.current?.selectPoints) {
                  cosmographRef.current.selectPoints([index]);
                }
              });
              
              // Try to get node from local state first (for original nodes)
              if (index < nodes.length) {
                const node = nodes[index];
                if (node) {
                  onNodeClick(node);
                  onNodeSelect(node.id);
                  return;
                }
              }
              
              // For incrementally added nodes, check the data preparer
              const nodeData = dataPreparerRef.current.getNodeByIndex(index);
              if (nodeData) {
                console.log(`[GraphCanvasV2] Clicked on incrementally added node:`, nodeData);
                
                // We have the basic node data, now fetch full details from server
                if (nodeData.id) {
                  try {
                    // Import the graph client
                    const { GraphClient } = await import('../api/graphClient');
                    const client = new GraphClient();
                    
                    // Fetch full node details including centrality
                    const fullNodeData = await client.getNodeDetails(nodeData.id);
                    console.log(`[GraphCanvasV2] Fetched full node details:`, fullNodeData);
                    
                    // Call the callbacks with the full data
                    onNodeClick(fullNodeData as any);
                    onNodeSelect(nodeData.id);
                  } catch (error) {
                    console.error(`[GraphCanvasV2] Failed to fetch node details:`, error);
                    // Fall back to using the minimal data we have
                    onNodeClick(nodeData);
                    onNodeSelect(nodeData.id);
                  }
                } else {
                  // Use the minimal data we have
                  onNodeClick(nodeData);
                  onNodeSelect(nodeData.id || '');
                }
              } else {
                console.warn(`[GraphCanvasV2] No node data found for index ${index}`);
              }
            } else {
              // Clicked on empty space - clear selection
              onClearSelection();
              
              // Also clear visual selection in Cosmograph
              requestAnimationFrame(() => {
                if (cosmographRef.current?.unselectAllPoints) {
                  cosmographRef.current.unselectAllPoints();
                }
              });
            }
          }}
          onMouseMove={(index?: number) => {
            if (typeof index === 'number' && index >= 0 && index < nodes.length) {
              const node = nodes[index];
              if (onNodeHover) {
                onNodeHover(node);
              }
            } else if (onNodeHover) {
              onNodeHover(null);
            }
          }}
        />
      </div>
    );
  }
);

GraphCanvasV2.displayName = 'GraphCanvasV2';

export default GraphCanvasV2;