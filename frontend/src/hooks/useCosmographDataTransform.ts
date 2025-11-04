/**
 * useCosmographDataTransform Hook
 * 
 * Handles transformation of graph nodes and links into Cosmograph format.
 * Extracted from GraphCanvasV2 to improve testability and separation of concerns.
 */

import { useMemo, useRef } from 'react';
import { GraphNode, GraphLink } from '../types/graph';
import { 
  CosmographDataPreparer,
  getGlobalDataPreparer,
  sanitizeNode,
  sanitizeLink
} from '../utils/cosmographDataPreparer';

interface TransformConfig {
  clusteringMethod?: string;
  centralityMetric?: string;
  clusterStrength?: number;
}

interface CosmographData {
  nodes: any[];
  links: any[];
}

export const useCosmographDataTransform = (
  nodes: GraphNode[],
  links: GraphLink[],
  config: TransformConfig
): CosmographData => {
  // Reference to the data preparer (singleton pattern)
  const dataPreparerRef = useRef<CosmographDataPreparer>(
    getGlobalDataPreparer({
      clusteringMethod: config.clusteringMethod,
      centralityMetric: config.centralityMetric,
      clusterStrength: config.clusterStrength
    })
  );

  // Memoized transformation of nodes and links
  const cosmographData = useMemo(() => {
    const preparer = dataPreparerRef.current;
    
    // Reset preparer state for clean transformation
    preparer.reset();
    
    // Build index maps for efficient lookups
    const nodeIdToIndex = new Map<string, number>();
    const nodeTypeIndexMap = new Map<string, number>();
    
    // Transform nodes with sanitization
    const transformedNodes = nodes.map((node, index) => {
      nodeIdToIndex.set(node.id, index);
      
      // Track node type for color generation
      const nodeType = node.node_type || 'Unknown';
      if (!nodeTypeIndexMap.has(nodeType)) {
        nodeTypeIndexMap.set(nodeType, nodeTypeIndexMap.size);
      }
      
      // Sanitize and transform node for Cosmograph
      return sanitizeNode(node, index, {
        clusteringMethod: config.clusteringMethod,
        centralityMetric: config.centralityMetric,
        clusterStrength: config.clusterStrength,
        nodeTypeIndexMap
      });
    });
    
    // Transform links with sanitization and filtering
    const transformedLinks = links
      .map(link => sanitizeLink(link, nodeIdToIndex))
      .filter(link => link !== null);
    
    return {
      nodes: transformedNodes,
      links: transformedLinks
    };
  }, [nodes, links, config.clusteringMethod, config.centralityMetric, config.clusterStrength]);

  return cosmographData;
};
