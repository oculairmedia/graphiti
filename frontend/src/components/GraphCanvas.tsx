import React, { useEffect, useRef, forwardRef, useState, useCallback, use } from 'react';
import { Cosmograph, prepareCosmographData } from '@cosmograph/react';
import '../styles/cosmograph.css';
import { GraphNode } from '../api/types';
import type { GraphData } from '../types/graph';
import { useGraphConfig } from '../contexts/GraphConfigProvider';
import { generateNodeTypeColor } from '../utils/nodeTypeColors';
import { logger } from '../utils/logger';
import { hexToRgba, generateHSLColor } from '../utils/colorCache';
import { applyClusteringToGraphData, type ClusteringConfig } from '../utils/clustering';
import { DataKitCoordinator } from '../utils/DataKitCoordinator';
import { useGraphZoom } from '../hooks/useGraphZoom';
import { useGraphEvents } from '../hooks/useGraphEvents';
import { useSimulation } from '../hooks/useSimulation';
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts';
import { useColorUtils } from '../hooks/useColorUtils';
import { searchIndex } from '../utils/searchIndex';
import { GraphConfigContext } from '../contexts/useGraphConfig';
import { useWebSocketContext } from '../contexts/WebSocketProvider';
import { useRustWebSocket } from '../contexts/RustWebSocketProvider';
import { useDuckDB } from '../contexts/DuckDBProvider';
import { useLoadingCoordinator } from '../contexts/LoadingCoordinator';

const dataKitCoordinator = DataKitCoordinator.getInstance();

// Example of React 19's use API for conditional context consumption
// This demonstrates how 'use' can be called conditionally, unlike useContext
function ConditionalConfigConsumer({ shouldUseConfig }: { shouldUseConfig: boolean }) {
  if (!shouldUseConfig) {
    return null; // Early return before using context
  }
  
  // The 'use' API allows conditional consumption after early returns
  const config = use(GraphConfigContext);
  
  if (!config) {
    return <div>Loading config...</div>;
  }
  
  return <div>Config loaded: {config.config.layout}</div>;
}

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

interface GraphNodeWithPosition extends GraphNode {
  x?: number;
  y?: number;
}

interface GraphStats {
  total_nodes: number;
  total_edges: number;
  density?: number;
  [key: string]: unknown;
}

interface CosmographRef {
  setZoomLevel: (level: number, duration?: number) => void;
  getZoomLevel: () => number;
  fitView: (duration?: number, padding?: number) => void;
  fitViewByPointIndices: (indices: number[], duration?: number, padding?: number) => void;
  zoomToPoint: (index: number, duration?: number, scale?: number, canZoomOut?: boolean) => void;
  trackPointPositionsByIndices: (indices: number[]) => void;
  getTrackedPointPositionsMap: () => Map<number, [number, number]> | undefined;
  getTrackedPointPositionsArray: () => Float32Array | undefined;
  // Selection methods
  selectNode: (node: GraphNode, selectAdjacentNodes?: boolean) => void;
  selectNodes: (nodes: GraphNode[]) => void;
  getSelectedNodes: () => GraphNode[];
  unselectNodes: () => void;
  unselectAll: () => void;
  // Focus methods
  focusNode: (node?: GraphNode) => void;
  unfocusNode: () => void;
  // Adjacent nodes
  getAdjacentNodes: (id: string) => GraphNode[] | undefined;
  // Node position methods
  getNodePositions: () => Record<string, { x: number; y: number }>;
  getNodePositionsMap: () => Map<string, [number, number]>;
  restart: () => void;
  start: () => void;
  // Selection tools
  activateRectSelection: () => void;
  deactivateRectSelection: () => void;
  activatePolygonalSelection: () => void;
  deactivatePolygonalSelection: () => void;
  // Data manager for incremental updates (Cosmograph 2.0.0-beta.25)
  dataManager?: {
    addPoints: (points: any[]) => Promise<void>;
    addLinks: (links: any[]) => Promise<void>;
    removePointsByIds: (ids: string[]) => Promise<void>;
    removePointsByIndices: (indices: number[]) => Promise<void>;
    removeLinksByPointIdPairs: (pairs: [string, string][]) => Promise<void>;
    removeLinksByPointIndicesPairs: (pairs: [number, number][]) => Promise<void>;
  };
  selectPointsInRect: (selection: [[number, number], [number, number]] | null, addToSelection?: boolean) => void;
  selectPointsInPolygon: (polygonPoints: [number, number][], addToSelection?: boolean) => void;
  getConnectedPointIndices: (index: number) => number[] | undefined;
  // Search methods
  getPointIndicesByExactValues: (keyValues: Record<string, unknown>) => number[] | undefined;
  _canvasElement?: HTMLCanvasElement;
}

interface GraphCanvasProps {
  onNodeClick: (node: GraphNode) => void;
  onNodeSelect: (nodeId: string) => void;
  onSelectNodes?: (nodes: GraphNode[]) => void;
  onClearSelection?: () => void;
  onNodeHover?: (node: GraphNode | null) => void;
  onStatsUpdate?: (stats: { nodeCount: number; edgeCount: number; lastUpdated: number }) => void;
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
  // Live statistics
  getLiveStats: () => { nodeCount: number; edgeCount: number; lastUpdated: number };
  // Selection tools
  activateRectSelection: () => void;
  deactivateRectSelection: () => void;
  activatePolygonalSelection: () => void;
  deactivatePolygonalSelection: () => void;
  selectPointsInRect: (selection: [[number, number], [number, number]] | null, addToSelection?: boolean) => void;
  selectPointsInPolygon: (polygonPoints: [number, number][], addToSelection?: boolean) => void;
  getConnectedPointIndices: (index: number) => number[] | undefined;
  // Search methods
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
  // External incremental flag control
  setIncrementalUpdateFlag: (enabled: boolean) => void;
}

interface GraphCanvasComponentProps extends GraphCanvasProps {
  nodes: GraphNode[];
  links: GraphLink[];
}

// Use WeakMap to track initialization per canvas element
// This properly handles multiple instances and React dev mode
const cosmographInitializationMap = new WeakMap<HTMLElement, boolean>();

const GraphCanvasComponent = forwardRef<GraphCanvasHandle, GraphCanvasComponentProps>(
  ({ onNodeClick, onNodeSelect, onSelectNodes, onClearSelection, onNodeHover, onStatsUpdate, selectedNodes, highlightedNodes, className, stats, nodes, links }, ref) => {
    const cosmographRef = useRef<CosmographRef | null>(null);
    
    // Add a stable ref for the Cosmograph instance to prevent issues in dev mode
    const stableCosmographRef = useRef<CosmographRef | null>(null);
    useEffect(() => {
      stableCosmographRef.current = cosmographRef.current;
    });
    const [isReady, setIsReady] = useState(false);
    const [isCanvasReady, setIsCanvasReady] = useState(false);
    
    // Get loading coordinator - will always be available since we're inside ParallelInitProvider
    const loadingCoordinator = useLoadingCoordinator();
    
    const [cosmographData, setCosmographData] = useState<{ nodes: GraphNode[]; links: GraphLink[] } | null>(null);
    const [dataKitError, setDataKitError] = useState<string | null>(null);
    const [isDataPreparing, setIsDataPreparing] = useState(false);
    const { config, setCosmographRef } = useGraphConfig();
    
    // Get DuckDB connection
    const { service: duckdbService, isInitialized: isDuckDBInitialized, getDuckDBConnection } = useDuckDB();
    
    // Glowing nodes state for real-time visualization
    const [glowingNodes, setGlowingNodes] = useState<Map<string, number>>(new Map());
    const [glowingNodeIndices, setGlowingNodeIndices] = useState<number[]>([]);
    
    // CSS variables for label styling (avoids dynamic style tag injection)
    const containerStyle: React.CSSProperties = {
      ['--cosmograph-label-size' as any]: `${config.labelSize}px`,
      ['--cosmograph-border-width' as any]: '0px',
      ['--cosmograph-border-color' as any]: 'rgba(0,0,0,0.5)',
    };
    
    // Live statistics tracking for real-time updates
    const [liveStats, setLiveStats] = useState<{
      nodeCount: number;
      edgeCount: number;
      lastUpdated: number;
    }>({
      nodeCount: 0,
      edgeCount: 0,
      lastUpdated: Date.now()
    });
    const { 
      subscribe: subscribeToWebSocket,
      subscribeToDeltaUpdate,
      subscribeToGraphUpdate 
    } = useWebSocketContext();
    
    // Call onStatsUpdate when liveStats changes
    useEffect(() => {
      if (onStatsUpdate) {
        onStatsUpdate(liveStats);
      }
    }, [liveStats, onStatsUpdate]);
    
    // Track current data for incremental updates
    const [currentNodes, setCurrentNodes] = useState<GraphNode[]>([]);
    const [currentLinks, setCurrentLinks] = useState<GraphLink[]>([]);
    
    // Use ref to access current data without causing re-subscriptions
    const cosmographDataRef = useRef<typeof cosmographData>(null);
    
    // Batch delta updates for performance
    const deltaQueueRef = useRef<any[]>([]);
    const deltaTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    
    // DuckDB data state - keep Arrow tables in native format
    const [duckDBData, setDuckDBData] = useState<{ points: any; links: any } | null>(null);
    
    // Simulation control state
    const [keepRunning, setKeepRunning] = useState(false);
    const simulationTimerRef = useRef<NodeJS.Timeout | null>(null);
    
    // Track simulation state for debugging incremental updates
    const [isSimulationActive, setIsSimulationActive] = useState(false);
    const lastResumeTimeRef = useRef<number>(0);
    
    // Flag to prevent Data Kit reprocessing during incremental updates
    const isIncrementalUpdateRef = useRef(false);
    
    // Add component ID for debugging multiple instances
    const componentId = useRef(Math.random().toString(36).substr(2, 9));
    
    // Determine whether to use DuckDB table names or prepared data
    const useDuckDBTables = false; // Disabled due to production DuckDB table conflicts
    
    // Fetch DuckDB tables when available - moved here to maintain hook order
    React.useEffect(() => {
      if (useDuckDBTables && duckdbService) {
        const fetchTables = async () => {
          try {
            const [nodesTable, edgesTable] = await Promise.all([
              duckdbService.getNodesTable(),
              duckdbService.getEdgesTable()
            ]);
            
            if (nodesTable && edgesTable) {
              // Keep Arrow tables in native format for Cosmograph
              // Cosmograph v2.0 can handle Arrow tables directly
              setDuckDBData({
                points: nodesTable,
                links: edgesTable
              });
            }
          } catch (error) {
            logger.error('Failed to fetch DuckDB tables:', error);
          }
        };
        
        fetchTables();
      }
    }, [useDuckDBTables, duckdbService]);
    
    // Update current data tracking and search index when props change
    useEffect(() => {
      setCurrentNodes(nodes);
      setCurrentLinks(links);
      
      // Initialize/update live stats with current data
      setLiveStats({
        nodeCount: nodes.length,
        edgeCount: links.length,
        lastUpdated: Date.now()
      });
      
      // Update search index for fast searching
      if (nodes.length > 0) {
        searchIndex.buildIndex(nodes);
        logger.log('Search index updated with', nodes.length, 'nodes');
      }
    }, [nodes, links]);
    
    // Double-click detection using refs to avoid re-renders
    const lastClickTimeRef = useRef<number>(0);
    const lastClickedNodeRef = useRef<GraphNode | null>(null);
    const doubleClickTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    
    // Selection handlers for keyboard shortcuts
    const handleSelectAll = useCallback(() => {
      if (!cosmographRef.current || !currentNodes.length) return;
      
      // Use onSelectNodes if available (for multi-select)
      if (onSelectNodes) {
        onSelectNodes(currentNodes);
      } else {
        // Fallback: Select all visible nodes in Cosmograph
        if (cosmographRef.current.selectNodes) {
          cosmographRef.current.selectNodes(currentNodes);
        }
        
        // For React state, we need to call onNodeSelect for each node
        // since it expects a single node ID
        currentNodes.forEach(node => {
          if (!selectedNodes.includes(node.id)) {
            onNodeSelect?.(node.id);
          }
        });
      }
    }, [currentNodes, onNodeSelect, onSelectNodes, selectedNodes]);
    
    const handleDeselectAll = useCallback(() => {
      onClearSelection?.();
    }, [onClearSelection]);
    
    // Initialize keyboard shortcuts
    useKeyboardShortcuts({
      onSelectAll: handleSelectAll,
      onDeselectAll: handleDeselectAll,
      cosmographRef
    });
    
    // Subscribe to WebSocket node access events
    const glowTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    // CosmographPopup removed - not available in @cosmograph/react v2
    // const popupRef = useRef<CosmographPopup | null>(null);
    const popupTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    
    useEffect(() => {
      const unsubscribe = subscribeToWebSocket((event) => {
        if (event.type === 'node_access' && event.node_ids) {
          console.log('[GraphCanvas] Node access event received:', {
            nodeIds: event.node_ids,
            nodeCount: event.node_ids.length,
            firstNodeId: event.node_ids[0]
          });
          
          // Cancel any existing glow timeout
          if (glowTimeoutRef.current) {
            clearTimeout(glowTimeoutRef.current);
          }
          
          const now = Date.now();
          
          // Update glowing nodes map
          setGlowingNodes(() => {
            // Create a fresh map with only the new nodes
            const updated = new Map<string, number>();
            event.node_ids.forEach(nodeId => {
              updated.set(nodeId, now);
            });
            console.log('[GraphCanvas] Glowing nodes updated:', {
              totalGlowing: updated.size,
              glowingIds: Array.from(updated.keys()).slice(0, 3)
            });
            return updated;
          });
          
          // Convert node IDs to indices for Cosmograph
          const indices: number[] = [];
          
          if (!event.node_ids || event.node_ids.length === 0) {
            console.log('[GraphCanvas] No node IDs to glow');
            setGlowingNodeIndices([]);
            // Clear selection in Cosmograph
            if (cosmographRef.current) {
              cosmographRef.current.unselectAllPoints();
            }
            return;
          }
          
          // Try DuckDB data first
          if (useDuckDBTables && duckDBData?.points) {
            console.log('[GraphCanvas] Using DuckDB data for indices, numRows:', duckDBData.points.numRows);
            const numRows = duckDBData.points.numRows || 0;
            for (let i = 0; i < numRows; i++) {
              const row = duckDBData.points.get(i);
              if (row && event.node_ids.includes(row.id)) {
                indices.push(i);
                console.log('[GraphCanvas] Found glowing node at index:', i, 'id:', row.id);
              }
            }
          } 
          // Try Cosmograph data
          else if (cosmographData?.points && Array.isArray(cosmographData.points)) {
            console.log('[GraphCanvas] Using cosmographData for indices, length:', cosmographData.points.length);
            cosmographData.points.forEach((point: any, index: number) => {
              if (event.node_ids.includes(point.id)) {
                indices.push(index);
                console.log('[GraphCanvas] Found glowing node at index:', index, 'id:', point.id);
              }
            });
          }
          // Fallback to transformedData which should match what Cosmograph is rendering
          else if (transformedData.nodes && transformedData.nodes.length > 0) {
            console.log('[GraphCanvas] Using transformedData.nodes for indices, length:', transformedData.nodes.length);
            transformedData.nodes.forEach((node: any, index: number) => {
              if (event.node_ids.includes(node.id)) {
                indices.push(index);
                console.log('[GraphCanvas] Found glowing node at index:', index, 'id:', node.id);
              }
            });
          } else {
            console.log('[GraphCanvas] No data source available for finding indices');
          }
          
          console.log('[GraphCanvas] Final glowing node indices:', indices, 'for IDs:', event.node_ids);
          setGlowingNodeIndices(indices);
          
          // Use Cosmograph's selectPoints method to highlight the nodes
          if (cosmographRef.current && indices.length > 0) {
            console.log('[GraphCanvas] Calling cosmographRef.selectPoints with', indices.length, 'indices');
            cosmographRef.current.selectPoints(indices, false);
            
            // If only one node, also set it as focused
            if (indices.length === 1) {
              cosmographRef.current.setFocusedPoint(indices[0]);
            }
          }
          
          // Log that we're ready to apply glow
          console.log('[GraphCanvas] Ready to apply glow effect, functions should be called now');
          
          // We'll handle the popup in a separate effect that has access to transformedData
          
          // No need to force update - the animation loop will handle it
          
          // Remove glow after 2 seconds
          glowTimeoutRef.current = setTimeout(() => {
            setGlowingNodes(() => new Map());
            setGlowingNodeIndices([]);
            // Clear selection in Cosmograph
            if (cosmographRef.current) {
              cosmographRef.current.unselectAllPoints();
            }
            console.log('[GraphCanvas] Glow effect cleared');
          }, 2000);
        }
      });
      
      return () => {
        unsubscribe();
        if (glowTimeoutRef.current) {
          clearTimeout(glowTimeoutRef.current);
        }
        if (popupTimeoutRef.current) {
          clearTimeout(popupTimeoutRef.current);
        }
        // CosmographPopup cleanup removed - not available in v2
      };
    }, [subscribeToWebSocket]);
    
    // Process batched delta updates using Cosmograph API
    const processDeltaBatch = useCallback(async () => {
      console.log('[GraphCanvas] processDeltaBatch called, queue length:', deltaQueueRef.current.length);
      
      if (deltaQueueRef.current.length === 0) {
        console.log('[GraphCanvas] Delta queue is empty, skipping');
        return;
      }
      
      // Check if Cosmograph is ready
      if (!cosmographRef.current) {
        console.warn('[GraphCanvas] Cosmograph ref not ready');
        return;
      }
      
      // Log available properties for debugging
      console.log('[GraphCanvas] Cosmograph ref properties:', Object.keys(cosmographRef.current));
      console.log('[GraphCanvas] Checking for dataManager:', !!cosmographRef.current.dataManager);
      
      if (!cosmographRef.current.dataManager) {
        console.warn('[GraphCanvas] dataManager not available, attempting fallback to setData');
        
        // Fallback: Use setData for full replacement if dataManager is not available
        // This is less efficient but ensures updates work
        const deltas = [...deltaQueueRef.current];
        deltaQueueRef.current = [];
        
        try {
          // Get current data and apply deltas
          const currentNodesMap = new Map(currentNodes.map(n => [n.id, n]));
          const currentLinksMap = new Map(currentLinks.map(l => [`${l.source}-${l.target}`, l]));
          
          for (const delta of deltas) {
            const { operation, nodes: deltaNodes, edges: deltaEdges } = delta;
            
            if (operation === 'add') {
              // Add new nodes
              deltaNodes?.forEach(node => {
                currentNodesMap.set(node.id, {
                  ...node,
                  index: currentNodesMap.size
                });
              });
              
              // Add new edges
              deltaEdges?.forEach(edge => {
                const key = `${edge.source || edge.from}-${edge.target || edge.to}`;
                currentLinksMap.set(key, edge);
              });
            }
            // Handle other operations as needed
          }
          
          // Convert back to arrays and update
          const updatedNodes = Array.from(currentNodesMap.values());
          const updatedLinks = Array.from(currentLinksMap.values());
          
          console.log('[GraphCanvas] Fallback update - nodes:', updatedNodes.length, 'links:', updatedLinks.length);
          
          // Use setData to update the graph
          if (cosmographRef.current.setData) {
            cosmographRef.current.setData(updatedNodes, updatedLinks);
            setCurrentNodes(updatedNodes);
            setCurrentLinks(updatedLinks);
          }
        } catch (error) {
          console.error('[GraphCanvas] Error in fallback update:', error);
        }
        
        return;
      }
      
      console.log('[GraphCanvas] Processing delta batch with Cosmograph dataManager');
      
      // Process all queued deltas at once
      const deltas = [...deltaQueueRef.current];
      deltaQueueRef.current = [];
      
      try {
        // Group operations by type for efficiency
        const pointsToAdd: any[] = [];
        const linksToAdd: any[] = [];
        const pointIdsToDelete: string[] = [];
        const linkPairsToDelete: [string, string][] = [];
        const pointsToUpdate: Map<string, any> = new Map();
        
        // Process all deltas to group operations
        for (const delta of deltas) {
          const { operation, nodes: deltaNodes, edges: deltaEdges } = delta;
          
          if (operation === 'add') {
            if (deltaNodes && deltaNodes.length > 0) {
              deltaNodes.forEach(node => {
                // Use complete transformation matching setData for Cosmograph compatibility
                pointsToAdd.push({
                  id: String(node.id),
                  label: String(node.label || node.id),
                  node_type: String(node.node_type || 'Unknown'),
                  centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
                  cluster: String(node.node_type || 'Unknown'),
                  clusterStrength: 0.7,
                  degree_centrality: Number(node.properties?.degree_centrality || 0),
                  pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
                  betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
                  eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0),
                  created_at: node.properties?.created_at || node.created_at || node.properties?.created || null,
                  created_at_timestamp: (node.properties?.created_at || node.created_at || node.properties?.created) ? 
                    new Date(node.properties?.created_at || node.created_at || node.properties?.created).getTime() : null
                });
              });
            }
            if (deltaEdges && deltaEdges.length > 0) {
              // Get current nodes to build index map
              const currentNodes = cosmographDataRef.current?.nodes || [];
              const nodeIndexMap = new Map<string, number>();
              
              // Map existing nodes to their indices
              currentNodes.forEach((node, idx) => {
                nodeIndexMap.set(String(node.id), idx);
              });
              
              // Map new nodes being added to their future indices
              pointsToAdd.forEach((node, idx) => {
                nodeIndexMap.set(String(node.id), currentNodes.length + idx);
              });
              
              deltaEdges.forEach(edge => {
                const source = String(edge.source || edge.from || edge.source_node_uuid);
                const target = String(edge.target || edge.to || edge.target_node_uuid);
                const sourceIndex = nodeIndexMap.get(source);
                const targetIndex = nodeIndexMap.get(target);
                
                if (sourceIndex !== undefined && targetIndex !== undefined) {
                  linksToAdd.push({
                    source: source,
                    target: target,
                    sourceIndex: sourceIndex,
                    targetIndex: targetIndex,
                    weight: edge.weight || 1,
                    edge_type: edge.edge_type || edge.name || 'RELATES_TO'
                  });
                } else {
                  console.warn('[GraphCanvas] Edge references unknown nodes:', source, target, 'indices:', sourceIndex, targetIndex);
                }
              });
            }
          } else if (operation === 'update') {
            if (deltaNodes && deltaNodes.length > 0) {
              // For updates, we need to remove and re-add nodes with complete transformation
              deltaNodes.forEach(node => {
                pointsToUpdate.set(node.id, {
                  id: String(node.id),
                  label: String(node.label || node.id),
                  node_type: String(node.node_type || 'Unknown'),
                  centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
                  cluster: String(node.node_type || 'Unknown'),
                  clusterStrength: 0.7,
                  degree_centrality: Number(node.properties?.degree_centrality || 0),
                  pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
                  betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
                  eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0),
                  created_at: node.properties?.created_at || node.created_at || node.properties?.created || null,
                  created_at_timestamp: (node.properties?.created_at || node.created_at || node.properties?.created) ? 
                    new Date(node.properties?.created_at || node.created_at || node.properties?.created).getTime() : null
                });
              });
            }
            if (deltaEdges && deltaEdges.length > 0) {
              // For edge updates, remove and re-add
              deltaEdges.forEach(edge => {
                const source = edge.source || edge.from;
                const target = edge.target || edge.to;
                linkPairsToDelete.push([source, target]);
                linksToAdd.push({
                  source,
                  target,
                  weight: edge.weight || 1,
                  ...edge
                });
              });
            }
          } else if (operation === 'delete') {
            if (deltaNodes && deltaNodes.length > 0) {
              deltaNodes.forEach(node => {
                pointIdsToDelete.push(node.id);
              });
            }
            if (deltaEdges && deltaEdges.length > 0) {
              deltaEdges.forEach(edge => {
                linkPairsToDelete.push([
                  edge.source || edge.from,
                  edge.target || edge.to
                ]);
              });
            }
          }
        }
        
        // Apply all operations to Cosmograph
        const promises: Promise<void>[] = [];
        
        // Handle updates (remove then add)
        if (pointsToUpdate.size > 0) {
          const updateIds = Array.from(pointsToUpdate.keys());
          promises.push(
            cosmographRef.current.dataManager!.removePointsByIds(updateIds).then(() => {
              return cosmographRef.current!.dataManager!.addPoints(Array.from(pointsToUpdate.values()));
            })
          );
        }
        
        // Handle deletions
        if (pointIdsToDelete.length > 0) {
          promises.push(cosmographRef.current.dataManager!.removePointsByIds(pointIdsToDelete));
        }
        
        if (linkPairsToDelete.length > 0) {
          promises.push(cosmographRef.current.dataManager!.removeLinksByPointIdPairs(linkPairsToDelete));
        }
        
        // Handle additions
        if (pointsToAdd.length > 0) {
          promises.push(cosmographRef.current.dataManager!.addPoints(pointsToAdd));
        }
        
        if (linksToAdd.length > 0) {
          promises.push(cosmographRef.current.dataManager!.addLinks(linksToAdd));
        }
        
        // Wait for all operations to complete
        if (promises.length > 0) {
          console.log('[GraphCanvas] Applying updates to Cosmograph...');
          try {
            await Promise.all(promises);
            console.log('[GraphCanvas] Successfully applied delta updates:', {
              pointsAdded: pointsToAdd.length,
              linksAdded: linksToAdd.length,
              pointsDeleted: pointIdsToDelete.length,
              pointsUpdated: pointsToUpdate.size,
              linksDeleted: linkPairsToDelete.length
            });
            
            // Log the actual points being added for debugging
            if (pointsToAdd.length > 0) {
              console.log('[GraphCanvas] Points being added:', pointsToAdd);
            }
            
            // Optional: restart simulation with low energy for smooth transition
            if (keepRunning && cosmographRef.current) {
              console.log('[GraphCanvas] Restarting simulation...');
              cosmographRef.current.restart();
            }
            
            // Update live stats after successful delta processing
            try {
              setLiveStats(prev => {
                // Calculate new counts based on operations performed
                const newNodeCount = prev.nodeCount + pointsToAdd.length - pointIdsToDelete.length;
                const newEdgeCount = prev.edgeCount + linksToAdd.length - linkPairsToDelete.length;
                
                console.log('[GraphCanvas] Live stats updated:', { 
                  nodeCount: newNodeCount, 
                  edgeCount: newEdgeCount,
                  added: { nodes: pointsToAdd.length, edges: linksToAdd.length },
                  deleted: { nodes: pointIdsToDelete.length, edges: linkPairsToDelete.length }
                });
                
                return {
                  nodeCount: newNodeCount,
                  edgeCount: newEdgeCount,
                  lastUpdated: Date.now()
                };
              });
            } catch (statsError) {
              console.warn('[GraphCanvas] Failed to update live stats:', statsError);
            }
          } catch (error) {
            console.error('[GraphCanvas] Error applying updates to Cosmograph:', error);
          }
        } else {
          console.log('[GraphCanvas] No operations to apply');
        }
        
      } catch (error) {
        console.error('[GraphCanvas] Error applying delta updates:', error);
      }
    }, [keepRunning]);
      
    
    // Store processDeltaBatch in a ref to avoid dependency issues
    const processDeltaBatchRef = useRef<(() => Promise<void>) | null>(null);
    processDeltaBatchRef.current = processDeltaBatch;
    
    // Use Rust WebSocket for delta updates
    const { subscribe: subscribeToRust } = useRustWebSocket();
    
    useEffect(() => {
      console.log('[GraphCanvas] Setting up Rust WebSocket subscription');
      const unsubscribe = subscribeToRust((update) => {
        console.log('[GraphCanvas] Received delta update from Rust server:', update);
        console.log('[GraphCanvas] Current queue length before push:', deltaQueueRef.current.length);
        
        // Queue the delta update
        deltaQueueRef.current.push(update.data);
        console.log('[GraphCanvas] Queue length after push:', deltaQueueRef.current.length);
        
        // Clear existing timeout
        if (deltaTimeoutRef.current) {
          clearTimeout(deltaTimeoutRef.current);
          console.log('[GraphCanvas] Cleared existing timeout');
        }
        
        // Process batch after 50ms of no new updates
        console.log('[GraphCanvas] Setting timeout to process batch in 50ms');
        deltaTimeoutRef.current = setTimeout(() => {
          console.log('[GraphCanvas] Timeout triggered, calling processDeltaBatch');
          if (processDeltaBatchRef.current) {
            processDeltaBatchRef.current();
          }
          deltaTimeoutRef.current = null;
        }, 50);
      });
      
      console.log('[GraphCanvas] Rust WebSocket subscription setup complete');
      return () => {
        console.log('[GraphCanvas] Cleaning up Rust WebSocket subscription');
        unsubscribe();
      };
    }, [subscribeToRust]);
    
    // Keep existing Python WebSocket subscription for other events
    useEffect(() => {
      const unsubscribeDelta = subscribeToDeltaUpdate((event) => {
        // This is for Python server delta updates if any
        console.log('[GraphCanvas] Python server delta update:', event);
      });
      
      const unsubscribeGraph = subscribeToGraphUpdate((event) => {
        // Handle full graph updates if needed
        console.log('[GraphCanvas] Graph update event:', event);
      });
      
      return () => {
        unsubscribeDelta();
        unsubscribeGraph();
        if (deltaTimeoutRef.current) {
          clearTimeout(deltaTimeoutRef.current);
        }
      };
    }, [subscribeToDeltaUpdate, subscribeToGraphUpdate]);
    
    // Keep ref in sync with state
    useEffect(() => {
      cosmographDataRef.current = cosmographData;
    }, [cosmographData]);
    
    // Animation loop for smooth color transitions
    useEffect(() => {
      if (glowingNodes.size === 0) return;
      
      let animationFrameId: number;
      let lastUpdate = Date.now();
      
      const animate = () => {
        const now = Date.now();
        
        // Update at 60fps (every ~16ms)
        if (now - lastUpdate >= 16 && cosmographRef.current && glowingNodes.size > 0) {
          lastUpdate = now;
          
          // Check if any nodes are still animating
          let hasActiveAnimations = false;
          glowingNodes.forEach((startTime) => {
            if (now - startTime < 2000) { // 2 second fade duration
              hasActiveAnimations = true;
            }
          });
          
          if (hasActiveAnimations && cosmographRef.current.start) {
            // Call start() to trigger a single frame update
            cosmographRef.current.start();
          }
        }
        
        // Continue animation if there are still glowing nodes
        if (glowingNodes.size > 0) {
          animationFrameId = requestAnimationFrame(animate);
        }
      };
      
      // Start animation loop
      animationFrameId = requestAnimationFrame(animate);
      
      return () => {
        if (animationFrameId) {
          cancelAnimationFrame(animationFrameId);
        }
      };
    }, [glowingNodes]);
    
    // Search functionality using indexed search
    const performSearch = useCallback(() => {
      if (!cosmographRef.current || !config.searchTerm || config.searchTerm.trim() === '') {
        // Clear search highlights if search is empty
        return;
      }
      
      // Use search index for fast search
      const matchingNodes = searchIndex.search(config.searchTerm, {
        limit: 500,
        fuzzy: false
      });
      
      if (matchingNodes.length > 0) {
        // Select matching nodes
        const matchingIds = matchingNodes.map(node => node.id);
        if (onSelectNodes) {
          onSelectNodes(matchingNodes);
        } else {
          // Fallback to individual selection
          matchingIds.forEach(id => onNodeSelect?.(id));
        }
        
        // Focus on the first few matches
        if (cosmographRef.current.fitViewByIndices && matchingNodes.length <= 10) {
          const nodeIndices = matchingNodes
            .slice(0, 10)
            .map(node => currentNodes.findIndex(n => n.id === node.id))
            .filter(idx => idx >= 0);
          
          if (nodeIndices.length > 0) {
            cosmographRef.current.fitViewByIndices(nodeIndices, 1000, 0.2);
          }
        }
      }
      
      logger.log(`Search found ${matchingNodes.length} nodes for query: ${config.searchTerm}`);
    }, [config.searchTerm, currentNodes, onNodeSelect, onSelectNodes]);
    
    // Trigger search when searchTerm changes
    useEffect(() => {
      if (config.queryType === 'search' && config.searchTerm) {
        performSearch();
      }
    }, [config.searchTerm, config.queryType, performSearch]);
    
    // Memoize color strategy and color by field - moved here before dataKitConfig
    const { pointColorStrategy, pointColorBy } = React.useMemo(() => {
      switch (config.colorScheme) {
        case 'by-type': 
          return { pointColorStrategy: 'map', pointColorBy: 'node_type' };
        case 'by-centrality': 
          return { pointColorStrategy: 'interpolatePalette', pointColorBy: 'degree_centrality' };
        case 'by-pagerank': 
          return { pointColorStrategy: 'interpolatePalette', pointColorBy: 'pagerank_centrality' };
        case 'by-degree': 
          return { pointColorStrategy: 'degree', pointColorBy: undefined }; // 'degree' strategy doesn't need pointColorBy
        case 'by-community': 
          return { pointColorStrategy: 'palette', pointColorBy: 'cluster' };
        default: 
          return { pointColorStrategy: 'map', pointColorBy: 'node_type' };
      }
    }, [config.colorScheme]);
    
    // Memoize size by field based on mapping - moved here before dataKitConfig
    const pointSizeBy = React.useMemo(() => {
      switch (config.sizeMapping) {
        case 'uniform': return undefined; // Will use uniform size
        case 'degree': return 'degree_centrality';
        case 'betweenness': return 'betweenness_centrality';
        case 'pagerank': return 'pagerank_centrality';
        case 'importance': return 'eigenvector_centrality';
        case 'connections': return 'degree_centrality'; // Same as degree
        case 'custom': return 'centrality'; // Default centrality field
        default: return 'centrality';
      }
    }, [config.sizeMapping]);

    // Data Kit configuration for Cosmograph v2.0 - stable config to prevent reprocessing
    const dataKitConfig = React.useMemo(() => ({
      points: {
        pointIdBy: 'id',              // Required: unique identifier field
        pointIndexBy: 'index',        // Required: ordinal index field
        pointLabelBy: 'label',        // Node display labels
        pointColorBy: pointColorBy || 'node_type',    // Dynamic color by field based on scheme
        pointSizeBy: pointSizeBy || 'centrality',    // Dynamic size by field based on mapping
        pointIncludeColumns: ['degree_centrality', 'pagerank_centrality', 'betweenness_centrality', 'eigenvector_centrality', 'created_at', 'created_at_timestamp'] // Include additional columns including temporal data
      },
      links: {
        linkSourceBy: 'source',         // Source node ID field
        linkSourceIndexBy: 'sourceIndex', // Required: source node index
        linkTargetBy: 'target',         // Target node ID field (singular for single target)
        linkTargetIndexBy: 'targetIndex', // Required: target node index
        // linkColorBy removed - using linkColorByFn instead
        linkWidthBy: config.linkWidthBy || 'weight',         // Dynamic width column
        linkIncludeColumns: ['created_at', 'updated_at', 'weight', 'strength', 'confidence', 'edge_type'] // Include various link properties
      }
    }), [pointColorBy, pointSizeBy, config.linkWidthBy]);

    // Track previous data to prevent unnecessary reprocessing
    const prevDataRef = useRef<{ nodeCount: number; linkCount: number }>({ nodeCount: 0, linkCount: 0 });
    
    // Memoize expensive node transformations
    const memoizedNodes = React.useMemo(() => {
      if (!nodes || nodes.length === 0) return [];
      
      return nodes.map((node, arrayIndex) => ({
        id: String(node.id),
        // Use the preserved idx from DuckDB if available, otherwise use array index
        index: node.idx !== undefined ? node.idx : (node.properties?.idx !== undefined ? node.properties.idx : arrayIndex),
        label: String(node.label || node.id),
        node_type: String(node.node_type || 'Unknown'),
        centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
        cluster: String(node.node_type || 'Unknown'),
        clusterStrength: 0.7,
        degree_centrality: Number(node.properties?.degree_centrality || 0),
        pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
        betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
        eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0),
        created_at: node.properties?.created_at || node.created_at || null,
        created_at_timestamp: node.properties?.created_at ? new Date(node.properties?.created_at).getTime() : null
      }));
    }, [nodes]);
    
    // Memoize link transformations
    const memoizedLinks = React.useMemo(() => {
      if (!links || links.length === 0) return [];
      
      return links.map(link => ({
        source: String(link.source),
        target: String(link.target),
        sourceIndex: link.sourceIndex,  // Preserve sourceIndex from useGraphDataQuery
        targetIndex: link.targetIndex,  // Preserve targetIndex from useGraphDataQuery
        edge_type: String(link.edge_type || 'default'),
        weight: Number(link.weight || 1),
        created_at: link.created_at,
        updated_at: link.updated_at
      }));
    }, [links]);
    
    // Data Kit preparation effect
    useEffect(() => {
      // Skip if using DuckDB tables directly
      if (isDuckDBInitialized && duckdbService) {
        logger.log('GraphCanvas: Using DuckDB tables directly, skipping data preparation');
        // Mark dataPreparation as complete since we're using DuckDB directly
        loadingCoordinator.setStageComplete('dataPreparation', {
          skipped: true,
          reason: 'Using DuckDB directly',
          nodesCount: nodes?.length || 0,
          linksCount: links?.length || 0
        });
        return;
      }
      
      // Skip reprocessing if we're in the middle of an incremental update
      if (isIncrementalUpdateRef.current) {
        return;
      }
      
      if (!nodes || !links || nodes.length === 0) {
        setCosmographData(null);
        setDataKitError(null);
        prevDataRef.current = { nodeCount: 0, linkCount: 0 };
        return;
      }
      
      // Skip if data hasn't actually changed (same counts)
      if (prevDataRef.current.nodeCount === nodes.length && 
          prevDataRef.current.linkCount === links.length) {
        return;
      }
      
      prevDataRef.current = { nodeCount: nodes.length, linkCount: links.length };

      let cancelled = false;
      
      // Fallback timeout to ensure dataPreparation completes
      const dataPreparationTimeout = setTimeout(() => {
        if (loadingCoordinator.getStageStatus('dataPreparation') !== 'complete') {
          console.warn('GraphCanvas: Data preparation timeout, marking as complete');
          loadingCoordinator.setStageComplete('dataPreparation', {
            nodesCount: memoizedNodes.length,
            linksCount: memoizedLinks.length,
            fallback: true
          });
        }
      }, 2000); // 2 seconds should be enough for data preparation
      
      const prepareData = async () => {
        // Execute data preparation directly without DataKitCoordinator wrapper
        let transformedNodes: any[] = [];
        let transformedLinks: any[] = [];
        
        try {
          setIsDataPreparing(true);
          setDataKitError(null);
          
          // Report data preparation started
          loadingCoordinator.updateStage('dataPreparation', { 
            status: 'loading', 
            progress: 10 
          });
            
          // Use memoized data instead of re-transforming
          transformedNodes = memoizedNodes.filter(node => node.id && node.id !== 'undefined');

          // Apply clustering if enabled
          let clusterAssignments: (string | number)[] = [];
          let clusterStrengths: number[] = [];
          
          if (config.clusteringEnabled && config.clusteringMethod !== 'none') {
            const clusteringConfig: ClusteringConfig = {
              method: config.clusteringMethod,
              centralityMetric: config.centralityMetric,
              clusterStrength: config.clusterStrength
            };
            
            const { nodes: clusteredNodes, clusterMapping, clusterPositions } = 
              applyClusteringToGraphData(transformedNodes, clusteringConfig);
            
            // If using DuckDB, we need to update the table; otherwise update the nodes
            if (useDuckDBTables && duckdbService) {
              // Extract cluster data for DuckDB update
              clusterAssignments = clusteredNodes.map(node => node.cluster || 'none');
              clusterStrengths = clusteredNodes.map(node => node.clusterStrength || 0);
              
              // We'll update DuckDB after data preparation is complete
            } else {
              // For non-DuckDB mode, use the clustered nodes directly
              transformedNodes = clusteredNodes;
            }
            
            // Update dynamic config with cluster mapping
            config.updateConfig({ 
              clusterMapping,
              clusterPositions 
            });
            
            logger.log('GraphCanvas: Applied clustering', {
              method: config.clusteringMethod,
              numClusters: clusterMapping.size,
              numNodes: transformedNodes.length,
              mode: useDuckDBTables ? 'DuckDB' : 'JavaScript'
            });
          }

          // Create a map for quick node index lookup
          const nodeIndexMap = new Map<string, number>();
          transformedNodes.forEach((node, index) => {
            nodeIndexMap.set(node.id, index);
          });

          logger.log('GraphCanvas: Processing links:', memoizedLinks.length, 'nodes in map:', nodeIndexMap.size);
          
          // Report progress
          loadingCoordinator.updateStage('dataPreparation', { 
            status: 'loading', 
            progress: 50 
          });
          
          // Use memoized links
          transformedLinks = memoizedLinks.map(link => {
            const sourceIndex = nodeIndexMap.get(String(link.source));
            const targetIndex = nodeIndexMap.get(String(link.target));
            
            const linkData = {
              source: String(link.source), // Ensure string type
              sourceIndex: sourceIndex !== undefined ? sourceIndex : -1, // Required for v2.0
              target: String(link.target), // Ensure string type
              targetIndex: targetIndex !== undefined ? targetIndex : -1, // Required for v2.0
              edge_type: String(link.edge_type || 'default'), // Ensure string type
              weight: Number(link.weight || 1), // Ensure number type
              // Include temporal data if available
              created_at: link.created_at,
              updated_at: link.updated_at
            };
            
            // Validate that source and target exist and have valid indices
            if (!linkData.source || !linkData.target || linkData.source === 'undefined' || linkData.target === 'undefined' || 
                linkData.sourceIndex === -1 || linkData.targetIndex === -1) {
              logger.warn('Invalid link found:', link, 'indices:', linkData.sourceIndex, linkData.targetIndex);
            }
            
            return linkData;
          }).filter(link => link.source && link.target && link.source !== 'undefined' && link.target !== 'undefined' && 
                           link.sourceIndex !== -1 && link.targetIndex !== -1); // Remove invalid links
          
          logger.log('GraphCanvas: Transformed links:', transformedLinks.length, 'valid links');

          
          // Log node type distribution for color mapping debugging
          const nodeTypeDistribution = transformedNodes.reduce((acc, node) => {
            acc[node.node_type] = (acc[node.node_type] || 0) + 1;
            return acc;
          }, {} as Record<string, number>);
          
          // Validate we have valid data before proceeding
          if (transformedNodes.length === 0) {
            throw new Error('No valid nodes found after transformation');
          }
          
          // BYPASS Data Kit - it's causing issues with links configuration
          // Use direct data instead
          logger.log('GraphCanvas: Bypassing Data Kit, using direct data');
          
          if (!cancelled) {
            // If using DuckDB and clustering is enabled, update the DuckDB table
            if (useDuckDBTables && duckdbService && clusterAssignments.length > 0) {
              try {
                await duckdbService.updateClusterData(clusterAssignments, clusterStrengths);
                logger.log('GraphCanvas: Updated DuckDB table with cluster data');
              } catch (error) {
                logger.error('GraphCanvas: Failed to update DuckDB cluster data:', error);
              }
            }
            
            // Ensure all nodes have proper index field
            const indexedNodes = transformedNodes.map((node, idx) => ({
              ...node,
              index: node.index !== undefined ? node.index : idx
            }));
            
            // Ensure links have proper source and target indices
            const indexedLinks = transformedLinks.map(link => ({
              ...link,
              sourceIndex: link.sourceIndex !== undefined ? link.sourceIndex : -1,
              targetIndex: link.targetIndex !== undefined ? link.targetIndex : -1
            }));
            
            setCosmographData({
              points: indexedNodes,
              links: indexedLinks
            });
            
            // Mark data preparation as complete
            loadingCoordinator.setStageComplete('dataPreparation', {
              nodesCount: transformedNodes.length,
              linksCount: transformedLinks.length
            });
          }
        } catch (error) {
          if (!cancelled) {
            const errorMessage = error instanceof Error ? error.message : 'Unknown error';
            logger.error('GraphCanvas: Data Kit preparation failed:', errorMessage);
            setDataKitError(errorMessage);
            
            // Fallback to direct data passing
            // Still try to update DuckDB if needed
            if (useDuckDBTables && duckdbService && clusterAssignments.length > 0) {
              try {
                await duckdbService.updateClusterData(clusterAssignments, clusterStrengths);
              } catch (err) {
                logger.error('GraphCanvas: Failed to update DuckDB cluster data in fallback:', err);
              }
            }
            
            // Ensure all nodes have proper index field in fallback too
            const indexedNodes = transformedNodes.map((node, idx) => ({
              ...node,
              index: node.index !== undefined ? node.index : idx
            }));
            
            // Ensure links have proper indices in fallback too
            const indexedLinks = transformedLinks.map(link => ({
              ...link,
              sourceIndex: link.sourceIndex !== undefined ? link.sourceIndex : -1,
              targetIndex: link.targetIndex !== undefined ? link.targetIndex : -1
            }));
            
            setCosmographData({
              points: indexedNodes,
              links: indexedLinks
            });
            
            // Still mark as complete even with error (we have fallback data)
            loadingCoordinator.setStageComplete('dataPreparation', {
              nodesCount: transformedNodes.length,
              linksCount: transformedLinks.length,
              hadError: true
            });
          }
        } finally {
            if (!cancelled) {
              setIsDataPreparing(false);
              
              // Ensure dataPreparation is marked complete in all cases
              if (loadingCoordinator.getStageStatus('dataPreparation') !== 'complete') {
                loadingCoordinator.setStageComplete('dataPreparation', {
                  nodesCount: transformedNodes.length || 0,
                  linksCount: transformedLinks.length || 0,
                  finally: true
                });
              }
            }
        }
      };

      prepareData();
      
      return () => {
        cancelled = true;
        clearTimeout(dataPreparationTimeout);
      };
    }, [nodes, links, dataKitConfig, isDuckDBInitialized, duckdbService, useDuckDBTables, config.clusteringEnabled, config.clusteringMethod, config.centralityMetric, config.clusterStrength]);

    // Mark canvas complete when Cosmograph data is loaded
    // This is more reliable than polling for canvas element when hidden
    useEffect(() => {
      if (cosmographData) {
        logger.log('GraphCanvas: Cosmograph data loaded, marking canvas as complete');
        
        // Mark canvas stage as complete when data is loaded
        // Cosmograph will handle the actual rendering
        loadingCoordinator.setStageComplete('canvas', {
          canvasReady: true,
          hasData: true
        });
      }
    }, [cosmographData]);

    // Canvas readiness tracking with single polling mechanism and WebGL context loss recovery
    const intervalRef = useRef<NodeJS.Timeout | null>(null);
    const [webglContextLost, setWebglContextLost] = useState(false);
    
    // WebGL context loss recovery
    const setupWebGLContextRecovery = useCallback(() => {
      const canvas = cosmographRef.current?._canvasElement;
      if (!canvas) return;

      const handleContextLost = (event: Event) => {
        event.preventDefault();
        setWebglContextLost(true);
      };

      const handleContextRestored = () => {
        setWebglContextLost(false);
        
        // Trigger re-render by restarting the simulation
        try {
          cosmographRef.current?.restart();
        } catch (error) {
          // WebGL context recovery error
        }
      };

      canvas.addEventListener('webglcontextlost', handleContextLost);
      canvas.addEventListener('webglcontextrestored', handleContextRestored);

      return () => {
        canvas.removeEventListener('webglcontextlost', handleContextLost);
        canvas.removeEventListener('webglcontextrestored', handleContextRestored);
      };
    }, []);
    
    useEffect(() => {
      // Set up continuous polling to check for cosmographRef availability
      let checkCount = 0;
      let webglCleanup: (() => void) | undefined;
      
      // Report canvas initialization started
      loadingCoordinator.updateStage('canvas', { status: 'loading', progress: 10 });
      
      // Fallback timeout to ensure canvas completes even if detection fails
      const fallbackTimeout = setTimeout(() => {
        if (loadingCoordinator.getStageStatus('canvas') !== 'complete') {
          console.warn('GraphCanvas: Canvas detection timeout, marking as complete');
          loadingCoordinator.setStageComplete('canvas', {
            canvasReady: true,
            fallback: true
          });
        }
      }, 1500); // 1.5 seconds fallback, since we mark complete when data loads
      
      const pollCosmographRef = () => {
        
        if (cosmographRef.current) {
          try {
            const canvas = cosmographRef.current._canvasElement;
            
            // Check if this specific canvas element has already been initialized
            if (canvas && cosmographInitializationMap.get(canvas)) {
              // Already initialized, just update state
              setCosmographRef(cosmographRef);
              setIsReady(true);
              setIsCanvasReady(true);
              
              // Report canvas ready
              loadingCoordinator.setStageComplete('canvas', {
                canvasReady: true
              });
              
              return;
            }
            
            // Mark this canvas as initialized
            if (canvas) {
              cosmographInitializationMap.set(canvas, true);
            }
            
            // Set the ref for use in GraphConfigProvider
            console.log('GraphCanvas: Setting cosmographRef');
            setCosmographRef(cosmographRef);
            setIsReady(true);
            
            // Report significant canvas progress
            loadingCoordinator.updateStage('canvas', { 
              status: 'loading', 
              progress: 50 
            });
            
            // Set up WebGL context loss recovery
            webglCleanup = setupWebGLContextRecovery();
            
            // Start canvas polling with optimized intervals
            const pollCanvas = () => {
              const hasCanvas = !!cosmographRef.current?._canvasElement;
              
              setIsCanvasReady(prevReady => {
                if (hasCanvas !== prevReady && hasCanvas) {
                  // Canvas is now ready - immediately mark as complete
                  loadingCoordinator.setStageComplete('canvas', {
                    canvasReady: true
                  });
                }
                return hasCanvas;
              });
              
              // Stop polling once canvas is found or after reasonable attempts
              if (!hasCanvas && checkCount < 20) { // Max 3 seconds of polling  
                checkCount++;
                // Progressive delay: 100ms, 150ms, 200ms, etc.
                const delay = Math.min(100 + (checkCount * 50), 500);
                // Clear any existing timeout before setting new one
                if (intervalRef.current) {
                  clearTimeout(intervalRef.current);
                }
                intervalRef.current = setTimeout(pollCanvas, delay);
              } else if (!hasCanvas) {
                // Canvas not found after polling, log warning
                logger.warn('Canvas element not found after polling');
                setIsCanvasReady(false);
              }
            };
            
            // Start canvas polling immediately
            pollCanvas();
          } catch (error) {
            // Canvas setup error - WeakMap will handle proper cleanup
          }
        } else {
          // Keep polling for cosmographRef with exponential backoff for up to 3 seconds
          if (checkCount < 30) {
            checkCount++;
            // Exponential backoff: 50ms, 100ms, 150ms, 200ms, etc.
            const delay = Math.min(50 + (checkCount * 10), 200);
            // Use intervalRef to track this timeout as well
            if (intervalRef.current) {
              clearTimeout(intervalRef.current);
            }
            intervalRef.current = setTimeout(pollCosmographRef, delay);
          } else {
            // Set a fallback timeout to prevent permanent blocking
            setIsReady(false);
          }
        }
      };
      
      // Start polling immediately
      pollCosmographRef();
      
      return () => {
        if (intervalRef.current) {
          clearTimeout(intervalRef.current);
          intervalRef.current = null;
        }
        clearTimeout(fallbackTimeout);
        if (webglCleanup) {
          webglCleanup();
        }
        // WeakMap automatically handles cleanup when canvas element is garbage collected
      };
    }, [setCosmographRef, setupWebGLContextRecovery]);


    // Simplified data transformation for legacy compatibility
    const transformedData = React.useMemo(() => {
      // Use the actual data that's being rendered by Cosmograph
      if (cosmographData?.points && cosmographData?.links) {
        return { nodes: cosmographData.points, links: cosmographData.links };
      }
      // Fallback to original data if cosmographData isn't ready
      return { nodes, links };
    }, [nodes, links, cosmographData]);
    
    // Handle popup for glowing nodes (search results)
    useEffect(() => {
      if (glowingNodes.size > 0 && cosmographRef.current && transformedData.nodes.length > 0) {
        // Get the first glowing node
        const firstGlowingNodeId = Array.from(glowingNodes.keys())[0];
        const nodeIndex = transformedData.nodes.findIndex(n => n.id === firstGlowingNodeId);
        
        if (nodeIndex >= 0) {
          // Clear existing popup timeout
          if (popupTimeoutRef.current) {
            clearTimeout(popupTimeoutRef.current);
          }
          
          // CosmographPopup not available - log search result instead
          logger.log('Search result found:', {
            count: glowingNodes.size,
            nodeIndex: nodeIndex
          });
        }
      }
    }, [glowingNodes, transformedData.nodes]);
    
    // Memoize node types for color generation
    const allNodeTypes = React.useMemo(() => {
      if (!nodes || nodes.length === 0) return [];
      return [...new Set(nodes.map(n => n.node_type).filter(Boolean))].sort();
    }, [nodes]);
    
    
    // Memoize color palette based on scheme
    const pointColorPalette = React.useMemo(() => {
      if (config.colorScheme === 'by-type') {
        return undefined; // Use pointColorByMap for type-based coloring
      }
      
      // For gradient-based schemes, use gradient from low to high color
      if (['by-centrality', 'by-pagerank', 'by-degree'].includes(config.colorScheme)) {
        return [config.gradientLowColor, config.gradientHighColor];
      }
      
      // For community detection, use a diverse palette
      if (config.colorScheme === 'by-community') {
        return ['#ff6b6b', '#4ecdc4', '#45b7d1', '#f39c12', '#e74c3c', '#9b59b6', '#3498db', '#2ecc71'];
      }
      
      return undefined;
    }, [config.colorScheme, config.gradientLowColor, config.gradientHighColor]);
    
    // Memoize color by function
    const pointColorByFn = React.useMemo(() => {
      if (config.colorScheme !== 'by-type') return undefined;
      
      return (nodeType: string) => {
        const typeColor = config.nodeTypeColors[nodeType];
        if (typeColor) {
          return typeColor;
        }
        
        const typeIndex = allNodeTypes.indexOf(nodeType);
        const generatedColor = generateNodeTypeColor(nodeType, typeIndex);
        return generatedColor;
      };
    }, [config.colorScheme, config.nodeTypeColors, allNodeTypes]);
    
    // Helper function to apply opacity to a color
    const applyOpacityToColor = (color: string, opacity: number): string => {
      if (color.startsWith('rgba')) {
        const match = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+),?\s*([\d.]+)?\)/);
        if (match) {
          return `rgba(${match[1]}, ${match[2]}, ${match[3]}, ${opacity})`;
        }
      } else if (color.startsWith('rgb')) {
        const match = color.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
        if (match) {
          return `rgba(${match[1]}, ${match[2]}, ${match[3]}, ${opacity})`;
        }
      } else if (color.startsWith('#')) {
        const hex = color.slice(1);
        const r = parseInt(hex.slice(0, 2), 16);
        const g = parseInt(hex.slice(2, 4), 16);
        const b = parseInt(hex.slice(4, 6), 16);
        return `rgba(${r}, ${g}, ${b}, ${opacity})`;
      }
      return color;
    };
    
    // Create node lookup maps for performance (avoid repeated array searches)
    const nodeIdToDataMap = React.useMemo(() => {
      const map = new Map<string, GraphNode>();
      currentNodes.forEach(node => {
        map.set(node.id, node);
      });
      return map;
    }, [currentNodes]);
    
    const linkIndexToDataMap = React.useMemo(() => {
      const map = new Map<number, GraphLink>();
      currentLinks.forEach((link, index) => {
        map.set(index, link);
      });
      return map;
    }, [currentLinks]);
    
    // Pre-calculate weight stats once
    const weightStats = React.useMemo(() => {
      if (currentLinks.length === 0) return { min: 1, max: 1, range: 1 };
      const weights = currentLinks.map(l => l.weight || 1);
      const maxWeight = Math.max(...weights);
      const minWeight = Math.min(...weights);
      return {
        min: minWeight,
        max: maxWeight,
        range: maxWeight - minWeight || 1
      };
    }, [currentLinks]);
    
    // Memoize link color function based on scheme and glowing nodes
    // linkColorByFn receives the value from linkColorBy column (edge_type) and the link index
    const linkColorFn = React.useMemo(() => {
      // Return undefined for uniform scheme to avoid function calls
      if (config.linkColorScheme === 'uniform' && config.linkOpacityScheme === 'uniform' && glowingNodes.size === 0) {
        return undefined;
      }
      
      // Pre-cache color values for common edge types
      const typeColorCache = new Map<string, string>([
        ['relates_to', '#4ECDC4'],
        ['causes', '#F6AD55'],
        ['precedes', '#B794F6'],
        ['contains', '#90CDF4'],
        ['default', config.linkColor]
      ]);
      
      // Return a single function that handles all cases
      return (edgeType: any, linkIndex: number) => {
        // If nodes are glowing, override the color scheme to highlight connected edges
        if (glowingNodes.size > 0) {
          // Get the correct data source
          const dataSource = useDuckDBTables ? duckDBData : cosmographData;
          if (!dataSource || !dataSource.links) {
            return config.linkColor;
          }
          
          // Handle Arrow table vs array data
          let link: any;
          if (useDuckDBTables && duckDBData?.links?.get) {
            // Arrow table - use get method
            link = duckDBData.links.get(linkIndex);
            if (!link) return config.linkColor;
          } else if (cosmographData?.links?.[linkIndex]) {
            // JavaScript array
            link = cosmographData.links[linkIndex];
          } else {
            return config.linkColor;
          }
          const sourceId = String(link.source);
          const targetId = String(link.target);
          
          // Check if either source or target node is glowing
          const sourceGlowTime = glowingNodes.get(sourceId);
          const targetGlowTime = glowingNodes.get(targetId);
          
          if (sourceGlowTime || targetGlowTime) {
            // Use the earlier glow time if both nodes are glowing
            const glowStartTime = sourceGlowTime && targetGlowTime 
              ? Math.min(sourceGlowTime, targetGlowTime)
              : sourceGlowTime || targetGlowTime;
            
            // Calculate fade progress (0 to 1, where 1 is fully faded back to normal)
            const elapsed = Date.now() - glowStartTime;
            const fadeDuration = 2000; // 2 seconds total, same as nodes
            const fadeProgress = Math.min(elapsed / fadeDuration, 1);
            
            // Use the same highlight color as nodes for consistency
            const highlightColor = config.nodeAccessHighlightColor;
            const baseColor = config.linkColor;
            
            // Parse colors to RGB
            const parseColor = (color: string): [number, number, number, number] => {
              if (color.startsWith('rgba')) {
                const match = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+),?\s*([\d.]+)?\)/);
                if (match) {
                  return [
                    parseInt(match[1]), 
                    parseInt(match[2]), 
                    parseInt(match[3]), 
                    parseFloat(match[4] || '1')
                  ];
                }
              } else if (color.startsWith('#')) {
                const hex = color.slice(1);
                return [
                  parseInt(hex.slice(0, 2), 16),
                  parseInt(hex.slice(2, 4), 16),
                  parseInt(hex.slice(4, 6), 16),
                  1
                ];
              }
              return [102, 102, 102, 0.5]; // Default gray color
            };
            
            const [baseR, baseG, baseB, baseA] = parseColor(baseColor);
            const [highlightR, highlightG, highlightB, highlightA] = parseColor(highlightColor);
            
            // Use easing function for smooth transition (ease-in-out)
            const easeInOut = (t: number) => t < 0.5 
              ? 2 * t * t 
              : -1 + (4 - 2 * t) * t;
            
            const easedProgress = easeInOut(fadeProgress);
            
            // Interpolate between highlight and base color
            const r = Math.round(highlightR + (baseR - highlightR) * easedProgress);
            const g = Math.round(highlightG + (baseG - highlightG) * easedProgress);
            const b = Math.round(highlightB + (baseB - highlightB) * easedProgress);
            const a = highlightA + (baseA - highlightA) * easedProgress;
            
            return `rgba(${r}, ${g}, ${b}, ${a})`;
          }
          
          // Return normal color for non-connected edges
          return config.linkColor;
        }
        
        // Apply opacity scheme if needed
        let opacity = 1;
        if (config.linkOpacityScheme && config.linkOpacityScheme !== 'uniform') {
          const link = linkIndexToDataMap.get(linkIndex);
          if (link) {
            switch (config.linkOpacityScheme) {
              case 'by-source-centrality': {
                const sourceNode = nodeIdToDataMap.get(link.source);
                if (sourceNode) {
                  const centrality = sourceNode.properties?.degree_centrality || 0;
                  opacity = 0.1 + (centrality * 0.9);
                }
                break;
              }
              case 'by-distance': {
                const sourceNode = nodeIdToDataMap.get(link.source);
                const targetNode = nodeIdToDataMap.get(link.target);
                if (sourceNode?.x !== undefined && targetNode?.x !== undefined) {
                  const distance = Math.sqrt(
                    Math.pow(targetNode.x - sourceNode.x, 2) + 
                    Math.pow(targetNode.y - sourceNode.y, 2)
                  );
                  const maxDist = 500;
                  const normalizedDist = Math.min(distance / maxDist, 1);
                  opacity = 0.1 + (1 - normalizedDist) * 0.9;
                }
                break;
              }
            }
          }
        }
        
        // Original color scheme logic when not glowing
        if (!config.linkColorScheme || config.linkColorScheme === 'uniform') {
          const baseColor = config.linkColor;
          // Apply opacity if needed
          if (opacity < 1) {
            return applyOpacityToColor(baseColor, opacity);
          }
          return baseColor;
        }
        
        // Get the actual link data from the current links when needed
        const link = linkIndexToDataMap.get(linkIndex);
        if (!link) return config.linkColor;
        
        switch (config.linkColorScheme) {
          case 'by-weight': {
            // Color by edge weight - interpolate between low and high colors
            const weight = link.weight || 1;
            const normalized = (weight - weightStats.min) / weightStats.range;
            // Interpolate between link color and a highlight color
            const r = Math.round(102 + (239 - 102) * normalized); // From #666 to #ef4444
            const g = Math.round(102 + (68 - 102) * normalized);
            const b = Math.round(102 + (68 - 102) * normalized);
            const color = `rgb(${r}, ${g}, ${b})`;
            return opacity < 1 ? applyOpacityToColor(color, opacity) : color;
          }
            
          case 'by-type': {
            // Color by edge type - edgeType is already passed as the first parameter
            const edgeTypeStr = String(edgeType || 'default');
            const color = typeColorCache.get(edgeTypeStr) || config.linkColor;
            return opacity < 1 ? applyOpacityToColor(color, opacity) : color;
          }
            
          case 'by-distance': {
            // Color by link distance/length
            const sourceNode = nodeIdToDataMap.get(link.source);
            const targetNode = nodeIdToDataMap.get(link.target);
            if (sourceNode?.x !== undefined && targetNode?.x !== undefined) {
              const distance = Math.sqrt(
                Math.pow(targetNode.x - sourceNode.x, 2) + 
                Math.pow(targetNode.y - sourceNode.y, 2)
              );
              const maxDist = 500; // Approximate max distance
              const normalizedDist = Math.min(distance / maxDist, 1);
              // Fade from bright to dim based on distance
              const distOpacity = Math.round(255 * (1 - normalizedDist * 0.7));
              return `rgba(102, 102, 102, ${distOpacity / 255})`;
            }
            return config.linkColor;
          }
            
          case 'by-source-node': {
            // Color from source (originating) node
            const sourceNode = nodeIdToDataMap.get(link.source);
            if (sourceNode) {
              const sourceNodeColor = config.nodeTypeColors[sourceNode.node_type] || config.linkColor;
              return opacity < 1 ? applyOpacityToColor(sourceNodeColor, opacity) : sourceNodeColor;
            }
            const color = config.linkColor;
            return opacity < 1 ? applyOpacityToColor(color, opacity) : color;
          }
          
          case 'gradient': {
            // Gradient from source to target node colors (future: true gradient)
            const sourceNode = nodeIdToDataMap.get(link.source);
            const targetNode = nodeIdToDataMap.get(link.target);
            const sourceNodeColor = sourceNode ? config.nodeTypeColors[sourceNode.node_type] : '';
            const targetNodeColor = targetNode ? config.nodeTypeColors[targetNode.node_type] : '';
            // For now, blend the colors simply
            const color = sourceNodeColor || config.linkColor;
            return opacity < 1 ? applyOpacityToColor(color, opacity) : color;
          }
            
          case 'by-community': {
            // Color bridges between communities differently
            const sourceNode = nodeIdToDataMap.get(link.source);
            const targetNode = nodeIdToDataMap.get(link.target);
            const sourceCommunity = sourceNode?.cluster;
            const targetCommunity = targetNode?.cluster;
            const color = sourceCommunity !== targetCommunity ? '#FF6B6B' : config.linkColor;
            return opacity < 1 ? applyOpacityToColor(color, opacity) : color;
          }
            
          default:
            return opacity < 1 ? applyOpacityToColor(config.linkColor, opacity) : config.linkColor;
        }
      };
    }, [config.linkColorScheme, config.linkOpacityScheme, config.linkColor, config.nodeTypeColors, config.nodeAccessHighlightColor, glowingNodes, useDuckDBTables, duckDBData, cosmographData, applyOpacityToColor, nodeIdToDataMap, linkIndexToDataMap, weightStats]);
    
    // Memoize link width function based on scheme
    const linkWidthFn = React.useMemo(() => {
      if (!config.linkWidthScheme || config.linkWidthScheme === 'uniform') {
        return undefined; // Use default weight column
      }
      
      return (weight: any, linkIndex: number) => {
        const link = linkIndexToDataMap.get(linkIndex);
        if (!link) return 1;
        
        // Cache source node lookup
        const sourceNode = nodeIdToDataMap.get(link.source);
        if (!sourceNode) return 1;
        
        switch (config.linkWidthScheme) {
          case 'by-source-centrality': {
            // Width based on source node's degree centrality
            const centrality = sourceNode.properties?.degree_centrality || 0;
            // Scale centrality to reasonable width range (0.5 to 5)
            return 0.5 + (centrality * 4.5);
          }
          
          case 'by-source-pagerank': {
            // Width based on source node's PageRank
            const pagerank = sourceNode.properties?.pagerank_centrality || sourceNode.properties?.pagerank || 0;
            // PageRank is usually much smaller, so scale more aggressively
            return 0.5 + (pagerank * 50);
          }
          
          case 'by-source-betweenness': {
            // Width based on source node's betweenness centrality
            const betweenness = sourceNode.properties?.betweenness_centrality || 0;
            return 0.5 + (betweenness * 4.5);
          }
          
          case 'by-weight': {
            // Use the actual weight value
            return Number(weight || 1);
          }
          
          default:
            return Number(weight || 1);
        }
      };
    }, [config.linkWidthScheme, nodeIdToDataMap, linkIndexToDataMap]);
    
    // Debug logging for link color scheme
    useEffect(() => {
      console.log('[GraphCanvas] Link color scheme changed:', config.linkColorScheme);
      console.log('[GraphCanvas] Link width scheme changed:', config.linkWidthScheme);
      console.log('[GraphCanvas] Link opacity scheme changed:', config.linkOpacityScheme);
    }, [config.linkColorScheme, config.linkWidthScheme, config.linkOpacityScheme]);

    // Note: We don't need these separate functions anymore since we're using inline functions in the props
    
    // Improved throttling for mouse move with requestAnimationFrame
    const lastHoverTimeRef = useRef<number>(0);
    const lastHoveredIndexRef = useRef<number | undefined>(undefined);
    const hoverAnimationFrameRef = useRef<number | null>(null);
    const pendingHoverRef = useRef<{ index: number | undefined } | null>(null);
    
    const handleMouseMove = React.useCallback((index: number | undefined) => {
      // Skip if same index
      if (index === lastHoveredIndexRef.current) {
        return;
      }

      // Store pending hover
      pendingHoverRef.current = { index };

      // Cancel previous animation frame
      if (hoverAnimationFrameRef.current) {
        cancelAnimationFrame(hoverAnimationFrameRef.current);
      }

      // Helper to resolve a node by Cosmograph index using ID mapping for correctness
      const resolveNodeByIndex = async (idx: number) => {
        // Try to use Cosmograph API to get the actual point by index, then map by id
        if (cosmographRef.current && typeof cosmographRef.current.getPointsByIndices === 'function') {
          try {
            const points = await cosmographRef.current.getPointsByIndices([idx]);
            const point = points && points[0];
            const nodeId = point?.id != null ? String(point.id) : undefined;
            if (nodeId) {
              const nodeById = transformedData.nodes.find(n => n.id === nodeId);
              if (nodeById) return nodeById;
            }
          } catch (e) {
            // Swallow and use fallbacks below
          }
        }
        // Fallbacks: try transformedData by index first (more aligned with Cosmograph), then currentNodes
        if (idx >= 0 && idx < transformedData.nodes.length) {
          return transformedData.nodes[idx];
        }
        if (idx >= 0 && idx < currentNodes.length) {
          return currentNodes[idx];
        }
        return undefined;
      };

      // Schedule update on next animation frame
      hoverAnimationFrameRef.current = requestAnimationFrame(() => {
        const now = Date.now();

        // Throttle to max 30fps (33ms) for better performance
        if (now - lastHoverTimeRef.current < 33) {
          // Reschedule for next frame
          hoverAnimationFrameRef.current = requestAnimationFrame(async () => {
            if (pendingHoverRef.current) {
              const { index } = pendingHoverRef.current;
              lastHoverTimeRef.current = now;
              lastHoveredIndexRef.current = index;

              if (index !== undefined && index >= 0) {
                const hoveredNode = await resolveNodeByIndex(index);
                // Ensure still relevant (no newer hover superseded this)
                if (lastHoveredIndexRef.current === index) {
                  if (hoveredNode) {
                    console.log('[GraphCanvas] Hover resolved - index:', index, 'nodeId:', hoveredNode.id, 'label:', hoveredNode.label);
                  } else {
                    console.warn('[GraphCanvas] Failed to resolve node for hover index:', index);
                  }
                  onNodeHover?.(hoveredNode ?? null);
                }
              } else {
                onNodeHover?.(null);
              }

              pendingHoverRef.current = null;
            }
          });
          return;
        }

        if (pendingHoverRef.current) {
          const { index } = pendingHoverRef.current;
          lastHoverTimeRef.current = now;
          lastHoveredIndexRef.current = index;

          if (index !== undefined && index >= 0) {
            // Resolve node accurately by index -> id mapping
            resolveNodeByIndex(index).then(hoveredNode => {
              if (lastHoveredIndexRef.current === index) {
                if (hoveredNode) {
                  console.log('[GraphCanvas] Hover resolved (fallback) - index:', index, 'nodeId:', hoveredNode.id, 'label:', hoveredNode.label);
                } else {
                  console.warn('[GraphCanvas] Failed to resolve node for hover index (fallback):', index);
                }
                onNodeHover?.(hoveredNode ?? null);
              }
            });
          } else {
            onNodeHover?.(null);
          }

          pendingHoverRef.current = null;
        }
      });
    }, [currentNodes, transformedData.nodes, onNodeHover]);

    // Method to select a single node in Cosmograph
    const selectCosmographNode = useCallback((node: GraphNode) => {
      if (cosmographRef.current) {
        try {
          // For Cosmograph v2.0 with Data Kit, we need to use point indices
          if (typeof cosmographRef.current.selectPoint === 'function') {
            // Try to find the node index from the transformed data
            const nodeIndex = transformedData.nodes.findIndex(n => n.id === node.id);
            if (nodeIndex >= 0) {
              cosmographRef.current.selectPoint(nodeIndex);
            } else {
              logger.warn('Could not find node index for selection:', node.id);
            }
          } else if (typeof cosmographRef.current.selectPoints === 'function') {
            const nodeIndex = transformedData.nodes.findIndex(n => n.id === node.id);
            if (nodeIndex >= 0) {
              cosmographRef.current.selectPoints([nodeIndex]);
            }
          }
        } catch (error) {
          logger.error('Error selecting Cosmograph node:', error);
        }
      }
    }, [transformedData.nodes]);

    // Method to select multiple nodes in Cosmograph
    const selectCosmographNodes = useCallback((nodes: GraphNode[]) => {
      if (cosmographRef.current) {
        try {
          if (typeof cosmographRef.current.selectPoints === 'function') {
            // Convert node IDs to indices
            const nodeIndices = nodes.map(node => {
              return transformedData.nodes.findIndex(n => n.id === node.id);
            }).filter(index => index >= 0); // Remove invalid indices
            
            if (nodeIndices.length > 0) {
              cosmographRef.current.selectPoints(nodeIndices);
              
              // For multiple nodes, use fitViewByIndices to show all selected nodes
              if (nodeIndices.length > 1) {
                // Call fitViewByIndices after this function completes
                setTimeout(() => {
                  if (cosmographRef.current && typeof cosmographRef.current.fitViewByIndices === 'function') {
                    cosmographRef.current.fitViewByIndices(nodeIndices, config.fitViewDuration, config.fitViewPadding);
                    
                    // Track positions of all selected nodes
                    if (typeof cosmographRef.current.trackPointPositionsByIndices === 'function') {
                      cosmographRef.current.trackPointPositionsByIndices(nodeIndices);
                    }
                  }
                }, 0);
              } else if (nodeIndices.length === 1) {
                // For single node, set focused point
                if (typeof cosmographRef.current.setFocusedPoint === 'function') {
                  // Enable following if configured
                  if (config.followSelectedNode) {
                    cosmographRef.current.setFocusedPoint(nodeIndices[0]);
                  } else {
                    cosmographRef.current.setFocusedPoint(nodeIndices[0]);
                  }
                }
                // Track single node position
                if (typeof cosmographRef.current.trackPointPositionsByIndices === 'function') {
                  cosmographRef.current.trackPointPositionsByIndices(nodeIndices);
                }
              }
            } else {
              logger.warn('No valid node indices found for selection');
            }
          } else {
            logger.warn('No selectPoints method found on Cosmograph instance');
          }
        } catch (error) {
          logger.error('Error selecting Cosmograph nodes:', error);
        }
      }
    }, [transformedData.nodes, config.fitViewDuration, config.fitViewPadding]);

    // Method to get current live statistics
    const getLiveStats = useCallback(() => {
      return {
        nodeCount: liveStats.nodeCount,
        edgeCount: liveStats.edgeCount,
        lastUpdated: liveStats.lastUpdated
      };
    }, [liveStats]);

    // Method to clear Cosmograph selection and return to default state
    const clearCosmographSelection = useCallback(() => {
      if (cosmographRef.current) {
        try {
          // Use native Cosmograph methods to clear selection
          if (typeof cosmographRef.current.unselectAll === 'function') {
            cosmographRef.current.unselectAll();
          } else if (typeof cosmographRef.current.unselectAllPoints === 'function') {
            cosmographRef.current.unselectAllPoints();
          } else if (typeof cosmographRef.current.selectPoints === 'function') {
            cosmographRef.current.selectPoints([]);
          } else {
            logger.warn('No clear selection method found on Cosmograph instance');
          }
          
          // Clear focused node and stop tracking
          if (typeof cosmographRef.current.unfocusNode === 'function') {
            cosmographRef.current.unfocusNode();
          } else if (typeof cosmographRef.current.setFocusedPoint === 'function') {
            cosmographRef.current.setFocusedPoint();
          }
          
          // Stop tracking positions
          if (typeof cosmographRef.current.trackPointPositionsByIndices === 'function') {
            cosmographRef.current.trackPointPositionsByIndices([]);
          }
        } catch (error) {
          logger.error('Error clearing Cosmograph selection:', error);
        }
      }
    }, []);

    const zoomIn = useCallback(() => {
      if (!cosmographRef.current) return;
      
      try {
        // Use the official Cosmograph v2.0 API method with animation duration
        const currentZoom = cosmographRef.current.getZoomLevel();
        if (currentZoom !== undefined) {
          const newZoom = Math.min(currentZoom * 1.5, 10);
          cosmographRef.current.setZoomLevel(newZoom, config.fitViewDuration);
        } else {
          logger.warn('Could not get current zoom level for zoom in');
        }
      } catch (error) {
        logger.warn('Zoom in failed:', error);
      }
    }, [config.fitViewDuration]);

    const zoomOut = useCallback(() => {
      if (!cosmographRef.current) return;
      
      try {
        // Use the official Cosmograph v2.0 API method with animation duration
        const currentZoom = cosmographRef.current.getZoomLevel();
        if (currentZoom !== undefined) {
          const newZoom = Math.max(currentZoom / 1.5, 0.1);
          cosmographRef.current.setZoomLevel(newZoom, config.fitViewDuration);
        } else {
          logger.warn('Could not get current zoom level for zoom out');
        }
      } catch (error) {
        logger.warn('Zoom out failed:', error);
      }
    }, [config.fitViewDuration]);

    const fitView = useCallback(() => {
      if (!cosmographRef.current) return;
      
      // Ensure canvas is ready
      if (!isCanvasReady) {
        logger.warn('GraphCanvas: Cannot fitView - canvas not ready');
        return;
      }
      
      // Ensure we have data (nodes are required, links are optional)
      if (!currentNodes.length) {
        logger.warn('GraphCanvas: Cannot fitView - no nodes');
        return;
      }
      
      try {
        logger.log('GraphCanvas: Calling fitView with duration:', config.fitViewDuration, 'padding:', config.fitViewPadding);
        
        // Call fitView directly without pausing simulation
        // Cosmograph v2.0 handles the animation smoothly without needing to pause
        cosmographRef.current.fitView(config.fitViewDuration, config.fitViewPadding);
        
      } catch (error) {
        logger.warn('Fit view failed:', error);
      }
    }, [config.fitViewDuration, config.fitViewPadding, currentNodes.length, isCanvasReady]);

    const fitViewByIndices = useCallback((indices: number[], duration?: number, padding?: number) => {
      if (!cosmographRef.current) return;
      
      try {
        // Use the Cosmograph v2.0 fitViewByIndices method with config defaults
        const actualDuration = duration !== undefined ? duration : config.fitViewDuration;
        const actualPadding = padding !== undefined ? padding : config.fitViewPadding;
        cosmographRef.current.fitViewByIndices(indices, actualDuration, actualPadding);
      } catch (error) {
        logger.warn('Fit view by indices failed:', error);
      }
    }, [config.fitViewDuration, config.fitViewPadding]);

    const focusOnNodes = useCallback((nodeIds: string[], duration?: number, padding?: number) => {
      console.log('GraphCanvas: focusOnNodes called with nodeIds:', nodeIds);
      console.log('GraphCanvas: cosmographRef.current exists:', !!cosmographRef.current);
      
      if (!cosmographRef.current) {
        logger.warn('GraphCanvas: focusOnNodes returning early - no cosmographRef');
        return;
      }
      
      // Use currentNodes instead of nodes prop to avoid stale closures in dev mode
      const nodesList = currentNodes.length > 0 ? currentNodes : nodes;
      console.log('GraphCanvas: using nodes.length:', nodesList.length);
      
      if (!nodesList.length) {
        logger.warn('GraphCanvas: focusOnNodes returning early - no nodes available');
        return;
      }
      
      try {
        // Find indices of the nodes with the given IDs
        const indices: number[] = [];
        nodeIds.forEach(nodeId => {
          const index = nodesList.findIndex(node => node.id === nodeId);
          if (index >= 0) {
            indices.push(index);
          }
        });
        
        console.log('GraphCanvas: Found indices:', indices);
        
        if (indices.length > 0) {
          // First select the nodes visually
          const nodesToSelect = indices.map(idx => nodesList[idx]).filter(Boolean);
          if (nodesToSelect.length > 0) {
            selectCosmographNodes(nodesToSelect);
          }
          
          // Use requestAnimationFrame for better timing in dev mode
          requestAnimationFrame(() => {
            // Double-check cosmographRef is still valid
            if (!cosmographRef.current) {
              logger.warn('GraphCanvas: cosmographRef lost after frame');
              return;
            }
            
            // Verify the method exists
            if (typeof cosmographRef.current.fitViewByIndices !== 'function') {
              logger.warn('fitViewByIndices method not available on Cosmograph instance');
              return;
            }
            
            const actualDuration = duration !== undefined ? duration : 1000;
            const actualPadding = padding !== undefined ? padding : 0.2;
            
            // Use shorter delay in development for better responsiveness
            const delay = process.env.NODE_ENV === 'development' ? 50 : 200;
            
            setTimeout(() => {
              try {
                // Final safety check
                if (cosmographRef.current && typeof cosmographRef.current.fitViewByIndices === 'function') {
                  console.log('GraphCanvas: Calling fitViewByIndices with indices:', indices);
                  cosmographRef.current.fitViewByIndices(indices, actualDuration, actualPadding);
                }
              } catch (error) {
                console.error('GraphCanvas: fitViewByIndices failed:', error);
                logger.warn('fitViewByIndices failed:', error);
              }
            }, delay);
          });
        } else {
          logger.warn('No nodes found with the provided IDs:', nodeIds);
        }
      } catch (error) {
        logger.warn('Focus on nodes failed:', error);
      }
    }, [nodes, selectCosmographNodes]);

    const zoomToPoint = useCallback((index: number, duration?: number, scale?: number, canZoomOut?: boolean) => {
      if (!cosmographRef.current) return;
      
      try {
        // Don't restart simulation - just zoom to the point
        // The simulation can continue running at its current state
        
        // Use the Cosmograph v2.0 zoomToPoint method with config defaults
        const actualDuration = duration !== undefined ? duration : config.fitViewDuration;
        const actualScale = scale !== undefined ? scale : 6.0; // Good zoom scale for detailed focus
        const actualCanZoomOut = canZoomOut !== undefined ? canZoomOut : true;
        cosmographRef.current.zoomToPoint(index, actualDuration, actualScale, actualCanZoomOut);
      } catch (error) {
        logger.warn('Zoom to point failed:', error);
      }
    }, [config.fitViewDuration]);

    const trackPointPositionsByIndices = useCallback((indices: number[]) => {
      if (!cosmographRef.current) return;
      
      try {
        cosmographRef.current.trackPointPositionsByIndices(indices);
      } catch (error) {
        logger.warn('Track point positions failed:', error);
      }
    }, []);

    const getTrackedPointPositionsMap = useCallback(() => {
      if (!cosmographRef.current) return undefined;
      
      try {
        return cosmographRef.current.getTrackedPointPositionsMap();
      } catch (error) {
        logger.warn('Get tracked point positions failed:', error);
        return undefined;
      }
    }, []);

    // Rectangle selection methods
    const activateRectSelection = useCallback(() => {
      if (!cosmographRef.current) return;
      
      try {
        cosmographRef.current.activateRectSelection();
      } catch (error) {
        logger.warn('Activate rect selection failed:', error);
      }
    }, []);

    const deactivateRectSelection = useCallback(() => {
      if (!cosmographRef.current) return;
      
      try {
        cosmographRef.current.deactivateRectSelection();
      } catch (error) {
        logger.warn('Deactivate rect selection failed:', error);
      }
    }, []);

    const selectPointsInRect = useCallback((selection: [[number, number], [number, number]] | null, addToSelection = false) => {
      if (!cosmographRef.current) return;
      
      try {
        cosmographRef.current.selectPointsInRect(selection, addToSelection);
      } catch (error) {
        logger.warn('Select points in rect failed:', error);
      }
    }, []);

    // Polygonal selection methods
    const activatePolygonalSelection = useCallback(() => {
      if (!cosmographRef.current) return;
      
      try {
        cosmographRef.current.activatePolygonalSelection();
      } catch (error) {
        logger.warn('Activate polygonal selection failed:', error);
      }
    }, []);

    const deactivatePolygonalSelection = useCallback(() => {
      if (!cosmographRef.current) return;
      
      try {
        cosmographRef.current.deactivatePolygonalSelection();
      } catch (error) {
        logger.warn('Deactivate polygonal selection failed:', error);
      }
    }, []);

    const selectPointsInPolygon = useCallback((polygonPoints: [number, number][], addToSelection = false) => {
      if (!cosmographRef.current) return;
      
      try {
        cosmographRef.current.selectPointsInPolygon(polygonPoints, addToSelection);
      } catch (error) {
        logger.warn('Select points in polygon failed:', error);
      }
    }, []);

    // Get connected nodes
    const getConnectedPointIndices = useCallback((index: number): number[] | undefined => {
      if (!cosmographRef.current) return undefined;
      
      try {
        return cosmographRef.current.getConnectedPointIndices(index);
      } catch (error) {
        logger.warn('Get connected point indices failed:', error);
        return undefined;
      }
    }, []);

    // Search for nodes by exact property values
    const getPointIndicesByExactValues = useCallback((keyValues: Record<string, unknown>): number[] | undefined => {
      if (!cosmographRef.current) return undefined;
      
      try {
        return cosmographRef.current.getPointIndicesByExactValues(keyValues);
      } catch (error) {
        logger.warn('Get point indices by exact values failed:', error);
        return undefined;
      }
    }, []);

    // Incremental update methods
    const addIncrementalData = useCallback(async (newNodes: GraphNode[], newLinks: GraphLink[], runSimulation = false) => {
      if (!cosmographRef.current) return;
      
      try {
        // Set flag to prevent main Data Kit effect from running
        isIncrementalUpdateRef.current = true;
        
        // Merge new data with existing data
        const updatedNodes = [...currentNodes, ...newNodes];
        const updatedLinks = [...currentLinks, ...newLinks];
        
        // Update internal state
        setCurrentNodes(updatedNodes);
        setCurrentLinks(updatedLinks);
        
        // Transform and use Cosmograph's setData directly for efficiency
        if (cosmographRef.current.setData && updatedNodes.length > 0) {
          const transformedNodes = updatedNodes.map(node => ({
            id: String(node.id),
            label: String(node.label || node.id),
            node_type: String(node.node_type || 'Unknown'),
            centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
            cluster: String(node.node_type || 'Unknown'),
            clusterStrength: 0.7,
            degree_centrality: Number(node.properties?.degree_centrality || 0),
            pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
            betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
            eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0),
            // Include temporal data for timeline
            created_at: node.properties?.created_at || node.created_at || node.properties?.created || null,
            created_at_timestamp: (node.properties?.created_at || node.created_at || node.properties?.created) ? new Date(node.properties?.created_at || node.created_at || node.properties?.created).getTime() : null
          }));
          
          const transformedLinks = updatedLinks.map(link => ({
            source: String(link.source),
            target: String(link.target),
            edge_type: String(link.edge_type || 'default'),
            weight: Number(link.weight || 1)
          }));
          
          // Use direct setData without Data Kit reprocessing for better performance
          cosmographRef.current.setData(transformedNodes, transformedLinks, runSimulation);
        }
      } catch (error) {
        logger.error('Incremental data update failed:', error);
      } finally {
        // Reset flag after a brief delay
        setTimeout(() => {
          isIncrementalUpdateRef.current = false;
        }, 100);
      }
    }, [currentNodes, currentLinks]);
    
    const updateNodes = useCallback(async (updatedNodes: GraphNode[]) => {
      if (!cosmographRef.current?.setData) return;
      
      try {
        isIncrementalUpdateRef.current = true;
        
        // Create a map for quick lookup
        const updateMap = new Map(updatedNodes.map(node => [node.id, node]));
        
        // Update existing nodes
        const newCurrentNodes = currentNodes.map(node => 
          updateMap.has(node.id) ? updateMap.get(node.id)! : node
        );
        
        setCurrentNodes(newCurrentNodes);
        
        // Transform and update directly
        const transformedNodes = newCurrentNodes.map(node => ({
          id: String(node.id),
          label: String(node.label || node.id),
          node_type: String(node.node_type || 'Unknown'),
          centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
          degree_centrality: Number(node.properties?.degree_centrality || 0),
          pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
          betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
          eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0),
          // Include temporal data for timeline
          created_at: node.properties?.created_at || node.created_at || node.properties?.created || null,
          created_at_timestamp: (node.properties?.created_at || node.created_at || node.properties?.created) ? new Date(node.properties?.created_at || node.created_at || node.properties?.created).getTime() : null,
          // Cluster by node type for proper grouping
          cluster: String(node.node_type || 'Unknown'),
          clusterStrength: 0.7 // Strong clustering by type (0-1 range)
        }));
        
        const transformedLinks = currentLinks.map(link => ({
          source: String(link.source),
          target: String(link.target),
          edge_type: String(link.edge_type || 'default'),
          weight: Number(link.weight || 1)
        }));
        
        cosmographRef.current.setData(transformedNodes, transformedLinks, false);
      } catch (error) {
        logger.error('Node update failed:', error);
      } finally {
        setTimeout(() => {
          isIncrementalUpdateRef.current = false;
        }, 100);
      }
    }, [currentNodes, currentLinks]);
    
    const updateLinks = useCallback(async (updatedLinks: GraphLink[]) => {
      if (!cosmographRef.current?.setData) return;
      
      try {
        isIncrementalUpdateRef.current = true;
        
        // Create a map for quick lookup by source-target pair
        const updateMap = new Map(updatedLinks.map(link => [`${link.source}-${link.target}`, link]));
        
        // Update existing links
        const newCurrentLinks = currentLinks.map(link => {
          const key = `${link.source}-${link.target}`;
          return updateMap.has(key) ? updateMap.get(key)! : link;
        });
        
        setCurrentLinks(newCurrentLinks);
        
        // Transform and update directly
        const transformedNodes = currentNodes.map(node => ({
          id: String(node.id),
          label: String(node.label || node.id),
          node_type: String(node.node_type || 'Unknown'),
          centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
          degree_centrality: Number(node.properties?.degree_centrality || 0),
          pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
          betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
          eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0),
          // Include temporal data for timeline
          created_at: node.properties?.created_at || node.created_at || node.properties?.created || null,
          created_at_timestamp: (node.properties?.created_at || node.created_at || node.properties?.created) ? new Date(node.properties?.created_at || node.created_at || node.properties?.created).getTime() : null,
          // Cluster by node type for proper grouping
          cluster: String(node.node_type || 'Unknown'),
          clusterStrength: 0.7 // Strong clustering by type (0-1 range)
        }));
        
        const transformedLinks = newCurrentLinks.map(link => ({
          source: String(link.source),
          target: String(link.target),
          edge_type: String(link.edge_type || 'default'),
          weight: Number(link.weight || 1)
        }));
        
        cosmographRef.current.setData(transformedNodes, transformedLinks, false);
      } catch (error) {
        logger.error('Link update failed:', error);
      } finally {
        setTimeout(() => {
          isIncrementalUpdateRef.current = false;
        }, 100);
      }
    }, [currentLinks, currentNodes]);
    
    const removeNodes = useCallback(async (nodeIds: string[]) => {
      if (!cosmographRef.current?.setData) return;
      
      try {
        isIncrementalUpdateRef.current = true;
        
        const nodeIdSet = new Set(nodeIds);
        
        // Remove nodes
        const filteredNodes = currentNodes.filter(node => !nodeIdSet.has(node.id));
        
        // Remove links connected to removed nodes
        const filteredLinks = currentLinks.filter(link => 
          !nodeIdSet.has(link.source) && !nodeIdSet.has(link.target)
        );
        
        setCurrentNodes(filteredNodes);
        setCurrentLinks(filteredLinks);
        
        // Transform and update directly
        const transformedNodes = filteredNodes.map(node => ({
          id: String(node.id),
          label: String(node.label || node.id),
          node_type: String(node.node_type || 'Unknown'),
          centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
          degree_centrality: Number(node.properties?.degree_centrality || 0),
          pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
          betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
          eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0),
          // Include temporal data for timeline
          created_at: node.properties?.created_at || node.created_at || node.properties?.created || null,
          created_at_timestamp: (node.properties?.created_at || node.created_at || node.properties?.created) ? new Date(node.properties?.created_at || node.created_at || node.properties?.created).getTime() : null,
          // Cluster by node type for proper grouping
          cluster: String(node.node_type || 'Unknown'),
          clusterStrength: 0.7 // Strong clustering by type (0-1 range)
        }));
        
        const transformedLinks = filteredLinks.map(link => ({
          source: String(link.source),
          target: String(link.target),
          edge_type: String(link.edge_type || 'default'),
          weight: Number(link.weight || 1)
        }));
        
        cosmographRef.current.setData(transformedNodes, transformedLinks, false);
      } catch (error) {
        logger.error('Node removal failed:', error);
      } finally {
        setTimeout(() => {
          isIncrementalUpdateRef.current = false;
        }, 100);
      }
    }, [currentNodes, currentLinks]);
    
    const removeLinks = useCallback(async (linkIds: string[]) => {
      if (!cosmographRef.current?.setData) return;
      
      try {
        isIncrementalUpdateRef.current = true;
        
        const linkIdSet = new Set(linkIds);
        
        // Remove links (assuming linkIds are in "source-target" format)
        const filteredLinks = currentLinks.filter(link => {
          const linkId = `${link.source}-${link.target}`;
          return !linkIdSet.has(linkId);
        });
        
        setCurrentLinks(filteredLinks);
        
        // Transform and update directly
        const transformedNodes = currentNodes.map(node => ({
          id: String(node.id),
          label: String(node.label || node.id),
          node_type: String(node.node_type || 'Unknown'),
          centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
          degree_centrality: Number(node.properties?.degree_centrality || 0),
          pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
          betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
          eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0),
          // Include temporal data for timeline
          created_at: node.properties?.created_at || node.created_at || node.properties?.created || null,
          created_at_timestamp: (node.properties?.created_at || node.created_at || node.properties?.created) ? new Date(node.properties?.created_at || node.created_at || node.properties?.created).getTime() : null,
          // Cluster by node type for proper grouping
          cluster: String(node.node_type || 'Unknown'),
          clusterStrength: 0.7 // Strong clustering by type (0-1 range)
        }));
        
        const transformedLinks = filteredLinks.map(link => ({
          source: String(link.source),
          target: String(link.target),
          edge_type: String(link.edge_type || 'default'),
          weight: Number(link.weight || 1)
        }));
        
        cosmographRef.current.setData(transformedNodes, transformedLinks, false);
      } catch (error) {
        logger.error('Link removal failed:', error);
      } finally {
        setTimeout(() => {
          isIncrementalUpdateRef.current = false;
        }, 100);
      }
    }, [currentLinks, currentNodes]);

    // Simulation control methods
    const startSimulation = useCallback((alpha = 1.0) => {
      if (cosmographRef.current && typeof cosmographRef.current.start === 'function') {
        cosmographRef.current.start(alpha);
      }
    }, []);
    
    const pauseSimulation = useCallback(() => {
      if (cosmographRef.current && typeof cosmographRef.current.pause === 'function') {
        cosmographRef.current.pause();
      }
      
      // Clear the keep-running timer
      if (simulationTimerRef.current) {
        clearInterval(simulationTimerRef.current);
        simulationTimerRef.current = null;
      }
    }, []);
    
    const resumeSimulation = useCallback(() => {
      if (cosmographRef.current && typeof cosmographRef.current.start === 'function') {
        const currentTime = Date.now();
        lastResumeTimeRef.current = currentTime;
        
        cosmographRef.current.start(0.3); // Resume with moderate energy
        setIsSimulationActive(true);
        
        
        // Use requestAnimationFrame to ensure the simulation state is properly propagated
        requestAnimationFrame(() => {
        });
      }
    }, []);
    
    const keepSimulationRunning = useCallback((enable: boolean) => {
      setKeepRunning(enable);
      
      // Don't interfere with Cosmograph's built-in simulation control
      // The simulation will run naturally based on the simulationDecay setting
      
      if (simulationTimerRef.current) {
        clearInterval(simulationTimerRef.current);
        simulationTimerRef.current = null;
      }
    }, []);

    
    // Handle tab visibility changes to restart simulation with debouncing
    useEffect(() => {
      let visibilityTimeoutId: NodeJS.Timeout | null = null;
      let focusTimeoutId: NodeJS.Timeout | null = null;
      
      const handleVisibilityChange = () => {
        // Clear any existing timeout
        if (visibilityTimeoutId) {
          clearTimeout(visibilityTimeoutId);
        }
        
        // Debounce visibility change handling
        visibilityTimeoutId = setTimeout(() => {
          if (!document.hidden && cosmographRef.current && !config.disableSimulation) {
            // Tab is now visible, restart simulation with low energy
            if (typeof cosmographRef.current.start === 'function') {
              cosmographRef.current.start(0.1);
            }
          }
        }, 300); // 300ms debounce
      };

      // Also handle window focus for better reliability
      const handleFocus = () => {
        // Clear any existing timeout
        if (focusTimeoutId) {
          clearTimeout(focusTimeoutId);
        }
        
        // Debounce focus handling
        focusTimeoutId = setTimeout(() => {
          if (cosmographRef.current && !config.disableSimulation) {
            // Window regained focus, ensure simulation is running
            if (typeof cosmographRef.current.start === 'function') {
              cosmographRef.current.start(0.05); // Even lower energy for focus events
            }
          }
        }, 500); // 500ms debounce for focus
      };

      document.addEventListener('visibilitychange', handleVisibilityChange);
      window.addEventListener('focus', handleFocus);
      
      return () => {
        document.removeEventListener('visibilitychange', handleVisibilityChange);
        window.removeEventListener('focus', handleFocus);
        
        // Clean up timeouts
        if (visibilityTimeoutId) {
          clearTimeout(visibilityTimeoutId);
        }
        if (focusTimeoutId) {
          clearTimeout(focusTimeoutId);
        }
      };
    }, [config.disableSimulation, setupWebGLContextRecovery]);
    
    // Cleanup all timers and refs on unmount
    useEffect(() => {
      return () => {
        // Clear simulation timer
        if (simulationTimerRef.current) {
          clearInterval(simulationTimerRef.current);
          simulationTimerRef.current = null;
        }
        // Clear double-click timeout
        if (doubleClickTimeoutRef.current) {
          clearTimeout(doubleClickTimeoutRef.current);
          doubleClickTimeoutRef.current = null;
        }
        // Clear canvas polling interval
        if (intervalRef.current) {
          clearTimeout(intervalRef.current);
          intervalRef.current = null;
        }
        // Clear hover animation frame
        if (hoverAnimationFrameRef.current) {
          cancelAnimationFrame(hoverAnimationFrameRef.current);
          hoverAnimationFrameRef.current = null;
        }
        // Clear refs to prevent memory leaks
        cosmographRef.current = null;
        lastClickedNodeRef.current = null;
        isIncrementalUpdateRef.current = false;
        lastResumeTimeRef.current = 0;
        pendingHoverRef.current = null;
      };
    }, []);

    // Create stable method refs
    const methodsRef = useRef({
      clearSelection: clearCosmographSelection,
      selectNode: selectCosmographNode,
      selectNodes: selectCosmographNodes,
      zoomIn,
      zoomOut,
      fitView,
      fitViewByIndices,
      zoomToPoint,
      trackPointPositionsByIndices,
      getTrackedPointPositionsMap,
      activateRectSelection,
      deactivateRectSelection,
      activatePolygonalSelection,
      deactivatePolygonalSelection,
      selectPointsInRect,
      selectPointsInPolygon,
      getConnectedPointIndices,
      getPointIndicesByExactValues,
      addIncrementalData,
      updateNodes,
      updateLinks,
      removeNodes,
      removeLinks,
      startSimulation,
      pauseSimulation,
      resumeSimulation,
      keepSimulationRunning
    });
    
    // Update methods ref when dependencies change
    useEffect(() => {
      methodsRef.current = {
        clearSelection: clearCosmographSelection,
        selectNode: selectCosmographNode,
        selectNodes: selectCosmographNodes,
        focusOnNodes,
        zoomIn,
        zoomOut,
        fitView,
        fitViewByIndices,
        zoomToPoint,
        trackPointPositionsByIndices,
        getTrackedPointPositionsMap,
        activateRectSelection,
        deactivateRectSelection,
        activatePolygonalSelection,
        deactivatePolygonalSelection,
        selectPointsInRect,
        selectPointsInPolygon,
        getConnectedPointIndices,
        getPointIndicesByExactValues,
        addIncrementalData,
        updateNodes,
        updateLinks,
        removeNodes,
        removeLinks,
        startSimulation,
        pauseSimulation,
        resumeSimulation,
        keepSimulationRunning
      };
    }, [
      clearCosmographSelection,
      selectCosmographNode,
      selectCosmographNodes,
      focusOnNodes,
      zoomIn,
      zoomOut,
      fitView,
      fitViewByIndices,
      zoomToPoint,
      trackPointPositionsByIndices,
      getTrackedPointPositionsMap,
      activateRectSelection,
      deactivateRectSelection,
      activatePolygonalSelection,
      deactivatePolygonalSelection,
      selectPointsInRect,
      selectPointsInPolygon,
      getConnectedPointIndices,
      getPointIndicesByExactValues,
      addIncrementalData,
      updateNodes,
      updateLinks,
      removeNodes,
      removeLinks,
      startSimulation,
      pauseSimulation,
      resumeSimulation,
      keepSimulationRunning,
      getLiveStats
    ]);
    
    // Expose methods to parent via ref with minimal dependencies
    React.useImperativeHandle(ref, () => ({
      clearSelection: clearCosmographSelection,
      selectNode: selectCosmographNode,
      selectNodes: selectCosmographNodes,
      focusOnNodes,
      zoomIn,
      zoomOut,
      fitView,
      fitViewByIndices,
      zoomToPoint,
      trackPointPositionsByIndices,
      getTrackedPointPositionsMap,
      activateRectSelection,
      deactivateRectSelection,
      activatePolygonalSelection,
      deactivatePolygonalSelection,
      selectPointsInRect,
      selectPointsInPolygon,
      getConnectedPointIndices,
      getPointIndicesByExactValues,
      addIncrementalData,
      updateNodes,
      updateLinks,
      removeNodes,
      removeLinks,
      startSimulation,
      pauseSimulation,
      resumeSimulation,
      keepSimulationRunning,
      setData: (nodes: GraphNode[], links: GraphLink[], runSimulation = true) => {
        if (cosmographRef.current && typeof cosmographRef.current.setData === 'function') {
          cosmographRef.current.setData(nodes, links, runSimulation);
        }
      },
      restart: () => {
        if (cosmographRef.current && typeof cosmographRef.current.restart === 'function') {
          cosmographRef.current.restart();
        }
      },
      getLiveStats,
      setIncrementalUpdateFlag: (enabled: boolean) => {
        isIncrementalUpdateRef.current = enabled;
      }
    }), [
      clearCosmographSelection,
      selectCosmographNode,
      selectCosmographNodes,
      focusOnNodes,
      zoomIn,
      zoomOut,
      fitView,
      fitViewByIndices,
      zoomToPoint,
      trackPointPositionsByIndices,
      getTrackedPointPositionsMap,
      activateRectSelection,
      deactivateRectSelection,
      activatePolygonalSelection,
      deactivatePolygonalSelection,
      selectPointsInRect,
      selectPointsInPolygon,
      getConnectedPointIndices,
      getPointIndicesByExactValues,
      addIncrementalData,
      updateNodes,
      updateLinks,
      removeNodes,
      removeLinks,
      startSimulation,
      pauseSimulation,
      resumeSimulation,
      keepSimulationRunning,
      getLiveStats
    ]);

    // Handle Cosmograph events with native selection methods and multi-selection
    // Cosmograph v2.0 onClick signature: (index: number | undefined, pointPosition: [number, number] | undefined, event: MouseEvent) => void
    const handleClick = async (index?: number, pointPosition?: [number, number], event?: MouseEvent) => {
      
      if (typeof index === 'number' && cosmographRef.current) {
        
        // Get the original node data using the index
        let originalNode: GraphNode | undefined;
        
        // First, try to get the actual node data from Cosmograph using the index
        // This ensures we get the correct node regardless of filtering or ordering
        if (typeof cosmographRef.current.getPointsByIndices === 'function') {
          try {
            const pointData = await cosmographRef.current.getPointsByIndices([index]);
            
            if (pointData && pointData.numRows && pointData.numRows > 0) {
              // Convert the point data to GraphNode format
              const pointArray = cosmographRef.current.convertCosmographDataToObject(pointData);
              if (pointArray && pointArray.length > 0) {
                const point = pointArray[0];
                // Use the node ID from the actual data to find the correct node in transformedData
                const nodeId = String(point.id);
                
                // Find the matching node in transformedData by ID, not by index
                originalNode = transformedData.nodes.find(n => n.id === nodeId);
                
                // If not found in transformedData, create from point data
                if (!originalNode) {
                  originalNode = {
                    id: nodeId,
                    label: String(point.label || point.id || index),
                    name: String(point.name || point.label || point.id),  // Include name field
                    node_type: String(point.node_type || 'Unknown'),
                    summary: point.summary || null,
                    size: Number(point.size || point.degree_centrality || 1),
                    properties: {
                      degree_centrality: Number(point.degree_centrality || 0),
                      pagerank_centrality: Number(point.pagerank_centrality || 0),
                      betweenness_centrality: Number(point.betweenness_centrality || 0),
                      eigenvector_centrality: Number(point.eigenvector_centrality || 0),
                      name: String(point.name || point.label || point.id),  // Include name in properties
                      ...point // Include all other properties
                    }
                  } as GraphNode;
                }
              }
            }
          } catch (error) {
            logger.error('Failed to retrieve point data from Cosmograph:', error);
          }
        }
        
        // Fallback: If we still don't have the node, try by index (less reliable)
        if (!originalNode && index >= 0 && index < transformedData.nodes.length) {
          originalNode = transformedData.nodes[index];
        }
        
        if (originalNode) {
          const currentTime = Date.now();
          const timeDiff = currentTime - lastClickTimeRef.current;
          const isDoubleClick = timeDiff < 300 && lastClickedNodeRef.current?.id === originalNode.id;
          
          // Clear any existing timeout
          if (doubleClickTimeoutRef.current) {
            clearTimeout(doubleClickTimeoutRef.current);
            doubleClickTimeoutRef.current = null;
          }
          
          // Use native Cosmograph selection methods
          if (event?.shiftKey || event?.ctrlKey || event?.metaKey) {
            // Multi-selection with shift/ctrl
            if (typeof cosmographRef.current.selectPoints === 'function') {
              // Get currently selected point indices
              const currentlySelectedIndices: number[] = [];
              if (typeof cosmographRef.current.getSelectedPointIndices === 'function') {
                const selected = cosmographRef.current.getSelectedPointIndices();
                if (selected) currentlySelectedIndices.push(...selected);
              }
              
              const isAlreadySelected = currentlySelectedIndices.includes(index);
              
              if (isAlreadySelected) {
                // Deselect the node - remove from selection
                const newSelection = currentlySelectedIndices.filter(i => i !== index);
                cosmographRef.current.selectPoints(newSelection);
              } else {
                // Add to selection
                cosmographRef.current.selectPoints([...currentlySelectedIndices, index]);
              }
            }
            
            // Highlight adjacent nodes if shift is held
            if (event?.shiftKey && typeof cosmographRef.current.getAdjacentNodes === 'function') {
              const adjacentNodes = cosmographRef.current.getAdjacentNodes(originalNode.id);
              if (adjacentNodes && adjacentNodes.length > 0) {
                logger.log(`Node ${originalNode.label} has ${adjacentNodes.length} adjacent nodes`);
              }
            }
            
            // Always call onNodeClick to show the info panel even with modifiers
            onNodeClick(originalNode);
          } else {
            // Handle single click or double click
            if (isDoubleClick) {
              // Double-click - select, focus, and zoom
              
              // Select the node
              if (typeof cosmographRef.current.selectPoint === 'function') {
                cosmographRef.current.selectPoint(index);
              } else if (typeof cosmographRef.current.selectPoints === 'function') {
                cosmographRef.current.selectPoints([index]);
              }
              
              // Focus the node (draws a ring around it)
              if (typeof cosmographRef.current.setFocusedPoint === 'function') {
                cosmographRef.current.setFocusedPoint(index);
              }
              
              // Center and zoom to the selected node
              zoomToPoint(index);
              
              // Track the selected node position
              trackPointPositionsByIndices([index]);
              
              // Log tracking info - position will be tracked
              logger.log(`Tracking node ${originalNode.label} (index: ${index})`);
              
              // Show the info panel
              onNodeClick(originalNode);
            } else {
              // Single click - wait to see if it's a double click
              doubleClickTimeoutRef.current = setTimeout(() => {
                // Single click confirmed - select and show info panel
                
                // Select the node
                if (typeof cosmographRef.current.selectPoint === 'function') {
                  cosmographRef.current.selectPoint(index);
                } else if (typeof cosmographRef.current.selectPoints === 'function') {
                  cosmographRef.current.selectPoints([index]);
                }
                
                // Track the selected node position for following during simulation
                trackPointPositionsByIndices([index]);
                
                // Focus the node (draws a ring around it) and optionally follow it
                if (typeof cosmographRef.current.setFocusedPoint === 'function') {
                  if (config.followSelectedNode) {
                    // Enable following - camera will track this node during simulation
                    cosmographRef.current.setFocusedPoint(index);
                  } else {
                    // Just highlight without following
                    cosmographRef.current.setFocusedPoint(index);
                  }
                }
                
                // Removed automatic zoom on node selection for now
                
                // Show the info panel
                onNodeClick(originalNode);
                
                // Show node details (popup removed - using NodeDetailsPanel instead)
                if (cosmographRef.current) {
                  // Clear any existing timeouts
                  if (popupTimeoutRef.current) {
                    clearTimeout(popupTimeoutRef.current);
                  }
                  
                  // CosmographPopup not available - details shown in NodeDetailsPanel
                  logger.log('Node double-clicked:', {
                    label: originalNode.label || originalNode.id,
                    type: originalNode.node_type,
                    connections: originalNode.properties?.degree,
                    pagerank: originalNode.properties?.pagerank_centrality
                  });
                }
              }, 300);
            }
          }
          
          // Update click tracking using refs (no re-render)
          lastClickTimeRef.current = currentTime;
          lastClickedNodeRef.current = originalNode;
          
          // Debug logging for click issues
          console.log('[GraphCanvas] Click handled - index:', index, 'nodeId:', originalNode.id, 'label:', originalNode.label);
        } else {
          logger.warn('Could not find or create node data for index:', index);
        }
      } else {
        // Empty space was clicked - clear all selections and return to default state
        // Clear any popup timeouts
        if (popupTimeoutRef.current) {
          clearTimeout(popupTimeoutRef.current);
        }
        
        if (cosmographRef.current) {
          // Clear selection using native methods
          if (typeof cosmographRef.current.unselectAll === 'function') {
            cosmographRef.current.unselectAll();
          } else if (typeof cosmographRef.current.unselectAllPoints === 'function') {
            cosmographRef.current.unselectAllPoints();
          } else if (typeof cosmographRef.current.selectPoints === 'function') {
            cosmographRef.current.selectPoints([]);
          }
          
          // Clear focused node and stop tracking
          if (typeof cosmographRef.current.unfocusNode === 'function') {
            cosmographRef.current.unfocusNode();
          } else if (typeof cosmographRef.current.setFocusedPoint === 'function') {
            cosmographRef.current.setFocusedPoint();
          }
          
          // Stop tracking positions
          if (typeof cosmographRef.current.trackPointPositionsByIndices === 'function') {
            cosmographRef.current.trackPointPositionsByIndices([]);
          }
          
          // Removed automatic fitView on empty space for now
        }
        onClearSelection?.();
      }
    };

    // Don't show individual loading state - unified loading screen handles it
    // Just render empty div while preparing to maintain layout
    if (isDataPreparing) {
      return <div className={`relative overflow-hidden ${className}`} />;
    }

    // Show error state if Data Kit failed (with fallback)
    if (dataKitError && !cosmographData) {
      return (
        <div className={`relative overflow-hidden ${className} flex items-center justify-center`}>
          <div className="text-destructive text-center">
            <p className="text-sm">Data preparation failed: {dataKitError}</p>
            <p className="text-xs text-muted-foreground mt-1">Using fallback rendering</p>
          </div>
        </div>
      );
    }

    // Don't render if no data is available and DuckDB is not initialized
    if (!cosmographData && !isDuckDBInitialized) {
      return (
        <div className={`relative overflow-hidden ${className} flex items-center justify-center`}>
          <div className="text-muted-foreground text-center">
            <p className="text-sm">No graph data available</p>
          </div>
        </div>
      );
    }

    
    // Pass Arrow tables directly to Cosmograph when using DuckDB
    // When not using DuckDB, cosmographData contains the points and links arrays directly
    const pointsData = useDuckDBTables ? duckDBData?.points : (cosmographData ? cosmographData.points : memoizedNodes);
    const linksData = useDuckDBTables ? duckDBData?.links : (cosmographData ? cosmographData.links : memoizedLinks);

    if (!pointsData) {
      return (
        <div className={`relative overflow-hidden ${className} flex items-center justify-center`}>
          <div className="text-muted-foreground text-center">
            <p className="text-sm">Waiting for data...</p>
          </div>
        </div>
      );
    }

    return (
      <div
        className={`relative overflow-hidden ${className}`}
        style={containerStyle}
      >
          <Cosmograph
            ref={cosmographRef}
            onMount={(cosmograph) => {
              console.log('[GraphCanvas] Cosmograph mounted, checking internals');
              // Store the actual Cosmograph instance
              if (cosmograph) {
                cosmographRef.current = cosmograph as any;
                
                // Try to access internal API directly or through a property
                const internalApi = (cosmograph as any)._internalApi || 
                                   (cosmograph as any).internal ||
                                   (cosmograph as any).api ||
                                   cosmograph;
                
                // Check if dataManager is available through various paths
                const dataManager = internalApi?.dataManager || 
                                   (cosmograph as any).dataManager ||
                                   (cosmograph as any).getDataManager?.();
                
                if (dataManager) {
                  console.log('[GraphCanvas] ✅ Found dataManager, storing reference');
                  (cosmographRef.current as any).dataManager = dataManager;
                } else {
                  console.log('[GraphCanvas] ⚠️ dataManager not found, available properties:', Object.keys(cosmograph));
                  console.log('[GraphCanvas] Cosmograph prototype:', Object.getOwnPropertyNames(Object.getPrototypeOf(cosmograph)));
                }
              }
            }}
            // Use DuckDB table names or prepared data
            points={pointsData}
            links={linksData}
            // Point configuration - use DuckDB column names when using DuckDB
            pointIdBy="id"
            pointIndexBy={useDuckDBTables ? "idx" : "index"}
            pointLabelBy="label"
            pointColorBy={useDuckDBTables ? "node_type" : pointColorBy}
            pointSizeBy={useDuckDBTables ? "size" : pointSizeBy}
            pointClusterBy={config.clusteringEnabled ? "cluster" : undefined}  // Use the cluster field we added to nodes
            pointClusterStrengthBy={config.clusteringEnabled ? "clusterStrength" : undefined}  // Use the clusterStrength field we added
            // Link configuration - use DuckDB column names when using DuckDB
            linkSourceBy="source"
            linkSourceIndexBy={useDuckDBTables ? "sourceidx" : "sourceIndex"}
            linkTargetBy="target"
            linkTargetIndexBy={useDuckDBTables ? "targetidx" : "targetIndex"}
            linkColorBy="edge_type"  // Required for linkColorByFn to work
            linkWidthBy={config.linkWidthBy || "weight"}
            
            // Override with UI-specific configurations
            fitViewOnInit={false} // Disable automatic fitView to prevent simulation interruption
            // fitViewDelay={1500} // Not needed when fitViewOnInit is false
            fitViewDuration={config.fitViewDuration}
            fitViewPadding={config.fitViewPadding}
            // initialZoomLevel={1.5} // Commented out - causing infinite zoom loop
            disableZoom={false}
            backgroundColor={config.backgroundColor}
            
            // Use Cosmograph v2.0 built-in color strategies
            pointColorStrategy={pointColorStrategy}
            pointColorPalette={pointColorPalette}
            pointColorByMap={config.nodeTypeColors}
            
            // Size configuration - keep normal sizing always
            pointSizeStrategy={'auto'}
            pointSizeRange={[config.minNodeSize * config.sizeMultiplier, config.maxNodeSize * config.sizeMultiplier]}
            
            // Interaction
            enableDrag={true}
            enableRightClickRepulsion={true}
            onClick={handleClick}
            onMouseMove={handleMouseMove}
            
            // Hover and focus styling from config
            hoveredPointCursor={config.hoveredPointCursor}
            renderHoveredPointRing={config.renderHoveredPointRing}
            hoveredPointRingColor={config.hoveredPointRingColor}
            
            // Selection ring colors for when nodes are selected via API
            focusedPointRingColor={config.nodeAccessHighlightColor}
            selectedPointRingColor={config.nodeAccessHighlightColor}
            renderFocusedPointRing={true}
            renderSelectedPointRing={true}
            renderLinks={config.renderLinks}
            
            // Zoom event handlers (debugging disabled for now)
            // onZoomStart={(e, userDriven) => {
            //   console.log('Zoom started', { userDriven, transform: e.transform });
            // }}
            // onZoom={(e, userDriven) => {
            //   console.log('Zooming', { userDriven, k: e.transform.k });
            // }}
            // onZoomEnd={(e, userDriven) => {
            //   console.log('Zoom ended', { userDriven, transform: e.transform });
            // }}
            
            nodeGreyoutOpacity={selectedNodes.length > 0 || highlightedNodes.length > 0 || glowingNodeIndices.length > 0 ? 0.1 : 1}
            
            // Performance
            pixelRatio={1}
            showFPSMonitor={config.showFPS}
            renderUnselectedNodesTransparency={config.pixelationThreshold > 0 ? Math.max(0.1, 1 - config.pixelationThreshold / 20) : 1}
            
            // Zoom behavior
            enableSimulationDuringZoom={true}
            
            // Simulation - Cosmograph v2.0 API
            enableSimulation={true} // Explicitly enable simulation
            spaceSize={config.spaceSize}
            randomSeed={config.randomSeed}
            simulationRepulsion={config.repulsion}
            simulationRepulsionTheta={config.simulationRepulsionTheta}
            simulationCluster={config.simulationCluster}
            simulationClusterStrength={config.simulationClusterStrength}
            simulationImpulse={config.simulationImpulse}
            simulationLinkSpring={config.linkSpring}
            simulationLinkDistance={config.linkDistance}
            simulationLinkDistRandomVariationRange={config.linkDistRandomVariationRange}
            simulationGravity={config.gravity}
            simulationCenter={config.centerForce}
            simulationFriction={config.friction}
            simulationDecay={config.simulationDecay}
            simulationRepulsionFromMouse={config.mouseRepulsion}
            
            // Link Properties - disable advanced features in performance mode
            linkColor={config.linkColor}
            linkColorByFn={config.performanceMode ? undefined : (config.linkColorScheme === 'uniform' && config.linkOpacityScheme === 'uniform' ? undefined : linkColorFn)}
            linkOpacity={config.linkOpacity}
            linkGreyoutOpacity={config.linkGreyoutOpacity}
            linkWidth={1}
            // linkWidthBy is already set above to 'weight'
            linkWidthByFn={config.performanceMode ? undefined : (config.linkWidthScheme === 'uniform' ? undefined : linkWidthFn)}
            linkWidthScale={config.linkWidth}
            linkWidthRange={[0.5, 5]} // Set link width range for auto scaling
            scaleLinksOnZoom={config.scaleLinksOnZoom}
            linkArrows={config.edgeArrows || config.linkArrows}
            linkArrowsSizeScale={config.edgeArrowScale || config.linkArrowsSizeScale}
            curvedLinks={config.performanceMode ? false : config.curvedLinks}
            curvedLinkSegments={config.performanceMode ? 10 : config.curvedLinkSegments}
            curvedLinkWeight={config.curvedLinkWeight}
            curvedLinkControlPointDistance={config.curvedLinkControlPointDistance}
            linkVisibilityDistanceRange={config.linkVisibilityDistance}
            linkVisibilityMinTransparency={config.linkVisibilityMinTransparency}
            useClassicQuadtree={config.useClassicQuadtree}
            
            // Label rendering with Cosmograph's optimized features
            showLabels={config.performanceMode ? false : config.renderLabels}
            showDynamicLabels={config.renderLabels && config.showDynamicLabels} // Auto-show evenly distributed visible labels
            showTopLabels={config.renderLabels && config.showTopLabels} // Show labels for most important nodes
            showTopLabelsLimit={config.showTopLabelsLimit || 100} // Limit to configurable number of nodes
            showLabelsFor={!config.renderLabels ? selectedNodes : undefined} // Show labels only for selected when labels are off
            
            // Label appearance
            pointLabelFontSize={config.labelSize}
            pointLabelClassName={'cosmograph-dynamic-label'}
            
            // Hovered label
            showHoveredPointLabel={config.showHoveredNodeLabel}
            hoveredPointLabelClassName={`
              background: ${config.hoveredLabelBackgroundColor};
              color: ${config.hoveredLabelColor};
              font-weight: ${config.hoveredLabelFontWeight};
              font-size: ${config.hoveredLabelSize}px;
              padding: 3px 6px;
              border-radius: 3px;
            `}
            
            // Label weights and margins
            staticLabelWeight={0.8}
            dynamicLabelWeight={0.7}
            labelMargin={5}
            labelPadding={[6.5, 4.5, 6.5, 4.5]}
          />
        
        {/* Performance Overlay */}
        {(config.showNodeCount || config.showDebugInfo) && (stats || liveStats) && (
          <div className="absolute top-4 left-4 glass text-xs text-muted-foreground p-2 rounded space-y-1">
            {config.showNodeCount && (
              <>
                <div>Nodes: {(liveStats?.nodeCount ?? stats?.total_nodes ?? 0).toLocaleString()}</div>
                <div>Edges: {(liveStats?.edgeCount ?? stats?.total_edges ?? 0).toLocaleString()}</div>
              </>
            )}
            {config.showDebugInfo && (
              <>
                {stats?.density !== undefined && (
                  <div>Density: {stats.density.toFixed(4)}</div>
                )}
                <div>Selected: {selectedNodes.length}</div>
                <div>Highlighted: {highlightedNodes.length}</div>
                <div>View: {config.queryType}</div>
                <div>Color: {config.colorScheme}</div>
                <div>Labels: {config.renderLabels ? 'On' : 'Off'}</div>
                <div>Physics: {config.disableSimulation ? 'Off' : 'On'}</div>
              </>
            )}
          </div>
        )}
      </div>
    );
  }
);

// Export the ref type for external use
export type GraphCanvasRef = GraphCanvasHandle;

// Export with React.memo to prevent unnecessary re-renders
export const GraphCanvas = React.memo(GraphCanvasComponent, (prevProps, nextProps) => {
  // Optimized comparison - only re-render for essential changes
  
  // Most important: check if data references changed (should be stable during incremental updates)
  const dataChanged = prevProps.nodes !== nextProps.nodes || prevProps.links !== nextProps.links;
  
  // Check callback functions by reference (they should be stable with useCallback)
  const callbacksChanged = prevProps.onNodeClick !== nextProps.onNodeClick ||
                           prevProps.onNodeSelect !== nextProps.onNodeSelect ||
                           prevProps.onClearSelection !== nextProps.onClearSelection ||
                           prevProps.onNodeHover !== nextProps.onNodeHover;
  
  // Simple reference comparison for selection arrays (should be stable)
  const selectedNodesChanged = prevProps.selectedNodes !== nextProps.selectedNodes;
  const highlightedNodesChanged = prevProps.highlightedNodes !== nextProps.highlightedNodes;
  
  // Stats and className changes
  const statsChanged = prevProps.stats !== nextProps.stats;
  const classNameChanged = prevProps.className !== nextProps.className;
  
  const shouldRerender = dataChanged || callbacksChanged || selectedNodesChanged || 
                        highlightedNodesChanged || statsChanged || classNameChanged;
  
  // Return true to skip re-render, false to re-render
  return !shouldRerender;
});

GraphCanvas.displayName = 'GraphCanvas';// Trigger rebuild with all changes Wed Aug  6 01:00:43 AM EDT 2025
