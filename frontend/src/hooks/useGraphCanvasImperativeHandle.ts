/**
 * useGraphCanvasImperativeHandle
 * Extracted from GraphCanvasV2.tsx - encapsulates all imperative handle logic
 * including ref management, ref-sync effects, and the useImperativeHandle call.
 *
 * PERFORMANCE FIX (P3-2): Dependencies are stored in refs to avoid handle recreation.
 * Only setGlowingNodes (stable from useState) appears in the dependency array.
 */

import { useEffect, useRef, useImperativeHandle, type ForwardedRef, type RefObject } from 'react';
import type { CosmographRef } from '@cosmograph/react';
import type { GraphCanvasHandle } from '../types/graphCanvas';
import type { GraphNode, GraphLink } from '../types/graph';

/** Subset of config used by the imperative handle */
interface ImperativeHandleConfig {
  simulationEnabled?: boolean;
}

/** Statistics shape consumed by getLiveStats */
interface ImperativeHandleStatistics {
  nodeCount: number;
  edgeCount: number;
  lastUpdated: number;
}

export interface UseGraphCanvasImperativeHandleDeps {
  /** The forwarded ref from GraphCanvasV2 */
  ref: ForwardedRef<GraphCanvasHandle>;
  /** Cosmograph component ref */
  cosmographRef: RefObject<CosmographRef>;
  /** Current node→index map for O(1) lookups */
  nodeIndexMap: Map<string, number>;
  /** Current statistics snapshot */
  statistics: ImperativeHandleStatistics;
  /** Graph config (only simulationEnabled is read) */
  config: ImperativeHandleConfig;
  /** Current links array (used by removeLinks to resolve IDs) */
  links: GraphLink[];

  // Selection callbacks
  clearAllSelection: () => void;
  selectSingleNode: (id: string) => void;
  selectMultipleNodes: (ids: string[]) => void;

  // Data mutation callbacks
  setData: (nodes: GraphNode[], links: GraphLink[]) => void;
  addNodes: (nodes: GraphNode[]) => void;
  addLinks: (links: GraphLink[]) => void;
  updateNodes: (nodes: GraphNode[]) => void;
  updateLinks: (links: GraphLink[]) => void;
  removeNodes: (ids: string[]) => void;
  removeLinks: (links: GraphLink[]) => void;

  // Simulation
  reheat: (alpha: number) => void;

  // Glow effects (stable setter from useState)
  setGlowingNodes: (glowMap: Map<string, number>) => void;
}

/**
 * Encapsulates the entire imperative handle for GraphCanvasV2.
 * Call this hook inside the forwardRef component to expose the GraphCanvasHandle API.
 */
export function useGraphCanvasImperativeHandle(deps: UseGraphCanvasImperativeHandleDeps): void {
  const {
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
  } = deps;

  // PERFORMANCE FIX (P3-2): Store dependencies in refs to avoid handle recreation.
  // These refs are updated by the sync effect below and read by the imperative handle.
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
  const linksRef = useRef(links);

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
    linksRef.current = links;
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
      setDataRef.current(newNodes, newLinks);
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
      lastUpdated: statisticsRef.current.lastUpdated,
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
    getPointIndicesByExactValues: async (keyValues) => {
      // Cosmograph's getPointIndicesByExactValues returns a Promise
      // Our interface accepts Record<string, unknown> but we need to adapt
      // to Cosmograph's (column, values) signature
      const entries = Object.entries(keyValues);
      if (entries.length === 0) return undefined;
      const [column, value] = entries[0];
      const values = Array.isArray(value) ? value : [value];
      return cosmographRef.current?.getPointIndicesByExactValues?.(column, values as (string | number)[]);
    },

    // Incremental update methods - read from refs
    addIncrementalData: (newNodes: GraphNode[], newLinks: GraphLink[]) => {
      addNodesRef.current(newNodes);
      addLinksRef.current(newLinks);
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
      // Convert linkIds to GraphLink objects for the hook that expects GraphLink[]
      // linkIds are typically "source-target" format
      const linkIdSet = new Set(linkIds);
      const linksToRemove = linksRef.current.filter(link => {
        const linkId = `${link.source}-${link.target}`;
        return linkIdSet.has(linkId) || linkIdSet.has(link.source) || linkIdSet.has(link.target);
      });
      if (linksToRemove.length > 0) {
        removeLinksRef.current(linksToRemove);
      }
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
    getCosmographRef: () => cosmographRef,
  }), [setGlowingNodes]); // Only setGlowingNodes is needed - it's stable from useState
}
