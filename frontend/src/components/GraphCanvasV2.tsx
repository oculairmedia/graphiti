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
import type { GraphData } from '../types/graph';
import { useGraphConfig } from '../contexts/GraphConfigProvider';
import { generateNodeTypeColor } from '../utils/nodeTypeColors';
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

// Keep necessary imports from original
import { useGraphZoom } from '../hooks/useGraphZoom';
import { useGraphEvents } from '../hooks/useGraphEvents';
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts';
import { useColorUtils } from '../hooks/useColorUtils';
import { searchIndex } from '../utils/searchIndex';
import { useLoadingCoordinator } from '../contexts/LoadingCoordinator';
import { ProgressiveLoader } from '../services/progressive-loader';
import { ProgressiveLoadingOverlay } from './ProgressiveLoadingOverlay';
import { useDuckDB } from '../contexts/DuckDBProvider';

interface GraphLink {
  source: string;
  target: string;
  from: string;
  to: string;
  sourceIndex?: number;
  targetIndex?: number;
  weight?: number;
  edge_type?: string;
  [key: string]: unknown;
}

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
}

interface GraphCanvasComponentProps extends GraphCanvasProps {
  nodes: GraphNode[];
  links: GraphLink[];
}

// Track component instances
let instanceCounter = 0;

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
    
    // Track this instance
    const instanceId = useRef(++instanceCounter);
    
    // Log initialization
    console.log(`[GraphCanvasV2 #${instanceId.current}] Initializing with`, {
      nodeCount: initialNodes?.length || 0,
      linkCount: initialLinks?.length || 0,
      hasCallbacks: {
        onNodeClick: !!onNodeClick,
        onNodeSelect: !!onNodeSelect,
        onStatsUpdate: !!onStatsUpdate,
        onContextReady: !!onContextReady
      }
    });
    
    // Component state
    const cosmographRef = useRef<any>(null);
    const [isReady, setIsReady] = useState(false);
    const [isCanvasReady, setIsCanvasReady] = useState(false);
    const [loadingPhase, setLoadingPhase] = useState<string>('');
    const [loadingProgress, setLoadingProgress] = useState<{ loaded: number; total: number }>({ loaded: 0, total: 0 });
    
    // Context hooks
    const { config, setCosmographRef, updateConfig } = useGraphConfig();
    const loadingCoordinator = useLoadingCoordinator();
    const { service: duckdbService, isInitialized: isDuckDBInitialized, getDuckDBConnection } = useDuckDB();
    
    // === 1. USE OUR NEW HOOKS ===
    
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
      initialNodes,
      initialLinks: initialLinks as any,
      dataSource: {
        enableCache: true,
        cacheDuration: 5 * 60 * 1000,
        maxCacheSize: 100
      },
      optimisticUpdates: true,
      autoDedup: true,
      onDataUpdate: (event) => {
        console.log('[GraphCanvasV2] Data update event', event);
        // Don't call updateStatistics here as it can cause loops
      },
      debug: true
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
      onSelectionChange: (selected) => {
        if (onSelectNodes) {
          const selectedNodeObjects = nodes.filter(n => selected.nodes.includes(n.id));
          onSelectNodes(selectedNodeObjects);
        }
      }
    });
    
    // Memoize WebSocket callbacks to prevent re-subscriptions
    const handleNodeAccess = useCallback((event: any) => {
      console.log('[GraphCanvasV2] Node access event', event);
    }, []);
    
    const handleGraphUpdate = useCallback((event: any) => {
      console.log('[GraphCanvasV2] Graph update event', event);
      if (event.nodes && event.edges) {
        setData(event.nodes, event.edges as any);
      }
    }, [setData]);
    
    const handleDeltaUpdate = useCallback((event: any) => {
      console.log('[GraphCanvasV2] Delta update event', event);
      if (event.nodes) {
        if (event.operation === 'add') {
          addNodes(event.nodes);
        } else if (event.operation === 'update') {
          updateNodes(event.nodes);
        } else if (event.operation === 'remove') {
          removeNodes(event.nodes.map(n => n.id));
        }
      }
    }, [addNodes, updateNodes, removeNodes]);
    
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
      enablePython: true,
      enableRust: true,
      batchInterval: 100,
      onNodeAccess: handleNodeAccess,
      onGraphUpdate: handleGraphUpdate,
      onDeltaUpdate: handleDeltaUpdate
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
      enableKeyboardControls: true,
      onZoomChange: (zoom) => {
        console.log('[GraphCanvasV2] Zoom changed', zoom);
      }
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
        const node = nodes.find(n => n.id === nodeId);
        if (node) {
          onNodeClick(node);
          onNodeSelect(nodeId);
        }
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
    
    // === 2. COSMOGRAPH SETUP ===
    
    // Prepare data for Cosmograph
    const cosmographData = useMemo(() => {
      console.log('[GraphCanvasV2] Preparing cosmograph data:', {
        hasNodes: !!nodes,
        hasLinks: !!links,
        nodeCount: nodes?.length || 0,
        linkCount: links?.length || 0
      });
      
      // Always return data structure, even if empty
      if (!nodes || !links) {
        console.log('[GraphCanvasV2] No data arrays provided');
        return { nodes: [], links: [] };
      }
      
      // Transform nodes for Cosmograph
      const transformedNodes = nodes.map((node, index) => ({
        ...node,
        index,
        size: 5,
        color: generateNodeTypeColor(node.node_type)
      }));
      
      // Transform links for Cosmograph
      const transformedLinks = links.map(link => ({
        ...link,
        source: link.source,
        target: link.target,
        from: link.source,
        to: link.target
      }));
      
      return {
        nodes: transformedNodes,
        links: transformedLinks
      };
    }, [nodes, links]);
    
    // CSS variables for styling
    const containerStyle: React.CSSProperties = {
      ['--cosmograph-label-size' as any]: `${config.labelSize}px`,
      ['--cosmograph-border-width' as any]: '0px',
      ['--cosmograph-border-color' as any]: 'rgba(0,0,0,0.5)',
      width: '100%',
      height: '100%',
      position: 'absolute' as const,
      inset: 0,
    };
    
    // === 3. IMPERATIVE HANDLE ===
    
    useImperativeHandle(ref, () => ({
      // Selection methods
      clearSelection: clearAllSelection,
      selectNode: (node: GraphNode) => selectSingleNode(node.id),
      selectNodes: (nodeList: GraphNode[]) => selectMultipleNodes(nodeList.map(n => n.id)),
      
      // Camera methods
      focusOnNodes: (nodeIds: string[], duration?: number, padding?: number) => {
        const targetNodes = nodes.filter(n => nodeIds.includes(n.id));
        if (targetNodes.length > 0) {
          fitToNodes(targetNodes, padding || 50, duration !== undefined);
        }
      },
      zoomIn,
      zoomOut,
      fitView: (duration?: number, padding?: number) => fitToView(padding || 50, duration !== undefined),
      fitViewByPointIndices: (indices: number[], duration?: number, padding?: number) => {
        const targetNodes = indices.map(i => nodes[i]).filter(Boolean);
        if (targetNodes.length > 0) {
          fitToNodes(targetNodes, padding || 50, duration !== undefined);
        }
      },
      zoomToPoint: (index: number, duration?: number, scale?: number) => {
        const node = nodes[index];
        if (node) {
          centerOnNode(node.id, scale, duration !== undefined);
        }
      },
      trackPointPositionsByIndices: (indices: number[]) => {
        // This would need to be implemented with Cosmograph's tracking API
        console.warn('[GraphCanvasV2] trackPointPositionsByIndices not yet implemented');
      },
      getTrackedPointPositionsMap: () => {
        // This would need to be implemented with Cosmograph's tracking API
        console.warn('[GraphCanvasV2] getTrackedPointPositionsMap not yet implemented');
        return undefined;
      },
      
      // Data methods
      setData: (newNodes: GraphNode[], newLinks: GraphLink[]) => {
        setData(newNodes, newLinks as any);
        if (config.simulationEnabled) {
          restartSim();
        }
      },
      restart: restartSim,
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
        if (alpha !== undefined) {
          reheat(alpha);
        } else {
          startSim();
        }
      },
      pauseSimulation: stopSim,
      resumeSimulation: startSim,
      keepSimulationRunning: (enable: boolean) => {
        if (enable && !isSimulationRunning) {
          startSim();
        } else if (!enable && isSimulationRunning) {
          stopSim();
        }
      },
      setIncrementalUpdateFlag: (enabled: boolean) => {
        console.log('[GraphCanvasV2] Incremental update flag set to', enabled);
      }
    }), [
      nodes,
      statistics,
      clearAllSelection,
      selectSingleNode,
      selectMultipleNodes,
      zoomIn,
      zoomOut,
      fitToView,
      fitToNodes,
      centerOnNode,
      setData,
      addNodes,
      addLinks,
      updateNodes,
      updateLinks,
      removeNodes,
      removeLinks,
      restartSim,
      startSim,
      stopSim,
      reheat,
      isSimulationRunning,
      config.simulationEnabled
    ]);
    
    // === 4. EFFECTS ===
    
    // Log component lifecycle
    useEffect(() => {
      console.log(`[GraphCanvasV2 #${instanceId.current}] Component mounted`);
      return () => {
        console.log(`[GraphCanvasV2 #${instanceId.current}] Component unmounting`);
      };
    }, []);
    
    // Note: Data is already initialized from props in useGraphDataManagement hook
    // We don't need to update it again here as it causes infinite loops
    
    // Update Cosmograph ref in context
    useEffect(() => {
      if (cosmographRef.current) {
        setCosmographRef(cosmographRef);
      }
    }, [cosmographRef.current, setCosmographRef]);
    
    // Handle highlighted nodes
    useEffect(() => {
      if (highlightedNodes && highlightedNodes.length > 0) {
        highlightNodeVisuals(highlightedNodes, 2000);
      }
    }, [highlightedNodes, highlightNodeVisuals]);
    
    // Handle selected nodes
    useEffect(() => {
      if (selectedNodes && selectedNodeIds) {
        const currentSelection = Array.from(selectedNodeIds);
        const toSelect = selectedNodes.filter(id => !currentSelection.includes(id));
        const toDeselect = currentSelection.filter(id => !selectedNodes.includes(id));
        
        toSelect.forEach(id => selectSingleNode(id));
        toDeselect.forEach(id => deselectNode(id));
      }
    }, [selectedNodes, selectedNodeIds, selectSingleNode, deselectNode]);
    
    // Update statistics when nodes or links change
    // Note: Don't include updateStatistics in deps to avoid infinite loop
    useEffect(() => {
      updateStatistics(nodes, links, 'full');
    }, [nodes, links]);
    
    // Notify when context is ready
    useEffect(() => {
      if (onContextReady) {
        onContextReady(isReady && isCanvasReady);
      }
    }, [isReady, isCanvasReady, onContextReady]);
    
    // Mark dataPreparation and canvas stages complete when cosmograph data is ready
    useEffect(() => {
      if (cosmographData && cosmographData.nodes?.length > 0) {
        // Only mark complete if not already complete
        if (loadingCoordinator.getStageStatus('dataPreparation') !== 'complete') {
          console.log(`[GraphCanvasV2 #${instanceId.current}] Marking dataPreparation as complete`);
          loadingCoordinator.setStageComplete('dataPreparation', {
            nodesCount: cosmographData.nodes?.length || 0,
            linksCount: cosmographData.links?.length || 0
          });
        }
        
        // Only mark canvas complete if not already complete
        if (loadingCoordinator.getStageStatus('canvas') !== 'complete') {
          console.log(`[GraphCanvasV2 #${instanceId.current}] Marking canvas as complete`);
          loadingCoordinator.setStageComplete('canvas', {
            canvasReady: true,
            hasData: true
          });
        }
      }
    }, [cosmographData?.nodes?.length, cosmographData?.links?.length]); // Use stable dependencies
    
    // Fallback timeout to ensure stages complete even if detection fails - DISABLED FOR DEBUGGING
    // useEffect(() => {
    //   const fallbackTimeout = setTimeout(() => {
    //     // Check and complete dataPreparation if needed
    //     if (loadingCoordinator.getStageStatus('dataPreparation') !== 'complete') {
    //       console.warn(`[GraphCanvasV2 #${instanceId.current}] Data preparation timeout, marking as complete`);
    //       loadingCoordinator.setStageComplete('dataPreparation', {
    //         nodesCount: nodes?.length || 0,
    //         linksCount: links?.length || 0,
    //         fallback: true
    //       });
    //     }
        
    //     // Check and complete canvas if needed
    //     if (loadingCoordinator.getStageStatus('canvas') !== 'complete') {
    //       console.warn(`[GraphCanvasV2 #${instanceId.current}] Canvas detection timeout, marking as complete`);
    //       loadingCoordinator.setStageComplete('canvas', {
    //         canvasReady: true,
    //         fallback: true
    //       });
    //     }
    //   }, 1500); // 1.5 seconds fallback
      
    //   return () => clearTimeout(fallbackTimeout);
    // }, [loadingCoordinator, nodes, links]);
    
    // === 5. RENDER ===
    
    console.log('[GraphCanvasV2] Render state:', {
      loading,
      error,
      hasCosmographData: !!cosmographData,
      cosmographDataNodes: cosmographData?.nodes?.length || 0,
      cosmographDataLinks: cosmographData?.links?.length || 0,
      hookNodes: nodes?.length || 0,
      hookLinks: links?.length || 0
    });
    
    if (loading || !cosmographData) {
      console.log('[GraphCanvasV2] Showing loading state');
      return (
        <div className="flex items-center justify-center h-full">
          <div className="text-gray-500">Loading graph data...</div>
        </div>
      );
    }
    
    if (error) {
      console.log('[GraphCanvasV2] Showing error state:', error);
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
        
        <Cosmograph
          ref={cosmographRef}
          nodes={cosmographData.nodes}
          links={cosmographData.links}
          nodeSize={config.nodeSize}
          linkWidth={config.linkWidth}
          backgroundColor={config.backgroundColor}
          nodeColor={(node: any) => {
            if (isNodeHighlighted(node.id)) {
              return '#ff0000';
            }
            if (isNodeSelected(node.id)) {
              return '#0066cc';
            }
            return node.color || generateNodeTypeColor(node.node_type);
          }}
          linkColor={() => visualStyle.links?.stroke || '#999'}
          showLabels={config.showLabels}
          labelSize={config.labelSize}
          simulationEnabled={config.simulationEnabled}
          simulationGravity={config.simulationGravity}
          simulationCenter={config.simulationCenter}
          simulationRepulsion={config.simulationRepulsion}
          simulationLinkDistance={config.simulationLinkDistance}
          simulationLinkSpring={config.simulationLinkSpring}
          simulationFriction={config.simulationFriction}
          simulationDecay={config.simulationDecay}
          onReady={() => {
            console.log('[GraphCanvasV2] Cosmograph ready');
            setIsReady(true);
            setIsCanvasReady(true);
          }}
          onClick={(node: any) => {
            if (node) {
              handleInteractionNodeClick(node.id, { x: 0, y: 0 });
            }
          }}
          onHover={(node: any) => {
            handleInteractionNodeHover(node?.id || null);
          }}
        />
      </div>
    );
  }
);

GraphCanvasV2.displayName = 'GraphCanvasV2';

export default GraphCanvasV2;