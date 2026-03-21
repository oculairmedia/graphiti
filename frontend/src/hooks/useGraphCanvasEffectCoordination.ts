import { useEffect, type RefObject } from 'react';
import type { CosmographRef } from '@cosmograph/react';
import type { GraphNode, GraphLink } from '../types/graph';

interface CosmographData {
  nodes: GraphNode[];
  links: GraphLink[];
}

interface LoadingCoordinator {
  getStageStatus: (stage: string) => string;
  setStageComplete: (stage: string, data: Record<string, unknown>) => void;
}

export interface UseGraphCanvasEffectCoordinationDeps {
  cosmographRef: RefObject<CosmographRef>;
  cosmographData: CosmographData | null;
  highlightedNodes: string[];
  selectedNodes: string[];
  nodes: GraphNode[];
  links: GraphLink[];
  nodeIndexMap: Map<string, number>;
  selectedNodeIds: Set<string>;
  config: {
    disableSimulation?: boolean;
    repulsion?: number;
    linkSpring?: number;
    linkDistance?: number;
    gravity?: number;
    centerForce?: number;
    friction?: number;
    simulationDecay?: number;
    simulationCluster?: number;
    mouseRepulsion?: number;
    simulationRepulsionTheta?: number;
    clusteringEnabled?: boolean;
    clusterStrength?: number;
    fitViewOnInit?: boolean;
    fitViewDelay?: number;
    fitViewDuration?: number;
    fitViewPadding?: number;
  };
  loadingCoordinator: LoadingCoordinator;

  highlightNodeVisuals: (nodeIds: string[], duration: number) => void;
  selectSingleNode: (id: string) => void;
  deselectNode: (id: string) => void;
  updateStatistics: (nodes: GraphNode[], links: GraphLink[], mode: string) => void;
  resetCounts: (nodeCount: number, edgeCount: number) => void;
  onContextReady?: (isReady: boolean) => void;
  setIsReady: (ready: boolean) => void;
  setIsCanvasReady: (ready: boolean) => void;
}

export function useGraphCanvasEffectCoordination(deps: UseGraphCanvasEffectCoordinationDeps): void {
  const {
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
  } = deps;

  // Sync highlighted nodes → Cosmograph visual selection
  // PERFORMANCE FIX (GRAPH-36): O(1) lookup per node instead of O(n) findIndex
  useEffect(() => {
    if (highlightedNodes && highlightedNodes.length > 0 && cosmographRef.current && nodes) {
      const indices: number[] = [];
      highlightedNodes.forEach(nodeId => {
        const index = nodeIndexMap.get(nodeId);
        if (index !== undefined) indices.push(index);
      });

      if (indices.length > 0) {
        if (cosmographRef.current.selectPoints) {
          cosmographRef.current.selectPoints(indices, false);
        }
        if (cosmographRef.current.fitViewByIndices) {
          cosmographRef.current.fitViewByIndices(indices, 500, 0.1);
        }
      }

      highlightNodeVisuals(highlightedNodes, 2000);
    } else if (highlightedNodes && highlightedNodes.length === 0 && cosmographRef.current) {
      if (cosmographRef.current.unselectAllPoints) {
        cosmographRef.current.unselectAllPoints();
      }
    }
  }, [highlightedNodes, highlightNodeVisuals, nodes, nodeIndexMap]);

  // Sync selectedNodes prop → internal selection state
  // PERFORMANCE FIX: Set operations instead of Array.includes (O(1) vs O(n))
  useEffect(() => {
    if (selectedNodes && Array.isArray(selectedNodes) && selectedNodeIds) {
      const selectedSet = new Set(selectedNodes);

      for (const id of selectedNodes) {
        if (!selectedNodeIds.has(id)) {
          selectSingleNode(id);
        }
      }

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
      cosmographRef.current.restart?.();
      cosmographRef.current.start?.(1.0);
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
    config.clusterStrength,
  ]);

  // Notify when context is ready (500ms delay for Cosmograph initialization)
  useEffect(() => {
    const timer = setTimeout(() => {
      if (onContextReady && cosmographRef.current && cosmographData?.nodes?.length > 0) {
        onContextReady(true);
        setIsReady(true);
        setIsCanvasReady(true);
      }
    }, 500);

    return () => clearTimeout(timer);
  }, [cosmographData?.nodes?.length]); // eslint-disable-line react-hooks/exhaustive-deps

  // FitView after simulation settles
  useEffect(() => {
    if (cosmographRef.current && cosmographData?.nodes?.length > 0 && config.fitViewOnInit !== false) {
      const fitDelay = config.fitViewDelay || 1500;

      const fitTimer = setTimeout(() => {
        if (cosmographRef.current?.fitView) {
          cosmographRef.current.fitView(
            config.fitViewDuration || 1000,
            config.fitViewPadding !== undefined ? config.fitViewPadding : 0.2,
          );
        }
      }, fitDelay);

      return () => clearTimeout(fitTimer);
    }
  }, [cosmographData?.nodes?.length, config.fitViewOnInit, config.fitViewDelay, config.fitViewDuration, config.fitViewPadding]);

  // Mark loading stages complete when cosmograph data is ready
  useEffect(() => {
    if (cosmographData) {
      resetCounts(cosmographData.nodes?.length || 0, cosmographData.links?.length || 0);

      if (loadingCoordinator.getStageStatus('dataPreparation') !== 'complete') {
        loadingCoordinator.setStageComplete('dataPreparation', {
          nodesCount: cosmographData.nodes?.length || 0,
          linksCount: cosmographData.links?.length || 0,
        });
      }

      if (loadingCoordinator.getStageStatus('canvas') !== 'complete') {
        loadingCoordinator.setStageComplete('canvas', {
          canvasReady: true,
          hasData: (cosmographData.nodes?.length || 0) > 0,
        });
      }
    }
  }, [cosmographData?.nodes?.length, cosmographData?.links?.length, resetCounts]); // eslint-disable-line react-hooks/exhaustive-deps
}
