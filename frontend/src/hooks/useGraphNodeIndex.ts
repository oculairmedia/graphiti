/**
 * useGraphNodeIndex Hook
 * Maintains a Map of node ID → array index for O(1) lookups
 * Extracted from GraphCanvasV2 for better separation of concerns (GRAPH-35)
 * 
 * PERFORMANCE FIX (GRAPH-36): Replaces O(n) findIndex calls with O(1) Map lookups
 */

import { useMemo } from 'react';
import { GraphNode } from '../api/types';

interface NodeIndexReturn {
  nodeIndexMap: Map<string, number>;
  getNodeIndex: (nodeId: string) => number | undefined;
  getNodeIndices: (nodeIds: string[]) => number[];
}

export function useGraphNodeIndex(nodes: GraphNode[] | null | undefined): NodeIndexReturn {
  // Create node ID → index Map for O(1) lookups
  const nodeIndexMap = useMemo(() => {
    const map = new Map<string, number>();
    if (nodes) {
      nodes.forEach((node, index) => {
        map.set(node.id, index);
      });
    }
    return map;
  }, [nodes]);
  
  // Get single node index - O(1)
  const getNodeIndex = useMemo(() => {
    return (nodeId: string): number | undefined => {
      return nodeIndexMap.get(nodeId);
    };
  }, [nodeIndexMap]);
  
  // Get multiple node indices - O(m) where m is number of nodeIds
  const getNodeIndices = useMemo(() => {
    return (nodeIds: string[]): number[] => {
      const indices: number[] = [];
      nodeIds.forEach(nodeId => {
        const index = nodeIndexMap.get(nodeId);
        if (index !== undefined) {
          indices.push(index);
        }
      });
      return indices;
    };
  }, [nodeIndexMap]);
  
  return {
    nodeIndexMap,
    getNodeIndex,
    getNodeIndices
  };
}
