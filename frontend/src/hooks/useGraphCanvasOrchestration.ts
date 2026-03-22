import React, { useEffect, useRef, useState, useCallback, useMemo, type ForwardedRef, type RefObject } from 'react';
import type { CosmographRef } from '@cosmograph/react';
import type { GraphNode, GraphLink } from '../types/graph';
import type { GraphCanvasHandle } from '../types/graphCanvas';
import type {
  GraphCanvasComponentProps,
  WebSocketEvent,
  DeltaUpdateEvent,
  StatsUpdatePayload,
} from '../types/graphCanvasV2Types';

import { useGraphConfig } from './useGraphConfigHooks';
import { generateNodeTypeColor } from '../utils/NodeColorManager';
import { useGraphStatistics } from './useGraphStatistics';
import { useGraphDataManagement } from './useGraphDataManagement';
import { useGraphSelection } from './useGraphSelection';
import { useGraphWebSocket } from './useGraphWebSocket';
import { useGraphCamera } from './useGraphCamera';
import { useGraphInteractions } from './useGraphInteractions';
import { useGraphSimulation } from './useGraphSimulation';
import { useGraphVisualEffects } from './useGraphVisualEffects';
import { useCosmographIncrementalUpdates } from './useCosmographIncrementalUpdates';
import { useCosmographDataTransform } from './useCosmographDataTransform';
import { useGraphCanvasEvents } from './useGraphCanvasEvents';
import { useCosmographVisualization } from './useCosmographVisualization';
import { useGraphCanvasImperativeHandle } from './useGraphCanvasImperativeHandle';
import { useGraphCanvasEffectCoordination } from './useGraphCanvasEffectCoordination';
import { useGraphCanvasDebug } from './useGraphCanvasDebug';
import { useGraphGlowEffects } from './useGraphGlowEffects';
import { useGraphFPS } from './useGraphFPS';
import { useGraphNodeIndex } from './useGraphNodeIndex';
import { useGraphLiveCounts } from './useGraphLiveCounts';
import { useLoadingCoordinator } from '../contexts/LoadingCoordinator';
import { useGraphStore } from '../stores/useGraphStore';
import { inspectCosmographSchema, attachSchemaDebugger, isSchemaDebuggingEnabled } from '../utils/debugCosmographSchema';

export interface GraphCanvasOrchestrationResult {
  cosmographRef: RefObject<CosmographRef>;
  cosmographData: ReturnType<typeof useCosmographDataTransform>;
  config: ReturnType<typeof useGraphConfig>['config'];
  visualConfig: ReturnType<typeof useCosmographVisualization>;
  eventHandlers: { handleClick: (...args: unknown[]) => void; handleMouseOver: (...args: unknown[]) => void; handleMouseOut: (...args: unknown[]) => void };
  containerStyle: React.CSSProperties & Record<string, string>;
  loading: boolean;
  error: unknown;
  statistics: { nodeCount: number; edgeCount: number; lastUpdated: number };
  liveNodeCount: number;
  liveEdgeCount: number;
  fps: number;
  glowingNodesSize: number;
  loadingPhase: string;
  loadingProgress: { loaded: number; total: number };
  isReady: boolean;
  setIsReady: (ready: boolean) => void;
  isCanvasReady: boolean;
  setIsCanvasReady: (ready: boolean) => void;
}

export function useGraphCanvasOrchestration(
  props: GraphCanvasComponentProps,
  ref: ForwardedRef<GraphCanvasHandle>,
): GraphCanvasOrchestrationResult {
  const {
    onNodeClick,
    onNodeSelect,
    onClearSelection,
    onStatsUpdate,
    onContextReady,
    selectedNodes = [],
    highlightedNodes = [],
    nodes: initialNodes = [],
    links: initialLinks = [],
  } = props;

  const cosmographRef = useRef<CosmographRef>(null);
  const [isReady, setIsReady] = useState(false);
  const [isCanvasReady, setIsCanvasReady] = useState(false);
  const nodesLengthRef = useRef<number>(0);
  const linksLengthRef = useRef<number>(0);

  const streamingProgress = useGraphStore(state => state.streamingProgress);
  const loadingPhase = streamingProgress.isStreaming ? streamingProgress.phase : '';
  const loadingProgress = { loaded: streamingProgress.loaded, total: streamingProgress.total };

  // Schema debugger (conditional on debug flag)
  useEffect(() => {
    if (isSchemaDebuggingEnabled()) {
      attachSchemaDebugger();
      if (cosmographRef.current && isCanvasReady) {
        inspectCosmographSchema(cosmographRef);
      }
    }
  }, [isCanvasReady]);

  const {
    glowingNodes,
    setGlowingNodes,
    addGlowingNodes,
    clearGlowingNodes,
    glowTimeoutRef,
  } = useGraphGlowEffects({ fadeDuration: 2000, cleanupDelay: 100 });

  const { config, setCosmographRef } = useGraphConfig();
  const loadingCoordinator = useLoadingCoordinator();

  const { liveNodeCount, liveEdgeCount, resetCounts } = useGraphLiveCounts({ debug: false });

  const handleStatsUpdate = useCallback((stats: StatsUpdatePayload) => {
    if (onStatsUpdate) {
      onStatsUpdate({
        nodeCount: stats.nodeCount,
        edgeCount: stats.edgeCount,
        lastUpdated: stats.lastUpdated,
      });
    }
  }, [onStatsUpdate]);

  const {
    statistics,
    updateStatistics,
  } = useGraphStatistics(initialNodes, initialLinks, {
    detailed: true,
    updateThrottle: 1000,
    trackPerformance: true,
    onStatsUpdate: handleStatsUpdate,
  });

  const memoizedInitialData = useMemo(
    () => ({ nodes: initialNodes, links: initialLinks }),
    [initialNodes?.length, initialLinks?.length],
  );

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
  } = useGraphDataManagement({
    initialNodes: memoizedInitialData.nodes,
    initialLinks: memoizedInitialData.links,
    dataSource: { enableCache: true, cacheDuration: 5 * 60 * 1000, maxCacheSize: 100 },
    optimisticUpdates: true,
    autoDedup: true,
    onDataUpdate: () => {},
    debug: false,
  });

  useEffect(() => {
    nodesLengthRef.current = nodes?.length || 0;
    linksLengthRef.current = links?.length || 0;
  }, [nodes?.length, links?.length]);

  // IMPORTANT: Must be defined before useGraphSelection which uses nodeIndexMap
  const { nodeIndexMap, getNodeIndex, getNodeIndices } = useGraphNodeIndex(nodes);

  const {
    selectedNodeIds,
    selectNode: selectSingleNode,
    selectNodes: selectMultipleNodes,
    deselectNode,
    clearSelection: clearAllSelection,
  } = useGraphSelection(nodes, links, {
    mode: 'multiple',
    onSelectionChange: undefined,
  });

  const handleNodeAccess = useCallback((_event: WebSocketEvent) => {}, []);

  const {
    applyDelta,
    replaceDataWithConfig,
    isReady: incrementalUpdatesReady,
  } = useCosmographIncrementalUpdates(
    cosmographRef,
    nodes,
    links as GraphLink[],
    {
      debug: import.meta.env.DEV,
      config: {
        clusteringMethod: config.clusteringMethod,
        centralityMetric: config.centralityMetric,
        clusterStrength: config.clusterStrength,
      },
      onError: (error) => {
        if (process.env.NODE_ENV === 'development') {
          console.error('[GraphCanvasV2] Incremental update error:', error);
        }
      },
      onSuccess: () => {},
      fallbackToFullUpdate: (fallbackNodes, fallbackEdges) => {
        setData(fallbackNodes, fallbackEdges);
      },
    },
  );

  // Ref for markIncrementalSync — declared before handleDeltaUpdate but populated
  // after useCosmographDataTransform initializes (avoids block-scope forward reference).
  const markIncrementalSyncRef = useRef<(() => void) | null>(null);

  const handleGraphUpdate = useCallback(async (event: WebSocketEvent) => {
    if (event.nodes && event.edges) {
      if (incrementalUpdatesReady && replaceDataWithConfig) {
        const success = await replaceDataWithConfig(event.nodes, event.edges);
        if (success) return;
      }
      setData(event.nodes, event.edges);
    }
  }, [setData, incrementalUpdatesReady, replaceDataWithConfig]);

  const handleDeltaUpdate = useCallback(async (event: DeltaUpdateEvent) => {
    if (incrementalUpdatesReady && cosmographRef.current) {
      const success = await applyDelta(event as unknown as import('../utils/cosmographDataPreparer').DeltaUpdate);
      if (success) {
        markIncrementalSyncRef.current?.();
        return;
      }
    }

    if (event.nodes && event.nodes.length > 0) {
      if (event.operation === 'add') addNodes(event.nodes);
      else if (event.operation === 'update') updateNodes(event.nodes);
      else if (event.operation === 'delete') removeNodes(event.nodes.map((n: GraphNode) => n.id));
    }

    if (event.edges && event.edges.length > 0) {
      if (event.operation === 'add') addLinks(event.edges);
      else if (event.operation === 'update') addLinks(event.edges);
      else if (event.operation === 'delete') removeLinks(event.edges);
    }
  }, [incrementalUpdatesReady, applyDelta, addNodes, updateNodes, removeNodes, addLinks, removeLinks]);

  useGraphWebSocket({
    enablePython: false,
    enableRust: true,
    batchInterval: 500,
    onNodeAccess: handleNodeAccess,
    onGraphUpdate: handleGraphUpdate,
    onDeltaUpdate: handleDeltaUpdate,
    debug: false,
  });

  useGraphCamera(nodes, {
    initialZoom: 1,
    minZoom: 0.1,
    maxZoom: 10,
    enableKeyboardControls: true,
  });

  useGraphInteractions(nodes, links, {
    enableClick: true,
    enableDrag: false,
    enableHover: true,
    onNodeClick: () => {},
    onNodeHover: () => {},
  });

  const { reheat } = useGraphSimulation(nodes, links, {
    autoStart: false,
    forces: [
      { type: 'charge', strength: -300, enabled: true },
      { type: 'link', strength: 1, enabled: true },
      { type: 'center', strength: 0.1, enabled: true },
    ],
  });

  const { highlightNodes: highlightNodeVisuals } = useGraphVisualEffects(nodes, links, {
    enabled: true,
    defaultNodeStyle: {
      fill: (node: GraphNode) => generateNodeTypeColor(node.node_type, 0),
      strokeWidth: 2,
      opacity: 0.9,
    },
    defaultLinkStyle: {
      stroke: '#999',
      strokeWidth: 1,
      opacity: 0.6,
    },
  });

  const cosmographData = useCosmographDataTransform(
    nodes || [],
    links || [],
    {
      clusteringMethod: config.clusteringMethod,
      centralityMetric: config.centralityMetric,
      clusterStrength: config.clusterStrength,
    },
  );
  markIncrementalSyncRef.current = cosmographData.markIncrementalSync;

  const { handleClick, handleMouseOver, handleMouseOut } = useGraphCanvasEvents({
    nodes: nodes || [],
    cosmographRef,
    onNodeClick,
    onNodeSelect,
    onClearSelection,
  });

  const eventHandlers = useMemo(() => ({
    handleClick,
    handleMouseOver,
    handleMouseOut,
  }), [handleClick, handleMouseOver, handleMouseOut]);

  const visualConfig = useCosmographVisualization({
    config,
    cosmographData,
    glowingNodes,
    highlightedNodes,
  });

  const containerStyle: React.CSSProperties & Record<string, string> = {
    '--cosmograph-label-size': `${config.labelSize}px`,
    '--cosmograph-border-width': '0px',
    '--cosmograph-border-color': 'rgba(0,0,0,0.5)',
    width: '100%',
    height: '100%',
    position: 'relative',
  };

  useGraphCanvasImperativeHandle({
    ref,
    cosmographRef,
    nodeIndexMap,
    statistics,
    config,
    links,
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
    reheat,
    setGlowingNodes,
  });

  const { fps } = useGraphFPS({
    enabled: config.showFPS,
    hasData: (cosmographData?.nodes?.length || 0) > 0,
    stateUpdateInterval: 2000,
  });

  useGraphCanvasDebug({
    cosmographRef,
    nodes,
    getNodeIndices,
    addGlowingNodes,
    clearGlowingNodes,
    glowTimeoutRef,
    setCosmographRef,
    onContextReady,
  });

  useGraphCanvasEffectCoordination({
    cosmographRef,
    cosmographData,
    highlightedNodes,
    selectedNodes,
    nodes,
    links,
    nodeIndexMap,
    selectedNodeIds,
    config,
    loadingCoordinator,
    highlightNodeVisuals,
    selectSingleNode,
    deselectNode,
    updateStatistics,
    resetCounts,
    onContextReady,
    setIsReady,
    setIsCanvasReady,
  });

  return {
    cosmographRef,
    cosmographData,
    config,
    visualConfig,
    eventHandlers,
    containerStyle,
    loading,
    error,
    statistics,
    liveNodeCount,
    liveEdgeCount,
    fps,
    glowingNodesSize: glowingNodes.size,
    loadingPhase,
    loadingProgress,
    isReady,
    setIsReady,
    isCanvasReady,
    setIsCanvasReady,
  };
}
